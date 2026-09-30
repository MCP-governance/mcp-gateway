"""PAC-15 rules over OPA REST: 200 normal-behaviour cases + 100 bug/abnormal probes.

python3 pac15_suite.py [normal|bugs|all]   (OPA at $OPA, default localhost:18181)

The same inputs are sent to the original draft and to the reviewed copy (`run.sh` starts
both). Inputs carry the facts the reviewed copy asks for as well (a local connector's
identity, lifetime and scopes; the approver's id); the original ignores fields it does
not read, so the normal set means the same thing to both.
"""
import copy, json, os, sys, time, urllib.request

OPA = os.environ.get("OPA", "http://localhost:18181")
BASE = json.load(open(os.path.join(os.path.dirname(__file__), "examples", "allow.json")))
NOW = BASE["facts"]["now_ns"]
T0, T1 = 1700000000000000000, 1900000000000000000


def post(path, doc):
    req = urllib.request.Request(f"{OPA}/v1/data/{path}", json.dumps({"input": doc}).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r).get("result")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def decide(doc):
    return post("mcp/decision/decision", doc)


def digest(doc):
    return post("mcp/pac15/request_digest", doc)[1]


def setp(doc, path, value):
    node = doc
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value


def make(i, *, local=False, obo=True, cond=False, transfer=False, prod_eq=False, auto=False,
         kind="file", action="READ", high=False):
    """A consistent ALLOW document; every id is varied by i."""
    d = copy.deepcopy(BASE)
    r, f, a = d["request"], d["facts"], d["facts"]["approval"]
    u, ag, se, sv, ft = f"user-{i}", f"agent-{i}", f"sess-{i}", f"srv-{i % 7}", f"tool_{i % 11}"
    rid = f"req-{i:04d}"
    r.update(id=rid, user_id=u, agent_id=ag, session_id=se, server_id=sv, feature_id=ft, action=action,
             on_behalf_of=obo, high_risk=high, automated=auto)
    if kind == "file":
        args, key, tgt = {"path": f"/data/f{i}.txt"}, "path", {"files": [f"/data/f{i}.txt"], "commands": [], "recipients": []}
        bindings = [{"argument_path": ["path"], "target_type": "file"}]
    elif kind == "command":
        args, key, tgt = {"cmd": f"ls -l /tmp/{i}"}, "cmd", {"files": [], "commands": [f"ls -l /tmp/{i}"], "recipients": []}
        bindings = [{"argument_path": ["cmd"], "target_type": "command"}]
    elif kind == "recipient":
        args, key, tgt = {"to": f"p{i}@corp.test", "mode": "plain"}, "to", {"files": [], "commands": [], "recipients": [f"p{i}@corp.test"]}
        bindings = [{"argument_path": ["to"], "target_type": "recipient"},
                    {"argument_path": ["mode"], "target_type": "scalar", "allowed_values": ["plain", "html"]}]
    else:  # nested path binding
        args, key, tgt = {"opts": {"path": f"/n/{i}"}}, "opts", {"files": [f"/n/{i}"], "commands": [], "recipients": []}
        bindings = [{"argument_path": ["opts", "path"], "target_type": "file"}]
    r["arguments"], r["targets"] = args, tgt
    f["parameters"]["canonical_arguments"] = copy.deepcopy(args)
    f["parameters"]["derived_targets"] = copy.deepcopy(tgt)
    a["allowed_argument_keys"] = sorted(set(args) | {"unused_key"})
    a["parameter_bindings"] = bindings
    a["targets"] = {k: v + [f"other-{k}"] for k, v in tgt.items()}
    a.update(server_id=sv, subject={"user_id": u, "agent_id": ag, "session_id": se},
             actions=[action, "LIST"], status="CONDITIONAL_APPROVED" if cond else "APPROVED",
             connections=[{"server_id": "srv-x", "endpoint_id": "e-x", "final_target_id": "t-x"},
                          {"server_id": sv, "endpoint_id": f"ep-{sv}", "final_target_id": f"tg-{sv}"}],
             features=[{"server_id": sv, "type": "tool", "id": ft, "definition_hash": "sha256:feature-v1"},
                       {"server_id": sv, "type": "prompt", "id": "other", "definition_hash": "sha256:x"}],
             data_scopes=[{"asset_id": f"asset-{i % 5}", "grade": "internal"}, {"asset_id": "asset-x", "grade": "secret"}],
             transfer_pairs=[{"destination_id": f"dest-{i % 3}", "grade": "internal"}])
    a["limits"]["allow_automated"] = auto
    r["data"] = {"asset_id": f"asset-{i % 5}", "grade": "internal"}
    f["data"].update(asset_id=f"asset-{i % 5}", grade="internal")
    f["classification"].update(high_risk=high, transfer_required=transfer, on_behalf_of=obo, automated=auto)
    if transfer:
        r["transfer"] = {"enabled": True, "destination_id": f"dest-{i % 3}"}
        f["transfer"]["final_destination_id"] = f"dest-{i % 3}"
    f["identity"].update(user_id=u, agent_id=ag, session_id=se, allowed_actions=[action, "LIST"])
    f["delegation"].update(user_id=u, agent_id=ag, user_actions=[action], agent_actions=[action, "LIST"],
                           delegated_actions=[action])
    if local:
        f["auth"] = {"mode": "local", "verified": True, "not_revoked": True, "connector_id": f"conn-{i % 3}",
                     "valid_from_ns": T0, "valid_until_ns": T1, "scopes": [action]}
        a["local_connectors"] = [f"conn-{i % 3}", "conn-spare"]
    else:
        f["auth"].update(audience=sv, scopes=[action])
    f["connection"].update(server_id=sv, endpoint_id=f"ep-{sv}", final_target_id=f"tg-{sv}")
    f["catalog_feature"].update(server_id=sv, id=ft)
    f["action"]["normalized"] = action
    if prod_eq:
        f["environment"]["production_equivalent"] = True
    f["execution"]["reservation_request_id"] = rid
    return d


