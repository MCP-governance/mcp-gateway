"""실제 LiteLLM 1.105와 실제 MINT(deploy/, OPA·PostgreSQL·Presidio)를 잇는 정상 업무·철회·복구 검수.

대역이 없다: MCP는 공급자 운영 Microsoft Learn MCP, 판정·원장은 설치된 MINT, 관리·집계는 LiteLLM 컨테이너다.
CI(.github/workflows/verify.yml의 litellm 작업)가 단계 사이에 ./mint.sh·docker 조작을 끼워 부른다.

    python3 litellm_addon_e2e.py <단계>     단계: prepare register call-a drift isolation-start isolation-check
                                            rotate-check revoke recover restart-check call-b

환경: MINT_BIND, MINT_CA(루트 PEM), MINT_ROOT_PASSWORD_FILE, LITELLM_URL, LITELLM_MASTER_KEY, E2E_STATE(상태 JSON 경로),
EMP_PASSWORD(시험 직원 두 명의 비밀번호, CI가 매번 만든다). 성공은 MCP 결과 본문과 MINT 원장 행을 함께 대조한다.
LiteLLM·Learn의 한도 초과나 오류 응답은 성공으로 세지 않는다.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intake_register  # noqa: E402

BIND = os.environ["MINT_BIND"]
MINT = f"https://{BIND}"
CA = os.environ["MINT_CA"]
LITE = os.environ.get("LITELLM_URL", "http://127.0.0.1:4000")
MASTER = os.environ["LITELLM_MASTER_KEY"]
STATE = Path(os.environ.get("E2E_STATE", "/tmp/litellm-e2e.json"))
LEARN = "https://learn.microsoft.com/api/mcp"
EMPLOYEES = ("emp1", "emp2")
CONSTRAINT = {"type": "object", "additionalProperties": False, "required": ["query"],
              "properties": {"query": {"type": "string", "maxLength": 300}}}
SUPPLIER = {"legal_entity": "Microsoft Corporation", "supplier_contact": "https://learn.microsoft.com",
            "security_contact": "https://msrc.microsoft.com", "support_end": "2099-12-31",
            "vulnerability_policy_url": "https://www.microsoft.com/msrc/cvd"}
IMPACT = {"data_class": "nonimportant", "personal_data": "none", "external_transfer": False,
          "permission": "r", "users": 5, "autonomy": "approve_each"}


def state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(data: dict) -> None:
    STATE.write_text(json.dumps(data))
    STATE.chmod(0o600)


def evidence(step: str, **fields) -> None:
    print(json.dumps({"step": step, **fields}, ensure_ascii=False), flush=True)


def lite(method: str, path: str, body: dict | None = None, params: dict | None = None, key: str = MASTER) -> dict:
    response = httpx.request(method, LITE + path, json=body, params=params, timeout=60,
                             headers={"Authorization": f"Bearer {key}"})
    if response.status_code >= 300:
        raise SystemExit(f"LiteLLM {method} {path} -> {response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def mint(method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.request(method, MINT + path, verify=CA, timeout=120, headers=headers, **kwargs)


def sql(query: str) -> list[list[str]]:
    out = subprocess.run(["docker", "exec", "mint-db-1", "psql", "-U", "mcp", "-d", "mcp_governance", "-At", "-F", "\t",
                          "-c", query], check=True, capture_output=True, text=True).stdout
    return [line.split("\t") for line in out.splitlines() if line]


def console_token(user: str, password: str) -> str:
    response = mint("POST", "/auth/mock-login", json={"email": user, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


def mcp_token(user: str, password: str) -> str:
    # The employee's own MCP grant through the same IdP path a harness uses (no device: an AI-gateway-only account).
    response = mint("POST", "/oauth/token", data={"grant_type": "password", "client_id": "litellm-e2e",
                                                  "username": user, "password": password})
    if response.status_code != 200:
        raise SystemExit(f"{user} MCP 토큰 발급 실패 {response.status_code}: {response.text[:200]}")
    return response.json()["access_token"]


def root_password() -> str:
    return Path(os.environ["MINT_ROOT_PASSWORD_FILE"]).read_text().strip()


def sync_rows() -> dict[str, tuple[str, str]]:
    return {row[0]: (row[1], row[2]) for row in sql(
        "SELECT j.server_id, j.status, coalesce(e.scope->>'failure','') FROM litellm_sync_jobs j "
        "LEFT JOIN approval_events e ON e.id=j.event_id")}


def wait_sync(server: str, want: str = "verified", seconds: int = 180, failure: str | None = None) -> float:
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        current = sync_rows().get(server)
        if current and current[0] == want and (failure is None or failure in current[1]):
            return round(time.monotonic() - started, 1)
        time.sleep(3)
    raise SystemExit(f"동기화가 {seconds}초 안에 {server}={want}{'/' + failure if failure else ''}에 이르지 못함: {sync_rows()}")


async def _mcp_call(headers: dict, server: str, arguments: dict) -> tuple[list[str], dict]:
    # Same SDK release as the gateway (mcp 2.2.0), talking to LiteLLM's aggregated MCP endpoint like a harness does.
    async with httpx.AsyncClient(headers=headers, timeout=90) as http:
        async with Client(streamable_http_client(LITE + "/mcp/", http_client=http), read_timeout_seconds=90) as client:
            tools = [tool.name for tool in (await client.list_tools()).tools]
            wanted = [name for name in tools if name in {f"{server}{sep}microsoft_docs_search" for sep in "-_/."}]
            if not wanted:
                return tools, {"error": "tool-not-listed"}
            result = await client.call_tool(wanted[0], arguments)
            text = "".join(getattr(c, "text", "") or "" for c in result.content)
            failed = getattr(result, "is_error", None)
            failed = getattr(result, "isError", False) if failed is None else failed
            return tools, {"is_error": bool(failed), "text": text}


def call(headers: dict, server: str, arguments: dict) -> tuple[list[str], dict]:
    try:
        return asyncio.run(_mcp_call(headers, server, arguments))
    except Exception as exc:  # LiteLLM refuses an unauthorized tool by failing the session; that is a refusal, not a pass
        return [], {"error": type(exc).__name__, "detail": str(exc)[:200]}


def fresh_token(who: str) -> str:
    # Access tokens live ten minutes; each step asks the IdP again instead of carrying an expired one.
    return mcp_token(who, os.environ["EMP_PASSWORD"])


def a_headers(who: str, server: str) -> dict:
    return {"x-litellm-api-key": state()["keys"][who], f"x-mcp-{server}-authorization": f"Bearer {fresh_token(who)}"}


def succeeded(result: dict) -> bool:
    # Learn answers search hits as JSON text; an error, a quota message or an empty body is not a business success.
    return (not result.get("error") and not result.get("is_error") and len(result.get("text", "")) > 200
            and "rate limit" not in result["text"].lower())


def ledger(server: str, since: int) -> list[list[str]]:
    return sql(f"SELECT id, user_token, decision, policy_id, upstream_executed, coalesce(client->>'ingress','') "
               f"FROM decisions WHERE server_id='{server}' AND id>{since} ORDER BY id")


def last_decision() -> int:
    return int(sql("SELECT coalesce(max(id),0) FROM decisions")[0][0])


def register(server: str, tool: str, mask: bool) -> dict:
    s = state()
    requester = console_token("emp1", os.environ["EMP_PASSWORD"])
    approver = console_token("root", root_password())
    os.environ["SSL_CERT_FILE"] = CA  # intake_register uses urllib's default context
    result = intake_register.register(
        MINT, requester, approver, endpoint=LEARN, server_id=server, name="Microsoft Learn " + server,
        tools={tool: "r"}, data_class="public", valid_days=30, allowed=list(EMPLOYEES),
        purpose="사내 개발자가 Microsoft 공식 문서를 검색합니다.", review_note="공급자 공개 문서 검색 도구의 입력 계약을 검토했습니다.",
        risk_acceptance="공개 문서 검색만 허용합니다.", parameter_constraints={tool: CONSTRAINT},
        supplier_assurance=SUPPLIER, impact_input=IMPACT, ack_warnings=True,
        tool_reviews={tool: {"purpose": "공식 문서 검색", "asset": "learn.microsoft.com", "destinations": [], "mask": mask}})
    s.setdefault("intakes", {})[server] = result["intake_id"]
    save(s)
    return result


def prepare() -> None:
    s = {"keys": {}, "users": {}}
    for who in (*EMPLOYEES, "emp3"):
        lite("POST", "/user/new", {"user_id": "lite-" + who, "user_role": "internal_user"})
        s["keys"][who] = lite("POST", "/key/generate", {"user_id": "lite-" + who, "key_alias": who})["key"]
    lite("POST", "/user/new", {"user_id": "mint-sync", "user_role": "proxy_admin"})
    for name in ("admin1", "admin2"):
        s["keys"][name] = lite("POST", "/key/generate", {"user_id": "mint-sync", "key_alias": name})["key"]
        Path(f"/tmp/{name}.key").write_text(s["keys"][name] + "\n")
        Path(f"/tmp/{name}.key").chmod(0o600)
    # MINT creates servers only after reading this switch back from the management API.
    lite("POST", "/config/field/update", {"field_name": "require_key_mcp_access_defined", "field_value": True,
                                          "config_type": "general_settings"})
    field = lite("GET", "/config/field/info", params={"field_name": "require_key_mcp_access_defined"})
    for who in EMPLOYEES:
        fresh_token(who)  # an AI-gateway-only employee gets a grant without a managed PC
    save(s)
    write_bindings(s, mismatched=False)
    evidence("prepare", litellm_version=lite("GET", "/health/readiness").get("litellm_version"),
             explicit_key_access=field.get("field_value"), employees=list(EMPLOYEES))


def write_bindings(s: dict, mismatched: bool) -> None:
    sha = lambda key: hashlib.sha256(key.encode()).hexdigest()  # noqa: E731 - LiteLLM stores the SHA-256 of a virtual key
    users = [{"mint_user_id": who, "litellm_user_id": "lite-" + who, "key_hashes": [sha(s["keys"][who])]} for who in EMPLOYEES]
    if mismatched:
        # emp3's key is bound to an operator mapping that names the wrong LiteLLM owner.
        users.append({"mint_user_id": "emp3", "litellm_user_id": "lite-nobody", "key_hashes": [sha(s["keys"]["emp3"])]})
    Path("/tmp/bindings.json").write_text(json.dumps({"users": users, "teams": [], "workers": ["http://litellm:4000"]}))


def step_register() -> None:
    for server, tool, mask in (("learn", "microsoft_docs_search", True), ("msdocs", "microsoft_docs_search", False)):
        result = register(server, tool, mask)
        evidence("register", server=server, status=result["status"], intake=result["intake_id"])
    seconds = {server: wait_sync(server) for server in ("learn", "msdocs")}
    remote = lite("GET", "/v1/mcp/server")
    servers = remote if isinstance(remote, list) else remote.get("data", remote)
    evidence("sync-verified", seconds=seconds, litellm_servers=sorted(
        f"{x.get('alias') or x.get('server_name')}={x.get('url')}|{x.get('auth_type')}" for x in servers))


def call_a() -> None:
    since = last_decision()
    for who in EMPLOYEES:
        tools, result = call(a_headers(who, "learn"), "learn", {"query": "Azure Functions Python 트리거"})
        evidence("call-a", who=who, tools=tools, ok=succeeded(result), is_error=result.get("is_error"),
                 error=result.get("error"), chars=len(result.get("text", "")))
        assert succeeded(result), result
    rows = ledger("learn", since)
    evidence("ledger-a", rows=rows)
    owners = {row[1] for row in rows if row[2] == "Allow" and row[4] == "t"}
    assert owners == {"emp-emp1", "emp-emp2"}, rows
    # Without the employee's own MINT token LiteLLM has nothing to pass on and MINT refuses: no new Allow.
    before = last_decision()
    _, refused = call({"x-litellm-api-key": state()["keys"]["emp1"]}, "learn", {"query": "Azure"})
    assert not succeeded(refused), refused
    assert not [r for r in ledger("learn", before) if r[2] == "Allow"]
    evidence("call-a-without-mint-token", refused=refused)


def drift() -> None:
    s = state()
    remote_id = "mint_" + hashlib.sha256(b"learn").hexdigest()[:32]
    info = lite("GET", "/key/info", params={"key": s["keys"]["emp1"]})["info"]
    permission = info.get("object_permission") or {}
    tampered = {**permission, "mcp_tool_permissions": {**(permission.get("mcp_tool_permissions") or {}), remote_id: []}}
    tampered.pop("object_permission_id", None)
    lite("POST", "/key/update", {"key": s["keys"]["emp1"], "object_permission": tampered})
    started = time.monotonic()
    while time.monotonic() - started < 240:
        current = lite("GET", "/key/info", params={"key": s["keys"]["emp1"]})["info"]
        tools = ((current.get("object_permission") or {}).get("mcp_tool_permissions") or {}).get(remote_id)
        if tools == ["microsoft_docs_search"]:
            break
        time.sleep(5)
    else:
        raise SystemExit("LiteLLM에서 바꾼 키 권한을 MINT가 4분 안에 되돌리지 못함")
    detected = round(time.monotonic() - started, 1)
    drift_events = sql("SELECT count(*) FROM approval_events WHERE kind='litellm-sync' AND scope::text LIKE '%\"drift\"%'")
    evidence("drift-repaired", seconds=detected, drift_events=drift_events[0][0])
    assert int(drift_events[0][0]) >= 1


def isolation_start() -> None:
    write_bindings(state(), mismatched=True)


def isolation_check() -> None:
    wait_sync("learn", want="failed", failure="key-owner-mismatch")
    _, result = call(a_headers("emp1", "learn"), "learn", {"query": "Azure Container Apps"})
    evidence("isolation", emp1_ok=succeeded(result), sync=sync_rows().get("learn"))
    assert succeeded(result), result
    write_bindings(state(), mismatched=False)


def rotate_check() -> None:
    # The first management key is gone; MINT must keep working on the rotated one without a restart.
    s = state()
    lite("POST", "/key/delete", {"keys": [s["keys"]["admin1"]]})
    evidence("rotate", admin1_deleted=True)


def revoke() -> None:
    root = console_token("root", root_password())
    response = mint("DELETE", "/gw/registry/servers/learn", root)
    assert response.status_code == 200, response.text
    started = time.monotonic()
    while time.monotonic() - started < 180:
        rows = sync_rows().get("learn")
        present = [x for x in _servers() if (x.get("alias") or x.get("server_name")) == "learn"]
        if not present and rows and rows[0] in {"verified", "failed"}:
            break
        time.sleep(3)
    else:
        raise SystemExit(f"철회가 LiteLLM에 반영되지 않음: {sync_rows()}")
    seconds = round(time.monotonic() - started, 1)
    since = last_decision()
    _, revoked = call(a_headers("emp1", "learn"), "learn", {"query": "Azure"})
    _, unrelated = call(a_headers("emp1", "msdocs"), "msdocs", {"query": "Azure Blob Storage"})
    evidence("revoke", seconds=seconds, sync=sync_rows().get("learn"), revoked_ok=succeeded(revoked),
             unrelated_ok=succeeded(unrelated), allow_after=[r for r in ledger("learn", since) if r[2] == "Allow"])
    assert not succeeded(revoked) and succeeded(unrelated)
    assert not [r for r in ledger("learn", since) if r[2] == "Allow"]


def _servers() -> list[dict]:
    remote = lite("GET", "/v1/mcp/server")
    return remote if isinstance(remote, list) else remote.get("data", [])


def recover() -> None:
    register("learn", "microsoft_docs_search", True)
    seconds = wait_sync("learn")
    _, result = call(a_headers("emp2", "learn"), "learn", {"query": "Azure Kubernetes Service"})
    evidence("recover", seconds=seconds, emp2_ok=succeeded(result))
    assert succeeded(result), result


def restart_check() -> None:
    wait_sync("learn")
    _, result = call(a_headers("emp1", "learn"), "learn", {"query": "Azure Monitor"})
    evidence("restart", emp1_ok=succeeded(result))
    assert succeeded(result), result


def call_b() -> None:
    wait_sync("learn")
    server = [x for x in _servers() if (x.get("alias") or x.get("server_name")) == "learn"]
    assert server and server[0].get("url") == LEARN and (server[0].get("auth_type") or "none") == "none", server
    since = last_decision()
    s = state()
    # Plugin route: LiteLLM calls Learn itself; the guardrail sends the employee's MINT token to the decision API first.
    headers = {"x-litellm-api-key": s["keys"]["emp1"], "Authorization": f"Bearer {fresh_token('emp1')}"}
    query = "contact alice.kim@example.com about Azure Functions"
    _, result = call(headers, "learn", {"query": query})
    rows = sql(f"SELECT id, decision, policy_id, client->>'ingress', request_payload::text LIKE '%alice.kim@example.com%', "
               f"privacy_types::text FROM decisions WHERE server_id='learn' AND id>{since} ORDER BY id")
    results = sql("SELECT count(*) FROM approval_events WHERE kind='addon-result' AND target_id IN (" +
                  ",".join(f"'{r[0]}'" for r in rows) + ")") if rows else [["0"]]
    evidence("call-b", ok=succeeded(result), rows=rows, addon_results=results[0][0], url=server[0].get("url"))
    assert succeeded(result), result
    assert rows and rows[-1][1] == "Allow" and rows[-1][3] == "ai-gateway-addon", rows
    assert rows[-1][4] == "f", "가린 인자가 아니라 원래 인자가 기록됨"
    assert "EMAIL" in rows[-1][5], "입력의 메일 주소를 찾지 못해 제한 인자가 적용되지 않음"
    assert int(results[0][0]) >= 1, "사후 기록(addon-result)이 남지 않음"
    # No MINT token: the guardrail refuses before LiteLLM reaches Learn.
    _, refused = call({"x-litellm-api-key": s["keys"]["emp1"]}, "learn", {"query": "Azure"})
    evidence("call-b-without-mint-token", refused=refused)
    assert not succeeded(refused)


STEPS = {"prepare": prepare, "register": step_register, "call-a": call_a, "drift": drift,
         "isolation-start": isolation_start, "isolation-check": isolation_check, "rotate-check": rotate_check,
         "revoke": revoke, "recover": recover, "restart-check": restart_check, "call-b": call_b}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        raise SystemExit("usage: litellm_addon_e2e.py " + "|".join(STEPS))
    STEPS[sys.argv[1]]()
