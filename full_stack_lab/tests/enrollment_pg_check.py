"""Managed Linux and Windows enrollment, activation, heartbeat and reconnect on isolated PostgreSQL."""
from __future__ import annotations

import json
import os
import uuid

from fastapi import HTTPException

from app import db, endpoint_plane, idp, mcp_sessions
from app.agent_contract import authenticated_user, issue_token
from termination_lab_support import Checks, add_principal, apply_schema, isolated_disposal, run, signing_keys

CHECKS = Checks("managed endpoint enrollment and reconnect (PostgreSQL)")


async def refused(awaitable) -> bool:
    try:
        await awaitable
    except (PermissionError, ValueError, HTTPException):
        return True
    return False


async def device_jwt(key: str):
    response = await idp.device_token(x_endpoint_key=key)
    return response, json.loads(response.body)


async def mcp_status(token: str) -> int:
    try:
        await authenticated_user("Bearer " + token, require_mcp=True)
        return 200
    except HTTPException as exc:
        return exc.status_code


async def check_prerequisites():
    owner = "enroll-owner"
    await add_principal(owner)
    await add_principal("enroll-admin", role="admin")
    await db.execute("UPDATE principals SET status='disabled' WHERE token=%s", ("enroll-disabled",))
    await add_principal("enroll-disabled", status="disabled")
    invite = uuid.uuid4()
    await db.execute(
        """INSERT INTO account_invitations(id,username,department,token_sha256,issued_by,expires_at)
           VALUES (%s,'not-accepted','lab',%s,%s,now()+interval '1 hour')""",
        (invite, endpoint_plane._hash_key("unaccepted-invite"), "enroll-admin"))
    await db.execute(
        """INSERT INTO signup_requests(id,username,display_name,password_hash,status)
           VALUES (%s,'awaiting-approval','Awaiting Approval','not-a-password','pending')""", (uuid.uuid4(),))
    CHECKS.ok("가입 승인 전 신청과 미수락 초대는 등록 키트 발급 불가",
              await refused(endpoint_plane.enrollment_token("awaiting-approval"))
              and await refused(endpoint_plane.enrollment_token("not-accepted")))
    CHECKS.ok("중지된 계정은 장치 등록 키트 발급 불가",
              await refused(endpoint_plane.enrollment_token("enroll-disabled")))

    kit = await endpoint_plane.enrollment_token(owner)
    key = "enroll-one-time-key-material-0123456789"
    device = await endpoint_plane.consume_enrollment(kit["enrollment_token"], key, "one-time-host", "enrolluser", 1001)
    CHECKS.ok("등록 토큰은 한 번만 소비됨",
              await refused(endpoint_plane.consume_enrollment(kit["enrollment_token"], key, "one-time-host", "enrolluser", 1001)))
    expired = await endpoint_plane.enrollment_token(owner)
    await db.execute("UPDATE endpoint_enrollment_tokens SET expires_at=now()-interval '1 second' WHERE token_hash=%s",
                     (endpoint_plane._hash_key(expired["enrollment_token"]),))
    CHECKS.ok("30분 만료 토큰은 등록 거부",
              await refused(endpoint_plane.consume_enrollment(expired["enrollment_token"], key, "expired-host", "enrolluser", 1001)))
    await endpoint_plane.revoke_device(device["endpoint_id"], "enroll-admin")