def approve(d, **over):
    d["facts"]["individual_approval"] = {
        "verified": True, "approver_authorized": True, "single_use_reserved": True, "status": "APPROVED",
        "approver_id": "approver-1",
        "request_id": d["request"]["id"], "request_digest": digest(d), "server_id": d["request"]["server_id"],
        "feature_id": d["request"]["feature_id"], "action": d["request"]["action"],
        "valid_from_ns": T0, "valid_until_ns": T1, **over}
    return d


def mut(d, changes):
    for p, v in changes.items():
        setp(d, p, v)
    return d


# ---------------------------------------------------------------- 200 normal
def normal_cases():
    kinds = ["file", "command", "recipient", "nested"]
    actions = ["READ", "WRITE", "LIST", "SEND"]
    c = []
    for i in range(60):  # ALLOW variants
        opts = dict(local=i % 2 == 1, obo=i % 3 != 0, cond=i % 5 == 0, transfer=i % 4 == 0,
                    prod_eq=i % 7 == 0, auto=i % 6 == 0, kind=kinds[i % 4], action=actions[i % 4])
        c.append((f"allow-{i:02d} {opts}", make(i, **opts), "ALLOW", []))
    for i in range(20):  # high risk with a digest-bound single-use approval
        c.append((f"high-risk approved {i}", approve(make(100 + i, kind=kinds[i % 4], high=True, transfer=i % 2 == 0)), "ALLOW", []))
    for i in range(20):  # high risk, no approval yet -> held
        c.append((f"high-risk pending {i}", make(200 + i, kind=kinds[i % 4], high=True, local=i % 2 == 0), "APPROVAL", ["PAC-13"]))
    # boundaries (8)
    c += [
        ("approval starts exactly now", mut(make(300), {"facts.approval.valid_from_ns": NOW}), "ALLOW", []),
        ("approval ends 1ns after now", mut(make(301), {"facts.approval.valid_until_ns": NOW + 1}), "ALLOW", []),
        ("approval ends exactly now", mut(make(302), {"facts.approval.valid_until_ns": NOW}), "DENY", ["PAC-01"]),
        ("approval not yet valid", mut(make(303), {"facts.approval.valid_from_ns": NOW + 1}), "DENY", ["PAC-01"]),
        ("limits exactly reached", mut(make(304), {"facts.execution.retry_count": 2, "facts.execution.active_concurrency": 2,
            "facts.execution.total_calls": 10, "facts.execution.chain_depth": 3, "facts.execution.requested_timeout_ms": 30000}), "ALLOW", []),
        ("calls one over", mut(make(305), {"facts.execution.total_calls": 11}), "DENY", ["PAC-15"]),
        ("reservation expires now", mut(make(306), {"facts.execution.reservation_expires_ns": NOW}), "DENY", ["PAC-15"]),
        ("token ends exactly now", mut(make(307), {"facts.auth.valid_until_ns": NOW}), "DENY", ["PAC-06"]),
    ]
    # 92 single-policy denials: (label, changes, ids, make-kwargs)
    D = [
        ("PAC-01 status PENDING", {"facts.approval.status": "PENDING"}, ["PAC-01"], {}),
        ("PAC-01 status REVOKED", {"facts.approval.status": "REVOKED"}, ["PAC-01"], {}),
        ("PAC-01 condition unmet", {"facts.approval.conditions_met": False}, ["PAC-01"], {"cond": True}),
        ("PAC-01 approval for other server", {"facts.approval.server_id": "srv-other"}, ["PAC-01"], {}),
        ("PAC-02 server version drift", {"facts.baseline.server_version": "1.0.1"}, ["PAC-02"], {}),
        ("PAC-02 feature hash drift", {"facts.baseline.feature_definition_hash": "sha256:new"}, ["PAC-02"], {}),
        ("PAC-02 baseline unverified", {"facts.baseline.verified": False}, ["PAC-02"], {}),
        ("PAC-03 env not approved", {"facts.approval.environments": ["dev"]}, ["PAC-03"], {}),
        ("PAC-03 env mismatch", {"request.environment": "dev"}, ["PAC-03"], {}),
        ("PAC-03 prod-eq without controls", {"facts.approval.production_controls": False}, ["PAC-03"], {"prod_eq": True}),
        ("PAC-04 session changed", {"facts.identity.session_id": "sess-other", "request.session_id": "sess-other"}, ["PAC-04"], {"obo": False}),
        ("PAC-04 agent spoofed in request", {"request.agent_id": "agent-evil"}, ["PAC-04"], {"obo": False}),
        ("PAC-04 identity unverified", {"facts.identity.verified": False}, ["PAC-04"], {"obo": False}),
        ("PAC-05 action not delegated", {"facts.delegation.delegated_actions": ["LIST"]}, ["PAC-05"], {}),
        ("PAC-05 agent lacks right", {"facts.delegation.agent_actions": ["LIST"]}, ["PAC-05"], {}),
        ("PAC-05 delegation for other user", {"facts.delegation.user_id": "user-x"}, ["PAC-05"], {}),
        ("PAC-06 token revoked", {"facts.auth.not_revoked": False}, ["PAC-06"], {}),
        ("PAC-06 foreign issuer", {"facts.auth.issuer": "https://evil.test"}, ["PAC-06"], {}),
        ("PAC-06 scope missing", {"facts.auth.scopes": ["LIST"]}, ["PAC-06"], {}),
        ("PAC-06 local unverified", {"facts.auth.verified": False}, ["PAC-06"], {"local": True}),
        ("PAC-07 endpoint unknown", {"facts.connection.endpoint_id": "ep-evil"}, ["PAC-07"], {}),
        ("PAC-07 final target unverified", {"facts.connection.final_target_verified": False}, ["PAC-07"], {}),
        ("PAC-07 crossed pair", {"facts.connection.final_target_id": "t-x"}, ["PAC-07"], {}),
        ("PAC-08 type swapped", {"facts.catalog_feature.type": "prompt", "request.feature_type": "prompt"}, ["PAC-08"], {}),
        ("PAC-08 rug-pull hash", {"facts.catalog_feature.definition_hash": "sha256:evil"}, ["PAC-08"], {}),
        ("PAC-08 catalog unverified", {"facts.catalog_feature.verified": False}, ["PAC-08"], {}),
        ("PAC-09 action not in approval", {"facts.approval.actions": ["LIST"]}, ["PAC-09"], {}),
        ("PAC-09 subject lacks action", {"facts.identity.allowed_actions": ["LIST"]}, ["PAC-09"], {"obo": False}),
        ("PAC-09 normalization mismatch", {"facts.action.normalized": "DELETE"}, ["PAC-09"], {}),
        ("PAC-10 schema invalid", {"facts.parameters.schema_valid": False}, ["PAC-10"], {}),
        ("PAC-10 coverage incomplete", {"facts.parameters.coverage_complete": False}, ["PAC-10"], {}),
        ("PAC-10 target outside approval", {"facts.approval.targets.files": ["other"]}, ["PAC-10"], {}),
        ("PAC-10 key not allowed", {"facts.approval.allowed_argument_keys": ["unused_key"]}, ["PAC-10"], {}),
        ("PAC-10 scalar out of range", {"request.arguments.mode": "script", "facts.parameters.canonical_arguments.mode": "script"}, ["PAC-10"], {"kind": "recipient"}),
        ("PAC-10 command substituted", {"request.arguments.cmd": "rm -rf /", "facts.parameters.canonical_arguments.cmd": "rm -rf /"}, ["PAC-10"], {"kind": "command"}),
        ("PAC-11 asset swap", {"request.data.asset_id": "asset-x", "facts.data.asset_id": "asset-x"}, ["PAC-11"], {}),
        ("PAC-11 grade mislabel", {"request.data.grade": "public"}, ["PAC-11"], {}),
        ("PAC-11 data unverified", {"facts.data.verified": False}, ["PAC-11"], {}),
        ("PAC-12 destination redirect", {"facts.transfer.final_destination_id": "dest-evil"}, ["PAC-12"], {"transfer": True}),
        ("PAC-12 destination unverified", {"facts.transfer.final_destination_verified": False}, ["PAC-12"], {"transfer": True}),
        ("PAC-12 grade not paired", {"facts.transfer.data_grade": "secret"}, ["PAC-12"], {"transfer": True}),
        ("PAC-14 user suspended", {"facts.revocation.user": True}, ["PAC-14"], {}),
        ("PAC-14 feature revoked", {"facts.revocation.feature": True}, ["PAC-14"], {}),
        ("PAC-14 stale revocation", {"facts.revocation.fresh": False}, ["PAC-14"], {}),
        ("PAC-15 automated not allowed", {"request.automated": True, "facts.classification.automated": True}, ["PAC-15"], {}),
        ("PAC-15 chain too deep", {"facts.execution.chain_depth": 4}, ["PAC-15"], {}),
        ("PAC-15 previous mutation unknown", {"facts.execution.previous_mutation_status": "unknown"}, ["PAC-15"], {}),
        ("PAC-15 reservation for other id", {"facts.execution.reservation_request_id": "req-zzz"}, ["PAC-15"], {}),
        ("PAC-15 timeout too long", {"facts.execution.requested_timeout_ms": 30001}, ["PAC-15"], {}),
        ("INPUT untrusted facts", {"facts.trusted": False}, ["INPUT_CONTRACT"], {}),
        ("INPUT empty request id", {"request.id": ""}, ["INPUT_CONTRACT"], {}),
        ("INPUT transfer flag spoofed", {"request.transfer.enabled": True}, ["INPUT_CONTRACT"], {}),
        ("INPUT automated flag spoofed", {"request.automated": True}, ["INPUT_CONTRACT"], {}),
        ("INPUT classification unverified", {"facts.classification.verified": False}, ["INPUT_CONTRACT"], {}),
    ]
    hr = [  # high-risk approval failures
        ("PAC-13 approver unauthorized", {"approver_authorized": False}),
        ("PAC-13 approval expired", {"valid_until_ns": NOW}),
        ("PAC-13 approval rejected", {"status": "REJECTED"}),
        ("PAC-13 approval for other request", {"request_id": "req-other"}),
        ("PAC-13 approval for other action", {"action": "DELETE"}),
        ("PAC-13 approval unverified", {"verified": False}),
    ]
    j = 400
    while len(c) < 200:
        for label, ch, ids, kw in D:
            if len(c) >= 200:
                break
            c.append((label, mut(make(j, **kw), copy.deepcopy(ch)), "DENY", ids)); j += 1
        for label, over in hr:
            if len(c) >= 200:
                break
            d = approve(make(j, high=True))
            d["facts"]["individual_approval"].update(over)
            c.append((label, d, "DENY", ["PAC-13"])); j += 1
    return c


