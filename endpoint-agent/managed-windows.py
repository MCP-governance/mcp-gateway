#!/usr/bin/env python3
"""Administrator-installed Windows enrollment, policy service and header broker.

The Windows counterpart of managed-linux.py. Simple mode (the default, D-239) enrolls the signed-in
employee's own account as it is, administrator or not, with no logout. The isolated mode
(「고급: 격리 계정」) enrolls one ordinary companion account and keeps a per-account Windows Firewall
rule that blocks every outbound destination except the Gateway host's Gateway and model-proxy ports.
In both, a SYSTEM task holds the device key, writes the harnesses' machine-wide settings and hands
the account a short-lived token over a named pipe whose DACL admits only that account's SID.
This is not remote attestation against a compromised administrator.
"""
import argparse
import ctypes
import hashlib
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

PROGRAM_FILES = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
PROGRAM_DATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
PROGRAMS = PROGRAM_FILES / "MCPGatewayManaged"
STATE = PROGRAM_DATA / "MCPGatewayManaged"
FILES = {"managed-mcp.json": PROGRAM_FILES / "ClaudeCode" / "managed-mcp.json",
         "managed-settings.json": PROGRAM_FILES / "ClaudeCode" / "managed-settings.json",
         # Codex on Windows reads only this enforced file; managed_config.toml is not supported there.
         "requirements.toml": PROGRAM_DATA / "OpenAI" / "Codex" / "requirements.toml"}
CODEX_BLOCK = "codex-config.toml"
BEGIN = "# >>> mcp-gateway managed >>>"
END = "# <<< mcp-gateway managed <<<"
SYSTEM, ADMINISTRATORS, USERS = "S-1-5-18", "S-1-5-32-544", "S-1-5-32-545"
TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
TRUSTED = {SYSTEM, ADMINISTRATORS, TRUSTED_INSTALLER}
# WriteData, AppendData, WriteEA, DeleteChild, WriteAttributes, Delete, WRITE_DAC, WRITE_OWNER, GENERIC_ALL, GENERIC_WRITE
WRITE_RIGHTS = 0x2 | 0x4 | 0x10 | 0x40 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000
RULES = ("egress", "gateway-tcp", "gateway-udp")
TASK = "MCPGatewayManaged-{user}"
# The cached credential has to outlive one slow round (60 s pause + the observers' 40 s and 45 s limits),
# or the harness is given the not-active placeholder between two rounds of an active device.
TOKEN_CACHE_SECONDS = 180


def pipe_name(username):
    return r"\\.\pipe\mcpgw-" + username.lower()


def powershell(script, payload=None, timeout=60):
    """Values travel in an environment variable as JSON, never spliced into the script text."""
    env = dict(os.environ, MCPGW_INPUT=json.dumps(payload or {}))
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                           "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                           "$in = $env:MCPGW_INPUT | ConvertFrom-Json; " + script],
                          capture_output=True, timeout=timeout, env=env)
    if done.returncode:
        raise ValueError(done.stderr.decode("utf-8", "replace").strip()[:300] or "PowerShell 실패")
    text = done.stdout.decode("utf-8", "replace").strip()
    return json.loads(text) if text else None


# -- addresses ------------------------------------------------------------------

def complement(addresses):
    """Every address range outside `addresses`, as Windows Firewall RemoteAddress ranges."""
    ranges = []
    for version, top in ((4, 2 ** 32 - 1), (6, 2 ** 128 - 1)):
        start = 0
        for value in sorted(int(ip) for ip in map(ipaddress.ip_address, addresses) if ip.version == version):
            if value > start:
                ranges.append((version, start, value - 1))
            start = value + 1
        if start <= top:
            ranges.append((version, start, top))
    return [f"{ipaddress.ip_address(a) if v == 4 else ipaddress.IPv6Address(a)}-"
            f"{ipaddress.ip_address(b) if v == 4 else ipaddress.IPv6Address(b)}" for v, a, b in ranges]


def other_ports(ports):
    ranges, start = [], 1
    for port in sorted(set(ports)):
        if port > start:
            ranges.append(f"{start}-{port - 1}" if port - 1 > start else str(start))
        start = port + 1
    if start <= 65535:
        ranges.append(f"{start}-65535")
    return ranges


def firewall_rules(username, sid, gateway_ips, ports):
    """Block rules win over any allow rule. Scoped by the account SID (LocalUser), not by program
    path, so a copied or renamed harness binary is confined the same way."""
    owner = f"D:(A;;CC;;;{sid})"
    name = f"MCPGW-{username}-"
    return [{"Name": name + "egress", "Protocol": "Any", "RemoteAddress": complement(gateway_ips), "LocalUser": owner},
            {"Name": name + "gateway-tcp", "Protocol": "TCP", "RemoteAddress": gateway_ips,
             "RemotePort": other_ports(ports), "LocalUser": owner},
            {"Name": name + "gateway-udp", "Protocol": "UDP", "RemoteAddress": gateway_ips, "LocalUser": owner}]


APPLY_RULES = """
foreach ($r in $in.rules) {
  Remove-NetFirewallRule -Name $r.Name -ErrorAction SilentlyContinue
  $a = @{ Name=$r.Name; DisplayName=$r.Name; Group='MCP Gateway'; Direction='Outbound'; Action='Block';
          Profile='Any'; Enabled='True'; Protocol=$r.Protocol; RemoteAddress=@($r.RemoteAddress); LocalUser=$r.LocalUser }
  if ($r.RemotePort) { $a.RemotePort = @($r.RemotePort) }
  New-NetFirewallRule @a | Out-Null
}
"""
READ_RULES = """
$rules = foreach ($n in $in.names) {
  $r = Get-NetFirewallRule -Name $n -ErrorAction SilentlyContinue
  if (-not $r) { continue }
  $addr = $r | Get-NetFirewallAddressFilter; $port = $r | Get-NetFirewallPortFilter; $sec = $r | Get-NetFirewallSecurityFilter
  [pscustomobject]@{ Name=$r.Name; Enabled="$($r.Enabled)"; Direction="$($r.Direction)"; Action="$($r.Action)";
    Profile="$($r.Profile)"; Protocol="$($port.Protocol)"; RemotePort=@($port.RemotePort); RemoteAddress=@($addr.RemoteAddress);
    LocalUser="$($sec.LocalUser)" }
}
[pscustomobject]@{ rules=@($rules); profiles=@(Get-NetFirewallProfile | ForEach-Object { [bool]$_.Enabled }) } | ConvertTo-Json -Depth 4 -Compress
"""


# -- accounts, files and ACLs -----------------------------------------------------

