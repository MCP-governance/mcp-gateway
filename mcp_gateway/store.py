"""SQLite record of relayed calls and the proxy's own client keys.

Recording is observability, not enforcement: a full queue or a failing disk drops
records (counted and shown in the console) instead of holding up traffic.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
import sqlite3
import threading
import time
from pathlib import Path

import anyio

log = logging.getLogger("mcp_gateway")

KEY_PREFIX = "mcpp_"
EVENT_TYPES = {
    "ts": "REAL", "server": "TEXT", "http_method": "TEXT", "status": "INTEGER",
    "outcome": "TEXT", "source": "TEXT", "reason": "TEXT",
    "principal": "TEXT", "key_id": "TEXT", "auth": "TEXT", "client_ip": "TEXT", "user_agent": "TEXT",
    "mcp_methods": "TEXT", "tool": "TEXT", "target": "TEXT", "arguments": "TEXT",
    "client_name": "TEXT", "client_version": "TEXT", "protocol_version": "TEXT", "session": "TEXT",
    "request_parse": "TEXT", "response_parse": "TEXT", "error_code": "INTEGER", "error_message": "TEXT",
    "server_methods": "TEXT", "sse_events": "INTEGER",
    "ttfb_ms": "REAL", "duration_ms": "REAL", "bytes_in": "INTEGER", "bytes_out": "INTEGER",
}
EVENT_COLUMNS = tuple(EVENT_TYPES)
EVENT_DDL = ",\n    ".join(f"{name} {kind}" for name, kind in EVENT_TYPES.items())
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {EVENT_DDL}
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS events_server_ts ON events(server, ts);
CREATE TABLE IF NOT EXISTS keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    servers TEXT NOT NULL,
    rate_per_minute INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    expires_at REAL,
    disabled_at REAL,
    last_used_at REAL
);
"""
OUTCOMES = ("ok", "tool_error", "rpc_error", "incomplete", "upstream_error", "proxy_error", "denied")


