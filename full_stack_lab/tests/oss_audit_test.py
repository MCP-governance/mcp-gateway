"""Security-boundary checks; provider success is tested separately against Keycloak."""
import asyncio
import hashlib
import json
import logging
import os
import secrets
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import audit, main, oidc, secret_scan
from intake_worker import gitleaks_counts

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
REFRESH_ENV = {"OIDC_ISSUER": "https://idp.example", "OIDC_CLIENT_ID": "cid", "OIDC_CLIENT_SECRET": "client-secret",
               "OIDC_SESSION_SECRET": "session-secret-" * 3}


@patch.dict(os.environ, REFRESH_ENV)
def refresh_cases(module):
    """Run module._refresh_upstream over every branch with a fake ledger and IdP; return {case: (result, log)}."""
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    def row(**over):
        base = {"upstream_token": module.seal("old-access"), "upstream_refresh_token": module.seal("old-refresh"),
                "upstream_expires_at": NOW - timedelta(seconds=5), "expires_at": NOW + timedelta(hours=1),
                "last_activity_at": NOW - timedelta(minutes=1), "user_id": "u", "status": "active"}
        return {**base, **over}

    def reply(status=200, **body):
        def raise_for_status():
            if status >= 400:
                raise RuntimeError("status")
        return lambda: SimpleNamespace(status_code=status, json=lambda: body, raise_for_status=raise_for_status)

    def down():
        raise ConnectionError("down")

    def refused():
        raise AssertionError("no IdP call expected")

    def plain(value):
        return module.unseal(bytes(value)) if isinstance(value, bytes) else value

    def casefile(found, post, metadata=True):
        log = []

        class Cursor:
            async def fetchone(self):
                return found

        class Conn:
            async def execute(self, sql, params=()):
                log.append(("sql", " ".join(sql.split()), tuple(plain(v) for v in params)))
                return Cursor()

        @asynccontextmanager
        async def transaction():
            yield Conn()

        class Http:
            def __init__(self, **kwargs):
                log.append(("client", kwargs))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, auth, data):
                log.append(("post", url, auth, data))
                return post()

        loaded = (AsyncMock(return_value={"token_endpoint": "https://idp.example/token"}) if metadata
                  else AsyncMock(side_effect=RuntimeError("metadata")))
        with patch.object(module.db, "transaction", transaction), patch.object(module.httpx, "AsyncClient", Http), \
                patch.object(module, "datetime", Clock), patch.object(module, "http_transport", lambda: "pinned"), \
                patch.object(module, "client", lambda: SimpleNamespace(load_server_metadata=loaded)):
            try:
                result = asyncio.run(module._refresh_upstream({"jti": "j", "identity_binding": "b"}))
                if result:
                    result = {**result, "upstream_token": plain(result["upstream_token"])}
            except HTTPException as exc:
                result = ("HTTP", exc.status_code, exc.detail)
        return result, log

    ok = {"access_token": "new-access", "expires_in": 3600}
    return {
        "fresh": casefile(row(upstream_expires_at=NOW + timedelta(seconds=120)), refused),
        "rotated": casefile(row(), reply(**ok, refresh_token="new-refresh")),
        "kept refresh": casefile(row(), reply(**ok)),
        "invalid_grant": casefile(row(), reply(400, error="invalid_grant")),
        "other 400": casefile(row(), reply(400, error="invalid_request")),
        "no access token": casefile(row(), reply(expires_in=3600)),
        "no lifetime": casefile(row(), reply(access_token="x", expires_in=0)),
        "idp down": casefile(row(), down),
        "metadata down": casefile(row(), refused, metadata=False),
        "no refresh token": casefile(row(upstream_refresh_token=None), refused),
        "missing": casefile(None, refused),
        "suspended": casefile(row(status="suspended"), refused),
        "session over": casefile(row(expires_at=NOW), refused),
        "idle": casefile(row(last_activity_at=NOW - timedelta(minutes=30)), refused),
    }


