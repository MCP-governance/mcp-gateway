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
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPROVED = Path("/opt/mcpgw-approved")
PROGRAMS = Path("/usr/local/lib/mcpgw-managed")
STATE = Path("/var/lib/mcpgw-managed")
SHIM_DIR = Path("/usr/local/bin")
SUDOERS = Path("/etc/sudoers.d/mcpgw-managed")
PRIVILEGED = {"sudo", "wheel", "docker", "lxd", "libvirt", "root", "adm"}
PACKAGES = {"apt-get": ["gcc", "nftables", "apparmor-utils"],
            "dnf": ["gcc", "nftables", "apparmor-utils"],
            "pacman": ["gcc", "nftables", "apparmor"]}
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


def step(message: str) -> None:
    print(f"[{message}]", flush=True)


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

def ensure_packages() -> list[str]:
    missing = [tool for tool in ("gcc", "nft", "apparmor_parser") if not shutil.which(tool)]
    if not missing:
        return []
    manager = next((m for m in PACKAGES if shutil.which(m)), None)
    if not manager:
        raise Failed("필수 구성요소를 설치할 패키지 관리자를 찾지 못했습니다: " + ", ".join(missing))
    step("필수 구성요소 설치")
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    try:
        if manager == "apt-get":
            run("apt-get", "update", "-qq", quiet=True, env=env)
            run("apt-get", "install", "-y", "-qq", *PACKAGES[manager], quiet=True, env=env)
        elif manager == "dnf":
            run("dnf", "install", "-y", "-q", *PACKAGES[manager], quiet=True)
        else:
            run("pacman", "-S", "--needed", "--noconfirm", *PACKAGES[manager], quiet=True)
    except subprocess.CalledProcessError as exc:
        raise Failed(f"필수 구성요소 설치가 실패했습니다({manager}). 사내 패키지 저장소를 확인하세요") from exc
    still = [tool for tool in ("gcc", "nft", "apparmor_parser") if not shutil.which(tool)]
    if still:
        raise Failed("설치 후에도 없는 필수 구성요소: " + ", ".join(still))
    return missing


def search_roots(employee: str) -> list[Path]:
    home = Path(pwd.getpwnam(employee).pw_dir)
    roots = [HERE / "harness", Path("/usr/local/lib/node_modules"), Path("/usr/lib/node_modules"),
             home / ".npm-global/lib/node_modules", home / ".local/share/reflex", home / ".local/lib"]
    return [root for root in roots if root.exists()]


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
        return handle.read(4) == b"\x7fELF"


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
        source = release_directory(employee, name)
        if not source:
            if name == "claude" and (APPROVED / "claude").is_file():
                placed[name] = {"path": str(APPROVED / name), "source": "already-approved"}
                continue
            raise Failed(f"공식 {name} 설치를 찾지 못했습니다. {name}을 설치한 뒤 다시 실행하세요")
        files = ["codex", "codex-code-mode-host"] if name == "codex" else ["claude"]
        for item in files:
            origin, target = source / item, APPROVED / item
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


def write_shims(employee: str, managed: str) -> list[str]:
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
    written = []
    for name in ("codex", "claude"):
        shim = SHIM_DIR / name
        if shim.exists() and not shim.read_text(errors="replace").startswith("#!/bin/bash\n# mcpgw"):
            backup = PROGRAMS / managed / (name + ".original-path")
            backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            backup.write_text(str(shim.resolve()) + "\n", encoding="utf-8")
        shim.write_text("#!/bin/bash\n# mcpgw managed harness launcher\n"
                        'command="' + name + '"\n'
                        'for argument in "$@"; do command+=" $(printf %q "$argument")"; done\n'
                        f'exec sudo -n -u {managed} -- "{shell}" -c "$command"\n', encoding="utf-8")
        shim.chmod(0o755)
        written.append(str(shim))
    return written


def remove_shims(managed: str) -> None:
    for name in ("codex", "claude"):
        shim = SHIM_DIR / name
        if shim.is_file() and shim.read_text(errors="replace").startswith("#!/bin/bash\n# mcpgw"):
            shim.unlink()
            recorded = PROGRAMS / managed / (name + ".original-path")
            if recorded.is_file():
                original = Path(recorded.read_text(encoding="utf-8").strip())
                if original.exists():
                    shim.symlink_to(original)
    SUDOERS.unlink(missing_ok=True)


# -- the managed installer ----------------------------------------------------------