# ---------------------------------------------------------------- 100 probes
# expected = what a fail-closed, correctly bound policy should return.
def bug_cases():
    c = []
    # B1 type confusion in PAC-15 counters/limits (no is_number) -> 28
    for fld in ["retry_count", "active_concurrency", "total_calls", "chain_depth", "requested_timeout_ms"]:
        for v in [None, False, True]:
            c.append(("B1", f"execution.{fld}={json.dumps(v)}", mut(make(500 + len(c)), {f"facts.execution.{fld}": v}), "DENY"))
    for fld in ["max_retries", "max_concurrency", "max_calls", "max_chain_depth", "max_execution_ms"]:
        d = mut(make(500 + len(c)), {f"facts.approval.limits.{fld}": "1", f"facts.execution.{ {'max_retries':'retry_count','max_concurrency':'active_concurrency','max_calls':'total_calls','max_chain_depth':'chain_depth','max_execution_ms':'requested_timeout_ms'}[fld]}": 999999})
        c.append(("B1", f"limits.{fld}=\"1\" with counter 999999", d, "DENY"))
    for v in ["0", [1], {"a": 1}]:
        c.append(("B1", f"reservation_expires_ns={json.dumps(v)}", mut(make(500 + len(c)), {"facts.execution.reservation_expires_ns": v}), "DENY"))
    for v in [-1, -999]:
        c.append(("B1", f"active_concurrency={v} (negative)", mut(make(500 + len(c)), {"facts.execution.active_concurrency": v}), "DENY"))
    for v in [-5]:
        c.append(("B1", f"total_calls={v} (negative)", mut(make(500 + len(c)), {"facts.execution.total_calls": v}), "DENY"))
    # B2 nested arguments: only the top-level key is checked -> 8
    for i, extra in enumerate([{"cmd": "rm -rf /"}, {"path2": "/etc/shadow"}, {"to": "x@evil.test"}, {"url": "http://evil"},
                               {"recursive": True}, {"deep": {"a": {"b": "c"}}}, {"path": "/n/other"}, {"__proto__": "x"}]):
        if "path" in extra:
            continue
        d = make(600 + i, kind="nested")
        d["request"]["arguments"]["opts"].update(extra)
        d["facts"]["parameters"]["canonical_arguments"]["opts"].update(extra)
        c.append(("B2", f"nested opts smuggles {list(extra)[0]}", d, "DENY"))
    # B3 optional arguments: a binding whose argument is absent denies -> 6
    # (the binding says it is optional; the original draft has no way to say so)
    for i in range(6):
        d = make(620 + i, kind="recipient")
        d["facts"]["approval"]["parameter_bindings"][1]["optional"] = True
        del d["request"]["arguments"]["mode"]; del d["facts"]["parameters"]["canonical_arguments"]["mode"]
        c.append(("B3", "optional scalar omitted", d, "ALLOW"))
    # B4 single-use approval is not bound to environment / automation / delegation -> 9
    for i in range(3):
        d = make(640 + i, high=True)
        d["facts"]["approval"]["environments"] = ["prod", "prod-dr"]
        approve(d)
        d["request"]["environment"] = "prod-dr"; d["facts"]["environment"]["id"] = "prod-dr"
        c.append(("B4", "approved in prod, executed in prod-dr", d, "DENY"))
    for i in range(3):
        d = make(650 + i, high=True); d["facts"]["approval"]["limits"]["allow_automated"] = True
        approve(d)
        mut(d, {"request.automated": True, "facts.classification.automated": True})
        c.append(("B4", "approved manual call, executed as automated", d, "DENY"))
    for i in range(3):
        d = make(660 + i, high=True, obo=False)
        approve(d)
        mut(d, {"request.on_behalf_of": True, "facts.classification.on_behalf_of": True})
        c.append(("B4", "approved direct call, executed on behalf of user", d, "DENY"))
    # B5 a local connector skips every token check -> 6
    # A local connection has no issuer or audience. The first run of this suite also
    # changed those two fields and counted them as anomalies; that was the test's error,
    # not the draft's, so they are replaced by the connector's own identity and lifetime.
    for i, ch in enumerate([{"facts.auth.scopes": []}, {"facts.auth.connector_id": "conn-unapproved"},
                            {"facts.auth.valid_from_ns": NOW + 1},
                            {"facts.auth.not_revoked": False}, {"facts.auth.valid_until_ns": 1},
                            {"facts.auth.scopes": ["LIST"]}]):
        d = make(680 + i, local=True)
        c.append(("B5", f"local mode ignores {list(ch)[0]}", mut(d, ch), "DENY"))
    # B6 self-approval / approver identity not checked -> 4
    for i in range(4):
        d = approve(make(700 + i, high=True))
        d["facts"]["individual_approval"]["approver_id"] = d["request"]["user_id"]
        c.append(("B6", "requester approves own high-risk call", d, "DENY"))
    # B7 malformed / hostile input must still yield DENY (not error, not undefined) -> rest
    weird = [
        ("input {}", {}), ("input []", []), ("input null", None), ("input string", "x"),
        ("request null", {**BASE, "request": None}), ("facts null", {**BASE, "facts": None}),
        ("facts string", {**BASE, "facts": "trusted"}), ("arguments array", mut(copy.deepcopy(BASE), {"request.arguments": ["path"]})),
        ("targets string", mut(copy.deepcopy(BASE), {"request.targets": "file-1"})),
        ("targets.files string", mut(copy.deepcopy(BASE), {"request.targets.files": "file-1", "facts.parameters.derived_targets.files": "file-1"})),
        ("approval list", mut(copy.deepcopy(BASE), {"facts.approval": [BASE["facts"]["approval"]]})),
        ("now_ns string", mut(copy.deepcopy(BASE), {"facts.now_ns": "1800000000000000000"})),
        ("now_ns float", mut(copy.deepcopy(BASE), {"facts.now_ns": 1.8e18})),
        ("trusted string", mut(copy.deepcopy(BASE), {"facts.trusted": "true"})),
        ("high_risk string both", mut(copy.deepcopy(BASE), {"request.high_risk": "no", "facts.classification.high_risk": "no"})),
        ("transfer.enabled string both", mut(copy.deepcopy(BASE), {"request.transfer.enabled": "no", "facts.classification.transfer_required": "no"})),
        ("on_behalf_of string both", mut(copy.deepcopy(BASE), {"request.on_behalf_of": "no", "facts.classification.on_behalf_of": "no"})),
        ("automated null both", mut(copy.deepcopy(BASE), {"request.automated": None, "facts.classification.automated": None})),
        ("individual_approval null on high risk", mut(copy.deepcopy(BASE), {"request.high_risk": True, "facts.classification.high_risk": True, "facts.individual_approval": None})),
        ("workflow flag string", mut(copy.deepcopy(BASE), {"request.high_risk": True, "facts.classification.high_risk": True, "facts.approval_workflow_available": "true"})),
        ("binding unknown type", mut(copy.deepcopy(BASE), {"facts.approval.parameter_bindings": [{"argument_path": ["path"], "target_type": "url"}]})),
        ("binding empty path", mut(copy.deepcopy(BASE), {"facts.approval.parameter_bindings": [{"argument_path": [], "target_type": "file"}]})),
        ("scalar binding w/o allowed_values", mut(copy.deepcopy(BASE), {"facts.approval.parameter_bindings": [{"argument_path": ["path"], "target_type": "scalar"}], "request.targets.files": [], "facts.parameters.derived_targets.files": []})),
        ("path with traversal", mut(copy.deepcopy(BASE), {"request.arguments.path": "file-1/../../etc/passwd", "facts.parameters.canonical_arguments.path": "file-1/../../etc/passwd"})),
        ("unicode lookalike action", mut(copy.deepcopy(BASE), {"request.action": "REАD", "facts.action.normalized": "REАD"})),
        ("huge argument 1MB", mut(copy.deepcopy(BASE), {"request.arguments.path": "A" * 1000000, "facts.parameters.canonical_arguments.path": "A" * 1000000})),
        ("policy_version missing", mut(copy.deepcopy(BASE), {"facts.approval.baseline": {k: v for k, v in BASE["facts"]["approval"]["baseline"].items() if k != "policy_version"}})),
        ("request id whitespace", mut(copy.deepcopy(BASE), {"request.id": " ", "facts.execution.reservation_request_id": " "})),
        ("duplicate targets", mut(copy.deepcopy(BASE), {"request.targets.files": ["file-1", "file-1"], "facts.parameters.derived_targets.files": ["file-1", "file-1"]})),
    ]
    expect = {"now_ns float": "ALLOW", "duplicate targets": "ALLOW", "request id whitespace": "DENY",
              "individual_approval null on high risk": "APPROVAL"}
    for label, d in weird:
        if len(c) >= 100:
            break
        c.append(("B7", label, d, expect.get(label, "DENY")))
    B = lambda ch: mut(copy.deepcopy(BASE), ch)
    extra = [
        ("reservation_expires_ns=true", B({"facts.execution.reservation_expires_ns": True})),
        ("reservation_expires_ns=null", B({"facts.execution.reservation_expires_ns": None})),
        ("limits.max_calls=null", B({"facts.approval.limits.max_calls": None})),
        ("approval valid_until string", B({"facts.approval.valid_until_ns": "1900000000000000000"})),
        ("token valid window inverted", B({"facts.auth.valid_from_ns": T1, "facts.auth.valid_until_ns": T0})),
        ("status lowercase approved", B({"facts.approval.status": "approved"})),
        ("auth mode LOCAL uppercase", B({"facts.auth": {"mode": "LOCAL", "verified": True}})),
        ("argument key lookalike", B({"request.arguments": {"раth": "file-1"}, "facts.parameters.canonical_arguments": {"раth": "file-1"}})),
        ("revocation flag null", B({"facts.revocation.server": None})),
        ("environment prod-eq null", B({"facts.environment.production_equivalent": None})),
        ("baseline verified string", B({"facts.baseline.verified": "true"})),
        ("scalar allowed_values string", B({"facts.approval.parameter_bindings": [{"argument_path": ["path"], "target_type": "scalar", "allowed_values": "file-1"}], "request.targets.files": [], "facts.parameters.derived_targets.files": []})),
        ("feature_type missing", B({"request.feature_type": None})),
        ("duplicate_status CLEAR uppercase", B({"facts.execution.duplicate_status": "CLEAR"})),
    ]
    for label, d in extra:
        if len(c) >= 100:
            break
        c.append(("B8", label, d, "DENY"))
    assert len(c) == 100, len(c)
    return c


