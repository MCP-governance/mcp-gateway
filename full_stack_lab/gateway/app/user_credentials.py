"""Credentials an employee connects for a service that must see that employee, not the organisation (D-235).

The employee's own GitHub account is the first one. The value is used only for that employee's calls to that
server's registered endpoint: it is never an MINT login token (AGENTS.md), never a shared one, and never leaves
this module in plaintext except as the Authorization header of such a call. The database holds AES-GCM
ciphertext bound to (principal, endpoint); the key is the device secret USER_CREDENTIAL_KEY (console.sh).
Nothing here logs, returns or records a value: the ledger gets who, which service, which account name, when.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import db, review

LOG = logging.getLogger(__name__)

# Hosts whose servers need a per-employee credential. A registration may opt out with credential_scope="shared".
SERVICES = {
    "api.githubcopilot.com": {
        "label": "GitHub",
        "user_url": "https://api.github.com/user",
        "token_url": "https://github.com/settings/personal-access-tokens/new",
        "device_code_url": "https://github.com/login/device/code",
        "device_token_url": "https://github.com/login/oauth/access_token",
    },
}
TOKEN_FORMAT = re.compile(r"^[\x21-\x7e]{8,2000}$")
KINDS = ("token", "device")
DEVICE_SCOPES = os.getenv("GITHUB_OAUTH_SCOPES", "repo read:org read:user")
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device-code"
DEVICE_LIFETIME_CAP = 900
MIN_INTERVAL = 5


class Unavailable(RuntimeError):
    """The device key is missing or malformed: nothing can be stored or read."""


class Rejected(ValueError):
    """The service did not accept the credential (message is safe to show)."""


def service_for(spec: dict | None) -> dict | None:
    if not spec or spec.get("credential_scope") == "shared" or not spec.get("endpoint"):
        return None
    return SERVICES.get(urlsplit(spec["endpoint"]).hostname or "")


def _key() -> bytes:
    raw = os.getenv("USER_CREDENTIAL_KEY", "")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except ValueError:
        key = b""
    if len(key) != 32:
        raise Unavailable("직원 연결 보관 키가 없습니다.")
    return key


def available() -> bool:
    try:
        _key()
        return True
    except Unavailable:
        return False


def _aad(principal: str, endpoint: str) -> bytes:
    return f"{principal}\n{endpoint}".encode()


def seal(principal: str, endpoint: str, secret: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(_key()).encrypt(nonce, secret.encode(), _aad(principal, endpoint))


def unseal(principal: str, endpoint: str, blob: bytes) -> str:
    blob = bytes(blob)
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], _aad(principal, endpoint)).decode()


def _expired(expires_at) -> bool:
    return bool(expires_at) and expires_at <= datetime.now(UTC)


async def lookup(principal: str, endpoint: str) -> dict | None:
    """The principal's usable credential for this endpoint, or None (absent, undecryptable, or expired)."""
    row = await db.fetch_one(
        """SELECT ciphertext, expires_at, last_used_at FROM user_upstream_credentials
            WHERE principal=%s AND endpoint=%s""", (principal, endpoint))
    if not row:
        return None
    try:
        secret = unseal(principal, endpoint, row["ciphertext"])
    except Exception:
        # A changed key or a swapped row reads as "not connected"; the cause is not worth a value in a log.
        LOG.warning("stored employee credential could not be read")
        return None
    last = row["last_used_at"]
    if not last or last < datetime.now(UTC) - timedelta(minutes=5):
        await db.execute("UPDATE user_upstream_credentials SET last_used_at=now() WHERE principal=%s AND endpoint=%s",
                         (principal, endpoint))
    return {"secret": secret, "expires_at": row["expires_at"].timestamp() if row["expires_at"] else 0}


async def listing(principal: str) -> dict[str, dict]:
    rows = await db.fetch_all(
        """SELECT endpoint, kind, account, expires_at, created_at, last_used_at FROM user_upstream_credentials
            WHERE principal=%s""", (principal,))
    return {row["endpoint"]: row for row in rows}


