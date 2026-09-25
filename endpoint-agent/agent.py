"""엔드포인트 평면 에이전트.

이 프로세스는 통제하지 않는다. 오직 본다.

게이트웨이는 자기를 통과한 호출만 알고, 그것이 이 저장소가 반복해서 적어 온
한계다. 사람들의 PC에는 MCP 클라이언트 설정 파일이 있고, 거기 적힌 서버 목록이
"이 조직에서 실제로 쓰이는 MCP"의 모집단에 가장 가깝다. 그 목록과 Registry를
대조해야만 두 가지를 말할 수 있다.

  1. 등록되지 않은 서버가 쓰이고 있다            (강제 경로 밖의 경로)
  2. 폐기한 서버가 아직 설정에 남아 있다          (회수되지 않은 접근 경로)

두 번째가 종료 판정의 C1(모집단)에 직접 들어간다.

── 설정 대조만으로 부족한 이유 ──────────────────────────────────────────────

설정 파일은 "쓰겠다고 적어 둔 것"이다. 적지 않고 띄운 것은 거기 없다. 터미널에서
`npx some-mcp-server`를 직접 실행하거나, 팀 서버에 MCP를 하나 올려놓고 주소만
공유하면 설정 파일에는 아무 흔적이 없고 게이트웨이도 그 호출을 보지 못한다.

그래서 두 번째 관측 축이 있다. 이 에이전트는 자기가 도는 단말에서

  · 듣고 있는 소켓과 그 소켓을 가진 프로세스
  · 게이트웨이가 허용한 내부 대역의 TCP 응답
  · MCP initialize에 MCP로 답하는지 여부

를 확인해 올린다. 이 관측은 게이트웨이 장비에서 할 수 없다. 사원 PC의
루프백은 정의상 그 단말 안에만 있고, 내부 세그먼트는 NAT와 방화벽 뒤에 있다.
그 단말의 권한을 가진 프로세스만 답할 수 있는 질문이라 여기에 둔다.

── 통제하지 않는 이유 ────────────────────────────────────────────────────────

설정 파일을 고치거나 프로세스를 죽이는 권한을 이 에이전트에 주면, 에이전트가
침해당했을 때 조직의 모든 개발 환경을 조작할 수 있는 경로가 된다. 관측만 하는
프로세스는 침해당해도 거짓 인벤토리를 올리는 것이 최대치이고, 그 거짓은 판정을
보수적인 쪽으로만 민다. 조치는 사람이 한다.

── 자격 ──────────────────────────────────────────────────────────────────────

관리자 계정으로 로그인하지 않는다. 장치 키 하나만 갖고, 그 키로 할 수 있는 일은
보고 두 가지뿐이다. 키가 새도 관리자 API는 열리지 않는다.

── 탐색 범위 ────────────────────────────────────────────────────────────────

이 에이전트는 스캔 대역을 스스로 고르지 않는다. 게이트웨이의 탐색 정책이 정하고
여기서는 받아서 따른다. 정책이 꺼져 있으면 망 탐색을 하지 않고, 대역이 비어
있으면 루프백만 본다. 루프백은 이 단말 자신이므로 언제나 범위 안이다.
보내는 것은 MCP initialize 한 번뿐이고 그 밖의 어떤 요청도 만들지 않는다.
"""
from __future__ import annotations

import ipaddress
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AGENT_VERSION = "3.0.0"

