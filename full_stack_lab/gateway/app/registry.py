"""The MCP Registry: registry/catalog.toml + registry/contracts.lock.json -> database.

catalog.toml says what the organisation approved (servers, tools with r/w/x, data
classification, usage relationships). contracts.lock.json pins what those servers
looked like when they were approved (tool description/schema hashes, server version).
Both are reviewed in git; the database is the runtime copy the policy path reads.

Run as a module to (re)generate the lock from the live servers:

    python -m app.registry lock      # prints the lock JSON for every catalog server
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from . import db
from .contract import canonical_hash

REGISTRY_DIR = Path(os.getenv("REGISTRY_DIR", "/registry"))
CATALOG_PATH = REGISTRY_DIR / "catalog.toml"
LOCK_PATH = REGISTRY_DIR / "contracts.lock.json"

_cache: dict[str, Any] = {"mtime": None, "catalog": None}


def catalog() -> dict:
    """Parsed catalog.toml, reloaded when the file changes."""
    mtime = CATALOG_PATH.stat().st_mtime if CATALOG_PATH.exists() else None
    if _cache["catalog"] is None or _cache["mtime"] != mtime:
        _cache["catalog"] = tomllib.loads(CATALOG_PATH.read_text(encoding="utf-8")) if mtime else {"servers": {}}
        _cache["mtime"] = mtime
    return _cache["catalog"]


def catalog_version() -> str:
    raw = CATALOG_PATH.read_bytes() if CATALOG_PATH.exists() else b""
    return "catalog-" + hashlib.sha256(raw).hexdigest()[:12]


def servers() -> dict[str, dict]:
    return catalog().get("servers", {})


def server(server_id: str) -> dict | None:
    return servers().get(server_id)


def approved_tools(server_id: str) -> dict[str, str]:
    return dict((server(server_id) or {}).get("tools", {}))


def source_ref(spec: dict) -> str:
    """Supply-chain attribution key: one per package version, never shared by two servers."""
    return f"{spec['package']}@{spec['version']}"


def lock() -> dict:
    if not LOCK_PATH.exists():
        return {"servers": {}}
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def lock_digest() -> str:
    return hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest() if LOCK_PATH.exists() else ""


def usage_relationships() -> list[dict]:
    return list(catalog().get("usage_relationships", []))


async def sync() -> dict:
    """Bring mcp_servers / mcp_tools / usage_relationships in line with the files.

    Approved hashes are taken from the lock only when the lock itself changed since
    the last sync (or the row has none). A contract re-approved at runtime through
    the Console therefore survives restarts until someone commits a new lock - and
    then the committed lock wins, which is the reviewable state.
    """
    cat_servers = servers()
    pinned = lock().get("servers", {})
    digest = lock_digest()
    applied = await db.fetch_one("SELECT value FROM gateway_settings WHERE key='contracts_lock_digest'")
    apply_lock = bool(digest) and (not applied or applied["value"] != digest)
    stats = {"servers": 0, "tools": 0, "lock_applied": apply_lock}

    for server_id, spec in cat_servers.items():
        await db.execute(
            """INSERT INTO mcp_servers(id, display_name, transport, endpoint, source_url, source_ref, supplier,
                                       license, status, status_reason, package, version, deployment, downstream,
                                       exit_terms, server_held_credentials)
               VALUES (%s,%s,'streamable-http',%s,%s,%s,%s,%s,'PENDING','카탈로그 등록, 계약 확인 전',%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET display_name=EXCLUDED.display_name, endpoint=EXCLUDED.endpoint,
                 source_url=EXCLUDED.source_url, source_ref=EXCLUDED.source_ref, supplier=EXCLUDED.supplier,
                 license=EXCLUDED.license, package=EXCLUDED.package, version=EXCLUDED.version,
                 deployment=EXCLUDED.deployment, downstream=EXCLUDED.downstream,
                 exit_terms=EXCLUDED.exit_terms, server_held_credentials=EXCLUDED.server_held_credentials""",
            (server_id, spec["display_name"], spec["endpoint"], spec["source_url"], source_ref(spec),
             spec["supplier"], spec.get("license"), spec["package"], spec["version"],
             spec.get("deployment", "internal"), spec.get("downstream"),
             Jsonb(spec.get("exit_terms") or {}), Jsonb(spec.get("server_held_credentials") or [])),
        )
        stats["servers"] += 1
        approved = spec.get("tools", {})
        pinned_tools = (pinned.get(server_id) or {}).get("tools", {})
        pinned_version = (pinned.get(server_id) or {}).get("server_version")
        # Every advertised tool gets a row, approved or not: an unapproved tool that
        # appears or disappears is still a change to the contract.
        for name in sorted(set(approved) | set(pinned_tools)):
            action = approved.get(name, "x")
            enabled = name in approved
            await db.execute(
                """INSERT INTO mcp_tools(server_id, name, action, enabled)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (server_id, name) DO UPDATE SET action=EXCLUDED.action, enabled=EXCLUDED.enabled""",
                (server_id, name, action, enabled),
            )
            entry = pinned_tools.get(name)
            if entry and apply_lock:
                await db.execute(
                    """UPDATE mcp_tools SET approved_description_hash=%s, approved_schema_hash=%s,
                              approved_server_version=%s WHERE server_id=%s AND name=%s""",
                    (entry["description_sha256"], entry["schema_sha256"], pinned_version, server_id, name),
                )
            stats["tools"] += 1
        # Tools that neither the catalog nor the lock know any more.
        await db.execute(
            "DELETE FROM mcp_tools WHERE server_id=%s AND NOT (name = ANY(%s::text[]))",
            (server_id, sorted(set(approved) | set(pinned_tools))),
        )

    # Servers that left the catalog are switched off, not deleted: their audit rows
    # and termination cases still refer to them.
    await db.execute(
        """UPDATE mcp_servers SET status='DISABLED', status_reason='카탈로그에서 제거된 서버'
           WHERE NOT (id = ANY(%s::text[])) AND status <> 'DISABLED'""",
        (sorted(cat_servers),),
    )
    for rel in usage_relationships():
        await db.execute(
            """INSERT INTO usage_relationships(id, server_id, organization, purpose, provider, owner_department,
                                               allowed_resources)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET server_id=EXCLUDED.server_id, purpose=EXCLUDED.purpose,
                 provider=EXCLUDED.provider, owner_department=EXCLUDED.owner_department,
                 allowed_resources=EXCLUDED.allowed_resources""",
            (rel["id"], rel["server"], catalog().get("organization", {}).get("name", "BoB Corp"),
             rel["purpose"], rel["provider"], rel.get("owner_department"), Jsonb(rel.get("allowed_resources", []))),
        )
    if apply_lock:
        await db.execute(
            """INSERT INTO gateway_settings(key, value, updated_by) VALUES ('contracts_lock_digest',%s,'registry-sync')
               ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_by=EXCLUDED.updated_by, updated_at=now()""",
            (digest,),
        )
    return stats


def tool_hashes(tool: dict) -> dict:
    return {"description_sha256": canonical_hash(tool["description"]),
            "schema_sha256": canonical_hash(tool["input_schema"])}


async def build_lock() -> dict:
    """Discover every catalog server now and describe it as a lock document."""
    from . import upstream
    result: dict[str, Any] = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                              "catalog": catalog_version(), "servers": {}}
    for server_id, spec in sorted(servers().items()):
        discovered = await upstream.discover(spec["endpoint"])
        result["servers"][server_id] = {
            "package": source_ref(spec),
            "server_name": discovered["advertised_name"],
            "server_version": discovered["version"],
            "protocol_version": discovered["protocol_version"],
            "tools": {tool["name"]: tool_hashes(tool) for tool in sorted(discovered["tools"], key=lambda t: t["name"])},
        }
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["lock"]:
        print(json.dumps(asyncio.run(build_lock()), ensure_ascii=False, indent=1, sort_keys=True))
    else:
        print("usage: python -m app.registry lock", file=sys.stderr)
        sys.exit(2)
