"""시험 공용 도구: 게이트웨이 토큰 발급(제품 /oauth/token·/auth/mock-login), LiteLLM 호출, 원시 로그 기록.

LiteLLM 이미지(v1.105.0)의 venv(httpx, mcp 2.2.0)에서 호스트 망으로 실행한다. 비밀(토큰·키)은 기록하지 않고
토큰은 jti와 끝 8자, 키는 별칭만 남긴다.
"""
import asyncio, base64, json, os, time
from datetime import datetime, timezone
import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

GW = os.environ.get("GW", "https://100.83.175.111")
CA = os.environ.get("GW_CA", "/secrets/gateway-ca.pem")
LLM = os.environ.get("LLM", "http://127.0.0.1:4010")
MASTER = lambda: open("/secrets/litellm_master_key").read().strip()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def claims(tok):
    p = tok.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


async def gw_token(user, password, client_id):
    """제품 로그인 경로(OAuth password grant, 하네스용 bob-sso와 같은 경로). 비관리 계정만 발급된다."""
    async with httpx.AsyncClient(verify=CA, timeout=20) as c:
        r = await c.post(GW + "/oauth/token", data={"grant_type": "password", "client_id": client_id, "username": user, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"token {user}: {r.status_code}")
    return r.json()["access_token"]


async def console_token(user, password):
    """Console 로그인 API(콘솔이 쓰는 것과 같음). scope=console 토큰이라 MCP에는 쓸 수 없다."""
    async with httpx.AsyncClient(verify=CA, timeout=20) as c:
        r = await c.post(GW + "/auth/mock-login", json={"email": user, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"console login {user}: {r.status_code}")
    return r.json()["access_token"]


async def revoke(tok):
    async with httpx.AsyncClient(verify=CA, timeout=20) as c:
        r = await c.post(GW + "/oauth/revoke", data={"token": tok})
    return r.status_code


def tokinfo(tok):
    c = claims(tok)
    return {"gw_sub": c.get("sub"), "gw_client_id": c.get("client_id"), "gw_scope": c.get("scope"), "token_jti": c.get("jti"), "token_tail": tok[-8:]}


def _meta(res):
    for name in ("meta", "_meta", "field_meta"):
        v = getattr(res, name, None)
        if v:
            return v
    return None


def _http(headers, timeout, url):
    return httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(timeout),
                              verify=(CA if url.startswith("https") else True))


def _err(e):
    subs = getattr(e, "exceptions", None)
    return (" | ".join(repr(x) for x in subs) if subs else repr(e))[:300]


async def mcp_op(url, headers, op, tool=None, args=None, timeout=60):
    """MCP SDK로 initialize 후 list_tools 또는 call_tool 한 번. 결과를 분류해 돌려준다."""
    t0 = time.monotonic(); out = {"t_request": now(), "url": url, "op": op, "tool": tool}
    try:
        async with streamable_http_client(url, http_client=_http(headers, timeout, url)) as (r, w, *_):
            async with ClientSession(r, w) as s:
                await asyncio.wait_for(s.initialize(), timeout)
                if op == "list":
                    res = await asyncio.wait_for(s.list_tools(), timeout)
                    out.update(transport="ok", tools=[t.name for t in res.tools], meta=_meta(res))
                else:
                    res = await asyncio.wait_for(s.call_tool(tool, args or {}), timeout)
                    text = " ".join(getattr(c, "text", "") or "" for c in (res.content or []))
                    err = getattr(res, "is_error", None)
                    if err is None:
                        err = getattr(res, "isError", None)
                    out.update(transport="ok", is_error=bool(err), text=text[:300])
    except BaseException as e:
        out.update(transport="error", error=_err(e))
    out["ms"] = int((time.monotonic() - t0) * 1000)
    return out


async def litellm_admin(method, path, **kw):
    async with httpx.AsyncClient(timeout=60) as c:
        return await c.request(method, LLM + path, headers={"Authorization": "Bearer " + MASTER()}, **kw)


async def new_key(user_id, alias, **extra):
    body = {"user_id": user_id, "key_alias": alias, **extra}
    r = await litellm_admin("POST", "/key/generate", json=body)
    if r.status_code != 200:
        raise RuntimeError(f"key/generate {alias}: {r.status_code} {r.text[:200]}")
    return r.json()["key"]


async def delete_keys_by_alias_prefix(prefix):
    r = await litellm_admin("GET", "/key/list", params={"return_full_object": "true", "size": 200})
    keys = [k for k in (r.json().get("keys") or []) if isinstance(k, dict) and str(k.get("key_alias") or "").startswith(prefix)]
    if keys:
        await litellm_admin("POST", "/key/delete", json={"keys": [k["token"] for k in keys]})
    return len(keys)


def wilson(k, n, z=1.959964):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))