def load_config() -> dict:
    if "--config" not in sys.argv:
        return {}
    position = sys.argv.index("--config")
    if len(sys.argv) <= position + 1:
        raise SystemExit("--config 뒤에 설정 파일 경로가 필요합니다.")
    try:
        config = json.loads(Path(sys.argv[position + 1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"엔드포인트 설정을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(config, dict):
        raise SystemExit("엔드포인트 설정은 JSON 객체여야 합니다.")
    return config


CONFIG = load_config()


def setting(name: str, default: str) -> str:
    return str(CONFIG.get(name, os.getenv(name, default)))


GATEWAY_URL = setting("ENDPOINT_GATEWAY_URL", "http://gateway:8080").rstrip("/")
DEVICE_KEY = setting("ENDPOINT_DEVICE_KEY", "")
ENDPOINT_ID = setting("ENDPOINT_ID", "")
INTERVAL = int(setting("ENDPOINT_REPORT_SECONDS", "60"))
ONE_SHOT = "--once" in sys.argv or setting("ENDPOINT_ONE_SHOT", "0") not in ("0", "false", "")
SCAN_ENABLED = setting("ENDPOINT_NETSCAN", "1") not in ("0", "false", "")

SCAN_PATHS = [
    Path(item) for item in
    setting("ENDPOINT_CONFIG_PATHS", "/endpoint-configs").split(os.pathsep) if item.strip()
]

CONFIG_NAMES = {
    "claude_desktop_config.json",
    "claude_config.json",
    ".claude.json",          # Claude Code: user scope + projects.<dir>.mcpServers
    "managed-mcp.json",      # Claude Code: /etc/claude-code (IT-managed)
    ".mcp.json",
    "mcp.json",
    "mcp_settings.json",
    "cline_mcp_settings.json",
    "settings.json",         # Gemini CLI ~/.gemini, /etc/gemini-cli; VS Code
    "mcp_config.json",       # Antigravity
    "opencode.json",
    "config.toml",           # Codex ~/.codex
    "managed_config.toml",   # Codex /etc/codex (IT-managed)
}

SERVER_KEYS = ("mcpServers", "mcp_servers", "servers", "mcp")

# 프로세스 명령줄에서 MCP 서버를 알아보는 표지. 좁게 잡으면 못 보고 넓게 잡으면
# 모든 node 프로세스가 MCP가 된다. 확정이 아니라 'suspected'로만 올리고, 확정은
# initialize 응답이 한다.
PROCESS_MARKERS = re.compile(
    r"(@modelcontextprotocol/|mcp[-_]server|server[-_]mcp|mcp\.server|fastmcp|"
    r"uvx\s+mcp|npx\s+.*mcp|modelcontextprotocol)",
    re.IGNORECASE,
)

# MCP 경로 후보. 순서는 흔한 것부터다. 실패한 후보에 재시도하지 않는다.
MCP_PATHS = ("/mcp/", "/mcp", "/")

PROBE_TIMEOUT = float(os.getenv("ENDPOINT_PROBE_TIMEOUT", "1.5"))


def log(message: str) -> None:
    print(f"[endpoint-agent] {message}", flush=True)


def endpoint_id() -> str:
    """이 엔드포인트의 안정적인 식별자.

    무작위로 만들면 재시작할 때마다 새 엔드포인트가 되고, 그러면 '지금 남아 있는
    잔존 설정 수'가 영원히 줄지 않는다.
    """
    return ENDPOINT_ID or f"endpoint-{socket.gethostname()}".lower()[:120]


def command_digest(value: str) -> str:
    """Compare commands exactly without sending arguments that may contain secrets."""
    return "sha256:" + hashlib.sha256(" ".join(value.split()).encode()).hexdigest()


# ── 설정 파일 관측 ───────────────────────────────────────────────────────────

def candidate_files() -> list[Path]:
    found: list[Path] = []
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            continue
        for path in sorted([*root.rglob("*.json"), *root.rglob("*.toml")]):
            # 깊게 파고들면 node_modules 같은 곳의 JSON을 전부 읽게 된다.
            if len(path.relative_to(root).parts) > 4 or "node_modules" in path.parts:
                continue
            if path.suffix == ".toml" and path.name == "config.toml" and path.parent.name != ".codex":
                continue
            if path.name in CONFIG_NAMES or path.parent.name in {".cursor", ".vscode", ".claude"}:
                found.append(path)
    return found


def server_entries(document: dict) -> dict:
    for key in SERVER_KEYS:
        value = document.get(key)
        if isinstance(value, dict) and value:
            if key == "mcp" and isinstance(value.get("servers"), dict):
                return value["servers"]
            if all(isinstance(item, dict) for item in value.values()):
                return value
    return {}


def all_server_entries(document: dict) -> dict:
    """Top-level servers plus Claude Code's per-project ones in ~/.claude.json
    (`projects.<dir>.mcpServers`), which is where `claude mcp add` writes by default."""
    entries = dict(server_entries(document))
    projects = document.get("projects")
    if isinstance(projects, dict):
        for directory, project in projects.items():
            if isinstance(project, dict):
                for name, config in server_entries(project).items():
                    entries[f"{name}@{directory}"] = config
    return entries


def read_config(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8") or "{}"
    if path.suffix == ".toml":
        import tomllib
        document = tomllib.loads(text)
    else:
        document = json.loads(text)
    return document if isinstance(document, dict) else None


def describe(name: str, config: dict) -> dict | None:
    """설정 한 항목을 보고 가능한 형태로 줄인다.

    env와 headers는 의도적으로 버린다. 거기에 토큰이 들어 있고, 관측 목적에는
    필요 없다. 필요한 것은 "어느 서버를 가리키는가"뿐이다.
    """
    url = config.get("url") or config.get("endpoint") or config.get("serverUrl") or config.get("httpUrl")
    if url:
        transport = str(config.get("type") or config.get("transport") or "streamable-http")
        return {"server_label": name, "transport": transport, "endpoint_ref": str(url)}
    command = config.get("command")
    if command:
        args = config.get("args") or []
        if not isinstance(args, list):
            args = [str(args)]
        if isinstance(command, list):  # OpenCode: "command": ["npx", "-y", "server"]
            command, args = (command or [""])[0], [*command[1:], *args]
        return {
            "server_label": name,
            "transport": "stdio",
            "endpoint_ref": command_digest(" ".join([str(command), *[str(item) for item in args]])),
        }
    return None


def collect_configs() -> list[dict]:
    entries: list[dict] = []
    for path in candidate_files():
        try:
            document = read_config(path)
        except (OSError, ValueError, ImportError):  # TOMLDecodeError is a ValueError; no tomllib before 3.11
            continue
        if document is None:
            continue
        for name, config in all_server_entries(document).items():
            if not isinstance(config, dict):
                continue
            described = describe(str(name), config)
            if described:
                entries.append({"config_path": str(path), **described})
    return entries


# ── 로컬 소켓 관측 (이 단말의 권한이라야 보이는 것) ──────────────────────────
#
# 게이트웨이 장비에서는 답할 수 없는 질문이 여기 있다. 어떤 프로세스가 그 포트를
# 갖고 있는가는 그 단말 안에서만 보이고, 루프백은 정의상 밖에서 닿지 않는다.

def _run(command: list[str], timeout: int = 10) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              check=False)
        return done.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _linux_listeners() -> list[dict]:
    """/proc에서 LISTEN 소켓과 소유 프로세스를 읽는다.

    ss나 netstat에 의존하지 않는 이유는 최소 컨테이너 이미지에 둘 다 없는 경우가
    흔하고, 그때 조용히 빈 목록을 올리면 "미등록 리스너 0건"이 된다. 없는 것과
    못 본 것은 다르다.
    """
    inode_to_socket: dict[str, tuple[str, int]] = {}
    for name, size in (("tcp", 4), ("tcp6", 16)):
        try:
            lines = Path(f"/proc/net/{name}").read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 10 or parts[3] != "0A":  # 0A = TCP_LISTEN
                continue
            raw_address, raw_port = parts[1].split(":")
            port = int(raw_port, 16)
            try:
                packed = bytes.fromhex(raw_address)
                if size == 4:
                    address = str(ipaddress.ip_address(packed[::-1]))
                else:
                    # /proc은 32비트 워드 단위 리틀엔디언으로 적는다.
                    words = [packed[i:i + 4][::-1] for i in range(0, 16, 4)]
                    address = str(ipaddress.ip_address(b"".join(words)))
            except (ValueError, IndexError):
                continue
            inode_to_socket[parts[9]] = (address, port)
    if not inode_to_socket:
        return []

    owners: dict[str, tuple[str, str]] = {}
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        try:
            fds = list((pid_dir / "fd").iterdir())
        except OSError:
            continue  # 다른 사용자의 프로세스. 권한이 없으면 소유자는 비운다.
        try:
            raw = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except OSError:
            raw = ""
        name = raw.split(" ")[0].rsplit("/", 1)[-1][:120]
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:["):
                owners[target[8:-1]] = (name, raw.strip()[:600])

    found = []
    for inode, (address, port) in inode_to_socket.items():
        name, command = owners.get(inode, ("", ""))
        found.append({"address": address, "port": port,
                      "process_name": name, "command_line": command})
    return found


def _windows_listeners() -> list[dict]:
    rows = []
    pid_names: dict[str, str] = {}
    for line in _run(["tasklist", "/FO", "CSV", "/NH"]).splitlines():
        cells = [cell.strip('"') for cell in line.split('","')]
        if len(cells) >= 2:
            pid_names[cells[1].strip('"')] = cells[0].strip('"')
    for line in _run(["netstat", "-ano", "-p", "TCP"]).splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        address, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        pid = parts[4]
        rows.append({"address": address.strip("[]") or "0.0.0.0", "port": int(port),
                     "process_name": pid_names.get(pid, ""), "command_line": ""})
    return rows


def _bsd_listeners() -> list[dict]:
    rows = []
    for line in _run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]).splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        local = parts[8]
        address, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        rows.append({"address": address.strip("[]") or "0.0.0.0", "port": int(port),
                     "process_name": parts[0][:120], "command_line": ""})
    return rows


def local_listeners() -> list[dict]:
    system = platform.system()
    if system == "Linux":
        rows = _linux_listeners()
    elif system == "Windows":
        rows = _windows_listeners()
    else:
        rows = _bsd_listeners()
    seen = set()
    unique = []
    for row in rows:
        key = (row["address"], row["port"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def stdio_processes() -> list[dict]:
    """설정에 없이 직접 실행된 stdio MCP 서버.

    포트를 열지 않으므로 어떤 망 스캔으로도 보이지 않는다. 이것도 강제 경로 밖의
    경로이고, 단말에서만 보인다.
    """
    found = []
    if platform.system() != "Linux":
        output = _run(["ps", "-eo", "pid=,comm=,args="]) if platform.system() != "Windows" else ""
        for line in output.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 3 or not PROCESS_MARKERS.search(parts[2]):
                continue
            found.append({"source": "stdio-process", "address": "local-process", "port": None,
                          "process_name": parts[1][:120], "command_line": command_digest(parts[2]),
                          "mcp_evidence": "suspected"})
        return found
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        try:
            raw = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        if not raw or not PROCESS_MARKERS.search(raw):
            continue
        found.append({"source": "stdio-process", "address": "local-process", "port": None,
                      "process_name": raw.split(" ")[0].rsplit("/", 1)[-1][:120],
                      "command_line": command_digest(raw), "mcp_evidence": "suspected"})
    return found


# ── MCP 확인 ────────────────────────────────────────────────────────────────
#
# 열려 있는 포트와 MCP 서버는 다르다. 구분하지 않으면 사무실 프린터가 섀도 MCP로
# 올라가고, 그런 목록은 아무도 보지 않게 된다.

INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "mcp-governance-endpoint-agent", "version": AGENT_VERSION},
    },
}


def probe_mcp(address: str, port: int) -> dict | None:
    """MCP initialize 한 번만 보낸다. 그 밖의 어떤 요청도 만들지 않는다."""
    host = f"[{address}]" if ":" in address else address
    body = json.dumps(INITIALIZE).encode()
    for path in MCP_PATHS:
        url = f"http://{host}:{port}{path}"
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("content-type", "application/json")
        request.add_header("accept", "application/json, text/event-stream")
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=PROBE_TIMEOUT) as response:
                payload = response.read(20000).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read(20000).decode("utf-8", "replace")
            except Exception:
                continue
        except Exception:
            continue
        info = _parse_initialize(payload)
        if info:
            return {**info, "path": path}
    return None