@patch.dict(os.environ, REFRESH_ENV)
def session_cases(module):
    """Run module.validate_session / touch_session / end_session over every branch with a fake ledger and IdP."""
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    issuer = "https://idp.example"
    base = {"scope": "console", "jti": "j", "sub": "u", "identity_binding": "b"}
    metadata_ok = {"introspection_endpoint": issuer + "/introspect", "revocation_endpoint": issuer + "/revoke"}

    def plain(value):
        return module.unseal(bytes(value)) if isinstance(value, bytes) else value

    def person(**over):
        return {"expires_at": NOW + timedelta(hours=1), "last_activity_at": NOW - timedelta(minutes=1),
                "user_id": "u", "role": "employee", "status": "active", **over}

    def upstream(**over):
        return {"upstream_token": module.seal("access"), "upstream_refresh_token": module.seal("refresh"),
                "upstream_expires_at": NOW + timedelta(minutes=10), "issuer": issuer, **over}

    def reply(body=None, status=200, bad_json=False):
        def raise_for_status():
            if status >= 400:
                raise RuntimeError("status")

        def json():
            if bad_json:
                raise ValueError("json")
            return body
        return lambda: SimpleNamespace(status_code=status, json=json, raise_for_status=raise_for_status)

    def down():
        raise ConnectionError("down")

    def silent():
        return SimpleNamespace(status_code=200)

    def case(operation, claims, *, provider="local", sess=None, row=None, ended=None, metadata=metadata_ok,
             introspect=None, revoke=silent, refresh=None, changed=1):
        log, warned = [], []

        async def fetch_one(sql, params=()):
            sql = " ".join(sql.split())
            log.append(("fetch", sql, tuple(params)))
            if "cs.expires_at" in sql:
                return sess
            return row if "upstream_expires_at" in sql else ended

        async def execute(sql, params=()):
            log.append(("sql", " ".join(sql.split()), tuple(params)))
            return changed

        class Http:
            def __init__(self, **kwargs):
                log.append(("client", kwargs))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, auth, data):
                log.append(("post", url, auth, {k: plain(v) for k, v in data.items()}))
                return (introspect if url.endswith("/introspect") else revoke)()

        async def refreshed(given):
            log.append(("refresh", given["jti"], given["identity_binding"]))
            return refresh

        class Collect(logging.Handler):
            def emit(self, record):
                warned.append(record.getMessage())

        logger, collect = logging.getLogger(module.__name__), Collect()
        logger.addHandler(collect)
        loaded = (AsyncMock(return_value=metadata) if metadata is not None
                  else AsyncMock(side_effect=RuntimeError("metadata")))
        try:
            with patch.dict(os.environ, {"AUTH_PROVIDER": provider}), patch.object(module.db, "fetch_one", fetch_one), \
                    patch.object(module.db, "execute", execute), patch.object(module.httpx, "AsyncClient", Http), \
                    patch.object(module, "datetime", Clock), patch.object(module, "http_transport", lambda: "pinned"), \
                    patch.object(module, "client", lambda: SimpleNamespace(load_server_metadata=loaded)), \
                    patch.object(module, "_refresh_upstream", refreshed):
                try:
                    result = asyncio.run(getattr(module, operation)(claims))
                except HTTPException as exc:
                    result = ("HTTP", exc.status_code, exc.detail, exc.headers)
        finally:
            logger.removeHandler(collect)
        return result, log + [("warn", message) for message in warned]

    active, inactive = reply({"active": True}), reply({"active": False})
    renewed = {"upstream_token": module.seal("new-access"), "issuer": issuer}
    nearly = upstream(upstream_expires_at=NOW + timedelta(seconds=30))
    admin = person(role="admin")
    return {
        "mcp scope, local": case("validate_session", {"scope": "mcp"}),
        "mcp scope, sso": case("validate_session", {"scope": "mcp"}, provider="oidc"),
        "managed device, sso": case("validate_session", {"scope": "mcp", "device_id": "d"}, provider="oidc"),
        "scope not a string": case("validate_session", {"scope": ["console"]}, provider="oidc"),
        "no jti": case("validate_session", {**base, "jti": ""}),
        "no subject": case("validate_session", {**base, "sub": ""}),
        "no session": case("validate_session", base),
        "suspended": case("validate_session", base, sess=person(status="suspended"), ended=upstream(),
                          introspect=active),
        "session over": case("validate_session", base, sess=person(expires_at=NOW), ended=upstream()),
        "suspended, no binding": case("validate_session", {**base, "identity_binding": None},
                                      sess=person(status="suspended")),
        "suspended, no tokens": case("validate_session", base, sess=person(status="suspended"), ended=None),
        "admin idle": case("validate_session", base, sess=person(role="admin", last_activity_at=NOW - timedelta(minutes=30)),
                           ended=upstream()),
        "employee idle": case("validate_session", base, sess=person(last_activity_at=NOW - timedelta(hours=3)),
                              row=upstream(), introspect=active),
        "no binding, local": case("validate_session", {**base, "identity_binding": None}, sess=person()),
        "no binding, sso": case("validate_session", {**base, "identity_binding": None}, provider="oidc", sess=person()),
        "binding gone": case("validate_session", base, sess=person(), row=None),
        "other issuer": case("validate_session", base, sess=person(), row=upstream(issuer="https://other.example")),
        "admin refresh refused": case("validate_session", base, sess=admin, row=nearly, ended=nearly, refresh=None),
        "admin refreshed": case("validate_session", base, sess=admin, row=nearly, refresh=renewed, introspect=active),
        "admin no expiry": case("validate_session", base, sess=admin, row=upstream(upstream_expires_at=None),
                                refresh=renewed, introspect=active),
        "admin fresh": case("validate_session", base, sess=admin, row=upstream(), introspect=active),
        "employee stale upstream": case("validate_session", base, sess=person(), row=nearly, introspect=active),
        "active": case("validate_session", base, sess=person(), row=upstream(), introspect=active),
        "revoked upstream": case("validate_session", base, sess=person(), row=upstream(), ended=upstream(),
                                 introspect=inactive),
        "active is not true": case("validate_session", base, sess=person(), row=upstream(), ended=upstream(),
                                   introspect=reply({"active": "true"})),
        "introspection status": case("validate_session", base, sess=person(), row=upstream(),
                                     introspect=reply({"active": True}, status=500)),
        "introspection down": case("validate_session", base, sess=person(), row=upstream(), introspect=down),
        "introspection json": case("validate_session", base, sess=person(), row=upstream(),
                                   introspect=reply(bad_json=True)),
        "metadata down": case("validate_session", base, sess=person(), row=upstream(), metadata=None),
        "no introspection endpoint": case("validate_session", base, sess=person(), row=upstream(),
                                          metadata={"revocation_endpoint": issuer + "/revoke"}),
        "end, both tokens": case("end_session", base, ended=upstream()),
        "end, access only": case("end_session", base, ended=upstream(upstream_refresh_token=None)),
        "end, no revocation endpoint": case("end_session", base, ended=upstream(),
                                            metadata={"introspection_endpoint": issuer + "/introspect"}),
        "end, revocation down": case("end_session", base, ended=upstream(), revoke=down),
        "end, metadata down": case("end_session", base, ended=upstream(), metadata=None),
        "end, row missing": case("end_session", base, ended=None),
        "end, no binding": case("end_session", {**base, "identity_binding": None}),
        "touch, mcp scope": case("touch_session", {**base, "scope": "mcp"}),
        "touch, scope list": case("touch_session", {**base, "scope": ["console"]}),
        "touch, lookalike scope": case("touch_session", {**base, "scope": "consolex"}),
        "touch, console scope": case("touch_session", {**base, "scope": "mcp console"}),
        "touch, expired": case("touch_session", base, changed=0),
    }