def key_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1)], 1)


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def _query(self, sql: str, args=()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    # ── events ──────────────────────────────────────────────────────────────
    def insert_events(self, rows: list[dict]) -> None:
        placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
        values = [tuple(row.get(name) for name in EVENT_COLUMNS) for row in rows]
        with self.lock:
            self.db.execute("BEGIN")
            try:
                self.db.executemany(f"INSERT INTO events ({', '.join(EVENT_COLUMNS)}) VALUES ({placeholders})", values)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def purge(self, before: float) -> int:
        with self.lock:
            return self.db.execute("DELETE FROM events WHERE ts < ?", (before,)).rowcount

    def events(self, *, server=None, outcome=None, principal=None, tool=None, search=None,
               after_id=None, before_id=None, limit=200) -> list[dict]:
        where, args = [], []
        for column, value in (("server", server), ("outcome", outcome), ("principal", principal), ("tool", tool)):
            if value:
                where.append(f"{column} = ?")
                args.append(value)
        if search:
            where.append("(" + " OR ".join(f"{c} LIKE ? ESCAPE '\\'" for c in
                         ("server", "principal", "tool", "target", "mcp_methods", "error_message", "reason", "client_name")) + ")")
            pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args += [pattern] * 8
        if after_id is not None:
            where.append("id > ?")
            args.append(after_id)
        if before_id is not None:
            where.append("id < ?")
            args.append(before_id)
        sql = "SELECT * FROM events" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY id DESC LIMIT ?"
        return self._query(sql, (*args, max(1, min(int(limit), 1000))))

    def event(self, event_id: int) -> dict | None:
        rows = self._query("SELECT * FROM events WHERE id = ?", (event_id,))
        return rows[0] if rows else None

    def summary(self, since: float, bucket_seconds: int = 3600) -> dict:
        window = (since,)
        totals = self._query("SELECT outcome, COUNT(*) AS n FROM events WHERE ts >= ? GROUP BY outcome", window)
        series = self._query(
            "SELECT CAST(ts / ? AS INTEGER) * ? AS bucket, outcome, COUNT(*) AS n FROM events "
            "WHERE ts >= ? GROUP BY bucket, outcome ORDER BY bucket", (bucket_seconds, bucket_seconds, since))
        servers = self._query(
            "SELECT server, outcome, COUNT(*) AS n FROM events WHERE ts >= ? GROUP BY server, outcome", window)
        tools = self._query(
            "SELECT server, tool, COUNT(*) AS n, SUM(outcome NOT IN ('ok')) AS failed FROM events "
            "WHERE ts >= ? AND tool IS NOT NULL GROUP BY server, tool ORDER BY n DESC LIMIT 20", window)
        methods = self._query(
            "SELECT mcp_methods AS method, COUNT(*) AS n FROM events WHERE ts >= ? AND mcp_methods IS NOT NULL "
            "AND mcp_methods != '' GROUP BY mcp_methods ORDER BY n DESC LIMIT 15", window)
        principals = self._query(
            "SELECT principal, outcome, COUNT(*) AS n FROM events WHERE ts >= ? GROUP BY principal, outcome", window)
        clients = self._query(
            "SELECT COALESCE(client_name, '') AS client, COUNT(*) AS n FROM events WHERE ts >= ? "
            "GROUP BY client ORDER BY n DESC LIMIT 12", window)
        flows = self._query(
            "SELECT principal, server, outcome, COUNT(*) AS n FROM events WHERE ts >= ? "
            "GROUP BY principal, server, outcome", window)
        # Latency of calls the upstream answered; proxy refusals would drag it toward zero.
        latency = self._query(
            "SELECT server, ttfb_ms FROM events WHERE ts >= ? AND source = 'upstream' AND ttfb_ms IS NOT NULL "
            "ORDER BY id DESC LIMIT 20000", window)
        by_server: dict[str, list[float]] = {}
        for row in latency:
            by_server.setdefault(row["server"], []).append(row["ttfb_ms"])
        every = [value for values in by_server.values() for value in values]
        return {
            "totals": {row["outcome"]: row["n"] for row in totals},
            "series": series, "servers": servers, "tools": tools, "methods": methods,
            "principals": principals, "clients": clients, "flows": flows,
            "latency": {
                "p50": percentile(every, 0.5), "p95": percentile(every, 0.95),
                "servers": {name: {"p50": percentile(v, 0.5), "p95": percentile(v, 0.95), "n": len(v)}
                            for name, v in by_server.items()},
            },
        }

    def stats(self) -> dict:
        with self.lock:
            pages = self.db.execute("PRAGMA page_count").fetchone()[0]
            size = self.db.execute("PRAGMA page_size").fetchone()[0]
            count = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"bytes": pages * size, "events": count}

    # ── keys ────────────────────────────────────────────────────────────────
    def create_key(self, name: str, servers: list[str], rate_per_minute: int = 0,
                   expires_at: float | None = None) -> tuple[dict, str]:
        secret = KEY_PREFIX + secrets.token_urlsafe(32)
        row = {
            "id": secrets.token_hex(6), "name": name, "prefix": secret[:12], "hash": key_hash(secret),
            "servers": json.dumps(servers), "rate_per_minute": rate_per_minute,
            "created_at": time.time(), "expires_at": expires_at,
        }
        with self.lock:
            self.db.execute(
                "INSERT INTO keys (id, name, prefix, hash, servers, rate_per_minute, created_at, expires_at) "
                "VALUES (:id, :name, :prefix, :hash, :servers, :rate_per_minute, :created_at, :expires_at)", row)
        return self.key(row["id"]), secret

    def _key_row(self, row: dict | None) -> dict | None:
        if row is None:
            return None
        row = dict(row)
        row["servers"] = json.loads(row["servers"])
        row.pop("hash", None)
        return row

    def key(self, key_id: str) -> dict | None:
        rows = self._query("SELECT * FROM keys WHERE id = ?", (key_id,))
        return self._key_row(rows[0] if rows else None)

    def key_by_secret(self, secret: str) -> dict | None:
        rows = self._query("SELECT * FROM keys WHERE hash = ?", (key_hash(secret),))
        return self._key_row(rows[0] if rows else None)

    def keys(self) -> list[dict]:
        return [self._key_row(row) for row in self._query("SELECT * FROM keys ORDER BY created_at DESC")]

    def update_key(self, key_id: str, **fields) -> dict | None:
        allowed = {"name", "servers", "rate_per_minute", "expires_at", "disabled_at"}
        changes = {name: (json.dumps(value) if name == "servers" else value)
                   for name, value in fields.items() if name in allowed}
        if changes:
            with self.lock:
                self.db.execute(f"UPDATE keys SET {', '.join(f'{name} = :{name}' for name in changes)} WHERE id = :id",
                                {**changes, "id": key_id})
        return self.key(key_id)

    def touch_keys(self, used: dict[str, float]) -> None:
        with self.lock:
            self.db.executemany("UPDATE keys SET last_used_at = ? WHERE id = ?",
                                [(ts, key_id) for key_id, ts in used.items()])

    def key_usage(self, since: float) -> dict[str, dict]:
        rows = self._query(
            "SELECT key_id, COUNT(*) AS n, SUM(outcome = 'denied') AS denied FROM events "
            "WHERE ts >= ? AND key_id IS NOT NULL GROUP BY key_id", (since,))
        return {row["key_id"]: {"calls": row["n"], "denied": row["denied"]} for row in rows}


class Recorder:
    """Batches records onto a worker thread so the relay path never waits on the disk."""

    def __init__(self, store: Store, retention_days: float, queue_size: int = 10000):
        self.store = store
        self.retention = retention_days * 86400
        self.send, self.receive = anyio.create_memory_object_stream(queue_size)
        self.dropped = 0
        self.written = 0
        self.used_keys: dict[str, float] = {}

    def record(self, row: dict) -> None:
        try:
            self.send.send_nowait(row)
        except (anyio.WouldBlock, anyio.BrokenResourceError, anyio.ClosedResourceError):
            self.dropped += 1
        if row.get("key_id") and row.get("auth") == "key":
            self.used_keys[row["key_id"]] = row["ts"]

    async def run(self) -> None:
        last_purge = 0.0
        async with self.receive:
            while True:
                try:
                    batch = [await self.receive.receive()]
                except anyio.EndOfStream:
                    return
                while len(batch) < 500:
                    try:
                        batch.append(self.receive.receive_nowait())
                    except (anyio.WouldBlock, anyio.EndOfStream):
                        break
                await self._write(batch)
                if time.time() - last_purge > 600:
                    last_purge = time.time()
                    await anyio.to_thread.run_sync(self.store.purge, time.time() - self.retention)

    async def _write(self, batch: list[dict]) -> None:
        used, self.used_keys = self.used_keys, {}
        try:
            await anyio.to_thread.run_sync(self.store.insert_events, batch)
            if used:
                await anyio.to_thread.run_sync(self.store.touch_keys, used)
            self.written += len(batch)
        except Exception as error:  # noqa: BLE001 - a broken disk must not stop the proxy
            self.dropped += len(batch)
            log.warning("could not write %d records: %s", len(batch), type(error).__name__)

    async def close(self) -> None:
        await self.send.aclose()