def _parse_initialize(payload: str) -> dict | None:
    """JSON 본문과 SSE 프레임을 모두 읽는다."""
    chunks = [payload]
    for line in payload.splitlines():
        if line.startswith("data:"):
            chunks.append(line[5:].strip())
    for chunk in chunks:
        try:
            document = json.loads(chunk)
        except ValueError:
            continue
        if not isinstance(document, dict):
            continue
        result = document.get("result")
        if not isinstance(result, dict):
            continue
        server = result.get("serverInfo") or {}
        if "protocolVersion" in result or server:
            return {"server_name": str(server.get("name") or "")[:200],
                    "server_version": str(server.get("version") or "")[:80],
                    "protocol_version": str(result.get("protocolVersion") or "")[:40]}
    return None


def tcp_open(address: str, port: int, timeout: float) -> bool:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((address, port)) == 0
    except OSError:
        return False


# ── 망 탐색 ─────────────────────────────────────────────────────────────────

def scan_targets(policy: dict) -> list[str]:
    """게이트웨이가 허용한 대역만 펼친다.

    이 함수 밖에서 대상 주소가 만들어지는 경로는 없다. 대역이 비어 있으면
    루프백만 본다 — 루프백은 이 단말 자신이라 언제나 범위 안이다.
    """
    targets = ["127.0.0.1"]
    limit = int(policy.get("max_hosts") or 0)
    for entry in policy.get("allowed_cidrs") or []:
        try:
            network = ipaddress.ip_network(str(entry), strict=False)
        except ValueError:
            continue
        if not (network.is_private or network.is_loopback or network.is_link_local):
            # 게이트웨이가 잘못 내려줘도 공인 대역은 스캔하지 않는다. 범위 통제가
            # 한쪽에만 있으면 그 한쪽이 틀리는 날 통제가 없다.
            continue
        for address in network.hosts() if network.num_addresses > 2 else network:
            targets.append(str(address))
            if len(targets) >= limit:
                break
        if len(targets) >= limit:
            break
    seen, unique = set(), []
    for item in targets:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[:limit] if limit else unique[:1]


