"""Operational containment and isolated checks against the loaded policy (D-121/122)."""
import asyncio
import copy
import json
import logging
import os
import uuid
from pathlib import Path

import httpx
from psycopg.types.json import Jsonb

from . import db, local_jobs, release, review
from .contract import POLICY_RESULT, canonical_hash
from .selective import restricted_tools

INTERVAL = int(os.getenv("OPS_RESPONSE_INTERVAL_SECONDS", "5"))
REPEAT = int(os.getenv("OPS_AUTO_STOP_REPEAT", "3"))
WINDOW = int(os.getenv("OPS_AUTO_STOP_WINDOW_SECONDS", "300"))
SOURCES = {s.strip() for s in os.getenv("OPS_AUTO_STOP_SOURCES", "drift,anomaly,volume").split(",") if s.strip()}
SERVERS = {s.strip() for s in os.getenv("OPS_AUTO_STOP_SERVERS", "*").split(",") if s.strip()}
if min(INTERVAL, REPEAT, WINDOW) <= 0 or SOURCES - {"drift", "anomaly", "volume"}:
    raise ValueError("Invalid operational response settings")
LOG = logging.getLogger(__name__)


def alert_kind(policy_id):
    if policy_id == "MCP-REGISTRY-001":
        return "unapproved-connection"
    if policy_id.startswith("MCP-SHADOW-"):
        return "unapproved-connection"
    if policy_id.startswith(("P-ANOMALY-", "P-VOLUME-")):
        return "call-burst"
    return None


async def emit_alert(kind, origin, origin_id, evidence, synthetic=False):
    return await db.fetch_one(
        """INSERT INTO ops_alerts(kind,origin,origin_id,evidence,synthetic) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING RETURNING id,synthetic""", (kind, origin, str(origin_id), Jsonb(evidence), synthetic))


async def catalog_alerts(server_id, findings, snapshot_id, synthetic=False):
    added = sorted({name for f in findings if f.get("type") == "tool-set-drift" for name in f.get("added", [])})
    if added:
        return await emit_alert("new-tool", "catalog", snapshot_id, {"server_id": server_id, "added": added}, synthetic)


async def observed_alerts():
    rows = await db.fetch_all(
        """SELECT d.id,d.server_id,d.policy_id,d.conflicts FROM decisions d
           WHERE d.created_at>now()-interval '1 day'
             AND (d.policy_id='MCP-REGISTRY-001' OR d.policy_id LIKE 'MCP-SHADOW-%%'
                  OR d.policy_id LIKE 'P-ANOMALY-%%' OR d.policy_id LIKE 'P-VOLUME-%%')
             AND NOT EXISTS (SELECT 1 FROM ops_alerts a WHERE a.origin='decision' AND a.origin_id=d.id::text AND NOT a.synthetic)
           ORDER BY d.id LIMIT 1000""")
    for row in rows:
        kind = alert_kind(row["policy_id"])
        if kind:
            await emit_alert(kind, "decision", row["id"], {"server_id": row["server_id"], "policy_id": row["policy_id"]})


def selected(server_id, source):
    return source in SOURCES and ("*" in SERVERS or server_id in SERVERS)


async def suspend(server_id, source, reason, evidence, batch=None):
    existing = await db.fetch_one(
        """SELECT s.status, EXISTS(SELECT 1 FROM ops_suspensions x
               WHERE x.server_id=s.id AND x.resumed_at IS NULL) AS suspended
             FROM mcp_servers s WHERE s.id=%s""", (server_id,))
    if not existing:
        raise LookupError("등록되지 않은 서버입니다.")
    if existing["suspended"] or existing["status"] in ("DISABLED", "BLOCKED_SUPPLY_CHAIN"):
        return False
    local_runner = globals().get("local_jobs")
    if local_runner is not None:
        await local_runner.quiesce(server_id=server_id)
    async with db.transaction() as connection:
        server = await (await connection.execute(
            "SELECT status FROM mcp_servers WHERE id=%s FOR UPDATE", (server_id,))).fetchone()
        if not server or server["status"] in ("DISABLED", "BLOCKED_SUPPLY_CHAIN"):
            return False
        row = await (await connection.execute(
            """INSERT INTO ops_suspensions(server_id,source,reason,evidence) VALUES (%s,%s,%s,%s)
               ON CONFLICT (server_id) WHERE resumed_at IS NULL DO NOTHING RETURNING id""",
            (server_id, source, reason, Jsonb(evidence)))).fetchone()
        if not row:
            return False
        await connection.execute(
            "UPDATE mcp_servers SET status='DISABLED',status_reason=%s WHERE id=%s", (reason, server_id))
        await connection.execute(
            """UPDATE mcp_runtimes SET status='STOPPING',error=%s,updated_at=now()
               WHERE intake_id IN (SELECT id FROM mcp_intake_requests WHERE registered_server_id=%s)
                 AND status NOT IN ('STOPPED','FAILED','STOPPING')""", (reason, server_id))
        scope = {"source": source, **evidence}
        if batch:
            scope["batch"] = batch
        await connection.execute(
            """INSERT INTO approval_events(kind,outcome,target_kind,target_id,actor,reason,scope)
               VALUES ('automatic-suspension','held','server',%s,'system',%s,%s)""",
            (server_id, reason, Jsonb(scope)))
        from . import litellm_sync
        await litellm_sync.enqueue(server_id, connection)
    return True


