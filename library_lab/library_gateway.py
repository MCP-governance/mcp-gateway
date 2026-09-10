"""FastAPI Gateway that authorizes a public MCP server through an isolated runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import casbin
from fastapi import FastAPI, Header
from fastapi.responses import HTMLResponse, JSONResponse
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
POLICY_VERSION = "casbin-public-time-v1"
PUBLIC_MCP_PYTHON = os.environ.get("PUBLIC_MCP_PYTHON", sys.executable)
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("mcp-library-lab.gateway")
enforcer = casbin.Enforcer(str(ROOT / "casbin_model.conf"), str(ROOT / "casbin_policy.csv"))
audit_events: list[dict] = []
app = FastAPI(title="MCP library integration lab")


class TimeRequest(BaseModel):
    timezone: str = Field(default="Asia/Seoul", min_length=1, max_length=64)


class GatewayResult(BaseModel):
    trace_id: str
    decision: str
    policy_id: str
    reason: str
    upstream_called: bool
    result: dict | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(event: dict) -> None:
    audit_events.append(event)
    del audit_events[:-30]


def page() -> str:
    return """<!doctype html><meta charset="utf-8"><title>Library MCP Gateway Lab</title>
<style>body{font:15px system-ui;background:#f3f6fa;color:#17213a;max-width:900px;margin:30px auto;padding:0 16px}.box{background:#fff;border:1px solid #d9e0ea;border-radius:10px;padding:18px;margin:14px 0}select,button{font:inherit;padding:8px;margin:4px}button{background:#195cff;color:#fff;border:0;border-radius:6px;font-weight:700}pre{white-space:pre-wrap;background:#111827;color:#dbe7ff;padding:12px;border-radius:7px}.allow{color:#087a3d}.deny{color:#b4232d}</style>
<h1>오픈소스 MCP 라이브러리 실습</h1><p>FastAPI → Pydantic → Casbin → 공개 <code>mcp-server-time</code> → OpenTelemetry 콘솔 trace</p>
<div class="box"><label>역할 <select id="role"><option>customer</option><option>employee</option><option>admin</option><option value="guest">guest (차단 확인)</option></select></label><label>시간대 <select id="timezone"><option>Asia/Seoul</option><option>UTC</option><option>America/New_York</option></select></label><button onclick="callTime()">공개 MCP 시간 조회</button></div>
<div class="box"><b id="state">대기</b><pre id="result">버튼을 누르세요.</pre></div><div class="box"><h2>Gateway 감사 로그</h2><pre id="audit">불러오는 중...</pre></div>
<script>const $=id=>document.getElementById(id);async function refresh(){const data=await fetch('/audit').then(r=>r.json());$('audit').textContent=JSON.stringify(data.events,null,2)}async function callTime(){const res=await fetch('/time',{method:'POST',headers:{'Content-Type':'application/json','X-User-Role':$('role').value},body:JSON.stringify({timezone:$('timezone').value})});const body=await res.json();$('state').textContent=body.decision+' — '+body.reason;$('state').className=body.decision==='ALLOW'?'allow':'deny';$('result').textContent=JSON.stringify(body,null,2);refresh()}refresh();</script>"""


@app.get("/", response_class=HTMLResponse)
def gui() -> str:
    return page()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "role": "library-gateway", "policy_version": POLICY_VERSION}


@app.get("/audit")
def audit() -> dict:
    return {"count": len(audit_events), "events": audit_events}


@app.post("/time", response_model=GatewayResult)
def get_time(request: TimeRequest, x_user_role: str = Header(default="customer")) -> JSONResponse:
    trace_id = uuid.uuid4().hex
    event = {"trace_id": trace_id, "role": x_user_role, "data_class": "public", "required_permission": "r", "tool": "mcp-server-time.get_current_time", "policy_version": POLICY_VERSION, "at": now()}
    with tracer.start_as_current_span("gateway.decision") as span:
        span.set_attribute("mcp.trace_id", trace_id)
        span.set_attribute("mcp.role", x_user_role)
        if x_user_role not in {"customer", "employee", "admin"} or not enforcer.enforce(x_user_role, "public", "r"):
            event.update({"decision": "DENY", "policy_id": "P-CASBIN-001", "reason": "role lacks r permission for public data", "upstream_called": False})
            record(event)
            return JSONResponse(GatewayResult(**event).model_dump(), status_code=403)
        try:
            with tracer.start_as_current_span("public_mcp.call") as upstream_span:
                upstream_span.set_attribute("mcp.server", "mcp-server-time")
                completed = subprocess.run([PUBLIC_MCP_PYTHON, str(ROOT / "public_time_probe.py"), request.timezone], capture_output=True, text=True, timeout=15, check=True)
                result = json.loads(completed.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
            event.update({"decision": "DENY", "policy_id": "P-UPSTREAM-001", "reason": str(exc), "upstream_called": False})
            record(event)
            return JSONResponse(GatewayResult(**event).model_dump(), status_code=502)
        event.update({"decision": "ALLOW", "policy_id": "P-CASBIN-ALLOW-001", "reason": "Casbin allowed public read", "upstream_called": True, "result": result})
        record(event)
        return JSONResponse(GatewayResult(**event).model_dump())
