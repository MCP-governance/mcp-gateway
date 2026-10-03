#!/usr/bin/env python3
"""Administrator-installed ordinary-user enrollment, policy service and header broker.

The installer needs root, systemd, AppArmor, nft and native (ELF) Codex/Claude.
Only the root service holds the device key. SO_PEERCRED binds the local token socket
to the enrolled UID. This is not remote attestation against compromised root.
"""
import argparse
import grp
import hashlib
import importlib.util
import json
import os
import pwd
import secrets
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

FILES = {"managed-mcp.json": Path("/etc/claude-code/managed-mcp.json"),
         "managed-settings.json": Path("/etc/claude-code/managed-settings.json"),
         "requirements.toml": Path("/etc/codex/requirements.toml"),
         "managed_config.toml": Path("/etc/codex/managed_config.toml")}
PROGRAMS = Path("/usr/local/lib/mcpgw-managed")
STATE = Path("/var/lib/mcpgw-managed")
PRIVILEGED = {"sudo", "wheel", "docker", "lxd", "libvirt", "root"}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protected(path):
    return all(p.stat().st_uid == 0 and not p.stat().st_mode & 0o022 for p in (path, *path.parents))


def private_write(path, content):
    # Atomic and never follow an existing output symlink.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix=".mcpgw-")
    temporary = Path(filename)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def request(config, path, body=None, *, credential=True):
    headers = {"Content-Type": "application/json"}
    if credential:
        headers["X-Endpoint-Key"] = config["device_key"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(config["gateway_url"] + path, data=data, headers=headers)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("장치 자격을 다른 주소로 전달하지 않습니다")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=15) as response:
        return json.loads(response.read(131072))


def verify_transport(config):
    observer = load_module("transport_observer", Path(__file__).with_name("agent.py"))
    observer.GATEWAY_URL = config["gateway_url"]
    observer.CONFIG["ENDPOINT_TAILSCALE_NODE_ID"] = config.get("tailscale_node_id", "")
    observer.validate_gateway()
    parsed = urlsplit(config["gateway_url"])
    if parsed.path not in ("", "/") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Gateway 기본 주소만 허용합니다")


def apply_policy(policy):
    if set(policy["files"]) != set(FILES):
        raise ValueError("지원하지 않는 관리형 파일 목록")
    for name, target in FILES.items():
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if not protected(target.parent) or target.is_symlink():
            raise ValueError("관리형 설정 경로가 보호되지 않았습니다")
        private_write(target, policy["files"][name])
        target.chmod(0o644)


def checks(config, policy):
    uid, name = config["uid"], "mcpgw-" + config["username"]
    account = pwd.getpwnam(config["username"])
    groups = {grp.getgrgid(g).gr_name for g in os.getgrouplist(account.pw_name, account.pw_gid)}
    profiles = Path("/sys/kernel/security/apparmor/profiles").read_text()
    rule_file = Path("/usr/local/lib/mcpgw-enforcement") / name / "egress.nft"
    nft = subprocess.run(["nft", "-j", "list", "table", "inet", f"mcpgw_uid_{uid}"], capture_output=True, check=True, text=True)
    # Compare the actual kernel expressions to the root-installed file, excluding
    # volatile packet counters/handles. Removing or broadening a rule is a mismatch.
    expected = subprocess.run(["nft", "-j", "-c", "-f", str(rule_file)], capture_output=True, text=True, check=True)
    # nft -c checks syntax but does not emit a ruleset. Retain a canonical kernel
    # baseline captured immediately after installation; read it on every heartbeat.
    baseline = json.loads(Path(config["nft_baseline"]).read_text())
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k not in {"handle", "counter", "metainfo"}}
        if isinstance(value, list):
            return [stable(item) for item in value if not (isinstance(item, dict) and set(item) <= {"counter", "metainfo"})]
        return value
    hashes = {name: hashlib.sha256(target.read_bytes()).hexdigest() for name, target in FILES.items()}
    return hashes, {"apparmor_enforcing": all(f"{name}{suffix} (enforce)" in profiles for suffix in ("", "-codex", "-claude", "-credential")),
                    "nftables_active": expected.returncode == 0 and stable(json.loads(nft.stdout)) == stable(baseline),
                    "protected_configs": all(protected(p) and not p.is_symlink() and p.stat().st_mode & 0o777 == 0o644 for p in FILES.values()),
                    "ordinary_account": account.pw_uid == uid and account.pw_shell == str(rule_file.parent / "login-shell")
                       and not groups & PRIVILEGED}