ACCOUNT = """
$sid = (New-Object Security.Principal.NTAccount($in.user)).Translate([Security.Principal.SecurityIdentifier]).Value
$profile = (Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList\\$sid" -ErrorAction SilentlyContinue).ProfileImagePath
$admins = @(Get-LocalGroupMember -SID S-1-5-32-544 | ForEach-Object { $_.SID.Value })
[pscustomobject]@{ sid=$sid; profile=$profile; admin=($admins -contains $sid) } | ConvertTo-Json -Compress
"""
OWNED_PROCESSES = """
$n = 0
foreach ($p in Get-CimInstance Win32_Process) {
  $o = Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid -ErrorAction SilentlyContinue
  if ($o.Sid -eq $in.sid) { $n++ }
}
$n
"""
ACL = """
$out = foreach ($p in $in.paths) {
  $acl = Get-Acl -LiteralPath $p
  $owner = (New-Object Security.Principal.NTAccount($acl.Owner)).Translate([Security.Principal.SecurityIdentifier]).Value
  $rules = foreach ($e in $acl.Access) {
    try { $s = $e.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { $s = "$($e.IdentityReference)" }
    [pscustomobject]@{ sid=$s; rights=[int64]$e.FileSystemRights; allow=("$($e.AccessControlType)" -eq 'Allow');
                       inherit_only=("$($e.PropagationFlags)" -match 'InheritOnly') }
  }
  [pscustomobject]@{ path=$p; owner=$owner; rules=@($rules) }
}
@($out) | ConvertTo-Json -Depth 4 -Compress
"""
HOST = """
$admins = @(Get-LocalGroupMember -SID S-1-5-32-544 -ErrorAction SilentlyContinue | ForEach-Object { $_.SID.Value })
@(Get-LocalUser | Where-Object { $_.Enabled -and $_.SID.Value -ne $in.sid } | ForEach-Object {
  [pscustomobject]@{ name=$_.Name; sid=$_.SID.Value; admin=($admins -contains $_.SID.Value) } }) | ConvertTo-Json -Compress
"""


def account(username):
    return powershell(ACCOUNT, {"user": username})


def lock_down(directory, readers=True):
    """Administrators own it; SYSTEM and Administrators write; ordinary users only read (or nothing)."""
    directory.mkdir(parents=True, exist_ok=True)
    grants = [f"*{SYSTEM}:(OI)(CI)F", f"*{ADMINISTRATORS}:(OI)(CI)F"] + ([f"*{USERS}:(OI)(CI)RX"] if readers else [])
    # icacls /T would write the (OI)(CI) grants onto existing files as empty DACLs: grant the root, children inherit.
    commands = [["icacls", str(directory), "/setowner", f"*{ADMINISTRATORS}", "/T", "/C", "/Q"],
                ["icacls", str(directory), "/inheritance:r", "/grant:r", *grants, "/Q"]]
    if any(directory.iterdir()):
        commands.append(["icacls", str(directory / "*"), "/reset", "/T", "/C", "/Q"])
    for command in commands:
        subprocess.run(command, check=True, capture_output=True)


def protected(paths):
    """No one but SYSTEM, Administrators or TrustedInstaller owns or may change these paths."""
    rows = powershell(ACL, {"paths": [str(p) for p in paths]})
    rows = rows if isinstance(rows, list) else [rows]
    return len(rows) == len(paths) and all(
        row["owner"] in TRUSTED and all(rule["sid"] in TRUSTED or not rule["allow"] or rule["inherit_only"]  # applies to children only
                                        or not rule["rights"] & 0xFFFFFFFF & WRITE_RIGHTS for rule in row["rules"] or [])
        for row in rows)


def write_file(path, content):
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(4))
    # newline="": text mode would write CRLF on Windows and the reported hashes would never match the Gateway's.
    temporary.write_text(content, encoding="utf-8", newline="")
    os.replace(temporary, path)


def codex_config(config):
    return Path(config["profile"]) / ".codex" / "config.toml"


def codex_parts(text):
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == END]
    if not starts and not ends:
        return text, None, ""
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("직원 설정의 관리 구간 확인 필요")
    start, end = starts[0], ends[0]
    return "".join(lines[:start]), "".join(lines[start + 1:end]), "".join(lines[end + 1:])


def codex_block(text):
    block = codex_parts(text)[1]
    return block.replace("\r\n", "\n") if block is not None else None


def without_codex_block(text, owned=None):
    before, block, after = codex_parts(text)
    if block is None:
        return text
    if '"""' in block or "'''" in block:
        raise ValueError("직원 설정의 관리 구간 확인 필요")
    # Codex can move unrelated tables inside our markers. Only remove tables we actually rendered.
    sections = re.split(r"(?m)(?=^\[)", block)
    expected = set(re.findall(r"(?m)^\[[^\r\n]+\]", owned or ""))
    kept = []
    for section in sections:
        heading = section.splitlines()[0] if section.startswith("[") else ""
        if not heading:
            if section.strip():
                raise ValueError("직원 설정의 관리 구간 확인 필요")
        elif heading in expected or (heading.startswith("[mcp_servers.") and
                                     "http_headers_helper" in section and "managed-windows.py" in section):
            continue
        else:
            kept.append(section)
    return before + "".join(kept) + after


def with_codex_block(text, block):
    # Last in the file: a root key after our tables would otherwise fall inside them.
    rest = without_codex_block(text, block).rstrip("\r\n")
    return (rest + "\n\n" if rest else "") + BEGIN + "\n" + block + END + "\n"


def checked_codex_text(path):
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        codex_parts(current)
        without_codex_block(current)
    except ValueError:
        backup = path.with_name(path.name + ".mcpgw-" + secrets.token_hex(4) + ".backup")
        shutil.copyfile(path, backup)
        raise
    return current


def apply_policy(config, policy):
    files = policy["files"]
    if set(files) != set(FILES) | {CODEX_BLOCK}:
        raise ValueError("지원하지 않는 관리형 파일 목록")
    path = codex_config(config)
    current = checked_codex_text(path)
    updated = with_codex_block(current, files[CODEX_BLOCK])
    for directory in {target.parent for target in FILES.values()}:
        lock_down(directory)
    for name, target in FILES.items():
        write_file(target, files[name])
    path.parent.mkdir(parents=True, exist_ok=True)
    write_file(path, updated)
    folder = STATE / config.get("username", "").lower()
    if config.get("username") and folder.is_dir():
        write_file(folder / CODEX_BLOCK, files[CODEX_BLOCK])


def restore_codex_block(config, policy):
    """Simple mode: the block lives in the employee's own config.toml, which their Codex app rewrites (plugins and the
    like). That is the employee's file, not a control: put our block back before reporting instead of letting one
    rewrite quarantine the PC (pj3 10-25). True when it was rewritten."""
    path = codex_config(config)
    try:
        current = checked_codex_text(path)
    except OSError:
        return False  # unreadable: the heartbeat reports the mismatch
    if codex_block(current) == policy["files"][CODEX_BLOCK]:
        return False
    # ponytail: a writer that drops the markers but keeps our tables leaves duplicates for Codex; seen only if Codex does.
    write_file(path, with_codex_block(current, policy["files"][CODEX_BLOCK]))
    return True


