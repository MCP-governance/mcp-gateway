from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from pydantic import BaseModel, Field


if not isinstance(trace.get_tracer_provider(), TracerProvider):
    trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer("container-agent-service")

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8080")
LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-local-testbed")
ASSERTION_SECRET = os.getenv("AGENT_ASSERTION_SECRET", "lab-assertion-only")
PRINCIPALS = {
    "lab-customer": {"user_id": "customer-01", "role": "customer"},
    "lab-employee": {"user_id": "employee-01", "role": "employee"},
    "lab-admin": {"user_id": "admin-01", "role": "admin"},
}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one approved synthetic lab file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": [
                            "/data/public/notice.txt",
                            "/data/nonimportant/team-note.txt",
                            "/data/sensitive/secret.txt",
                        ],
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    }
]
EVENTS: list[dict[str, Any]] = []


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


app = FastAPI(title="MCP Gateway Learning Lab")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sign_gateway_assertion(call: dict[str, Any], role: str) -> str:
    payload = {
        "request_id": call["request_id"],
        "session_id": call["session_id"],
        "user_id": call["user_id"],
        "agent_id": call["agent_id"],
        "tool_call_id": call["tool_call_id"],
        "server_id": call["server_id"],
        "tool_name": call["tool_name"],
        "arguments_sha256": hashlib.sha256(canonical(call["arguments"]).encode()).hexdigest(),
        "role": role,
    }
    import hmac

    return hmac.new(ASSERTION_SECRET.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest()


def principal(authorization: str | None) -> dict[str, str]:
    token = (authorization or "").removeprefix("Bearer ")
    value = PRINCIPALS.get(token)
    if not value:
        raise HTTPException(status_code=401, detail="use one of the lab tokens in the GUI")
    return value


def select_fixture(message: str) -> str:
    lowered = message.lower()
    if any(word in lowered for word in ("중요", "비밀", "sensitive", "secret")):
        return "/data/sensitive/secret.txt"
    if any(word in lowered for word in ("비중요", "팀", "nonimportant", "team")):
        return "/data/nonimportant/team-note.txt"
    return "/data/public/notice.txt"


def remember(event: dict[str, Any]) -> None:
    # ponytail: process-local evidence list; move it to an append-only store only when restarts must retain it.
    EVENTS.insert(0, event)
    del EVENTS[20:]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model_path": "LiteLLM -> local OpenAI-compatible mock"}


@app.get("/events")
async def events() -> dict[str, list[dict[str, Any]]]:
    return {"events": EVENTS}


@app.get("/gateway-audit/{request_id}")
async def gateway_audit(request_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=4) as client:
        response = await client.get(f"{GATEWAY_URL}/audit/{request_id}")
        response.raise_for_status()
    return response.json()


@app.post("/mock-llm/v1/chat/completions")
async def local_mock_llm(request: dict[str, Any]) -> dict[str, Any]:
    messages = request.get("messages", [])
    latest_user_message = next(
        (
            str(item.get("content", ""))
            for item in reversed(messages)
            if isinstance(item, dict) and item.get("role") == "user"
        ),
        "",
    )
    path = select_fixture(latest_user_message)
    tool_call_id = f"call_{uuid.uuid4().hex[:12]}"
    return {
        "id": f"chatcmpl_{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.get("model", "local-tool-model"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {"name": "read_file", "arguments": json.dumps({"path": path})},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/chat")
async def chat(request: ChatRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    caller = principal(authorization)
    request_id = f"req-{uuid.uuid4().hex}"
    with tracer.start_as_current_span("agent.tool_proposal") as span:
        agent_trace_id = f"{span.get_span_context().trace_id:032x}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                model_response = await client.post(
                    f"{LITELLM_URL}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                    json={
                        "model": "lab-tool-model",
                        "messages": [{"role": "user", "content": request.message}],
                        "tools": TOOLS,
                        "tool_choice": {"type": "function", "function": {"name": "read_file"}},
                    },
                )
                model_response.raise_for_status()
            tool_call = model_response.json()["choices"][0]["message"]["tool_calls"][0]
            arguments = json.loads(tool_call["function"]["arguments"])
            if tool_call["function"]["name"] != "read_file" or not isinstance(arguments, dict):
                raise ValueError("unexpected tool proposal")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=502, detail=f"LiteLLM tool proposal failed: {type(error).__name__}") from error

        call = {
            "request_id": request_id,
            "session_id": "lab-session-01",
            "user_id": caller["user_id"],
            "agent_id": "learning-lab-agent",
            "tool_call_id": tool_call["id"],
            "server_id": "file-mcp",
            "tool_name": tool_call["function"]["name"],
            "arguments": arguments,
        }
        model_evidence = {
            "event": "tool_proposal",
            "request_id": request_id,
            "trace_id": agent_trace_id,
            "source": "LiteLLM proxy",
            "model": "lab-tool-model",
            "tool_name": call["tool_name"],
            "message_sha256": sha256_text(request.message),
            "arguments_sha256": hashlib.sha256(canonical(arguments).encode()).hexdigest(),
            "raw_prompt_stored": False,
            "raw_model_output_stored": False,
        }
        remember(model_evidence)
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                gateway_response = await client.post(
                    f"{GATEWAY_URL}/tool-call",
                    headers={
                        "X-Agent-Role": caller["role"],
                        "X-Agent-Assertion": sign_gateway_assertion(call, caller["role"]),
                    },
                    json=call,
                )
                gateway_response.raise_for_status()
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"gateway request failed: {type(error).__name__}") from error

    return {"request_id": request_id, "principal": caller, "model_evidence": model_evidence, "gateway": gateway_response.json()}


