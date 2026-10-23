#!/usr/bin/env python3
"""One elevation, one connected endpoint: everything between "run the file" and "type codex".

The employee runs install.sh (Linux) or install.cmd (Windows) from the kit, confirms the OS
elevation prompt once, and this does the rest: required packages, the approved harness binaries,
the managed account (created when the employee's own account is an administrator), the managed
configuration, and the harness model sign-in. An existing install is rolled back first, so the
same file is also the repair and the reinstall path.

It never weakens the controls: AppArmor/nftables confinement, the device heartbeat and the
Gateway's per-call decision are configured exactly as the manual path configured them, and the
organization still activates the device in the Console before MCP authentication opens.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import importlib.util
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPROVED = Path("/opt/mcpgw-approved")
PROGRAMS = Path("/usr/local/lib/mcpgw-managed")
STATE = Path("/var/lib/mcpgw-managed")
SHIM_DIR = Path("/usr/local/bin")
SUDOERS = Path("/etc/sudoers.d/mcpgw-managed")
FUNCTIONS = Path("/etc/profile.d/mcpgw-managed.sh")
# Debian-family and Arch shells read these for every interactive terminal; profile.d alone only
# reaches login shells (Fedora's /etc/bashrc already loads profile.d for both).
RC_FILES = (Path("/etc/bash.bashrc"), Path("/etc/zsh/zshrc"))
HOOK_BEGIN, HOOK_END = "# >>> mcpgw managed launchers >>>", "# <<< mcpgw managed launchers <<<"
PRIVILEGED = {"sudo", "wheel", "docker", "lxd", "libvirt", "root", "adm"}
MIN_PYTHON = (3, 10)
# 도구 → 패키지. 설치 첫머리에 한 번 조회해 없는 것만 모아 패키지 관리자를 한 번 갱신하고 한 번에 설치한다.
# openssl은 로컬 MCP 승인 서명 검증(local-runner)이, curl은 하네스·점검 도구가 쓴다.
REQUIRED = {"gcc": "gcc", "nft": "nftables", "apparmor_parser": "apparmor-utils", "curl": "curl", "openssl": "openssl"}
RENAMED = {"pacman": {"apparmor-utils": "apparmor"}}
# 로컬 MCP 격리 실행용 컨테이너 엔진. 러너는 /usr/bin의 podman·docker만 쓴다. 키가 곧 지원하는 패키지 관리자다.
ENGINES = {"apt-get": "docker.io", "dnf": "podman", "pacman": "docker"}
ENGINE_BINARIES = ("podman", "docker")
INSTALL_VERB = {"apt-get": "apt-get install", "dnf": "dnf install", "pacman": "pacman -S"}
# The harness vendors ship the executable and its tool-call host side by side in one release
# directory; taking them from anywhere else pairs mismatched builds (D-67).
VENDOR_GLOBS = ("**/@openai/codex-*/vendor/*/bin", "**/@anthropic-ai/claude-code*/vendor/*/bin",
                "**/@anthropic-ai/claude-code*/bin", "**/@anthropic-ai/claude-code-*", "**/bin")


class Failed(Exception):
    """Reported to the employee as one line; the caller rolls back."""


def run(*command: str, check: bool = True, quiet: bool = False, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, text=True,
                          stdout=subprocess.DEVNULL if quiet else None, **kwargs)


def out(*command: str) -> str:
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    return done.stdout.strip()


_open_step: list = []
timings: list[tuple[str, int]] = []


def step(message: str) -> None:
    """한 줄 안내. 단계가 끝나는 시각(다음 단계 시작·close_step)으로 소요 시간을 재, 마지막에 한 줄로 보인다."""
    close_step()
    print(f"[{message}]", flush=True)
    _open_step[:] = [message, time.monotonic()]


def close_step() -> None:
    if _open_step:
        timings.append((_open_step[0], round(time.monotonic() - _open_step[1])))
        _open_step.clear()


def groups_of(name: str) -> set[str]:
    person = pwd.getpwnam(name)
    return {grp.getgrgid(gid).gr_name for gid in os.getgrouplist(name, person.pw_gid)}


def employee_account(explicit: str | None) -> str:
    """Who ran the installer. sudo/pkexec keep the original account in the environment."""
    name = explicit or os.environ.get("SUDO_USER") or os.environ.get("PKEXEC_UID")
    if name and name.isdigit():
        name = pwd.getpwuid(int(name)).pw_name
    if not name:
        raise Failed("설치를 실행한 직원 계정을 알 수 없습니다. install.sh로 실행하세요")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", name) or pwd.getpwnam(name).pw_uid < 1000:
        raise Failed(f"일반 직원 계정이 아닙니다: {name}")
    return name


# -- packages and harness binaries -------------------------------------------------

def check_python() -> None:
    """설치기와 서비스가 쓰는 /usr/bin/python3가 모두 지원 판본인지 설치 전에 확인한다(서비스는 시스템 python3로 돈다)."""
    if sys.version_info < MIN_PYTHON:
        raise Failed("Python 3.10 이상이 필요합니다(설치기 판본 %d.%d)" % sys.version_info[:2])
    system = Path("/usr/bin/python3")
    if not system.is_file():
        raise Failed("관리형 서비스가 쓰는 /usr/bin/python3가 없습니다")
    found = out(str(system), "-c", "import sys;print('%d.%d' % sys.version_info[:2])")
    if not re.fullmatch(r"\d+\.\d+", found) or tuple(map(int, found.split("."))) < MIN_PYTHON:
        raise Failed(f"/usr/bin/python3가 3.10 미만입니다({found or '판본 확인 실패'})")


def has_engine() -> bool:
    return any(Path("/usr/bin", name).is_file() for name in ENGINE_BINARIES)


def install_packages(manager: str, names: list[str], env: dict) -> bool:
    command = {"apt-get": ["apt-get", "install", "-y", "-qq"], "dnf": ["dnf", "install", "-y", "-q"],
               "pacman": ["pacman", "-S", "--needed", "--noconfirm"]}[manager]
    return run(*command, *[RENAMED.get(manager, {}).get(name, name) for name in names],
               check=False, quiet=True, env=env).returncode == 0


def ensure_packages() -> None:
    """필수 구성요소와 컨테이너 엔진을 설치 한 번에 갖춘다. 없는 도구만 한 번에 조회·설치하고(패키지 관리자 갱신도 한 번),
    엔진은 못 받아도 설치를 멈추지 않는다: 원격 MCP는 엔진 없이 쓰고, 로컬 MCP만 엔진 설치 뒤 쓸 수 있다."""
    missing = [tool for tool in REQUIRED if not shutil.which(tool)]
    if missing or not has_engine():
        install_missing(missing)
    start_engine()


def install_missing(missing: list[str]) -> None:
    manager = next((m for m in ENGINES if shutil.which(m)), None)
    if not manager:
        if missing:
            raise Failed("필수 구성요소를 설치할 패키지 관리자를 찾지 못했습니다: " + ", ".join(missing))
        print("컨테이너 엔진이 없습니다. 로컬 MCP는 podman 또는 docker를 설치한 뒤 사용할 수 있습니다.", flush=True)
        return
    step("필수 구성요소 설치" if missing else "컨테이너 엔진 설치")
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    refreshed = manager != "apt-get" or run("apt-get", "update", "-qq", check=False, quiet=True, env=env).returncode == 0
    if missing:
        if not refreshed or not install_packages(manager, [REQUIRED[tool] for tool in missing], env):
            raise Failed(f"필수 구성요소 설치가 실패했습니다({manager}). 사내 패키지 저장소를 확인하세요")
        still = [tool for tool in missing if not shutil.which(tool)]
        if still:
            raise Failed("설치 후에도 없는 필수 구성요소: " + ", ".join(still))
    if not has_engine() and not (refreshed and install_packages(manager, [ENGINES[manager]], env)):
        print(f"컨테이너 엔진을 설치하지 못했습니다. 로컬 MCP는 엔진 설치 뒤 사용할 수 있습니다: "
              f"sudo {INSTALL_VERB[manager]} {ENGINES[manager]}", flush=True)


def start_engine() -> None:
    """docker는 데몬이 떠 있어야 하고 재부팅 뒤에도 켜져야 한다. podman은 데몬이 없다(러너는 podman을 먼저 쓴다)."""
    if Path("/usr/bin/docker").is_file() and not Path("/usr/bin/podman").is_file():
        if run("systemctl", "enable", "--now", "docker", check=False, quiet=True, stderr=subprocess.DEVNULL).returncode:
            print("docker 서비스를 켜지 못했습니다. 로컬 MCP는 켠 뒤 사용할 수 있습니다: sudo systemctl enable --now docker", flush=True)


def search_roots(employee: str) -> list[Path]:
    home = Path(pwd.getpwnam(employee).pw_dir)
    # The last one is where OpenAI's own installer puts the executable beside its tool-call host.
    roots = [HERE / "harness", Path("/usr/local/lib/node_modules"), Path("/usr/lib/node_modules"),
             home / ".npm-global/lib/node_modules", home / ".local/share/reflex", home / ".local/lib",
             *sorted(home.glob(".nvm/versions/node/*/lib/node_modules"), reverse=True),
             home / ".codex/packages/standalone/current/bin"]
    if sys.platform == "darwin":
        roots += [Path("/opt/homebrew/lib/node_modules"), Path("/opt/homebrew/bin"),
                  Path("/usr/local/bin"), home / ".local/bin",
                  *sorted(Path("/opt/homebrew/Cellar/codex").glob("*/bin"), reverse=True)]
    return [root for root in roots if root.exists()]


def native_claude(employee: str) -> Path | None:
    """Anthropic's own installer keeps versioned executables (no folder named claude) and points
    ~/.local/bin/claude at the active one."""
    home = Path(pwd.getpwnam(employee).pw_dir)
    versions = sorted((home / ".local/share/claude/versions").glob("*"), reverse=True)
    for found in (home / ".local/bin/claude", *versions):
        real = found.resolve()
        if real.is_file() and native(real):
            return real
    return None


def release_directory(employee: str, name: str) -> Path | None:
    """A directory holding the native executable; for codex also its tool-call host."""
    wanted = ("codex", "codex-code-mode-host") if name == "codex" else ("claude",)
    direct = [root for root in search_roots(employee)
              if all((root / item).is_file() for item in wanted)]
    if direct:
        return direct[0]
    for root in search_roots(employee):
        for glob in VENDOR_GLOBS:
            for found in sorted(root.glob(glob)):
                if all((found / item).is_file() for item in wanted):
                    return found
    return None


def native(path: Path) -> bool:
    with open(path, "rb") as handle:
        magic = handle.read(4)
        return (magic in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
                if sys.platform == "darwin" else magic == b"\x7fELF")


def place_harnesses(employee: str) -> dict[str, dict]:
    """Copy the official executables into the root-owned approved path and pin their digests.

    This fixes what the organization approved and what the AppArmor profile will allow; it is an
    integrity record of the copied bytes, not a vendor signature check.
    """
    APPROVED.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chown(APPROVED, 0, 0)
    APPROVED.chmod(0o755)
    placed: dict[str, dict] = {}
    for name in ("codex", "claude"):
        files = ["codex", "codex-code-mode-host"] if name == "codex" else ["claude"]
        source = release_directory(employee, name)
        origins = {item: source / item for item in files} if source else None
        if not origins and name == "claude" and (found := native_claude(employee)):
            source, origins = found.parent, {"claude": found}
        if not origins:
            if name == "claude" and (APPROVED / "claude").is_file():
                placed[name] = {"path": str(APPROVED / name), "source": "already-approved"}
                continue
            # PC에 있는 하네스만 관리한다. 없는 것은 나중에 설치하고 키트를 다시 실행하면 추가된다.
            print(f"{name}이(가) 이 PC에 없어 건너뜁니다.", flush=True)
            continue
        for item, origin in origins.items():
            target = APPROVED / item
            if not native(origin):
                raise Failed(f"native 실행 파일이 아닙니다: {origin}")
            digest = hashlib.sha256(origin.read_bytes()).hexdigest()
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                temporary = target.with_name("." + item + ".new")
                shutil.copyfile(origin, temporary)
                os.chown(temporary, 0, 0)
                temporary.chmod(0o755)
                temporary.replace(target)
            placed.setdefault(name, {"path": str(APPROVED / name), "source": str(source), "digests": {}})
            placed[name]["digests"][item] = digest
    if not placed:
        raise Failed("이 PC에서 codex·claude를 찾지 못했습니다. 둘 중 하나를 설치한 뒤 다시 실행하세요")
    return placed


# -- the managed account ------------------------------------------------------------

def managed_account(employee: str) -> tuple[str, bool]:
    """The employee's own account when it is an ordinary one; otherwise a created companion.

    An administrator account cannot be confined by a profile it can edit, so the harnesses run as
    a separate ordinary account — the same split Windows uses for contained agent connectors.
    """
    if not groups_of(employee) & PRIVILEGED:
        return employee, False
    name = ("managed-" + employee)[:31]
    try:
        pwd.getpwnam(name)
    except KeyError:
        step(f"관리 계정 만들기: {name}")
        run("useradd", "--create-home", "--shell", "/bin/bash", "--comment", "MCP managed harness account", name)
    if groups_of(name) & PRIVILEGED:
        raise Failed(f"{name} 계정에 관리 권한이 있어 통제를 설치할 수 없습니다")
    return name, True


MARK = b"#!/bin/bash\n# mcpgw"


def shim_state(path: Path) -> tuple[bool, bool]:
    """(something is there, it is one of ours). A dangling symlink is still something."""
    if path.is_symlink():
        return True, False
    if path.is_file():
        with path.open("rb") as handle:
            return True, handle.read(len(MARK)) == MARK
    return False, False


def replaced_dir(managed: str) -> Path:
    keep = PROGRAMS / managed / "replaced"
    keep.mkdir(mode=0o700, parents=True, exist_ok=True)
    return keep


def write_shims(employee: str, managed: str, names=("codex", "claude")) -> list[str]:
    """`codex` and `claude` in the employee's own account, run as the managed account.

    Only for an employee who is already an administrator: the sudoers rule grants them a login
    shell they could already obtain, and it names that one program. The call still enters the
    managed account's login shell, so AppArmor and the UID firewall attach as they do on sign-in.
    """
    shell = Path("/usr/local/lib/mcpgw-enforcement") / ("mcpgw-" + managed) / "login-shell"
    if not shell.is_file():
        raise Failed("관리형 로그인 셸이 설치되지 않아 실행 연결을 만들 수 없습니다")
    SUDOERS.write_text(f"{employee} ALL=({managed}) NOPASSWD: {shell}\n", encoding="utf-8")
    SUDOERS.chmod(0o440)
    if subprocess.run(["visudo", "-cqf", str(SUDOERS)], check=False).returncode:
        SUDOERS.unlink(missing_ok=True)
        raise Failed("sudo 규칙 검사에 실패해 실행 연결을 만들지 않았습니다")
    launchers = [replace_launcher(name, managed, shell) for name in names]
    write_functions(employee)
    return launchers


def launcher_functions(shim_dir: Path, employee: str) -> str:
    """The employee's own PATH lists ~/.local/bin and the like before /usr/local/bin, so the
    launcher alone loses to a harness installed there: that one runs unmanaged, with no managed
    MCP and nothing in the Console. A shell function wins over PATH lookup.

    Only for the employee: the managed account's own login shell reads /etc/profile.d too, and a
    function there would call the launcher from inside the confined account (denied by its profile),
    while another user on the device has no sudo rule for it. Without the launcher (a removal that
    skipped this file) the command still has to run."""
    return ("# mcpgw managed harness launchers\n"
            f"if [ \"$(id -un)\" = '{employee}' ]; then\n"
            + "".join(f'  {name}() {{ if [ -x {shim_dir / name} ]; then {shim_dir / name} "$@"; '
                      f'else command {name} "$@"; fi; }}\n' for name in ("codex", "claude"))
            + "fi\n")


def edit_hook(path: Path, install: bool) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    block = re.compile(rf"\n?{re.escape(HOOK_BEGIN)}.*?{re.escape(HOOK_END)}\n", re.S)
    kept = block.sub("", text)
    if install:
        kept += (f"\n{HOOK_BEGIN}\n[ -r {FUNCTIONS} ] && . {FUNCTIONS}\n{HOOK_END}\n")
    if kept == text:
        return
    temporary = path.with_name("." + path.name + ".mcpgw")
    temporary.write_text(kept, encoding="utf-8")
    shutil.copymode(path, temporary)
    temporary.replace(path)


def write_functions(employee: str) -> None:
    FUNCTIONS.write_text(launcher_functions(SHIM_DIR, employee), encoding="utf-8")
    FUNCTIONS.chmod(0o644)
    for rc in RC_FILES:
        edit_hook(rc, True)


def remove_functions() -> None:
    FUNCTIONS.unlink(missing_ok=True)
    for rc in RC_FILES:
        edit_hook(rc, False)


def replace_launcher(name: str, managed: str, shell: Path) -> str:
    shim = SHIM_DIR / name
    exists, ours = shim_state(shim)
    if exists and not ours:
        keep = replaced_dir(managed)
        # A symlink keeps its target; a real file keeps its bytes. Writing to the path without
        # unlinking first would follow the link and overwrite the program it points at.
        if shim.is_symlink():
            (keep / (name + ".symlink")).write_text(os.readlink(shim), encoding="utf-8")
        else:
            shutil.copy2(shim, keep / name)
    shim.unlink(missing_ok=True)
    # The harness runs in the managed account's home. Its own working directory is not readable by
    # that account, and starting a child from a directory it cannot search fails - which is how the
    # header helper failed on PJ1. `cd /` keeps that out of the way; the login shell moves to $HOME.
    # The entry wrapper by absolute path: the managed account's own ~/.local/bin comes first on its
    # PATH, and a harness installer that ran there at login (PJ1, 10-15) put an unapproved copy in it
    # that AppArmor then refused. Only the wrapper next to the login shell moves into the harness profile.
    shim.write_text(MARK.decode() + " managed harness launcher\n"
                    'command="' + str(shell.parent / name) + '"\n'
                    'for argument in "$@"; do command+=" $(printf %q "$argument")"; done\n'
                    'cd / || exit 1\n'
                    f'exec sudo -n -u {managed} -- "{shell}" -c "cd \\"\\$HOME\\" && $command"\n', encoding="utf-8")
    shim.chmod(0o755)
    return str(shim)


def remove_shims(managed: str) -> None:
    keep = PROGRAMS / managed / "replaced"
    for name in ("codex", "claude"):
        shim = SHIM_DIR / name
        if not shim_state(shim)[1]:
            continue
        shim.unlink()
        link, copied = keep / (name + ".symlink"), keep / name
        if link.is_file():
            shim.symlink_to(link.read_text(encoding="utf-8").strip())
            link.unlink()
        elif copied.is_file():
            shutil.move(copied, shim)
    SUDOERS.unlink(missing_ok=True)
    remove_functions()


# -- the managed installer ----------------------------------------------------------

def installed(account: str) -> bool:
    return (STATE / account / "config.json").is_file()


def rollback(account: str) -> None:
    # The kit's own installer, not the copy under /usr/local: a device installed by an older kit
    # is removed by the newest removal logic.
    step(f"기존 설치 제거: {account}")
    remove_shims(account)
    run(sys.executable, "-B", str(HERE / "managed-linux.py"), "rollback", "--user", account, check=False)


def close_sessions(account: str) -> None:
    """The profile and the firewall attach on the next sign-in, so no session of that account may
    outlive the install. The installer closes them instead of asking the employee to."""
    run("loginctl", "terminate-user", account, check=False, quiet=True,
        stderr=subprocess.DEVNULL)
    run("pkill", "-u", account, check=False, quiet=True, stderr=subprocess.DEVNULL)
    # The enforcer refuses while any process of the account is alive; a harness or a pending model
    # sign-in takes a moment to exit after the signal (10-23 kuku VM). Wait, then force.
    for _ in range(20):
        if run("pgrep", "-u", account, check=False, quiet=True).returncode:
            return
        time.sleep(0.5)
    run("pkill", "-KILL", "-u", account, check=False, quiet=True, stderr=subprocess.DEVNULL)
    time.sleep(1)


def failure_reason(output: str) -> str:
    """The line that says why, not the last one: the enforcer's refusal ("...: error: ...") is printed
    before the wrapper's "Command [...] returned non-zero" line, which only names the program (10-23 kuku VM)."""
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if ": error: " in line:
            return line.split(": error: ", 1)[1][:300]
    for line in reversed(lines):
        if not line.startswith(("Traceback", "File ", "raise ", "subprocess.")) and "returned non-zero" not in line:
            return line[:300]
    return lines[-1][:300] if lines else ""