def set_user_environment(config, values, *, owned_only=False):
    """HTTPS_PROXY etc. for the account only, so other accounts' tools are untouched. The hive is
    loaded when the account is signed out (the installer requires that)."""
    import winreg
    loaded = None
    try:
        winreg.OpenKey(winreg.HKEY_USERS, config["sid"]).Close()
        root = config["sid"]
    except OSError:
        loaded = "MCPGW-" + config["sid"]
        subprocess.run(["reg", "load", "HKU\\" + loaded, str(Path(config["profile"]) / "NTUSER.DAT")], check=True, capture_output=True)
        root = loaded
    try:
        with winreg.CreateKeyEx(winreg.HKEY_USERS, root + r"\Environment", 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
            for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "NODE_EXTRA_CA_CERTS", "CODEX_CA_CERTIFICATE"):
                if owned_only:
                    try:
                        value = str(winreg.QueryValueEx(key, name)[0])
                    except FileNotFoundError:
                        continue
                    if not value.lower().startswith(str(PROGRAMS).lower() + os.sep):
                        continue
                if values.get(name):
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, values[name])
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
            # The account's own PATH, appended to the machine one: how a created companion account
            # finds the approved harness at all. Entries that are not ours are kept.
            try:
                current = [part for part in str(winreg.QueryValueEx(key, "PATH")[0]).split(os.pathsep) if part]
            except FileNotFoundError:
                current = []
            kept = [part for part in current if not part.lower().startswith(str(PROGRAMS).lower())]
            wanted = kept + ([values["PATH_APPEND"]] if values.get("PATH_APPEND") else [])
            if wanted:
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, os.pathsep.join(wanted))
            elif current:
                winreg.DeleteValue(key, "PATH")
    finally:
        if loaded:
            subprocess.run(["reg", "unload", "HKU\\" + loaded], check=False, capture_output=True)


# -- Gateway ---------------------------------------------------------------------

def request(config, path, body=None, *, credential=True):
    context = verify_transport(config)
    headers = {"Content-Type": "application/json"}
    if credential:
        headers["X-Endpoint-Key"] = config["device_key"]
    data = json.dumps(body).encode() if body is not None else None

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("장치 자격을 다른 주소로 전달하지 않습니다")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
    with opener.open(urllib.request.Request(config["gateway_url"] + path, data=data, headers=headers), timeout=15) as response:
        return json.loads(response.read(131072))


def verify_transport(config):
    import importlib.util
    spec = importlib.util.spec_from_file_location("transport_observer", Path(__file__).with_name("agent.py"))
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    observer.GATEWAY_URL = config["gateway_url"]
    observer.CONFIG["ENDPOINT_TAILSCALE_NODE_ID"] = config.get("tailscale_node_id", "")
    observer.validate_gateway()
    parsed = urlsplit(config["gateway_url"])
    if parsed.path not in ("", "/") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Gateway 기본 주소만 허용합니다")
    return observer.tls_context(config.get("ca_certificate", ""), config.get("ca_sha256", ""))


def harness_launchers(config, native, harnesses):
    """Keep CA trust in the harness process tree, outside the account's registry environment."""
    if not config.get("ca_certificate"):
        return native, {}
    verify_transport(config)
    folder = PROGRAMS / "launchers" / config["sid"]
    lock_down(folder)
    ca = folder / "root.crt"
    if any(c in str(path) for path in (folder, native) for c in ('"', '%', '\r', '\n')):
        raise ValueError("하네스 실행 경로 형식 오류")
    write_file(ca, config["ca_certificate"])
    owned = {str(ca.relative_to(PROGRAMS)): hashlib.sha256(ca.read_bytes()).hexdigest()}
    for name, variable in (("claude", "NODE_EXTRA_CA_CERTS"), ("codex", "CODEX_CA_CERTIFICATE")):
        if name + ".exe" not in harnesses:
            continue
        executable = Path(os.path.relpath(native, folder)) / (name + ".exe")
        script = (f'@echo off\nsetlocal\nset "{variable}=%~dp0root.crt"\n'
                  f'"%~dp0{executable}" %*\nexit /b %errorlevel%\n')
        path = folder / (name + ".cmd")
        write_file(path, script)
        owned[str(path.relative_to(PROGRAMS))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return folder, owned


def ports(policy):
    return [policy["gateway_port"]] + ([policy["proxy_port"]] if policy.get("proxy_port") else [])


def rule_state(config):
    state = powershell(READ_RULES, {"names": [f"MCPGW-{config['username']}-{r}" for r in RULES]})
    state["rules"] = sorted(state["rules"] or [], key=lambda rule: rule["Name"])
    return state


def firewall_enforcing(config, rules, baseline):
    # A matching but incomplete installation snapshot cannot establish enforcement.
    if not isinstance(rules, dict) or not isinstance(baseline, dict):
        return False
    profiles, entries = rules.get("profiles"), rules.get("rules")
    names = {f"MCPGW-{config['username']}-{name}" for name in RULES}
    owner = f"D:(A;;CC;;;{config['sid']})"
    return (isinstance(profiles, list) and len(profiles) == 3 and all(p is True for p in profiles)
            and isinstance(entries, list) and len(entries) == len(names)
            and all(isinstance(rule, dict) and isinstance(rule.get("Name"), str) for rule in entries)
            and {rule.get("Name") for rule in entries} == names
            and all(rule.get("Enabled") == "True" and rule.get("Direction") == "Outbound"
                    and rule.get("Action") == "Block" and rule.get("Profile") == "Any"
                    and rule.get("LocalUser") == owner for rule in entries)
            and entries == baseline.get("rules"))


def checks(config, policy, *, findings=None):
    import importlib.util
    spec = importlib.util.spec_from_file_location("command_settings", Path(__file__).with_name("agent.py"))
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    commands_ok, commands = observer.user_command_settings(config["profile"])
    # 계정 사용자 환경의 CODEX_HOME·CLAUDE_CONFIG_DIR는 하네스를 위 검사가 읽지 않는 설정 폴더로 보낸다.
    # 값은 읽지 않고(보고 금지) 존재만 보며, 고정 표기로만 보고한다. 읽기 실패는 모두 실패(fail closed).
    # 계정이 로그아웃이면 하이브가 안 올라와 있어 FileNotFoundError(변수 없음)다: 그때는 하네스도 못 뜬다.
    environment = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_USERS, config["sid"] + r"\Environment") as key:
            for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
                try:
                    winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                environment.append({"file": "env:" + name, "keys": []})
    except FileNotFoundError:
        pass
    except (ImportError, OSError):
        environment = [{"file": "env", "keys": []}]
    commands_ok = commands_ok and not environment
    if findings is not None:
        findings.extend(commands + environment)
    targets = list(FILES.values())
    hashes = {name: hashlib.sha256(target.read_bytes()).hexdigest() for name, target in FILES.items()}
    try:
        block = codex_block(codex_config(config).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 사용자 파일 읽기 실패도 heartbeat의 실패 항목으로 보낸다.
        block = None
    hashes[CODEX_BLOCK] = hashlib.sha256((block or "").encode()).hexdigest()
    if config.get("mode") == "simple":
        # Nothing is confined in simple mode: the managed files, rendered and protected, are all there is (D-239).
        return hashes, {"protected_configs": protected(targets + list({t.parent for t in targets})
                                                       + [PROGRAMS, Path(sys.executable).parent])}
    rules = rule_state(config)
    baseline = json.loads(Path(config["firewall_baseline"]).read_text(encoding="utf-8"))
    return hashes, {
        # Every profile on, and the account's rules exactly as installed (a removed, disabled or
        # broadened rule is a mismatch).
        "firewall_enforcing": firewall_enforcing(config, rules, baseline),
        "protected_configs": protected(targets + list({t.parent for t in targets}) + [PROGRAMS, Path(sys.executable).parent]),
        "ordinary_account": account(config["username"]) == {"sid": config["sid"], "profile": config["profile"], "admin": False},
        "user_command_helpers": commands_ok,
    }


def host_report(config):
    accounts = powershell(HOST, {"sid": config["sid"]}) or []
    accounts = accounts if isinstance(accounts, list) else [accounts]
    versions = harness_versions(config["profile"])
    return {"kernel": ("Windows " + platform.version())[:120], "wsl": False,
            "other_accounts": [{"name": a["name"][:64], "uid": int(a["sid"].rsplit("-", 1)[1]),
                                "privileged_groups": ["Administrators"] if a["admin"] else []} for a in accounts[:64]],
            **({"harnesses": versions} if versions else {})}


# -- named pipe (header broker) ----------------------------------------------------

def serve_pipe(config, cache, lock):
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", wintypes.LPVOID), ("bInheritHandle", wintypes.BOOL)]
    descriptor = wintypes.LPVOID()
    # Protected DACL: the enrolled account may only read; SYSTEM and the creating owner (who must be able
    # to add instances) have full control; nobody else may open it.
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"D:P(A;;GR;;;{config['sid']})(A;;GA;;;SY)(A;;GA;;;OW)", 1, ctypes.byref(descriptor), None):
        raise OSError(ctypes.get_last_error(), "파이프 보안 설명자")
    attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    invalid = wintypes.HANDLE(-1).value

    def instance(first=False):
        # PIPE_ACCESS_OUTBOUND (+ FILE_FLAG_FIRST_PIPE_INSTANCE: refuse a name someone already holds);
        # PIPE_TYPE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS
        handle = kernel32.CreateNamedPipeW(pipe_name(config["username"]), 0x2 | (0x00080000 if first else 0), 0x8, 255,
                                           8192, 8192, 0, ctypes.byref(attributes))
        if handle == invalid:
            raise OSError(ctypes.get_last_error(), "파이프를 만들 수 없습니다")
        return handle
    handle = instance(first=True)
    while True:
        connected = kernel32.ConnectNamedPipe(handle, None) or ctypes.get_last_error() == 535  # ERROR_PIPE_CONNECTED
        waiting = instance()  # the next client never finds the name missing
        try:
            if connected:
                with lock:
                    answer = ({"Authorization": "Bearer " + cache["token"]} if time.monotonic() < cache.get("until", 0)
                              else {"error": "엔드포인트 활성화·정책 연결이 필요합니다"})
                data = json.dumps(answer).encode()
                written = wintypes.DWORD()
                kernel32.WriteFile(handle, data, len(data), ctypes.byref(written), None)
                kernel32.FlushFileBuffers(handle)
                kernel32.DisconnectNamedPipe(handle)
        finally:
            kernel32.CloseHandle(handle)
        handle = waiting


