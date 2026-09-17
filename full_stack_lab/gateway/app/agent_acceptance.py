"""Executable v1.1 evidence: real HTTP login -> Agent -> Gateway -> OPA -> MCP.

Provider mode is exercised against a real local HTTP compatibility stub, not an LLM.
Run serially in an isolated demo: docker compose exec -T gateway python -m app.agent_acceptance
"""
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from uuid import uuid4

import httpx
import jwt

from . import db
from .agent_contract import ALGORITHM, AUDIENCE, IDENTITIES, ISSUER, Envelope, issue_agent_assertion, private_key
from .core import canonical_hash, effect_count, execute_call, _discover, HTTP_MCP_URL

AGENT = "http://agent-service:8000"
GATEWAY = "http://gateway:8080"
checks = []


def check(name, condition, detail=""):
    checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


async def login(client, email, base=AGENT):
    r = await client.post(base + "/auth/mock-login", json={"email": email, "password": os.getenv("MOCK_SSO_PASSWORD", "test-password")})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def envelope(**changes):
    return {"request_id": str(uuid4()), "session_id": str(uuid4()), "user_id": "user-test-001", "agent_id": "document-agent-test", "tool_call_id": str(uuid4()), "server_id": "file-mcp", "tool_name": "read_file", "arguments": {"path": "/data/public/notice.txt"}, **changes}


def agent_headers(user_headers: dict[str, str], request: dict, email: str = "miso@bob.local") -> dict[str, str]:
    return {**user_headers, "X-Agent-Assertion": "Bearer " + issue_agent_assertion(IDENTITIES[email], Envelope(**request))}


