"""Record the scope review of tools on an existing Console registration, through the Console API.

A registration made before every tool carried a scope serves only the tools that have one. This reads the
registration, then posts the reviewer's purpose, asset and outside hosts for the tools that lack a review.
The reviewer must be an administrator other than the person who asked for the server.

  python3 tool_scope_review.py --console https://gateway.example --server-id notes \
      --purpose "공개 노트 검색·읽기" --asset "notes" [--destinations host1,host2] [--tools search,read] < identity.json

identity.json: {"email": "...", "password": "..."}   Prints the API answer as one JSON line. stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def call(base: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    request = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"content-type": "application/json", **({"authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode(errors='replace')[:400]}") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--console", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--destinations", default="", help="outside hosts the tools may reach, comma separated; empty means none")
    parser.add_argument("--tools", default="", help="only these tools; default: every approved tool without a review")
    args = parser.parse_args()
    base = args.console.rstrip("/")
    token = call(base, "POST", "/auth/mock-login", body=json.load(sys.stdin))["access_token"]
    registration = call(base, "GET", "/gw/registry", token)["registrations"].get(args.server_id)
    if not registration:
        raise SystemExit(f"{args.server_id}: not a Console registration")
    pending = [t for t in registration["tools"] if t not in (registration.get("tool_reviews") or {})]
    names = [t.strip() for t in args.tools.split(",") if t.strip()] or pending
    hosts = [h.strip() for h in args.destinations.split(",") if h.strip()]
    if not names:
        print(json.dumps({"server_id": args.server_id, "reviewed": [], "unreviewed": []}))
        return
    reviews = {name: {"purpose": args.purpose, "asset": args.asset, "destinations": hosts} for name in names}
    print(json.dumps(call(base, "POST", f"/gw/registry/servers/{args.server_id}/tool-reviews", token, {"reviews": reviews}), ensure_ascii=False))


if __name__ == "__main__":
    main()
