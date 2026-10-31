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
import math
import os
import platform
import re
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AGENT_VERSION = "3.1.0"


def user_command_settings(home):
    """관리 계정 홈만 검사하며 명령 값과 파서 오류 본문은 반환하지 않는다."""
    import stat

    home = Path(home)
    found_by_file = {}
    if not home.is_absolute():
        return False, [{"file": "~", "keys": []}]
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    # POSIX: 각 단계를 앞 단계 핸들 기준·링크 비추적으로 연다. 검사 뒤 디렉터리를 링크로 바꿔도
    # root의 읽기가 홈 밖으로 나가지 않는다(S6 검토). Windows는 경로 검사라 교체 경쟁이 남는다.
    posix = os.open in os.supports_dir_fd and hasattr(os, "O_DIRECTORY")
    opened_fds = []

    def linked(info):
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)

    def report(file, keys=()):
        found_by_file.setdefault(file, set()).update(keys)

    def enter(parent, name):
        if posix:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=parent)
            except FileNotFoundError:
                return None
            opened_fds.append(fd)
            return fd
        path = parent / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if linked(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError
        return path

    def read(parent, name):
        flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
        if posix:
            fd = os.open(name, flags, dir_fd=parent)
            info = None
        else:
            info = (parent / name).lstat()
            if linked(info) or not stat.S_ISREG(info.st_mode):
                raise ValueError
            fd = os.open(parent / name, flags)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            # 하드 링크는 선택한 경로 밖의 inode다.
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or info is not None and (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                raise ValueError
            raw = source.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError
        return raw.decode("utf-8-sig")

    def invalid_constant(value):
        raise ValueError

    try:
        try:
            if posix:
                root = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
                opened_fds.append(root)
                current = root
                for part in home.parts[1:]:
                    current = enter(current, part)
                    if current is None:
                        raise ValueError
            else:
                for parent in (home, *home.parents):
                    info = parent.lstat()
                    if linked(info) or not stat.S_ISDIR(info.st_mode):
                        raise ValueError
                current = home
        except (OSError, ValueError):
            return False, [{"file": "~", "keys": []}]

        for folder, names, keys in (
                (".claude", ["settings.json", "settings.local.json"],
                 {"apiKeyHelper", "otelHeadersHelper", "awsCredentialExport", "awsAuthRefresh"}),
                (".codex", ["config.toml"], {"notify"})):
            try:
                directory = enter(current, folder)
                if directory is None:
                    continue
                entries = os.listdir(directory) if posix else [p.name for p in directory.iterdir()]
                if folder == ".codex":
                    # 프로필 파일 이름은 직원이 정하므로 보고에는 고정 표기만 쓴다(S6 검토).
                    if len(entries) > 4096:
                        raise ValueError
                    profiles = sorted(n for n in entries if n.lower().endswith(".config.toml"))
                    if len(profiles) > 120:
                        raise ValueError
                    names = names + profiles
            except (OSError, ValueError):
                report(folder)
                continue
            for name in names:
                label = f"{folder}/{name}" if name in {"settings.json", "settings.local.json", "config.toml"} else ".codex/*.config.toml"
                try:
                    text = read(directory, name)
                except FileNotFoundError:
                    continue
                except (OSError, ValueError):
                    report(label)
                    continue
                try:
                    if folder == ".claude":
                        document = json.loads(text, parse_constant=invalid_constant)
                    else:
                        document = toml_loads(text)
                    if not isinstance(document, dict):
                        raise ValueError
                    found = set(document) & keys
                    # Codex profiles live inside config.toml as well as *.config.toml.
                    if folder == ".codex":
                        profiles = document.get("profiles", {})
                        if not isinstance(profiles, dict) or any(not isinstance(p, dict) for p in profiles.values()):
                            raise ValueError
                        if any("notify" in p for p in profiles.values()):
                            found.add("notify")
                    if found:
                        report(label, found)
                except (ValueError, ImportError, RecursionError):
                    report(label)
    finally:
        for fd in opened_fds:
            os.close(fd)
    findings = [{"file": file, "keys": sorted(keys)} for file, keys in sorted(found_by_file.items())]
    return not findings, findings


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
ORIGIN = setting("ENDPOINT_ORIGIN", "manual" if ONE_SHOT else "automatic")
ORIGIN = ORIGIN if ORIGIN in ("automatic", "manual") else "manual"
SCAN_ENABLED = setting("ENDPOINT_NETSCAN", "1") not in ("0", "false", "")
PROCESS_ENABLED = setting("ENDPOINT_PROCESS_SCAN", "1" if SCAN_ENABLED else "0") not in ("0", "false", "")
PROCESS_UID = setting("ENDPOINT_PROCESS_UID", "")
PROCESS_SID = setting("ENDPOINT_PROCESS_SID", "")
SCAN_ERRORS: set[str] = set()

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
    r"uvx\s+mcp|npx\s+.*mcp|modelcontextprotocol|ida[-_]mcp|ghidra[-_]?mcp|obsidian[-_]mcp|bridge_mcp_ghidra|"
    r"@playwright/mcp|@bytebase/dbhub|blender[-_]mcp|mcp[-_]for[-_]blender)",
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


def safe_endpoint_ref(value: str) -> str:
    # URL userinfo/query/fragment may contain credentials; retain only an exact digest.
    try:
        parsed = urlsplit(value)
        if not (parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
            return value
    except ValueError:
        pass
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


# ── 증거 출처 ────────────────────────────────────────────────────────────────
#
# 보내기 직전 형태(projection)와 그 형태를 만든 원본의 해시를 같이 보낸다. 서버는 저장한
# 필드만으로 projection 해시를 다시 계산해 이 값과 대조한다. 두 구현이 같은 바이트를
# 만들어야 하므로 정규화 규칙은 endpoint_plane.canonical_sha256과 같다.

SECRET_KEYS = {"env", "headers", "http_headers", "env_http_headers", "bearer_token_env_var"}
INVENTORY_FIELDS = ("config_path", "server_label", "transport", "endpoint_ref")
LISTENER_FIELDS = ("source", "address", "port", "process_name", "command_line", "mcp_evidence",
                   "server_name", "server_version", "protocol_version")


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, default=str).encode()).hexdigest()


def canonical_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def projection(record: dict, fields: tuple) -> dict:
    return {key: record.get(key) if key == "port" else ("" if record.get(key) is None else record.get(key)) for key in fields}


def provenance(raw, shaped: dict, steps: list, collector: str) -> dict:
    return {"raw_sha256": canonical_sha256(raw), "projection_sha256": canonical_sha256(shaped),
            "transformations": steps[:8], "collector": collector}


def seal_os_event(event: dict, raw_text: str, collector: str, steps: list) -> dict:
    """Fix the event's time format and attach the hashes. The raw text is the journal line or
    event XML exactly as read; only its hash leaves the device."""
    observed = datetime.fromisoformat(str(event["observed_at"]).replace("Z", "+00:00"))
    event["observed_at"] = canonical_time(observed)
    event.setdefault("denial_class", "unknown")
    event["provenance"] = {
        "raw_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
        "projection_sha256": canonical_sha256({key: event[key] for key in ("event_id", "observed_at", "kind", "details", "denial_class")}),
        "transformations": steps, "collector": collector}
    return event


# ── 설정 파일 관측 ───────────────────────────────────────────────────────────

def candidate_files() -> list[Path]:
    found: list[Path] = []
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            continue
        try:
            candidates = sorted([*root.rglob("*.json"), *root.rglob("*.toml")])
        except OSError:
            SCAN_ERRORS.add("config_unreadable")
            continue
        for path in candidates:
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



def toml_loads(text):
    """tomllib (3.11+), else the distribution's tomli/toml package (Ubuntu 20.04·22.04 ship Python 3.8/3.10).
    The service runs with -I -S, so the root-owned system package folder is added for this import only."""
    try:
        import tomllib as parser
    except ImportError:
        import sys
        system = "/usr/lib/python3/dist-packages"
        added = system not in sys.path
        if added:
            sys.path.append(system)
        try:
            try:
                import tomli as parser
            except ImportError:
                import toml as parser
        finally:
            if added:
                sys.path.remove(system)
    return parser.loads(text)


def read_config(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8") or "{}"
    if path.suffix == ".toml":
        document = toml_loads(text)
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
        return {"server_label": name, "transport": transport, "endpoint_ref": safe_endpoint_ref(str(url))}
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


# The Codex desktop app writes its own computer-use runtimes (cua_repl, node_repl) into config.toml. They are part of the
# app, not an MCP server someone added, and the managed allow-list disables them like any other unlisted server.
VENDOR_BUNDLED = re.compile(r"/windowsapps/openai\.codex_[^/]+/|/openai/codex/runtimes/|/applications/codex\.app/")


def vendor_bundled(path: Path, config: dict) -> bool:
    command = config.get("command")
    if path.name != "config.toml" or path.parent.name != ".codex" or not isinstance(command, str):
        return False
    return bool(VENDOR_BUNDLED.search(command.replace("\\", "/").lower()))


def collect_configs() -> list[dict]:
    entries: list[dict] = []
    for path in candidate_files():
        try:
            document = read_config(path)
        except (OSError, ValueError, ImportError):  # TOMLDecodeError is a ValueError; no tomllib before 3.11
            SCAN_ERRORS.add("config_unreadable")
            continue
        if document is None:
            SCAN_ERRORS.add("config_unreadable")
            continue
        for name, config in all_server_entries(document).items():
            if not isinstance(config, dict) or vendor_bundled(path, config):
                continue
            described = describe(str(name), config)
            if described:
                entry = {"config_path": str(path), **described}
                steps = (["drop_env_headers"] if SECRET_KEYS & config.keys() else []) + (
                    ["command_sha256"] if described["transport"] == "stdio"
                    else ["url_sha256"] if described["endpoint_ref"].startswith("sha256:") else [])
                raw = {"config_path": str(path), "name": str(name),
                       "config": {key: value for key, value in config.items() if key not in SECRET_KEYS}}
                entry["provenance"] = provenance(raw, projection(entry, INVENTORY_FIELDS), steps, "config-file")
                entries.append(entry)
    return entries


# ── 로컬 소켓 관측 (이 단말의 권한이라야 보이는 것) ──────────────────────────
#
# 게이트웨이 장비에서는 답할 수 없는 질문이 여기 있다. 어떤 프로세스가 그 포트를
# 갖고 있는가는 그 단말 안에서만 보이고, 루프백은 정의상 밖에서 닿지 않는다.

def _run(command: list[str], timeout: int = 10) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              check=False)
        if done.returncode != 0:
            SCAN_ERRORS.add("source_unavailable")
        return done.stdout or ""
    except (OSError, subprocess.SubprocessError):
        SCAN_ERRORS.add("source_unavailable")
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
            SCAN_ERRORS.add("source_unavailable")
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
        except FileNotFoundError:
            continue
        except OSError:
            SCAN_ERRORS.add("source_unavailable")
            continue  # 다른 사용자의 프로세스. 권한이 없으면 소유자는 비운다.
        try:
            raw = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except FileNotFoundError:
            continue
        except OSError:
            SCAN_ERRORS.add("source_unavailable")
            raw = ""
        name = raw.split(" ")[0].rsplit("/", 1)[-1][:120]
        for fd in fds:
            try:
                target = os.readlink(fd)
            except FileNotFoundError:
                continue
            except OSError:
                SCAN_ERRORS.add("source_unavailable")
                continue
            if target.startswith("socket:["):
                owners[target[8:-1]] = (name, raw.strip()[:600])

    found = []
    for inode, (address, port) in inode_to_socket.items():
        name, command = owners.get(inode, ("", ""))
        found.append({"address": address, "port": port,
                      "process_name": name, "command_line": command})
    return found


def _windows_processes() -> dict[str, tuple[str, str]]:
    """PID -> (name, command line). tasklist has no command line, and without one a node.exe
    or python.exe MCP server looks like any other process."""
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    if PROCESS_SID:
        if not re.fullmatch(r"S-1-\d+(?:-\d+)+", PROCESS_SID):
            raise ValueError("Invalid managed process SID")
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ErrorActionPreference='Stop'; "
                  "$rows=@(); foreach($p in Get-CimInstance Win32_Process) { "
                  "if($p.ProcessId -eq 0) {continue}; "
                  "$o=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid; "
                  "if($o.ReturnValue -ne 0) {throw 'owner_unavailable'}; "
                  f"if($o.Sid -eq '{PROCESS_SID}') {{ $rows += $p | "
                  "Select-Object ProcessId,Name,CommandLine } }; ConvertTo-Json -InputObject $rows -Compress")
    try:
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, timeout=30, check=False)
        if done.returncode != 0 or not done.stdout.strip():
            SCAN_ERRORS.add("source_unavailable")
            return {}
        rows = json.loads(done.stdout.decode("utf-8", "replace"))
    except (OSError, subprocess.SubprocessError, ValueError):
        SCAN_ERRORS.add("source_unavailable")
        return {}
    if isinstance(rows, dict):
        rows = [rows]
    return {str(row.get("ProcessId")): (str(row.get("Name") or "")[:120], str(row.get("CommandLine") or "")[:600])
            for row in rows if isinstance(row, dict)}


