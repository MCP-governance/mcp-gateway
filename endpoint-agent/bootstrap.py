#!/usr/bin/env python3
"""One elevation, one connected endpoint: everything between "run the file" and "type claude".

The employee runs install.sh from the kit, confirms the sudo prompt once and answers nothing else.
Simple mode (the default, D-239) leaves the employee's own account and harnesses as they are and adds
the managed settings, the header helper and the reporting service; the Gateway activates the PC when
its install checks pass (if the organization allows it) and still decides every call. --isolated (or a
kit downloaded with 「고급: 격리 계정」) is the earlier install: required packages, the approved harness
binaries, a separate managed account for an administrator, AppArmor/nftables confinement, and an
administrator's activation. The install ends by measuring a model answer, the tool count and one
approved server's initialize. An existing install is replaced after enrollment and policy retrieval, so the same file is also the
repair, the reinstall and the switch between modes.
"""
from __future__ import annotations

import argparse
import contextlib
import grp
import hashlib
import importlib.util
import io
import json
import os
import pwd
import re
import shlex
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
MIN_PYTHON = (3, 8)  # Ubuntu 20.04; Claude Code·Codex themselves need 20.04+
# 도구 → 패키지. 설치 첫머리에 한 번 조회해 없는 것만 모아 패키지 관리자를 한 번 갱신하고 한 번에 설치한다.
# openssl은 로컬 MCP 승인 서명 검증(local-runner)이, curl은 하네스·점검 도구가 쓴다.
REQUIRED = {"gcc": "gcc", "nft": "nftables", "apparmor_parser": "apparmor-utils", "curl": "curl", "openssl": "openssl"}
# Simple mode compiles and confines nothing; openssl (local MCP signatures) and curl are tried, never required.
OPTIONAL = {"curl": "curl", "openssl": "openssl"}
COMPANION_COMMENT = "MCP managed harness account"
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
    if kwargs.get("stderr") == subprocess.DEVNULL:
        kwargs["stderr"] = subprocess.PIPE
    done = subprocess.run(command, check=False, text=True,
                          stdout=subprocess.DEVNULL if quiet else None, **kwargs)
    if done.returncode:
        error = subprocess.CalledProcessError(done.returncode, command, stderr=done.stderr)
        if DIAGNOSTIC:
            DIAGNOSTIC(Path(command[0]).name, error)
        if check:
            raise error
    return done


def out(*command: str) -> str:
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    return done.stdout.strip()


class _Lines:
    """Until main() opens the screen (and in --self-check): one line per step."""
    rows: list = []

    def step(self, message):
        print(f"[{message}]", flush=True)

    def close_step(self, mark="✓"):
        pass

    def say(self, text):
        print(text, flush=True)


SCREEN = _Lines()
DIAGNOSTIC = None


def step(message: str) -> None:
    """한 단계. 화면이 단계마다 소요 시간을 재고, 끝에 결과 세 칸과 다음 할 일을 보인다(D-239)."""
    SCREEN.step(message)


def close_step() -> None:
    SCREEN.close_step()


def say(text: str) -> None:
    SCREEN.say(text)


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
        raise Failed("Python 3.8 이상이 필요합니다(설치기 판본 %d.%d)" % sys.version_info[:2])
    system = Path("/usr/bin/python3")
    if not system.is_file():
        raise Failed("관리형 서비스가 쓰는 /usr/bin/python3가 없습니다")
    found = out(str(system), "-c", "import sys;print('%d.%d' % sys.version_info[:2])")
    if not re.fullmatch(r"\d+\.\d+", found) or tuple(map(int, found.split("."))) < MIN_PYTHON:
        raise Failed(f"/usr/bin/python3가 3.8 미만입니다({found or '판본 확인 실패'})")


def has_engine() -> bool:
    return any(Path("/usr/bin", name).is_file() for name in ENGINE_BINARIES)


