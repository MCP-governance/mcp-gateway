"""Optional LiteLLM 1.105 management-plane reconciliation (D-208).

Only explicit operator bindings cross this boundary. Transport tokens, upstream
credentials and raw management responses never enter the queue or event ledger.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import http.client
import json
import logging
import os
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

LOG = logging.getLogger(__name__)
STATES = {"pending": "동기화 대기", "failed": "동기화 실패", "verified": "동기화 완료"}
MAX_BODY = 2 * 1024 * 1024
# A: LiteLLM's MCP server points at MINT /mcp/<server>/ and forwards the employee's own MINT token (oauth_delegate
# passes the caller's per-server header through; LiteLLM stores nothing). B: LiteLLM calls the upstream directly and the
# guardrail asks MINT before each call. One setting chooses both the registered address and the auth mode (D-249).
ROUTES = {"mint": "oauth_delegate", "direct": None}
# Subject-level failures deny that key or team only; these make the registered server itself untrustworthy.
SERVER_LEVEL = {"server-readback-mismatch", "worker-server-readback-mismatch", "invalid-worker-server-response"}


class SyncError(Exception):
    pass


def enabled():
    return bool(os.getenv("MINT_LITELLM_SYNC_URL", "").strip())


def origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise SyncError("invalid-management-origin")
    return value.rstrip("/")


def route():
    value = os.getenv("MINT_LITELLM_ROUTE", "mint").strip() or "mint"
    if value not in ROUTES:
        raise SyncError("invalid-route")
    return value


def mint_endpoint(server_id):
    base = os.getenv("MINT_LITELLM_MINT_MCP_URL") or os.getenv("GATEWAY_PUBLIC_MCP_URL", "")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise SyncError("invalid-mint-mcp-url")
    return base.rstrip("/") + "/" + quote(server_id, safe="") + "/"


async def team_ceiling(api, config):
    """True when key grants cannot leak through a team MINT grants (D-249).

    LiteLLM 1.105 only uses require_key_mcp_access_defined to stop a key without its own MCP list from inheriting
    its team's servers, and its /config/field API refuses that field (a config-file setting). With no team bindings
    MINT grants keys explicitly and that inheritance never carries a MINT grant, so the switch is irrelevant. With
    team bindings the switch must be read back, or the operator must state it is set in the config file.
    """
    if not config["teams"]:
        return "no-team-grants"
    try:
        setting = await api.request("GET", "/config/field/info", params={"field_name": "require_key_mcp_access_defined"})
        if isinstance(setting, dict) and setting.get("field_value") is True:
            return "read-back"
    except SyncError:
        pass
    if os.getenv("MINT_LITELLM_KEY_ACCESS_CONFIRMED") == "1":
        return "operator-confirmed"
    raise SyncError("explicit-key-access-required")


def recheck_seconds():
    return max(30, int(os.getenv("MINT_LITELLM_SYNC_RECHECK_SECONDS", "300")))


def configuration():
    url = origin(os.environ["MINT_LITELLM_SYNC_URL"])
    if int(os.getenv("DB_POOL_MAX", "10")) < 2:
        raise SyncError("sync-requires-two-pool-connections")
    config = json.loads(Path(os.environ["MINT_LITELLM_SYNC_BINDINGS_FILE"]).read_text(encoding="utf-8"))
    users, teams = config.get("users", []), config.get("teams", [])
    if not isinstance(users, list) or not isinstance(teams, list):
        raise SyncError("invalid-bindings")
    ids, owners, hashes, team_ids = set(), set(), set(), set()
    for user in users:
        if (set(user) != {"mint_user_id", "litellm_user_id", "key_hashes"}
                or not all(isinstance(user[k], str) and user[k] for k in ("mint_user_id", "litellm_user_id"))
                or user["mint_user_id"] in ids or user["litellm_user_id"] in owners
                or not isinstance(user["key_hashes"], list)):
            raise SyncError("invalid-user-binding")
        ids.add(user["mint_user_id"])
        owners.add(user["litellm_user_id"])
        for key in user["key_hashes"]:
            if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) or key in hashes:
                raise SyncError("invalid-key-hash")
            hashes.add(key)
    for team in teams:
        if (set(team) != {"team_id", "mint_user_ids"} or not isinstance(team["team_id"], str)
                or not team["team_id"] or team["team_id"] in team_ids or not isinstance(team["mint_user_ids"], list)
                or not team["mint_user_ids"] or not set(team["mint_user_ids"]) <= ids):
            raise SyncError("invalid-team-binding")
        team_ids.add(team["team_id"])
    workers = config.get("workers", [])
    if not isinstance(workers, list) or not workers:
        raise SyncError("worker-inventory-required")
    return url, {"users": users, "teams": teams, "workers": [origin(w) for w in workers], "management_origin": url,
                 "route": route()}


def management_key():
    path = os.getenv("MINT_LITELLM_SYNC_KEY_FILE")
    value = (Path(path).read_text(encoding="utf-8").strip() if path else
             os.getenv(os.getenv("MINT_LITELLM_SYNC_KEY_ENV", "MINT_LITELLM_ADMIN_KEY"), ""))
    if not value or "\n" in value or "\r" in value:
        raise SyncError("management-key-unavailable")
    return value


class ManagementAPI:
    def __init__(self, url):
        self.url = origin(url)

    async def request(self, method, path, body=None, params=None, missing=False):
        # A fresh secret reference is resolved for every request, including retries after rotation.
        request = asyncio.create_task(asyncio.to_thread(self._request, method, path, body, params, missing, management_key()))
        try:
            return await asyncio.shield(request)
        except asyncio.CancelledError:
            # A blocking HTTP write must finish before the database writer lock is released.
            await request
            raise

    def _request(self, method, path, body, params, missing, key):
        parsed = urlsplit(self.url)
        # A private CA for the management origin only; other outbound TLS keeps the system store.
        context = ssl.create_default_context(cafile=os.getenv("MINT_LITELLM_SYNC_CA_FILE") or None)
        connection = (http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=8, context=context)
                      if parsed.scheme == "https" else
                      http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=8))
        try:
            target = path + ("?" + urlencode(params) if params else "")
            connection.request(method, target, body=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(MAX_BODY + 1)
            if response.status == 404 and missing:
                return None
            if not 200 <= response.status < 300:
                raise SyncError("http-" + str(response.status))
            if len(data) > MAX_BODY:
                raise SyncError("response-too-large")
            return json.loads(data) if data else None
        except (OSError, http.client.HTTPException, ValueError):
            # Exception text and HTTP bodies may contain credentials or query strings.
            raise SyncError("management-transport-or-json") from None
        finally:
            connection.close()


def merged_permissions(current, server_id, tools):
    result = copy.deepcopy(current or {})
    result.pop("object_permission_id", None)
    servers = result.get("mcp_servers") or []
    if not isinstance(servers, list) or any(s in {"*", "all-proxy-servers", "all-team-servers"} for s in servers):
        raise SyncError("unbounded-server-grant")
    result["mcp_servers"] = sorted(set(servers) | {server_id})
    permissions = result.get("mcp_tool_permissions") or {}
    if not isinstance(permissions, dict):
        raise SyncError("invalid-tool-permissions")
    # Keep an explicit empty tool grant on revocation: an absent field can inherit access.
    result["mcp_tool_permissions"] = {**permissions, server_id: sorted(tools)}
    return result


def subjects(config):
    users = {u["mint_user_id"]: u["litellm_user_id"] for u in config["users"]}
    return ([{"kind": "key", "id": key, "users": [u["mint_user_id"]], "owners": [u["litellm_user_id"]]}
             for u in config["users"] for key in u["key_hashes"]]
            + [{"kind": "team", "id": t["team_id"], "users": sorted(t["mint_user_ids"]),
                "owners": sorted(users[u] for u in t["mint_user_ids"])} for t in config["teams"]])


def check_subject(info, subject):
    if subject["kind"] == "key":
        if info.get("user_id") != subject["owners"][0]:
            raise SyncError("key-owner-mismatch")
    else:
        members = info.get("members_with_roles")
        if (not isinstance(members, list) or not members or any(not m.get("user_id") for m in members)
                or {m["user_id"] for m in members} != set(subject["owners"])):
            raise SyncError("team-membership-mismatch")


async def propagate(api, plan, config, observations):
    try:
        await _propagate(api, plan, config, observations)
    except Exception as exc:
        if plan["active"] and getattr(exc, "server_level", True):
            path = "/v1/mcp/server/" + quote(plan["remote_id"], safe="")
            try:
                current = await api.request("GET", path, missing=True)
                if isinstance(current, dict) and (current.get("mcp_info") or {}).get("mint_server_id") == plan["server_id"]:
                    await api.request("DELETE", path, missing=True)
                    remaining = await api.request("GET", path, missing=True)
                    observations.append({"kind": "failed-grant-cleanup", "present": remaining is not None})
            except Exception:
                observations.append({"kind": "failed-grant-cleanup", "unknown": True})
        raise


async def _propagate(api, plan, config, observations):
    sid = plan["remote_id"]
    path = "/v1/mcp/server/" + quote(sid, safe="")
    existing = await api.request("GET", path, missing=True)
    if existing is not None and (existing.get("mcp_info") or {}).get("mint_server_id") != plan["server_id"]:
        raise SyncError("server-ownership-conflict")
    active = plan["active"]
    existing_auth = (existing.get("auth_type") or "none") if existing else "none"
    # Direct routing must not inherit pass-through auth from A: it would hand the employee's MINT token to the upstream.
    expected_auth = plan.get("auth") or ("none" if existing_auth == "oauth_delegate" else existing_auth)
    expected_byok = bool(existing.get("is_byok")) if existing else False
    errors, subject_errors, failed_subjects, credential_targets = [], [], [], []
    session_users = set(plan.get("session_users", []))
    if active:
        observations.append({"kind": "team-ceiling", "basis": await team_ceiling(api, config)})
        if plan.get("unsupported"):
            raise SyncError("unsupported-or-credentialed-endpoint")
        payload = {"server_id": sid, "server_name": plan["server_id"], "alias": plan["server_id"], "url": plan["endpoint"],
                   "transport": "http", "auth_type": expected_auth, "allowed_tools": plan["tools"],
                   "allow_all_keys": False, "available_on_public_internet": False,
                   "mcp_info": {"mint_server_id": plan["server_id"]}}
        if existing and existing_auth not in {"none", "oauth_delegate"}:
            if existing.get("url") != plan["endpoint"]:
                raise SyncError("credential-origin-change-refused")
            # Existing OAuth/BYOK configuration belongs to LiteLLM; never downgrade it or copy its secrets.
            payload.pop("auth_type")
        await api.request("PUT" if existing else "POST", "/v1/mcp/server", payload)
    else:
        try:
            credential_targets = await api.request("GET", path + "/user-credentials")
            if not isinstance(credential_targets, list):
                raise SyncError("invalid-credential-inventory")
            for credential in credential_targets:
                session_users.add(credential["user_id"])
            plan["session_users"] = sorted(session_users)
        except (SyncError, KeyError, TypeError):
            errors.append("credential-owner-inventory-unavailable")
            if existing is not None:
                plan["inventory_unknown"] = True
        # Remove routing first, even when permission or credential cleanup will fail later.
        await api.request("DELETE", path, missing=True)
    current_subjects = subjects(config)
    current_by_id = {(s["kind"], s["id"]): s for s in current_subjects}
    all_subjects = {(s["kind"], s["id"]): s for s in plan.get("subjects", [])}
    all_subjects.update(current_by_id)
    for subject in all_subjects.values():
        kind, identifier = subject["kind"], subject["id"]
        session_users.update(subject["owners"])
        grant = (active and current_by_id.get((kind, identifier)) == subject
                 and set(subject["users"]) <= set(plan["allowed_users"]))
        tools = plan["tools"] if grant else []
        info_path = "/key/info" if kind == "key" else "/team/info"
        params = {"key" if kind == "key" else "team_id": identifier}
        try:
            data = await api.request("GET", info_path, params=params, missing=True)
            if data is None or (kind == "key" and data.get("info", {}).get("status") == "deleted"):
                if grant:
                    raise SyncError("bound-subject-unavailable")
                observations.append({"kind": kind, "subject_sha256": hashlib.sha256(identifier.encode()).hexdigest(), "absent": True})
                continue
            info = data["info" if kind == "key" else "team_info"]
            stale = current_by_id.get((kind, identifier)) != subject
            try:
                check_subject(info, subject)
            except SyncError as exc:
                if not stale:
                    raise
                # A mapping the operator has since removed or corrected: no longer ours to write, and no grant
                # can reach it through MINT (it is not in the current bindings). Seen in CI after a mapping fix.
                observations.append({"kind": kind, "subject_sha256": hashlib.sha256(identifier.encode()).hexdigest(),
                                     "stale": True, "skipped": str(exc)})
                continue
            permissions = merged_permissions(info.get("object_permission"), sid, tools)
            await api.request("POST", "/key/update" if kind == "key" else "/team/update",
                              {**params, "object_permission": permissions})
            reread = await api.request("GET", info_path, params=params)
            checked_info = reread["info" if kind == "key" else "team_info"]
            check_subject(checked_info, subject)
            actual = checked_info.get("object_permission") or {}
            observed = (actual.get("mcp_tool_permissions") or {}).get(sid)
            observations.append({"kind": kind, "subject_sha256": hashlib.sha256(identifier.encode()).hexdigest(),
                                 "tools": observed, "server_granted": sid in (actual.get("mcp_servers") or [])})
            if not active:
                # LiteLLM 1.105 drops a deleted server from a key's permission on write (CI); absent and empty both deny.
                if observed not in (None, []):
                    raise SyncError("permissions-readback-mismatch")
            elif actual != permissions and {k: v for k, v in actual.items() if k != "object_permission_id"} != permissions:
                raise SyncError("permissions-readback-mismatch")
        except (SyncError, KeyError, TypeError) as exc:
            # One wrong key or team stops only that subject; the others keep the server (D-249).
            subject_errors.append(str(exc) if isinstance(exc, SyncError) else "invalid-permissions-response")
            failed_subjects.append(hashlib.sha256(identifier.encode()).hexdigest())
    if failed_subjects:
        observations.append({"kind": "partial", "failed_subjects_sha256": sorted(failed_subjects)})
    if not active:
        # The admin inventory works after server deletion and never returns credential values.
        try:
            credentials = await api.request("GET", path + "/user-credentials")
            if not isinstance(credentials, list):
                raise SyncError("invalid-credential-inventory")
            for credential in credential_targets + credentials:
                owner = credential["user_id"]
                session_users.add(owner)
                plan.setdefault("session_users", []).append(owner)
                await api.request("DELETE", path + "/oauth-user-credential", params={"user_id": owner})
                await api.request("DELETE", path + "/user-credential", params={"user_id": owner})
            remaining = await api.request("GET", path + "/user-credentials")
            observations.append({"kind": "credentials", "remaining": len(remaining) if isinstance(remaining, list) else None})
            if remaining != []:
                raise SyncError("credentials-readback-mismatch")
        except (SyncError, KeyError, TypeError) as exc:
            errors.append(str(exc) if isinstance(exc, SyncError) else "invalid-credential-response")
        for worker in config["workers"]:
            try:
                worker_api = ManagementAPI(worker)
                before = await worker_api.request("GET", "/v1/mcp/sessions")
                for owner in sorted(session_users):
                    await worker_api.request("DELETE", "/v1/mcp/sessions", params={"user_id": owner})
                after = await worker_api.request("GET", "/v1/mcp/sessions")
                residual = [s for s in after["sessions"] if s.get("user_id") in session_users]
                observations.append({"kind": "sessions", "worker_pid": after["worker_pid"],
                                     "selectors_sha256": sorted(hashlib.sha256(u.encode()).hexdigest() for u in session_users),
                                     "worker_sha256": hashlib.sha256(worker.encode()).hexdigest(), "remaining": len(residual)})
                if before["worker_pid"] != after["worker_pid"] or residual:
                    raise SyncError("sessions-readback-mismatch")
            except (SyncError, KeyError, TypeError) as exc:
                errors.append(str(exc) if isinstance(exc, SyncError) else "invalid-session-response")
    for worker in config["workers"]:
        try:
            remote = await ManagementAPI(worker).request("GET", path, missing=True)
            matches = (isinstance(remote, dict) and remote.get("url") == plan["endpoint"]
                       and remote.get("allowed_tools") == plan["tools"]
                       and remote.get("approval_status") == "active"
                       and (remote.get("auth_type") or "none") == expected_auth
                       and bool(remote.get("is_byok")) == expected_byok
                       and (remote.get("mcp_info") or {}).get("mint_server_id") == plan["server_id"]
                       and remote.get("allow_all_keys") is False
                       and remote.get("available_on_public_internet") is False) if active else remote is None
            observations.append({"kind": "worker-server", "worker_sha256": hashlib.sha256(worker.encode()).hexdigest(),
                                 "present": remote is not None, "matches": matches})
            if not matches:
                errors.append("worker-server-readback-mismatch")
        except (SyncError, TypeError) as exc:
            errors.append(str(exc) if isinstance(exc, SyncError) else "invalid-worker-server-response")
    final = await api.request("GET", path, missing=True)
    if active:
        actual = {k: final.get(k) for k in payload} if isinstance(final, dict) else None
        # LiteLLM may augment mcp_info with its public-status flags.
        if actual:
            actual["mcp_info"] = {"mint_server_id": (final.get("mcp_info") or {}).get("mint_server_id")}
        observations.append({"kind": "server", "present": final is not None,
                             "tools": final.get("allowed_tools") if isinstance(final, dict) else None,
                             "matches": actual == payload})
        if (actual != payload or final.get("approval_status") != "active"
                or (final.get("auth_type") or "none") != expected_auth or bool(final.get("is_byok")) != expected_byok):
            errors.append("server-readback-mismatch")
    else:
        observations.append({"kind": "server", "present": final is not None})
        if final is not None:
            errors.append("server-delete-readback-mismatch")
    if active and SERVER_LEVEL & set(errors):
        await api.request("DELETE", path, missing=True)
        observations.append({"kind": "server-removed", "reason": "server-level-mismatch"})
    if plan.get("unsupported"):
        errors.append("unsupported-or-credentialed-endpoint")
    if plan.get("inventory_unknown"):
        errors.append("credential-owner-inventory-unknown")
    if errors or subject_errors:
        error = SyncError(",".join(sorted(set(errors + subject_errors))))
        error.server_level = bool(SERVER_LEVEL & set(errors))
        raise error


async def observe(api, plan, config):
    """Read-only check of a verified state. Returns mismatch codes and writes nothing (D-249)."""
    path = "/v1/mcp/server/" + quote(plan["remote_id"], safe="")
    found, problems = await api.request("GET", path, missing=True), []
    if plan["active"]:
        if (not isinstance(found, dict) or found.get("url") != plan["endpoint"]
                or found.get("allowed_tools") != plan["tools"] or found.get("approval_status") != "active"
                or (plan.get("auth") and (found.get("auth_type") or "none") != plan["auth"])
                or (found.get("mcp_info") or {}).get("mint_server_id") != plan["server_id"]
                or found.get("allow_all_keys") is not False):
            problems.append("server-drift")
    elif found is not None:
        problems.append("server-drift")
    for subject in subjects(config):
        kind, identifier = subject["kind"], subject["id"]
        params = {"key" if kind == "key" else "team_id": identifier}
        try:
            data = await api.request("GET", "/key/info" if kind == "key" else "/team/info", params=params, missing=True)
            info = data["info" if kind == "key" else "team_info"] if data else None
            if info is None:
                continue
            check_subject(info, subject)
            granted = plan["active"] and set(subject["users"]) <= set(plan["allowed_users"])
            tools = ((info.get("object_permission") or {}).get("mcp_tool_permissions") or {}).get(plan["remote_id"])
            if (tools or []) != (plan["tools"] if granted else []):
                problems.append(kind + "-drift")
        except SyncError as exc:
            problems.append(str(exc) if "mismatch" in str(exc) else kind + "-unreadable")
        except (KeyError, TypeError):
            problems.append(kind + "-unreadable")
    return sorted(set(problems))


async def initialize():
    if enabled():
        from . import db
        await db.execute((Path(__file__).with_name("litellm_sync_tables.sql")).read_text(encoding="utf-8"))


async def enqueue(server_id, connection=None):
    if not enabled():
        return
    from . import db
    query = """INSERT INTO litellm_sync_jobs(server_id) VALUES (%s)
               ON CONFLICT(server_id) DO UPDATE SET revision=litellm_sync_jobs.revision+1,
                 status='pending',retry_at=now(),updated_at=now()"""
    if connection is None:
        await db.execute(query, (server_id,))
    else:
        await connection.execute(query, (server_id,))


async def desired(server_id):
    from . import db, registry
    spec = registry.runtime()["servers"].get(server_id)
    row = await db.fetch_one("SELECT status,lifecycle FROM mcp_servers WHERE id=%s", (server_id,))
    result = {"server_id": server_id, "remote_id": "mint_" + hashlib.sha256(server_id.encode()).hexdigest()[:32],
              "active": False, "tools": [], "allowed_users": [], "endpoint": None}
    if not spec or not row or row["status"] != "READY" or row["lifecycle"] != "OPERATING":
        return result
    event = await db.fetch_one("""SELECT scope FROM approval_events WHERE kind='server-register'
                                 AND outcome='approved' AND target_kind='server' AND target_id=%s
                                 ORDER BY id DESC LIMIT 1""", (server_id,))
    if not event or event["scope"].get("intake") != spec.get("intake_id"):
        return result
    if datetime.fromisoformat(spec["valid_until"]) <= datetime.now(timezone.utc):
        return result
    tools = await db.fetch_all("""SELECT name FROM mcp_tools WHERE server_id=%s AND enabled
                                 AND approved_schema_hash IS NOT NULL AND scope_review IS NOT NULL ORDER BY name""", (server_id,))
    audience = spec.get("allowed_principals") or []
    people = await db.fetch_all("""SELECT user_id FROM principals WHERE (%s OR token=ANY(%s::text[]))
                                  AND status='active' AND user_id IS NOT NULL""",
                                (registry.ALL_PRINCIPALS in audience, audience))
    endpoint = spec["endpoint"]
    parsed = urlsplit(endpoint)
    mode = route()
    # Device-run servers have no network address; a credential in the URL may only stay inside MINT (route A).
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or (mode == "direct" and (parsed.username or parsed.password or parsed.query or parsed.fragment))):
        result["unsupported"] = True
        return result
    if mode == "mint":
        endpoint = mint_endpoint(server_id)
    result["auth"] = ROUTES[mode]
    result.update(active=bool(tools and people), tools=sorted(set(t["name"] for t in tools) & set(spec["tools"])),
                  allowed_users=sorted(set(p["user_id"] for p in people)), endpoint=endpoint)
    result["active"] = bool(result["active"] and result["tools"])
    return result


def fingerprint(plan, config):
    return hashlib.sha256(json.dumps([plan, config], sort_keys=True).encode()).hexdigest()


def retry_seconds(attempts):
    return min(300, 5 * 2 ** min(attempts, 6))


async def reconcile():
    if not enabled():
        return
    from . import db
    url, config = configuration()
    # A session lock serializes external writers without keeping row locks across HTTP.
    async with (await db.pool()).connection() as guard:
        acquired = False
        try:
            acquired = (await (await guard.execute(
                "SELECT pg_try_advisory_lock(hashtext('litellm-sync')) AS ok")).fetchone())["ok"]
            await guard.commit()
            if acquired:
                await _reconcile(url, config)
        finally:
            try:
                # Cancellation can arrive after acquisition but before fetchone returns.
                await guard.rollback()
                await guard.execute("SELECT pg_advisory_unlock(hashtext('litellm-sync'))")
                await guard.commit()
            except BaseException:
                # A pooled session must never be returned while still owning the writer lock.
                await guard.close()
                raise


async def _reconcile(url, config):
    from psycopg.types.json import Jsonb
    from . import db, registry, review
    known = await db.fetch_all("SELECT server_id FROM litellm_sync_jobs")
    ids = sorted(set(registry.runtime()["servers"]) | {r["server_id"] for r in known})
    for server_id in ids:
        row = await db.fetch_one("SELECT * FROM litellm_sync_jobs WHERE server_id=%s", (server_id,))
        if not row:
            await db.execute("INSERT INTO litellm_sync_jobs(server_id) VALUES (%s) ON CONFLICT DO NOTHING", (server_id,))
            row = await db.fetch_one("SELECT * FROM litellm_sync_jobs WHERE server_id=%s", (server_id,))
        observations, plan, digest = [], None, None
        try:
            plan = await desired(server_id)
            digest = fingerprint(plan, config)
            now = datetime.now(timezone.utc)
            if row["fingerprint"] == digest:
                if row["status"] == "verified":
                    if (now - row["updated_at"]).total_seconds() < recheck_seconds():
                        continue
                    # A verified state is re-read on a timer: LiteLLM-side edits are invisible from MINT otherwise.
                    problems = await observe(ManagementAPI(url), plan, config)
                    if not problems:
                        await db.execute("UPDATE litellm_sync_jobs SET updated_at=now() WHERE server_id=%s AND revision=%s",
                                         (server_id, row["revision"]))
                        continue
                    observations.append({"kind": "drift", "problems": problems})
                elif row["retry_at"] > now:
                    continue
            plan["subjects"] = row["subjects"]
            plan["session_users"] = row["session_users"]
            plan["inventory_unknown"] = row["inventory_unknown"]
            await propagate(ManagementAPI(url), plan, config, observations)
            latest = await desired(server_id)
            if fingerprint(latest, config) != digest:
                if not latest["active"]:
                    latest.update(subjects=plan["subjects"], session_users=plan["session_users"],
                                  inventory_unknown=plan["inventory_unknown"])
                    plan = latest
                    await propagate(ManagementAPI(url), plan, config, observations)
                else:
                    await ManagementAPI(url).request("DELETE", "/v1/mcp/server/" + quote(plan["remote_id"], safe=""), missing=True)
                    observations.append({"kind": "mint-state-changed", "action": "route-removal-requested"})
                raise SyncError("mint-state-changed-during-propagation")
            state, failure = "verified", None
        except Exception as exc:
            state = "failed"
            failure = str(exc) if isinstance(exc, SyncError) else type(exc).__name__
        async with db.transaction() as connection:
            current = await (await connection.execute(
                "SELECT * FROM litellm_sync_jobs WHERE server_id=%s FOR UPDATE", (server_id,))).fetchone()
            retained = {(s["kind"], s["id"]): s for s in current["subjects"] + row["subjects"]}
            retained.update({(s["kind"], s["id"]): s for s in subjects(config)})
            owners = sorted(set(current["session_users"]) | set(row["session_users"])
                            | set((plan or {}).get("session_users", [])) | {u["litellm_user_id"] for u in config["users"]})
            unknown = bool(current["inventory_unknown"] or row["inventory_unknown"] or (plan or {}).get("inventory_unknown"))
            superseded = current["revision"] != row["revision"]
            if superseded:
                state, failure = "failed", "queued-revision-changed"
            # The ledger's outcome vocabulary is fixed (approval_events CHECK); the sync state travels in scope.
            event_id = await review.record_event("litellm-sync", "recorded", "server", server_id, "system",
                scope={"evidence_class": "G5", "state": state, "revision": row["revision"], "attempt": current["attempts"] + 1,
                       "desired_sha256": digest, "observed_at": datetime.now(timezone.utc).isoformat(),
                       "desired": {k: (plan or {}).get(k) for k in ("remote_id", "active", "tools", "allowed_users")},
                       "observations": observations, "failure": failure,
                       "scope": "configured-litellm-management-state"}, connection=connection)
            if superseded:
                await connection.execute("""UPDATE litellm_sync_jobs SET subjects=%s,session_users=%s,inventory_unknown=%s,
                    attempts=attempts+1,event_id=%s,updated_at=now() WHERE server_id=%s""",
                    (Jsonb(list(retained.values())), Jsonb(owners), unknown, event_id, server_id))
                continue
            await connection.execute("""UPDATE litellm_sync_jobs SET status=%s,fingerprint=%s,attempts=attempts+1,
                retry_at=now()+make_interval(secs => %s),subjects=%s,session_users=%s,inventory_unknown=%s,event_id=%s,updated_at=now()
                WHERE server_id=%s AND revision=%s""",
                (state, digest, retry_seconds(current["attempts"]), Jsonb(list(retained.values())), Jsonb(owners), unknown,
                 event_id, server_id, row["revision"]))


async def statuses():
    if not enabled():
        return {}
    from . import db
    try:
        configuration()
        rows = await db.fetch_all("SELECT server_id,status,event_id FROM litellm_sync_jobs")
        return {"*": {"label": "동기화 대기", "event_id": None},
                **{r["server_id"]: {"label": STATES.get(r["status"], "동기화 실패"), "event_id": r["event_id"]} for r in rows}}
    except Exception:
        return {"*": {"label": "동기화 실패", "event_id": None}}


async def watch():
    if not enabled() or os.getenv("MINT_LITELLM_SYNC_WORKER") == "0":
        return
    await initialize()
    while True:
        try:
            await reconcile()
        except Exception as exc:
            LOG.error("LiteLLM synchronization unavailable: %s", type(exc).__name__)
        await asyncio.sleep(5)


async def check():
    """Pre-start diagnosis for the installer: settings, secret, explicit key access and every worker, no writes."""
    report = {"enabled": enabled()}
    if not enabled():
        return report
    try:
        url, config = configuration()
        report.update(route=config["route"], users=len(config["users"]), teams=len(config["teams"]),
                      workers=len(config["workers"]))
        if config["route"] == "mint":
            report["mint_mcp_url"] = mint_endpoint("example")[:-len("example/")]
        management_key()
        report["team_ceiling"] = await team_ceiling(ManagementAPI(url), config)
        for worker in config["workers"]:
            await ManagementAPI(worker).request("GET", "/v1/mcp/server")
        report["ok"] = True
    except (SyncError, OSError, KeyError, ValueError) as exc:
        report.update(ok=False, failure=str(exc) if isinstance(exc, SyncError) else type(exc).__name__)
    return report


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["check"]:
        raise SystemExit("usage: python -m app.litellm_sync check")
    result = asyncio.run(check())
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok", True) else 1)