async def contain_drift(server_id, findings):
    if restricted_tools(findings) is None and selected(server_id, "drift"):
        await suspend(server_id, "drift", "미승인 계약 변경으로 자동 중지", {"findings": findings})


async def contain_repeated():
    # Synthetic events use other tables; a caller's client fields cannot opt out of containment.
    rows = await db.fetch_all(
        """WITH signals AS (
             SELECT d.id,d.server_id,d.created_at,p.policy_id FROM decisions d
             JOIN mcp_servers s ON s.id=d.server_id
             CROSS JOIN LATERAL (
               SELECT d.policy_id UNION SELECT d.would_policy_id
               UNION SELECT c->>'policy_id' FROM jsonb_array_elements(COALESCE(d.conflicts,'[]')) c
             ) p
             WHERE d.created_at > now()-make_interval(secs => %s)
               AND d.created_at > COALESCE((SELECT max(resumed_at) FROM ops_suspensions s
                                           WHERE s.server_id=d.server_id),'-infinity'::timestamptz)
           ) SELECT server_id,CASE WHEN policy_id LIKE 'P-ANOMALY-%%' THEN 'anomaly' ELSE 'volume' END AS source,
                    count(DISTINCT id) AS occurrences,max(id) AS last_decision_id
             FROM signals WHERE policy_id LIKE 'P-ANOMALY-%%' OR policy_id LIKE 'P-VOLUME-%%'
             GROUP BY server_id,source HAVING count(DISTINCT id)>=%s""", (WINDOW, REPEAT))
    for row in rows:
        if selected(row["server_id"], row["source"]):
            await suspend(row["server_id"], row["source"], "이상 호출 반복으로 자동 중지",
                          {"occurrences": row["occurrences"], "last_decision_id": row["last_decision_id"],
                           "window_seconds": WINDOW, "threshold": REPEAT})


async def resume(server_id, actor, note):
    from . import disposal
    if await asyncio.to_thread(disposal.blocked, server_id=server_id, raise_errors=True):
        raise ValueError("폐기된 서버는 새 도입 승인이 필요합니다.")
    async with db.transaction() as connection:
        server = await (await connection.execute(
            "SELECT lifecycle FROM mcp_servers WHERE id=%s FOR UPDATE", (server_id,))).fetchone()
        if not server or server["lifecycle"] != "OPERATING":
            raise ValueError("운영 중인 이용 관계만 복귀할 수 있습니다.")
        row = await (await connection.execute(
            """UPDATE ops_suspensions SET resumed_at=now(),resumed_by=%s,resume_note=%s
               WHERE server_id=%s AND resumed_at IS NULL RETURNING id""", (actor, note, server_id))).fetchone()
        if not row:
            raise ValueError("자동 중지 상태가 아닙니다.")
        await connection.execute(
            "UPDATE mcp_servers SET status='PENDING',status_reason='관리자 복귀 승인 · 계약 확인 대기' WHERE id=%s", (server_id,))
        await review.record_event("automatic-suspension-resume", "approved", "server", server_id, actor,
                                  reason=note, connection=connection)
        if local_jobs.is_local(server_id):
            await connection.execute(
                "DELETE FROM local_run_stops WHERE server_id=%s AND user_token='' AND device_id=''", (server_id,))
    return {"server_id": server_id, "status": "PENDING"}


