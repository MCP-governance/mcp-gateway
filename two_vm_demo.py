#!/usr/bin/env python3
"""Minimal two-VM MCP gateway demo using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROTOCOL = "2026-07-28"
SERVER_ID = "demo-mcp"
UPSTREAM_TOKEN = os.environ.get("MCP_DEMO_UPSTREAM_TOKEN", "demo-upstream-only")
POLICY_VERSION = "demo-rbac-v1"
DOCUMENTS = {
    "public-announcement": {"data_class": "public", "text": "Synthetic public announcement."},
    "team-notes": {"data_class": "nonimportant", "text": "Synthetic internal team note."},
    "customer-record": {"data_class": "important", "text": "Synthetic customer record."},
}
ROLE_PERMISSIONS = {
    "customer": {"public": "r"},
    "employee": {"public": "r", "nonimportant": "rw", "important": "r"},
    "admin": {"public": "rwx", "nonimportant": "rwx", "important": "rwx"},
}
TOOLS = {
    "read_document": {
        "name": "read_document",
        "description": "Read a synthetic document selected by document_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
    },
    "write_document": {
        "name": "write_document",
        "description": "Write synthetic content to a document. Records an upstream effect.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}, "content": {"type": "string", "maxLength": 300}},
            "required": ["document_id", "content"],
            "additionalProperties": False,
        },
    },
    "send_external": {
        "name": "send_external",
        "description": "Send a synthetic document to an external destination. Demo-only high-risk sink.",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}, "destination": {"type": "string", "maxLength": 200}},
            "required": ["document_id", "destination"],
            "additionalProperties": False,
        },
    },
}
TOOL_PERMISSIONS = {"read_document": "r", "write_document": "w", "send_external": "x"}


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: str, event: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(canonical(event) + "\n")


def send_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def send_html(handler: BaseHTTPRequestHandler, html: str) -> None:
    raw = html.encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def gui_html() -> str:
    return """<!doctype html>