@app.get("/", response_class=HTMLResponse)
async def page() -> str:
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>MCP Gateway Learning Lab</title>
<style>
body{max-width:920px;margin:32px auto;padding:0 16px;font:16px system-ui,sans-serif;background:#0b1020;color:#eaf0ff} button,select,input{font:inherit;padding:9px;margin:4px}button{cursor:pointer}.allow{color:#7ee787}.deny{color:#ff7b72}pre{white-space:pre-wrap;word-break:break-word;background:#141b33;padding:16px;border-radius:8px}.hint{color:#a9b7d0}</style>
</head><body>
<h1>MCP Gateway Learning Lab</h1>
<p class="hint">LiteLLM은 도구 호출을 제안하고, 실제 허용/차단은 Gateway + OPA가 결정합니다. 아래 결과의 <code>upstream_called</code>가 실제 전달 여부입니다.</p>
<label>실습 사용자 <select id="token"><option value="lab-customer">고객</option><option value="lab-employee">직원</option><option value="lab-admin">관리자</option></select></label>
<input id="message" size="42" value="공개 공지 보여줘"><button id="send">도구 요청</button>
<p><button data-token="lab-customer" data-message="공개 공지 보여줘">고객 → 공개 (통과)</button><button data-token="lab-customer" data-message="중요 비밀 문서 보여줘">고객 → 중요 (차단)</button><button data-token="lab-employee" data-message="비중요 팀 노트 보여줘">직원 → 비중요 (통과)</button><button data-token="lab-admin" data-message="중요 비밀 문서 보여줘">관리자 → 중요 (통과)</button></p>
<h2 id="state">대기 중</h2><pre id="result">요청 결과가 여기에 표시됩니다.</pre>
<script>
const token=document.querySelector('#token'),message=document.querySelector('#message'),state=document.querySelector('#state'),out=document.querySelector('#result');
async function run(t=token.value,m=message.value){token.value=t;message.value=m;state.textContent='LiteLLM → Gateway → OPA 처리 중…';state.className='';try{const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+t},body:JSON.stringify({message:m})});const j=await r.json();out.textContent=JSON.stringify(j,null,2);const allowed=j.gateway&&j.gateway.decision==='ALLOW';state.textContent=allowed?'통과: Mock MCP 실행 증적이 생성됨':'차단: Mock MCP로 전달되지 않음';state.className=allowed?'allow':'deny'}catch(e){state.textContent='요청 오류';state.className='deny';out.textContent=String(e)}}
document.querySelector('#send').onclick=()=>run();document.querySelectorAll('[data-message]').forEach(b=>b.onclick=()=>run(b.dataset.token,b.dataset.message));
</script></body></html>"""