def session_expected():
    """Outcomes the pre-move validate/touch/end code produced for session_cases, pinned as the oracle."""
    ses = ("fetch", "SELECT cs.expires_at,cs.last_activity_at,cs.user_id,p.role,p.status FROM console_sessions cs "
           "JOIN principals p ON p.user_id=cs.user_id WHERE cs.jti=%s AND cs.user_id=%s", ("j", "u"))
    ups = ("fetch", "SELECT s.upstream_token,s.upstream_refresh_token,s.upstream_expires_at,b.issuer FROM oidc_sessions s "
           "JOIN oidc_bindings b ON b.id=s.binding_id WHERE s.jti=%s AND s.binding_id=%s AND s.expires_at>now()", ("j", "b"))
    tok = ("fetch", "SELECT s.upstream_token,s.upstream_refresh_token,b.issuer FROM oidc_sessions s "
           "JOIN oidc_bindings b ON b.id=s.binding_id WHERE s.jti=%s AND s.binding_id=%s", ("j", "b"))
    touch = ("sql", "UPDATE console_sessions SET last_activity_at=now() WHERE jti=%s AND user_id=%s AND expires_at>now() "
             "AND last_activity_at>now()-interval '30 minutes'", ("j", "u"))
    gone = [("sql", "DELETE FROM console_sessions WHERE jti=%s", ("j",)), ("sql", "DELETE FROM oidc_sessions WHERE jti=%s", ("j",))]
    pinned = ("client", {"timeout": 10, "trust_env": False, "follow_redirects": False, "transport": "pinned"})
    refresh = ("refresh", "j", "b")
    warn = ("warn", "SSO token revocation failed during logout")

    def post(path, **data):
        return ("post", "https://idp.example/" + path, ("cid", "client-secret"), data)

    def deny(status, detail):
        return ("HTTP", status, detail, None)
    refresh_token = post("revoke", token="refresh", token_type_hint="refresh_token")
    access_token = post("revoke", token="access", token_type_hint="access_token")
    ended = [tok, *gone, pinned, refresh_token, access_token]

    def introspect(token):
        return [pinned, post("introspect", token=token)]
    expired, sso_again = deny(401, "로그인 세션이 만료됐습니다."), deny(401, "SSO로 다시 로그인하세요.")
    unreachable = deny(503, "SSO 세션 상태를 확인하지 못해 접근을 보류했습니다.")
    unbound, revoked = deny(401, "SSO 연결이 해제되었거나 만료됐습니다."), deny(401, "조직 SSO 세션이 만료되거나 폐기됐습니다.")
    return {
        "mcp scope, local": (None, []), "mcp scope, sso": (sso_again, []), "managed device, sso": (None, []),
        "scope not a string": (sso_again, []), "no jti": (expired, []), "no subject": (expired, []),
        "no session": (expired, [ses]), "suspended": (expired, [ses, *ended]), "session over": (expired, [ses, *ended]),
        "suspended, no binding": (expired, [ses, *gone]), "suspended, no tokens": (expired, [ses, tok, *gone]),
        "admin idle": (deny(401, "30분 동안 활동이 없어 로그아웃됐습니다."), [ses, *ended]),
        "employee idle": (None, [ses, ups, *introspect("access")]),
        "no binding, local": (None, [ses]), "no binding, sso": (sso_again, [ses]),
        "binding gone": (unbound, [ses, ups]), "other issuer": (unbound, [ses, ups]),
        "admin refresh refused": (deny(401, "SSO 세션이 만료됐습니다. 다시 로그인하세요."), [ses, ups, refresh, *ended]),
        "admin refreshed": (None, [ses, ups, refresh, *introspect("new-access")]),
        "admin no expiry": (None, [ses, ups, refresh, *introspect("new-access")]),
        "admin fresh": (None, [ses, ups, *introspect("access")]),
        "employee stale upstream": (None, [ses, ups, *introspect("access")]),
        "active": (None, [ses, ups, *introspect("access")]),
        "revoked upstream": (revoked, [ses, ups, *introspect("access"), *ended]),
        "active is not true": (revoked, [ses, ups, *introspect("access"), *ended]),
        "introspection status": (unreachable, [ses, ups, *introspect("access")]),
        "introspection down": (unreachable, [ses, ups, *introspect("access")]),
        "introspection json": (unreachable, [ses, ups, *introspect("access")]),
        "metadata down": (unreachable, [ses, ups]), "no introspection endpoint": (unreachable, [ses, ups, pinned]),
        "end, both tokens": (None, ended), "end, access only": (None, [tok, *gone, pinned, access_token]),
        "end, no revocation endpoint": (None, [tok, *gone]),
        "end, revocation down": (None, [tok, *gone, pinned, refresh_token, warn]),
        "end, metadata down": (None, [tok, *gone, warn]), "end, row missing": (None, [tok, *gone]),
        "end, no binding": (None, gone),
        "touch, mcp scope": (None, []), "touch, scope list": (None, []), "touch, lookalike scope": (None, []),
        "touch, console scope": (None, [touch]), "touch, expired": (expired, [touch]),
    }


