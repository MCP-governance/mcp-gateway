"""OCSF Base Events over HTTPS, with a PostgreSQL outbox independent of MCP dispatch."""
from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import logging
import os
import re
import ssl
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

LOG = logging.getLogger(__name__)
SOURCE_COLUMNS = {
    "decisions": "id,created_at,request_id,trace_id,user_token,server_id,tool_name,decision,policy_id,upstream_attempted,upstream_executed,prev_sha256,entry_sha256",
    "approval_events": "id,created_at,kind,outcome,target_kind,target_id,actor",
    "ops_alerts": "id,created_at,kind,origin,origin_id,synthetic",
}


def reference(value):
    return hashlib.sha256(str(value).encode()).hexdigest() if value is not None else None


def event(source, row):
    if source not in SOURCE_COLUMNS:
        raise ValueError("Unsupported SIEM source")
    timestamp = row["created_at"]
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        raise ValueError("SIEM timestamps require a timezone")
    data = {"source": source, "source_id": row["id"]}
    if source == "decisions":
        decision = row["decision"]
        if decision not in {"Allow", "Alert", "Restrict", "Approval", "Block"}:
            raise ValueError("Unsupported decision")
        data.update(decision=decision, policy_id=row["policy_id"] if re.fullmatch(r"[A-Z][A-Z0-9-]{0,99}", row["policy_id"]) else None,
                    upstream_attempted=bool(row["upstream_attempted"]), upstream_executed=bool(row["upstream_executed"]))
        for key in ("request_id", "trace_id", "user_token", "server_id", "tool_name"):
            data[key + "_ref"] = reference(row.get(key))
        for key in ("prev_sha256", "entry_sha256"):
            value = row.get(key) or ""
            data[key] = value if re.fullmatch(r"[0-9a-f]{64}", value) else None
        severity = 3 if decision in {"Block", "Alert"} else 1
    elif source == "approval_events":
        for key in ("kind", "outcome", "target_kind"):
            value = row.get(key) or ""
            data[key] = value if re.fullmatch(r"[a-z][a-z0-9-]{0,79}", value) else None
        data.update(target_ref=reference(row.get("target_id")), actor_ref=reference(row.get("actor")))
        severity = 1
    else:
        if row.get("synthetic") is not False:
            raise ValueError("Synthetic alerts cannot be forwarded")
        value = row.get("kind") or ""
        data.update(kind=value if re.fullmatch(r"[a-z][a-z0-9-]{0,79}", value) else None,
                    origin_ref=reference(row.get("origin_id")), synthetic=False)
        severity = 3
    # Base Event avoids inventing endpoints or claiming that every audit record is a detection.
    return {"category_uid": 0, "class_uid": 0, "activity_id": 99, "activity_name": "MINT Audit",
            "type_uid": 99, "severity_id": severity, "time": int(timestamp.timestamp() * 1000),
            "metadata": {"version": "1.4.0", "product": {"vendor_name": "MINT", "name": "MINT"},
                         "uid": f"mint:{source}:{row['id']}:{reference(timestamp.isoformat())}"},
            "unmapped": data}


def settings(environ=None):
    values = os.environ if environ is None else environ
    endpoint = values.get("SIEM_URL", "").strip()
    if not endpoint:
        return None
    try:
        parts = urlsplit(endpoint)
        parts.port
    except ValueError:
        raise ValueError("Invalid SIEM URL") from None
    loopback_http = (values.get("SIEM_ALLOW_LOOPBACK_HTTP") == "1" and parts.scheme == "http"
                     and parts.hostname in {"localhost", "127.0.0.1", "::1"})
    if (parts.scheme != "https" and not loopback_http) or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("SIEM requires an HTTPS URL without credentials, query or fragment")
    return {"url": endpoint, "token_file": values.get("SIEM_TOKEN_FILE", ""), "ca_file": values.get("SIEM_CA_FILE", "")}


def send(config, payload):
    parts = urlsplit(config["url"])
    headers = {"Content-Type": "application/json", "Idempotency-Key": payload["metadata"]["uid"]}
    # Read on every attempt so token/CA replacement needs no worker restart.
    if config["token_file"]:
        token = Path(config["token_file"]).read_text(encoding="utf-8").strip()
        if not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("Invalid SIEM credential file")
        headers["Authorization"] = "Bearer " + token
    # shortcut: 5s bounds idle socket I/O; add a total deadline before supporting untrusted receivers.
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=5,
                     context=ssl.create_default_context(cafile=config["ca_file"] or None))
    else:
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    try:
        connection.request("POST", parts.path or "/", body=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(), headers=headers)
        response = connection.getresponse()
        # No redirects, receiver bodies, response headers or credentials enter local logs.
        return response.status
    finally:
        connection.close()


async def deliver_one(config):
    from . import db
    async with db.transaction() as connection:
        row = await (await connection.execute(
            """SELECT * FROM siem_outbox WHERE delivered_at IS NULL AND next_attempt_at<=now()
               ORDER BY next_attempt_at,id LIMIT 1 FOR UPDATE SKIP LOCKED""")).fetchone()
        if not row:
            return False
        error = None
        try:
            columns = SOURCE_COLUMNS[row["source"]]
            source = await (await connection.execute(
                f"SELECT {columns} FROM {row['source']} WHERE id=%s", (row["source_id"],))).fetchone()
            payload = event(row["source"], source)
            status = await asyncio.to_thread(send, config, payload)
            if not 200 <= status < 300:
                error = f"HTTP-{status}"
        except Exception as exc:
            error = type(exc).__name__
        if error:
            delay = min(3600, 5 * 2 ** min(row["attempts"], 10))
            await connection.execute(
                """UPDATE siem_outbox SET attempts=attempts+1,last_error=%s,
                   next_attempt_at=now()+make_interval(secs=>%s) WHERE id=%s""", (error, delay, row["id"]))
        else:
            await connection.execute(
                "UPDATE siem_outbox SET attempts=attempts+1,last_error=NULL,delivered_at=now() WHERE id=%s", (row["id"],))
        return True


async def status():
    from . import db
    return await db.fetch_one(
        """SELECT count(*) FILTER (WHERE delivered_at IS NULL) AS pending,
           count(*) FILTER (WHERE delivered_at IS NULL AND attempts>0) AS retrying,
           min(created_at) FILTER (WHERE delivered_at IS NULL) AS oldest_pending,
           max(delivered_at) AS last_delivered FROM siem_outbox""")


async def watch():
    config = settings()
    if not config:
        raise ValueError("SIEM_URL is required for the SIEM worker")
    while True:
        try:
            # Bound each sweep; persistent rows, including permanent errors, are never discarded.
            for _ in range(50):
                if not await deliver_one(config):
                    break
        except Exception as exc:
            LOG.warning("SIEM worker unavailable: %s", type(exc).__name__)
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(watch())