def install_packages(manager: str, names: list[str], env: dict) -> bool:
    command = {"apt-get": ["apt-get", "install", "-y", "-qq"], "dnf": ["dnf", "install", "-y", "-q"],
               "pacman": ["pacman", "-S", "--needed", "--noconfirm"]}[manager]
    return run(*command, *[RENAMED.get(manager, {}).get(name, name) for name in names],
               check=False, quiet=True, env=env).returncode == 0


def ensure_packages(isolated: bool = True) -> None:
    """필수 구성요소와 컨테이너 엔진을 설치 한 번에 갖춘다. 없는 도구만 한 번에 조회·설치하고(패키지 관리자 갱신도 한 번),
    엔진은 못 받아도 설치를 멈추지 않는다: 원격 MCP는 엔진 없이 쓰고, 로컬 MCP만 엔진 설치 뒤 쓸 수 있다.
    간편 모드는 컴파일러·방화벽·AppArmor 도구가 필요 없고, curl·openssl도 없으면 시도만 한다(D-239)."""
    wanted = REQUIRED if isolated else OPTIONAL
    missing = [tool for tool in wanted if not shutil.which(tool)]
    if missing or not has_engine():
        install_missing(missing, required=isolated)
    start_engine()
    ensure_toml()


TOML_CHECK = ("import sys, importlib.util; sys.path.append('/usr/lib/python3/dist-packages'); "
              "sys.exit(0 if any(importlib.util.find_spec(n) for n in ('tomllib', 'tomli', 'toml')) else 1)")


def ensure_toml() -> None:
    """The endpoint agent reads Codex's config.toml. Python 3.11+ has tomllib; Ubuntu 20.04·22.04 (3.8·3.10)
    need the distribution's tomli (22.04) or toml (20.04) package, or Codex settings go unread. Best effort."""
    if sys.version_info >= (3, 11) or run("/usr/bin/python3", "-I", "-c", TOML_CHECK, check=False, quiet=True,
           stderr=subprocess.DEVNULL).returncode == 0 or not shutil.which("apt-get"):
        return
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    for package in ("python3-tomli", "python3-toml"):
        if run("apt-get", "install", "-y", "-qq", package, check=False, quiet=True, env=env,
               stderr=subprocess.DEVNULL).returncode == 0:
            return
    say("Codex 설정(TOML)을 읽을 패키지를 설치하지 못했습니다: sudo apt-get install python3-tomli")


def install_missing(missing: list[str], required: bool = True) -> None:
    manager = next((m for m in ENGINES if shutil.which(m)), None)
    if not manager:
        if missing and required:
            raise Failed("필수 구성요소를 설치할 패키지 관리자를 찾지 못했습니다: " + ", ".join(missing))
        say("컨테이너 엔진이 없습니다. 로컬 MCP는 podman 또는 docker를 설치한 뒤 사용할 수 있습니다.")
        return
    step("필수 구성요소 설치" if missing else "컨테이너 엔진 설치")
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    refreshed = manager != "apt-get" or run("apt-get", "update", "-qq", check=False, quiet=True, env=env,
                                            stderr=subprocess.DEVNULL).returncode == 0
    names = REQUIRED if required else OPTIONAL
    if missing:
        if not refreshed or not install_packages(manager, [names[tool] for tool in missing], env):
            if required:
                raise Failed(f"필수 구성요소 설치가 실패했습니다({manager}). 사내 패키지 저장소를 확인하세요")
            say("curl·openssl을 설치하지 못했습니다. 원격 MCP는 그대로 쓸 수 있습니다.")
        still = [tool for tool in missing if not shutil.which(tool)]
        if still and required:
            raise Failed("설치 후에도 없는 필수 구성요소: " + ", ".join(still))
    if not has_engine() and not (refreshed and install_packages(manager, [ENGINES[manager]], env)):
        say(f"컨테이너 엔진을 설치하지 못했습니다. 로컬 MCP는 엔진 설치 뒤 사용할 수 있습니다: "
            f"sudo {INSTALL_VERB[manager]} {ENGINES[manager]}")