def header(args):
    import getpass
    for _ in range(20):
        try:
            # os.open, not open(): the buffered file object's setup fails on a pipe with EINVAL.
            descriptor = os.open(pipe_name(getpass.getuser()), os.O_RDONLY | os.O_BINARY)
        except OSError:  # busy, or the service is restarting
            time.sleep(0.1)
            continue
        data = b""
        try:
            # One small answer, then the broker disconnects (reported as EINVAL/EPIPE, not EOF).
            while chunk := os.read(descriptor, 8192):
                data += chunk
        except OSError:
            pass
        finally:
            os.close(descriptor)
        try:
            response = json.loads(data)
            break
        except ValueError:
            continue
    else:
        response = None
    if not isinstance(response, dict) or set(response) != {"Authorization"}:
        # 헤더가 없으면 하네스가 OAuth 인증 대기로 표시·캐시해 복구 뒤에도 연결하지 않는다(D-148 PJ1).
        # 게이트웨이가 거부하는 고정 값이면 연결 실패로만 남아 다음 연결에서 다시 시도된다.
        print("관리형 연결 불가: 엔드포인트 활성화·정책 연결이 필요합니다", file=sys.stderr)
        response = {"Authorization": "Bearer endpoint-not-active"}
    print(json.dumps(response))


# -- commands ---------------------------------------------------------------------

CREATE_ACCOUNT = """
$existing = Get-LocalUser -Name $in.name -ErrorAction SilentlyContinue
if (-not $existing) { New-LocalUser -Name $in.name -NoPassword -FullName 'MCP managed harness account' -Description 'MCP Gateway managed harness account' | Out-Null }
"@ok" | Out-Null
"""
HARNESS = ("codex.exe", "codex-code-mode-host.exe", "claude.exe")


def managed_user(name, *, isolated=False):
    """The employee's own account when it is a standard one, else a created standard companion.

    An administrator cannot be confined by rules they can remove, and Windows has no way to run a
    program as another local account without that account's password, so the companion is one the
    employee signs in to. It is created without a password: Windows restricts blank-password local
    accounts to console sign-in, and the employee sets one at first sign-in.
    """
    person = account(name)
    if not person["admin"] and not isolated:
        return name, person, False
    companion = ("mcpgw-" + name)[:20]
    powershell(CREATE_ACCOUNT, {"name": companion})
    created = account(companion)
    if created["admin"]:
        raise ValueError(f"{companion} 계정에 관리자 권한이 있어 통제를 설치할 수 없습니다")
    return companion, created, True


def prepare_profile(name, person):
    """Create the companion's hive without a password or an interactive first sign-in."""
    if person.get("profile") and (Path(person["profile"]) / "NTUSER.DAT").is_file():
        return person
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    create = userenv.CreateProfile
    create.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    create.restype = ctypes.c_int32
    profile = ctypes.create_unicode_buffer(32768)
    result = create(person["sid"], name, profile, len(profile))
    if result < 0:
        raise ValueError("관리 계정 프로필 생성 실패")
    ready = account(name)
    if not ready.get("profile") or not (Path(ready["profile"]) / "NTUSER.DAT").is_file():
        raise ValueError("관리 계정 프로필 확인 실패")
    return ready


def place_harnesses(source_profile):
    """Copy the official harness executables where every account can run them, and pin the digests.

    Windows confinement is scoped to the account's SID, not to a program path, so this is about the
    companion account being able to run the harness at all - and a record of what was approved.
    """
    folder = PROGRAMS / "harness"
    lock_down(folder)
    # .local/bin and WinGet/Packages are where Claude Code's native installer and `winget install` put claude.exe.
    roots = [Path(__file__).parent / "harness", Path(source_profile) / "AppData/Roaming/npm/node_modules",
             Path(source_profile) / "AppData/Local/Programs", Path(source_profile) / ".local/bin",
             Path(source_profile) / "AppData/Local/Microsoft/WinGet/Packages", Path(os.environ.get("ProgramFiles", "")) / "nodejs"]
    placed = {}
    for item in HARNESS:
        found = next((candidate for root in roots if root.exists()
                      for candidate in sorted(root.rglob(item)) if candidate.is_file()), None)
        if not found:
            continue
        digest = hashlib.sha256(found.read_bytes()).hexdigest()
        target = folder / item
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            shutil.copyfile(found, target)
        placed[item] = digest
    if "codex.exe" in placed and "codex-code-mode-host.exe" not in placed:
        raise ValueError("Codex와 같은 릴리스의 codex-code-mode-host.exe를 찾지 못했습니다")
    if not placed:
        raise ValueError("공식 Codex 또는 Claude 설치를 찾지 못했습니다. 설치한 뒤 다시 실행하세요")
    return folder, placed