<html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MCP Gateway 실습 화면</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#192235;font:15px system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:28px 18px}h1{margin:0 0 6px}h2{font-size:17px;margin:0 0 14px}.sub{color:#586174;margin:0 0 22px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:#fff;border:1px solid #dce2ed;border-radius:12px;padding:18px;box-shadow:0 2px 8px #18233b0b}.full{grid-column:1/-1}label{display:block;font-weight:650;margin:9px 0 4px}select,input,textarea,button{font:inherit;border-radius:7px;border:1px solid #b8c3d5;padding:9px;width:100%}textarea{min-height:64px;resize:vertical}button{cursor:pointer;background:#1f5eff;color:#fff;border:0;font-weight:700;margin-top:14px}button.alt{background:#e8eefb;color:#173e94;margin:5px 6px 0 0;width:auto}.examples{display:flex;flex-wrap:wrap}.badge{display:inline-block;padding:4px 8px;border-radius:99px;font-weight:700;font-size:12px}.allow{background:#dff7e8;color:#076332}.deny{background:#ffe1e3;color:#9b1c27}.neutral{background:#e9edf5;color:#3c4960}pre{margin:0;white-space:pre-wrap;word-break:break-word;background:#101827;color:#d7e1f5;border-radius:8px;padding:13px;min-height:94px;max-height:310px;overflow:auto}.log{border-left:4px solid #8795aa;padding:7px 10px;margin:6px 0;background:#f7f9fc}.log.allow{border-left-color:#12a35b}.log.deny{border-left-color:#dd3545}@media(max-width:760px){.grid{grid-template-columns:1fr}.full{grid-column:auto}}
</style>
<main>
<h1>MCP Gateway 눈으로 보는 실습</h1>
<p class="sub">요청 생성 → Gateway 판정 → pj2 실제 효과 로그를 같은 화면에서 봅니다. 모든 데이터는 합성 데이터입니다.</p>
<section class="grid">
<article class="card"><h2>1. 요청 생성기</h2>
<label>사용자 역할</label><select id="role"><option value="customer">고객 (customer)</option><option value="employee" selected>직원 (employee)</option><option value="admin">관리자 (admin)</option></select>
<label>도구</label><select id="tool" onchange="fields()"><option value="read_document">읽기 (r)</option><option value="write_document">쓰기 (w)</option><option value="send_external">외부 전송 (x)</option></select>
<label>자료</label><select id="document"><option value="public-announcement">공개: public-announcement</option><option value="team-notes">비중요: team-notes</option><option value="customer-record">중요: customer-record</option></select>
<div id="write-box" hidden><label>새 내용</label><textarea id="content">synthetic update from GUI</textarea></div>
<div id="send-box" hidden><label>전송 대상</label><input id="destination" value="partner.example"></div>
<button onclick="runForm()">Gateway로 요청 보내기</button></article>
<article class="card"><h2>2. 빠른 비교</h2><p class="sub">아래 버튼은 대표적인 허용·차단 사례를 자동으로 넣어 호출합니다.</p><div class="examples">
<button class="alt" onclick="sample('allow-read')">고객 → 공개 읽기</button>
<button class="alt" onclick="sample('allow-write')">직원 → 비중요 쓰기</button>
<button class="alt" onclick="sample('deny-export')">직원 → 중요 전송</button>
<button class="alt" onclick="sample('allow-export')">관리자 → 중요 전송</button>
<button class="alt" onclick="sample('mismatch')">헤더 위변조</button>
</div><button onclick="runAll()">대표 사례 5개 순서대로 실행</button></article>
<article class="card full"><h2>3. 이번 Gateway 판정 결과 <span id="badge" class="badge neutral">대기</span></h2><pre id="result">버튼을 눌러 요청을 보내세요.</pre></article>
<article class="card"><h2>4. pj1 Gateway 감사 로그</h2><div id="audit">불러오는 중...</div></article>
<article class="card"><h2>5. pj2 upstream 실제 효과</h2><div id="effects">불러오는 중...</div></article>
</section></main>
<script>
const $=id=>document.getElementById(id); const value=id=>$(id).value;
function fields(){const tool=value('tool');$('write-box').hidden=tool!=='write_document';$('send-box').hidden=tool!=='send_external'}
function setForm(role,tool,document){$('role').value=role;$('tool').value=tool;$('document').value=document;fields()}
async function call(role,tool,document,extra={},headerTool=tool){
 const args={document_id:document,...extra}; const payload={jsonrpc:'2.0',id:`gui-${Date.now()}-${Math.random().toString(16).slice(2)}`,method:'tools/call',params:{name:tool,arguments:args}};
 const response=await fetch('/mcp',{method:'POST',headers:{'Content-Type':'application/json','MCP-Protocol-Version':'2026-07-28','Mcp-Method':'tools/call','Mcp-Name':headerTool,'X-User-Role':role},body:JSON.stringify(payload)});
 const body=await response.json(); const denied=Boolean(body.error); $('result').textContent=JSON.stringify(body,null,2); $('badge').textContent=denied?'차단됨':'통과'; $('badge').className='badge '+(denied?'deny':'allow'); await refresh(); return body;
}
function runForm(){const tool=value('tool'), extra=tool==='write_document'?{content:value('content')}:tool==='send_external'?{destination:value('destination')}:{ };return call(value('role'),tool,value('document'),extra)}
function sample(kind){if(kind==='allow-read'){setForm('customer','read_document','public-announcement');return runForm()}if(kind==='allow-write'){setForm('employee','write_document','team-notes');return runForm()}if(kind==='deny-export'){setForm('employee','send_external','customer-record');return runForm()}if(kind==='allow-export'){setForm('admin','send_external','customer-record');return runForm()}return call('customer','read_document','public-announcement',{},'send_external')}
async function runAll(){for(const kind of ['allow-read','allow-write','deny-export','allow-export','mismatch'])await sample(kind)}
function render(id,events,decision){const box=$(id);box.replaceChildren();if(!events.length){box.textContent='기록 없음';return}for(const event of events.slice(-8).reverse()){const row=document.createElement('div');row.className='log '+(event.decision===undefined?'neutral':event.decision.toLowerCase());row.textContent=event.decision?`${event.decision} | ${event.role} | ${event.data_class||'-'} | ${event.tool} | upstream_called=${event.upstream_called}`:`${event.effect} | ${event.document_id} | ${event.data_class}`;box.append(row)}}
async function refresh(){try{const [audit,effects]=await Promise.all([fetch('/audit').then(r=>r.json()),fetch('/effects').then(r=>r.json())]);render('audit',audit.events);render('effects',effects.events)}catch(error){$('audit').textContent='로그 연결 실패: '+error.message}}
fields();refresh();setInterval(refresh,3000);
</script>"""


def rpc_error(request_id: object, policy_id: str, reason: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32001, "message": "MCP tool call denied", "data": {
            "decision": "DENY", "policy_id": policy_id, "reason": reason
        }},
    }


def policy_decision(name: object, arguments: object, role: str) -> tuple[str, str, str | None, str | None]:
    """Return policy id, reason, data class, and required rwx permission."""
    if name not in TOOLS:
        return "MCP-ACCESS-001", "unregistered MCP tool", None, None
    if role not in ROLE_PERMISSIONS:
        return "P-ROLE-001", "unknown user role", None, None
    if not isinstance(arguments, dict):
        return "P-INPUT-001", "tool arguments must be an object", None, None
    document_id = arguments.get("document_id")
    document = DOCUMENTS.get(document_id)
    if not document:
        return "P-DATA-001", "unknown document classification", None, None
    if name == "write_document" and (not isinstance(arguments.get("content"), str) or not 0 < len(arguments["content"]) <= 300):
        return "P-INPUT-001", "write_document requires 1-300 characters of content", document["data_class"], "w"
    if name == "send_external" and (not isinstance(arguments.get("destination"), str) or not arguments["destination"]):
        return "P-INPUT-001", "send_external requires a destination", document["data_class"], "x"
    permission = TOOL_PERMISSIONS[name]
    data_class = document["data_class"]
    if permission not in ROLE_PERMISSIONS[role].get(data_class, ""):
        return "P-RBAC-001", f"{role} lacks {permission} permission for {data_class} data", data_class, permission
    return "P-ALLOW-001", "role, data class, and permission approved", data_class, permission


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if not 0 < length <= 65536:
        raise ValueError("invalid request size")
    value = json.loads(handler.rfile.read(length))
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


class MCPServer(BaseHTTPRequestHandler):
    effects_path = "/tmp/mcp-demo/effects.jsonl"

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            send_json(self, {"ok": True, "role": "upstream-mcp-server", "server_id": SERVER_ID})
            return
        if self.path == "/effects":
            path = Path(self.effects_path)
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
            send_json(self, {"count": len(events), "events": events})
            return
        send_json(self, {"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            send_json(self, {"error": "not found"}, 404)
            return
        if self.headers.get("X-Gateway-Token") != UPSTREAM_TOKEN:
            send_json(self, {"error": "gateway authentication required"}, 401)
            return
        try:
            request = read_json(self)
        except (ValueError, json.JSONDecodeError) as exc:
            send_json(self, {"error": str(exc)}, 400)
            return
        request_id = request.get("id")
        method = request.get("method")
        if method == "tools/list":
            send_json(self, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list(TOOLS.values())}})
            return
        if method != "tools/call":
            send_json(self, rpc_error(request_id, "P-PROTO-001", "unsupported method"))
            return
        params = request.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        document = DOCUMENTS.get(args.get("document_id"))
        if not document:
            send_json(self, rpc_error(request_id, "P-DATA-001", "unknown document"))
            return
        if name == "read_document":
            result = {"content": [{"type": "text", "text": document["text"]}]}
        elif name == "write_document":
            append_jsonl(self.effects_path, {
                "event": "upstream_effect", "effect": "document_write", "document_id": args.get("document_id"),
                "data_class": document["data_class"], "content_sha256": hashlib.sha256(str(args.get("content", "")).encode()).hexdigest(), "at": now(),
            })
            result = {"content": [{"type": "text", "text": "simulated document write"}]}
        elif name == "send_external":
            append_jsonl(self.effects_path, {
                "event": "upstream_effect", "effect": "external_send",
                "document_id": args.get("document_id"), "data_class": document["data_class"],
                "destination": args.get("destination"), "data_sha256": hashlib.sha256(document["text"].encode()).hexdigest(),
                "at": now(),
            })
            result = {"content": [{"type": "text", "text": "simulated external send"}]}
        else:
            send_json(self, rpc_error(request_id, "MCP-ACCESS-001", "unknown tool"))
            return
        send_json(self, {"jsonrpc": "2.0", "id": request_id, "result": result})


class Gateway(BaseHTTPRequestHandler):
    upstream = "http://127.0.0.1:9001/mcp"
    audit_path = "/tmp/mcp-demo/gateway.jsonl"

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/":
            send_html(self, gui_html())
            return
        if self.path == "/health":
            send_json(self, {"ok": True, "role": "mcp-security-gateway", "upstream": self.upstream})
            return
        if self.path == "/audit":
            path = Path(self.audit_path)
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []
            send_json(self, {"count": len(events), "events": events})
            return
        if self.path == "/effects":
            effects_url = self.upstream.rsplit("/", 1)[0] + "/effects"
            try:
                with urlopen(Request(effects_url, headers={"X-Gateway-Token": UPSTREAM_TOKEN}), timeout=5) as result:
                    send_json(self, json.loads(result.read()))
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                send_json(self, {"error": f"upstream effects unavailable: {exc}"}, 502)
            return
        send_json(self, {"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            send_json(self, {"error": "not found"}, 404)
            return
        trace_id = uuid.uuid4().hex
        try:
            request = read_json(self)
        except (ValueError, json.JSONDecodeError) as exc:
            append_jsonl(self.audit_path, {"trace_id": trace_id, "decision": "DENY", "policy_id": "P-PROTO-001", "reason": str(exc), "at": now()})
            send_json(self, rpc_error(None, "P-PROTO-001", str(exc)))
            return

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        name = params.get("name") if isinstance(params, dict) else None
        role = self.headers.get("X-User-Role", "customer")
        arguments = params.get("arguments") if isinstance(params, dict) else None
        policy_id, reason, data_class, permission = policy_decision(name, arguments, role) if method == "tools/call" else ("P-ALLOW-001", "tool discovery", None, None)
        event = {"trace_id": trace_id, "request_id": request_id, "method": method, "tool": name, "agent_id": self.headers.get("X-Agent-Id", "demo-agent"), "role": role, "data_class": data_class, "required_permission": permission, "policy_version": POLICY_VERSION, "at": now()}
        deny = None
        if self.headers.get("MCP-Protocol-Version") != PROTOCOL:
            deny = ("P-PROTO-001", "unsupported MCP protocol version")
        elif self.headers.get("Mcp-Method") != method:
            deny = ("P-PROTO-001", "Mcp-Method does not match JSON-RPC method")
        elif method == "tools/call" and self.headers.get("Mcp-Name") != name:
            deny = ("P-PROTO-001", "Mcp-Name does not match tool name")
        elif method not in {"tools/list", "tools/call"}:
            deny = ("P-PROTO-001", "unsupported MCP method")
        elif method == "tools/call" and policy_id != "P-ALLOW-001":
            deny = (policy_id, reason)

        if deny:
            policy_id, reason = deny
            event.update({"decision": "DENY", "policy_id": policy_id, "reason": reason, "upstream_called": False})
            append_jsonl(self.audit_path, event)
            send_json(self, rpc_error(request_id, policy_id, reason))
            return

        try:
            raw = json.dumps(request, ensure_ascii=False).encode()
            upstream_request = Request(self.upstream, data=raw, method="POST", headers={
                "Content-Type": "application/json", "MCP-Protocol-Version": PROTOCOL, "X-Gateway-Token": UPSTREAM_TOKEN,
            })
            with urlopen(upstream_request, timeout=5) as result:
                upstream_result = json.loads(result.read())
        except (HTTPError, URLError, TimeoutError) as exc:
            event.update({"decision": "DENY", "policy_id": "P-UPSTREAM-001", "reason": str(exc), "upstream_called": False})
            append_jsonl(self.audit_path, event)
            send_json(self, rpc_error(request_id, "P-UPSTREAM-001", "upstream unavailable"), 502)
            return
        event.update({"decision": "ALLOW", "policy_id": policy_id, "reason": reason, "upstream_called": True})
        append_jsonl(self.audit_path, event)
        send_json(self, upstream_result)


def post(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json", **headers})
    with urlopen(request, timeout=5) as result:
        return json.loads(result.read())


def run_client(gateway: str) -> None:
    cases = [
        ("customer reads public", "customer", "read_document", {"document_id": "public-announcement"}, "read_document"),
        ("employee writes nonimportant", "employee", "write_document", {"document_id": "team-notes", "content": "synthetic update"}, "write_document"),
        ("employee cannot export important", "employee", "send_external", {"document_id": "customer-record", "destination": "partner.example"}, "send_external"),
        ("customer cannot read important", "customer", "read_document", {"document_id": "customer-record"}, "read_document"),
        ("admin exports important", "admin", "send_external", {"document_id": "customer-record", "destination": "audit.example"}, "send_external"),
        ("blocked unregistered tool", "admin", "not_registered", {}, "not_registered"),
    ]
    for label, role, tool, arguments, header_name in cases:
        payload = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
        print(json.dumps({"case": label, "result": post(gateway, payload, {"MCP-Protocol-Version": PROTOCOL, "Mcp-Method": "tools/call", "Mcp-Name": header_name, "X-User-Role": role})}, ensure_ascii=False))
    mismatch = {"jsonrpc": "2.0", "id": "header-mismatch", "method": "tools/call", "params": {"name": "read_document", "arguments": {"document_id": "public-announcement"}}}
    print(json.dumps({"case": "blocked header/body mismatch", "result": post(gateway, mismatch, {"MCP-Protocol-Version": PROTOCOL, "Mcp-Method": "tools/call", "Mcp-Name": "send_external", "X-User-Role": "customer"})}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("server")
    server.add_argument("--host", default="0.0.0.0")
    server.add_argument("--port", type=int, default=9001)
    server.add_argument("--effects", default="/tmp/mcp-demo/effects.jsonl")
    gateway = sub.add_parser("gateway")
    gateway.add_argument("--host", default="0.0.0.0")
    gateway.add_argument("--port", type=int, default=8080)
    gateway.add_argument("--upstream", default="http://192.168.85.130:9001/mcp")
    gateway.add_argument("--audit", default="/tmp/mcp-demo/gateway.jsonl")
    client = sub.add_parser("client")
    client.add_argument("--gateway", default="http://127.0.0.1:8080/mcp")
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.command == "self-test":
        assert policy_decision("read_document", {"document_id": "public-announcement"}, "customer")[0] == "P-ALLOW-001"
        assert policy_decision("write_document", {"document_id": "team-notes", "content": "x"}, "employee")[0] == "P-ALLOW-001"
        assert policy_decision("send_external", {"document_id": "customer-record", "destination": "x"}, "employee")[0] == "P-RBAC-001"
        assert policy_decision("send_external", {"document_id": "customer-record", "destination": "x"}, "admin")[0] == "P-ALLOW-001"
        print("self-test: PASS")
    elif args.command == "server":
        MCPServer.effects_path = args.effects
        ThreadingHTTPServer((args.host, args.port), MCPServer).serve_forever()
    elif args.command == "gateway":
        Gateway.upstream, Gateway.audit_path = args.upstream, args.audit
        ThreadingHTTPServer((args.host, args.port), Gateway).serve_forever()
    else:
        run_client(args.gateway)


if __name__ == "__main__":
    main()