def host_report(config):
    """Every other login account on this device. The managed profile confines one UID;
    the rest are reported so the Console shows them as bypass paths, not as enforced."""
    accounts = []
    for entry in pwd.getpwall():
        if (entry.pw_uid in (0, config["uid"], 65534) or entry.pw_uid < 1000
                or entry.pw_shell.endswith(("nologin", "false", "sync"))):
            continue
        groups = set()
        for gid in os.getgrouplist(entry.pw_name, entry.pw_gid):
            try:
                groups.add(grp.getgrgid(gid).gr_name)
            except KeyError:  # a gid with no group entry grants nothing by name
                continue
        accounts.append({"name": entry.pw_name[:64], "uid": entry.pw_uid, "privileged_groups": sorted(groups & PRIVILEGED)})
    return {"kernel": os.uname().release[:120], "wsl": "microsoft" in Path("/proc/version").read_text().lower(),
            "other_accounts": accounts[:64]}


def install(args):
    if os.geteuid() != 0:
        raise ValueError("조직 관리자가 root로 설치해야 합니다")
    person = pwd.getpwnam(args.user)
    if person.pw_uid < 1000 or not person.pw_dir.startswith("/home/"):
        raise ValueError("/home의 실제 일반 사용자만 지원합니다")
    groups = {grp.getgrgid(g).gr_name for g in os.getgrouplist(person.pw_name, person.pw_gid)}
    if groups & PRIVILEGED:
        raise ValueError("관리 권한이 있는 계정에는 일반 사용자 집행을 설치할 수 없습니다")
    if subprocess.run(["pgrep", "-u", str(person.pw_uid)], capture_output=True).returncode == 0:
        raise ValueError("해당 계정의 기존 비관리 세션을 종료한 뒤 설치하세요")
    for dependency in ("gcc", "nft", "apparmor_parser", "systemctl"):
        if not shutil.which(dependency):
            raise ValueError("관리자가 먼저 설치할 필수 구성요소: " + dependency)
    if not Path("/sys/module/apparmor/parameters/enabled").read_text().startswith("Y"):
        raise ValueError("이 시스템에서 AppArmor 집행을 사용할 수 없습니다")
    enforcer = load_module("enforcer", Path(__file__).with_name("enforce-linux.py"))
    binaries = {}
    for name in ("codex", "claude"):
        selected = dict(s.split("=", 1) for s in args.client).get(name)
        candidate = selected or str(Path("/opt/mcpgw-approved") / name)
        binary = enforcer.trusted_binary(candidate)
        if binary.read_bytes()[:4] != b"\x7fELF":
            raise ValueError("공식 native ELF 배포판이 필요합니다: " + name)
        binaries[name] = str(binary)
    source = Path(__file__).parent
    PROGRAMS.mkdir(mode=0o755, parents=True, exist_ok=True)
    if not protected(PROGRAMS):
        raise ValueError("프로그램 경로가 root 관리 경로가 아닙니다")
    for name in ("managed-linux.py", "enforce-linux.py", "agent.py", "os-observer.py"):
        private_write(PROGRAMS / name, (source / name).read_text())
        (PROGRAMS / name).chmod(0o755)
    folder = STATE / args.user
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    if not protected(folder):
        raise ValueError("장치 비밀 경로가 root 관리 경로가 아닙니다")
    config_path = folder / "config.json"
    if config_path.exists():
        raise ValueError("이미 설치된 장치입니다. 기존 자격을 폐기하고 조직 관리자가 제거한 뒤 재설치하세요")
    bundle = json.loads(args.enrollment.read_text())
    verify_transport(bundle)
    bundle["device_key"] = secrets.token_urlsafe(32)
    enrolled = request(bundle, "/oauth/device-enroll", {"enrollment_token": bundle["enrollment_token"], "device_key": bundle["device_key"],
                           "hostname": socket.gethostname(), "local_username": args.user, "local_uid": person.pw_uid}, credential=False)
    config = {k: bundle[k] for k in ("gateway_url", "tailscale_node_id", "device_key")}
    config.update(endpoint_id=enrolled["endpoint_id"], username=args.user, uid=person.pw_uid,
                  socket=f"/run/mcpgw-{args.user}.sock", nft_baseline=str(folder / "nft-baseline.json"))
    private_write(config_path, json.dumps(config))
    policy = request(config, "/api/endpoint/managed-policy")
    if policy["tailscale_node_id"] != config["tailscale_node_id"]:
        raise ValueError("설치 키트와 정책의 Gateway 노드가 다릅니다")
    config.update(gateway_ips=policy["gateway_ips"], gateway_port=policy["gateway_port"], policy_hash=policy["policy_hash"],
                  proxy_port=policy.get("proxy_port"))
    private_write(config_path, json.dumps(config))
    for target in FILES.values():
        if target.exists():
            private_write(folder / (target.name + ".backup"), target.read_text())
    apply_policy(policy)
    subprocess.run([sys.executable, str(PROGRAMS / "enforce-linux.py"), "--user", args.user,
                    "--gateway-port", str(policy["gateway_port"]),
                    *(["--proxy-port", str(policy["proxy_port"]), "--proxy-env", json.dumps(policy["proxy_environment"])]
                      if policy.get("proxy_port") else []),
                    *[part for ip in policy["gateway_ips"] for part in ("--gateway-ip", ip)],
                    *[part for name, binary in binaries.items() for part in ("--client", name + "=" + binary)],
                    "--managed-agent", str(PROGRAMS / "managed-linux.py")], check=True)
    baseline = subprocess.check_output(["nft", "-j", "list", "table", "inet", f"mcpgw_uid_{person.pw_uid}"], text=True)
    private_write(Path(config["nft_baseline"]), baseline)
    unit = f"mcpgw-managed-{args.user}.service"
    Path("/etc/systemd/system", unit).write_text(
        "[Unit]\nDescription=MCP Gateway managed endpoint\nAfter=network-online.target apparmor.service\n"
        f"Requires=mcpgw-egress-{args.user}.service\n\n[Service]\nType=simple\n"
        f"ExecStart=/usr/bin/python3 -I -S {PROGRAMS}/managed-linux.py serve --config {config_path}\n"
        "Restart=always\nRestartSec=10\nUMask=0077\n\n[Install]\nWantedBy=multi-user.target\n")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", unit], check=True)
    args.enrollment.unlink()
    print(json.dumps({"endpoint_id": config["endpoint_id"], "user": args.user, "state": "pending-organization-activation", "service": unit}))