def install_managed(account: str, placed: dict[str, dict], enrollment: Path, owner_uid: int | None = None) -> dict:
    step(f"관리형 연결 설치: {account}")
    close_sessions(account)
    clients = [part for name, item in placed.items() for part in ("--client", f"{name}={item['path']}")]
    done = subprocess.run([sys.executable, "-B", str(HERE / "managed-linux.py"), "install", "--user", account,
                           *(["--owner-uid", str(owner_uid)] if owner_uid is not None else []),
                           "--enrollment", str(enrollment), *clients], capture_output=True, text=True)
    if done.returncode:
        raise Failed(failure_reason(done.stderr or done.stdout) or "관리형 연결 설치가 실패했습니다")
    return json.loads(done.stdout.splitlines()[-1])


# Each harness keeps its own sign-in in the managed account's home, so each is asked once.
LOGINS = {"codex": (".codex/auth.json", "codex login --device-auth"),
          "claude": (".claude/.credentials.json", "claude auth login")}


def harness_login(account: str, harnesses: list[str]) -> dict[str, bool]:
    """The model sign-in, in the managed account, while the installer still has the console.

    Interactive by design: the harness prints a one-time URL (and code) for the employee. Skipped
    when a credential is already there, and never fatal — Ctrl+C skips one, and the harness asks
    again on its first run.
    """
    home = Path(pwd.getpwnam(account).pw_dir)
    shell = Path("/usr/local/lib/mcpgw-enforcement") / ("mcpgw-" + account) / "login-shell"
    signed: dict[str, bool] = {}
    for name in harnesses:
        credential, command = LOGINS[name]
        if (home / credential).is_file():
            # The file only proves a sign-in once happened: a session the provider has since revoked
            # (PJ1, 10-22) still reports "Logged in" and then fails every model call with 401.
            print(f"기존 {name} 로그인을 그대로 씁니다. 모델 응답이 401·로그인 오류면 다시 로그인하세요: "
                  f"sudo -u {account} {shell} -c '{command}'")
            signed[name] = True
            continue
        step("Codex 장치 코드 로그인" if name == "codex" else f"{name} 모델 로그인")
        try:
            code = subprocess.run(["runuser", "-u", account, "--", str(shell), "-c", command], check=False).returncode
        except KeyboardInterrupt:
            code = 130
        signed[name] = code == 0
        if code and name == "codex":
            # An organization that turns off device-code sign-in refuses here, and the employee is left
            # with a connected endpoint and no model. Both ways out, in one line each.
            print(f"모델 로그인은 나중에 해도 됩니다. ChatGPT 보안 설정에서 장치 코드 로그인을 켠 뒤 다시: "
                  f"sudo -u {account} {shell} -c 'codex login --device-auth'")
        elif code:
            print(f"{name} 로그인은 나중에 해도 됩니다. 처음 실행하면 로그인 화면이 나옵니다.")
    return signed


