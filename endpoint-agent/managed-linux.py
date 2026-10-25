#!/usr/bin/env python3
"""Administrator-installed enrollment, policy service and header broker.

Two modes (D-239). simple (default): the employee's own account keeps running its own harnesses;
the installer writes the managed settings, the header helper and this service, and nothing else.
isolated: an ordinary account confined by AppArmor and a UID nftables table (needs AppArmor, nft
and native ELF Codex/Claude). Only the root service holds the device key. SO_PEERCRED and, in the
isolated enforcement stage, SO_PEERSEC bind the token socket to the enrolled UID and AppArmor identity.
This is not remote attestation against compromised root.
"""
import argparse
import grp
import hashlib
import importlib.util
import json
import os
import pwd
import queue
import re
import secrets
import shutil
import socket
import socketserver
import stat
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
TOKEN_CACHE_SECONDS = 180
# Copied to PROGRAMS by install. The digest of their text is the kit version, the same one /api/health reports
# (full_stack_lab/gateway/app/release.py KIT_PROGRAMS); tests/kit_continuity_check.py keeps the two lists equal.
PROGRAM_FILES = ("managed-linux.py", "enforce-linux.py", "broker_binding.py", "agent.py", "os-observer.py",
                 "offline_buffer.py", "local-runner.py")
STATUS_SHIM = Path("/usr/local/bin/mcpgw-status")
STATUS_STALE_SECONDS = 180
ADDED_SHOWN_SECONDS = 3600
ENFORCEMENT = Path("/usr/local/lib/mcpgw-enforcement")
# Simple mode: the employee's own harnesses trust the Gateway's private CA through the session environment
# (pam_env reads /etc/environment for every login, SSH included); no shell rc file is edited (D-239).
ENVIRONMENT = Path("/etc/environment")
CA_BEGIN, CA_END = "# >>> mcpgw managed ca >>>", "# <<< mcpgw managed ca <<<"
HARNESS_VERSIONS = {}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kit_version(folder):
    digest = hashlib.sha256()
    for name in PROGRAM_FILES:
        digest.update(name.encode() + b"\0" + (Path(folder) / name).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def machine_id():
    """Names this PC to the Gateway, so a reinstall here continues the earlier device and a copy elsewhere does not.
    A hash with a fixed label: the raw /etc/machine-id is never sent."""
    try:
        raw = Path("/etc/machine-id").read_text().strip()
    except OSError:
        return None
    return hashlib.sha256(b"mcpgw-machine:" + raw.encode()).hexdigest() if raw else None


def protected(path):
    return all(p.stat().st_uid == 0 and not p.stat().st_mode & 0o022 for p in (path, *path.parents))


def private_write(path, content):
    # Atomic and never follow an existing output symlink.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix=".mcpgw-")
    temporary = Path(filename)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def request(config, path, body=None, *, credential=True):
    context = verify_transport(config)
    headers = {"Content-Type": "application/json"}
    if credential:
        headers["X-Endpoint-Key"] = config["device_key"]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(config["gateway_url"] + path, data=data, headers=headers)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("장치 자격을 다른 주소로 전달하지 않습니다")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
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
    return observer.tls_context(config.get("ca_certificate", ""), config.get("ca_sha256", ""))


def apply_policy(policy):
    if set(policy["files"]) != set(FILES):
        raise ValueError("지원하지 않는 관리형 파일 목록")
    for name, target in FILES.items():
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        if not protected(target.parent) or target.is_symlink():
            raise ValueError("관리형 설정 경로가 보호되지 않았습니다")
        private_write(target, policy["files"][name])
        target.chmod(0o644)


def checks(config, policy, *, findings=None):
    uid, name = config["uid"], "mcpgw-" + config["username"]
    account = pwd.getpwnam(config["username"])
    commands_ok, commands = load_module("command_settings", Path(__file__).with_name("agent.py")).user_command_settings(getattr(account, "pw_dir", ""))
    if findings is not None:
        findings.extend(commands)
    if config.get("mode") == "simple":
        # Nothing is confined: the managed files, as rendered and root-owned, are all there is to report.
        hashes = {name: hashlib.sha256(target.read_bytes()).hexdigest() for name, target in FILES.items()}
        return hashes, {"protected_configs": all(protected(p) and not p.is_symlink() and p.stat().st_mode & 0o777 == 0o644
                                                 for p in FILES.values())}
    groups = {grp.getgrgid(g).gr_name for g in os.getgrouplist(account.pw_name, account.pw_gid)}
    profiles = set(Path("/sys/kernel/security/apparmor/profiles").read_text().splitlines())
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
    suffixes = (("", "-codex-entry", "-claude-entry", "-bound-codex", "-bound-claude",
                 "-bound-codex-tool", "-bound-claude-tool", "-bound-credential")
                if config.get("broker_binding", "warn") == "enforce" else ("", "-codex", "-claude", "-credential"))
    absent = {"codex", "claude"} - set(config.get("harnesses", ("codex", "claude")))
    suffixes = [suffix for suffix in suffixes if not any(h in suffix for h in absent)]
    return hashes, {"apparmor_enforcing": all(f"{name}{suffix} (enforce)" in profiles for suffix in suffixes),
                    "nftables_active": expected.returncode == 0 and stable(json.loads(nft.stdout)) == stable(baseline),
                    "protected_configs": all(protected(p) and not p.is_symlink() and p.stat().st_mode & 0o777 == 0o644 for p in FILES.values()),
                    "user_command_helpers": commands_ok,
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
            "other_accounts": accounts[:64], **({"harnesses": dict(HARNESS_VERSIONS)} if HARNESS_VERSIONS else {})}


def forget_stale_sign_in(home: str) -> None:
    """Claude Code keeps "needs sign-in" marks for MCP servers in the account's home, and the home
    outlives a reinstall. The managed servers sign in with this device's helper, so a mark left by
    an earlier device hides them as unauthenticated. Every path component is opened without
    following links: the folders belong to the employee's managed account, this runs as root."""
    folder = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in (*Path(home).parts[1:], ".claude"):
            inner = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            os.close(folder)
            folder = inner
        os.unlink("mcp-needs-auth-cache.json", dir_fd=folder)
    except FileNotFoundError:
        pass
    finally:
        os.close(folder)


# -- Launchers the employee's own shells find first. A terminal opened before the install has no launcher
# function, and its PATH (from the session's ~/.profile) lists ~/.local/bin ahead of /usr/local/bin, so
# `claude` there ran the unmanaged copy (10-23 pj2: the model sign-in went to the employee's account).
# Claude Code's native installer leaves a launcher the user replaced in place and keeps installing versions
# beside it; other installers may rewrite theirs, so the service puts ours back (D-228). --
HOME_LAUNCHER_DIRS = (".local/bin", "bin", ".npm-global/bin")
HOME_MARK = b"#!/bin/sh\n# mcpgw home launcher\n"
HOME_LAUNCHER_EVERY = 300


def _open_dir(home, sub):
    """The folder under the employee's home, every component opened without following links."""
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in sub.split("/"):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
    except OSError:
        os.close(fd)
        raise
    return fd


def _is_ours(name, folder):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
    except OSError:
        return False
    try:
        return os.read(fd, len(HOME_MARK)) == HOME_MARK
    finally:
        os.close(fd)


def home_launchers(config):
    """Point the employee's own harness launchers at the managed ones; keep what was there to restore."""
    if config.get("owner_uid") is None:
        return []
    person = pwd.getpwuid(config["owner_uid"])
    keep = STATE / config["username"] / "home-launchers"
    keep.mkdir(mode=0o700, parents=True, exist_ok=True)
    replaced = []
    for sub in HOME_LAUNCHER_DIRS:
        try:
            folder = _open_dir(person.pw_dir, sub)
        except OSError:
            continue
        try:
            for name in config.get("harnesses") or ("codex", "claude"):
                try:
                    info = os.stat(name, dir_fd=folder, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                key = sub.replace("/", "_") + "-" + name
                if stat.S_ISLNK(info.st_mode):
                    (keep / (key + ".symlink")).write_text(os.readlink(name, dir_fd=folder), encoding="utf-8")
                elif stat.S_ISREG(info.st_mode) and not _is_ours(name, folder):
                    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=folder)
                    with os.fdopen(source, "rb") as handle:
                        (keep / key).write_bytes(handle.read())
                else:
                    continue
                os.unlink(name, dir_fd=folder)
                target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755, dir_fd=folder)
                try:
                    os.write(target, HOME_MARK + f'exec /usr/local/bin/{name} "$@"\n'.encode())
                    os.fchown(target, person.pw_uid, person.pw_gid)
                    os.fchmod(target, 0o755)
                finally:
                    os.close(target)
                replaced.append(f"~/{sub}/{name}")
        finally:
            os.close(folder)
    return replaced


