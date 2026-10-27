"""PAC-15 facts from transport identity, reviewed capabilities and reserved state.

The execution agent is this Gateway broker, not an attested Claude/Codex binary.
Parameter bindings are materialized only after the reviewed schema and resource
scope pass; observing an argument never adds it to an approval.
"""
from __future__ import annotations

import json
import posixpath
import re
import time
from datetime import datetime

from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from . import db, registry, residency
from .agent_contract import AUDIENCE, ISSUER
from .contract import canonical_hash

VERSION = "pac15-v1"
BROKER = "mcp-governance-gateway-broker"
# Token claims and request headers by which a caller says "I act for someone else" (RFC 8693 act /
# may_act and the usual spellings). The Gateway has no verified actor identity to judge them with,
# so any of them makes PAC-05 refuse the call as unsupported (D-94).
DELEGATION_CLAIMS = ("act", "may_act", "on_behalf_of", "actor", "delegated_by")
DELEGATION_HEADERS = ("x-on-behalf-of", "x-act-as", "x-delegated-user")


def delegation(payload: dict) -> dict:
    """Whether the call asserts delegation, and what identity an agent could be judged by.
    The harness name from clientInfo or User-Agent is caller-reported: it is recorded as the
    source of the agent identity, never as a verified one."""
    claims, client = payload.get("transport_claims") or {}, payload.get("client") or {}
    sources = [f"claim:{key}" for key in DELEGATION_CLAIMS if key in claims]
    sources += [f"header:{name}" for name in client.get("delegation_headers") or [] if name in DELEGATION_HEADERS]
    harness = client.get("harness") or {}
    reported = "client_info" if harness.get("name") else "user_agent" if harness.get("user_agent") else "none"
    return {"asserted": bool(sources), "sources": sources, "verified": False, "actor_verified": False,
            "agent_identity": {"source": reported, "verified": False}}


def ns(value) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1_000_000_000)
    if isinstance(value, str):
        return ns(datetime.fromisoformat(value.replace("Z", "+00:00")))
    return int(value * 1_000_000_000) if type(value) in (int, float) else 0


_capabilities: dict = {"key": None, "document": None}


def capabilities() -> dict:
    """capabilities.json, re-read only when the file changed: the managed-configuration check asks
    for every server's scope on each connection of a managed device."""
    path = registry.REGISTRY_DIR / "capabilities.json"
    status = path.stat()
    key = (str(path), status.st_mtime_ns, status.st_size)
    if _capabilities["key"] != key:
        _capabilities.update(key=key, document=json.loads(path.read_text()))
    return _capabilities["document"]


def under(value: str, prefixes: list[str]) -> bool:
    return any(value == p or value.startswith(p.rstrip("/") + "/") for p in prefixes)


def scope(principal: dict, server: str, tool: str, action: str, resources: list, arguments: dict | None = None) -> dict:
    spec = registry.server(server) or {}
    envelope = spec.get("allowed_principals")
    if envelope is not None:
        terms = (spec.get("tool_reviews") or {}).get(tool) or {}
        allowed = registry.permits(envelope, principal["token"]) and tool in spec.get("tools", {})
        # A remote review approves the explicitly selected feature and declared
        # data class. An argument-induced escalation is outside that approval.
        allowed = allowed and action == spec.get("tools", {}).get(tool)
        constraint = spec.get("parameter_constraints", {}).get(tool)
        allowed = allowed and bool(constraint) and (arguments is None or Draft202012Validator(constraint).is_valid(arguments))
        return {"allowed": allowed, "id": spec.get("intake_id", ""),
                "valid_from": spec.get("registered_at"), "valid_until": spec.get("valid_until"),
                "actions": [spec.get("tools", {}).get(tool)], "resources_allowed": allowed,
                "commands": [], "transfer_destinations": spec.get("transfer_destinations", []),
                # An individual approval given under one purpose does not survive a changed purpose (POL-26).
                "transfer_terms": {key: terms.get(key) for key in ("purpose", "destinations", "grade")}}
    document = capabilities()
    for grant in document["capabilities"]:
        subject = principal["token"] in grant["principals"]
        # Only controlled, explicitly marked lab principals use the test grant.
        # This is not an employee/admin wildcard in a field deployment.
        test_subject = ("acceptance-" + principal["token"].rsplit("-", 1)[-1]
                        if principal["token"].startswith("acceptance-") else
                        "adversarial" if principal["token"].startswith("adversarial-") else
                        "boundary" if principal["token"].startswith("boundary-") else "")
        subject = subject or (principal.get("synthetic") is True
                              and test_subject in grant.get("synthetic_subjects", []))
        if (not subject or server not in grant["servers"] or tool not in spec.get("tools", {})
                or (grant.get("tools") is not None and tool not in grant["tools"])):
            continue
        actions = grant.get("server_actions", {}).get(server, grant["actions"])
        permitted = action in actions and all(
            r.kind in grant["resource_kinds"]
            and (r.kind != "path" or under(r.id, grant["path_roots"]))
            and (r.kind != "repository" or r.id in grant["repositories"])
            and (r.kind != "table" or r.id in grant["tables"] or r.id.startswith(("pg_catalog.", "information_schema.")))
            and (r.kind != "command" or r.id in grant["commands"])
            and (r.kind != "path" or action == "r" or not under(r.id, grant.get("readonly_path_roots", [])))
            for r in resources)
        constraint = grant.get("argument_schema")
        permitted = permitted and (arguments is None or constraint is None
                                   or Draft202012Validator(constraint).is_valid(arguments))
        if permitted:
            return {**grant, "actions": actions, "allowed": True, "resources_allowed": True}
    return {"allowed": False, "resources_allowed": False, "id": "missing", "actions": [],
            "valid_from": None, "valid_until": None, "commands": [], "transfer_destinations": []}