def ours(text, gateway_url):
    """A file this kit rendered: backing it up as the employee's own would put the managed copy back on removal."""
    return (gateway_url + "/mcp/") in text or '"allowManagedHooksOnly": true' in text or "allow_managed_hooks_only = true" in text


def file_version(path):
    """major.minor.build of a PE file's VS_FIXEDFILEINFO, or None."""
    try:
        api = ctypes.WinDLL("version")
        size = api.GetFileVersionInfoSizeW(str(path), None)
        buffer = ctypes.create_string_buffer(size) if size else None
        info, length = ctypes.c_void_p(), ctypes.c_uint()
        if not size or not api.GetFileVersionInfoW(str(path), 0, size, buffer) or not api.VerQueryValueW(
                buffer, "\\", ctypes.byref(info), ctypes.byref(length)) or length.value < 16:
            return None
        fixed = ctypes.cast(info, ctypes.POINTER(ctypes.c_uint32 * 4)).contents  # signature, struct version, MS, LS
        return f"{fixed[2] >> 16}.{fixed[2] & 0xFFFF}.{fixed[3] >> 16}" if fixed[0] == 0xFEEF04BD else None
    except (AttributeError, OSError):
        return None


def harness_versions(profile):
    """claude·codex versions read from their install folders, never by running them: this is the SYSTEM service,
    and the employee's own executable must not run with its rights (D-239)."""
    found = {}
    version = re.compile(r"^\d+\.\d+[0-9A-Za-z.+_-]*$")
    native = sorted((p.name for p in (Path(profile) / ".local/share/claude/versions").glob("*") if version.match(p.name)),
                    key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r"[.+_-]", v)], reverse=True)
    if native:
        found["claude"] = native[0][:40]
    # WinGet and the Codex desktop installer keep no version in the path: the executable's own version resource
    # (read as data, not run). pj3 10-25: WinGet claude.exe 2.1.302.0; codex.exe carries none.
    for name, pattern in (("claude", "AppData/Local/Microsoft/WinGet/Packages/Anthropic.ClaudeCode*/claude.exe"),
                          ("claude", ".local/bin/claude.exe"), ("codex", "AppData/Local/Programs/OpenAI/Codex/bin/codex.exe")):
        for path in sorted(Path(profile).glob(pattern)):
            value = file_version(path)
            if name not in found and value:
                found[name] = value
    for name, package in (("claude", "@anthropic-ai/claude-code"), ("codex", "@openai/codex")):
        manifest = Path(profile) / "AppData/Roaming/npm/node_modules" / package / "package.json"
        if name not in found and manifest.is_file():
            try:
                value = str(json.loads(manifest.read_text(encoding="utf-8")).get("version", ""))
            except (OSError, ValueError):
                continue
            if version.match(value):
                found[name] = value[:40]
    return found


def broadcast_environment():
    """Explorer re-reads the user environment, so a terminal opened after the install has the CA variables."""
    try:
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result))
    except (AttributeError, OSError):
        pass


# Ends on ConvertTo-Json: a silenced "no such user" leaves $? false, and powershell.exe -Command then exits 1 (pj3 10-25).
REMOVE_COMPANION = """
$sid = $null
$u = @(Get-LocalUser | Where-Object { $_.Name -eq $in.name })[0]
if ($u -and $u.FullName -eq 'MCP managed harness account') {
  $sid = $u.SID.Value
  Get-ScheduledTask -TaskName ('MCPGatewayTray-' + $sid) -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
  Remove-LocalUser -SID $sid
}
ConvertTo-Json -InputObject $sid -Compress
"""


def previous_installs(employee):
    """This employee's earlier installs in either mode: the same account, or the companion of an isolated one."""
    names = [employee, ("mcpgw-" + employee)[:20]]
    return [name for name in names if (STATE / name.lower() / "config.json").is_file()]


def retire_companion(employee):
    """Switching to simple mode leaves no companion account, tray task or tray folder behind (D-239).
    Its profile folder stays: what the employee kept there is theirs."""
    sid = powershell(REMOVE_COMPANION, {"name": ("mcpgw-" + employee)[:20]})
    if sid:
        tray = PROGRAM_DATA / "MCPGatewayManagedTray" / str(sid)
        for name in ("settings.json", "status.json", "status.tmp"):
            (tray / name).unlink(missing_ok=True)
        if tray.is_dir() and not any(tray.iterdir()):
            tray.rmdir()


def enroll(args):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise ValueError("관리자 권한으로 실행해야 합니다")
    args = argparse.Namespace(**vars(args))
    bundle = json.loads(args.enrollment.read_text(encoding="utf-8"))
    verify_transport(bundle)
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,31}", args.user):
        raise ValueError("일반 사용자 계정 이름을 지정하세요")
    employee = args.user
    isolated = getattr(args, "isolated_account", False)
    source_person = account(employee) if isolated else None
    if isolated:
        args.user, person, companion = managed_user(employee, isolated=True)
        person = prepare_profile(args.user, person)
    else:
        # Simple mode (D-239): the signed-in employee's own account, administrator or not, sessions left running.
        person, companion = account(employee), False
    if not person["profile"] or not (Path(person["profile"]) / "NTUSER.DAT").exists():
        if not companion:
            raise ValueError("해당 계정으로 한 번 로그인해 사용자 프로필을 만든 뒤 설치하세요")
        raise ValueError(f"{args.user} 계정으로 한 번 로그인해 프로필을 만든 뒤 이 파일을 다시 실행하세요")
    if isolated and int(powershell(OWNED_PROCESSES, {"sid": person["sid"]}, timeout=180)):
        raise ValueError(f"{args.user} 계정을 로그아웃한 뒤 다시 실행하세요. 실행 중인 비관리 세션을 남기지 않습니다")
    checked_codex_text(Path(person["profile"]) / ".codex" / "config.toml")
    python = PROGRAMS / "python" / "python.exe"
    if not protected([Path(sys.executable), Path(sys.executable).parent]):
        raise ValueError("보호된 설치 경로의 실행 파일이 필요합니다. 설치 마법사에서 다시 시도하세요")
    helper = f'"{python}" -I -S "{PROGRAMS / "managed-windows.py"}" header'
    bundle["device_key"] = secrets.token_urlsafe(32)
    try:
        enrolled = request(bundle, "/oauth/device-enroll", {
            "enrollment_token": bundle["enrollment_token"], "device_key": bundle["device_key"], "hostname": socket.gethostname(),
            "platform": "windows", "local_username": args.user, "local_sid": person["sid"], "helper_command": helper,
            "mode": "isolated" if isolated else "simple"}, credential=False)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 409, 410):
            raise ValueError("이미 연결되어 있습니다" if previous_installs(employee)
                             else "등록 자격 확인 필요 · 새 키트로 다시 시도") from None
        raise
    config = {k: bundle[k] for k in ("gateway_url", "tailscale_node_id", "device_key")}
    config.update({k: bundle[k] for k in ("ca_certificate", "ca_sha256") if k in bundle})
    folder = STATE / args.user.lower()
    config.update(endpoint_id=enrolled["endpoint_id"], username=args.user, sid=person["sid"], profile=person["profile"],
                  mode="isolated" if isolated else "simple", firewall_baseline=str(folder / "firewall-baseline.json"))
    policy = request(config, "/api/endpoint/managed-policy")
    if policy["tailscale_node_id"] != config["tailscale_node_id"]:
        raise ValueError("설치 키트와 정책의 Gateway 노드가 다릅니다")
    if set(policy["files"]) != set(FILES) | {CODEX_BLOCK}:
        raise ValueError("지원하지 않는 관리형 파일 목록")
    config.update(gateway_ips=policy["gateway_ips"], gateway_port=policy["gateway_port"], proxy_port=policy.get("proxy_port"),
                  policy_hash=policy["policy_hash"])
    registration = {"employee": employee, "config": config, "policy": policy, "enrolled": enrolled,
                    "companion": companion, "source_person": source_person}
    if getattr(args, "registration", None):
        write_file(args.registration, json.dumps(registration))
    return registration