def _windows_listeners(processes: dict[str, tuple[str, str]] | None = None) -> list[dict]:
    rows = []
    processes = _windows_processes() if processes is None else processes
    for line in _run(["netstat", "-ano", "-p", "TCP"]).splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        address, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        name, command = processes.get(parts[4], ("", ""))
        rows.append({"address": address.strip("[]") or "0.0.0.0", "port": int(port),
                     "process_name": name, "command_line": command})
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


def sealed_listener(finding: dict, raw: dict, collector: str) -> dict:
    steps = ["command_sha256"] if raw.get("command_line") else []
    finding["provenance"] = provenance({**raw, "source": finding["source"], "address": finding.get("address"),
                                        "port": finding.get("port")},
                                       projection(finding, LISTENER_FIELDS), steps, collector)
    return finding


CONTAINER_ID = re.compile(r"(?:docker|libpod)-([0-9a-f]{64})\.scope|/docker/([0-9a-f]{64})")


def _approved_local_run(pid_dir: Path, seen: dict) -> bool:
    """A process inside a container the kit's local runner started for an approved local MCP.

    Without this every call to an approved local server raised MCP-SHADOW-002 for its own container
    (10-23 PJ1). The runner's containers carry the label mcpgw.local=1; only root or the engine's group
    can create a labelled container, and either could already do anything on this PC."""
    try:
        found = CONTAINER_ID.search((pid_dir / "cgroup").read_text(errors="replace"))
    except OSError:
        return False
    if not found:
        return False
    container = found.group(1) or found.group(2)
    if container not in seen:
        seen[container] = False
        for binary in ("/usr/bin/docker", "/usr/bin/podman"):
            if os.path.isfile(binary):
                try:
                    label = subprocess.run([binary, "inspect", "--format", '{{index .Config.Labels "mcpgw.local"}}', container],
                                           capture_output=True, text=True, timeout=5, check=False).stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    continue
                if label == "1":
                    seen[container] = True
                    break
    return seen[container]


