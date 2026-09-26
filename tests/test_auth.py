import time

import httpx
import pytest
from starlette.testclient import TestClient

from mcp_gateway.app import create_app
from mcp_gateway.auth import RateLimiter
from mcp_gateway.config import AuthSettings, Settings, StoreSettings, Upstream

LITELLM = "http://litellm.test:4000"


class Upstreams:
    """One MockTransport for the MCP upstreams and a fake LiteLLM, told apart by host."""

    def __init__(self, keys=None, litellm_error=None):
        self.mcp = []
        self.litellm = []
        self.keys = keys or {}
        self.litellm_error = litellm_error

    def __call__(self, request):
        if request.url.host == "litellm.test":
            self.litellm.append(request)
            if self.litellm_error:
                raise self.litellm_error
            info = self.keys.get(request.headers.get("authorization", "").removeprefix("Bearer "))
            if info is None:
                return httpx.Response(401, json={"error": {"message": "Authentication Error"}})
            return httpx.Response(200, json={"key": "hashed", "info": info})
        self.mcp.append(request)
        # A stream, not json=: the proxy relays raw bytes, which a pre-read body no longer has.
        return httpx.Response(200, stream=httpx.ByteStream(b'{"jsonrpc":"2.0","id":1,"result":{}}'),
                              headers={"content-type": "application/json"})


def app(tmp_path, upstreams, **auth):
    settings = Settings(
        {"files": Upstream("http://files:9000/mcp"), "mail": Upstream("http://mail:9000/mcp")},
        auth=AuthSettings(**auth), store=StoreSettings(path=str(tmp_path / "proxy.db")),
    )
    return TestClient(create_app(settings, transport=httpx.MockTransport(upstreams)))


def test_proxy_keys_gate_servers_and_never_reach_upstream(tmp_path):
    upstreams = Upstreams()
    with app(tmp_path, upstreams, providers=("keys",)) as client:
        runtime = client.app.state.runtime
        _, secret = runtime.store.create_key("ysg", ["files"])
        missing = client.post("/mcp/files", content=b"{}")
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == 'Bearer realm="mcp-proxy"'
        assert client.post("/mcp/files", headers={"Authorization": "Bearer mcpp_wrong"}).status_code == 401
        allowed = client.post("/mcp/files", content=b"{}", headers={"Authorization": f"Bearer {secret}"})
        assert allowed.status_code == 200
        assert client.post("/mcp/mail", content=b"{}", headers={"Authorization": f"Bearer {secret}"}).status_code == 403
    assert len(upstreams.mcp) == 1
    assert "authorization" not in upstreams.mcp[0].headers


def test_disabled_and_expired_keys_stop_working_at_once(tmp_path):
    upstreams = Upstreams()
    with app(tmp_path, upstreams, providers=("keys",)) as client:
        runtime = client.app.state.runtime
        row, secret = runtime.store.create_key("jwj", ["*"])
        headers = {"Authorization": f"Bearer {secret}"}
        assert client.post("/mcp/mail", headers=headers).status_code == 200
        runtime.store.update_key(row["id"], disabled_at=time.time())
        # The console calls forget() after a change; a revoked key must not ride the cache.
        runtime.auth.forget()
        assert client.post("/mcp/mail", headers=headers).status_code == 401
        runtime.store.update_key(row["id"], disabled_at=None, expires_at=time.time() - 1)
        runtime.auth.forget()
        assert client.post("/mcp/mail", headers=headers).status_code == 401


def test_rate_limit_answers_429_with_retry_after(tmp_path):
    upstreams = Upstreams()
    with app(tmp_path, upstreams, providers=("keys",)) as client:
        _, secret = client.app.state.runtime.store.create_key("pse", ["files"], rate_per_minute=2)
        headers = {"Authorization": f"Bearer {secret}"}
        assert [client.post("/mcp/files", headers=headers).status_code for _ in range(3)] == [200, 200, 429]
        limited = client.post("/mcp/files", headers=headers)
        assert int(limited.headers["retry-after"]) >= 1
    assert len(upstreams.mcp) == 2


def test_litellm_virtual_key_grants_servers_from_its_metadata(tmp_path):
    upstreams = Upstreams(keys={"sk-ysg": {"key_alias": "ysg-laptop", "metadata": {"mcp_proxy_servers": ["files"]}}})
    with app(tmp_path, upstreams, providers=("litellm",), litellm_url=LITELLM) as client:
        headers = {"x-litellm-api-key": "Bearer sk-ysg"}
        assert client.post("/mcp/files", content=b"{}", headers=headers).status_code == 200
        assert client.post("/mcp/files", content=b"{}", headers=headers).status_code == 200
        assert client.post("/mcp/mail", content=b"{}", headers=headers).status_code == 403
        assert client.post("/mcp/files", headers={"Authorization": "Bearer sk-unknown"}).status_code == 401
    # Three requests with one key: LiteLLM was asked once (cache), the unknown key once more.
    assert len(upstreams.litellm) == 2
    assert upstreams.litellm[0].url.path == "/key/info"
    assert len(upstreams.mcp) == 2
    assert all("x-litellm-api-key" not in r.headers and "authorization" not in r.headers for r in upstreams.mcp)


def test_litellm_key_without_metadata_gets_the_configured_default(tmp_path):
    upstreams = Upstreams(keys={"sk-nkk": {"user_id": "nkk"}})
    with app(tmp_path, upstreams, providers=("litellm",), litellm_url=LITELLM, litellm_default_servers=("mail",)) as client:
        headers = {"Authorization": "Bearer sk-nkk"}
        assert client.post("/mcp/mail", headers=headers).status_code == 200
        assert client.post("/mcp/files", headers=headers).status_code == 403


def test_litellm_outage_fails_closed(tmp_path):
    upstreams = Upstreams(litellm_error=httpx.ConnectError("refused"))
    with app(tmp_path, upstreams, providers=("litellm",), litellm_url=LITELLM, litellm_default_servers=("*",)) as client:
        response = client.post("/mcp/files", headers={"Authorization": "Bearer sk-any"})
    assert response.status_code == 503
    assert upstreams.mcp == []


def test_blocked_litellm_key_is_refused(tmp_path):
    upstreams = Upstreams(keys={"sk-old": {"blocked": True, "metadata": {"mcp_proxy_servers": ["*"]}}})
    with app(tmp_path, upstreams, providers=("litellm",), litellm_url=LITELLM) as client:
        assert client.post("/mcp/files", headers={"Authorization": "Bearer sk-old"}).status_code == 401


def test_litellm_key_is_stripped_even_when_auth_is_off():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b""))

    settings = Settings({"files": Upstream("http://files:9000/mcp")})
    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        client.post("/mcp/files", headers={"x-litellm-api-key": "sk-leak", "Authorization": "Bearer user"})
    assert "x-litellm-api-key" not in calls[0].headers
    assert "authorization" not in calls[0].headers


def test_rate_limiter_refills_evenly():
    limiter = RateLimiter()
    assert limiter.retry_after("k", 60, now=0) is None
    for _ in range(59):
        limiter.retry_after("k", 60, now=0)
    assert limiter.retry_after("k", 60, now=0) == pytest.approx(1.0)
    assert limiter.retry_after("k", 60, now=1.0) is None
    assert limiter.retry_after("k", 0, now=0) is None