def restore_home_launchers(config):
    if config.get("owner_uid") is None:
        return
    person = pwd.getpwuid(config["owner_uid"])
    keep = STATE / config["username"] / "home-launchers"
    for sub in HOME_LAUNCHER_DIRS:
        try:
            folder = _open_dir(person.pw_dir, sub)
        except OSError:
            continue
        try:
            for name in ("codex", "claude"):
                key = sub.replace("/", "_") + "-" + name
                link, copied = keep / (key + ".symlink"), keep / key
                if not (link.is_file() or copied.is_file()) or not _is_ours(name, folder):
                    continue
                os.unlink(name, dir_fd=folder)
                if link.is_file():
                    os.symlink(link.read_text(encoding="utf-8"), name, dir_fd=folder)
                    os.chown(name, person.pw_uid, person.pw_gid, dir_fd=folder, follow_symlinks=False)
                else:
                    target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755, dir_fd=folder)
                    try:
                        os.write(target, copied.read_bytes())
                        os.fchown(target, person.pw_uid, person.pw_gid)
                    finally:
                        os.close(target)
        finally:
            os.close(folder)


def ours(text, gateway_url):
    """A file this kit rendered: backing it up as the employee's own would put the managed copy back on removal."""
    return (gateway_url + "/mcp/") in text or '"allowManagedHooksOnly": true' in text or "allow_managed_hooks_only = true" in text


def edit_environment(values):
    """Our block in /etc/environment: the CA variables, or none. A value the organization already set wins."""
    try:
        text = ENVIRONMENT.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    kept = re.sub(rf"\n?{re.escape(CA_BEGIN)}.*?{re.escape(CA_END)}\n", "\n", text, flags=re.S)
    kept = kept if kept.strip() else ""
    taken = {line.split("=", 1)[0].strip() for line in kept.splitlines() if "=" in line and not line.lstrip().startswith("#")}
    values = {k: v for k, v in values.items() if k not in taken}
    if values:
        kept = (kept.rstrip("\n") + "\n" if kept.strip() else "") + CA_BEGIN + "\n" + "".join(
            f'{k}="{v}"\n' for k, v in values.items()) + CA_END + "\n"
    if kept != text:
        private_write(ENVIRONMENT, kept)
        ENVIRONMENT.chmod(0o644)


def ca_environment(config):
    path = PROGRAMS / f"ca-{config['uid']}.crt"
    return {"NODE_EXTRA_CA_CERTS": str(path), "CODEX_CA_CERTIFICATE": str(path)} if config.get("ca_certificate") else {}


def write_helper(user):
    """Simple mode's header helper, at the path the Gateway renders for every Linux device. A script, not the
    compiled wrapper of the isolated stage: there is no profile to attach and no compiler on the PC (D-239)."""
    folder = ENFORCEMENT / ("mcpgw-" + user)
    for node in (ENFORCEMENT, folder):
        node.mkdir(mode=0o755, exist_ok=True)
        node.chmod(0o755)
    helper = folder / "header-helper"
    private_write(helper, f"#!/bin/sh\nexec /usr/bin/python3 -I -S {PROGRAMS}/managed-linux.py header --socket /run/mcpgw-{user}.sock\n")
    helper.chmod(0o755)