SESSION_EXPECTED = session_expected()


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_admin_boundary_and_limits(self):
        async def denied():
            raise HTTPException(403, "admin required")
        main.app.dependency_overrides[main.admin_caller] = denied
        for path in ("/api/audit/events", "/api/audit/export", "/api/audit/events/1"):
            self.assertEqual(self.client.get(path).status_code, 403)
        main.app.dependency_overrides[main.admin_caller] = lambda: {"roles": ["admin"]}
        self.assertEqual(self.client.get("/api/audit/events?limit=501").status_code, 422)
        self.assertEqual(self.client.get("/api/audit/events?since=2026-10-03T00:00:00").status_code, 422)

    def test_unknown_remains_unknown_and_filters_are_parameterized(self):
        where, params = audit.predicates(server="'; DELETE FROM decisions; --", execution="unknown")
        self.assertNotIn("DELETE", where)
        self.assertIn("upstream_attempted=true AND upstream_executed=false", where)
        self.assertEqual(params, ["'; DELETE FROM decisions; --"])
        for column in ("request_payload", "policy_input", "result,", "password", "token_sha256"):
            self.assertNotIn(column, audit.PROJECTION)
        with self.assertRaises(HTTPException):
            audit.predicates(since=datetime.now(), until=datetime.now(UTC))

    def test_pagination(self):
        # The second query is the invalid-row annotations (review.mark_invalid): none here.
        with patch.object(audit.db, "fetch_all", AsyncMock(side_effect=[[{"id": 3}, {"id": 2}, {"id": 1}], []])):
            page = asyncio.run(audit.events(limit=2))
        self.assertEqual([row["id"] for row in page["events"]], [3, 2])
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_before"], 2)