# A harness's own command line carries the employee's prompt (`claude -p "…modelcontextprotocol/python-sdk…"`): matching
# the markers there reported the harness itself as a stdio MCP server (S4-03, PJ1 10-25). The servers it starts are
# separate processes and are still checked.
HARNESS_SCRIPT = re.compile(r"[\\/](?:@anthropic-ai[\\/]claude-code[\\/]cli\.js|@openai[\\/]codex[\\/]bin[\\/]codex\.js)$", re.I)


def harness_process(command_line: str) -> bool:
    words = [word.strip("\"'") for word in re.findall(r'''"[^"]*"|'[^']*'|\S+''', command_line)]
    if not words:
        return False
    # A basename is not file identity: a renamed Python interpreter can run FastMCP.
    entry = os.path.normcase(os.path.realpath(shutil.which(words[0]) or words[0]))
    paths = CONFIG.get("ENDPOINT_HARNESS_PATHS", [])
    if isinstance(paths, list) and any(isinstance(path, str) and os.path.isabs(path)
                                     and entry == os.path.normcase(os.path.realpath(path)) for path in paths):
        return True
    # node (or bun) running the harness package's entry script
    return re.search(r"(?:^|[\\/])(?:node|bun)(?:\.exe)?$", words[0], re.I) is not None \
        and len(words) > 1 and HARNESS_SCRIPT.search(os.path.realpath(words[1])) is not None


