"""Reproductions of the paper's experiments E1-E3 on this lab's real components.

    python -m app.experiments e1|e2|e3        (./console.sh experiment e1)

Each run repeats the measurement N times (default 5, as in the paper) and prints one
JSON document: the observations, and what they mean for the criteria.

E1  Token revocation (RFC 7009) vs. what a resource server actually accepts.
    The IdP answers 200 and introspection (RFC 7662) turns inactive at once, but a
    verifier that only checks signatures keeps accepting the token until `exp`.
    Revoking only the access token leaves the refresh token usable.
E2  Session termination (Streamable HTTP, revisions before 2026-07-28): DELETE with
    Mcp-Session-Id against the ten real MCP servers - who issues sessions at all,
    who answers 405, and whether the session keeps working afterwards.
E3  Dual delegation: after the upstream (IdP) credential is revoked and confirmed
    inactive by introspection, the MCP server's own downstream credential (a Gitea
    token of the gitea-mcp account) still reads the repositories - until the provider
    side revokes it. Uses a dedicated experiment token of the same account so the
    running lab keeps working.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import sys
import time
from datetime import UTC, datetime

import httpx
import jwt

from . import db, registry

# 실기기 배치(compose.field.yaml)에서는 IDP_ISSUER가 PC용 공개 주소라 컨테이너 안에서 풀리지 않는다.
IDP = (os.getenv("IDP_INTERNAL_URL") or os.getenv("IDP_ISSUER", "http://agent-service:8000")).rstrip("/")
GITEA = os.getenv("GITEA_ADMIN_URL", "http://corp-git:3000").rstrip("/")
GITEA_ADMIN = os.getenv("GITEA_ADMIN_USER", "corpadmin")
GITEA_ADMIN_PASSWORD = os.getenv("GITEA_ADMIN_PASSWORD", "corp-admin-lab-only")
EXPERIMENT_USER = os.getenv("EXPERIMENT_EMAIL", "pse@bob.local")
EXPERIMENT_PASSWORD = os.getenv("MOCK_SSO_PASSWORD", "test-password")
ROUNDS = int(os.getenv("EXPERIMENT_ROUNDS", "5"))


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def _token(client: httpx.AsyncClient, client_id: str) -> dict:
    response = await client.post(f"{IDP}/oauth/token", data={
        "grant_type": "password", "client_id": client_id, "username": EXPERIMENT_USER, "password": EXPERIMENT_PASSWORD})
    response.raise_for_status()
    return response.json()


def _stateless_accepts(token: str) -> bool:
    """A resource server that validates only the signature and the claims."""
    from .agent_contract import ALGORITHM, AUDIENCE, ISSUER, public_key
    try:
        jwt.decode(token, public_key(), algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
        return True
    except jwt.PyJWTError:
        return False


async def _stateful_accepts(token: str) -> bool:
    """The Gateway's own check: signature + revocation list + account ledger."""
    from fastapi import HTTPException

    from .agent_contract import authenticated_user
    try:
        await authenticated_user(f"Bearer {token}")
        return True
    except HTTPException:
        return False