def start_engine() -> None:
    """docker는 데몬이 떠 있어야 하고 재부팅 뒤에도 켜져야 한다. podman은 데몬이 없다(러너는 podman을 먼저 쓴다)."""
    if Path("/usr/bin/docker").is_file() and not Path("/usr/bin/podman").is_file():
        if run("systemctl", "enable", "--now", "docker", check=False, quiet=True, stderr=subprocess.DEVNULL).returncode:
            say("docker 서비스를 켜지 못했습니다. 로컬 MCP는 켠 뒤 사용할 수 있습니다: sudo systemctl enable --now docker")


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
            # PC에 있는 하네스만 관리한다(D-216). 없는 것은 나중에 설치하고 키트를 다시 실행하면 추가된다.
            # 알리지 않는다: 하나도 없으면 아래에서 멈추고, 끝 안내는 배치한 것만 적는다.
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
    return ((STATE / account).exists()
            or (Path("/etc/systemd/system") / f"mcpgw-managed-{account}.service").exists()
            or (Path("/etc/systemd/system") / f"mcpgw-egress-{account}.service").exists())


def rollback(account: str) -> None:
    # The kit's own installer, not the copy under /usr/local: a device installed by an older kit
    # is removed by the newest removal logic.
    step(f"기존 설치 제거: {account}")
    done = subprocess.run([sys.executable, "-B", str(HERE / "managed-linux.py"), "rollback", "--user", account],
                          capture_output=True, text=True)
    if done.returncode:
        raise subprocess.CalledProcessError(done.returncode, "managed rollback", stderr=done.stderr)
    remove_shims(account)


def companion_of(employee: str) -> str:
    return ("managed-" + employee)[:31]


def remove_companion(employee: str) -> None:
    """The separate account an isolated install created, once nothing of it is installed. Only one this kit
    made (its comment says so); its home stays, with whatever the employee kept there (D-239)."""
    name = companion_of(employee)
    try:
        entry = pwd.getpwnam(name)
    except KeyError:
        return
    if entry.pw_gecos.split(",")[0] != COMPANION_COMMENT or installed(name):
        return
    close_sessions(name)
    run("userdel", name, check=False, quiet=True, stderr=subprocess.DEVNULL)
    say(f"격리 계정 {name}을 지웠습니다(홈 폴더 {entry.pw_dir}는 남김).")