def network_findings(policy: dict) -> list[dict]:
    ports = [int(p) for p in (policy.get("ports") or []) if str(p).isdigit()]
    if not ports:
        return []
    timeout = float(policy.get("connect_timeout_ms") or 300) / 1000.0
    targets = scan_targets(policy)
    pairs = [(address, port) for address in targets for port in ports]
    findings: list[dict] = []
    # 워커 수를 고정한다. 저사양 단말에서 수천 개의 소켓을 동시에 열면 그 단말이
    # 느려지고, 그러면 사람이 에이전트를 꺼 버린다. 꺼진 관측은 0건을 보고한다.
    with ThreadPoolExecutor(max_workers=min(32, max(4, len(pairs)))) as pool:
        opened = list(pool.map(lambda pair: (pair, tcp_open(pair[0], pair[1], timeout)), pairs))
    live = [pair for pair, ok in opened if ok]
    if not policy.get("probe_mcp", True):
        return [{"source": "network", "address": address, "port": port,
                 "mcp_evidence": "unknown"} for address, port in live]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(live)))) as pool:
        probed = list(pool.map(lambda pair: (pair, probe_mcp(pair[0], pair[1])), live))
    for (address, port), info in probed:
        if info is None:
            continue  # MCP가 아닌 포트는 올리지 않는다. 자산대장이 아니라 MCP 관측이다.
        findings.append({"source": "network", "address": address, "port": port,
                         "mcp_evidence": "confirmed", **{k: v for k, v in info.items() if k != "path"}})
    return findings