class ModelStub(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append(data)
        message = data["messages"][-1]["content"]
        if message.startswith("timeout"):
            time.sleep(0.7)
        status = 401 if message == "unauthorized" else 429 if message == "rate-limit" else 500 if message == "provider-error" else 200
        args = {"document_id": "notice-001"}
        name = "read_document"
        if message == "identity-injection":
            args["user_token"] = "admin-demo"
        if message == "unknown-tool":
            name = "delete_everything"
        if message == "wrong-type":
            args["document_id"] = 123
        if message == "important":
            args["document_id"] = "secret-001"
        arguments = "{" if message == "invalid-arguments-json" else json.dumps(args)
        calls = [{"id": "call-stub", "type": "function", "function": {"name": name, "arguments": arguments}}]
        if message == "multi-tool":
            calls *= 2
        if message == "no-tool":
            calls = []
        payload = {"choices": [{"message": {"role": "assistant", "tool_calls": calls}}]}
        if message == "missing-choices":
            payload = {}
        if message == "bad-shape":
            payload = {"choices": [{"message": "not-an-object"}]}
        raw = b"not-json" if message == "invalid-json" else json.dumps(payload).encode()
        if message == "oversize":
            raw = b" " * 130_000
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass


async def main():
    async with httpx.AsyncClient(timeout=40) as client:
        for _ in range(60):
            try:
                if (await client.get(AGENT + "/api/readiness")).json().get("status") == "ready":
                    break
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(1)
        ready = (await client.get(AGENT + "/api/readiness")).json()
        check("agent-ready-mock", ready["status"] == "ready" and ready["model"]["mode"] == "mock")
        check("unauthenticated-chat", (await client.post(AGENT + "/chat", json={"message": "공개 문서를 읽어줘"})).status_code == 401)
        check("invalid-login", (await client.post(AGENT + "/auth/mock-login", json={"email": "miso@bob.local", "password": "wrong"})).status_code == 401)
        users = {role: await login(client, email) for role, email in [("partner", "partner@bob.local"), ("employee", "miso@bob.local"), ("admin", "admin@bob.local")]}
        check("console-identity-required", (await client.get(AGENT + "/api/console")).status_code == 401)
        consoles = {role: (await client.get(AGENT + "/api/console", headers=header)).json()
                    for role, header in users.items()}
        check("console-live-state", bool(consoles["employee"]["health"]["components"]["opa"]))
        # 메뉴를 감추기만 하면 개발자 도구를 여는 순간 통제가 사라진다. 역할이 볼 수
        # 없는 화면은 응답 자체에 데이터가 없어야 한다.
        check("console-pages-partner", consoles["partner"]["viewer"]["pages"] == ["execution", "intake"])
        check("console-pages-employee", consoles["employee"]["viewer"]["pages"] == ["execution", "intake", "audit"])
        check("console-pages-admin", {"risks", "mcpscan", "policy"} <= set(consoles["admin"]["viewer"]["pages"]))
        check("console-supply-chain-admin-only",
              consoles["partner"]["supply_chain"] == [] and consoles["employee"]["supply_chain"] == []
              and isinstance(consoles["admin"]["supply_chain"], list))
        check("console-ledger-hidden-from-partner",
              not consoles["partner"]["ledger"] and not consoles["employee"]["ledger"])

        # 검색은 모든 역할이 쓴다. 같은 저장소를 다시 신청하기 전에 확인하는 것이
        # 중복 신청과 이미 거부된 서버의 재제출을 막는 유일한 수단이다.
        for role in ("partner", "employee", "admin"):
            found = (await client.get(AGENT + "/api/mcp-catalog/search?q=github", headers=users[role])).json()
            check(f"catalog-search-{role}", any(row["id"] == "github" for row in found["registry"]),
                  json.dumps([row["id"] for row in found["registry"]]))
        leak = (await client.get(AGENT + "/api/mcp-catalog/search?q=", headers=users["partner"])).json()
        check("catalog-search-no-purpose-leak",
              all("purpose" not in row and "submitted_by" not in row for row in leak["requests"]))
        check("catalog-search-identity-required",
              (await client.get(AGENT + "/api/mcp-catalog/search?q=x")).status_code == 401)

        # AI 코드 감사는 관리자 전용이고, endpoint 설정이 없으면 실행을 만들 수 없다.
        check("mcp-scan-admin-only",
              (await client.get(AGENT + "/api/mcp-scan", headers=users["employee"])).status_code == 403)
        scan_view = (await client.get(AGENT + "/api/mcp-scan", headers=users["admin"])).json()
        check("mcp-scan-config-visible",
              "configured" in scan_view["config"] and isinstance(scan_view["jobs"], list),
              json.dumps(scan_view["config"], ensure_ascii=False))
        # "설정이 있다"와 "실행할 워커가 살아 있다"를 화면이 구분하지 못하면, 큐에
        # 쌓이기만 하는 상태가 진행 중으로 읽힌다.
        check("mcp-scan-worker-liveness-visible",
              isinstance(scan_view.get("worker"), dict)
              and {"alive", "queued", "running", "stale"} <= set(scan_view["worker"]),
              json.dumps(scan_view.get("worker"), ensure_ascii=False, default=str)[:200])
        # 등록된 서버도 감사 대상이어야 한다. 도입 요청만 대상이면 심사한 코드와
        # 지금 도는 코드가 갈라져도 확인할 방법이 없다.
        check("mcp-scan-server-targets-listed",
              isinstance(scan_view.get("servers"), list)
              and any(row["id"] == "mock-stdio" and row["scannable"] for row in scan_view["servers"]),
              json.dumps([(row["id"], row["scannable"]) for row in scan_view.get("servers", [])]))
        if not scan_view["config"]["configured"]:
            blocked = await client.post(AGENT + "/api/mcp-scan/run", headers=users["admin"],
                                        json={"target_kind": "intake",
                                              "target_id": "00000000-0000-0000-0000-000000000000"})
            check("mcp-scan-refuses-without-endpoint", blocked.status_code == 409, blocked.text[:120])
        # 원격 전용 서버는 국소 감사 대상이 아니라는 사실이 409로 드러나야 한다.
        # 조용히 큐에 들어가면 영원히 실패만 반복한다.
        remote = await client.post(AGENT + "/api/mcp-scan/run", headers=users["admin"],
                                   json={"target_kind": "server", "target_id": "mock-http"})
        check("mcp-scan-rejects-unscannable-server", remote.status_code == 409, remote.text[:160])
        check("mcp-scan-cancel-admin-only",
              (await client.post(AGENT + "/api/mcp-scan/jobs/00000000-0000-0000-0000-000000000000/cancel",
                                 headers=users["employee"])).status_code == 403)

        # 신원 관리대장(Agent-Service miso 이식): 계정 상태가 애플리케이션 상수가
        # 아니라 DB에 있고, 이미 발급된 토큰도 다음 요청에서 막혀야 한다. 토큰
        # 만료를 기다리는 계정 정지는 정지가 아니다.
        check("accounts-admin-only",
              (await client.get(AGENT + "/api/accounts", headers=users["employee"])).status_code == 403)
        accounts = (await client.get(AGENT + "/api/accounts", headers=users["admin"])).json()["accounts"]
        check("accounts-no-password-hash",
              all("password_hash" not in row and row["has_password"] for row in accounts),
              json.dumps([row["email"] for row in accounts], ensure_ascii=False))
        check("account-self-lock-refused",
              (await client.put(AGENT + "/api/accounts/user-admin-001/status", headers=users["admin"],
                                json={"status": "disabled"})).status_code == 409)
        check("account-status-admin-only",
              (await client.put(AGENT + "/api/accounts/user-partner-001/status", headers=users["employee"],
                                json={"status": "disabled"})).status_code == 403)
        disabled = await client.put(AGENT + "/api/accounts/user-partner-001/status", headers=users["admin"],
                                    json={"status": "disabled"})
        try:
            check("account-disable", disabled.status_code == 200, disabled.text[:160])
            # 이미 들고 있던 토큰
            check("account-disabled-existing-token-blocked",
                  (await client.get(AGENT + "/api/console", headers=users["partner"])).status_code == 403)
            # 새 로그인
            relogin = await client.post(AGENT + "/auth/mock-login", json={
                "email": "partner@bob.local", "password": os.getenv("MOCK_SSO_PASSWORD", "test-password")})
            check("account-disabled-login-blocked", relogin.status_code == 403, relogin.text[:160])
        finally:
            await client.put(AGENT + "/api/accounts/user-partner-001/status", headers=users["admin"],
                             json={"status": "active"})
        check("account-restored",
              (await client.get(AGENT + "/api/console", headers=users["partner"])).status_code == 200)
        # 계정별 해시이므로 다른 비밀번호는 통과하지 못한다.
        check("account-wrong-password",
              (await client.post(AGENT + "/auth/mock-login", json={
                  "email": "partner@bob.local", "password": "not-the-password"})).status_code == 401)

        # 실시간 흐름도 역할 범위를 그대로 따른다.
        async with client.stream("GET", AGENT + "/api/stream/decisions", headers=users["employee"]) as response:
            check("live-stream-opens", response.status_code == 200 and "text/event-stream" in response.headers["content-type"])
        check("live-stream-identity-required",
              (await client.get(AGENT + "/api/stream/decisions")).status_code == 401)
        check("console-approvals-admin-only",
              consoles["partner"]["approvals"] == [] and consoles["employee"]["approvals"] == [])
        # 감사 화면이 있는 직원도 자기 호출만 본다. 전체 판정은 관리자만 본다.
        check("console-decisions-scoped",
              consoles["partner"]["decisions"] == []
              and all(row["user_token"] == "emp-demo" for row in consoles["employee"]["decisions"]))
        intake_name = "검증 요청 " + str(uuid4())[:8]
        invalid_intake = await client.post(AGENT + "/api/mcp-requests", headers=users["employee"], json={
            "display_name": intake_name, "repository_url": "https://untrusted.invalid/repo", "requested_transport": "streamable-http", "purpose": "권한 검증용 외부 MCP 연동 요청입니다.",
        })
        check("intake-github-only", invalid_intake.status_code == 422)
        submitted = await client.post(AGENT + "/api/mcp-requests", headers=users["employee"], json={
            "display_name": intake_name, "repository_url": "https://github.com/MCP-governance/mcp-gateway.git", "requested_transport": "streamable-http", "purpose": "권한 검증용 외부 MCP 연동 요청입니다.",
        })
        submitted.raise_for_status()
        intake_id = submitted.json()["request"]["id"]
        try:
            check("intake-held-before-scan", submitted.json()["request"]["status"] == "HOLD")
            check("intake-admin-only-queue", (await client.post(AGENT + f"/api/mcp-requests/{intake_id}/queue-validation", headers=users["employee"], json={})).status_code == 403)
            queued = await client.post(AGENT + f"/api/mcp-requests/{intake_id}/queue-validation", headers=users["admin"], json={})
            check("intake-validation-queue", queued.status_code == 200 and queued.json()["request"]["status"] == "VALIDATION_QUEUED")
            # 검증 중인 저장소는 다시 신청할 수 없다.
            dup = await client.post(AGENT + "/api/mcp-requests", headers=users["employee"], json={
                "display_name": intake_name + " dup", "repository_url": "https://github.com/MCP-governance/mcp-gateway",
                "requested_transport": "streamable-http", "purpose": "중복 제출이 막히는지 확인하는 요청입니다.",
            })
            check("intake-duplicate-blocked", dup.status_code == 409, dup.text[:120])
            # 다만 FAILED는 사람의 판단이 아니라 검증이 끝나지 못한 오류다. 스캐너
            # 장애 한 번이 그 저장소를 영구히 신청 불가로 만들면 안 된다.
            await db.execute("UPDATE mcp_intake_requests SET status='FAILED' WHERE id=%s", (intake_id,))
            retry = await client.post(AGENT + "/api/mcp-requests", headers=users["employee"], json={
                "display_name": intake_name + " retry", "repository_url": "https://github.com/MCP-governance/mcp-gateway",
                "requested_transport": "streamable-http", "purpose": "검증 실패 뒤 재신청이 되는지 확인하는 요청입니다.",
            })
            check("intake-resubmit-after-failure", retry.status_code == 200, retry.text[:160])
            if retry.status_code == 200:
                await db.execute("DELETE FROM mcp_intake_requests WHERE id=%s", (retry.json()["request"]["id"],))
        finally:
            await db.execute("DELETE FROM mcp_intake_requests WHERE id=%s", (intake_id,))
        cases = [("partner", "공개 문서를 읽어줘", "Allow", 1), ("partner", "비밀 인증정보를 읽어줘", "Block", 0),
                 ("employee", "비밀 인증정보를 읽어줘", "Alert", 1), ("employee", "내부 업무 메모를 수정해줘", "Allow", 1),
                 ("admin", "공개 공지를 외부에 전송해줘", "Restrict", 1), ("admin", "중요 계약을 외부에 전송해줘", "Approval", 0)]
        for role, message, expected, delta in cases:
            before = effect_count()
            response = await client.post(AGENT + "/chat", headers=users[role], json={"message": message})
            response.raise_for_status()
            body = response.json()
            outcome = body.get("gateway_result") or {}
            check("chat-" + role + "-" + expected, outcome.get("decision") == expected and effect_count() - before == delta, body.get("message", ""))
            check("trace-" + role + "-" + expected, outcome["request_id"] == body["request_id"] and bool(outcome["trace_id"]) and outcome["request_payload"]["_agent_context"]["session_id"] == body["session_id"])
            if expected == "Approval":
                approval_id = outcome["approval_id"]
            if expected == "Restrict":
                check("agent-restrictions", outcome["effective_arguments"]["destination"] == "restricted.invalid" and len(outcome["effective_arguments"]["content"]) <= 80)
        check("approval-non-admin", (await client.post(AGENT + f"/approvals/{approval_id}/approve", headers=users["employee"], json={})).status_code == 403)
        before = effect_count()
        approved = await asyncio.gather(*(client.post(AGENT + f"/approvals/{approval_id}/approve", headers=users["admin"], json={}) for _ in range(2)))
        check("approval-race-exactly-once", sorted(r.status_code for r in approved) == [200, 409] and effect_count() == before + 1)
        request = {"message": "공개 문서를 읽어줘", "request_id": str(uuid4())}
        first = (await client.post(AGENT + "/chat", headers=users["employee"], json=request)).json()
        before = effect_count()
        again = (await client.post(AGENT + "/chat", headers=users["employee"], json=request)).json()
        check("chat-idempotency", again.get("replayed") and again["request_id"] == first["request_id"] and effect_count() == before)
        check("request-id-conflict", (await client.post(AGENT + "/chat", headers=users["employee"], json={**request, "message": "다른 요청"})).status_code == 409)
        session_id = first["session_id"]
        check("session-isolation", (await client.get(AGENT + "/sessions/" + session_id, headers=users["partner"])).status_code == 404)
        check("session-history", len((await client.get(AGENT + "/sessions/" + session_id, headers=users["employee"])).json()["runs"]) >= 1)
        check("cross-origin-request", (await client.post(AGENT + "/chat", headers={**users["employee"], "Origin": "https://untrusted.invalid"}, json={"message": "공開"})).status_code == 403)
        spoof = envelope(user_id="user-admin-001")
        check("identity-spoof", (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], spoof), json=spoof)).status_code == 403)
        traversal = envelope(arguments={"path": "/data/public/../sensitive/secret.txt"})
        check("path-traversal", (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], traversal), json=traversal)).status_code == 422)
        injection = envelope(arguments={"path": "/data/public/notice.txt", "user_token": "admin-demo"})
        check("argument-identity-injection", (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], injection), json=injection)).status_code == 422)
        unknown_server = envelope(server_id="evil")
        check("unknown-server", (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], unknown_server), json=unknown_server)).status_code == 422)
        for name, updates in [("expired", {"exp": datetime.now(UTC) - timedelta(seconds=5)}), ("wrong-audience", {"aud": "other"}), ("wrong-issuer", {"iss": "other"})]:
            claims = {"sub": "user-test-001", "iss": ISSUER, "aud": AUDIENCE, "iat": datetime.now(UTC) - timedelta(minutes=1), "nbf": datetime.now(UTC) - timedelta(minutes=1), "exp": datetime.now(UTC) + timedelta(minutes=1), "jti": str(uuid4()), **updates}
            # The gateway service itself has no private key. The acceptance run is
            # handed one on the exec line precisely so it can forge claim variants.
            token = jwt.encode(claims, private_key(), algorithm=ALGORITHM)
            check("jwt-" + name, (await client.post(GATEWAY + "/tool-call", headers={"Authorization": "Bearer " + token}, json=envelope())).status_code == 401)
        check("jwt-invalid-signature", (await client.post(GATEWAY + "/tool-call", headers={"Authorization": users["employee"]["Authorization"] + "tampered"}, json=envelope())).status_code == 401)
        delegated = envelope()
        check("agent-assertion-required", (await client.post(GATEWAY + "/tool-call", headers=users["employee"], json=delegated)).status_code == 401)
        check("human-token-is-not-agent-assertion", (await client.post(GATEWAY + "/tool-call", headers={**users["employee"], "X-Agent-Assertion": users["employee"]["Authorization"]}, json=delegated)).status_code == 401)
        changed = {**delegated, "tool_call_id": str(uuid4())}
        check("agent-assertion-envelope-bound", (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], delegated), json=changed)).status_code == 401)
        check("agent-assertion-actor-bound", (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], delegated, "admin@bob.local"), json=delegated)).status_code == 401)
        req = envelope()
        req_headers = agent_headers(users["employee"], req)
        first = (await client.post(GATEWAY + "/tool-call", headers=req_headers, json=req)).json()
        before = effect_count()
        replay = (await client.post(GATEWAY + "/tool-call", headers=req_headers, json=req)).json()
        check("gateway-idempotency", replay.get("replayed") and effect_count() == before)
        stuck = envelope()
        await db.execute(
            "INSERT INTO agent_gateway_receipts(id,user_id,fingerprint,created_at) VALUES (%s,%s,%s, now() - interval '1 hour')",
            (stuck["tool_call_id"], "user-test-001", canonical_hash(stuck)),
        )
        before = effect_count()
        settled = (await client.post(GATEWAY + "/tool-call", headers=agent_headers(users["employee"], stuck), json=stuck)).json()
        check("stuck-receipt-settled",
              settled.get("policy_id") == "MCP-RECEIPT-001" and settled.get("execution_status") == "unknown"
              and effect_count() == before,
              "응답 없이 중단된 receipt는 재실행 없이 unknown으로 확정")
        before = effect_count()
        with patch("app.core.refresh_catalog", side_effect=RuntimeError("catalog offline")):
            outcome = await execute_call({"user_token": "partner-demo", "tool_name": "read_document", "document_id": "notice-001"})
        check("stale-catalog-fail-closed", outcome["policy_id"] == "MCP-CATALOG-001" and effect_count() == before)
        outcome = await execute_call({"user_token": "admin-demo", "tool_name": "write_document", "document_id": "work-001", "content": 42})
        check("shared-input-schema", outcome["policy_id"] == "P-INPUT-SCHEMA-001" and effect_count() == before)
        with patch("app.core.GITHUB_TOKEN", "synthetic-transport-key"), patch("app.core.GITHUB_MCP_URL", HTTP_MCP_URL):
            discovered = await _discover("github")
        check("github-authenticated-transport-local", len(discovered["tools"]) == 3 and discovered["version"] == "1.0.0")
        outcome = await execute_call({"user_token": "admin-demo", "tool_name": "github_get_file", "owner": "unapproved", "repo": "private", "path": "README.md"})
        check("github-repository-allowlist", outcome["policy_id"] == "MCP-REPOSITORY-001" and effect_count() == before)
        fixture = "agent-test-" + str(uuid4())
        try:
            for scanner, critical in [(fixture + "-vuln", 1), (fixture + "-sbom", 0)]:
                await db.execute("INSERT INTO supply_chain_reports(scanner,source_ref,report_path,status,critical_count) VALUES (%s,'demo-v1','synthetic','IMPORTED',%s)", (scanner, critical))
            outcome = await execute_call({"user_token": "partner-demo", "tool_name": "read_document", "document_id": "notice-001"})
            check("sbom-cannot-clear-vulnerability", outcome["policy_id"] == "MCP-SUPPLY-001" and effect_count() == before)
        finally:
            await db.execute("DELETE FROM supply_chain_reports WHERE scanner IN (%s,%s)", (fixture + "-vuln", fixture + "-sbom"))
        await client.post(AGENT + "/auth/logout", headers=users["employee"], json={})
        check("logout-agent-revocation", (await client.get(AGENT + "/auth/me", headers=users["employee"])).status_code == 401)
        check("logout-gateway-revocation", (await client.post(GATEWAY + "/tool-call", headers=users["employee"], json=envelope())).status_code == 401)

        stub = ThreadingHTTPServer(("127.0.0.1", 0), ModelStub)
        threading.Thread(target=stub.serve_forever, daemon=True).start()
        provider_base = "http://127.0.0.1:18011"
        environment = {**os.environ, "MODEL_MODE": "provider", "MODEL_BASE_URL": f"http://127.0.0.1:{stub.server_port}/v1", "MODEL_NAME": "local-wire-stub", "MODEL_API_KEY": "synthetic-wire-key", "MODEL_TIMEOUT_SECONDS": "0.2"}
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.agent_service:app", "--host", "127.0.0.1", "--port", "18011"], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    if (await client.get(provider_base + "/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.2)
            headers = await login(client, "partner@bob.local", provider_base)
            for message in ["public", "important", "no-tool", "identity-injection", "unknown-tool", "wrong-type", "multi-tool", "invalid-json", "invalid-arguments-json", "missing-choices", "bad-shape", "oversize", "unauthorized", "rate-limit", "provider-error", "timeout"]:
                before = effect_count()
                response = await client.post(provider_base + "/chat", headers=headers, json={"message": message})
                response.raise_for_status()
                body = response.json()
                if message == "public":
                    passed = body.get("gateway_result", {}).get("decision") == "Allow" and effect_count() == before + 1
                elif message == "important":
                    passed = body.get("gateway_result", {}).get("decision") == "Block" and effect_count() == before
                elif message == "no-tool":
                    passed = body["status"] == "no_tool" and effect_count() == before
                else:
                    passed = body["status"] == "failed" and effect_count() == before
                check("provider-wire-" + message, passed, body.get("message", ""))
            await client.post(provider_base + "/chat", headers=headers, json={"message": "public demo@example.com 010-1234-5678"})
            last = ModelStub.seen[-1]["messages"][-1]["content"]
            check("provider-request-redaction", "demo@example.com" not in last and "010-1234-5678" not in last and "[EMAIL]" in last)
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait, 10)
            await asyncio.to_thread(stub.shutdown)
            stub.server_close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        print(json.dumps({"checks": checks, "summary": {"passed": sum(c["status"] == "PASS" for c in checks), "failed": sum(c["status"] != "PASS" for c in checks)}, "provider_evidence": "local HTTP wire stub; no external LLM call"}, ensure_ascii=False, indent=2))