def install(args):
    if os.geteuid() != 0:
        raise ValueError("조직 관리자가 root로 설치해야 합니다")
    # A manual install without --mode (and every caller before D-239) is the isolated one.
    args.mode = getattr(args, "mode", "isolated")
    simple = args.mode == "simple"
    bundle = json.loads(args.enrollment.read_text())
    verify_transport(bundle)
    person = pwd.getpwnam(args.user)
    if person.pw_uid < 1000 or not person.pw_dir.startswith("/home/"):
        raise ValueError("/home의 실제 일반 사용자만 지원합니다")
    groups = {grp.getgrgid(g).gr_name for g in os.getgrouplist(person.pw_name, person.pw_gid)}
    binaries = {}
    selected_clients = dict(s.split("=", 1) for s in args.client)
    if simple:
        # The employee's own harnesses, wherever their installer put them: nothing is copied or pinned.
        binaries = {name: path for name, path in selected_clients.items() if name in ("codex", "claude")}
    else:
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
        # Reject a mistaken owner before spending the one-time enrollment token.
        enforcer.nft_rules(person.pw_uid, [], 443, owner_uid=args.owner_uid)
        if args.owner_uid is not None:
            pwd.getpwuid(args.owner_uid)
        for name in ("codex", "claude"):
            candidate = selected_clients.get(name) or str(Path("/opt/mcpgw-approved") / name)
            if name not in selected_clients and not Path(candidate).is_file():
                continue  # 이 PC에 없는 하네스는 관리 대상에서 뺀다
            binary = enforcer.trusted_binary(candidate)
            if binary.read_bytes()[:4] != b"\x7fELF":
                raise ValueError("공식 native ELF 배포판이 필요합니다: " + name)
            binaries[name] = str(binary)
        # Before the one-time enrollment token is spent, not halfway through the install.
        if not binaries:
            raise ValueError("관리할 하네스(codex·claude)가 없습니다")
        if "codex" in binaries:
            enforcer.companions("codex", Path(binaries["codex"]))
    source = Path(__file__).parent
    PROGRAMS.mkdir(mode=0o755, parents=True, exist_ok=True)
    if not protected(PROGRAMS):
        raise ValueError("프로그램 경로가 root 관리 경로가 아닙니다")
    for name in PROGRAM_FILES:
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
    bundle["device_key"] = secrets.token_urlsafe(32)
    machine = machine_id()
    enrolled = request(bundle, "/oauth/device-enroll", {"enrollment_token": bundle["enrollment_token"], "device_key": bundle["device_key"],
                           "hostname": socket.gethostname(), "local_username": args.user, "local_uid": person.pw_uid,
                           "mode": args.mode, **({"machine_id": machine} if machine else {})}, credential=False)
    config = {k: bundle[k] for k in ("gateway_url", "tailscale_node_id", "device_key")}
    # manifest_pubkey: the approver's key for local MCP manifests, pinned here and never taken from policy.
    config.update({k: bundle[k] for k in ("ca_certificate", "ca_sha256", "manifest_pubkey", "local_engine") if k in bundle})
    ca_path = PROGRAMS / f"ca-{person.pw_uid}.crt"
    if config.get("ca_certificate"):
        private_write(ca_path, config["ca_certificate"])
        ca_path.chmod(0o644)
    # Simple mode answers any process of the employee by UID (broker_binding "uid"): there is no profile to bind to.
    config.update(endpoint_id=enrolled["endpoint_id"], username=args.user, uid=person.pw_uid,
                  owner_uid=None if simple else args.owner_uid, mode=args.mode,
                  broker_binding="uid" if simple else args.broker_binding, harnesses=sorted(binaries),
                  socket=f"/run/mcpgw-{args.user}.sock", nft_baseline=str(folder / "nft-baseline.json"))
    private_write(config_path, json.dumps(config))
    policy = request(config, "/api/endpoint/managed-policy")
    if policy["tailscale_node_id"] != config["tailscale_node_id"]:
        raise ValueError("설치 키트와 정책의 Gateway 노드가 다릅니다")
    config.update(gateway_ips=policy["gateway_ips"], gateway_port=policy["gateway_port"], policy_hash=policy["policy_hash"],
                  proxy_port=policy.get("proxy_port"))
    private_write(config_path, json.dumps(config))
    for target in FILES.values():
        if target.exists() and not ours(target.read_text(), config["gateway_url"]):
            private_write(folder / (target.name + ".backup"), target.read_text())
    apply_policy(policy)
    forget_stale_sign_in(person.pw_dir)
    if simple:
        write_helper(args.user)
        edit_environment(ca_environment(config))
    else:
        subprocess.run([sys.executable, str(PROGRAMS / "enforce-linux.py"), "--user", args.user,
                        *(["--owner-uid", str(args.owner_uid)] if args.owner_uid is not None else []),
                        "--gateway-port", str(policy["gateway_port"]),
                        *(["--ca", str(ca_path)] if config.get("ca_certificate") else []),
                        *(["--proxy-port", str(policy["proxy_port"]), "--proxy-env", json.dumps(policy["proxy_environment"])]
                          if policy.get("proxy_port") else []),
                        *[part for ip in policy["gateway_ips"] for part in ("--gateway-ip", ip)],
                        *[part for name, binary in binaries.items() for part in ("--client", name + "=" + binary)],
                        "--broker-binding", args.broker_binding,
                        "--managed-agent", str(PROGRAMS / "managed-linux.py")], check=True)
        baseline = subprocess.check_output(["nft", "-j", "list", "table", "inet", f"mcpgw_uid_{person.pw_uid}"], text=True)
        private_write(Path(config["nft_baseline"]), baseline)
    unit = f"mcpgw-managed-{args.user}.service"
    Path("/etc/systemd/system", unit).write_text(
        "[Unit]\nDescription=MCP Gateway managed endpoint\nAfter=network-online.target apparmor.service\n"
        + ("" if simple else f"Requires=mcpgw-egress-{args.user}.service\n") + "\n[Service]\nType=simple\n"
        f"ExecStart=/usr/bin/python3 -I -S {PROGRAMS}/managed-linux.py serve --config {config_path}\n"
        "Restart=always\nRestartSec=10\nUMask=0077\n\n[Install]\nWantedBy=multi-user.target\n")
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", unit], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        config["home_launchers"] = [] if simple else home_launchers(config)
    except OSError:
        config["home_launchers"] = []  # a new terminal still gets the launcher function
    args.enrollment.unlink()
    write_status_shim()
    # "active": the Gateway continued the activation of the earlier device of this employee on this PC (D-217).
    print(json.dumps({"endpoint_id": config["endpoint_id"], "user": args.user, "mode": args.mode,
                      "state": "active" if enrolled.get("state") == "active" else "pending-organization-activation",
                      "service": unit, "status_command": str(STATUS_SHIM), "home_launchers": config["home_launchers"]}))


STATE_LABEL = {"active": "활성", "pending": "활성화 대기", "quarantined": "중지 (점검에서 격리됨)",
               "revoked": "중지 (등록 해제됨)", "unknown": "확인 안 됨"}
MODE_LABEL = {"simple": "간편 모드 (게이트웨이 판정)", "isolated": "격리 계정"}


def status_path(user, suffix):
    return PROGRAMS / f"status-{user}.{suffix}"