async def save(principal: str, endpoint: str, secret: str, kind: str, account: str, expires_at: datetime | None,
               actor: str | None = None) -> dict:
    if kind not in KINDS or not TOKEN_FORMAT.match(secret) or not account:
        raise ValueError("연결 정보 형식이 올바르지 않습니다.")
    blob = seal(principal, endpoint, secret)
    async with db.transaction() as connection:
        row = await (await connection.execute(
            """INSERT INTO user_upstream_credentials(principal, endpoint, kind, account, ciphertext, expires_at)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (principal, endpoint) DO UPDATE SET kind=EXCLUDED.kind, account=EXCLUDED.account,
                 ciphertext=EXCLUDED.ciphertext, expires_at=EXCLUDED.expires_at, created_at=now(), last_used_at=NULL
               RETURNING kind, account, expires_at, created_at""",
            (principal, endpoint, kind, account, blob, expires_at))).fetchone()
        await review.record_event(
            "upstream-credential-connect", "recorded", "upstream-credential", f"{principal}|{endpoint}", actor or principal,
            applicant=principal, reason="직원 계정 연결",
            scope={"endpoint": endpoint, "kind": kind, "account": account,
                   "expires_at": expires_at.isoformat() if expires_at else None}, connection=connection)
    return row


async def remove(principal: str, endpoint: str | None, reason: str, actor: str | None = None) -> list[dict]:
    """Delete the principal's credentials (one endpoint, or all); each deletion is a ledger event without a value."""
    async with db.transaction() as connection:
        gone = await (await connection.execute(
            """DELETE FROM user_upstream_credentials WHERE principal=%s AND (%s::text IS NULL OR endpoint=%s)
               RETURNING endpoint, kind, account""", (principal, endpoint, endpoint))).fetchall()
        for row in gone:
            await review.record_event(
                "upstream-credential-disconnect", "recorded", "upstream-credential", f"{principal}|{row['endpoint']}",
                actor or principal, applicant=principal, reason=reason,
                scope={"endpoint": row["endpoint"], "kind": row["kind"], "account": row["account"]}, connection=connection)
    return list(gone)


async def holders(endpoint: str) -> list[dict]:
    return await db.fetch_all(
        """SELECT c.principal, c.account, p.display_name, p.user_id FROM user_upstream_credentials c
             LEFT JOIN principals p ON p.token=c.principal WHERE c.endpoint=%s ORDER BY c.principal""", (endpoint,))


# ── service calls ────────────────────────────────────────────────────────────
def _http() -> httpx.AsyncClient:
    # Fixed GitHub hosts only; no proxy variable may reroute a token, and no redirect may carry it elsewhere.
    return httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False)


def _token_expiry(response: httpx.Response) -> datetime | None:
    raw = response.headers.get("github-authentication-token-expiration", "").replace(" UTC", "").strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