def serve(args):
    if os.geteuid() != 0 or not protected(args.config):
        raise ValueError("root 관리 서비스와 비밀 설정이 필요합니다")
    config = json.loads(args.config.read_text())
    verify_transport(config)
    cache, lock = {}, threading.Lock()
    class Header(socketserver.BaseRequestHandler):
        def handle(self):
            _, uid, _ = struct.unpack("3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            with lock:
                if uid != config["uid"] or time.monotonic() >= cache.get("until", 0):
                    answer = {"error": "엔드포인트 활성화·정책 연결이 필요합니다"}
                else:
                    answer = {"Authorization": "Bearer " + cache["token"]}
            self.request.sendall(json.dumps(answer).encode())
    sock = Path(config["socket"])
    if sock.exists():
        sock.unlink()
    server = socketserver.ThreadingUnixStreamServer(str(sock), Header)
    os.chown(sock, config["uid"], pwd.getpwnam(config["username"]).pw_gid)
    sock.chmod(0o600)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    observer_config = args.config.with_name("observer.json")
    private_write(observer_config, json.dumps({"ENDPOINT_GATEWAY_URL": config["gateway_url"], "ENDPOINT_DEVICE_KEY": config["device_key"],
                 "ENDPOINT_ID": config["endpoint_id"], "ENDPOINT_CONFIG_PATHS": os.pathsep.join([pwd.getpwnam(config["username"]).pw_dir,
                 "/etc/codex", "/etc/claude-code"]), "ENDPOINT_TAILSCALE_NODE_ID": config["tailscale_node_id"], "ENDPOINT_NETSCAN": "0"}))
    previous = config["policy_hash"]
    while True:
        try:
            verify_transport(config)
            policy = request(config, "/api/endpoint/managed-policy")
            if (policy["gateway_ips"] != config["gateway_ips"] or policy["gateway_port"] != config["gateway_port"]
                    or policy["tailscale_node_id"] != config["tailscale_node_id"] or policy["gateway_url"] != config["gateway_url"]
                    # Installs older than the model proxy carry no proxy_port; they keep working without it.
                    or ("proxy_port" in config and policy.get("proxy_port") != config["proxy_port"])):
                raise ValueError("Gateway 네트워크 변경은 조직 관리자의 재설치가 필요합니다")
            if previous != policy["policy_hash"]:
                apply_policy(policy)
                config["policy_hash"] = policy["policy_hash"]
                private_write(args.config, json.dumps(config))
            previous = policy["policy_hash"]
            hashes, health = checks(config, policy)
            beat = {"policy_hash": policy["policy_hash"], "configuration_hashes": hashes, "checks": health}
            try:
                beat["host"] = host_report(config)
            except (OSError, KeyError, ValueError):
                pass  # the account report is informational; it never holds back the heartbeat
            try:
                report = request(config, "/api/endpoint/heartbeat", beat)
            except urllib.error.HTTPError as exc:
                if exc.code != 422 or "host" not in beat:
                    raise
                beat.pop("host")  # a Gateway older than D-62 rejects the extra field
                report = request(config, "/api/endpoint/heartbeat", beat)
            # The token comes first: the observers below can take up to 80 seconds, and a token
            # fetched after them would lapse before the next round.
            if report["state"] == "active" and report["compliant"]:
                token = request(config, "/oauth/device-token", {})
                with lock:
                    cache.update(token=token["access_token"], until=time.monotonic() + 120)
            else:
                with lock:
                    cache.clear()
            observers = {}
            for name, extra in (("agent.py", ["--once"]), ("os-observer.py", ["--uid", str(config["uid"]), "--profile", "mcpgw-" + config["username"]])):
                # Inventory and kernel-event reports are observations; one failing must not cut the
                # enforced account off from the Gateway.
                try:
                    subprocess.run([sys.executable, "-I", "-S", str(PROGRAMS / name), "--config", str(observer_config), *extra],
                                   check=True, timeout=40, stdout=subprocess.DEVNULL)
                    observers[name] = "ok"
                except (OSError, subprocess.SubprocessError) as exc:
                    observers[name] = type(exc).__name__
            print(json.dumps({"endpoint_id": config["endpoint_id"], "state": report["state"], "checks": health,
                              "observers": observers}), flush=True)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            with lock:
                cache.clear()
            print(json.dumps({"state": "connection-stopped", "error": type(exc).__name__,
                              "status": getattr(exc, "code", None), "reason": str(exc)[:200]}), flush=True)
        time.sleep(60)


def header(args):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(8)
        connection.connect(args.socket)
        response = json.loads(connection.recv(8192))
    if set(response) != {"Authorization"}:
        raise ValueError("엔드포인트 활성화·정책 연결이 필요합니다")
    print(json.dumps(response))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install")
    setup.add_argument("--user", required=True)
    setup.add_argument("--enrollment", type=Path, default=Path(__file__).with_name("enrollment.json"))
    setup.add_argument("--client", action="append", default=[])
    setup.set_defaults(run=install)
    service = commands.add_parser("serve")
    service.add_argument("--config", type=Path, required=True)
    service.set_defaults(run=serve)
    helper = commands.add_parser("header")
    helper.add_argument("--socket", required=True)
    helper.set_defaults(run=header)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Never echo requests, credentials, response bodies or header dictionaries.
        parser.exit(1, "관리형 설치/연결 실패: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