class OidcTest(unittest.TestCase):
    def test_callback_code_is_not_logged(self):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1", "GET", "/auth/oidc/callback?code=private-code&state=private-state", "1.1", 303), None)
        oidc.RedactCallbackQuery().filter(record)
        self.assertNotIn("private-code", record.getMessage())
        self.assertNotIn("private-state", record.getMessage())
        self.assertIn("/auth/oidc/callback", record.getMessage())

    def test_local_password_bypass_is_disabled(self):
        with patch.dict(os.environ, {"AUTH_PROVIDER": "oidc"}):
            with self.assertRaises(HTTPException) as denied:
                oidc.local_login_allowed()
            self.assertEqual(denied.exception.status_code, 403)
            for scope in ("console", "mcp", ""):
                with self.assertRaises(HTTPException):
                    asyncio.run(oidc.validate_session({"scope": scope}))
            asyncio.run(oidc.validate_session({"scope": "mcp", "device_id": "managed-test-device"}))

    def test_encrypted_upstream_credentials(self):
        with patch.dict(os.environ, {"OIDC_SESSION_SECRET": "test-only-"*8}):
            token = "synthetic-provider-credential"
            sealed = oidc.seal(token)
            self.assertNotIn(token.encode(), sealed)
            self.assertEqual(oidc.unseal(sealed), token)

    def test_client_wiring_has_one_owner_and_one_oauth_registry(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from app import agent_contract, identity_sessions, oidc_client
        self.assertIs(oidc.oauth, oidc_client.oauth)
        for name in oidc.__all__:
            owner = oidc_client if hasattr(oidc_client, name) else identity_sessions
            self.assertIs(getattr(oidc, name), getattr(owner, name), name)
        self.assertEqual(agent_contract.CONSOLE_SCOPE, oidc_client.CONSOLE_SCOPE)
        self.assertEqual(oidc.CONSOLE_SCOPE, "console")
        env = {"AUTH_PROVIDER": "oidc", "OIDC_ISSUER": "https://idp.example/realms/x/", "OIDC_CLIENT_ID": "cid",
               "OIDC_CLIENT_SECRET": "client-secret", "OIDC_REDIRECT_URI": "https://gw.example/auth/oidc/callback",
               "OIDC_SESSION_SECRET": "session-secret-" * 3, "OIDC_PROVIDER_LABEL": "SSO"}
        with patch.dict(os.environ, env), patch.dict(oidc.oauth._registry, clear=True),                 patch.dict(oidc.oauth._clients, clear=True):
            # Settings are read per call, never frozen at import.
            self.assertEqual(oidc.settings(), {"provider": "oidc", "issuer": "https://idp.example/realms/x",
                                               "client_id": "cid", "redirect_uri": env["OIDC_REDIRECT_URI"], "label": "SSO"})
            with patch.dict(os.environ, {"OIDC_CLIENT_ID": "other"}):
                self.assertEqual(oidc.settings()["client_id"], "other")
            first = oidc.client()
            self.assertIs(oidc_client.client(), first)
            self.assertIs(oidc.oauth.create_client("organization"), first)
            self.assertEqual(list(oidc_client.oauth._registry), ["organization"])
            self.assertIsInstance(first, oidc_client.PinnedOAuthApp)
            self.assertIs(first.client_cls, oidc_client.PinnedOAuthClient)
            self.assertEqual((first.client_id, first.client_secret), ("cid", "client-secret"))
            self.assertEqual(first._server_metadata_url,
                             "https://idp.example/realms/x/.well-known/openid-configuration")
            self.assertEqual(first.client_kwargs, {"scope": "openid profile", "code_challenge_method": "S256",
                                                   "timeout": 10, "trust_env": False})
            key = hashlib.sha256(env["OIDC_SESSION_SECRET"].encode()).digest()
            sealed = oidc.seal("token")
            self.assertEqual(AESGCM(key).decrypt(sealed[:12], sealed[12:], b"mcpgw-oidc-session"), b"token")
            self.assertEqual(oidc.unseal(oidc_client.seal("again")), "again")
            with patch.dict(os.environ, {"OIDC_DISCOVERY_URL": "http://keycloak:8080/realms/x/.well-known/openid-configuration"}),                     patch.dict(oidc.oauth._registry, clear=True), patch.dict(oidc.oauth._clients, clear=True):
                self.assertEqual(oidc.client()._server_metadata_url,
                                 "http://keycloak:8080/realms/x/.well-known/openid-configuration")
        with patch.dict(os.environ, {**env, "OIDC_CLIENT_SECRET": ""}), patch.dict(oidc.oauth._registry, clear=True),                 patch.dict(oidc.oauth._clients, clear=True):
            with self.assertRaises(HTTPException) as unconfigured:
                oidc.client()
            self.assertEqual(unconfigured.exception.status_code, 503)
            self.assertEqual(oidc.oauth._registry, {})

    def test_upstream_refresh_branches_hold_the_row_lock_and_keep_their_outcomes(self):
        from app import identity_sessions
        self.assertIs(oidc._refresh_upstream, identity_sessions._refresh_upstream)
        post = ("post", "https://idp.example/token", ("cid", "client-secret"),
                {"grant_type": "refresh_token", "refresh_token": "old-refresh"})
        unavailable = ("HTTP", 503, "인증 제공자에서 세션을 갱신하지 못해 접근을 보류했습니다.")
        expire = ("sql", "UPDATE console_sessions SET expires_at=now() WHERE jti=%s", ("j",))
        renew = "UPDATE oidc_sessions SET upstream_token=%s,upstream_refresh_token=%s,upstream_expires_at=%s WHERE jti=%s"
        renewed = {"upstream_token": "new-access", "issuer": "https://idp.example"}
        later = NOW + timedelta(hours=1)
        expected = {
            "fresh": ({"upstream_token": "old-access", "issuer": "https://idp.example"}, []),
            "rotated": (renewed, [post, ("sql", renew, ("new-access", "new-refresh", later, "j"))]),
            "kept refresh": (renewed, [post, ("sql", renew, ("new-access", "old-refresh", later, "j"))]),
            "invalid_grant": (None, [post, expire, ("sql", "UPDATE oidc_sessions SET upstream_refresh_token=NULL WHERE jti=%s", ("j",))]),
            "other 400": (unavailable, [post]), "no access token": (unavailable, [post]),
            "no lifetime": (unavailable, [post]), "idp down": (unavailable, [post]),
            "metadata down": (unavailable, []), "no refresh token": (None, [expire]),
            "missing": (None, []), "suspended": (None, []), "session over": (None, []), "idle": (None, []),
        }
        cases = refresh_cases(identity_sessions)
        self.assertEqual(cases.keys(), expected.keys())
        for name, (result, log) in cases.items():
            with self.subTest(name):
                if name != "metadata down":
                    lock, *rest = log
                    self.assertTrue(lock[1].endswith("WHERE s.jti=%s AND s.binding_id=%s FOR UPDATE OF s"), lock[1])
                    self.assertEqual(lock[2], ("j", "b"))
                    self.assertTrue(all(entry[1] == {"follow_redirects": False, "timeout": 10, "transport": "pinned",
                                                     "trust_env": False} for entry in rest if entry[0] == "client"))
                    log = [entry for entry in rest if entry[0] != "client"]
                self.assertEqual((result, log), expected[name])

    def test_session_validation_touch_and_end_keep_their_outcomes(self):
        from app import identity_sessions
        for name in ("validate_session", "touch_session", "end_session", "_refresh_upstream"):
            self.assertIs(getattr(oidc, name), getattr(identity_sessions, name), name)
        cases = session_cases(identity_sessions)
        self.assertEqual(cases.keys(), SESSION_EXPECTED.keys())
        for name, outcome in cases.items():
            with self.subTest(name):
                self.assertEqual(outcome, SESSION_EXPECTED[name])

    def test_callers_reach_session_checks_through_identity_sessions(self):
        from app import agent_contract, identity_sessions
        claims = {"jti": "j", "sub": "u", "scope": "console"}
        person = {"token": "t", "user_id": "u", "email": "e", "display_name": "n", "role": "employee", "department": "d",
                  "job_title": "j", "status": "active", "managed_required": False}
        calls = []

        async def end(given):
            calls.append(("end", given))

        async def validate(given):
            calls.append(("validate", given))
            if given.get("stop"):
                raise HTTPException(503, "stop")

        def run(row, **extra):
            calls.clear()
            with patch.object(agent_contract, "authenticate", return_value=({"user_id": "u"}, {**claims, **extra})), \
                    patch("app.disposal.blocked", return_value=False), \
                    patch.object(agent_contract.db, "fetch_one", AsyncMock(side_effect=[None, {**person, **row}])), \
                    patch.object(identity_sessions, "end_session", end), \
                    patch.object(identity_sessions, "validate_session", validate):
                try:
                    return asyncio.run(agent_contract.authenticated_user("Bearer x"))
                except HTTPException as exc:
                    return exc
        self.assertEqual(run({})["name"], "n")
        self.assertEqual(calls, [("validate", claims)])
        # An account that was switched off ends the session first, then answers 403 with the status header.
        denied = run({"status": "disabled"})
        self.assertEqual((denied.status_code, denied.headers), (403, {"X-Account-Status": "disabled"}))
        self.assertEqual(calls, [("end", claims)])
        # A failed session check propagates unchanged, and nothing after it ran.
        stopped = run({}, stop=True)
        self.assertEqual((stopped.status_code, stopped.detail), (503, "stop"))
        self.assertEqual(calls, [("validate", {**claims, "stop": True})])

    def test_handoff_cannot_be_reused_or_empty(self):
        from starlette.requests import Request
        request = Request({"type": "http", "headers": []})
        with patch.object(oidc.db, "fetch_one", AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as denied:
                asyncio.run(oidc.session(request))
            self.assertEqual(denied.exception.status_code, 401)


class SecretTest(unittest.TestCase):
    def test_real_scanner_checks_url_values_and_rejects_allow_comments(self):
        token = "npm_" + secrets.token_hex(18)
        for text in (f"https://external.example/?key={token}&page=1",
                     f"https://external.example/?key={token}#gitleaks:allow",
                     f"https://external.example/?key={token}%20%23%20gitleaks:allow"):
            self.assertIn("gitleaks:npm-access-token", asyncio.run(secret_scan.labels(text)))

    def test_sanitized_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder)/"report.json"
            report.write_text(json.dumps([{"RuleID": "github-pat", "File": folder+"/config.env",
                "StartLine": 2, "Secret": "synthetic-secret", "Match": "sensitive source snippet"}]))
            counts, findings = gitleaks_counts(report, Path(folder))
            self.assertEqual(counts["HIGH"], 1)
            self.assertEqual(findings[0]["target"], "config.env")
            self.assertNotIn("synthetic-secret", report.read_text())
            self.assertNotIn("sensitive source snippet", report.read_text())

    def test_missing_scanner_fails_closed(self):
        # The scanner is the in-process library now; a missing one must still block, never read as "clean".
        with patch.object(secret_scan, "LIBRARY", "/missing/libmcpgw_gitleaks.so"), patch.object(secret_scan, "_library", None):
            with self.assertRaises(secret_scan.InspectionUnavailable):
                asyncio.run(secret_scan.labels("ordinary outbound text"))


if __name__ == "__main__":
    unittest.main()
