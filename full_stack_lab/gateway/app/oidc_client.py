"""OIDC client wiring: settings, the single Authlib registry, the pinned transport and the session-token seal.

oidc and identity_sessions both build on this module, so the OAuth registry and the session
constants have exactly one owner and no import runs back toward oidc."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.starlette_client.apps import StarletteOAuth2App
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException

from .destination import pin_transport

# What a token was issued for. `mcp` tokens are what `bob-sso` keeps on the employee's
# PC for the harnesses, so they sit at rest in a file a local process can read; `console`
# tokens come from an interactive sign-in and last 30 minutes. They authenticate the same
# person, which is why the administrative APIs ask for the second: otherwise anything that
# could read the token file could also approve a high-risk call in that person's name.
# Missing scope never grants an administrative capability; old sessions sign in again.
CONSOLE_SCOPE = "console"
oauth = OAuth()
HANDOFF_COOKIE = "mcpgw_oidc_handoff"
ADMIN_IDLE = timedelta(minutes=30)
ADMIN_MAX = timedelta(hours=8)
TOKEN_LOGOUT_GRACE = timedelta(minutes=2)
REFRESH_EARLY_SECONDS = 60


def settings() -> dict:
    return {"provider": os.getenv("AUTH_PROVIDER", "local"),
            "issuer": os.getenv("OIDC_ISSUER", "").rstrip("/"),
            "client_id": os.getenv("OIDC_CLIENT_ID", "mcp-console"),
            "redirect_uri": os.getenv("OIDC_REDIRECT_URI", ""),
            "label": os.getenv("OIDC_PROVIDER_LABEL", "조직 SSO")}


def configured() -> bool:
    return all(os.getenv(k) for k in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
                                     "OIDC_REDIRECT_URI", "OIDC_SESSION_SECRET"))


def cipher() -> AESGCM:
    return AESGCM(hashlib.sha256(os.environ["OIDC_SESSION_SECRET"].encode()).digest())


def seal(value: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + cipher().encrypt(nonce, value.encode(), b"mcpgw-oidc-session")


def unseal(value: bytes) -> str:
    return cipher().decrypt(value[:12], value[12:], b"mcpgw-oidc-session").decode()


def http_transport():
    internal = []
    issuer = settings()["issuer"]
    # Keycloak advertises its configured discovery origin for dynamic backchannel endpoints.
    # Trust those configured origins only, never an arbitrary private host from metadata.
    for value in (issuer, os.getenv("OIDC_DISCOVERY_URL", issuer + "/.well-known/openid-configuration")):
        url = urlsplit(value)
        host = url.hostname or ""
        if (url.scheme in {"http", "https"} and not url.username and not url.password
                and (host in {"localhost", "127.0.0.1", "::1"}
                     or host.isascii() and host[:1].isalpha() and all(c.isalnum() or c == "-" for c in host))):
            internal.append((host, url.port or (443 if url.scheme == "https" else 80)))
    return pin_transport(httpx.AsyncHTTPTransport(trust_env=False), internal=internal)


class PinnedOAuthClient(AsyncOAuth2Client):
    def __init__(self, *args, **kwargs):
        # Authlib creates and closes a client per metadata/token/JWKS request; never share its pool.
        kwargs.update(transport=http_transport(), trust_env=False, follow_redirects=False)
        super().__init__(*args, **kwargs)


class PinnedOAuthApp(StarletteOAuth2App):
    client_cls = PinnedOAuthClient


def client():
    if not configured():
        raise HTTPException(503, "OIDC 설정이 완료되지 않았습니다.")
    if oauth.create_client("organization") is None:
        config = settings()
        oauth.register("organization", client_cls=PinnedOAuthApp,
                       client_id=config["client_id"], client_secret=os.environ["OIDC_CLIENT_SECRET"],
                       server_metadata_url=os.getenv("OIDC_DISCOVERY_URL", config["issuer"]+"/.well-known/openid-configuration"),
                       client_kwargs={"scope": "openid profile", "code_challenge_method": "S256", "timeout": 10,
                                      "trust_env": False})
    return oauth.create_client("organization")

