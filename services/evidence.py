"""OTLP collection, normalization, analysis, decision and audit boundaries."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import database as db
from .shared import authenticate


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await db.close()


def app(name: str) -> FastAPI:
    result = FastAPI(title=name, lifespan=lifespan)

    @result.get("/health")
    async def health():
        return {"status": "ok", "service": name}

    return result


processor = app("Evidence Processor")
analyzer = app("Evidence Analyzer")
decision = app("Evidence Decision API")
audit = app("Audit API")


def internal(request: Request) -> None:
    expected = os.getenv("SERVICE_TOKEN", "")
    supplied = request.headers.get("X-Service-Token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Service authentication required")


def value(item: dict) -> Any:
    if "stringValue" in item:
        return item["stringValue"]
    if "intValue" in item:
        return int(item["intValue"])
    if "doubleValue" in item:
        return float(item["doubleValue"])
    if "boolValue" in item:
        return bool(item["boolValue"])
    if "arrayValue" in item:
        return [value(v) for v in item["arrayValue"].get("values", [])]
    return None


def attributes(items: list[dict]) -> dict:
    return {item["key"]: value(item.get("value", {})) for item in items if isinstance(item.get("key"), str)}


# Whitelisting preserves routing/decision metadata while excluding bearer tokens,
# raw arguments, result content and arbitrary span attributes before persistence.
SAFE_KEYS = {"server", "tool", "hash", "approved", "status", "decision", "kind", "finding_count",
             "presidio.finding_count", "presidio.entity_types", "mcp.server", "mcp.tool", "tool.hash",
             "http.status_code", "http.response.status_code", "error.type"}


def clean(data: dict) -> dict:
    result = {}
    for key in SAFE_KEYS:
        item = data.get(key)
        if isinstance(item, (str, int, float, bool)) and not isinstance(item, bytes):
            result[key] = item[:250] if isinstance(item, str) else item
        elif key == "presidio.entity_types" and isinstance(item, list):
            result[key] = [v[:80] for v in item[:100] if isinstance(v, str)]
    entities = data.get("entities")
    if isinstance(entities, list):
        result["presidio.entity_types"] = [v[:80] for v in entities[:100] if isinstance(v, str)]
    findings = data.get("findings")
    if isinstance(findings, list):
        result["finding_count"] = len(findings)
        result["presidio.entity_types"] = sorted({str(v.get("entity_type", "unknown"))[:80]
                                                   for v in findings if isinstance(v, dict)})
    return result


def normalize(payload: dict) -> list[dict]:
    output = []
    for resource in payload.get("resourceSpans", []):
        service = attributes(resource.get("resource", {}).get("attributes", [])).get("service.name", "unknown")
        if not isinstance(service, str):
            service = "unknown"
        for scope in resource.get("scopeSpans", resource.get("instrumentationLibrarySpans", [])):
            for span in scope.get("spans", []):
                trace_id, span_id = span.get("traceId"), span.get("spanId")
                if not isinstance(trace_id, str) or not isinstance(span_id, str) or not trace_id or not span_id:
                    raise ValueError("Every span requires traceId and spanId")
                attrs = attributes(span.get("attributes", []))
                raw = attrs.get("evidence.data", "{}")
                data = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(data, dict):
                    data = {}
                metadata = clean({**attrs, **data})
                kind = attrs.get("evidence.kind", data.get("kind", span.get("name", "trace")))
                output.append({"trace_id": trace_id[:128], "span_id": span_id[:128],
                               "service": service[:250], "kind": str(kind)[:100],
                               "data": metadata, "failed": span.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")})
    return output


def evaluate(event: dict) -> tuple[str, list[str]]:
    data = event.get("data", {})
    flags = []
    status = str(data.get("status", data.get("decision", ""))).lower()
    if event.get("failed") or status in {"error", "failed", "blocked", "block", "denied"}:
        flags.append("execution-failed-or-blocked")
    count = data.get("presidio.finding_count", data.get("finding_count", 0))
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 0
    if count > 0:
        flags.append("presidio-findings")
    if "drift" in event.get("kind", "").lower():
        flags.append("tool-contract-drift")
    risk = "high" if "tool-contract-drift" in flags or count > 0 else "medium" if flags else "low"
    return risk, flags


@processor.post("/v1/traces")
async def traces(request: Request):
    internal(request)
    try:
        payload = await request.json()
        if not isinstance(payload, dict) or "resourceSpans" not in payload:
            raise ValueError("resourceSpans is required")
        rows = normalize(payload)
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise HTTPException(422, "Invalid OTLP JSON payload") from exc
    for event in rows:
        stored = await db.ingest(event)
        if stored.get("analyzed_at") is None:
            try:
                async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                    response = await client.post(os.environ["ANALYZER_URL"].rstrip("/") + "/analyze",
                                                 headers={"X-Service-Token": os.environ["SERVICE_TOKEN"]},
                                                 json={"event_id": stored["id"]})
                    response.raise_for_status()
            except (httpx.HTTPError, KeyError) as exc:
                raise HTTPException(503, "Evidence analysis unavailable; retry this batch") from exc
    return {}


class Analysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: int = Field(gt=0)


@analyzer.post("/analyze")
async def analyze_event(body: Analysis, request: Request):
    internal(request)
    row = await db.event(body.event_id)
    if row is None:
        raise HTTPException(404, "Evidence not found")
    risk, flags = evaluate(row["payload"])
    return await db.analyze(body.event_id, risk, flags)


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    tool: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    definition: dict


@decision.post("/tools/register")
async def register_tool(body: Registration, request: Request):
    internal(request)
    digest = hashlib.sha256(json.dumps(body.definition, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return await db.register(body.server, body.tool, digest, body.definition)


@decision.get("/tools")
async def decision_tools(request: Request):
    internal(request)
    return {"tools": await db.tools()}


@decision.get("/tools/{server}/{tool}")
async def decision_tool(server: str, tool: str, request: Request):
    internal(request)
    row = await db.tool(server, tool)
    return row if row is not None else {"server": server, "tool": tool, "approved": False, "hash": None}


@audit.get("/events")
async def audit_events(request: Request, limit: int = 100):
    await authenticate(request)
    return {"events": await db.events(max(1, min(limit, 500)))}


@audit.get("/tools")
async def audit_tools(request: Request):
    await authenticate(request)
    return {"tools": await db.tools()}


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: StrictBool


@audit.put("/tools/{server}/{tool}")
async def approve_tool(server: str, tool: str, body: Approval, request: Request):
    claims = await authenticate(request, admin=True)
    row = await db.approve(server, tool, body.approved, str(claims.get("sub", "admin")))
    if row is None:
        raise HTTPException(404, "Tool not found")
    return row