def next_step(summary, now, environment=None):
    """One line: what the employee does next, from the state the service last wrote."""
    environment = os.environ if environment is None else environment
    if now - (summary.get("updated") or 0) > STATUS_STALE_SECONDS:
        return f"서비스 다시 시작: sudo systemctl restart mcpgw-managed-{summary.get('user', '<계정>')}"
    state = summary.get("state", "unknown")
    if state == "pending":
        return "관리자 활성화 대기 — 관리자가 활성화하면 자동으로 연결됩니다"
    if state == "quarantined":
        return "관리자에게 격리 해제를 요청하세요"
    if state == "revoked":
        return "콘솔 내 PC 연결에서 새 설치 파일을 받아 다시 설치하세요"
    if not summary.get("connected"):
        return "게이트웨이 연결을 확인하세요 (네트워크·VPN)"
    # A terminal opened before the install lacks the CA variable: the harness cannot reach the Gateway from it.
    ca = summary.get("ca")
    if summary.get("mode") == "simple" and ca and environment.get("NODE_EXTRA_CA_CERTS") != ca:
        # The managed settings carry the CA for Claude when the Gateway renders it; Codex reads only the session.
        return ("claude는 지금 실행해도 됩니다 · codex는 새 터미널(또는 다시 로그인)에서 실행하세요" if summary.get("claude_ca")
                else "새 터미널(또는 다시 로그인)에서 claude·codex를 실행하세요")
    return "claude 또는 codex를 실행하세요"


def render_status(summary, now, environment=None):
    """What the employee reads: the state, the Gateway, the last report, the kit and the approved servers.
    Only these fields leave the root-owned service; no key, token or policy text."""
    def clock(moment):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(moment))
    updated = summary.get("updated") or 0
    silent = now - updated > STATUS_STALE_SECONDS
    state = "unknown" if silent else summary.get("state", "unknown")
    last, servers = summary.get("last_report"), summary.get("servers")
    local = summary.get("local") or {}
    prepared = f"{local['ready']}/{local['total']}" if local.get("total") else "—"
    lines = [f"장치 상태: {STATE_LABEL.get(state, STATE_LABEL['unknown'])}",
             "연결 방식: " + MODE_LABEL.get(summary.get("mode"), MODE_LABEL["isolated"]),
             f"게이트웨이: {'연결됨' if summary.get('connected') and not silent else '연결 안 됨'}",
             "마지막 보고: " + (f"{clock(last)} ({max(0, int(now - last))}초 전)" if last else "—"),
             "승인 서버: " + (f"{servers}개" if servers is not None else "—"),
             # The names the harness shows (mcp__<name>__tool): an employee cannot otherwise tell which servers this PC has.
             *(["서버 이름: " + ", ".join(summary["names"])] if summary.get("names") else []),
             *([f"새로 반영된 서버: {', '.join(added['servers'])} ({clock(added['at'])}) "
                "— 이미 열려 있는 하네스에 보이지 않으면 다시 시작하세요."]
               if (added := summary.get("added")) and not silent and now - added["at"] < ADDED_SHOWN_SECONDS else []),
             "로컬 MCP 준비: " + prepared + (f" ({local['note']})" if local.get("note") and local.get("total") else ""),
             "직원 문서 폴더: " + (", ".join(local["documents"]) if local.get("documents") else "—"),
             "키트 판본: " + (summary.get("kit") or "—")[:12]]
    if silent:
        lines.append("관리형 서비스가 응답하지 않습니다 (마지막 갱신 " + (clock(updated) if updated else "—") + ")")
    lines.append("다음 할 일: " + next_step(summary, now, environment))  # always last: the live view lifts it out
    return "\n".join(lines) + "\n"


def width(text):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def clip(text, room):
    out, used = "", 0
    for character in text:
        used += width(character)
        if used > room:
            break
        out += character
    return out


class Screen:
    """Full-screen progress for the installer and mcpgw-status (D-239): the steps with their seconds, three
    result cells and the next thing to do. Not a terminal, no curses or no UTF-8 locale: one line per step,
    as before, so logs and SSH sessions read the same."""

    def __init__(self, title):
        self.title, self.rows, self.cells, self.next, self.notes = title, [], [], "", []
        self.curses = self.window = None
        if os.environ.get("MCPGW_PLAIN") or not (sys.stdin.isatty() and sys.stdout.isatty()) \
                or os.environ.get("TERM", "dumb") in ("", "dumb"):
            return
        try:
            import curses
            import locale
            locale.setlocale(locale.LC_ALL, "")
            if "utf" not in (locale.getpreferredencoding(False) or "").lower():
                locale.setlocale(locale.LC_ALL, "C.UTF-8")
            self.window = curses.initscr()
            self.curses = curses
            curses.noecho()
            curses.cbreak()
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        except Exception:  # no terminfo, no curses build, no UTF-8 locale: plain lines
            self.stop()

    def stop(self):
        if self.window is not None:
            try:
                self.curses.endwin()
            except Exception:
                pass
        self.window = None

    def draw(self, extra=()):
        if self.window is None:
            return
        try:
            self.window.erase()
            height, room = self.window.getmaxyx()
            room -= 2
            lines = [(self.title, self.curses.A_BOLD), ("", 0)]
            for label, started, seconds, mark in self.rows:
                spent = f"{seconds}초" if seconds is not None else f"{int(time.monotonic() - started)}초"
                lines.append((f"{mark} {clip(label, room - 10)}".ljust(max(0, room - 8 - (width(label) - len(label)))) + spent, 0))
            for text in extra:
                lines.append((text, 0))
            if self.cells:
                lines += [("", 0)] + [(f"{name:<6} {value}", self.curses.A_BOLD) for name, value in self.cells]
            if self.next:
                lines += [("", 0), ("다음 할 일: " + self.next, self.curses.A_REVERSE)]
            lines += [("", 0)] + [(note, self.curses.A_DIM) for note in self.notes[-3:]]
            for row, (text, attribute) in enumerate(lines[:height - 1]):
                self.window.addstr(row, 1, clip(text, room), attribute)
            self.window.refresh()
        except self.curses.error:
            pass

    def step(self, label):
        self.close_step()
        self.rows.append([label, time.monotonic(), None, "…"])
        if self.window is None:
            print(f"[{label}]", flush=True)
        self.draw()

    def close_step(self, mark="✓"):
        if self.rows and self.rows[-1][2] is None:
            self.rows[-1][2] = round(time.monotonic() - self.rows[-1][1])
            self.rows[-1][3] = mark
        self.draw()

    def say(self, text):
        self.notes.append(text)
        if self.window is None:
            print(text, flush=True)
        self.draw()

    def result(self, cells, next_line):
        self.cells, self.next = cells, next_line
        if self.window is None:
            for name, value in cells:
                print(f"{name}: {value}", flush=True)
            print("다음 할 일: " + next_line, flush=True)
        self.draw()

    def finish(self, wait=8):
        """The last frame stays for `wait` seconds or a key, then the same summary goes to the scrollback."""
        if self.window is None:
            return
        self.draw(extra=["", f"{wait}초 뒤 또는 아무 키나 누르면 닫힙니다"])
        try:
            self.window.timeout(wait * 1000)
            self.window.getch()
        except self.curses.error:
            pass
        self.stop()
        for label, _, seconds, mark in self.rows:
            print(f"{mark} {label} {seconds if seconds is not None else '—'}초")
        for name, value in self.cells:
            print(f"{name}: {value}")
        if self.next:
            print("다음 할 일: " + self.next)
        for note in self.notes:
            print(note)

    def pause(self):
        """For a program that needs the terminal itself (a model sign-in): leave full screen until resume()."""
        if self.window is not None:
            self.curses.endwin()

    def resume(self):
        if self.window is not None:
            self.window.refresh()
            self.draw()