def _argument_error(error) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    if error.validator == "additionalProperties":
        names = sorted(str(k) for k in set(error.instance) - set(error.schema.get("properties") or {}))
        return "승인되지 않은 인자 " + ", ".join(f"{path}.{n}" if path else n for n in names)
    if error.validator == "required":
        names = [str(k) for k in error.validator_value if k not in error.instance]
        return "필요한 인자 " + ", ".join(f"{path}.{n}" if path else n for n in names) + " 없음"
    kind = {"pattern": "값이 승인된 주소·형식 밖", "enum": "값이 승인된 값이 아님", "const": "값이 승인된 값이 아님",
            "type": "형식이 승인 범위와 다름"}.get(error.validator, "값이 승인 범위 밖")
    return f"인자 {path or '(전체)'}: {kind}"


def argument_gap(principal: dict, server: str, tool: str, arguments: dict) -> str:
    """Which argument puts a call outside the approved scope, for the person who has to change it.

    Names the argument and the kind of mismatch, never the approved values: the reviewer's list of
    destinations or values is not shown to the caller anywhere else (tools/list carries the provider's
    schema), so the reason does not become a way to read it out one probe at a time."""
    spec = registry.server(server) or {}
    if spec.get("allowed_principals") is not None:
        constraints = [spec.get("parameter_constraints", {}).get(tool)]
    else:
        constraints = [g.get("argument_schema") for g in capabilities()["capabilities"]
                       if principal["token"] in g["principals"] and server in g["servers"]
                       and (g.get("tools") is None or tool in g["tools"])]
    for constraint in filter(None, constraints):
        errors = sorted(Draft202012Validator(constraint).iter_errors(arguments), key=lambda e: [str(p) for p in e.absolute_path])
        if errors:
            return "; ".join(dict.fromkeys(_argument_error(e) for e in errors[:3]))
    return ""


def visible(principal: dict, server_id: str, tool: str, action: str) -> bool:
    """Whether tools/list may show this tool to this person. SQL's effective action depends on its
    parsed statement; other tools keep their reviewed action, because testing every action would
    expose writes through a read-only capability."""
    actions = {"r", "w", "x"} if (server_id, tool) == ("postgres", "execute_sql") else {action}
    return any(scope(principal, server_id, tool, candidate, [])["allowed"] for candidate in actions)


def servers_for(principal: dict) -> list[str]:
    """Servers this person has at least one reviewed, permitted tool on: what tools/list would show
    them and what a managed harness configuration may carry (D-93)."""
    usable = []
    for server_id, spec in sorted(registry.servers().items()):
        if not registry.permits(registry.allowed_principals(server_id), principal["token"]):
            continue
        if any(visible(principal, server_id, tool, action)
               for tool, action in spec.get("tools", {}).items() if tool in registry.reviewed_tools(server_id)):
            usable.append(server_id)
    return usable