async def verify(service: dict, secret: str) -> tuple[str, datetime | None]:
    """The account name the token belongs to and when it lapses; raises Rejected with a safe message."""
    if not TOKEN_FORMAT.match(secret):
        raise Rejected("토큰 형식이 올바르지 않습니다.")
    try:
        async with _http() as client:
            response = await client.get(service["user_url"], headers={
                "Authorization": f"Bearer {secret}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "MINT"})
    except httpx.HTTPError:
        raise Rejected(f"{service['label']}에 연결하지 못했습니다. 잠시 후 다시 시도하세요.") from None
    if response.status_code in (401, 403):
        raise Rejected(f"{service['label']}이 이 토큰을 받아들이지 않았습니다. 토큰과 권한을 확인하세요.")
    try:
        login = response.json()["login"] if response.status_code == 200 else ""
    except (ValueError, KeyError, TypeError):
        login = ""
    if not isinstance(login, str) or not login:
        raise Rejected(f"{service['label']}에서 계정을 확인하지 못했습니다. 잠시 후 다시 시도하세요.")
    return login, _token_expiry(response)


def device_client_id() -> str:
    return os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()


# Pending device authorisations. ponytail: one agent-service process; a restart means "start again".
_flows: dict[str, dict] = {}


def _forget_old() -> None:
    now = time.monotonic()
    for key in [k for k, flow in _flows.items() if flow["until"] <= now]:
        del _flows[key]


async def device_start(principal: str, endpoint: str, service: dict) -> dict:
    client_id = device_client_id()
    if not client_id:
        raise Rejected("GitHub 인증 앱이 설정되지 않았습니다.")
    try:
        async with _http() as client:
            response = await client.post(service["device_code_url"], data={"client_id": client_id, "scope": DEVICE_SCOPES},
                                         headers={"Accept": "application/json", "User-Agent": "MINT"})
        body = response.json()
        code, user_code, uri = body["device_code"], body["user_code"], body["verification_uri"]
        life, interval = int(body.get("expires_in", 900)), int(body.get("interval", MIN_INTERVAL))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise Rejected(f"{service['label']}에서 인증 코드를 받지 못했습니다. 잠시 후 다시 시도하세요.") from None
    _forget_old()
    for key in [k for k, flow in _flows.items() if flow["principal"] == principal]:
        del _flows[key]
    flow_id = secrets.token_urlsafe(16)
    now = time.monotonic()
    _flows[flow_id] = {"principal": principal, "endpoint": endpoint, "device_code": code, "interval": max(interval, MIN_INTERVAL),
                       "next": now + max(interval, MIN_INTERVAL), "until": now + min(life, DEVICE_LIFETIME_CAP)}
    return {"flow_id": flow_id, "user_code": user_code, "verification_uri": uri,
            "interval": _flows[flow_id]["interval"], "expires_in": min(life, DEVICE_LIFETIME_CAP)}


async def device_poll(principal: str, flow_id: str, service: dict) -> dict:
    """pending | connected | expired | denied | failed. A finished flow is forgotten."""
    _forget_old()
    flow = _flows.get(flow_id)
    if not flow or flow["principal"] != principal:
        return {"state": "expired"}
    if time.monotonic() < flow["next"]:
        return {"state": "pending", "interval": flow["interval"]}
    try:
        async with _http() as client:
            response = await client.post(service["device_token_url"], data={
                "client_id": device_client_id(), "device_code": flow["device_code"], "grant_type": DEVICE_GRANT},
                headers={"Accept": "application/json", "User-Agent": "MINT"})
        body = response.json()
    except (httpx.HTTPError, ValueError):
        flow["next"] = time.monotonic() + flow["interval"]
        return {"state": "pending", "interval": flow["interval"]}
    error = body.get("error") if isinstance(body, dict) else "invalid"
    if error in ("authorization_pending", "slow_down"):
        if error == "slow_down":
            flow["interval"] = int(body.get("interval") or flow["interval"] + 5)
        flow["next"] = time.monotonic() + flow["interval"]
        return {"state": "pending", "interval": flow["interval"]}
    del _flows[flow_id]
    if error:
        return {"state": {"expired_token": "expired", "access_denied": "denied"}.get(error, "failed")}
    token = body.get("access_token")
    if not isinstance(token, str):
        return {"state": "failed"}
    try:
        account, expires = await verify(service, token)
        life = body.get("expires_in")
        if isinstance(life, int) and life > 0:
            expires = datetime.now(UTC) + timedelta(seconds=life)
        row = await save(principal, flow["endpoint"], token, "device", account, expires)
    except (Rejected, ValueError):
        return {"state": "failed"}
    return {"state": "connected", "account": row["account"]}


__all__ = ["service_for", "available", "lookup", "listing", "save", "remove", "holders", "verify", "device_start",
           "device_poll", "device_client_id", "Rejected", "Unavailable"]
