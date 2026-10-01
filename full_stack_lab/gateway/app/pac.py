"""PAC-15 facts from transport identity, reviewed capabilities and reserved state.

The execution agent is this Gateway broker, not an attested Claude/Codex binary.
Parameter bindings are materialized only after the reviewed schema and resource
scope pass; observing an argument never adds it to an approval.
"""
from __future__ import annotations

import json
import posixpath
import time
from datetime import datetime

from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from . import db, registry
from .agent_contract import AUDIENCE, ISSUER
from .contract import canonical_hash

VERSION = "pac15-v1"
BROKER = "mcp-governance-gateway-broker"


def ns(value) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1_000_000_000)
    if isinstance(value, str):
        return ns(datetime.fromisoformat(value.replace("Z", "+00:00")))
    return int(value * 1_000_000_000) if type(value) in (int, float) else 0


def capabilities() -> dict:
    return json.loads((registry.REGISTRY_DIR / "capabilities.json").read_text())


def under(value: str, prefixes: list[str]) -> bool:
    return any(value == p or value.startswith(p.rstrip("/") + "/") for p in prefixes)


def scope(principal: dict, server: str, tool: str, action: str, resources: list, arguments: dict | None = None) -> dict:
    spec = registry.server(server) or {}
    envelope = spec.get("allowed_principals")
    if envelope is not None:
        allowed = principal["token"] in envelope and tool in spec.get("tools", {})
        # A remote review approves the explicitly selected feature and declared
        # data class. An argument-induced escalation is outside that approval.
        allowed = allowed and action == spec.get("tools", {}).get(tool)
        constraint = spec.get("parameter_constraints", {}).get(tool)
        allowed = allowed and bool(constraint) and (arguments is None or Draft202012Validator(constraint).is_valid(arguments))
        return {"allowed": allowed, "id": spec.get("intake_id", ""),
                "valid_from": spec.get("registered_at"), "valid_until": spec.get("valid_until"),
                "actions": [spec.get("tools", {}).get(tool)], "resources_allowed": allowed,
                "commands": [], "transfer_destinations": spec.get("transfer_destinations", [])}
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


async def build(payload: dict, principal: dict, cls, tool: dict | None, contract: dict,
                context: dict, request_id: str, environment: str, approval_id: str | None) -> dict:
    now = time.time_ns()
    server, feature = cls.server, cls.tool
    spec = registry.server(server) or {}
    approved = scope(principal, server, feature, cls.action, cls.resources, payload["arguments"])
    execution_profile = capabilities().get("execution_profile", {})
    claims = payload.get("transport_claims") or {}
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
        elif (key in {"to", "cc", "bcc", "recipient"} or
              (isinstance(key, int) and len(path) > 1 and path[-2] in {"recipients", "cc", "bcc"})) and isinstance(value, str):
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
    catalog_ok = all(contract.get(k) is True for k in (
        "registered", "enabled", "schema_hash_match", "description_hash_match", "version_match", "known_tools_only"))
    connection_ok = catalog_ok and contract.get("transport_secure") is True and contract.get("endpoint_allowed") is True
    high_risk = cls.action == "x"
    destinations = [d.value for d in cls.destinations if d.external]
    # Multiple or unverified final transfer targets fail closed. HTTP redirects at
    # an MCP tool's downstream HTTP client are not proved by Gateway TLS.
    transfer = bool(destinations)
    destination = destinations[0] if len(destinations) == 1 else ""
    transfer_ok = not transfer
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
         "transfer_pairs": [], "limits": limits}
    request = {"id": request_id, "approval_nonce": payload.get("pac_request_id", request_id),
               **identity, "server_id": server, "feature_type": "tool", "feature_id": feature,
               "action": cls.action, "arguments": arguments, "environment": environment, "targets": targets,
               "data": {"asset_id": cls.primary.id, "grade": cls.data_class},
               "transfer": {"enabled": transfer, "destination_id": destination}, "high_risk": high_risk,
               "automated": True, "on_behalf_of": False}
    unresolved = await db.fetch_one(
        """SELECT 1 FROM decisions WHERE user_token=%s AND server_id=%s AND tool_name=%s
           AND upstream_attempted AND NOT upstream_executed AND action IN ('w','x')
           AND request_payload->'arguments'=%s LIMIT 1""", (principal["token"], server, feature, Jsonb(arguments)))
    facts = {"trusted": True, "now_ns": now, "approval": a, "approval_workflow_available": True,
             "classification": {"verified": tool is not None, "high_risk": high_risk, "transfer_required": transfer,
                                "automated": True, "on_behalf_of": False},
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