def install(args):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise ValueError("관리자 권한으로 실행해야 합니다")
    receipt = getattr(args, "registration", None)
    if receipt:
        if not protected([receipt, receipt.parent]):
            raise ValueError("보호된 등록 파일이 필요합니다")
        registration = json.loads(receipt.read_text(encoding="utf-8"))
    else:
        registration = enroll(args)
    employee = registration["employee"]
    config, policy, enrolled = (registration[k] for k in ("config", "policy", "enrolled"))
    isolated = getattr(args, "isolated_account", False)
    if args.user != employee or config["mode"] != ("isolated" if isolated else "simple"):
        raise ValueError("등록 계정 확인 실패")
    args.user = config["username"]
    person = account(args.user)
    if person["sid"] != config["sid"] or person["profile"] != config["profile"]:
        raise ValueError("등록 계정 확인 실패")
    companion, source_person = registration["companion"], registration["source_person"]
    python = PROGRAMS / "python" / "python.exe"
    lock_down(PROGRAMS)
    for name in ("managed-windows.py", "agent.py", "os-observer-windows.py", "offline_buffer.py", "windows_status.py", "kit_screen.py"):
        source = Path(__file__).parent / name
        if source.resolve() != (PROGRAMS / name).resolve():
            write_file(PROGRAMS / name, source.read_text(encoding="utf-8"))
    # Only a completed enrollment and policy fetch may retire the employee's working installation.
    for previous in previous_installs(employee):
        if previous.lower() != args.user.lower():
            rollback(argparse.Namespace(user=previous))
        else:
            powershell(STOP_SERVICE, {"name": TASK.format(user=args.user.lower()), "rules": []})
    if not isolated:
        retire_companion(employee)
    powershell(". $in.trust; New-EndpointProtectedDirectory $in.base; New-EndpointProtectedDirectory $in.tray $in.sid",
               {"trust": str(PROGRAMS / "windows-trust.ps1"), "base": str(PROGRAM_DATA / "MCPGatewayManagedTray"),
                "tray": str(PROGRAM_DATA / "MCPGatewayManagedTray" / person["sid"]), "sid": person["sid"]})
    if isolated:
        harness_folder, harnesses = place_harnesses(source_person["profile"])
    else:
        harness_folder, harnesses = None, harness_versions(person["profile"])
    folder = STATE / args.user.lower()
    lock_down(folder, readers=False)
    config_path = folder / "config.json"
    write_file(config_path, json.dumps(config))
    for name, target in FILES.items():
        if target.exists() and not (folder / (name + ".backup")).exists() and not ours(target.read_text(encoding="utf-8"), config["gateway_url"]):
            write_file(folder / (name + ".backup"), target.read_text(encoding="utf-8"))
    if codex_config(config).exists() and not (folder / "config.toml.backup").exists():
        write_file(folder / "config.toml.backup", codex_config(config).read_text(encoding="utf-8"))
    apply_policy(config, policy)
    if isolated:
        launcher_folder, launcher_files = harness_launchers(config, harness_folder, harnesses)
        set_user_environment(config, {**(policy.get("proxy_environment") or {}), "PATH_APPEND": str(launcher_folder)})
        powershell(APPLY_RULES, {"rules": firewall_rules(args.user, person["sid"], policy["gateway_ips"], ports(policy))})
        write_file(Path(config["firewall_baseline"]), json.dumps({"rules": rule_state(config)["rules"]}))
    else:
        # The employee's own harnesses trust the Gateway's CA through their user environment. No firewall rule,
        # no PATH entry, no copied harness; Claude takes the model proxy from the managed settings (D-239).
        launcher_files = {}
        set_user_environment(config, ca_environment(config))
        broadcast_environment()
    pythonw = python.with_name("pythonw.exe")
    powershell("""
$a = New-ScheduledTaskAction -Execute $in.python -Argument $in.arguments
$t = New-ScheduledTaskTrigger -AtStartup
$p = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$s = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $in.name -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName $in.name
""", {"python": str(pythonw), "name": TASK.format(user=args.user.lower()),
      "arguments": f'-B -I -S "{PROGRAMS / "managed-windows.py"}" serve --config "{config_path}"'})
    args.enrollment.unlink()
    print(json.dumps({"endpoint_id": config["endpoint_id"], "employee": employee, "managed_account": args.user,
                      "mode": config["mode"], "state": "active" if enrolled.get("state") == "active"
                      else "pending-organization-activation", "harnesses": harnesses if isolated else {},
                      "versions": {} if isolated else harnesses, "launcher_files": launcher_files,
                      "task": TASK.format(user=args.user.lower())}, ensure_ascii=False))
    if isolated:
        print("\n연결을 신청했습니다. 조직 관리자가 콘솔에서 활성화하면 사용할 수 있습니다.")
        if companion:
            print(f"{args.user} 계정으로 로그인해 비밀번호를 정하고, 그 계정에서 codex 또는 claude를 실행하세요.")
        print("처음 한 번은 codex login --device-auth 로 모델 로그인을 하세요.")
        print("Claude 모델 로그인: claude auth login")


def ca_environment(config):
    """Simple mode: the CA file every account may read, named in the employee's environment for both harnesses."""
    if not config.get("ca_certificate"):
        return {}
    folder = PROGRAMS / "launchers" / config["sid"]
    lock_down(folder)
    ca = folder / "root.crt"
    write_file(ca, config["ca_certificate"])
    return {"NODE_EXTRA_CA_CERTS": str(ca), "CODEX_CA_CERTIFICATE": str(ca)}