def run_normal():
    cases = normal_cases()
    assert len(cases) == 200, len(cases)
    fails, t = [], time.time()
    for name, doc, eff, ids in cases:
        st, res = decide(doc)
        if st != 200 or res != {"effect": eff, "policy_ids": ids}:
            fails.append((name, st, res, eff, ids))
    by = {}
    for _, _, eff, _ in cases:
        by[eff] = by.get(eff, 0) + 1
    print(f"NORMAL {200 - len(fails)}/200 passed  {by}  {time.time() - t:.1f}s")
    for f in fails:
        print("  FAIL", f)
    return not fails


def run_bugs():
    cases = bug_cases()
    assert len(cases) == 100, len(cases)
    groups = {}
    for g, name, doc, want in cases:
        st, res = decide(doc)
        got = res.get("effect") if st == 200 and isinstance(res, dict) else f"HTTP{st}:{'undefined' if res is None else res}"
        ok = got == want
        groups.setdefault(g, [0, 0, []])
        groups[g][0 if ok else 1] += 1
        if not ok:
            groups[g][2].append(f"{name}: want {want}, got {got} {res.get('policy_ids') if isinstance(res, dict) else ''}")
    total_bad = sum(v[1] for v in groups.values())
    print(f"BUGS {100 - total_bad}/100 behaved as a fail-closed policy should; {total_bad} anomalies")
    for g in sorted(groups):
        ok, bad, notes = groups[g]
        print(f"  {g}: ok {ok}, anomaly {bad}")
        for n in notes:
            print("     -", n)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("normal", "all"):
        run_normal()
    if mode in ("bugs", "all"):
        run_bugs()
