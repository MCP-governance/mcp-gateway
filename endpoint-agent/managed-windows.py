#!/usr/bin/env python3
"""Administrator-installed Windows enrollment, policy service and header broker.

The Windows counterpart of managed-linux.py. An elevated installer enrolls one ordinary
(non-administrator) account. A SYSTEM task holds the device key, writes the harnesses'
machine-wide settings, keeps a per-account Windows Firewall rule that blocks every outbound
destination except the Gateway host's Gateway and model-proxy ports, and hands the account a
short-lived token over a named pipe whose DACL admits only that account's SID.
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
    for command in (["icacls", str(directory), "/setowner", f"*{ADMINISTRATORS}", "/T", "/C", "/Q"],
                    ["icacls", str(directory), "/inheritance:r", "/grant:r", *grants, "/T", "/C", "/Q"]):
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
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def codex_config(config):
    return Path(config["profile"]) / ".codex" / "config.toml"


def codex_block(text):
    match = re.search(re.escape(BEGIN) + r"\n(.*?)" + re.escape(END), text.replace("\r\n", "\n"), re.S)
    return match.group(1) if match else None


def with_codex_block(text, block):
    # Last in the file: a root key after our tables would otherwise fall inside them.
    rest = re.sub(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "\n", text.replace("\r\n", "\n"), flags=re.S).rstrip("\n")
    return (rest + "\n\n" if rest else "") + BEGIN + "\n" + block + END + "\n"


def apply_policy(config, policy):
    files = policy["files"]
    if set(files) != set(FILES) | {CODEX_BLOCK}:
        raise ValueError("지원하지 않는 관리형 파일 목록")
    for directory in {target.parent for target in FILES.values()}:
        lock_down(directory)
    for name, target in FILES.items():
        write_file(target, files[name])
    path = codex_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    write_file(path, with_codex_block(current, files[CODEX_BLOCK]))


def set_user_environment(config, values):
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
        with winreg.CreateKeyEx(winreg.HKEY_USERS, root + r"\Environment", 0, winreg.KEY_SET_VALUE) as key:
            for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
                if values.get(name):
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, values[name])
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
    finally:
        if loaded:
            subprocess.run(["reg", "unload", "HKU\\" + loaded], check=False, capture_output=True)


# -- Gateway ---------------------------------------------------------------------

def request(config, path, body=None, *, credential=True):
    headers = {"Content-Type": "application/json"}
    if credential:
        headers["X-Endpoint-Key"] = config["device_key"]
    data = json.dumps(body).encode() if body is not None else None

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("장치 자격을 다른 주소로 전달하지 않습니다")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
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


def ports(policy):
    return [policy["gateway_port"]] + ([policy["proxy_port"]] if policy.get("proxy_port") else [])


def rule_state(config):
    state = powershell(READ_RULES, {"names": [f"MCPGW-{config['username']}-{r}" for r in RULES]})
    state["rules"] = sorted(state["rules"] or [], key=lambda rule: rule["Name"])
    return state


def checks(config, policy):
    targets = list(FILES.values())
    hashes = {name: hashlib.sha256(target.read_bytes()).hexdigest() for name, target in FILES.items()}
    block = codex_block(codex_config(config).read_text(encoding="utf-8")) if codex_config(config).exists() else None
    hashes[CODEX_BLOCK] = hashlib.sha256((block or "").encode()).hexdigest()
    rules = rule_state(config)
    baseline = json.loads(Path(config["firewall_baseline"]).read_text(encoding="utf-8"))
    return hashes, {
        # Every profile on, and the account's rules exactly as installed (a removed, disabled or
        # broadened rule is a mismatch).
        "firewall_enforcing": all(rules["profiles"]) and rules["rules"] == baseline["rules"],
        "protected_configs": protected(targets + list({t.parent for t in targets}) + [PROGRAMS, Path(sys.executable).parent]),
        "ordinary_account": account(config["username"]) == {"sid": config["sid"], "profile": config["profile"], "admin": False},
    }


def host_report(config):
    accounts = powershell(HOST, {"sid": config["sid"]}) or []
    accounts = accounts if isinstance(accounts, list) else [accounts]
    return {"kernel": ("Windows " + platform.version())[:120], "wsl": False,
            "other_accounts": [{"name": a["name"][:64], "uid": int(a["sid"].rsplit("-", 1)[1]),
                                "privileged_groups": ["Administrators"] if a["admin"] else []} for a in accounts[:64]]}


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
        raise ValueError("관리형 엔드포인트 서비스가 응답하지 않습니다")
    if set(response) != {"Authorization"}:
        raise ValueError("엔드포인트 활성화·정책 연결이 필요합니다")
    print(json.dumps(response))


# -- commands ---------------------------------------------------------------------

def install(args):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise ValueError("조직 관리자가 관리자 권한 PowerShell에서 설치해야 합니다")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,31}", args.user):
        raise ValueError("일반 사용자 계정 이름을 지정하세요")
    person = account(args.user)
    if person["admin"]:
        raise ValueError("관리자 그룹의 계정에는 일반 사용자 통제를 설치할 수 없습니다")
    if not person["profile"] or not (Path(person["profile"]) / "NTUSER.DAT").exists():
        raise ValueError("해당 계정으로 한 번 로그인해 사용자 프로필을 만든 뒤 설치하세요")
    if int(powershell(OWNED_PROCESSES, {"sid": person["sid"]}, timeout=180)):
        raise ValueError("해당 계정을 로그아웃한 뒤 설치하세요. 실행 중인 비관리 세션을 남기지 않습니다")
    python = Path(sys.executable)
    if not protected([python, python.parent]):
        raise ValueError("Python을 모든 사용자용(Program Files)으로 설치한 뒤 그 python.exe로 실행하세요")
    lock_down(PROGRAMS)
    for name in ("managed-windows.py", "agent.py"):
        write_file(PROGRAMS / name, (Path(__file__).parent / name).read_text(encoding="utf-8"))
    folder = STATE / args.user.lower()
    lock_down(folder, readers=False)
    config_path = folder / "config.json"
    if config_path.exists():
        raise ValueError("이미 설치된 장치입니다. 기존 자격을 폐기하고 제거한 뒤 재설치하세요")
    bundle = json.loads(args.enrollment.read_text(encoding="utf-8"))
    verify_transport(bundle)
    helper = f'"{python}" -I -S "{PROGRAMS / "managed-windows.py"}" header'
    bundle["device_key"] = secrets.token_urlsafe(32)
    enrolled = request(bundle, "/oauth/device-enroll", {
        "enrollment_token": bundle["enrollment_token"], "device_key": bundle["device_key"], "hostname": socket.gethostname(),
        "platform": "windows", "local_username": args.user, "local_sid": person["sid"], "helper_command": helper}, credential=False)
    config = {k: bundle[k] for k in ("gateway_url", "tailscale_node_id", "device_key")}
    config.update(endpoint_id=enrolled["endpoint_id"], username=args.user, sid=person["sid"], profile=person["profile"],
                  firewall_baseline=str(folder / "firewall-baseline.json"))
    write_file(config_path, json.dumps(config))
    policy = request(config, "/api/endpoint/managed-policy")
    if policy["tailscale_node_id"] != config["tailscale_node_id"]:
        raise ValueError("설치 키트와 정책의 Gateway 노드가 다릅니다")
    config.update(gateway_ips=policy["gateway_ips"], gateway_port=policy["gateway_port"], proxy_port=policy.get("proxy_port"),
                  policy_hash=policy["policy_hash"])
    write_file(config_path, json.dumps(config))
    for name, target in FILES.items():
        if target.exists():
            write_file(folder / (name + ".backup"), target.read_text(encoding="utf-8"))
    if codex_config(config).exists():
        write_file(folder / "config.toml.backup", codex_config(config).read_text(encoding="utf-8"))
    apply_policy(config, policy)
    set_user_environment(config, policy.get("proxy_environment") or {})
    powershell(APPLY_RULES, {"rules": firewall_rules(args.user, person["sid"], policy["gateway_ips"], ports(policy))})
    write_file(Path(config["firewall_baseline"]), json.dumps({"rules": rule_state(config)["rules"]}))
    powershell("""