async def exercise_platform(platform: str):
    owner = "enroll-owner"
    admin_token = "enroll-admin"
    await add_principal(admin_token, role="admin")
    key = f"enroll-{platform}-device-key-material-0123456789"
    username = "enrolluser"
    hostname = f"enroll-{platform}-host"
    sid = "S-1-5-21-111-222-333-1001" if platform == "windows" else None
    uid = None if platform == "windows" else 1001
    helper = '"C:\\Program Files\\MINT\\python.exe" -I -S "C:\\Program Files\\MINT\\managed-windows.py" header' if platform == "windows" else None

    async def enroll(device_key: str):
        kit = await endpoint_plane.enrollment_token(owner)
        return await endpoint_plane.consume_enrollment(kit["enrollment_token"], device_key, hostname, username, uid,
                                                       platform=platform, local_sid=sid, helper_command=helper)

    device = await enroll(key)
    endpoint = device["endpoint_id"]
    policy = await endpoint_plane.managed_policy(device)
    checks = {name: True for name in endpoint_plane.managed_checks(device)}
    CHECKS.ok(f"{platform}: DB에 소유자·로컬 신원·새 epoch·대기 상태 기록",
              device["owner_token"] == owner and device["device_epoch"] and device["managed_state"] == "pending"
              and (device["detail"].get("local_sid") == sid))

    pending, _ = await device_jwt(key)
    pending_token, _ = issue_token({"user_id": owner}, minutes=5, client_id=endpoint,
                                   extra={"device_id": endpoint, "device_epoch": device["device_epoch"],
                                          "scope": "mcp"})
    CHECKS.ok(f"{platform}: 대기 장치는 device token과 MCP 인증 거부",
              pending.status_code == 403 and await mcp_status(pending_token) == 403)

    beat = await endpoint_plane.heartbeat(device, policy["policy_hash"], policy["configuration_hashes"], checks)
    CHECKS.ok(f"{platform}: 같은 소유자 장치도 스스로 활성화 불가",
              await refused(endpoint_plane.activate_managed(endpoint, owner, beat["policy_hash"], "self")))
    active = await endpoint_plane.activate_managed(endpoint, admin_token, beat["policy_hash"], "approved")
    issued, body = await device_jwt(key)
    accepted = await authenticated_user("Bearer " + body["access_token"], require_mcp=True) if issued.status_code == 200 else None
    row = await db.fetch_one("SELECT managed_state,status,device_epoch,owner_token FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    CHECKS.ok(f"{platform}: 관리자 활성화 뒤 소유자 MCP 인증 허용",
              active["managed_state"] == row["managed_state"] == "active" and row["status"] == "active"
              and row["owner_token"] == owner and accepted["principal"] == owner
              and await mcp_status(body["access_token"]) == 200)

    other, _ = issue_token({"user_id": "enroll-other"}, minutes=5, client_id=endpoint,
                                extra={"device_id": endpoint, "device_epoch": device["device_epoch"],
                                       "device_policy": policy["policy_hash"], "scope": "mcp"})
    await add_principal("enroll-other")
    CHECKS.ok(f"{platform}: 다른 사용자 토큰은 장치 소유권 불일치로 거부", await mcp_status(other) == 403)

    async def heartbeat(report_hash=policy["policy_hash"], report_checks=checks, report_key=key):
        try:
            authorized = await endpoint_plane.authenticate_device(report_key, "enforcement")
        except PermissionError:
            return None
        return await endpoint_plane.heartbeat(authorized, report_hash, policy["configuration_hashes"], report_checks)

    bad = await heartbeat("0" * 64)
    row = await db.fetch_one("SELECT managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    CHECKS.ok(f"{platform}: 정책 해시가 다른 heartbeat는 격리", bad and not bad["compliant"] and row["managed_state"] == "quarantined")
    normal = await heartbeat()
    row = await db.fetch_one("SELECT managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    CHECKS.ok(f"{platform}: 정상 heartbeat만으로 격리 해제 불가", normal["state"] == row["managed_state"] == "quarantined")
    await endpoint_plane.activate_managed(endpoint, admin_token, policy["policy_hash"], "reactivated")

    false_checks = {**checks, next(iter(checks)): False}
    bad = await heartbeat(report_checks=false_checks)
    row = await db.fetch_one("SELECT managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    CHECKS.ok(f"{platform}: 검사 실패 heartbeat는 격리", bad and not bad["compliant"] and row["managed_state"] == "quarantined")
    await heartbeat()
    CHECKS.ok(f"{platform}: 검사 실패 뒤 정상 heartbeat에도 관리자 재활성화 필요",
              (await db.fetch_one("SELECT managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,)))["managed_state"] == "quarantined")
    await endpoint_plane.activate_managed(endpoint, admin_token, policy["policy_hash"], "reactivated")

    CHECKS.ok(f"{platform}: 다른 장치 키의 heartbeat 거부 및 상태 보존",
              await heartbeat(report_key="wrong-device-key-material-0123456789") is None
              and (await db.fetch_one("SELECT managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,)))["managed_state"] == "active")

    await db.execute("UPDATE endpoint_agents SET heartbeat_at=now()-interval '181 seconds' WHERE endpoint_id=%s", (endpoint,))
    stale, _ = await device_jwt(key)
    row = await db.fetch_one("SELECT managed_state FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    # D-160: stale is refused while stale, not a sticky quarantine (sleeping PCs).
    CHECKS.ok(f"{platform}: 180초 초과 heartbeat는 인증 거부(상태는 유지)", stale.status_code == 403 and row["managed_state"] == "active")
    await heartbeat()
    refreshed, refreshed_body = await device_jwt(key)
    CHECKS.ok(f"{platform}: 정상 보고가 돌아오면 토큰과 MCP 인증 회복",
              refreshed.status_code == 200 and await mcp_status(refreshed_body["access_token"]) == 200)

    session_id = f"enroll-session-{uuid.uuid4()}"
    await mcp_sessions.register(session_id, owner, "enroll-session-jti", endpoint, None)
    replacement_key = f"enroll-{platform}-replacement-key-material-0123456789"
    replacement = await enroll(replacement_key)
    old_row = await db.fetch_one("SELECT status FROM endpoint_agents WHERE endpoint_id=%s", (endpoint,))
    old_session = await db.fetch_one(
        "SELECT terminated_at,termination_reason FROM mcp_client_sessions WHERE session_hash=%s",
        (mcp_sessions._digest(session_id),))
    pool_notice = await db.fetch_one(
        "SELECT 1 FROM upstream_pool_events WHERE principal=%s AND reason='device-re-enrolled'",
        (owner,))
    CHECKS.ok(f"{platform}: 같은 로컬 장치 재등록은 새 epoch로 이전 장치 폐기",
              replacement["endpoint_id"] != endpoint and replacement["device_epoch"] != device["device_epoch"]
              and replacement["managed_state"] == "pending" and old_row["status"] == "revoked"
              and await mcp_status(refreshed_body["access_token"]) == 401)
    CHECKS.ok(f"{platform}: 재등록은 기존 MCP 세션을 종료하고 연결 풀 정리를 알림",
              old_session["terminated_at"] is not None
              and old_session["termination_reason"] == "device-re-enrolled" and pool_notice is not None)
    replacement_policy = await endpoint_plane.managed_policy(replacement)
    replacement_checks = {name: True for name in endpoint_plane.managed_checks(replacement)}
    await endpoint_plane.heartbeat(replacement, replacement_policy["policy_hash"],
                                   replacement_policy["configuration_hashes"], replacement_checks)
    await endpoint_plane.activate_managed(replacement["endpoint_id"], admin_token, replacement_policy["policy_hash"], "re-enrolled")
    await endpoint_plane.revoke_device(replacement["endpoint_id"], admin_token)


async def run_checks():
    signing_keys()
    os.environ["AUTH_PROVIDER"] = "local"
    await apply_schema()
    with isolated_disposal():
        await CHECKS.case("prerequisites", check_prerequisites())
        for platform in ("linux", "windows"):
            await CHECKS.case(platform, exercise_platform(platform))
    return CHECKS.finish()


if __name__ == "__main__":
    run(run_checks)