def stdio_processes() -> list[dict]:
    """설정에 없이 직접 실행된 stdio MCP 서버.

    포트를 열지 않으므로 어떤 망 스캔으로도 보이지 않는다. 이것도 강제 경로 밖의
    경로이고, 단말에서만 보인다.
    """
    found = []
    if platform.system() == "Windows":
        for name, raw in _windows_processes().values():
            if raw and PROCESS_MARKERS.search(raw) and not harness_process(raw):
                found.append(sealed_listener({"source": "stdio-process", "address": "local-process", "port": None,
                              "process_name": name, "command_line": command_digest(raw), "mcp_evidence": "suspected"},
                              {"process_name": name, "command_line": raw}, "process-table"))
        return found
    if platform.system() != "Linux":
        output = _run(["ps", "-eo", "pid=,comm=,args="])
        for line in output.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 3 or not PROCESS_MARKERS.search(parts[2]) or harness_process(parts[2]):
                continue
            found.append(sealed_listener({"source": "stdio-process", "address": "local-process", "port": None,
                          "process_name": parts[1][:120], "command_line": command_digest(parts[2]),
                          "mcp_evidence": "suspected"}, {"process_name": parts[1], "command_line": parts[2]}, "process-table"))
        return found
    containers: dict = {}
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.name.isdigit():
            continue
        try:
            if PROCESS_UID and pid_dir.stat().st_uid != int(PROCESS_UID):
                continue
            raw = (pid_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
        except FileNotFoundError:
            continue
        except OSError:
            SCAN_ERRORS.add("process_unreadable")
            continue
        if not raw or not PROCESS_MARKERS.search(raw) or harness_process(raw) or _approved_local_run(pid_dir, containers):
            continue
        found.append(sealed_listener({"source": "stdio-process", "address": "local-process", "port": None,
                      "process_name": raw.split(" ")[0].rsplit("/", 1)[-1][:120],
                      "command_line": command_digest(raw), "mcp_evidence": "suspected"},
                      {"process_name": raw.split(" ")[0].rsplit("/", 1)[-1], "command_line": raw}, "process-table"))
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
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
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


def _rpc_result(payload: str) -> dict:
    for chunk in [payload] + [line[5:].strip() for line in payload.splitlines() if line.startswith("data:")]:
        try:
            document = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(document, dict) and isinstance(document.get("result"), dict):
            return document["result"]
    raise ValueError("JSON-RPC 결과 없음")


def connection_check(gateway_url: str, context: ssl.SSLContext, authorization: str, servers: list[str],
                     timeout: float = 20) -> dict:
    """설치 확인(D-239): 직원 하네스와 같은 헤더로 승인 서버마다 initialize·tools/list만 보낸다. 도구는 실행하지 않는다.
    {initialized: [서버], failed: {서버: 사유}, tools: 도구 수}. 헤더 값은 돌려주지도 기록하지도 않는다."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                         urllib.request.HTTPSHandler(context=context))
    result = {"initialized": [], "failed": {}, "tools": 0}
    for server in servers:
        headers = {"Authorization": authorization, "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}

        def post(body: dict) -> str:
            request = urllib.request.Request(f"{gateway_url}/mcp/{server}/", data=json.dumps(body).encode(),
                                             headers=headers, method="POST")
            with opener.open(request, timeout=timeout) as response:
                if response.headers.get("mcp-session-id"):
                    headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
                return response.read(4_000_000).decode("utf-8", "replace")
        try:
            post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "mcpgw-install-check", "version": AGENT_VERSION}}})
            post({"jsonrpc": "2.0", "method": "notifications/initialized"})
            # ponytail: one page of tools/list; follow nextCursor if a server ever pages its tools.
            tools = _rpc_result(post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})).get("tools") or []
            result["initialized"].append(server)
            result["tools"] += len(tools)
        except urllib.error.HTTPError as exc:
            result["failed"][server] = f"HTTP {exc.code}"
        except (OSError, ValueError) as exc:
            result["failed"][server] = type(exc).__name__
    return result


MODEL_PROMPT = "Reply with the single word OK."


def model_check(argv: list[str], *, env: dict | None = None, cwd: str | None = None, timeout: int = 120) -> dict:
    """하네스가 모델 응답을 실제로 받는지. 자격 파일이 있다는 것만으로 성공 처리하지 않는다(D-239). 응답 본문은 남기지 않는다."""
    started = time.monotonic()
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                              env=env, cwd=cwd, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "seconds": round(time.monotonic() - started, 1), "detail": type(exc).__name__}
    ok = done.returncode == 0 and bool((done.stdout or "").strip())
    last = ((done.stderr or "").strip() or (done.stdout or "").strip()).splitlines()
    return {"ok": ok, "seconds": round(time.monotonic() - started, 1),
            "detail": "" if ok else (last[-1][:160] if last else f"종료 코드 {done.returncode}")}


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
        return [sealed_listener({"source": "network", "address": address, "port": port, "mcp_evidence": "unknown"},
                                {}, "network-probe") for address, port in live]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(live)))) as pool:
        probed = list(pool.map(lambda pair: (pair, probe_mcp(pair[0], pair[1])), live))
    for (address, port), info in probed:
        if info is None:
            continue  # MCP가 아닌 포트는 올리지 않는다. 자산대장이 아니라 MCP 관측이다.
        findings.append(sealed_listener({"source": "network", "address": address, "port": port,
                         "mcp_evidence": "confirmed", **{k: v for k, v in info.items() if k != "path"}},
                         {"probe": info}, "network-probe"))
    return findings


LISTENER_COLLECTOR = {"Linux": "proc-socket", "Windows": "windows-netstat"}.get(platform.system(), "lsof")


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
        elif marker and not harness_process(row.get("command_line") or row.get("process_name") or ""):
            evidence = "suspected"
        else:
            continue  # MCP 표지도 없고 initialize에도 답하지 않으면 MCP가 아니다.
        findings.append(sealed_listener({"source": "local-socket", "address": row["address"], "port": row["port"],
                         "process_name": row.get("process_name", ""),
                         "command_line": command_digest(row.get("command_line", "")),
                         "mcp_evidence": evidence,
                         **{k: v for k, v in (info or {}).items() if k != "path"}},
                         {"process_name": row.get("process_name", ""), "command_line": row.get("command_line", ""),
                          "probe": info}, LISTENER_COLLECTOR))
    return findings


# ── 게이트웨이 통신 ──────────────────────────────────────────────────────────

def tls_context(certificate: str | None = None, fingerprint: str | None = None) -> ssl.SSLContext:
    ca_file = setting("ENDPOINT_CA_FILE", "")
    if certificate is None and ca_file:
        certificate = Path(ca_file).read_text(encoding="utf-8")
        fingerprint = Path(ca_file).with_suffix(".sha256").read_text(encoding="utf-8").strip()
    certificate = setting("ENDPOINT_CA_CERTIFICATE", "") if certificate is None else certificate
    fingerprint = setting("ENDPOINT_CA_SHA256", "") if fingerprint is None else fingerprint
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if certificate or fingerprint:
        blocks = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", certificate, re.S)
        if len(blocks) != 1 or certificate.strip() != blocks[0]:
            raise ValueError("설치 키트에는 루트 인증서 하나만 허용합니다")
        expected = fingerprint.replace(":", "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or hashlib.sha256(ssl.PEM_cert_to_DER_cert(blocks[0])).hexdigest() != expected:
            raise ValueError("CA SHA-256 지문이 일치하지 않습니다")
        context.load_verify_locations(cadata=certificate)
    return context

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, *args):
        return None


def call(method: str, path: str, body: dict | None = None) -> dict:
    validate_gateway()
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(GATEWAY_URL + path, data=payload, method=method)
    request.add_header("content-type", "application/json")
    request.add_header("x-endpoint-key", DEVICE_KEY)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=tls_context()))
    with opener.open(request, timeout=30) as response:
        return json.loads(response.read() or b"{}")


def enroll() -> None:
    call("POST", "/api/endpoint/enroll", {
        "endpoint_id": endpoint_id(),
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}"[:80],
        "agent_version": AGENT_VERSION,
        "detail": {"scan_paths": [str(path) for path in SCAN_PATHS],
                   "capabilities": ["config-inventory", "local-socket", "network", "stdio-process"],
                   "process_scope": {"uid": PROCESS_UID or None, "sid": PROCESS_SID or None}},
    })


# Managed PostToolUse hook (D-301). The harness runs it as the employee after every MCP tool call; it appends one line
# to the employee's own spool and the service, which holds the device key, sends the spool on. Sizes and a hash of the
# arguments only — never the arguments or the result.
TOOL_EVENT_SPOOL = Path(".mcpgw") / "tool-events.jsonl"
TOOL_EVENT_LIMIT = 4 << 20
TOOL_EVENT_FILES = [Path(p) for p in setting("ENDPOINT_TOOL_EVENT_FILES", "").split(os.pathsep) if p.strip()]
TOOL_EVENT_FIELDS = {"event_id": str, "called_at": str, "harness": str, "account": str, "server": str, "tool": str,
                     "input_bytes": int, "input_sha256": str, "output_bytes": int, "failed": bool}


def tool_hook(harness: str) -> int:
    """Never blocks or fails the call it records: every error ends in exit 0."""
    try:
        payload = json.loads(sys.stdin.buffer.read(16 << 20) or b"{}")
        parts = str(payload.get("tool_name") or "").split("__", 2)
        if harness not in ("claude", "codex") or len(parts) != 3 or parts[0] != "mcp" or not parts[1] or not parts[2]:
            return 0
        arguments = json.dumps(payload.get("tool_input"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        response = payload.get("tool_response")
        output = b"" if response is None else json.dumps(response, ensure_ascii=False).encode()
        event = {"event_id": os.urandom(16).hex(), "called_at": datetime.now(timezone.utc).isoformat(), "harness": harness,
                 "account": (os.getenv("USERNAME") or os.getenv("USER") or "")[:120], "server": parts[1][:200], "tool": parts[2][:200],
                 "input_bytes": len(arguments), "input_sha256": hashlib.sha256(arguments).hexdigest(), "output_bytes": len(output),
                 "failed": isinstance(response, dict) and bool(response.get("isError") or response.get("is_error"))}
        spool = Path.home() / TOOL_EVENT_SPOOL
        spool.parent.mkdir(exist_ok=True)
        if not spool.exists() or spool.stat().st_size < TOOL_EVENT_LIMIT:
            with spool.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


def _plain_file(path: Path) -> bool:
    """The spool sits in the employee's home and the service reads it with more privilege: no links, junctions or devices."""
    try:
        for item in (path.parent, path):
            info = os.lstat(item)
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
        return stat.S_ISREG(os.lstat(path).st_mode) and os.lstat(path).st_size <= TOOL_EVENT_LIMIT
    except OSError:
        return False


def _tool_event(line: str) -> dict | None:
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if not isinstance(event, dict) or any(not isinstance(event.get(k), t) or (t is int and isinstance(event.get(k), bool))
                                          for k, t in TOOL_EVENT_FIELDS.items()):
        return None
    return {k: event[k] for k in TOOL_EVENT_FIELDS}


def report_tool_events() -> dict:
    """Send what the hook spooled. A batch moves aside first so the hook keeps appending to a fresh file; a batch that
    failed to send stays aside and goes first next time."""
    sent = 0
    for spool in TOOL_EVENT_FILES:
        batch = spool.with_name(spool.name + ".sending")
        if not batch.exists() and _plain_file(spool):
            try:
                spool.replace(batch)
            except OSError:
                continue
        if not _plain_file(batch):
            continue
        lines = batch.read_text(encoding="utf-8", errors="replace").splitlines()
        events = [e for e in map(_tool_event, lines[:5000]) if e]
        for start in range(0, len(events), 500):
            call("POST", "/api/endpoint/tool-events", {"endpoint_id": endpoint_id(), "events": events[start:start + 500]})
        sent += len(events)
        batch.unlink()
    return {"sent": sent}


def report_configs() -> dict:
    SCAN_ERRORS.clear()
    entries = collect_configs()
    complete = not SCAN_ERRORS and len(entries) <= 500
    result = call("POST", "/api/endpoint/inventory",
                  {"endpoint_id": endpoint_id(), "entries": entries[:500], "complete": complete, "origin": ORIGIN})
    return {**result, "state": "success" if complete else "partial"}


def report_processes() -> dict:
    if not PROCESS_ENABLED:
        return {"state": "disabled", "accepted": 0}
    SCAN_ERRORS.clear()
    findings = stdio_processes()
    complete = not SCAN_ERRORS and len(findings) <= 500
    result = call("POST", "/api/endpoint/listeners", {
        "endpoint_id": endpoint_id(), "findings": findings[:500], "sources": ["stdio-process"], "complete": complete,
        "origin": ORIGIN})
    return {**result, "state": "success" if complete else "partial"}


def report_listeners() -> dict:
    if not SCAN_ENABLED:
        return {"state": "disabled", "accepted": 0}
    try:
        policy = call("GET", "/api/endpoint/scan-policy")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            # 이 장치에 netscan 권한이 없다. 정상이다 — 관측 축은 선택이다.
            return {"state": "unauthorized", "accepted": 0, "error_code": "access_denied"}
        raise
    if not policy.get("enabled"):
        return {"state": "disabled", "accepted": 0, "error_code": "policy_disabled"}
    SCAN_ERRORS.clear()
    findings = listener_findings(policy) + network_findings(policy)
    complete = not SCAN_ERRORS and len(findings) <= 500
    result = call("POST", "/api/endpoint/listeners", {
        "endpoint_id": endpoint_id(), "findings": findings[:500],
        "sources": ["local-socket", "network"], "complete": complete, "origin": ORIGIN})
    return {**result, "state": "success" if complete else "partial"}


def report_status(channel: str, state: str, accepted_count: int = 0, error_code: str = "", **buffer_report) -> dict:
    return call("POST", "/api/endpoint/observation-status", {
        "endpoint_id": endpoint_id(), "channel": channel, "state": state,
        "accepted_count": min(500, accepted_count), "error_code": error_code, **buffer_report})


def once() -> dict:
    results = {}
    for channel, collect in (("inventory", report_configs), ("process", report_processes), ("network", report_listeners)):
        try:
            result = collect()
        except urllib.error.HTTPError as exc:
            result = {"state": "unauthorized" if exc.code in (401, 403) else "failed", "error_code": "delivery_failed"}
        except (OSError, ValueError, subprocess.SubprocessError):
            result = {"state": "failed", "error_code": "source_unavailable"}
        state, count = result["state"], result.get("accepted", 0)
        error = result.get("error_code", "incomplete_snapshot" if state == "partial" else "")
        try:
            report_status(channel, state, count, error)
        except (OSError, ValueError, subprocess.SubprocessError):
            state, error = "failed", "delivery_failed"
        results[channel] = {"state": state, "accepted_count": count, "error_code": error}
    if TOOL_EVENT_FILES:
        try:
            results["tools"] = report_tool_events()
        except (OSError, ValueError, urllib.error.URLError) as exc:
            log("도구 호출 기록 전송 실패: %s" % exc)
    print(json.dumps({"observation": results}), flush=True)
    return results


def measure_gateway(url: str, probes: int = 5, timeout: float = 2.0, *, context=None) -> dict:
    """Five TCP connects and one HTTP(S) round trip to the Gateway this device already reports to.

    The target is the caller's own configured Gateway address and nothing else. The latency
    figures are the TCP connect times; a failed connect or a failed HTTP probe counts toward
    the failure percentage, which is a probe failure rate and not a packet-loss measurement."""
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    samples, failed = [], 0
    for _ in range(probes):
        started = time.perf_counter()
        try:
            socket.create_connection((parts.hostname, port), timeout=timeout).close()
            samples.append((time.perf_counter() - started) * 1000)
        except OSError:
            failed += 1
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                            urllib.request.HTTPSHandler(context=context or tls_context()))
        with opener.open(urllib.request.Request(url.rstrip("/") + "/api/health"), timeout=5) as response:
            response.read(1024)
    except urllib.error.HTTPError as exc:
        failed += exc.code >= 500
    except (OSError, ValueError):
        failed += 1
    return summarise_samples(samples, failed, probes + 1)