$a = New-ScheduledTaskAction -Execute $in.python -Argument $in.arguments
$t = New-ScheduledTaskTrigger -AtStartup
$p = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
$s = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $in.name -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName $in.name
""", {"python": str(python), "name": TASK.format(user=args.user.lower()),
      "arguments": f'-I -S "{PROGRAMS / "managed-windows.py"}" serve --config "{config_path}"'})
    args.enrollment.unlink()
    print(json.dumps({"endpoint_id": config["endpoint_id"], "user": args.user, "state": "pending-organization-activation",
                      "task": TASK.format(user=args.user.lower())}, ensure_ascii=False))


def serve(args):
    config = json.loads(args.config.read_text(encoding="utf-8"))
    log = args.config.with_name("service.log")
    cache, lock = {}, threading.Lock()
    threading.Thread(target=serve_pipe, args=(config, cache, lock), daemon=True).start()
    observer_config = args.config.with_name("observer.json")
    write_file(observer_config, json.dumps({
        "ENDPOINT_GATEWAY_URL": config["gateway_url"], "ENDPOINT_DEVICE_KEY": config["device_key"], "ENDPOINT_ID": config["endpoint_id"],
        "ENDPOINT_CONFIG_PATHS": os.pathsep.join([str(Path(config["profile"]) / ".claude.json"), str(Path(config["profile"]) / ".codex"),
                                                  str(FILES["managed-mcp.json"].parent), str(FILES["requirements.toml"].parent)]),
        "ENDPOINT_TAILSCALE_NODE_ID": config["tailscale_node_id"], "ENDPOINT_NETSCAN": "0"}))
    previous = config["policy_hash"]

    def record(entry):
        if log.exists() and log.stat().st_size > 1_000_000:
            log.unlink()
        with open(log, "a", encoding="utf-8") as output:
            output.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}, ensure_ascii=False) + "\n")
    while True:
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
            hashes, health = checks(config, policy)
            beat = {"policy_hash": policy["policy_hash"], "configuration_hashes": hashes, "checks": health}
            try:
                beat["host"] = host_report(config)
            except (OSError, KeyError, ValueError, IndexError):
                pass  # informational; never holds back the heartbeat
            report = request(config, "/api/endpoint/heartbeat", beat)
            if report["state"] == "active" and report["compliant"]:
                token = request(config, "/oauth/device-token", {})
                with lock:
                    cache.update(token=token["access_token"], until=time.monotonic() + 120)
            else:
                with lock:
                    cache.clear()
            try:  # observation only; a failure never cuts the account off
                subprocess.run([sys.executable, "-I", "-S", str(PROGRAMS / "agent.py"), "--config", str(observer_config), "--once"],
                               check=True, timeout=40, capture_output=True)
                observer = "ok"
            except (OSError, subprocess.SubprocessError) as exc:
                observer = type(exc).__name__
            record({"endpoint_id": config["endpoint_id"], "state": report["state"], "checks": health, "observer": observer})
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            with lock:
                cache.clear()
            record({"state": "connection-stopped", "error": type(exc).__name__, "status": getattr(exc, "code", None),
                    "reason": str(exc)[:200]})
        time.sleep(60)


def rollback(args):
    """Run after the device credential is revoked in the Console and the account is signed out."""
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise ValueError("관리자 권한 PowerShell에서 실행하세요")
    folder = STATE / args.user.lower()
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    powershell("Unregister-ScheduledTask -TaskName $in.name -Confirm:$false -ErrorAction SilentlyContinue; "
               "foreach ($n in $in.rules) { Remove-NetFirewallRule -Name $n -ErrorAction SilentlyContinue }",
               {"name": TASK.format(user=args.user.lower()), "rules": [f"MCPGW-{args.user}-{r}" for r in RULES]})
    for name, target in FILES.items():
        backup = folder / (name + ".backup")
        if backup.exists():
            write_file(target, backup.read_text(encoding="utf-8"))
        elif target.exists():
            target.unlink()
    path = codex_config(config)
    if path.exists():
        backup = folder / "config.toml.backup"
        write_file(path, backup.read_text(encoding="utf-8") if backup.exists() else
                   re.sub(r"\n?" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "\n",
                          path.read_text(encoding="utf-8"), flags=re.S).lstrip("\n"))
    set_user_environment(config, {})
    for item in folder.iterdir():
        item.unlink()
    folder.rmdir()
    print("해당 계정의 방화벽 규칙·관리형 설정·예약 작업을 제거했습니다")


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
    setup = commands.add_parser("install")
    setup.add_argument("--user", required=True)
    setup.add_argument("--enrollment", type=Path, default=Path(__file__).with_name("enrollment.json"))
    setup.set_defaults(run=install)
    service = commands.add_parser("serve")
    service.add_argument("--config", type=Path, required=True)
    service.set_defaults(run=serve)
    commands.add_parser("header").set_defaults(run=header)
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