def listener_findings(policy: dict) -> list[dict]:
    findings: list[dict] = []
    probe = bool(policy.get("probe_mcp", True))
    for row in local_listeners():
        marker = PROCESS_MARKERS.search(row.get("command_line") or row.get("process_name") or "")
        info = None
        if probe and row["address"] not in {"0.0.0.0", "::"}:
            info = probe_mcp(row["address"], row["port"])
        elif probe:
            info = probe_mcp("127.0.0.1", row["port"])
        if info:
            evidence = "confirmed"
        elif marker:
            evidence = "suspected"
        else:
            continue  # MCP 표지도 없고 initialize에도 답하지 않으면 MCP가 아니다.
        findings.append({"source": "local-socket", "address": row["address"], "port": row["port"],
                         "process_name": row.get("process_name", ""),
                         "command_line": command_digest(row.get("command_line", "")),
                         "mcp_evidence": evidence,
                         **{k: v for k, v in (info or {}).items() if k != "path"}})
    findings.extend(stdio_processes())
    return findings


# ── 게이트웨이 통신 ──────────────────────────────────────────────────────────

def call(method: str, path: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(GATEWAY_URL + path, data=payload, method=method)
    request.add_header("content-type", "application/json")
    request.add_header("x-endpoint-key", DEVICE_KEY)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=30) as response:
        return json.loads(response.read() or b"{}")