def self_test_cases(base):
    cases = []
    for name, patch, decision, policy in (
        ("normal", {}, "Allow", "P-AUTHZ-ALLOW-001"),
        ("new-tool", {"contract": {"registered": False}}, "Block", "MCP-REGISTRY-001"),
        ("unapproved-connection", {"principal": {"shadow_endpoints": 1}}, "Alert", "MCP-SHADOW-001"),
        ("unapproved-listener", {"principal": {"shadow_listeners": 1}}, "Alert", "MCP-SHADOW-002"),
        ("call-burst", {"resource": {"data_class": "important"}, "context": {"recent_important": 10, "important_limit": 10}},
         "Approval", "P-VOLUME-001"),
        ("repeated-denials", {"context": {"recent_blocks": 5, "block_limit": 5}}, "Alert", "P-ANOMALY-001"),
    ):
        value = copy.deepcopy(base)
        for key, fields in patch.items():
            value[key] = {**value.get(key, {}), **fields}
        value["synthetic"] = True
        cases.append({"name": name, "input": value, "expected": {"decision": decision, "policy_id": policy}})
    return cases


async def self_test(opa_url):
    info = None
    results = []
    try:
        info = await release.policy_info(opa_url)
        digest = canonical_hash({k: info.get(k) for k in ("loaded_sha256", "loaded_data_sha256", "capabilities_sha256")})
    except Exception as exc:
        digest = canonical_hash({"policy_info_error": type(exc).__name__})
        results.append({"synthetic": True, "passed": False, "error": type(exc).__name__})
    previous = await db.fetch_one("SELECT passed FROM alert_self_tests WHERE policy_hash=%s ORDER BY id DESC LIMIT 1", (digest,))
    if previous and previous["passed"] and info and info["matches"]:
        return
    try:
        if not info or not info["matches"]:
            raise RuntimeError("배포 정책 일치 확인 실패")
        corpus = json.loads((Path(os.getenv("POLICY_PATH", "/policy/policy.rego")).parent / "replay_cases_pac15.json").read_text(encoding="utf-8"))
        corpus = corpus["pac15_replay"]
        baseline = {**corpus["base"], **next(c["patch"] for c in corpus["cases"] if c["id"] == "normal-public-read")}
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            for case in self_test_cases(baseline):
                response = await client.post(opa_url, json={"input": case["input"]})
                response.raise_for_status()
                actual = response.json().get("result")
                passed = (POLICY_RESULT.is_valid(actual)
                          and all(actual.get(k) == v for k, v in case["expected"].items()))
                alert = None
                if passed and case["name"] != "normal":
                    origin_id = str(uuid.uuid4())
                    if case["name"] == "new-tool":
                        alert = await catalog_alerts("synthetic", [{"type": "tool-set-drift", "added": ["synthetic-tool"]}], origin_id, True)
                    else:
                        kind = alert_kind(actual["policy_id"])
                        if kind:
                            alert = await emit_alert(kind, "self-test", origin_id, {"policy_hash": digest, "case": case["name"]}, True)
                    passed = bool(alert and alert["synthetic"])
                results.append({"case": case["name"], "synthetic": True, "expected": case["expected"],
                                "actual": actual, "alert_id": alert["id"] if alert else None, "passed": passed})
        after = await release.policy_info(opa_url)
        if info != after:
            raise RuntimeError("자체 시험 중 정책 변경")
    except Exception as exc:
        results.append({"synthetic": True, "passed": False, "error": type(exc).__name__})
    passed = bool(results) and all(r["passed"] for r in results)
    await db.execute("INSERT INTO alert_self_tests(policy_hash,passed,results) VALUES (%s,%s,%s)",
                     (digest, passed, Jsonb(results)))
    if not passed:
        await emit_alert("policy-self-test-failed", "self-test", digest,
                         {"policy_hash": digest, "results": results}, True)


async def tick(opa_url):
    # Keep cross-process exclusion through the work, without holding a database transaction across HTTP.
    async with (await db.pool()).connection() as guard:
        try:
            row = await (await guard.execute("SELECT pg_try_advisory_lock(721017121) AS acquired")).fetchone()
            await guard.commit()
            if not row["acquired"]:
                return
            from . import incidents
            try:
                await incidents.check_deadlines()
            except Exception:
                LOG.exception("Incident deadline check failed")
            await observed_alerts()
            await contain_repeated()
            await self_test(opa_url)
        finally:
            try:
                # Cancellation may arrive after acquisition but before its result was received.
                await guard.rollback()
                await guard.execute("SELECT pg_advisory_unlock(721017121)")
                await guard.commit()
            except BaseException:
                # A pooled connection must not carry the session lock into its next borrower.
                await guard.close()
                raise


async def watch(opa_url):
    while True:
        try:
            await tick(opa_url)
        except Exception:
            LOG.exception("Operational response check failed")
        await asyncio.sleep(INTERVAL)