def as_employee(employee: str, command: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """A command in the employee's own login shell: their PATH, their home, their harness."""
    return subprocess.run(["runuser", "-l", employee, "-c", command], capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL)


def find_clients(employee: str) -> dict[str, str]:
    """Simple mode: where the employee's own terminal finds claude and codex. Nothing is copied or pinned."""
    found = {}
    for name in ("claude", "codex"):
        try:
            path = as_employee(employee, f"command -v {name}").stdout.strip().splitlines()
        except (OSError, subprocess.SubprocessError):
            path = []
        if path and path[-1].startswith("/"):
            found[name] = path[-1]
    if not found:
        say("이 PC에서 claude·codex를 찾지 못했습니다. 연결은 설치하고, 하네스를 설치하면 바로 관리됩니다.")
    return found


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
    """Why the managed install failed, in the words that say it: the enforcer's refusal ("...: error: ..."),
    or the failing command's own error output plus the exception that named the command. The last line alone
    was a traceback line or a truncated "Command [...]" (10-23 kuku VM)."""
    lines = [line.rstrip() for line in (output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if ": error: " in line:
            return line.split(": error: ", 1)[1].strip()
    start = next((k for k in range(len(lines) - 1, -1, -1) if lines[k].startswith("Traceback")), None)
    before = [line.strip() for line in (lines[:start] if start is not None else [])
              if not line.startswith(("[", "{", "usermod:"))][-3:]
    error = next((line.strip() for line in reversed(lines)
                  if re.match(r"^[A-Za-z_][\w.]*(Error|Exception):", line.strip())), "")
    return " / ".join(before + ([error] if error else [])) or (lines[-1].strip() if lines else "")


def install_managed(account: str, placed: dict[str, dict], enrollment: Path, owner_uid: int | None = None,
                    mode: str = "isolated", *, prepared=None) -> dict:
    step(f"관리형 연결 설치: {account}")
    if mode == "isolated":
        close_sessions(account)  # simple mode leaves the employee's own sessions running
    spec = importlib.util.spec_from_file_location("managed_install", HERE / "managed-linux.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    arguments = argparse.Namespace(user=account, mode=mode, owner_uid=owner_uid, enrollment=enrollment,
                                   broker_binding="warn", client=[f"{name}={item['path']}" for name, item in placed.items()])
    # The enrollment result stays in this root process, never argv, environment or a user-writable receipt.
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        core.install(arguments, prepared=prepared)
    return json.loads(output.getvalue().splitlines()[-1])


# Each harness keeps its own sign-in in the account's home, so each is asked once.
LOGINS = {"codex": (".codex/auth.json", "codex login --device-auth"),
          "claude": (".claude/.credentials.json", "claude auth login")}


def harness_login(account: str, harnesses: list[str], simple: bool = False) -> dict[str, bool]:
    """The model sign-in, in the account the harness runs in, while the installer still has the console.

    Simple mode is the employee's own account: an existing sign-in is simply theirs, and with no terminal
    (a remote or scripted install) nothing is asked. Interactive otherwise: the harness prints a one-time
    URL (and code). Never fatal — Ctrl+C skips one, and the harness asks again on its first run.
    """
    home = Path(pwd.getpwnam(account).pw_dir)
    shell = Path("/usr/local/lib/mcpgw-enforcement") / ("mcpgw-" + account) / "login-shell"
    signed: dict[str, bool] = {}
    for name in harnesses:
        credential, command = LOGINS[name]
        if (home / credential).is_file():
            # The file only proves a sign-in once happened: a session the provider has since revoked
            # (PJ1, 10-22) still reports "Logged in" and then fails every model call with 401. The
            # model answer measured at the end says which.
            signed[name] = True
            continue
        if not sys.stdin.isatty():
            # A remote or scripted install has nobody to read the code: asking would hang it for 15 minutes (pj2 10-25).
            signed[name] = False
            continue
        step("Codex 장치 코드 로그인" if name == "codex" else f"{name} 모델 로그인")
        pause_screen()
        try:
            argv = (["runuser", "-l", account, "-c", command] if simple
                    else ["runuser", "-u", account, "--", str(shell), "-c", command])
            code = subprocess.run(argv, check=False).returncode
        except KeyboardInterrupt:
            code = 130
        finally:
            resume_screen()
        signed[name] = code == 0
        if code and name == "codex":
            # An organization that turns off device-code sign-in refuses here, and the employee is left
            # with a connected endpoint and no model. Both ways out, in one line each.
            say("모델 로그인은 나중에 해도 됩니다. ChatGPT 보안 설정에서 장치 코드 로그인을 켠 뒤 다시: "
                + ("codex login --device-auth" if simple else f"sudo -u {account} {shell} -c 'codex login --device-auth'"))
        elif code:
            say(f"{name} 로그인은 나중에 해도 됩니다. 처음 실행하면 로그인 화면이 나옵니다.")
    return signed


def pause_screen() -> None:
    getattr(SCREEN, "pause", lambda: None)()


def resume_screen() -> None:
    getattr(SCREEN, "resume", lambda: None)()


def wait_active(managed, account: str, seconds: int = 60) -> dict:
    """The service's own summary until the device is active (the Gateway activates a new simple-mode PC on its
    first passing heartbeat, about 10 s after the install) or the wait ends."""
    deadline = time.monotonic() + seconds
    summary = {}
    while time.monotonic() < deadline:
        try:
            summary = json.loads(managed.status_path(account, "json").read_text())
        except (OSError, ValueError):
            summary = {}
        if summary.get("state") in ("active", "quarantined", "revoked"):
            break
        time.sleep(2)
    return summary


def model_cell(managed, account: str, harnesses: list[str], simple: bool) -> tuple[str, str]:
    """① A real model answer from the harness the employee will type, as that account (D-239)."""
    name = next((h for h in ("claude", "codex") if h in harnesses), None)
    if not name:
        return ("모델 응답", "— (하네스 없음)")
    observer = managed.load_module("model_observer", HERE / "agent.py")
    prompt = observer.MODEL_PROMPT
    command = (f"claude -p {shlex.quote(prompt)}" if name == "claude"
               else f"codex exec --skip-git-repo-check {shlex.quote(prompt)}")
    if simple:
        # Before /etc/environment is read again by a new login, pass the CA the harness needs explicitly.
        config = json.loads((STATE / account / "config.json").read_text())
        prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in managed.ca_environment(config).items())
        argv = ["runuser", "-l", account, "-c", (prefix + " " if prefix else "") + command]
    else:
        argv = ["runuser", "-u", account, "--", str(Path("/usr/local/lib/mcpgw-enforcement") / ("mcpgw-" + account)
                                                    / "login-shell"), "-c", command]
    found = observer.model_check(argv)
    return ("모델 응답", f"{name} 정상 · {found['seconds']}초" if found["ok"]
            else f"{name} 실패 · {found['detail'] or '응답 없음'}")


def install_check(managed, account: str, harnesses: list[str], simple: bool) -> tuple[list, str]:
    """The three cells (model answer, tool count, one server's initialize) and the next thing to do."""
    step("설치 확인")
    summary = wait_active(managed, account)
    SCREEN.summary = summary
    state = summary.get("state")
    if state != "active":
        waiting = {"pending": "관리자 활성화 대기", "quarantined": "격리됨", "revoked": "등록 해제됨"}.get(state, "상태 확인 안 됨")
        cells = [model_cell(managed, account, harnesses, simple), ("도구", "— (" + waiting + ")"), ("서버 연결", "—")]
        next_line = ("관리자 활성화 뒤 claude·codex를 실행하세요(활성화되면 자동으로 연결됩니다)" if state == "pending"
                     else "mcpgw-status로 상태를 확인하세요")
        close_step()
        return cells, next_line
    try:
        connection = managed.connection_cells(managed.check_connection(summary), len(summary.get("names") or []))
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
        connection = [("도구", "—"), ("서버 연결", f"실패 · {exc}")]
    cells = [model_cell(managed, account, harnesses, simple), *connection]
    close_step()
    if re.search(r"log ?in|/login|401|로그인", cells[0][1], re.I):
        shell = Path("/usr/local/lib/mcpgw-enforcement") / ("mcpgw-" + account) / "login-shell"
        return cells, ("모델 로그인: claude auth login" if simple
                       else f"격리 계정 모델 로그인: sudo -u {account} {shell} -c 'claude auth login'")
    healthy = all("실패" not in value for _, value in cells)
    return cells, ("새 터미널에서 claude 또는 codex를 실행하세요" if healthy else "mcpgw-status --check 로 다시 확인하세요")


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
    global SCREEN, DIAGNOSTIC
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--user", help="설치 대상 직원 계정(기본: 설치를 실행한 계정)")
    parser.add_argument("--enrollment", type=Path, default=HERE / "enrollment.json")
    parser.add_argument("--remove", action="store_true", help="이 PC의 연결만 제거")
    parser.add_argument("--isolated", action="store_true",
                        help="고급: 별도 관리 계정·AppArmor·UID 방화벽으로 하네스를 격리(관리자 활성화)")
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
    started = time.monotonic()
    try:
        check_python()
        spec = importlib.util.spec_from_file_location("managed_linux", HERE / "managed-linux.py")
        managed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(managed)
        DIAGNOSTIC = managed.diagnostic
        bundle = {}
        if not args.remove:
            if not args.enrollment.is_file():
                raise Failed(f"설치 키트의 enrollment.json이 없습니다: {args.enrollment}")
            bundle = json.loads(args.enrollment.read_text())
            managed.verify_transport(bundle)
        employee = employee_account(args.user)
        if args.remove:
            for account in (employee, companion_of(employee)):
                if installed(account):
                    rollback(account)
            remove_shims(companion_of(employee))
            remove_companion(employee)
            print(json.dumps({"removed": employee}, ensure_ascii=False))
            return 0
        isolated = args.isolated or bundle.get("isolated") is True
        SCREEN = managed.Screen("내 PC 연결 · " + ("격리 계정" if isolated else "간편 모드"))
        try:
            return connect(managed, employee, isolated, args, started)
        except BaseException:
            SCREEN.close_step("✗")
            raise
        finally:
            if SCREEN.window is not None:
                SCREEN.finish(wait=0)  # the steps up to the failure stay in the scrollback
            SCREEN.stop()
    except Failed as exc:
        print(f"\n설치하지 못했습니다: {exc}", file=sys.stderr)
        return 1
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        if DIAGNOSTIC:
            DIAGNOSTIC("bootstrap", exc)
        print(f"\n설치하지 못했습니다: {type(exc).__name__}", file=sys.stderr)
        return 1


def connect(managed, employee: str, isolated: bool, args, started: float) -> int:
    step("구성요소 확인")
    ensure_packages(isolated)
    if isolated:
        account, companion = managed_account(employee)
    else:
        account, companion = employee, False
    bundle = json.loads(args.enrollment.read_text())
    credentials = [bundle.get("enrollment_token"), bundle.get("device_key")]
    try:
        prepared = managed.enroll(bundle, account, pwd.getpwnam(account).pw_uid, "isolated" if isolated else "simple")
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        managed.diagnostic("enroll", exc, credentials)
        raise Failed("연결 등록·정책 수신에 실패했습니다. 기존 설치는 유지됩니다.") from None
    credentials.append(prepared[0]["device_key"])
    managed.diagnostic("prepared", None)
    for previous in (employee, companion_of(employee)):
        if installed(previous):
            rollback(previous)
    if isolated:
        step("승인 하네스 배치")
        placed = place_harnesses(employee)
    else:
        remove_shims(companion_of(employee))
        remove_companion(employee)
        step("하네스 찾기")
        placed = {name: {"path": path} for name, path in find_clients(employee).items()}
    try:
        result = install_managed(account, placed, args.enrollment,
                                 pwd.getpwnam(employee).pw_uid if companion else None,
                                 "isolated" if isolated else "simple", prepared=prepared)
        if companion:
            step("직원 계정에서 바로 실행되게 연결")
            result["launchers"] = write_shims(employee, account, tuple(placed))
    except (Failed, OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        managed.diagnostic("install", exc, credentials)
        # Half a connection is worse than none: the account keeps its own shell and firewall.
        if installed(account) or (SHIM_DIR / "codex").is_file():
            rollback(account)
        raise
    managed.diagnostic("installed", None)
    close_step()  # 사람이 로그인하는 시간은 설치 소요에 넣지 않는다
    installing = round(time.monotonic() - started)
    if not args.skip_login:
        result["model_signed_in"] = harness_login(account, list(placed), simple=not isolated)
    cells, next_line = install_check(managed, account, list(placed), simple=not isolated)
    result.update(employee=employee, managed_account=account, mode="isolated" if isolated else "simple",
                  harnesses=({name: item.get("digests", {}) for name, item in placed.items()} if isolated
                             else {name: item["path"] for name, item in placed.items()}),
                  checks=dict(cells), install_seconds=installing, total_seconds=round(time.monotonic() - started))
    if isolated and companion:
        say(f"격리 계정 {account}에서 실행됩니다. 평소 계정({employee})에서 {' 또는 '.join(placed)}를 실행하세요.")
    say("로컬 MCP 준비(폴더 만들기·이미지 받기)는 활성화 뒤 백그라운드로 진행됩니다.")
    say("연결 상태: mcpgw-status (실시간 화면) · mcpgw-status --check (연결 확인)")
    say(f"설치 소요(로그인 제외) {installing}초 · 확인까지 {result['total_seconds']}초")
    SCREEN.result(cells, next_line)
    SCREEN.finish()
    SCREEN.stop()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