_NAME_SAFE = re.compile(r"[^0-9A-Za-z가-힣 ._()·\-]")


def harness_guidance(principal: dict | None, servers: list[str]) -> str:
    """Which approved MCP servers this person has, written into the harness's own memory (D-233).

    A harness defers MCP tools behind a search (Claude Code ToolSearch, Codex tool search) and shows the
    model only tool names, so a request that names no server ("react 저장소 구조 알려줘") is often answered
    from memory or with a built-in tool (4 of 12 such requests in one trial never reached an MCP tool).
    Only the administrator-reviewed display name and tool names go in: an upstream tool description is
    hash-pinned but still the supplier's text, and this text is loaded with the organisation's own trust."""
    lines = []
    for server_id in servers:
        spec = registry.server(server_id) or {}
        tools = [t for t, action in (spec.get("tools") or {}).items()
                 if principal and t in registry.reviewed_tools(server_id) and visible(principal, server_id, t, action)]
        if tools:
            lines.append(f"- {_NAME_SAFE.sub('', spec.get('display_name') or '').strip()[:60] or server_id} (`mcp__{server_id}__*`): "
                         + ", ".join(_NAME_SAFE.sub("", tool)[:48] for tool in tools[:12]))
    if not lines:
        return ("# 조직 승인 MCP 도구\n이 사용자에게 승인된 MCP 서버가 아직 없습니다. 필요한 MCP가 있으면 MINT 콘솔에서 도입을 신청하거나 "
                "관리자에게 사용 대상 추가를 요청하라고 안내하고, 설정 파일을 찾거나 다른 방법으로 MCP를 연결하려 하지 않습니다.\n")
    return ("# 조직 승인 MCP 도구\n"
            "이 PC에서는 조직 게이트웨이가 승인한 MCP 서버만 쓸 수 있습니다. 사용자가 서버 이름을 말하지 않아도 요청이 아래 서버가 맡는 일"
            "(저장소·문서 검색, 파일 열람, 변환, 기억 등)이면 기억이나 일반 지식으로 답하기 전에 먼저 해당 서버의 도구를 찾아(도구 검색) 사용합니다.\n"
            + "\n".join(lines)
            + "\n도구가 '차단'이나 '승인 대기'로 답하면 사유를 사용자에게 그대로 전하고, 같은 요청을 되풀이하거나 다른 경로로 우회하지 않습니다.\n")


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, (*path, index))
    else:
        yield list(path), value


def digest(document: dict) -> str:
    r, f = document["request"], document["facts"]
    binding = {key: r[key] for key in ("server_id", "feature_type", "feature_id", "action", "arguments",
                                      "targets", "data", "transfer", "environment", "automated", "on_behalf_of", "high_risk")}
    binding.update(request_id=r.get("approval_nonce", r["id"]), **{key: f["identity"][key] for key in ("user_id", "agent_id", "session_id")},
                   endpoint_id=f["connection"]["endpoint_id"], final_target_id=f["connection"]["final_target_id"],
                   final_destination_id=r["transfer"]["destination_id"] if r["transfer"]["enabled"] else "",
                   baseline=f["approval"]["baseline"])
    return canonical_hash(binding)


GRADES_UP_TO = {"public": ["public"], "nonimportant": ["public", "nonimportant"]}


GRADE_LABELS = {"public": "공개", "nonimportant": "내부", "important": "중요"}


def transfer_gap(pac_input: dict) -> str:
    """Why PAC-12 refused an external transfer, without naming the approved destinations (see argument_gap)."""
    facts, request = pac_input.get("facts") or {}, pac_input.get("request") or {}
    transfer = facts.get("transfer") or {}
    if not (request.get("transfer") or {}).get("enabled"):
        return ""
    grade = transfer.get("data_grade") or ""
    label = GRADE_LABELS.get(grade, "—")
    if not transfer.get("final_destination_id"):
        return "외부 목적지를 하나로 확인할 수 없습니다(한 호출에 목적지 하나)"
    pairs = (facts.get("approval") or {}).get("transfer_pairs") or []
    if not pairs:
        return "이 목적지로의 외부 전송이 도구 범위 심사에서 승인되지 않았습니다"
    if not transfer.get("verified"):
        return "서버의 외부 접속 허용 목록이 이 도구의 승인 목적지보다 넓어 최종 목적지를 확인할 수 없습니다"
    if grade == "important":
        return "「중요」 등급 데이터는 외부로 보낼 수 없습니다"
    if not any(p.get("grade") == grade for p in pairs):
        return f"데이터 등급 「{label}」의 외부 전송이 승인되지 않았습니다. 도구 범위 심사의 외부 전송 등급을 「{label}」로 승인해야 합니다"
    return ""