def serve(args):
    config = json.loads(args.config.read_text(encoding="utf-8"))
    verify_transport(config)
    log = args.config.with_name("service.log")
    cache, lock = {}, threading.Lock()
    threading.Thread(target=serve_pipe, args=(config, cache, lock), daemon=True).start()
    observer_config = args.config.with_name("observer.json")
    write_file(observer_config, json.dumps({
        "ENDPOINT_GATEWAY_URL": config["gateway_url"], "ENDPOINT_DEVICE_KEY": config["device_key"], "ENDPOINT_ID": config["endpoint_id"],
        "ENDPOINT_CA_CERTIFICATE": config.get("ca_certificate", ""), "ENDPOINT_CA_SHA256": config.get("ca_sha256", ""),
        "ENDPOINT_CONFIG_PATHS": os.pathsep.join([str(Path(config["profile"]) / ".claude.json"), str(Path(config["profile"]) / ".codex"),
                                                  str(FILES["managed-mcp.json"].parent), str(FILES["requirements.toml"].parent)]),
        "ENDPOINT_TAILSCALE_NODE_ID": config["tailscale_node_id"], "ENDPOINT_MANAGED_SID": config["sid"],
        "ENDPOINT_PROCESS_SID": config["sid"], "ENDPOINT_PROCESS_SCAN": "1", "ENDPOINT_NETSCAN": "0",
        "ENDPOINT_ORIGIN": "automatic"}))
    previous = config["policy_hash"]
    last_state = None
    from windows_status import publish
    status_path = PROGRAM_DATA / "MCPGatewayManagedTray" / config["sid"] / "status.json"

    def record(entry):
        if log.exists() and log.stat().st_size > 1_000_000:
            log.unlink()
        with open(log, "a", encoding="utf-8") as output:
            output.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}, ensure_ascii=False) + "\n")
    latest = {"inventory": "pending", "os": {"state": "failed", "error_code": "not_run", "accepted_count": 0}}

    def observe():
        # Beside the heartbeat, not inside it: up to 85 seconds spent here is time in which an activation by
        # the organization goes unnoticed and the employee's harness gets the not-active placeholder.
        while True:
            inventory_status = "success"
            try:  # configuration inventory is independent from OS event observation
                subprocess.run([sys.executable, "-B", "-I", "-S", str(PROGRAMS / "agent.py"), "--config", str(observer_config), "--once"],
                               check=True, timeout=40, capture_output=True)
            except (OSError, subprocess.SubprocessError) as exc:
                inventory_status = type(exc).__name__
            os_observer = {"state": "failed", "error_code": "collector_failed", "accepted_count": 0}
            try:  # OS events are separately gated, scoped and reported; disabled is never mapped to success.
                done = subprocess.run(
                    [sys.executable, "-B", "-I", "-S", str(PROGRAMS / "os-observer-windows.py"),
                     "--config", str(observer_config)], check=True, timeout=45, capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
                lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
                if lines:
                    candidate = json.loads(lines[-1])
                    if isinstance(candidate, dict) and candidate.get("channel") == "os":
                        os_observer = candidate
                    else:
                        os_observer["error_code"] = "invalid_collector_output"
                else:
                    os_observer["error_code"] = "missing_collector_output"
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                os_observer["error_code"] = type(exc).__name__
            with lock:
                latest.update(inventory=inventory_status, os=os_observer)
            time.sleep(55)
    threading.Thread(target=observe, daemon=True).start()
    while True:
        pause = 10  # until the organization activates the device: the first token follows within seconds
        try:
            verify_transport(config)
            policy = request(config, "/api/endpoint/managed-policy")
            if (policy["gateway_ips"] != config["gateway_ips"] or policy["gateway_port"] != config["gateway_port"]
                    or policy.get("proxy_port") != config.get("proxy_port") or policy["gateway_url"] != config["gateway_url"]
                    or policy["tailscale_node_id"] != config["tailscale_node_id"]):
                raise ValueError("Gateway 네트워크 변경은 조직 관리자의 재설치가 필요합니다")
            if previous != policy["policy_hash"]:
                apply_policy(config, policy)
                config["policy_hash"] = policy["policy_hash"]
                write_file(args.config, json.dumps(config))
            previous = policy["policy_hash"]
            if config.get("mode") == "simple" and restore_codex_block(config, policy):
                record({"codex_block": "restored"})
            findings = []
            hashes, health = checks(config, policy, findings=findings)
            beat = {"policy_hash": policy["policy_hash"], "configuration_hashes": hashes, "checks": health,
                    "user_command_settings": findings}
            try:
                beat["host"] = host_report(config)
            except (OSError, KeyError, ValueError, IndexError):
                pass  # informational; never holds back the heartbeat
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("agent.py"))
                probe = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(probe)
                beat["network_quality"] = probe.measure_gateway(config["gateway_url"], context=verify_transport(config))
            except (OSError, KeyError, ValueError):
                pass  # a failed measurement is simply absent
            try:
                report = request(config, "/api/endpoint/heartbeat", beat)
            except urllib.error.HTTPError as exc:
                if exc.code != 422 or "network_quality" not in beat:
                    raise
                beat.pop("network_quality")  # a Gateway older than this report rejects the extra field
                report = request(config, "/api/endpoint/heartbeat", beat)
            if report["state"] == "active" and report["compliant"]:
                token = request(config, "/oauth/device-token", {})
                with lock:
                    cache.update(token=token["access_token"], until=time.monotonic() + TOKEN_CACHE_SECONDS)
                # One fast round after the activation: the active-state guidance comes with the next policy fetch;
                # until then Claude tells the employee the PC still waits (pj3 10-25: up to a minute).
                pause = 60 if last_state == "active" else 10
            else:
                with lock:
                    cache.clear()
            last_state = report["state"]
            with lock:
                inventory_status, os_observer = latest["inventory"], latest["os"]
            record({"endpoint_id": config["endpoint_id"], "state": report["state"], "checks": health,
                    "config_inventory": inventory_status, "os_observer": os_observer})
            management = {"active": "활성", "pending": "활성화 대기", "quarantined": "격리됨", "revoked": "철회됨"}.get(report["state"], "확인 필요")
            # Connected means the authenticated heartbeat above succeeded. A partial process snapshot or a failed
            # inventory is a completeness result the Gateway already received; it is in service.log, not a lost link.
            # The tray shows the approved servers, the state and the versions; no key, token or policy text.
            publish(status_path, True, os_observer.get("recent_blocks", []), management,
                    details={"state": report["state"], "servers": sorted(policy["servers"]), "mode": config.get("mode", "isolated"),
                             "harnesses": beat.get("host", {}).get("harnesses", {}), "gateway": config["gateway_url"],
                             "protected_configs": health.get("protected_configs")})
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            with lock:
                cache.clear()
            record({"state": "connection-stopped", "error": type(exc).__name__, "status": getattr(exc, "code", None),
                    "reason": str(exc)[:200]})
            publish(status_path, False, management="확인 필요")
        time.sleep(pause)


# Simple mode has no firewall rules: the silenced misses leave $? false, so the script ends on a statement that succeeds.
STOP_SERVICE = """
$t = Get-ScheduledTask -TaskName $in.name -ErrorAction SilentlyContinue
if ($t) {
  Stop-ScheduledTask -TaskName $in.name; $end = [DateTime]::UtcNow.AddSeconds(30)
  while ((Get-ScheduledTask -TaskName $in.name).State -eq 'Running') {
    if ([DateTime]::UtcNow -gt $end) { throw '엔드포인트 종료 시간 초과' }; Start-Sleep -Milliseconds 100 }
  Unregister-ScheduledTask -TaskName $in.name -Confirm:$false
}
foreach ($n in $in.rules) { Remove-NetFirewallRule -Name $n -ErrorAction SilentlyContinue }
"@ok" | Out-Null
"""