def publish_status(summary):
    """Root writes, anyone reads: the summary the status command prints, and the same text for an account whose
    profile cannot run Python (`cat` is allowed there)."""
    summary = {**summary, "updated": time.time()}
    for suffix, text in (("json", json.dumps(summary)), ("txt", render_status(summary, summary["updated"], {}))):
        path = status_path(summary["user"], suffix)
        private_write(path, text)
        path.chmod(0o644)


def write_status_shim():
    private_write(STATUS_SHIM, "#!/bin/sh\n# mcpgw managed status\n"
                  f'exec /usr/bin/python3 -I -S {PROGRAMS}/managed-linux.py status "$@"\n')
    STATUS_SHIM.chmod(0o755)


def account_header(summary):
    """The Authorization the account's harness gets, from its own header helper run as that account."""
    user = summary["user"]
    helper = ENFORCEMENT / ("mcpgw-" + user) / "header-helper"
    command = [str(helper)]
    if os.geteuid() == 0:
        account = pwd.getpwnam(user)
        command = ["setpriv", "--reuid", str(account.pw_uid), "--regid", str(account.pw_gid), "--clear-groups", "--", *command]
    done = subprocess.run(command, capture_output=True, text=True, timeout=20, cwd="/", env={"PATH": "/usr/bin:/bin"})
    value = json.loads(done.stdout.strip().splitlines()[-1])["Authorization"]
    if value.startswith("Bearer endpoint-not-active"):
        raise ValueError("활성화 전이라 토큰이 없습니다")
    return value


def check_connection(summary):
    """tools/list and initialize over the Gateway with the account's own header (installer and mcpgw-status --check)."""
    observer = load_module("check_observer", Path(__file__).with_name("agent.py"))
    ca = summary.get("ca")
    certificate = Path(ca).read_text() if ca else ""
    fingerprint = hashlib.sha256(ssl_der(certificate)).hexdigest() if certificate else ""
    return observer.connection_check(summary["gateway"], observer.tls_context(certificate, fingerprint),
                                     account_header(summary), summary.get("names") or [])


def ssl_der(certificate):
    import ssl
    return ssl.PEM_cert_to_DER_cert(certificate.strip())


def connection_cells(found, servers):
    """② tool count and ③ one approved server's initialize, as the two cells beside the model answer."""
    failed = found.get("failed") or {}
    tools = f"{found['tools']}개 (서버 {len(found['initialized'])}/{servers})" if found.get("initialized") else "—"
    first = (f"{found['initialized'][0]} 연결 정상" if found.get("initialized")
             else ("실패 · " + ", ".join(f"{k} {v}" for k, v in list(failed.items())[:2])) if failed else "승인 서버 없음")
    return [("도구", tools), ("서버 연결", first)]


def status(args):
    user = args.user or pwd.getpwuid(os.getuid()).pw_name
    path = status_path(user, "json")
    if not args.user and not path.exists():
        # An administrator's own account differs from the managed account the harnesses run in.
        found = sorted(PROGRAMS.glob("status-*.json"))
        path = found[0] if len(found) == 1 else path
    try:
        summary = json.loads(path.read_text())
    except (OSError, ValueError):
        # Right after install the service has not written its first summary yet (10-23 pj2): not a failure.
        if list(Path("/etc/systemd/system").glob("mcpgw-managed-*.service")):
            print("장치 상태: 연결 준비 중")
            print("잠시 뒤 다시 확인하세요.")
            return
        raise ValueError("이 PC에는 관리형 연결의 상태가 없습니다. 설치되지 않았거나 서비스가 아직 시작되지 않았습니다") from None
    cells = []
    if args.check:
        try:
            cells = connection_cells(check_connection(summary), len(summary.get("names") or []))
        except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
            cells = [("연결 확인", f"실패 · {exc}")]
    screen = Screen("내 PC 연결 상태")
    if screen.window is None:
        print(render_status(summary, time.time()), end="")
        for name, value in cells:
            print(f"{name}: {value}")
        return
    # Live view: the service rewrites the summary every 10-60 s; q leaves, c checks the connection again.
    try:
        while True:
            try:
                summary = json.loads(path.read_text())
            except (OSError, ValueError):
                pass
            lines = render_status(summary, time.time()).splitlines()
            screen.next = lines.pop()[len("다음 할 일: "):]
            screen.cells = cells
            screen.draw(extra=lines + ["", "q 닫기 · c 연결 확인"])
            screen.window.timeout(2000)
            key = screen.window.getch()
            if key in (ord("q"), 27):
                break
            if key == ord("c"):
                try:
                    cells = connection_cells(check_connection(summary), len(summary.get("names") or []))
                except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
                    cells = [("연결 확인", f"실패 · {exc}")]
    finally:
        screen.stop()
    print(render_status(summary, time.time()), end="")


# -- Connectors and built-in features the managed account's harnesses carry. The kit sends the same report
# from an unmanaged PC with an employee token; here it goes under the device credential, so nothing in
# this service ever holds an employee token. --
INVENTORY_EVERY = 6 * 3600
# `claude mcp list`: "claude.ai Notion: https://mcp.notion.com/mcp - ✔ Connected". Read as mcpgw_pc.py reads it.
CLAUDE_LINE = re.compile(r"^(?P<name>.+?): (?P<target>.*?)(?: \((?:HTTP|SSE)\))? - (?P<status>[✔✓√✘✗×!-] .*)$")
PLUGIN_HEAD = re.compile(r"^\s*[❯>*-]\s+(?P<name>[\w.-]+@[\w.-]+)\s*$")
CODEX_FEATURES = ("apps", "plugins", "browser_use", "computer_use", "image_generation", "memories")
APP_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def origin(url):
    """scheme://host[:port] only: some MCP URLs carry a key in the path or query."""
    try:
        parts = urlsplit(url)
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return ""
    return f"{parts.scheme}://{parts.hostname}{port}" if parts.scheme in ("http", "https") and parts.hostname else ""


