"""Register a provider-hosted MCP server the D-57 way, through the Console API.

request (requester) -> contract review -> approval (approver, never the requester) -> activation.
There is no other way in: /api/registry/servers refuses a registration without an approved intake.

  python3 intake_register.py --console http://192.0.2.10:443 --endpoint https://mcp.context7.com/mcp \
      --server-id context7 --tools resolve-library-id=r,query-docs=r --data-class public --valid-days 30 \
      --allowed user --name "Context7" --parameter-constraints reviewed-scopes.json \
      --supplier-assurance supplier.json --impact-input impact.json < identities.json

identities.json: {"requester": {"email": "...", "password": "..."}, "approver": {"email": "...", "password": "..."}}
supplier.json: what the approver confirmed about the supplier (legal_entity, supplier_contact, security_contact,
  support_end YYYY-MM-DD, vulnerability_policy_url; optional subprocessors, sbom_submitted, vex_submitted,
  contract_basis_ref, exit_strategy). impact.json: the six impact answers (data_class, personal_data,
  external_transfer, permission, users, autonomy). Both are recorded as evidence, so they are never defaulted here.
Prints the registration result as one JSON line. stdlib only, so it runs on a bare appliance host.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _call(base: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    request = urllib.request.Request(base + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"content-type": "application/json", **({"authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode(errors='replace')[:400]}") from None


def login(base: str, identity: dict) -> str:
    return _call(base, "POST", "/auth/mock-login", body=identity)["access_token"]


def register(base: str, requester: str, approver: str, *, endpoint: str, server_id: str, name: str,
             tools: dict[str, str], data_class: str, valid_days: int, allowed: list[str], purpose: str,
             review_note: str, risk_acceptance: str, parameter_constraints: dict, supplier_assurance: dict,
             impact_input: dict, ack_warnings: bool = False, tool_reviews: dict | None = None) -> dict:
    if set(parameter_constraints) != set(tools):
        raise ValueError("Every selected tool needs an explicitly reviewed parameter constraint")
    found = _call(base, "POST", "/gw/registry/discover", approver, {"endpoint": endpoint})
    advertised = {tool["name"]: tool for tool in found["tools"]}
    missing = sorted(set(tools) - set(advertised))
    if missing:
        raise SystemExit(f"{endpoint} does not advertise: {', '.join(missing)}")
    flagged = {name: advertised[name]["warnings"] for name in tools if advertised[name]["warnings"]}
    if flagged and not ack_warnings:
        raise SystemExit(f"selected tools carry description warnings, read them and pass --ack-warnings: {flagged}")
    request = _call(base, "POST", "/api/mcp-requests", requester, {
        "display_name": name, "intake_kind": "remote-endpoint", "endpoint_url": endpoint,
        # The intake API asks which advertised tools the requester needs (same as the one-click screen).
        "requested_tools": sorted(tools),
        "requested_transport": "streamable-http", "purpose": purpose, "risk_input": impact_input})["request"]
    # Every approved tool carries a person's scope: why, on which asset, reaching which outside hosts.
    reviews = tool_reviews or {name: {"purpose": purpose[:200], "asset": endpoint.split("/")[2], "destinations": []}
                               for name in tools}
    scope = {"server_id": server_id, "endpoint": endpoint, "catalog_hash": found["catalog_hash"], "tools": tools,
             "data_class": data_class, "valid_days": valid_days, "poisoning_ack": bool(flagged), "tool_reviews": reviews}
    _call(base, "POST", f"/api/mcp-requests/{request['id']}/review-contract", approver,
          {**scope, "allowed_principals": allowed, "review_note": review_note,
           "parameter_constraints": parameter_constraints})
    _call(base, "POST", f"/api/mcp-requests/{request['id']}/approve", approver,
          {**supplier_assurance, "risk_acceptance": risk_acceptance})
    result = _call(base, "POST", f"/api/mcp-requests/{request['id']}/register", approver, scope)
    return {"intake_id": request["id"], "server_id": server_id, "status": result.get("status"),
            "tools": tools, "valid_until": result.get("valid_until"), "warnings_acknowledged": flagged or None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--console", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--parameter-constraints", required=True, type=argparse.FileType('r'),
                        help="Reviewed per-tool JSON schemas; no automatic unconstrained approval")
    parser.add_argument("--supplier-assurance", required=True, type=argparse.FileType('r'),
                        help="JSON of the supplier evidence the approver confirmed; recorded with the approval")
    parser.add_argument("--impact-input", required=True, type=argparse.FileType('r'),
                        help="JSON of the six impact answers; decides the risk tier and the approval method")
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--tools", required=True, help="name=r|w|x,...")
    parser.add_argument("--data-class", default="important", choices=["public", "nonimportant", "important"])
    parser.add_argument("--valid-days", type=int, default=30)
    parser.add_argument("--allowed", required=True, help="login ids or principal tokens, comma separated")
    parser.add_argument("--purpose", default="공급자 호스팅 MCP의 승인한 읽기 도구만 Gateway를 거쳐 사용합니다.")
    parser.add_argument("--review-note", default="실제 광고 도구 계약(설명·입력 스키마 해시)과 사용 주체·기한을 검토했습니다.")
    parser.add_argument("--risk", default="구현 소스 검사 없이 공급자 운영 서비스의 승인 도구만 사용하는 위험을 수용합니다.")
    parser.add_argument("--ack-warnings", action="store_true")
    args = parser.parse_args()
    identities = json.load(sys.stdin)
    base = args.console.rstrip("/")
    tools = dict(item.split("=", 1) for item in args.tools.split(","))
    result = register(base, login(base, identities["requester"]), login(base, identities["approver"]),
                      endpoint=args.endpoint, server_id=args.server_id, name=args.name, tools=tools,
                      data_class=args.data_class, valid_days=args.valid_days,
                      allowed=[p.strip() for p in args.allowed.split(",") if p.strip()], purpose=args.purpose,
                      review_note=args.review_note, risk_acceptance=args.risk,
                      parameter_constraints=json.load(args.parameter_constraints), ack_warnings=args.ack_warnings,
                      supplier_assurance=json.load(args.supplier_assurance), impact_input=json.load(args.impact_input))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
