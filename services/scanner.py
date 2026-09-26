"""Plan 2: bounded A.I.G task orchestration in the MCP Gateway process.

The upstream v4.6.3 task API is asynchronous. Accepted tasks are evidence,
never tool approvals. Only deployment-owned target names can be submitted.
"""
import asyncio
from collections import Counter
import hmac
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from services.shared import authenticate, emit

router = APIRouter(tags=["Scan Orchestrator"])
AIG_TASK_PATH = "/api/v1/app/taskapi"
MAX_AIG_RESPONSE = 4 * 1024 * 1024
MAX_TRIVY_REPORT = 16 * 1024 * 1024


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def allowed_target(name):
    try:
        targets = json.loads(os.environ.get("TEST_TARGETS", "{}"))
        if not isinstance(targets, dict):
            raise ValueError("Expected target map")
        target = targets.get(name)
        if target is None:
            raise HTTPException(400, "Unknown Security Test Zone target")
        if not isinstance(target, str):
            raise ValueError("Target must be a URL")
        parsed = urlsplit(target)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError("Invalid configured target")
        return target
    except (ValueError, TypeError):
        raise HTTPException(503, "Invalid Security Test Zone configuration") from None


def model_configuration():
    model, token = os.getenv("AIG_SCAN_MODEL", ""), os.getenv("AIG_SCAN_MODEL_TOKEN", "")
    if bool(model) != bool(token):
        raise HTTPException(503, "A.I.G model name and LLM token must be configured together")
    if not model:
        return None  # A.I.G may already own a configured default model.
    return {"model": model, "token": token,
            "base_url": os.getenv("AIG_SCAN_MODEL_BASE_URL", "https://api.openai.com/v1")}


async def aig_call(request, method, path, payload=None):
    base = os.getenv("AIG_BASE_URL", "http://aig-web:8088").rstrip("/")
    headers = {"username": os.getenv("AIG_USERNAME", "public_user")}
    # Official CLI supports this header. v4.6.3 OSS does not validate it, so
    # actual ingress protection is our admin JWT and isolated Docker network.
    if os.getenv("AIG_API_KEY"):
        headers["API-KEY"] = os.environ["AIG_API_KEY"]
    try:
        async with request.app.state.client.stream(
                method, base + AIG_TASK_PATH + path, json=payload,
                headers=headers, timeout=20, follow_redirects=False) as response:
            response.raise_for_status()
            parts, size = [], 0
            async for part in response.aiter_bytes():
                size += len(part)
                if size > MAX_AIG_RESPONSE:
                    raise HTTPException(502, "A.I.G response exceeds 4 MiB")
                parts.append(part)
            envelope = json.loads(b"".join(parts))
        if not isinstance(envelope, dict) or envelope.get("status") != 0:
            message = envelope.get("message", "") if isinstance(envelope, dict) else ""
            if isinstance(message, str) and any(s in message for s in ("model.token", "default model", "model configured")):
                raise HTTPException(503, "A.I.G requires a configured model and LLM credentials")
            raise HTTPException(502, "A.I.G rejected the scan operation")
        return envelope.get("data")
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(502, "A.I.G scan service unavailable") from None


def session_id(value):
    try:
        if not isinstance(value, str):
            raise ValueError("Session must be a string")
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise HTTPException(400, "Expected an A.I.G session UUID") from None


@router.post("/scans", status_code=202)
async def submit_scan(body: ScanRequest, request: Request):
    claims = await authenticate(request, admin=True)
    content = {"prompt": allowed_target(body.target), "thread": 1, "language": "en"}
    model = model_configuration()
    if model:
        content["model"] = model
    data = await aig_call(request, "POST", "/tasks", {"type": "mcp_scan", "content": content})
    if not isinstance(data, dict):
        raise HTTPException(502, "Invalid A.I.G submission response")
    try:
        sid = session_id(data.get("session_id"))
    except HTTPException:
        raise HTTPException(502, "Invalid A.I.G session ID") from None
    emit("mcp-gateway", "scan", {"server": body.target, "status": "submitted",
                                 "subject": claims["sub"], "session_id": sid})
    return {"session_id": sid, "status": "submitted", "approval": "unchanged"}


@router.get("/scans/{scan_id}")
async def get_scan(scan_id: str, request: Request):
    await authenticate(request, admin=True)
    sid = session_id(scan_id)
    data = await aig_call(request, "GET", "/status/" + sid)
    if not isinstance(data, dict) or not isinstance(data.get("status"), str):
        raise HTTPException(502, "Invalid A.I.G task status")
    status = data["status"]
    result = None
    if status in {"done", "completed"}:
        result = await aig_call(request, "GET", "/result/" + sid)
    emit("mcp-gateway", "scan", {"status": status, "session_id": sid})
    # Logs may contain model credentials and remote tool payloads. The authorized
    # administrator receives the report, while telemetry keeps only metadata.
    return {"session_id": sid, "status": status, "result": result, "approval": "unchanged"}


def trivy_summary(path):
    with path.open("rb") as report:
        raw = report.read(MAX_TRIVY_REPORT + 1)
    if len(raw) > MAX_TRIVY_REPORT:
        raise ValueError("Trivy report is too large")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("SchemaVersion") != 2:
        raise ValueError("Expected a Trivy schema 2 report")
    results = document.get("Results", [])
    if not isinstance(results, list):
        raise ValueError("Invalid Trivy results")
    severity, types = Counter(), Counter()
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Invalid Trivy result")
        for kind in ("Vulnerabilities", "Misconfigurations", "Secrets"):
            findings = result.get(kind) or []
            if not isinstance(findings, list):
                raise ValueError("Invalid Trivy findings")
            for finding in findings:
                if not isinstance(finding, dict):
                    raise ValueError("Invalid Trivy finding")
                # No matched secret, source path, description, or raw report is emitted.
                level = finding.get("Severity", "UNKNOWN")
                level = level if level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "UNKNOWN"
                severity[level] += 1
                types[kind] += 1
    return {"scanner": "Trivy", "finding_count": sum(types.values()),
            "severities": dict(severity), "types": dict(types), "approval": "unchanged"}


@router.post("/scans/trivy-result")
async def ingest_trivy_result(request: Request):
    secret = os.getenv("SERVICE_TOKEN", "")
    if not secret or not hmac.compare_digest(request.headers.get("x-service-token", "").encode(), secret.encode()):
        raise HTTPException(401, "Security Test Zone service authentication required")
    # The request cannot choose a file or submit findings: only a mounted report
    # produced by the deployment-owned Trivy job is accepted.
    try:
        summary = await asyncio.to_thread(trivy_summary, Path(os.getenv("TRIVY_REPORT_PATH", "/scan-reports/trivy.json")))
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "A completed valid Trivy report is required") from None
    emit("mcp-gateway", "scan", {"server": "security-test-zone", "status": "trivy_reported",
                                 "finding_count": summary["finding_count"]})
    return summary