def self_check() -> None:
    """The launcher replacement, where getting it wrong overwrites the program it replaces."""
    import tempfile
    global SHIM_DIR, PROGRAMS, SUDOERS, FUNCTIONS, RC_FILES
    with tempfile.TemporaryDirectory(prefix="mcpgw-selfcheck-") as folder:
        root = Path(folder)
        SHIM_DIR, PROGRAMS, SUDOERS = root / "bin", root / "lib", root / "sudoers"
        FUNCTIONS, RC_FILES = root / "mcpgw-managed.sh", (root / "bash.bashrc", root / "absent.rc")
        SHIM_DIR.mkdir()
        shell = root / "enforcement/mcpgw-m/login-shell"
        shell.parent.mkdir(parents=True)
        shell.write_text("#!/bin/sh\n")
        target = root / "node_modules/codex.js"
        target.parent.mkdir(parents=True)
        target.write_text("original launcher\n")
        (SHIM_DIR / "codex").symlink_to(target)
        (SHIM_DIR / "claude").write_text("a real file\n")
        assert shim_state(SHIM_DIR / "codex") == (True, False)
        written = [replace_launcher(name, "m", shell) for name in ("codex", "claude")]
        # The replaced program is untouched and both launchers are ours now.
        assert target.read_text() == "original launcher\n", "wrote through the symlink"
        assert all(shim_state(SHIM_DIR / name) == (True, True) for name in ("codex", "claude"))
        # Run it against a sudo stub: an argument with spaces and quotes has to reach the harness
        # as one argument, which is where a hand-built command line goes wrong.
        stub = root / "stub"
        stub.mkdir()
        (stub / "sudo").write_text('#!/bin/bash\nwhile [ "$1" != "-c" ]; do shift; done\nprintf %s "$2"\n')
        (stub / "sudo").chmod(0o755)
        reconstructed = subprocess.run([str(SHIM_DIR / "codex"), "exec", 'say "hi there"'],
                                       capture_output=True, text=True,
                                       env={**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "HOME": "/managed"})
        assert reconstructed.stdout.startswith(f'cd "$HOME" && {shell.parent / "codex"} exec '), reconstructed
        split = subprocess.run(["bash", "-c", 'eval "set -- $MCPGW_ARGS"; printf "%s|" "$@"'], capture_output=True,
                               text=True, env={**os.environ, "MCPGW_ARGS": reconstructed.stdout.split("codex ", 1)[1]})
        assert split.stdout == 'exec|say "hi there"|', split
        me = pwd.getpwuid(os.getuid()).pw_name
        write_functions(me)
        assert FUNCTIONS.is_file() and not RC_FILES[1].exists()
        remove_shims("m")
        assert (SHIM_DIR / "codex").is_symlink() and (SHIM_DIR / "codex").resolve() == target.resolve()
        assert (SHIM_DIR / "claude").read_text() == "a real file\n", "lost the replaced file"
        assert written and not SUDOERS.exists() and not FUNCTIONS.exists()
        # An employee's ~/.local/bin comes first on PATH. Typed in an interactive shell, the launcher
        # must still win; with the launcher gone the same command must still reach the harness.
        rc = RC_FILES[0]
        rc.write_text('[ -z "$PS1" ] && return\n')
        before = rc.read_text()
        early = root / "early"
        for folder_, label in ((early, "unmanaged"), (SHIM_DIR, "managed")):
            folder_.mkdir(exist_ok=True)
            for name in ("codex", "claude"):
                (folder_ / name).unlink(missing_ok=True)
                (folder_ / name).write_text(f'#!/bin/sh\necho "{label} {name} $*"\n')
                (folder_ / name).chmod(0o755)
        write_functions(me)
        write_functions(me)
        assert rc.read_text().count(HOOK_BEGIN) == 1, "the rc hook must be added once"
        typed = subprocess.run(["bash", "-c", f"PS1=x; PATH={early}:{SHIM_DIR}:/usr/bin:/bin; . {rc}; claude mcp list; codex"],
                               capture_output=True, text=True)
        assert typed.stdout == "managed claude mcp list\nmanaged codex \n", typed
        # The managed account reads the same /etc/profile.d: it must see no function, or its own
        # `claude` would call the launcher from inside the confined account.
        write_functions("another-account")
        other = subprocess.run(["bash", "-c", f"PS1=x; PATH={early}:{SHIM_DIR}:/usr/bin:/bin; . {rc}; claude"],
                               capture_output=True, text=True)
        assert other.stdout == "unmanaged claude \n", other
        write_functions(me)
        (SHIM_DIR / "claude").unlink()
        gone = subprocess.run(["bash", "-c", f"PATH={early}:/usr/bin:/bin; . {FUNCTIONS}; claude"],
                              capture_output=True, text=True)
        assert gone.stdout == "unmanaged claude \n", gone
        remove_functions()
        assert rc.read_text() == before and not FUNCTIONS.exists(), "rc file not restored"
    print("bootstrap self-check OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--user", help="설치 대상 직원 계정(기본: 설치를 실행한 계정)")
    parser.add_argument("--enrollment", type=Path, default=HERE / "enrollment.json")
    parser.add_argument("--remove", action="store_true", help="이 PC의 연결만 제거")
    parser.add_argument("--skip-login", action="store_true", help="하네스 모델 로그인을 건너뜀")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if os.name != "posix":
        print("이 설치기는 Linux용입니다. Windows에서는 install.cmd를 실행하세요.", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("관리자 권한이 필요합니다. install.sh로 실행하세요.", file=sys.stderr)
        return 2
    try:
        if not args.remove:
            check_python()
            if not args.enrollment.is_file():
                raise Failed(f"설치 키트의 enrollment.json이 없습니다: {args.enrollment}")
            spec = importlib.util.spec_from_file_location("managed_tls", HERE / "managed-linux.py")
            managed_tls = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(managed_tls)
            managed_tls.verify_transport(json.loads(args.enrollment.read_text()))
        employee = employee_account(args.user)
        account, companion = managed_account(employee)
        if args.remove:
            rollback(account)
            print(json.dumps({"removed": account}, ensure_ascii=False))
            return 0
        ensure_packages()
        step("승인 하네스 배치")
        placed = place_harnesses(employee)
        if installed(account):
            rollback(account)
        try:
            result = install_managed(account, placed, args.enrollment,
                                     pwd.getpwnam(employee).pw_uid if companion else None)
            if companion:
                step("직원 계정에서 바로 실행되게 연결")
                result["launchers"] = write_shims(employee, account, tuple(placed))
        except Failed:
            # Half a connection is worse than none: the account keeps its own shell and firewall.
            if installed(account) or (SHIM_DIR / "codex").is_file():
                rollback(account)
            raise
        close_step()  # 사람이 로그인하는 시간은 설치 소요에 넣지 않는다
        if not args.skip_login:
            result["model_signed_in"] = harness_login(account, list(placed))
        result.update(employee=employee, managed_account=account,
                      harnesses={name: item.get("digests", {}) for name, item in placed.items()})
        print(json.dumps(result, ensure_ascii=False))
        print("\n이전 연결의 활성화를 이어받았습니다. 바로 사용할 수 있습니다." if result.get("state") == "active"
              else "\n연결을 신청했습니다. 조직 관리자가 콘솔에서 활성화하면 사용할 수 있습니다.")
        print("연결 상태 확인: mcpgw-status" + (f" (제한된 계정에서는 cat /usr/local/lib/mcpgw-managed/status-{account}.txt)"
                                              if not companion else ""))
        print("로컬 MCP 준비(폴더 만들기·이미지 받기)는 활성화 뒤 백그라운드로 진행됩니다. 진행과 직원 문서 폴더 위치: mcpgw-status",
              flush=True)
        # A terminal opened before the install has neither the launcher functions nor a fresh PATH.
        names = " 또는 ".join(placed)
        # With the employee's own launchers replaced (D-228) a terminal opened before the install works too.
        print((f"평소 계정({employee})에서 {names}를 실행하세요." if result.get("home_launchers")
               else f"새 터미널을 열어 평소 계정({employee})에서 {names}를 실행하세요.") if companion
              else f"이 계정에서 {names}를 실행하세요.")
        signed = result.get("model_signed_in") or {}
        if "codex" in placed and not signed.get("codex"):
            print("Codex 로그인: codex login --device-auth")
        if "claude" in placed and not signed.get("claude"):
            print("Claude 로그인: claude를 실행한 뒤 /login")
        slow = [f"{label.split(':')[0]} {seconds}초" for label, seconds in timings if seconds]
        if slow:
            print(f"설치 소요(로그인 제외): {' · '.join(slow)} · 합계 {sum(seconds for _, seconds in timings)}초")
        return 0
    except Failed as exc:
        print(f"\n설치하지 못했습니다: {exc}", file=sys.stderr)
        return 1
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        print(f"\n설치하지 못했습니다: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
