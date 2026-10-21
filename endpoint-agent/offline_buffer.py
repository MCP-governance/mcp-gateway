"""Small durable queue for sanitized endpoint OS events."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 10_000
MAX_AGE = timedelta(days=7)
SECRET_KEYS = {"token", "access_token", "authorization", "password", "secret", "credential",
               "raw", "raw_text", "raw_event", "event_xml", "message"}


class BufferFull(Exception):
    pass


def _now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("buffer clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def _uid(event: dict) -> str:
    digest = (event.get("provenance") or {}).get("raw_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("OS event has no raw SHA-256")
    try:
        bytes.fromhex(digest)
    except ValueError as exc:
        raise ValueError("OS event raw SHA-256 is invalid") from exc
    return digest.lower()


def _contains_secret(value) -> bool:
    if isinstance(value, dict):
        return any(str(key).casefold() in SECRET_KEYS or _contains_secret(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


class EventBuffer:
    """JSONL spool; source cursors may advance after append has been fsynced."""

    def __init__(self, path: Path, *, max_bytes: int = MAX_BYTES, max_events: int = MAX_EVENTS,
                 max_age: timedelta = MAX_AGE):
        self.path = Path(path)
        self.meta_path = self.path.with_suffix(self.path.suffix + ".meta")
        self.max_bytes, self.max_events, self.max_age = max_bytes, max_events, max_age
        if max_bytes < 1024 or max_events < 1 or max_age <= timedelta(0):
            raise ValueError("invalid offline buffer limits")
        if self.path.parent.exists():
            for stale in self.path.parent.glob(self.path.name + ".*.tmp"):
                stale.unlink(missing_ok=True)

    def _meta(self) -> dict:
        if not self.meta_path.exists():
            return {"clock_high_water": "1970-01-01T00:00:00+00:00", "dropped": 0}
        value = json.loads(self.meta_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or type(value.get("dropped", 0)) is not int:
            raise ValueError("offline buffer metadata is corrupt")
        return value

    def _save_meta(self, meta: dict) -> None:
        _atomic_write(self.meta_path, json.dumps(meta, sort_keys=True, separators=(",", ":")).encode())

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        data = self.path.read_bytes()
        rows, offset = [], 0
        chunks = data.splitlines(keepends=True)
        for index, line in enumerate(chunks):
            complete = line.endswith((b"\n", b"\r"))
            try:
                row = json.loads(line)
                if (not isinstance(row, dict) or not isinstance(row.get("event"), dict)
                        or row.get("uid") != _uid(row["event"])):
                    raise ValueError("invalid offline buffer row")
            except (ValueError, TypeError, json.JSONDecodeError):
                if index == len(chunks) - 1 and not complete:
                    _atomic_write(self.path, data[:offset])
                    break
                raise ValueError("offline buffer contains a corrupt complete row")
            rows.append(row)
            offset += len(line)
        return rows

    def _logical_now(self, meta: dict, now: datetime | None) -> datetime:
        current = _now(now)
        high = _now(datetime.fromisoformat(meta.get("clock_high_water", "1970-01-01T00:00:00+00:00")))
        logical = max(current, high)
        meta["clock_high_water"] = logical.isoformat()
        return logical

    @staticmethod
    def _record_drop(meta: dict, count: int, reason: str, fingerprint: str) -> None:
        if count <= 0:
            return
        if meta.get("drop_fingerprint") == fingerprint:
            return
        prior = meta.get("drop_reason")
        if not meta.get("dropped"):
            meta["drop_uid"] = uuid.uuid4().hex
            meta["dropped"] = 0
        meta["drop_reason"] = reason if not prior or prior == reason else "mixed"
        meta["dropped"] += count
        meta["drop_fingerprint"] = fingerprint

    def _write_rows(self, rows: list[dict]) -> None:
        data = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
                        for row in rows)
        if len(data) > self.max_bytes or len(rows) > self.max_events:
            raise BufferFull("offline buffer limit reached")
        _atomic_write(self.path, data)

    def pending(self, *, now: datetime | None = None) -> list[dict]:
        meta = self._meta()
        logical = self._logical_now(meta, now)
        rows = self._read()
        keep = []
        expired = []
        for row in rows:
            queued = _now(datetime.fromisoformat(row["queued_at"]))
            if logical - queued >= self.max_age:
                expired.append(row["uid"])
            else:
                keep.append(row)
        if expired:
            self._record_drop(meta, len(expired), "retention", hashlib.sha256("\n".join(sorted(expired)).encode()).hexdigest())
            self._write_rows(keep)
        self._save_meta(meta)
        return keep

    def enqueue(self, events: list[dict], *, now: datetime | None = None) -> int:
        meta = self._meta()
        logical = self._logical_now(meta, now)
        rows = self.pending(now=logical)
        meta = self._meta()
        known = {row["uid"] for row in rows}
        # Refused earlier and still unstored: the journal re-reads them until the cursor moves, so they are counted once.
        refused = set(meta.get("refused_uids", []))
        additions = []
        for event in events:
            if _contains_secret(event):
                raise ValueError("offline buffer refuses raw or secret fields")
            uid = _uid(event)
            if uid not in known:
                additions.append({"uid": uid, "queued_at": logical.isoformat(), "event": event})
                known.add(uid)
        candidate = rows + additions
        encoded_size = sum(len((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
                           for row in candidate)
        added = {row["uid"] for row in additions}
        if len(candidate) > self.max_events or encoded_size > self.max_bytes:
            fresh = sorted(added - refused)
            self._record_drop(meta, len(fresh), "capacity",
                              hashlib.sha256("\n".join(fresh).encode()).hexdigest())
            meta["refused_uids"] = sorted(refused | added)
            self._save_meta(meta)
            raise BufferFull("offline buffer limit reached; collection stopped")
        self._write_rows(candidate)
        meta["refused_uids"] = sorted(refused - added)
        self._save_meta(meta)
        return len(additions)

    def acknowledge(self, events: list[dict]) -> None:
        done = {_uid(event) for event in events}
        rows = self._read()
        self._write_rows([row for row in rows if row["uid"] not in done])

    def dropped_count(self) -> int:
        return self._meta().get("dropped", 0)

    def drop_report(self) -> dict | None:
        meta = self._meta()
        if not meta.get("dropped"):
            return None
        return {"buffer_event_uid": meta["drop_uid"], "dropped_count": meta["dropped"],
                "buffer_reason": meta["drop_reason"]}

    def clear_dropped(self) -> None:
        meta = self._meta()
        meta["dropped"] = 0
        meta.pop("drop_uid", None)
        meta.pop("drop_reason", None)
        self._save_meta(meta)


def flush(buffer: EventBuffer, send, *, batch_size: int = 100) -> int:
    """Send durable batches; keep the current and later batches on any failed response."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    sent = 0
    while rows := buffer.pending():
        events = [row["event"] for row in rows[:batch_size]]
        send(events)
        buffer.acknowledge(events)
        sent += len(events)
    return sent
