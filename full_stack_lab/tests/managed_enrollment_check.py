"""Real IdP/DB boundary checks; no MCP supplier or OS enforcement is simulated.

Run inside gateway: docker compose exec -T gateway python - < tests/managed_enrollment_check.py
Active-device/kernel proof is the separate ordinary-account installation on PJ1.
"""
import asyncio
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

from app import db, endpoint_plane

BASE = "http://agent-service:8000"


def call(path, body, *, token=None, key=None, form=False):
    data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["X-Endpoint-Key"] = key
    request = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


async def main():
    name, password = "enroll-check-" + secrets.token_hex(4), secrets.token_urlsafe(20)
    principal = "emp-" + name
    created = False
    try:
        status, result = call("/auth/signup", {"username": name, "display_name": "Enrollment boundary check", "password": password})
        assert status == 200 and result["status"] == "pending", result
        status, admin = call("/auth/mock-login", {"email": "kkg@bob.local", "password": os.getenv("MOCK_SSO_PASSWORD", "test-password")})
        assert status == 200, admin
        admin = admin["access_token"]
        request = await db.fetch_one("SELECT id FROM signup_requests WHERE username=%s", (name,))
        status, result = call(f'/api/signup-requests/{request["id"]}/approve', {}, token=admin)
        assert status == 200 and result["status"] == "approved", result
        created = True
        person = await db.fetch_one("SELECT * FROM principals WHERE token=%s", (principal,))
        assert person["managed_required"] is True
        status, result = call("/oauth/token", {"grant_type": "password", "client_id": "unmanaged", "username": name, "password": password}, form=True)
        assert status == 403 and result["error"] == "invalid_client", result
        grant = await endpoint_plane.enrollment_token(principal)
        key = secrets.token_urlsafe(32)
        body = {"enrollment_token": grant["enrollment_token"], "device_key": key,
                "hostname": "protocol-boundary-check", "local_username": "boundary", "local_uid": 1234}
        race = await asyncio.gather(*[asyncio.to_thread(call, "/oauth/device-enroll", body) for _ in range(2)])
        assert sorted(status for status, _ in race) == [201, 403], race
        device = next(result for status, result in race if status == 201)
        assert device["state"] == "pending" and device["owner_token"] == principal
        status, result = call("/oauth/device-token", {}, key=key)
        assert status == 403 and result["error"] == "invalid_grant", result
        status, result = call("/oauth/device-token", {}, key=secrets.token_urlsafe(32))
        assert status == 401 and result["error"] == "invalid_client", result
        expired = await endpoint_plane.enrollment_token(principal)
        await db.execute("UPDATE endpoint_enrollment_tokens SET expires_at=now()-interval '1 second' WHERE token_hash=%s",
                         (endpoint_plane._hash_key(expired["enrollment_token"]),))
        status, result = call("/oauth/device-enroll", {**body, "enrollment_token": expired["enrollment_token"]})
        assert status == 403, result
        failure = await endpoint_plane.managed_failure(person, {"device_id": device["endpoint_id"], "device_epoch": device["device_epoch"], "scope": "mcp"})
        assert failure and "미활성" in failure
        try:
            await endpoint_plane.activate_managed(device["endpoint_id"], principal, "0" * 64, "Self approval must never activate this device.")
        except ValueError:
            pass
        else:
            raise AssertionError("Self approval activated a device")
        await endpoint_plane.revoke_device(device["endpoint_id"], "kkg")
        status, result = call("/oauth/device-token", {}, key=key)
        assert status == 401, result
        print("PASS signup requires managed enrollment; one-time race/expiry; pending/foreign-key/self-approval/revocation fail closed")
    finally:
        if created:
            await db.execute("UPDATE endpoint_agents SET status='revoked' WHERE owner_token=%s", (principal,))
            await db.execute("UPDATE principals SET status='deleted' WHERE token=%s", (principal,))
        await db.close()


asyncio.run(main())