async def e1() -> dict:
    from .idp import introspection
    rounds = []
    async with httpx.AsyncClient(timeout=20) as client:
        for index in range(ROUNDS):
            issued = await _token(client, f"e1-client-{index}")
            access, refresh = issued["access_token"], issued["refresh_token"]
            revoke = await client.post(f"{IDP}/oauth/revoke", data={"token": access, "token_type_hint": "access_token"})
            revoke_again = await client.post(f"{IDP}/oauth/revoke", data={"token": access})
            bogus = await client.post(f"{IDP}/oauth/revoke", data={"token": "not-a-token-" + secrets.token_hex(4)})
            introspected = await introspection(access)
            exp = jwt.decode(access, options={"verify_signature": False})["exp"]
            refreshed = await client.post(f"{IDP}/oauth/token", data={
                "grant_type": "refresh_token", "client_id": f"e1-client-{index}", "refresh_token": refresh})
            new_access = refreshed.json().get("access_token") if refreshed.status_code == 200 else None
            rounds.append({
                "revocation_http_status": revoke.status_code,
                "revocation_again_http_status": revoke_again.status_code,
                "revocation_of_garbage_http_status": bogus.status_code,
                "introspection_active_after": introspected.get("active"),
                "stateless_resource_server_accepts_after": _stateless_accepts(access),
                "stateful_gateway_accepts_after": await _stateful_accepts(access),
                "seconds_until_exp": max(0, int(exp - time.time())),
                "refresh_token_still_works": new_access is not None,
                "new_access_token_accepted_by_gateway": bool(new_access) and await _stateful_accepts(new_access),
            })
            if refreshed.status_code == 200:  # clean up the family
                await client.post(f"{IDP}/oauth/revoke", data={"token": refreshed.json()["refresh_token"]})
    return {
        "experiment": "E1", "at": _now(), "rounds": rounds,
        "findings": {
            "revocation_always_200": all(r["revocation_http_status"] == 200 and r["revocation_of_garbage_http_status"] == 200 for r in rounds),
            "introspection_inactive": all(r["introspection_active_after"] is False for r in rounds),
            "stateless_gap": all(r["stateless_resource_server_accepts_after"] for r in rounds),
            "gateway_blocks_immediately": not any(r["stateful_gateway_accepts_after"] for r in rounds),
            "refresh_survives_access_revocation": all(r["refresh_token_still_works"] for r in rounds),
        },
        "meaning": ("RFC 7009 응답(200)은 무효 토큰에도 같게 나오므로 대상 상태를 특정하지 못한다(C4 불충족 사유). "
                    "조사 응답은 즉시 비활성이지만 서명만 검증하는 자원 서버는 만료까지 수락한다(C3 공백 → T2). "
                    "접근 토큰만 폐기하면 갱신 토큰으로 새 접근 토큰을 받는다. 이 Gateway는 폐기 목록을 조회해 즉시 차단한다."),
    }


async def session_termination(endpoint: str) -> dict:
    """One E2 measurement against one Streamable HTTP endpoint."""
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "MCP-Protocol-Version": "2025-11-25"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "e2-probe", "version": "1"}}}
    out: dict = {"endpoint": endpoint}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(endpoint, json=init, headers=headers)
        session = response.headers.get("mcp-session-id")
        out.update({"initialize_status": response.status_code, "session_issued": bool(session)})
        if not session:
            out["meaning"] = "세션을 발급하지 않는 상태 비저장 서버 — 종료를 요청할 세션 자체가 없다"
            return out
        headers["Mcp-Session-Id"] = session
        await client.post(endpoint, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers)
        deleted = await client.delete(endpoint, headers=headers)
        out["delete_status"] = deleted.status_code
        after = await client.post(endpoint, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers)
        out["same_session_after_delete_status"] = after.status_code
        out["session_still_works"] = after.status_code == 200
        out["meaning"] = ("405 — 서버가 종료 요청을 거부했다. 소멸 시점은 서버 정책에 달렸다" if deleted.status_code == 405
                          else "종료 요청 수락" + (" · 그러나 같은 세션 호출이 계속 성립" if after.status_code == 200 else ""))
    return out


async def e2() -> dict:
    results = {}
    for server_id, spec in registry.servers().items():
        runs = []
        for _ in range(ROUNDS):
            try:
                runs.append(await session_termination(spec["endpoint"]))
            except Exception as exc:
                runs.append({"endpoint": spec["endpoint"], "error": f"{type(exc).__name__}: {exc}"[:200]})
        results[server_id] = {"sample": runs[0], "rounds": len(runs),
                              "consistent": len({json.dumps({k: v for k, v in r.items() if k != "endpoint"}, sort_keys=True) for r in runs}) == 1}
    issued = [k for k, v in results.items() if v["sample"].get("session_issued")]
    return {
        "experiment": "E2", "at": _now(), "servers": results,
        "findings": {"servers_without_sessions": sorted(set(results) - set(issued)), "servers_with_sessions": issued,
                     "delete_rejected_405": [k for k, v in results.items() if v["sample"].get("delete_status") == 405],
                     "session_survives_delete": [k for k, v in results.items() if v["sample"].get("session_still_works")]},
        "meaning": ("세션 계층에는 조직이 원용할 종료 수단이 거의 없다. 상태 비저장 서버에는 끊을 세션이 없고, "
                    "세션이 있어도 종료 요청의 발신 기록은 종료 의사 표시만 증명한다(논문 3.1)."),
    }