def parse_claude_servers(text, gateway_url):
    items = []
    for line in text.splitlines():
        match = CLAUDE_LINE.match(line.strip())
        if not match or match["target"].startswith(gateway_url + "/mcp/"):
            continue  # servers behind the Gateway are the Gateway's to see
        name, target = match["name"], match["target"].strip()
        kind = "connector" if name.startswith("claude.ai ") else "plugin" if name.startswith("plugin:") else "server"
        items.append({"harness": "claude", "kind": kind, "name": name[:200],
                      "target": origin(target) or ("stdio" if target else ""), "status": match["status"][:120]})
    return items


def parse_claude_plugins(text):
    """`claude plugin list`: "❯ productivity@synced", then "Status: ✔ loaded". Synced plugins are not MCP server lines."""
    items, current = [], None
    for line in text.splitlines():
        head = PLUGIN_HEAD.match(line)
        if head:
            current = {"harness": "claude", "kind": "plugin", "name": head["name"][:200], "target": "stdio",
                       "status": "", "active": False}
            items.append(current)
            continue
        status = re.match(r"^\s*Status:\s*(.+?)\s*$", line)
        if status and current is not None:
            current["status"] = status[1][:120]
            current["active"] = "loaded" in status[1].lower() and not re.search("[✘✗×]", status[1])
    return items


def effective_web_search(config_result, requirements_result):
    """The mode Codex runs with: the layered config clamped by the managed requirements, not a user file.
    Codex defaults to cached; a managed list that omits the mode leaves only the list's own value."""
    mode = ((config_result or {}).get("config") or {}).get("web_search") or "cached"
    allowed = ((requirements_result or {}).get("requirements") or {}).get("allowedWebSearchModes") or []
    if allowed and mode not in allowed:
        mode = "disabled" if "disabled" in allowed else str(allowed[0])
    return str(mode)


def parse_codex(gateway_url, servers, apps, features_text, web_search):
    items = []
    for server in servers:
        url = (server.get("transport") or {}).get("url") or ""
        if url.startswith(gateway_url + "/mcp/"):
            continue
        items.append({"harness": "codex", "kind": "server", "name": str(server.get("name"))[:200],
                      "target": origin(url) or "stdio", "status": "enabled" if server.get("enabled") else "disabled",
                      "active": bool(server.get("enabled"))})
    for app in apps:
        if APP_ID.match(str(app.get("id", ""))):
            items.append({"harness": "codex", "kind": "app", "name": str(app.get("runtimeName") or app["id"])[:200],
                          "target": app["id"], "status": "enabled" if app.get("enabled") else "disabled",
                          "active": bool(app.get("enabled"))})
    for line in features_text.splitlines():
        cells = line.split()
        if len(cells) >= 3 and cells[0] in CODEX_FEATURES and cells[-1] == "true":
            items.append({"harness": "codex", "kind": "feature", "name": cells[0], "target": "on", "status": "on"})
    if web_search != "disabled":
        items.append({"harness": "codex", "kind": "feature", "name": "web_search", "target": web_search, "status": web_search})
    return items


def run_as_managed(config, tool, arguments, stdin=None):
    """Start the managed account's own launcher as that account: the environment, proxy and profile are the ones
    the employee's harness gets. setpriv, not subprocess(user=): supported distributions include Python 3.8."""
    account = pwd.getpwnam(config["username"])
    environment = {"PATH": "/usr/bin:/bin"}
    if config.get("mode") == "simple":
        # The employee's own harness, found the way their terminal finds it (the login shell's PATH, ~/.local/bin).
        program = ["/bin/bash", "-lc", 'exec "$0" "$@"', tool]
        environment.update(HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name, **ca_environment(config))
    else:
        program = [str(ENFORCEMENT / ("mcpgw-" + config["username"]) / tool)]
    command = ["setpriv", "--reuid", str(account.pw_uid), "--regid", str(account.pw_gid), "--clear-groups", "--",
               *program, *arguments]
    return subprocess.Popen(command, stdin=stdin or subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            cwd=account.pw_dir, env=environment, text=True, encoding="utf-8", errors="replace")


def run_text(config, tool, arguments, timeout=120):
    process = run_as_managed(config, tool, arguments)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    if process.returncode != 0:
        raise ValueError(f"{tool} {arguments[0]} 실패")
    return output


def codex_rpc(config, calls, timeout=60):
    """`codex app-server` answers JSON-RPC while its stdin stays open; one process serves every call."""
    process = run_as_managed(config, "codex", ["app-server"], stdin=subprocess.PIPE)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
    wanted = {i + 2: method for i, (method, _) in enumerate(calls)}
    answers = {}
    try:
        for message in ({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "mcpgw-managed", "version": "1"}}},
                        {"method": "initialized"},
                        *({"id": i + 2, "method": m, "params": p} for i, (m, p) in enumerate(calls))):
            process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + timeout
        while len(answers) < len(wanted) and time.monotonic() < deadline:
            try:
                reply = json.loads(lines.get(timeout=max(0.1, deadline - time.monotonic())))
            except (queue.Empty, ValueError):
                continue
            if isinstance(reply, dict) and reply.get("id") in wanted:
                answers[wanted[reply["id"]]] = reply.get("result")
    finally:
        process.kill()
        process.communicate()
    return answers


def collect_inventory(config):
    """{harness: items} for the harnesses installed here. A harness whose command failed is left out: the Gateway
    marks every item of a reported harness absent, so a failed read must not look like an empty one."""
    found = {}
    for tool in config.get("harnesses", ()):
        try:
            version = re.search(r"\d+\.\d+[0-9A-Za-z.+_-]*", run_text(config, tool, ["--version"], timeout=30))
            if version:
                HARNESS_VERSIONS[tool] = version.group(0)[:40]
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass  # the version is shown when known, never required
    if "claude" in config.get("harnesses", ()):
        try:
            items = parse_claude_servers(run_text(config, "claude", ["mcp", "list"]), config["gateway_url"])
            try:
                items += parse_claude_plugins(run_text(config, "claude", ["plugin", "list"]))
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass  # a Claude Code without `plugin list`: the server lines still stand
            found["claude"] = items
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass
    if "codex" in config.get("harnesses", ()):
        try:
            servers = json.loads(run_text(config, "codex", ["mcp", "list", "--json"]) or "[]")
            answers = codex_rpc(config, [("app/installed", {}), ("config/read", {}), ("configRequirements/read", {})])
            if answers.get("app/installed") is not None:
                found["codex"] = parse_codex(
                    config["gateway_url"], servers, answers["app/installed"].get("apps", []),
                    run_text(config, "codex", ["features", "list"]),
                    effective_web_search(answers.get("config/read"), answers.get("configRequirements/read")))
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass
    return found