def enroll() -> None:
    call("POST", "/api/endpoint/enroll", {
        "endpoint_id": endpoint_id(),
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}"[:80],
        "agent_version": AGENT_VERSION,
        "detail": {"scan_paths": [str(path) for path in SCAN_PATHS],
                   "capabilities": ["config-inventory", "local-socket", "network", "stdio-process"]},
    })


def report_configs() -> dict:
    return call("POST", "/api/endpoint/inventory",
                {"endpoint_id": endpoint_id(), "entries": collect_configs()})


def report_listeners() -> dict | None:
    if not SCAN_ENABLED:
        return None
    try:
        policy = call("GET", "/api/endpoint/scan-policy")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            # 이 장치에 netscan 권한이 없다. 정상이다 — 관측 축은 선택이다.
            return None
        raise
    if not policy.get("enabled"):
        return None
    findings = listener_findings(policy) + network_findings(policy)
    return call("POST", "/api/endpoint/listeners",
                {"endpoint_id": endpoint_id(), "findings": findings[:500]})


def once() -> None:
    inventory = report_configs()
    counts = inventory.get("counts", {})
    log("설정 %d건 · 등록 %d · 섀도 %d · 폐기 잔존 %d · 사라진 항목 %d" % (
        inventory.get("accepted", 0), counts.get("registered", 0),
        counts.get("shadow", 0), counts.get("retired-residue", 0),
        inventory.get("removed", 0)))
    scan = report_listeners()
    if scan is None:
        log("망 탐색 없음 (권한 없음 또는 정책 꺼짐)")
        return
    counts = scan.get("counts", {})
    evidence = scan.get("evidence", {})
    log("리스너 %d건 · 등록 %d · 섀도 %d · 폐기 잔존 %d · MCP 확정 %d · 추정 %d" % (
        scan.get("accepted", 0), counts.get("registered", 0), counts.get("shadow", 0),
        counts.get("retired-residue", 0), evidence.get("confirmed", 0),
        evidence.get("suspected", 0)))