def summarise_samples(samples: list, failed: int, probes: int) -> dict:
    """Nearest-rank percentiles; jitter is the mean absolute difference of successive samples."""
    ordered = sorted(samples)
    nearest = lambda q: round(ordered[max(0, math.ceil(q * len(ordered)) - 1)], 1) if ordered else None
    jitter = (sum(abs(b - a) for a, b in zip(samples, samples[1:])) / (len(samples) - 1) if len(samples) > 1
              else 0.0 if samples else None)
    return {"measured_at": canonical_time(datetime.now(timezone.utc)), "rtt_p50_ms": nearest(0.5),
            "rtt_p95_ms": nearest(0.95), "jitter_ms": None if jitter is None else round(jitter, 1),
            "failure_pct": round(100 * failed / probes, 1), "probes": probes}


def validate_gateway() -> None:
    parsed = urlsplit(GATEWAY_URL)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("게이트웨이 기본 주소가 올바르지 않습니다")
    if parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"gateway", "localhost", "127.0.0.1", "::1"}):
        return
    raise ValueError("원격 게이트웨이는 HTTPS만 허용합니다")


def main() -> int:
    if not DEVICE_KEY:
        log("ENDPOINT_DEVICE_KEY가 없습니다. 관리자가 발급한 장치 자격이 필요합니다.")
        return 2
    try:
        validate_gateway()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        log(str(exc))
        return 2
    log(f"엔드포인트 {endpoint_id()} · 관측 경로 {[str(p) for p in SCAN_PATHS]}")
    enrolled = False
    while True:
        linked = False
        try:
            if not enrolled:
                enroll()
                enrolled = True
                log("등록 완료")
            results = once()
            failed = any(value["state"] in {"failed", "unauthorized"} for value in results.values())
            # The tray shows the link, not snapshot completeness (partial is reported to the Gateway already).
            linked = not any(value["state"] in {"failed", "unauthorized"} for value in results.values())
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
        status_path = CONFIG.get("ENDPOINT_TRAY_STATUS")
        if os.name == "nt" and status_path:
            from windows_status import publish
            publish(status_path, linked)
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
    assert PROCESS_MARKERS.search("uvx ida-mcp stdio")
    assert PROCESS_MARKERS.search("python bridge_mcp_ghidra.py")
    assert PROCESS_MARKERS.search("node /opt/obsidian-mcp/dist/index.js")
    assert PROCESS_MARKERS.search("node /opt/node_modules/@playwright/mcp/cli.js")
    assert PROCESS_MARKERS.search("node /opt/node_modules/@bytebase/dbhub/dist/index.js --transport=stdio")
    assert PROCESS_MARKERS.search("C:/synthetic/Scripts/mcp-for-blender.exe")
    assert not PROCESS_MARKERS.search("C:/synthetic/blender.exe --background scene.blend")

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
    codex = server_entries(toml_loads('[mcp_servers.git]\nurl = "http://gateway:8080/mcp/git/"\n'))
    assert describe("git", codex["git"])["endpoint_ref"].endswith("/mcp/git/")

    # 탐색 범위는 정책이 정하고, 공인 대역은 정책이 내려줘도 펼치지 않는다.
    assert scan_targets({"allowed_cidrs": [], "max_hosts": 8}) == ["127.0.0.1"]
    assert scan_targets({"allowed_cidrs": ["8.8.8.0/30"], "max_hosts": 8}) == ["127.0.0.1"]
    private = scan_targets({"allowed_cidrs": ["192.0.2.0/30"], "max_hosts": 8})
    assert "192.0.2.1" in private and "8.8.8.1" not in private
    assert len(scan_targets({"allowed_cidrs": ["10.0.0.0/20"], "max_hosts": 5})) == 5
    codex = Path("C:/Users/a/.codex/config.toml")
    assert vendor_bundled(codex, {"command": "C:\\Program Files\\WindowsApps\\OpenAI.Codex_26.1027.3384.0_x64__2p2nqsd0c76g0\\app\\ChatGPT.exe"})
    assert vendor_bundled(codex, {"command": "C:\\Users\\a\\AppData\\Local\\OpenAI\\Codex\\runtimes\\cua_node\\x\\bin\\node_repl.exe"})
    assert not vendor_bundled(codex, {"command": "C:\\Tools\\venv\\Scripts\\pyghidra-mcp.exe"})
    assert not vendor_bundled(Path("C:/Users/a/.claude.json"), {"command": "C:\\Program Files\\WindowsApps\\OpenAI.Codex_1\\app\\ChatGPT.exe"})

    # 훅 기록 줄: 알려진 필드와 형식만 보내고, 형식이 다른 줄은 버린다.
    good = {"event_id": "e" * 32, "called_at": "2026-10-31T00:00:00+00:00", "harness": "codex", "account": "a", "server": "ghidra",
            "tool": "decompile_function", "input_bytes": 3, "input_sha256": "0" * 64, "output_bytes": 9, "failed": False, "extra": 1}
    assert _tool_event(json.dumps(good)) == {k: good[k] for k in TOOL_EVENT_FIELDS}
    assert _tool_event(json.dumps({**good, "input_bytes": True})) is None and _tool_event("not json") is None
    print("endpoint-agent self-check OK")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "hook":
        raise SystemExit(tool_hook(sys.argv[2]))
    if "--self-check" in sys.argv:
        demo()
        raise SystemExit(0)
    sys.exit(main())