def report_inventory(config):
    found = collect_inventory(config)
    if not found:
        raise ValueError("보고할 하네스 목록을 읽지 못했습니다")
    answer = request(config, "/api/endpoint/harness-inventory", {
        "harnesses": sorted(found), "items": [item for items in found.values() for item in items]})
    print(json.dumps({"harness_inventory": "reported", "accepted": answer.get("accepted"), "harnesses": sorted(found)}), flush=True)


def serve(args):
    if os.geteuid() != 0 or not protected(args.config):
        raise ValueError("root 관리 서비스와 비밀 설정이 필요합니다")
    config = json.loads(args.config.read_text())
    verify_transport(config)
    binding = load_module("broker_binding", Path(__file__).with_name(
        "managed-macos.py" if sys.platform == "darwin" else "broker_binding.py"))
    if sys.platform == "darwin":
        binding.configure_runtime(sys.modules[__name__])
        binding.start_runtime(config, sys.modules[__name__])
    cache, lock = {}, threading.Lock()
    class Header(socketserver.BaseRequestHandler):
        def handle(self):
            permitted = binding.authorize_peer(self.request, config)
            with lock:
                if not permitted or time.monotonic() >= cache.get("until", 0):
                    # The state lets the helper tell the harness why there is no token (pending, quarantined).
                    answer = {"error": "엔드포인트 활성화·정책 연결이 필요합니다", "state": cache.get("state", "")}
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
                 "ENDPOINT_CA_CERTIFICATE": config.get("ca_certificate", ""), "ENDPOINT_CA_SHA256": config.get("ca_sha256", ""),
                 "ENDPOINT_ID": config["endpoint_id"], "ENDPOINT_CONFIG_PATHS": os.pathsep.join([pwd.getpwnam(config["username"]).pw_dir,
                 *sorted({str(path.parent) for path in FILES.values()})]), "ENDPOINT_TAILSCALE_NODE_ID": config["tailscale_node_id"], "ENDPOINT_NETSCAN": "0",
                 "ENDPOINT_PROCESS_SCAN": "1", "ENDPOINT_PROCESS_UID": str(config["uid"]), "ENDPOINT_ORIGIN": "automatic"}))
    previous = config["policy_hash"]
    runner = PROGRAMS / "local-runner.py"
    local = None
    if runner.exists():
        log = lambda item: print(json.dumps(item, ensure_ascii=False), flush=True)
        local = load_module("local_runner", runner)
        # Separate threads: an image pull that takes minutes must not hold the job loop, and the reverse.
        for target in (local.run, local.prepare):
            threading.Thread(target=target, daemon=True, args=(config, request, log)).start()

    def observe():
        # Beside the heartbeat, not inside it: a round that spends up to 80 seconds here is 80 seconds
        # in which an activation by the organization goes unnoticed and the employee's harness gets
        # the not-active placeholder instead of a token.
        while True:
            observers = {}
            for name, extra in (("agent.py", ["--once"]), ("os-observer.py", ["--uid", str(config["uid"]), "--profile", "mcpgw-" + config["username"]])):
                if name == "os-observer.py" and (sys.platform == "darwin" or config.get("mode") == "simple"):
                    continue  # 커널 이벤트 관측기는 격리 계정의 Linux(AppArmor·audit) 전용이다.
                # Inventory and kernel-event reports are observations; one failing must not cut the
                # enforced account off from the Gateway.
                try:
                    result = subprocess.run([sys.executable, "-I", "-S", str(PROGRAMS / name), "--config", str(observer_config), *extra],
                                            timeout=40, capture_output=True, text=True)
                    output = json.loads(result.stdout.splitlines()[-1])
                    observers[name] = output.get("observation", {"state": "failed"})
                except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
                    observers[name] = {"state": "failed", "error_code": type(exc).__name__}
            print(json.dumps({"endpoint_id": config["endpoint_id"], "observers": observers}), flush=True)
            time.sleep(55)
    threading.Thread(target=observe, daemon=True).start()
    try:
        kit = kit_version(PROGRAMS)
    except OSError:
        kit = None
    def harness_inventory():
        time.sleep(60)  # after the first heartbeat: the employee's harness gets its token first
        while True:
            try:
                report_inventory(config)
                wait = INVENTORY_EVERY
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                # A pending or revoked device is refused (401/403); retry soon. This never touches the heartbeat.
                print(json.dumps({"harness_inventory": "failed", "error": type(exc).__name__,
                                  "status": getattr(exc, "code", None)}), flush=True)
                wait = 900
            time.sleep(wait)
    if sys.platform.startswith("linux") and config.get("harnesses"):
        threading.Thread(target=harness_inventory, daemon=True).start()

    def keep_home_launchers():
        while True:
            try:
                again = home_launchers(config)
                if again:
                    print(json.dumps({"home_launcher": "restored", "paths": again}, ensure_ascii=False), flush=True)
            except OSError as exc:
                print(json.dumps({"home_launcher": "failed", "error": type(exc).__name__}), flush=True)
            time.sleep(HOME_LAUNCHER_EVERY)
    if sys.platform.startswith("linux") and config.get("owner_uid") is not None:
        threading.Thread(target=keep_home_launchers, daemon=True).start()
    # gateway and ca let the employee's own `mcpgw-status --check` reach the Gateway as their harness does.
    summary = {"user": config["username"], "state": "unknown", "connected": False, "last_report": None,
               "servers": None, "kit": kit, "mode": config.get("mode", "isolated"), "gateway": config["gateway_url"],
               "ca": str(PROGRAMS / f"ca-{config['uid']}.crt") if config.get("ca_certificate") else None}
    known = None  # server names of the policy applied before this one: what a new policy adds is shown to the employee
    while True:
        # Until the organization activates the device the loop runs fast, so the first token follows
        # the activation within seconds instead of a minute; an active device keeps the slow cadence.
        pause = 10
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
            if known is not None and set(policy["servers"]) - known:
                summary["added"] = {"servers": sorted(set(policy["servers"]) - known), "at": time.time()}
            known = set(policy["servers"])
            findings = []
            hashes, health = checks(config, policy, findings=findings)
            beat = {"policy_hash": policy["policy_hash"], "configuration_hashes": hashes, "checks": health,
                    "user_command_settings": findings}
            try:
                beat["host"] = host_report(config)
            except (OSError, KeyError, ValueError):
                pass  # the account report is informational; it never holds back the heartbeat
            try:
                beat["network_quality"] = load_module("probe", Path(__file__).with_name("agent.py")).measure_gateway(
                    config["gateway_url"], context=verify_transport(config))
            except (OSError, KeyError, ValueError):
                pass  # a failed measurement is simply absent
            try:
                report = request(config, "/api/endpoint/heartbeat", beat)
            except urllib.error.HTTPError as exc:
                if exc.code != 422 or not {"host", "network_quality"} & beat.keys():
                    raise
                beat.pop("host", None)  # a Gateway older than D-62 / this report rejects the extra field
                beat.pop("network_quality", None)
                report = request(config, "/api/endpoint/heartbeat", beat)
            if report["state"] == "active" and report["compliant"]:
                with lock:
                    token = request(config, "/oauth/device-token", {})
                    cache.update(token=token["access_token"], until=time.monotonic() + TOKEN_CACHE_SECONDS)
                pause = 60
            else:
                with lock:
                    cache.clear()
            with lock:
                cache["state"] = report["state"]
            summary.update(state=report["state"], connected=True, last_report=time.time(), servers=len(policy["servers"]),
                           names=sorted(policy["servers"]),
                           claude_ca="NODE_EXTRA_CA_CERTS" in policy["files"]["managed-settings.json"])
            print(json.dumps({"endpoint_id": config["endpoint_id"], "state": report["state"], "checks": health}), flush=True)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            with lock:
                cache.clear()
            # 401 on a device-key route: the Gateway no longer knows this credential (the administrator revoked it).
            summary.update(connected=False, **({"state": "revoked"} if getattr(exc, "code", None) == 401 else {}))
            print(json.dumps({"state": "connection-stopped", "error": type(exc).__name__,
                              "status": getattr(exc, "code", None), "reason": str(exc)[:200]}), flush=True)
        if local:
            summary["local"] = dict(local.preparation)
        try:
            publish_status(summary)
        except OSError:
            pass  # the employee's view is a convenience; it never stops the connection
        time.sleep(pause)


