from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from pydantic import BaseModel, Field

from app.policy_core import APPROVED_TOOL, PATH_CLASSES, classify_path, scan_catalog, sha256, verify_assertion


if not isinstance(trace.get_tracer_provider(), TracerProvider):
    trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer("container-policy-gateway")

MOCK_MCP_URL = os.getenv("MOCK_MCP_URL", "http://mock-mcp:9000")
OPA_URL = os.getenv("OPA_URL", "http://opa:8181/v1/data/mcp/authz/decision")
MCP_GATEWAY_TOKEN = os.getenv("MCP_GATEWAY_TOKEN", "lab-upstream-only")
ASSERTION_SECRET = os.getenv("AGENT_ASSERTION_SECRET", "lab-assertion-only")
AUDIT_FILE = Path(os.getenv("AUDIT_FILE", "/runtime/gateway.jsonl"))
APPROVED_SCHEMA = APPROVED_TOOL["input_schema"]
APPROVED_SCHEMA_HASH = sha256(APPROVED_SCHEMA)


class ToolCall(BaseModel):
    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    server_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]


app = FastAPI(title="Container Policy Gateway")


def now() -> str:
    return datetime.now(UTC).isoformat()


def append_audit(event: dict[str, Any]) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def result(
    call: ToolCall,
    *,
    decision: str,
    policy_id: str,
    reason: str,
    trace_id: str,
    upstream_called: bool,
    data_class: str | None = None,
    upstream: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": call.request_id,
        "trace_id": trace_id,
        "decision": decision,
        "policy_id": policy_id,
        "reason": reason,
        "data_class": data_class,
        "upstream_called": upstream_called,
        "upstream": upstream,
    }


async def upstream_catalog() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=4) as client:
        response = await client.get(
            f"{MOCK_MCP_URL}/tools/list", headers={"X-Gateway-Token": MCP_GATEWAY_TOKEN}
        )
        response.raise_for_status()
        tools = response.json()["tools"]
    if not isinstance(tools, list):
        raise ValueError("upstream catalog is not a tool list")
    return tools


async def opa_decision(input_document: dict[str, Any]) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=4) as client:
        response = await client.post(OPA_URL, json={"input": input_document})
        response.raise_for_status()
    decision = response.json().get("result")
    if not isinstance(decision, dict):
        raise ValueError("OPA returned no decision")
    return {key: str(value) for key, value in decision.items()}


@app.get("/health")
async def health() -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get("http://opa:8181/health")
            response.raise_for_status()
    except httpx.HTTPError:
        return JSONResponse({"status": "waiting-for-opa"}, status_code=503)
    return JSONResponse({"status": "ok", "approved_schema_sha256": APPROVED_SCHEMA_HASH})


@app.get("/audit/{request_id}")
async def audit_for_request(request_id: str) -> dict[str, Any]:
    if not AUDIT_FILE.exists():
        return {"events": []}
    events = [
        json.loads(line)
        for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines()
        if line and json.loads(line).get("request_id") == request_id
    ]
    return {"events": events}


@app.post("/tool-call")
async def tool_call(
    call: ToolCall,
    x_agent_role: str | None = Header(default=None),
    x_agent_assertion: str | None = Header(default=None),
) -> JSONResponse:
    with tracer.start_as_current_span("gateway.policy_check") as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        call_dict = call.model_dump()
        data_class = classify_path(str(call.arguments.get("path", "")))

        if not verify_assertion(call_dict, x_agent_role or "", x_agent_assertion, ASSERTION_SECRET):
            output = result(
                call,
                decision="DENY",
                policy_id="P-IDENTITY-001",
                reason="missing or invalid agent assertion",
                trace_id=trace_id,
                upstream_called=False,
                data_class=data_class,
            )
        elif call.server_id != "file-mcp" or call.tool_name != "read_file" or not data_class:
            output = result(
                call,
                decision="DENY",
                policy_id="P-INPUT-001",
                reason="server, tool, or path is outside the approved contract",
                trace_id=trace_id,
                upstream_called=False,
                data_class=data_class,
            )
        else:
            try:
                catalog = scan_catalog(await upstream_catalog())
                policy_input = {
                    "principal": {"role": x_agent_role},
                    "resource": {"data_class": data_class},
                    "tool": {"action": "r"},
                    "contract": {
                        "valid": True,
                        "schema_hash_match": catalog["schema_hash_match"],
                    },
                    "catalog": catalog,
                }
                decision = await opa_decision(policy_input)
                output = result(
                    call,
                    decision=decision["decision"],
                    policy_id=decision["policy_id"],
                    reason=decision["reason"],
                    trace_id=trace_id,
                    upstream_called=False,
                    data_class=data_class,
                )
            except (httpx.HTTPError, KeyError, ValueError) as error:
                output = result(
                    call,
                    decision="DENY",
                    policy_id="P-CONTROL-001",
                    reason=f"control-plane lookup failed: {type(error).__name__}",
                    trace_id=trace_id,
                    upstream_called=False,
                    data_class=data_class,
                )

        if output["decision"] == "ALLOW":
            try:
                async with httpx.AsyncClient(timeout=4) as client:
                    response = await client.post(
                        f"{MOCK_MCP_URL}/tools/read-file",
                        headers={"X-Gateway-Token": MCP_GATEWAY_TOKEN},
                        json={
                            "request_id": call.request_id,
                            "tool_call_id": call.tool_call_id,
                            "path": call.arguments["path"],
                        },
                    )
                    response.raise_for_status()
                output["upstream_called"] = True
                output["upstream"] = response.json()
            except httpx.HTTPError as error:
                output["decision"] = "DENY"
                output["policy_id"] = "P-UPSTREAM-001"
                output["reason"] = f"approved request could not reach upstream: {type(error).__name__}"

        append_audit(
            {
                "timestamp": now(),
                "event_id": str(uuid.uuid4()),
                "principal_role": x_agent_role,
                "server_id": call.server_id,
                "tool_name": call.tool_name,
                "arguments_sha256": sha256(call.arguments),
                **output,
            }
        )
        return JSONResponse(output)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from app import test_policy  # noqa: F401
    else:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=8080)
