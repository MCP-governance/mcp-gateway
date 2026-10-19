"""Signed write-ahead tombstones, stored outside PostgreSQL (D-123)."""
import asyncio
import base64
import hashlib
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DIRECTORY = Path(os.getenv("DISPOSAL_DIR", "/disposal"))
# "ledger" is a retention seal over the audit chain (D-141); retention.py reads it.
KINDS = {"token", "refresh", "server", "credential", "ledger"}
LOG = logging.getLogger(__name__)


class IntegrityError(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def key(private=False):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    name = "DISPOSAL_PRIVATE_KEY" if private else "DISPOSAL_PUBLIC_KEY"
    material = base64.urlsafe_b64decode(os.environ[name])
    return (Ed25519PrivateKey.from_private_bytes(material) if private
            else Ed25519PublicKey.from_public_bytes(material))


def signed(value):
    return {"payload": value, "signature": base64.b64encode(key(True).sign(encoded(value))).decode()}


def verified(envelope):
    try:
        key().verify(base64.b64decode(envelope["signature"], validate=True), encoded(envelope["payload"]))
        return envelope["payload"]
    except Exception as exc:
        raise IntegrityError("폐기 목록 서명 검증 실패") from exc


@contextmanager
def locked(directory):
    # All ingress/issuer processes share this lock; a torn append is never silently repaired.
    with (directory / "journal.lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read(directory=None):
    # shortcut: verify the whole journal per check; add a verified index after retention/load measurements.
    directory = directory or DIRECTORY
    try:
        raw = (directory / "journal.jsonl").read_bytes()
        head = verified(json.loads((directory / "head.json").read_bytes()))
        if head != {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}:
            raise IntegrityError("폐기 목록 길이 또는 해시 불일치")
        records, previous = [], "0" * 64
        for sequence, line in enumerate(raw.splitlines()):
            record = verified(json.loads(line))
            if record["sequence"] != sequence or record["previous"] != previous:
                raise IntegrityError("폐기 목록 연속성 손상")
            if sequence == 0:
                if record["kind"] != "genesis":
                    raise IntegrityError("폐기 목록 시작 기록 없음")
            elif record["kind"] not in KINDS or not isinstance(record["subject"], str) or not record["subject"]:
                raise IntegrityError("폐기 목록 대상 손상")
            records.append(record)
            previous = hashlib.sha256(line).hexdigest()
        if not records:
            raise IntegrityError("폐기 목록이 비어 있음")
        return records
    except IntegrityError:
        raise
    except Exception as exc:
        raise IntegrityError("폐기 목록 누락 또는 손상") from exc


def _append(directory, records, item):
    path = directory / "journal.jsonl"
    raw = path.read_bytes() if records else b""
    payload = {**item, "sequence": len(records), "previous": hashlib.sha256(raw.splitlines()[-1]).hexdigest()
               if raw else "0" * 64, "at": datetime.now(timezone.utc).isoformat()}
    with path.open("ab") as handle:
        handle.write(encoded(signed(payload)) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    raw = path.read_bytes()
    temporary = directory / "head.pending"
    with temporary.open("wb") as handle:
        handle.write(encoded(signed({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, directory / "head.json")
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def initialize(directory=None):
    directory = directory or DIRECTORY
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with locked(directory):
        if any((directory / name).exists() for name in ("journal.jsonl", "head.json", "head.pending")):
            raise IntegrityError("기존 폐기 목록은 초기화할 수 없음")
        _append(directory, [], {"kind": "genesis", "subject": "", "server_id": "", "detail": {}})


def remember(kind, subject, server_id="", detail=None, directory=None):
    directory = directory or DIRECTORY
    if kind not in KINDS or not isinstance(subject, str) or not subject:
        raise ValueError("폐기 대상 식별자가 필요합니다.")
    with locked(directory):
        records = read(directory)
        if any((r["kind"], r["subject"], r["server_id"]) == (kind, subject, server_id) for r in records):
            return
        _append(directory, records, {"kind": kind, "subject": subject, "server_id": server_id, "detail": detail or {}})


def blocked(jti=None, server_id=None, refresh=None):
    try:
        with locked(DIRECTORY):
            records = read()
        return any((jti is not None and r["kind"] == "token" and r["subject"] == str(jti))
                   or (refresh is not None and r["kind"] == "refresh" and r["subject"] == refresh)
                   or (server_id is not None and r["kind"] in {"server", "credential"}
                       and (r["server_id"] or r["subject"]) == server_id) for r in records)
    except (IntegrityError, OSError):
        return True


def remember_token(jti, expires_at):
    remember("token", str(jti), detail={"expires_at": expires_at.isoformat()})


async def capture_existing():
    from . import db
    with locked(DIRECTORY):
        records = read()
    known = {(r["kind"], r["subject"], r["server_id"]) for r in records}
    def save(kind, subject, server_id="", detail=None):
        identity = (kind, str(subject), server_id)
        if identity not in known:
            remember(kind, str(subject), server_id, detail)
            known.add(identity)
    verified(signed({"purpose": "disposal-key-check"}))
    for row in await db.fetch_all("SELECT jti,expires_at FROM agent_revoked_tokens"):
        save("token", row["jti"], detail={"expires_at": row["expires_at"].isoformat()})
    for row in await db.fetch_all("SELECT token_sha256 FROM oauth_refresh_tokens WHERE revoked_at IS NOT NULL OR rotated_at IS NOT NULL"):
        save("refresh", row["token_sha256"])
    for row in await db.fetch_all("SELECT id FROM mcp_servers WHERE lifecycle='RETIRED'"):
        save("server", row["id"], row["id"])
    for row in await db.fetch_all(
        """SELECT t.id,t.kind,c.server_id FROM revocation_targets t JOIN termination_cases c ON c.id=t.case_id
           WHERE t.status IN ('REVOKED','EXPIRED') AND t.kind IN ('server-held-credential','api-key','client-token','refresh-token')"""):
        save("credential", row["id"], row["server_id"], {"target_kind": row["kind"]})


async def reconcile():
    from psycopg.types.json import Jsonb
    from . import db
    with locked(DIRECTORY):
        records = read()
    restored = []
    async with db.transaction() as connection:
        for record in records[1:]:
            kind, subject, server = (record[k] for k in ("kind", "subject", "server_id"))
            if kind == "ledger":
                # Re-purging resurrected rows waits on the purge step (LEDGER_RETENTION.md); verify_audit_chain flags them.
                continue
            cursor = await connection.execute(
                """INSERT INTO disposal_blocks(kind,subject,server_id,detail) VALUES (%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING subject""", (kind, subject, server, Jsonb(record)))
            missing = await cursor.fetchone()
            if kind == "token":
                if datetime.fromisoformat(record["detail"]["expires_at"]) <= datetime.now(timezone.utc):
                    continue
                changed = await connection.execute(
                    """INSERT INTO agent_revoked_tokens(jti,expires_at) VALUES (%s,%s)
                       ON CONFLICT DO NOTHING""", (subject, record["detail"]["expires_at"]))
            elif kind == "refresh":
                changed = await connection.execute(
                    "UPDATE oauth_refresh_tokens SET revoked_at=now() WHERE token_sha256=%s AND revoked_at IS NULL", (subject,))
            else:
                changed = await connection.execute(
                    """UPDATE mcp_servers SET status='DISABLED', status_reason='폐기 상태 복원'
                       WHERE id=%s AND status<>'DISABLED'""", (server or subject,))
                if kind == "server":
                    lifecycle = await connection.execute(
                        "UPDATE mcp_servers SET lifecycle='RETIRED' WHERE id=%s AND lifecycle<>'RETIRED'", (server or subject,))
                    if lifecycle.rowcount:
                        missing = True
                    await connection.execute(
                        "UPDATE usage_relationships SET status='TERMINATED' WHERE server_id=%s AND status<>'TERMINATED'", (server or subject,))
                await connection.execute(
                    """UPDATE mcp_runtimes SET status='STOPPING',error='폐기 상태 복원',updated_at=now()
                       WHERE intake_id IN (SELECT id FROM mcp_intake_requests WHERE registered_server_id=%s)
                         AND status NOT IN ('STOPPED','FAILED','STOPPING')""", (server or subject,))
            if missing or changed.rowcount:
                restored.append({"kind": kind, "subject": subject, "server_id": server})
        if restored:
            await connection.execute(
                """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
                   VALUES ('disposal-reconciled','held','system','disposal','system','폐기 상태 복원',%s)""",
                (Jsonb({"restored": restored}),))
    return restored


async def watch(interval=60):
    from . import db
    from psycopg.types.json import Jsonb
    while True:
        try:
            try:
                await capture_existing()
                await reconcile()
                detail = {"ready": True}
            except Exception:
                LOG.exception("Disposal reconciliation failed; access remains blocked by the signed journal")
                detail = {"ready": False, "reason": "폐기 목록 확인 불가"}
                previous = await db.fetch_one("SELECT detail FROM worker_heartbeats WHERE worker='disposal'")
                if not previous or previous["detail"].get("ready") is not False:
                    await db.execute(
                        """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason)
                           VALUES ('disposal-integrity-failure','held','system','disposal','system','폐기 목록 확인 불가')""")
            await db.execute(
                """INSERT INTO worker_heartbeats(worker,role,seen_at,detail) VALUES ('disposal','disposal',now(),%s)
                   ON CONFLICT(worker) DO UPDATE SET seen_at=now(),detail=EXCLUDED.detail""", (Jsonb(detail),))
        except Exception:
            LOG.exception("Disposal status could not be persisted")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["init"]:
        raise SystemExit("usage: python -m app.disposal init")
    initialize()