def rollback(args):
    """Run after the device credential is revoked in the Console and the account is signed out.
    enforce-linux.py --rollback alone left the service, the /etc files and the device secret behind,
    and a reinstall then refused the device as already installed."""
    if os.geteuid() != 0:
        raise ValueError("root로 실행하세요")
    person = pwd.getpwnam(args.user)
    folder = STATE / args.user
    unit = f"mcpgw-managed-{args.user}.service"
    try:
        config = json.loads((folder / "config.json").read_text())
        restore_home_launchers(config)
    except (OSError, ValueError):
        config = {}
    if Path("/etc/systemd/system", unit).exists():
        subprocess.run(["systemctl", "disable", "--now", unit], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path("/etc/systemd/system", unit).unlink(missing_ok=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    if (Path("/usr/local/lib/mcpgw-enforcement") / f"mcpgw-{args.user}" / "state.json").exists():
        # The enforcer beside this file: run from a new kit, that is the kit's copy. The copy a failed earlier
        # install left under /usr/local is the old code and stopped this removal (10-23 kuku VM, D-229).
        subprocess.run([sys.executable, str(Path(__file__).with_name("enforce-linux.py")), "--user", args.user, "--rollback"],
                       check=True)
    elif (ENFORCEMENT / f"mcpgw-{args.user}" / "header-helper").exists():
        shutil.rmtree(ENFORCEMENT / f"mcpgw-{args.user}", ignore_errors=True)  # simple mode: only the helper script
    for name, target in FILES.items():
        backup = folder / (target.name + ".backup")
        if backup.exists():
            private_write(target, backup.read_text())
            target.chmod(0o644)
        else:
            target.unlink(missing_ok=True)
    Path(f"/run/mcpgw-{args.user}.sock").unlink(missing_ok=True)
    for suffix in ("json", "txt"):
        status_path(args.user, suffix).unlink(missing_ok=True)
    if not list(PROGRAMS.glob("status-*.json")):
        STATUS_SHIM.unlink(missing_ok=True)
    shutil.rmtree(folder, ignore_errors=True)
    (PROGRAMS / f"ca-{person.pw_uid}.crt").unlink(missing_ok=True)
    # The CA lines serve every simple install on this PC; the last one removed takes them out.
    remaining = [json.loads(path.read_text()) for path in STATE.glob("*/config.json")]
    others = [c for c in remaining if c.get("mode") == "simple" and c.get("ca_certificate")]
    if config.get("mode") == "simple" or not others:
        edit_environment(ca_environment(others[0]) if others else {})
    print("해당 계정의 관리형 서비스·설정·방화벽·프로필을 제거했습니다")


UNAVAILABLE = {"Authorization": "Bearer endpoint-not-active"}


def header(args):
    reason = ""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(8)
            connection.connect(args.socket)
            response = json.loads(connection.recv(8192))
        if set(response) != {"Authorization"}:
            # The service says why it has no token; the Gateway turns the suffix into the 401 line the employee sees (D-217).
            state = response.get("state") if isinstance(response, dict) else ""
            reason = state if state in ("pending", "quarantined") else ""
            raise ValueError("엔드포인트 활성화·정책 연결이 필요합니다")
    except (OSError, ValueError) as exc:
        # 헤더가 없으면 하네스가 OAuth 인증 대기로 표시·캐시해 복구 뒤에도 연결하지 않는다(D-148 PJ1).
        # 게이트웨이가 거부하는 고정 값이면 연결 실패로만 남아 다음 연결에서 다시 시도된다.
        print("관리형 연결 불가: " + str(exc), file=sys.stderr)
        response = {"Authorization": UNAVAILABLE["Authorization"] + ("." + reason if reason else "")}
    print(json.dumps(response))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("install")
    setup.add_argument("--user", required=True)
    setup.add_argument("--owner-uid", type=int, help="연결을 시작할 수 있는 직원 계정 UID")
    setup.add_argument("--enrollment", type=Path, default=Path(__file__).with_name("enrollment.json"))
    setup.add_argument("--client", action="append", default=[])
    setup.add_argument("--broker-binding", choices=("warn", "enforce"), default="warn")
    setup.add_argument("--mode", choices=("simple", "isolated"), default="isolated",
                       help="simple: 직원 계정 그대로(커널 격리 없음) · isolated: 관리 계정 격리")
    setup.set_defaults(run=install)
    service = commands.add_parser("serve")
    service.add_argument("--config", type=Path, required=True)
    service.set_defaults(run=serve)
    helper = commands.add_parser("header")
    helper.add_argument("--socket", required=True)
    helper.set_defaults(run=header)
    show = commands.add_parser("status", help="이 PC의 관리형 연결 상태")
    show.add_argument("--user")
    show.add_argument("--check", action="store_true", help="게이트웨이로 initialize·tools/list를 보내 연결을 확인")
    show.set_defaults(run=status)
    remove = commands.add_parser("rollback")
    remove.add_argument("--user", required=True)
    remove.set_defaults(run=rollback)
    args = parser.parse_args()
    try:
        args.run(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Never echo requests, credentials, response bodies or header dictionaries.
        parser.exit(1, "관리형 설치/연결 실패: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