def transfer_binding(spec: dict, feature: str, destinations: list[str]) -> tuple[bool, list[dict]]:
    """POL-26: whether the final destination is proven, and the purpose/destination/grade pairs approved together.

    Multiple or unverified final transfer targets fail closed. HTTP redirects at an MCP tool's
    downstream HTTP client are not proved by Gateway TLS. The egress proxy of a server the runtime
    runs admits the reviewed hosts of all its tools (D-114); only when that set is inside this
    tool's own reviewed hosts does every final hop, redirects included, stay within this binding.
    """
    if not destinations:
        return True, []
    destination = destinations[0] if len(destinations) == 1 else ""
    terms = (spec.get("tool_reviews") or {}).get(feature) or {}
    covered = bool(destination) and any(destination == h or (h.startswith("*.") and destination.endswith(h[1:]))
                                        for h in terms.get("destinations") or [])
    pairs = [{"destination_id": destination, "grade": grade, "purpose": terms.get("purpose", "")}
             for grade in GRADES_UP_TO.get(terms.get("grade"), [])] if covered else []
    egress = {h for review in (spec.get("tool_reviews") or {}).values() for h in review.get("destinations") or []}
    return covered and bool(spec.get("runtime")) and egress <= set(terms.get("destinations") or []), pairs


async def build(payload: dict, principal: dict, cls, tool: dict | None, contract: dict,
                context: dict, request_id: str, environment: str, approval_id: str | None) -> dict:
    now = time.time_ns()
    server, feature = cls.server, cls.tool
    spec = registry.server(server) or {}
    approved = scope(principal, server, feature, cls.action, cls.resources, payload["arguments"])
    execution_profile = capabilities().get("execution_profile", {})
    claims = payload.get("transport_claims") or {}
    delegated = delegation(payload)
    revoked = bool(claims.get("jti") and await db.fetch_one(
        "SELECT jti FROM agent_revoked_tokens WHERE jti=%s", (claims["jti"],)))
    auth_ok = (claims.get("sub") == principal["user_id"] and claims.get("iss") == ISSUER
               and claims.get("aud") == AUDIENCE and bool(claims.get("jti")) and not revoked
               and ns(claims.get("nbf")) <= now < ns(claims.get("exp")))
    identity = {"user_id": principal["user_id"], "agent_id": BROKER, "session_id": claims.get("jti", "")}
    arguments = payload["arguments"]
    schema_ok = bool(tool and tool.get("input_schema") is not None
                     and Draft202012Validator(tool["input_schema"]).is_valid(arguments))
    targets = {"files": [], "commands": [], "recipients": []}
    bindings = []
    for path, value in leaves(arguments):
        key = path[-1] if path else ""
        kind = "scalar"
        if key == "command":
            kind = "command"
            targets["commands"].append(value)
        elif (key in {"path", "repo_path", "source", "destination", "file_path", "outputPath"}
              or (isinstance(key, int) and len(path) > 1 and path[-2] == "paths")) and isinstance(value, str):
            # Only paths classified by this server's reviewed extractor are targets.
            if any(r.kind == "path" for r in cls.resources):
                kind = "file"
                targets["files"].append(value)
        elif ((key in {"to", "cc", "bcc", "recipient"} or
               (isinstance(key, int) and len(path) > 1 and path[-2] in {"recipients", "cc", "bcc"})) and isinstance(value, str)
              # A name alone is not a recipient: a knowledge graph's relation {"from": .., "to": "stdio"} was held
              # to the mail domain list. An address, or a call the classifier read as mail, still is.
              and ("@" in value or any(d.kind == "email" for d in cls.destinations))):
            kind = "recipient"
            targets["recipients"].append(value)
        bindings.append({"argument_path": path, "target_type": kind,
                         "allowed_values": [value] if schema_ok and approved["allowed"] else []})
    parameter_ok = schema_ok and approved["resources_allowed"]
    if targets["files"]:
        parameter_ok = parameter_ok and all(v.startswith("/") and v == posixpath.normpath(v)
                                            for v in targets["files"])
    if targets["commands"]:
        parameter_ok = parameter_ok and all(c in approved["commands"] for c in targets["commands"])
    # Recipient scope and destinations come from the approved organization policy,
    # never from whichever e-mail address happens to arrive in this request.
    internal_domains = registry.catalog().get("organization", {}).get("internal_email_domains", [])
    if targets["recipients"]:
        parameter_ok = parameter_ok and all(isinstance(v, str) and v.rsplit("@", 1)[-1] in internal_domains
                                            for v in targets["recipients"])
    endpoint = spec.get("endpoint", "")
    baseline = {"server_version": (tool or {}).get("approved_server_version", ""),
                "feature_definition_hash": (tool or {}).get("approved_description_hash", ""),
                "schema_hash": (tool or {}).get("approved_schema_hash", ""), "policy_version": VERSION,
                # An individual approval must not survive a changed reviewed scope.
                "scope_sha256": canonical_hash(approved)}
    location_facts = residency.facts(spec, registry.catalog().get("organization", {}), cls, residency.load_pack())
    baseline["residency_sha256"] = canonical_hash(location_facts)
    catalog_ok = all(contract.get(k) is True for k in (
        "registered", "enabled", "schema_hash_match", "description_hash_match", "version_match", "known_tools_only"))
    connection_ok = catalog_ok and contract.get("transport_secure") is True and contract.get("endpoint_allowed") is True
    high_risk = cls.action == "x"
    destinations = sorted({d.host for d in cls.destinations if d.external})  # two links to one host are one target
    transfer = bool(destinations)
    destination = destinations[0] if len(destinations) == 1 else ""
    transfer_ok, transfer_pairs = transfer_binding(spec, feature, destinations)
    reservation = await db.fetch_one("SELECT * FROM call_reservations WHERE request_id=%s", (request_id,))
    active = bool(reservation and reservation["released_at"] is None and ns(reservation["expires_at"]) > now)
    limits = execution_profile.get("limits", {})
    a = {"status": "APPROVED" if approved["allowed"] else "UNAPPROVED", "server_id": server,
         "valid_from_ns": ns(approved.get("valid_from")), "valid_until_ns": ns(approved.get("valid_until")),
         "baseline": baseline, "environments": approved.get("environments", ["prod"]) if spec.get("intake_id") else approved.get("environments", []),
         "production_controls": execution_profile.get("production_controls") is True,
         "subject": identity, "auth_issuer": ISSUER, "auth_resource": AUDIENCE,
         "connections": [{"server_id": server, "endpoint_id": endpoint, "final_target_id": endpoint}],
         "features": [{"server_id": server, "type": "tool", "id": feature, "definition_hash": baseline["feature_definition_hash"]}],
         "actions": approved["actions"], "allowed_argument_keys": list((tool or {}).get("input_schema", {}).get("properties", {})),
         "parameter_bindings": bindings, "targets": targets if parameter_ok else {"files": [], "commands": [], "recipients": []},
         "data_scopes": [{"asset_id": cls.primary.id, "grade": cls.data_class}] if approved["resources_allowed"] else [],
         "transfer_pairs": transfer_pairs, "limits": limits}
    request = {"id": request_id, "approval_nonce": payload.get("pac_request_id", request_id),
               **identity, "server_id": server, "feature_type": "tool", "feature_id": feature,
               "action": cls.action, "arguments": arguments, "environment": environment, "targets": targets,
               "data": {"asset_id": cls.primary.id, "grade": cls.data_class},
               "transfer": {"enabled": transfer, "destination_id": destination}, "high_risk": high_risk,
               "automated": True, "on_behalf_of": delegated["asserted"]}
    unresolved = await db.fetch_one(
        """SELECT 1 FROM decisions WHERE user_token=%s AND server_id=%s AND tool_name=%s
           AND upstream_attempted AND NOT upstream_executed AND action IN ('w','x')
           AND request_payload->'arguments'=%s
           AND NOT EXISTS (SELECT 1 FROM dispatch_intents i WHERE i.decision_id = decisions.id
                            AND i.state IN ('confirmed_executed','confirmed_not_executed')) LIMIT 1""",
        (principal["token"], server, feature, Jsonb(arguments)))
    facts = {"trusted": True, "now_ns": now, "approval": a, "approval_workflow_available": True,
             "residency": location_facts,
             "classification": {"verified": tool is not None, "high_risk": high_risk, "transfer_required": transfer,
                                "automated": True, "on_behalf_of": delegated["asserted"]},
             "delegation": delegated,
             "baseline": {"server_version": (tool or {}).get("observed_server_version", ""),
                          "feature_definition_hash": (tool or {}).get("observed_description_hash", ""),
                          "schema_hash": (tool or {}).get("observed_schema_hash", ""),
                          "policy_version": VERSION, "verified": catalog_ok},
             "environment": {"verified": bool(environment), "id": environment, "production_equivalent": environment == "prod"},
             "identity": {**identity, "verified": auth_ok, "allowed_actions": approved["actions"]},
             "auth": {"mode": "http", "verified": auth_ok, "not_revoked": not revoked,
                      "issuer": claims.get("iss", ""), "audience": claims.get("aud", ""),
                      "valid_from_ns": ns(claims.get("nbf")), "valid_until_ns": ns(claims.get("exp")),
                      "scopes": approved["actions"] if auth_ok and set(str(claims.get("scope", "")).split()) & {"mcp", "console"} else []},
             "connection": {"verified": connection_ok, "final_target_verified": connection_ok,
                            "server_id": server, "endpoint_id": endpoint, "final_target_id": endpoint},
             "catalog_feature": {"verified": catalog_ok, "server_id": server, "type": "tool", "id": feature,
                                 "definition_hash": baseline["feature_definition_hash"]},
             "action": {"verified": cls.base_action in {"r", "w", "x"}, "normalized": cls.action},
             "parameters": {"verified": parameter_ok, "normalized": parameter_ok, "schema_valid": schema_ok,
                            "coverage_complete": parameter_ok, "canonical_arguments": arguments, "derived_targets": targets},
             "data": {"verified": approved["resources_allowed"], **request["data"]},
             "transfer": {"verified": transfer_ok, "final_destination_verified": transfer_ok,
                          "final_destination_id": destination, "data_grade": cls.data_class},
             "revocation": {"verified": auth_ok and principal["status"] == "active", "fresh": True,
                            "user": principal["status"] != "active", "agent": False,
                            "server": contract.get("lifecycle") != "OPERATING", "feature": not contract.get("enabled"),
                            "approval": not approved["allowed"]},
             "execution": {"atomic_reservation_verified": active, "reservation_request_id": request_id,
                           "reservation_expires_ns": ns(reservation["expires_at"]) if reservation else 0,
                           "duplicate_status": "duplicate" if context["duplicate_in_flight"] else "clear",
                           "previous_mutation_status": "unconfirmed" if unresolved else "clear", "retry_count": 0, "chain_depth": 1,
                           "active_concurrency": context["active_calls"], "total_calls": context["recent_calls"] + 1,
                           "requested_timeout_ms": context["execution_timeout_ms"]}}
    document = {"request": request, "facts": facts}
    if approval_id:
        row = await db.fetch_one("SELECT * FROM approvals WHERE id=%s", (approval_id,))
        reviewer = await db.fetch_one("SELECT role,status,user_id FROM principals WHERE token=%s", (row["reviewed_by"],)) if row else None
        facts["individual_approval"] = {"verified": bool(row and row["request_fingerprint"] == canonical_hash(row["request_payload"])),
                                       "approver_authorized": bool(reviewer and reviewer["role"] == "admin" and reviewer["status"] == "active"),
                                       "approver_id": reviewer["user_id"] if reviewer else "", "single_use_reserved": bool(row and row["status"] == "APPROVED"),
                                       "status": row["status"] if row else "MISSING", "request_id": row["request_payload"].get("pac_request_id", "") if row else "",
                                       "request_digest": (row["request_payload"].get("pac_digest", "") if row else ""),
                                       "server_id": server, "feature_id": feature, "action": cls.action,
                                       "valid_from_ns": ns(row["created_at"]) if row else 0, "valid_until_ns": ns(row["expires_at"]) if row else 0}
    return document