def installed(account: str) -> bool:
    return (STATE / account / "config.json").is_file()


def rollback(account: str) -> None:
    # The kit's own installer, not the copy under /usr/local: a device installed by an older kit
    # is removed by the newest removal logic.
    step(f"기존 설치 제거: {account}")
    remove_shims(account)
    run(sys.executable, str(HERE / "managed-linux.py"), "rollback", "--user", account, check=False)


def close_sessions(account: str) -> None:
    """The profile and the firewall attach on the next sign-in, so no session of that account may
    outlive the install. The installer closes them instead of asking the employee to."""
    run("loginctl", "terminate-user", account, check=False, quiet=True,
        stderr=subprocess.DEVNULL)
    run("pkill", "-u", account, check=False, quiet=True, stderr=subprocess.DEVNULL)


def install_managed(account: str, placed: dict[str, dict], enrollment: Path) -> dict:
    step(f"관리형 연결 설치: {account}")
    close_sessions(account)
    clients = [part for name, item in placed.items() for part in ("--client", f"{name}={item['path']}")]
    done = subprocess.run([sys.executable, str(HERE / "managed-linux.py"), "install", "--user", account,
                           "--enrollment", str(enrollment), *clients], capture_output=True, text=True)
    if done.returncode:
        raise Failed((done.stderr or done.stdout).strip().splitlines()[-1][:300] if (done.stderr or done.stdout)
                     else "관리형 연결 설치가 실패했습니다")
    return json.loads(done.stdout.splitlines()[-1])


def harness_login(account: str) -> bool:
    """The model sign-in, in the managed account, while the installer still has the console.

    Interactive by design: the harness prints a one-time URL and code for the employee. Skipped
    when a credential is already there, and never fatal — `codex login` can be run again later.
    """
    home = Path(pwd.getpwnam(account).pw_dir)
    if (home / ".codex/auth.json").is_file():
        return True
    shell = Path("/usr/local/lib/mcpgw-enforcement") / ("mcpgw-" + account) / "login-shell"
    step("하네스 모델 로그인 (화면의 안내를 따르세요)")
    return subprocess.run(["runuser", "-u", account, "--", str(shell), "-c",
                           "codex login --device-auth"], check=False).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help="설치 대상 직원 계정(기본: 설치를 실행한 계정)")
    parser.add_argument("--enrollment", type=Path, default=HERE / "enrollment.json")
    parser.add_argument("--remove", action="store_true", help="이 PC의 연결만 제거")
    parser.add_argument("--skip-login", action="store_true", help="하네스 모델 로그인을 건너뜀")
    args = parser.parse_args()
    if os.name != "posix":
        print("이 설치기는 Linux용입니다. Windows에서는 install.cmd를 실행하세요.", file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("관리자 권한이 필요합니다. install.sh로 실행하세요.", file=sys.stderr)
        return 2
    try:
        employee = employee_account(args.user)
        account, companion = managed_account(employee)
        if args.remove:
            rollback(account)
            print(json.dumps({"removed": account}, ensure_ascii=False))
            return 0
        if not args.enrollment.is_file():
            raise Failed(f"설치 키트의 enrollment.json이 없습니다: {args.enrollment}")
        ensure_packages()
        step("승인 하네스 배치")
        placed = place_harnesses(employee)
        if installed(account):
            rollback(account)
        try:
            result = install_managed(account, placed, args.enrollment)
            if companion:
                step("직원 계정에서 바로 실행되게 연결")
                result["launchers"] = write_shims(employee, account)
        except Failed:
            # Half a connection is worse than none: the account keeps its own shell and firewall.
            if installed(account) or (SHIM_DIR / "codex").is_file():
                rollback(account)
            raise
        if not args.skip_login:
            result["model_signed_in"] = harness_login(account)
        result.update(employee=employee, managed_account=account,
                      harnesses={name: item.get("digests", {}) for name, item in placed.items()})
        print(json.dumps(result, ensure_ascii=False))
        print("\n연결을 신청했습니다. 조직 관리자가 콘솔에서 활성화하면 사용할 수 있습니다.")
        print(f"평소 계정({employee})에서 codex 또는 claude를 실행하세요." if companion
              else "이 계정에서 codex 또는 claude를 실행하세요.")
        return 0
    except Failed as exc:
        print(f"\n설치하지 못했습니다: {exc}", file=sys.stderr)
        return 1
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        print(f"\n설치하지 못했습니다: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