def _gitea(sudo: str | None = None, token: str | None = None) -> dict:
    if token:
        return {"Authorization": f"token {token}"}
    basic = base64.b64encode(f"{GITEA_ADMIN}:{GITEA_ADMIN_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}"}
    if sudo:
        headers["Sudo"] = sudo
    return headers


async def e3() -> dict:
    from .idp import introspection
    creds = (registry.server("gitea") or {}).get("server_held_credentials") or []
    account = creds[0]["account"] if creds else "mcp-bot"
    rounds = []
    async with httpx.AsyncClient(timeout=20) as client:
        for index in range(ROUNDS):
            name = f"e3-experiment-{int(time.time())}-{index}"
            created = await client.post(f"{GITEA}/api/v1/users/{account}/tokens", headers=_gitea(sudo=account),
                                        json={"name": name, "scopes": ["read:repository"]})
            created.raise_for_status()
            server_token = created.json()["sha1"]
            # Upstream: the organisation's client credential for the relationship.
            issued = await _token(client, f"e3-client-{index}")
            await client.post(f"{IDP}/oauth/revoke", data={"token": issued["refresh_token"]})
            await client.post(f"{IDP}/oauth/revoke", data={"token": issued["access_token"]})
            upstream_inactive = (await introspection(issued["access_token"])).get("active") is False and \
                (await introspection(issued["refresh_token"])).get("active") is False
            # Downstream: the MCP server's own credential against the document store.
            before = await client.get(f"{GITEA}/api/v1/repos/bob/payment-service/contents/README.md", headers=_gitea(token=server_token))
            revoked = await client.delete(f"{GITEA}/api/v1/users/{account}/tokens/{name}", headers=_gitea(sudo=account))
            after = await client.get(f"{GITEA}/api/v1/repos/bob/payment-service/contents/README.md", headers=_gitea(token=server_token))
            rounds.append({
                "upstream_fully_revoked_and_introspected_inactive": upstream_inactive,
                "downstream_access_with_server_credential_after_upstream_revocation": before.status_code,
                "provider_side_revocation_status": revoked.status_code,
                "downstream_access_after_provider_revocation": after.status_code,
            })
    return {
        "experiment": "E3", "at": _now(), "account": account, "rounds": rounds,
        "findings": {
            "upstream_revoked": all(r["upstream_fully_revoked_and_introspected_inactive"] for r in rounds),
            "downstream_access_persisted": all(r["downstream_access_with_server_credential_after_upstream_revocation"] == 200 for r in rounds),
            "blocked_only_after_provider_revocation": all(r["downstream_access_after_provider_revocation"] in (401, 403) for r in rounds),
        },
        "meaning": ("상위 자격을 완전히 폐기하고 조사 응답으로 확인해도, MCP 서버가 하위 시스템에 보유한 자격으로의 접근은 "
                    "제공자가 그 자격을 폐기할 때까지 성립한다. 제공자가 고지하지 않으면 모집단조차 열거할 수 없다(C1 → T3). "
                    "이 실습에서는 조직이 하위 시스템(Gitea)의 관리자라서 고지된 자격을 스스로 폐기·확인할 수 있다(C2·C4)."),
    }


async def main(name: str) -> int:
    await db.wait_until_ready()
    runner = {"e1": e1, "e2": e2, "e3": e3}.get(name)
    if not runner:
        print("usage: python -m app.experiments e1|e2|e3", file=sys.stderr)
        return 2
    print(json.dumps(await runner(), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "")))