def rollback(args):
    """Run after the device credential is revoked in the Console and the account is signed out."""
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise ValueError("관리자 권한 PowerShell에서 실행하세요")
    folder = STATE / args.user.lower()
    config_path = folder / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {
        **account(args.user), "username": args.user}
    path = codex_config(config)
    current = checked_codex_text(path)
    owned = folder / CODEX_BLOCK
    try:
        current = without_codex_block(current, owned.read_text(encoding="utf-8") if owned.exists() else None)
    except ValueError:
        shutil.copyfile(path, path.with_name(path.name + ".mcpgw-" + secrets.token_hex(4) + ".backup"))
        raise
    powershell(STOP_SERVICE, {"name": TASK.format(user=args.user.lower()), "rules": [f"MCPGW-{args.user}-{r}" for r in RULES]})
    tray = PROGRAM_DATA / "MCPGatewayManagedTray" / config["sid"]
    if tray.is_dir():
        from windows_status import publish
        publish(tray / "status.json", False, management="제거됨", details={"state": "removed"})
    for name, target in FILES.items():
        backup = folder / (name + ".backup")
        if backup.exists():
            lock_down(target.parent)
            write_file(target, backup.read_text(encoding="utf-8"))
        elif target.exists() and (config_path.exists() or "managed-windows.py" in target.read_text(encoding="utf-8") or
                                  ours(target.read_text(encoding="utf-8"), config.get("gateway_url", "https://invalid.invalid"))):
            target.unlink()
    if path.exists():
        write_file(path, current)
    set_user_environment(config, {}, owned_only=not config_path.exists())
    launcher_folder = PROGRAMS / "launchers" / config["sid"]
    for name in ("root.crt", "claude.cmd", "codex.cmd"):
        (launcher_folder / name).unlink(missing_ok=True)
    if launcher_folder.exists() and not any(launcher_folder.iterdir()):
        launcher_folder.rmdir()
    if launcher_folder.parent.exists() and not any(launcher_folder.parent.iterdir()):
        launcher_folder.parent.rmdir()
    if folder.exists():
        for item in folder.iterdir():
            item.unlink()
        folder.rmdir()
    broadcast_environment()
    powershell(STOP_SERVICE, {"name": "MCPGatewayTray-" + config["sid"], "rules": []})
    for name in ("settings.json", "status.json", "status.tmp"):
        (tray / name).unlink(missing_ok=True)
    if tray.is_dir() and not any(tray.iterdir()):
        tray.rmdir()
    print("해당 계정의 방화벽 규칙·관리형 설정·예약 작업을 제거했습니다")


def probe(args):
    """The tray's 연결 확인, as the signed-in employee (never elevated): ① a model answer from their own harness,
    ② the tool count and ③ one approved server's initialize, with the header their harness gets (D-239)."""
    import getpass
    import io
    import importlib.util
    import contextlib
    spec = importlib.util.spec_from_file_location("probe_observer", Path(__file__).with_name("agent.py"))
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    settings = json.loads(Path(args.settings).read_text(encoding="utf-8"))
    status = json.loads(Path(settings["status_path"]).read_text(encoding="utf-8"))
    servers = status.get("servers") or []
    out = {"servers": len(servers)}
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(io.StringIO()):
        header(argparse.Namespace())
    authorization = json.loads(captured.getvalue().strip().splitlines()[-1])["Authorization"]
    if authorization.startswith("Bearer endpoint-not-active"):
        out["connection"] = {"initialized": [], "failed": {}, "tools": 0, "waiting": status.get("state") or "pending"}
    else:
        context = observer.tls_context(settings.get("ca_certificate") or "", settings.get("ca_sha256") or "")
        out["connection"] = observer.connection_check(settings["gateway_url"], context, authorization, servers)
    harness = next((shutil.which(name) for name in ("claude", "codex") if shutil.which(name)), None)
    if harness and not args.skip_model:
        name = Path(harness).stem.lower()
        argv = ([harness, "-p", observer.MODEL_PROMPT] if name == "claude"
                else [harness, "exec", "--skip-git-repo-check", observer.MODEL_PROMPT])
        out["model"] = {"harness": name, **observer.model_check(argv, cwd=os.path.expanduser("~"))}
    else:
        out["model"] = {"harness": None, "ok": False, "seconds": 0, "detail": "하네스 없음" if not harness else "건너뜀"}
    out["user"] = getpass.getuser()
    print(json.dumps(out, ensure_ascii=False))


def self_check():
    assert complement(["100.83.175.111"]) == ["0.0.0.0-100.83.175.110", "100.83.175.112-255.255.255.255",
                                              "::-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"]
    assert complement(["0.0.0.0", "fd7a:115c:a1e0::1"])[0] == "0.0.0.1-255.255.255.255"
    assert other_ports([443, 3128]) == ["1-442", "444-3127", "3129-65535"]
    assert other_ports([1, 65535]) == ["2-65534"]
    rules = firewall_rules("kim", "S-1-5-21-1-2-3-1001", ["100.83.175.111"], [443, 3128])
    assert [r["Name"] for r in rules] == ["MCPGW-kim-egress", "MCPGW-kim-gateway-tcp", "MCPGW-kim-gateway-udp"]
    assert all(r["LocalUser"] == "D:(A;;CC;;;S-1-5-21-1-2-3-1001)" for r in rules)
    text = with_codex_block('model = "x"\n', "\n[mcp_servers.a]\nurl = \"u\"\n")
    assert text.startswith('model = "x"\n\n' + BEGIN) and codex_block(text) == "\n[mcp_servers.a]\nurl = \"u\"\n"
    assert codex_block(with_codex_block(text, "\n[mcp_servers.b]\n")) == "\n[mcp_servers.b]\n"
    assert codex_block("no block") is None
    print("managed-windows self-check OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command, run in (("install", install), ("enroll", enroll)):
        setup = commands.add_parser(command)
        setup.add_argument("--user", required=True)
        setup.add_argument("--isolated-account", action="store_true", help="고급: 별도 표준 계정과 방화벽으로 격리")
        setup.add_argument("--enrollment", type=Path, default=Path(__file__).with_name("enrollment.json"))
        setup.add_argument("--registration", type=Path)
        setup.set_defaults(run=run)
    service = commands.add_parser("serve")
    service.add_argument("--config", type=Path, required=True)
    service.set_defaults(run=serve)
    commands.add_parser("header").set_defaults(run=header)
    check = commands.add_parser("probe")
    check.add_argument("--settings", required=True)
    check.add_argument("--skip-model", action="store_true")
    check.set_defaults(run=probe)
    remove = commands.add_parser("rollback")
    remove.add_argument("--user", required=True)
    remove.set_defaults(run=rollback)
    commands.add_parser("self-check").set_defaults(run=lambda _: self_check())
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Never echo requests, credentials, response bodies or header dictionaries.
        parser.exit(1, "관리형 설치/연결 실패: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
