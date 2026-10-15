"""Shared setup for the termination/dispatch lab checks (run through termination_dispatch_lab.sh).

Each check gets its own empty PostgreSQL database with the product schema applied the way
core.bootstrap() applies it. Rows here are synthetic principals and servers."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
import traceback
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import db

APP = Path(__file__).resolve().parent.parent / "gateway" / "app"
if not APP.exists():
    APP = Path("/app/app")


class Checks:
    """Named checks with a JSON line each; any failure makes the run fail."""

    def __init__(self, title: str) -> None:
        self.title, self.results, self.started = title, [], time.monotonic()

    def ok(self, name: str, condition: bool, **detail) -> None:
        self.results.append({"check": name, "ok": bool(condition), **detail})
        print(json.dumps(self.results[-1], ensure_ascii=False, default=str), flush=True)

    async def case(self, name: str, coroutine) -> None:
        try:
            await coroutine
        except Exception as exc:
            self.results.append({"check": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            print(json.dumps(self.results[-1], ensure_ascii=False, default=str), flush=True)
            traceback.print_exc()

    def finish(self) -> int:
        failed = [r["check"] for r in self.results if not r["ok"]]
        print(json.dumps({"title": self.title, "checks": len(self.results), "failed": failed,
                          "seconds": round(time.monotonic() - self.started, 1)}, ensure_ascii=False), flush=True)
        return 1 if failed or not self.results else 0


async def apply_schema() -> None:
    await db.wait_until_ready()
    # The same files, in the same order, as core.bootstrap().
    for name in ("agent_tables.sql", "lifecycle_tables.sql", "v2_tables.sql", "oidc_tables.sql"):
        await db.execute((APP / name).read_text(encoding="utf-8"))


async def add_principal(token: str, role: str = "employee", status: str = "active", department: str = "플랫폼개발팀") -> None:
    await db.execute(
        """INSERT INTO principals(token, display_name, role, department, synthetic, user_id, email, status)
           VALUES (%s,%s,%s,%s,true,%s,%s,%s)
           ON CONFLICT (token) DO UPDATE SET status=EXCLUDED.status, role=EXCLUDED.role""",
        (token, token, role, department, token, f"{token}@bob.local", status))


async def add_server(server_id: str, endpoint: str = "http://mcp-lab:8000/mcp") -> None:
    await db.execute(
        """INSERT INTO mcp_servers(id, display_name, transport, endpoint, source_url, source_ref, supplier, status, status_reason)
           VALUES (%s,%s,'streamable-http',%s,'https://example.test','lab','lab','READY','lab')
           ON CONFLICT (id) DO NOTHING""", (server_id, server_id, endpoint))


async def reservation(request_id: str, token: str, server: str, tool: str = "t", fingerprint: str = "f",
                      ttl: int = 120, released: bool = False) -> None:
    await db.execute(
        """INSERT INTO call_reservations(request_id, user_token, server_id, tool_name, fingerprint, data_class, expires_at, released_at)
           VALUES (%s,%s,%s,%s,%s,'nonimportant', now() + make_interval(secs => %s), CASE WHEN %s THEN now() END)""",
        (request_id, token, server, tool, fingerprint, ttl, released))


def run(main) -> None:
    async def wrapped() -> int:
        try:
            return await main()
        finally:
            await db.close()
    sys.exit(asyncio.run(wrapped()))


def signing_keys() -> None:
    """A throwaway Ed25519 pair for this run, in the form the gateway reads from its environment."""
    key = Ed25519PrivateKey.generate()
    raw = lambda data: base64.urlsafe_b64encode(data).decode()  # noqa: E731
    os.environ["AGENT_JWT_PRIVATE_KEY"] = raw(key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
    os.environ["AGENT_JWT_PUBLIC_KEY"] = raw(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def mint(user_id: str, client_id: str = "lab", minutes: int = 10) -> tuple[str, dict]:
    """(authorization header, claims the ingress would verify) for a token this IdP signs."""
    from app.agent_contract import authenticate, issue_token
    token, _ = issue_token({"user_id": user_id}, minutes=minutes, client_id=client_id)
    header = "Bearer " + token
    return header, authenticate(header)[1]


def call_payload(token: str, server: str, tool: str, arguments: dict, claims: dict) -> dict:
    return {"server_id": server, "tool": tool, "arguments": arguments, "user_token": token,
            "client": {"agent": "lab"}, "transport_claims": claims}
