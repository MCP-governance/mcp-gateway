"""엔드포인트 평면 에이전트.

이 프로세스는 통제하지 않는다. 오직 본다.

게이트웨이는 자기를 통과한 호출만 알고, 그것이 이 저장소가 반복해서 적어 온
한계다. 사람들의 PC에는 MCP 클라이언트 설정 파일이 있고, 거기 적힌 서버 목록이
"이 조직에서 실제로 쓰이는 MCP"의 모집단에 가장 가깝다. 그 목록과 Registry를
대조해야만 두 가지를 말할 수 있다.

  1. 등록되지 않은 서버가 쓰이고 있다            (강제 경로 밖의 경로)
  2. 폐기한 서버가 아직 설정에 남아 있다          (회수되지 않은 접근 경로)

두 번째가 종료 판정의 C1(모집단)에 직접 들어간다. 관리대장에서 지운 것과 사람들의
PC에서 사라진 것은 다른 사건이고, 종료를 진술하려면 뒤쪽이 필요하다.

왜 통제하지 않는가: 엔드포인트에서 설정 파일을 고치거나 프로세스를 죽이는 권한을
이 에이전트에 주면, 에이전트가 침해당했을 때 조직의 모든 개발 환경을 조작할 수
있는 경로가 된다. 관측만 하는 프로세스는 침해당해도 거짓 인벤토리를 올리는 것이
최대치이고, 그 거짓은 판정을 보수적인 쪽으로만 민다. 조치는 사람이 한다.

읽기 전용 원칙: 설정 파일은 읽기 전용으로 마운트되고, 이 스크립트에는 쓰기 경로가
없다. 파일 내용 전체를 보내지도 않는다 — 서버 이름·전송·주소만 보낸다. 사람들의
API 키가 인벤토리 테이블에 쌓이면 그 테이블이 조직에서 가장 위험한 표가 된다.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENT_VERSION = "1.0.0"

GATEWAY_URL = os.getenv("ENDPOINT_GATEWAY_URL", "http://gateway:8080")
LOGIN_URL = os.getenv("ENDPOINT_LOGIN_URL", GATEWAY_URL + "/api/session")
EMAIL = os.getenv("ENDPOINT_AGENT_EMAIL", "admin@bob.local")
PASSWORD = os.getenv("MOCK_SSO_PASSWORD", "test-password")
OWNER_TOKEN = os.getenv("ENDPOINT_OWNER_TOKEN", "")
ENDPOINT_ID = os.getenv("ENDPOINT_ID", "")
INTERVAL = int(os.getenv("ENDPOINT_REPORT_SECONDS", "60"))
ONE_SHOT = os.getenv("ENDPOINT_ONE_SHOT", "0") not in ("0", "false", "")

# 관측 대상 경로. 콜론이 아니라 os.pathsep로 나누는 이유는 이 스크립트가 컨테이너
# 안에서도 개발자 PC에서도 같은 방식으로 돌아야 하기 때문이다.
SCAN_PATHS = [
    Path(item) for item in
    os.getenv("ENDPOINT_CONFIG_PATHS", "/endpoint-configs").split(os.pathsep) if item.strip()
]

# MCP 클라이언트마다 파일 이름이 다르다. 목록을 좁게 잡으면 못 보고, 넓게 잡으면
# 아무 JSON이나 MCP 설정으로 읽는다. 이름으로 후보를 고르고 내용으로 확정한다.
CONFIG_NAMES = {
    "claude_desktop_config.json",
    "claude_config.json",
    ".mcp.json",
    "mcp.json",
    "mcp_settings.json",
    "cline_mcp_settings.json",
    "settings.json",
}

# 설정 파일이 서버 목록을 담는 키. 제품마다 다르고, 중첩된 경우도 있다.
SERVER_KEYS = ("mcpServers", "mcp_servers", "servers", "mcp")


def log(message: str) -> None:
    print(f"[endpoint-agent] {message}", flush=True)


def endpoint_id() -> str:
    """이 엔드포인트의 안정적인 식별자.

    무작위로 만들면 재시작할 때마다 새 엔드포인트가 되고, 그러면 '지금 남아 있는
    잔존 설정 수'가 영원히 줄지 않는다. 호스트 이름을 쓰되 운영자가 덮어쓸 수 있게 둔다.
    """
    return ENDPOINT_ID or f"endpoint-{socket.gethostname()}".lower()[:120]


def candidate_files() -> list[Path]:
    found: list[Path] = []
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            continue
        for path in sorted(root.rglob("*.json")):
            # 깊게 파고들면 node_modules 같은 곳의 JSON을 전부 읽게 된다.
            if len(path.relative_to(root).parts) > 4:
                continue
            if path.name in CONFIG_NAMES or path.parent.name in {".cursor", ".vscode", ".claude"}:
                found.append(path)
    return found


def server_entries(document: dict) -> dict:
    for key in SERVER_KEYS:
        value = document.get(key)
        if isinstance(value, dict) and value:
            # {"mcp": {"servers": {...}}} 형태도 받는다.
            if key == "mcp" and isinstance(value.get("servers"), dict):
                return value["servers"]
            if all(isinstance(item, dict) for item in value.values()):
                return value
    return {}


def describe(name: str, config: dict) -> dict | None:
    """설정 한 항목을 보고 가능한 형태로 줄인다.

    env와 headers는 의도적으로 버린다. 거기에 토큰이 들어 있고, 관측 목적에는
    필요 없다. 필요한 것은 "어느 서버를 가리키는가"뿐이다.
    """
    url = config.get("url") or config.get("endpoint") or config.get("serverUrl")
    if url:
        transport = str(config.get("type") or config.get("transport") or "streamable-http")
        return {"server_label": name, "transport": transport, "endpoint_ref": str(url)}
    command = config.get("command")
    if command:
        args = config.get("args") or []
        if not isinstance(args, list):
            args = [str(args)]
        return {
            "server_label": name,
            "transport": "stdio",
            "endpoint_ref": " ".join([str(command), *[str(item) for item in args]]),
        }
    return None


def collect() -> list[dict]:
    entries: list[dict] = []
    for path in candidate_files():
        try:
            document = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError):
            continue
        if not isinstance(document, dict):
            continue
        for name, config in server_entries(document).items():
            if not isinstance(config, dict):
                continue
            described = describe(str(name), config)
            if described:
                entries.append({"config_path": str(path), **described})
    return entries


def post(url: str, body: dict, token: str | None = None) -> dict:
    payload = json.dumps(body).encode()
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("content-type", "application/json")
    if token:
        request.add_header("authorization", "Bearer " + token)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read() or b"{}")


def sign_in() -> str:
    """합성 IdP에 로그인해 토큰을 받는다.

    한계를 분명히 적는다. 실습에서는 에이전트가 관리자 계정으로 로그인한다.
    운영에서는 엔드포인트마다 별도 자격(디바이스 인증서 또는 워크로드 신원)이어야
    하고, 그 자격은 인벤토리 보고 외에 아무것도 할 수 없어야 한다. 지금 구성은
    에이전트가 침해되면 관리자 API 전체가 노출된다 — 이 실습에서만 허용되는 절충이다.
    """
    data = post(LOGIN_URL, {"email": EMAIL, "password": PASSWORD})
    return data["access_token"]


def report_once(token: str) -> dict:
    entries = collect()
    body = {"endpoint_id": endpoint_id(), "entries": entries}
    return post(GATEWAY_URL + "/api/endpoint/inventory", body, token)


def enroll(token: str) -> None:
    post(GATEWAY_URL + "/api/endpoint/enroll", {
        "endpoint_id": endpoint_id(),
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}"[:80],
        "agent_version": AGENT_VERSION,
        "owner_token": OWNER_TOKEN or None,
        "detail": {"scan_paths": [str(path) for path in SCAN_PATHS]},
    }, token)


def main() -> int:
    log(f"엔드포인트 {endpoint_id()} · 관측 경로 {[str(p) for p in SCAN_PATHS]}")
    token = None
    while True:
        try:
            if token is None:
                token = sign_in()
                enroll(token)
                log("등록 완료")
            result = report_once(token)
            counts = result.get("counts", {})
            log("보고 %d건 · 등록 %d · 섀도 %d · 폐기 잔존 %d · 사라진 항목 %d" % (
                result.get("accepted", 0), counts.get("registered", 0),
                counts.get("shadow", 0), counts.get("retired-residue", 0),
                result.get("removed", 0)))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                # 토큰 만료나 계정 정지. 다시 로그인해 보고, 계정이 정지된 것이면
                # 다음 회전에서도 같은 오류가 나고 그것이 정상이다.
                token = None
            log("보고 실패(HTTP %s): %s" % (exc.code, exc.read()[:200].decode("utf-8", "replace")))
        except Exception as exc:
            log("보고 실패: %s" % exc)
        if ONE_SHOT:
            return 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