def main() -> int:
    if not DEVICE_KEY:
        log("ENDPOINT_DEVICE_KEY가 없습니다. 관리자가 발급한 장치 자격이 필요합니다.")
        return 2
    parsed = urlsplit(GATEWAY_URL)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {
        "gateway", "localhost", "127.0.0.1", "::1"}):
        log("원격 Gateway 주소는 HTTPS가 필요합니다. 로컬 터널만 HTTP를 허용합니다.")
        return 2
    log(f"엔드포인트 {endpoint_id()} · 관측 경로 {[str(p) for p in SCAN_PATHS]}")
    enrolled = False
    while True:
        try:
            if not enrolled:
                enroll()
                enrolled = True
                log("등록 완료")
            once()
            failed = False
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode("utf-8", "replace")
            if exc.code in (401, 403):
                # 자격이 폐기됐다. 다음 회전에서도 같은 오류가 나고 그것이 정상이다.
                enrolled = False
            log("보고 실패(HTTP %s): %s" % (exc.code, detail))
            failed = True
        except Exception as exc:
            log("보고 실패: %s" % exc)
            failed = True
        if ONE_SHOT:
            return 1 if failed else 0
        time.sleep(INTERVAL)


def demo() -> None:
    """의존성 없이 돌아가는 자체 점검. 분류 로직이 깨지면 여기서 먼저 걸린다."""
    assert command_digest("node  server.js --token secret") == command_digest("node server.js --token secret")
    assert "secret" not in command_digest("node server.js --token secret")
    assert PROCESS_MARKERS.search("node /app/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js")
    assert PROCESS_MARKERS.search("python -m mcp_server_time --local-timezone UTC")
    assert not PROCESS_MARKERS.search("/usr/bin/postgres -D /var/lib/postgresql/data")

    frame = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","serverInfo":{"name":"demo","version":"1.0.0"}}}\n'
    parsed = _parse_initialize(frame)
    assert parsed and parsed["server_name"] == "demo" and parsed["protocol_version"] == "2025-06-18"
    assert _parse_initialize('{"jsonrpc":"2.0","id":1,"error":{"code":-32000}}') is None
    assert _parse_initialize("<html>hello</html>") is None

    # 하네스마다 다른 설정 모양이 같은 형태로 줄어야 Registry와 대조된다.
    gemini = describe("fs", {"httpUrl": "http://gateway:8080/mcp/filesystem/", "headers": {"Authorization": "x"}})
    assert gemini == {"server_label": "fs", "transport": "streamable-http", "endpoint_ref": "http://gateway:8080/mcp/filesystem/"}
    opencode = describe("notes", {"type": "local", "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/n"]})
    assert opencode["transport"] == "stdio"
    assert opencode["endpoint_ref"] == command_digest("npx -y @modelcontextprotocol/server-filesystem /n")
    claude = all_server_entries({"mcpServers": {"a": {"url": "u"}},
                                 "projects": {"/w": {"mcpServers": {"b": {"command": "c"}}}}})
    assert set(claude) == {"a", "b@/w"}
    import tomllib
    codex = server_entries(tomllib.loads('[mcp_servers.git]\nurl = "http://gateway:8080/mcp/git/"\n'))
    assert describe("git", codex["git"])["endpoint_ref"].endswith("/mcp/git/")

    # 탐색 범위는 정책이 정하고, 공인 대역은 정책이 내려줘도 펼치지 않는다.
    assert scan_targets({"allowed_cidrs": [], "max_hosts": 8}) == ["127.0.0.1"]
    assert scan_targets({"allowed_cidrs": ["8.8.8.0/30"], "max_hosts": 8}) == ["127.0.0.1"]
    private = scan_targets({"allowed_cidrs": ["10.1.2.0/30"], "max_hosts": 8})
    assert "10.1.2.1" in private and "8.8.8.1" not in private
    assert len(scan_targets({"allowed_cidrs": ["10.0.0.0/20"], "max_hosts": 5})) == 5
    print("endpoint-agent self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        demo()
        raise SystemExit(0)
    sys.exit(main())
