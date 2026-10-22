#!/usr/bin/env python3
"""MINT가 승인·운영 중인 서버 목록으로 LiteLLM `mcp_servers` YAML을 만든다 (업스트림 방식, D-191).

    MINT_ADMIN_TOKEN=<콘솔 로그인 토큰> python gen_mcp_servers.py --gateway https://console.corp --api-prefix /gw --base-url https://gateway.corp > mcp_servers.yaml
    python gen_mcp_servers.py --registry-file registry.json --base-url http://edge-proxy:8081 > mcp_servers.yaml

LiteLLM은 서버마다 `oauth_delegate`로 등록되어 직원이 보낸 MINT 토큰을 그대로 MINT에 전달한다. 공유 서비스 키를 넣지 않는다.
표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.request

NOT_SERVING = {"DISABLED", "BLOCKED_SUPPLY_CHAIN"}
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def serving(servers: list[dict]) -> list[str]:
    """운영 중인 서버 ID. 상태를 알 수 없는 항목은 목록에서 뺀다(모르면 노출하지 않는다)."""
    return sorted(row["id"] for row in servers
                  if ID.fullmatch(str(row.get("id", ""))) and row.get("status") not in NOT_SERVING | {None}
                  and (row.get("lifecycle") or "OPERATING") == "OPERATING")


def alias(server_id: str) -> str:
    # LiteLLM은 직원 헤더 x-mcp-<별칭>-authorization을 첫 '-'로 나눠 읽어서 별칭에 '-'를 쓰지 못한다.
    return server_id.replace("-", "_")


def render(server_ids: list[str], base_url: str) -> str:
    base = base_url.rstrip("/")
    lines = ["mcp_servers:"]
    for sid in server_ids:
        lines += [f"  {alias(sid)}:", f"    url: {base}/mcp/{sid}/", "    transport: http",
                  "    auth_type: oauth_delegate",
                  "    extra_headers: [x-agent-task-id, x-workstation-id, traceparent]"]
    lines.append("# 직원 헤더: " + ", ".join(f"x-mcp-{alias(sid)}-authorization: Bearer <본인 MINT 토큰>" for sid in server_ids))
    return "\n".join(lines) + "\n"


def load(args) -> list[dict]:
    if args.registry_file:
        with open(args.registry_file, encoding="utf-8") as handle:
            return json.load(handle)["servers"]
    token = os.environ.get("MINT_ADMIN_TOKEN")
    if not (args.gateway and token):
        sys.exit("--registry-file 또는 (--gateway 와 환경 변수 MINT_ADMIN_TOKEN)이 필요합니다.")
    request = urllib.request.Request(args.gateway.rstrip("/") + args.api_prefix + "/registry", headers={"Authorization": f"Bearer {token}"})
    context = ssl.create_default_context(cafile=args.ca_file) if args.ca_file else None
    try:
        with urllib.request.urlopen(request, timeout=15, context=context) as response:
            return json.load(response)["servers"]
    except OSError as exc:  # HTTPError 포함
        sys.exit(f"MINT 서버 목록을 읽지 못했습니다: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gateway", help="MINT 관리 API 주소(콘솔 주소, 목록 조회용)")
    parser.add_argument("--api-prefix", default="/api", help="관리 API 경로 접두어(콘솔 주소로 읽으면 /gw)")
    parser.add_argument("--registry-file", help="GET /api/registry 응답을 저장한 JSON")
    parser.add_argument("--base-url", help="LiteLLM이 MINT에 접속하는 MCP 주소(기본: --gateway)")
    parser.add_argument("--ca-file", help="사설 CA 인증서(PEM)")
    args = parser.parse_args()
    base = args.base_url or args.gateway
    if not base:
        sys.exit("--base-url 또는 --gateway가 필요합니다.")
    ids = serving(load(args))
    if not ids:
        sys.exit("운영 중인 승인 서버가 없어 YAML을 만들지 않았습니다.")
    sys.stdout.write(render(ids, base))


if __name__ == "__main__":
    main()
