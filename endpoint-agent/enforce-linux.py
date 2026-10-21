"""Root-installed enforcement for an ordinary Linux SSH account.

AppArmor restricts executable paths; nftables restricts every IP protocol, including
loopback, for the UID. This is an administrator-managed testboard profile, not EDR
for privileged users or a claim of control over every possible AI program.
"""
from __future__ import annotations

import argparse
import grp
import ipaddress
import json
import mmap
import os
import pwd
import re
import subprocess
import tempfile
from pathlib import Path

BASE = Path("/usr/local/lib/mcpgw-enforcement")


def run(*args, **kwargs):
    kwargs.setdefault("check", True)
    return subprocess.run(args, text=True, **kwargs)


def trusted_binary(raw: str) -> Path:
    path = Path(raw).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("승인 실행 파일이 아닙니다")
    for node in (path, *path.parents):
        if node.stat().st_uid != 0 or node.stat().st_mode & 0o022:
            raise ValueError("실행 파일과 상위 경로는 root 소유이고 사용자 쓰기가 금지돼야 합니다")
    if not re.fullmatch(r"/[A-Za-z0-9_./+-]+", str(path)):
        raise ValueError("정책에 넣을 수 없는 실행 경로입니다")
    return path


def companions(key: str, binary: Path) -> list[Path]:
    """Programs a harness starts from its own release folder. Codex runs every tool call through
    codex-code-mode-host next to its executable; without that file (and the profile allowing it)
    no MCP tool can be called from the managed account."""
    if key != "codex":
        return []
    host = binary.with_name("codex-code-mode-host")
    if host.exists():
        return [trusted_binary(str(host))]
    with open(binary, "rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as image:
        if image.find(b"codex-code-mode-host") != -1:
            raise ValueError("Codex와 같은 릴리스의 codex-code-mode-host를 같은 폴더에 설치하세요: " + str(host))
    return []


def fixed_options(key: str, binary: Path) -> list[str]:
    """Options the managed account's launcher always adds. Codex's interactive CLI starts a shared
    background server from its installed package layout and talks to it over a Unix socket; the
    approved copy is one executable and the profile allows no Unix IPC, so it runs its own server
    (--no-daemon, a root option every subcommand accepts). Builds that predate the flag don't know it."""
    if key != "codex":
        return []
    with open(binary, "rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as image:
        return ["--no-daemon"] if image.find(b"--no-daemon") != -1 else []


def nft_rules(uid: int, addresses: list[str], port: int, proxy_port: int | None = None,
              owner_uid: int | None = None) -> str:
    rules = []
    if owner_uid is not None:
        if type(owner_uid) is not int or not 1000 <= owner_uid < 2**32 - 1 or owner_uid == uid:
            raise ValueError("소유자는 관리 계정과 다른 일반 사용자 UID여야 합니다")
        # Preserve Tailscale's 0xff0000 connmark field; only the owner's original flow earns this bit.
        rules += [f'oifname "lo" ct direction original ct state new meta skuid {owner_uid} '
                  'ct mark set ct mark or 0x00000100',
                  f'meta skuid {uid} oifname "lo" ct direction reply '
                  'ct mark and 0x00000100 == 0x00000100 accept']
    ports = f"{{ {port}, {proxy_port} }}" if proxy_port else str(port)
    for address in addresses:
        ip = ipaddress.ip_address(address)
        family = "ip6" if ip.version == 6 else "ip"
        rules.append(f"meta skuid {uid} {family} daddr {ip} tcp dport {ports} accept")
    return (f"destroy table inet mcpgw_uid_{uid}\ntable inet mcpgw_uid_{uid} {{\n chain output {{\n"
            "type filter hook output priority -10; policy accept;\n" + "\n".join(rules) +
            f'\nmeta skuid {uid} limit rate 10/second burst 20 packets log prefix "MCPGW_DENY uid={uid} "\n'
            f"meta skuid {uid} counter reject with icmpx type admin-prohibited\n }}\n}}\n")


TOOLS = "cat,ls,head,tail,grep,sed,cut,sort,uniq,wc,printf,env,find,stat,id,whoami,uname,date,timeout,sleep,true,false,tr,locale,locale-check,getconf"


def profile(name: str, shell: Path, home: str, binaries: dict[str, Path], helper: bool, managed: bool = False,
            extras: dict[str, list[Path]] | None = None, binding_mode: str = "warn") -> str:
    if binding_mode not in {"warn", "enforce"}:
        raise ValueError("지원하지 않는 헤더 브로커 결속 모드")
    if binding_mode == "enforce" and not managed:
        raise ValueError("프로세스 결속은 관리형 Linux 브로커에서만 지원합니다")
    if managed and binding_mode == "enforce":
        return bound_profile(name, shell, home, binaries, extras or {})
    def common(shells: str) -> str:
        return f"""
  #include <abstractions/base>
  /etc/** r,
  /usr/** mr,
  /lib{{,32,64}}/** mr,
  /dev/tty rw,
  /dev/pts/** rw,
  /proc/** r,
  /run/systemd/resolve/{{stub-resolv.conf,resolv.conf}} r,
  /sys/kernel/mm/transparent_hugepage/enabled r,
  /sys/fs/cgroup/**/cpu.max r,
  /sys/fs/cgroup/**/memory.{{max,high}} r,
  owner {home}/** rwk,
  owner {home}/ r,
  /tmp/** rwk,
  /var/tmp/** rwk,
  network inet stream,
  network inet6 stream,
  signal (receive, send) peer={name}*,
  /usr/{{bin,sbin}}/{{{shells}{TOOLS}}} ix,
  # No general interpreter, package manager, git, downloaded executable or Unix IPC.
"""
    clients = "".join(f"  {BASE}/{name}/{key} px -> {name}-{key}-entry,\n" for key in binaries)
    credential = f"  {BASE}/{name}/header-helper px -> {name}-credential,\n" if helper else ""
    text = f"#include <tunables/global>\nprofile {name} {shell} {{\n{common('bash,dash,sh,')}\n{clients}}}\n"
    # A companion runs under the harness's own profile (ix): same network and execution limits.
    allowed = {key: "".join(f"  {extra} mrix,\n" for extra in (extras or {}).get(key, [])) for key in binaries}
    for key, binary in binaries.items():
        # Both harnesses start the header helper with `sh -c` (dash); the model's shell tool
        # runs bash. bash therefore moves to a -tool profile that has everything the harness
        # has except the helper and its socket, so a command the model writes cannot fetch
        # the device token (DEV-31). Anything bash starts, sh included, stays in -tool.
        text += f"""profile {name}-{key}-entry {{
  #include <abstractions/base>
  /usr/** mr,
  /etc/** r,
  /lib{{,32,64}}/** mr,
  {binary} px -> {name}-{key},
}}
profile {name}-{key} {{
{common('dash,sh,')}
  /usr/bin/bash px -> {name}-{key}-tool,
  {binary} mr,
{allowed[key]}{credential}
  {f'unix (send, receive) type=stream peer=(label={name}-credential),' if managed else ''}
}}
profile {name}-{key}-tool {{
{common('bash,dash,sh,')}
{allowed[key]}}}
"""
    if helper:
        python = Path("/usr/bin/python3").resolve()
        text += f"""profile {name}-credential {{
  #include <abstractions/base>
  /etc/** r,
  /usr/** mr,
  /lib{{,32,64}}/** mr,
  /proc/** r,
  owner {home}/.mcpgw/ rw,
  owner {home}/.mcpgw/** rwk,
  network inet stream,
  network inet6 stream,
  {python} ix,
  {f'network unix stream, /run/{name}.sock rw,' if managed else ''}
}}
"""
    return text


def bound_profile(name: str, shell: Path, home: str, binaries: dict[str, Path],
                  extras: dict[str, list[Path]]) -> str:
    """Strict stage: only a harness can delegate to the fixed native header helper.

    Shell-based header commands cannot work in this stage. Do not restore dash ix
    to repair compatibility: it would give arbitrary shell children the credential.
    """
    def common() -> str:
        return f"""
  #include <abstractions/base>
  /etc/** r,
  /usr/** mr,
  /lib{{,32,64}}/** mr,
  /dev/tty rw,
  /dev/pts/** rw,
  /proc/** r,
  deny /proc/*/{{mem,environ}} r,
  deny /proc/*/task/*/{{mem,environ}} r,
  deny ptrace (trace, read, tracedby, readby),
  deny capability sys_ptrace,
  /run/systemd/resolve/{{stub-resolv.conf,resolv.conf}} r,
  /sys/kernel/mm/transparent_hugepage/enabled r,
  /sys/fs/cgroup/**/cpu.max r,
  /sys/fs/cgroup/**/memory.{{max,high}} r,
  owner {home}/** rwk,
  owner {home}/ r,
  /tmp/** rwk,
  /var/tmp/** rwk,
  network inet stream,
  network inet6 stream,
  signal (receive, send) peer={name}*,
"""

    def no_broker() -> str:
        return f"""
  deny {BASE}/{name}/header-helper x,
  deny /run/{name}.sock rw,
  deny unix (connect, send, receive) type=stream peer=(addr="/run/{name}.sock"),
"""

    socket_rules = f"""
  /run/{name}.sock rw,
  unix (create, getattr, getopt, setopt, shutdown) type=stream,
  unix (connect, send, receive) type=stream peer=(addr="/run/{name}.sock", label=unconfined),
"""
    clients = "".join(f"  {BASE}/{name}/{key} px -> {name}-{key}-entry,\n" for key in binaries)
    text = (f"#include <tunables/global>\nprofile {name} {shell} {{\n{common()}"
            f"  /usr/{{bin,sbin}}/{{bash,dash,sh,{TOOLS}}} ix,\n{no_broker()}{clients}}}\n")
    for key, binary in binaries.items():
        harness, tool = f"{name}-bound-{key}", f"{name}-bound-{key}-tool"
        children = "".join(f"  {extra} mrpx -> {tool},\n" for extra in extras.get(key, []))
        tools = "".join(f"  {extra} mrix,\n" for extra in extras.get(key, []))
        text += f"""profile {name}-{key}-entry {{
{common()}{no_broker()}
  {binary} px -> {harness},
}}
profile {harness} {{
{common()}{socket_rules}
  {binary} mr,
  /usr/{{bin,sbin}}/{{bash,dash,sh,{TOOLS}}} px -> {tool},
{children}
  {BASE}/{name}/header-helper px -> {name}-bound-credential,
}}
profile {tool} {{
{common()}{no_broker()}
  /usr/{{bin,sbin}}/{{bash,dash,sh,{TOOLS}}} ix,
{tools}}}
"""
    text += f"""profile {name}-bound-credential {{
  #include <abstractions/base>
  /etc/** r,
  /usr/** mr,
  /lib{{,32,64}}/** mr,
  /proc/** r,
  deny ptrace (trace, read, tracedby, readby),
  deny capability sys_ptrace,
  deny /proc/*/{{mem,environ}} r,
  deny /proc/*/task/*/{{mem,environ}} r,
  /usr/bin/python3{{,.[0-9]*}} ix,
{socket_rules}}}
"""
    return text


def wrapper(path: Path, executable: Path, home: str, username: str, login: bool = False,
            fixed: list[str] | None = None, environment: dict[str, str] | None = None,
            options: list[str] | None = None, guard: str | None = None) -> None:
    # Native wrapper avoids a shebang/interpreter attachment ambiguity and removes
    # runtime variables such as BUN_BE_BUN, LD_PRELOAD and alternate config roots.
    # `options` go in front of the caller's own arguments.
    leading = options or []
    arguments = ("char *args[] = {" + ",".join(json.dumps(x) for x in [str(executable), *fixed]) + ",NULL};"
                 if fixed is not None else
                 f"char **args = calloc(argc + {len(leading) + 1}, sizeof(char *)); if (!args) return 125;"
                 + "".join(f"args[{i + 1}] = {json.dumps(item)};" for i, item in enumerate(leading)))
    forward = "" if fixed is not None else f"for (int i=1; i<argc; i++) args[i+{len(leading)}]=argv[i];"
    # Tools read either case of the proxy variables; set both.
    extra = "".join(f"setenv({json.dumps(name)}, {json.dumps(value)}, 1); "
                    for key, value in (environment or {}).items() for name in (key, key.lower()))
    if guard == "codex":
        guard_code = r'''
  /* openai/codex rust-v0.160.0, codex-rs/ (Apache-2.0):
     utils/cli/src/shared_options.rs:9-68: i/image, m/model, p/profile,
       s/sandbox, C/cd, local-provider, add-dir all take values.
     tui/src/cli.rs:62-64: a/ask-for-approval takes a value.
     exec/src/cli.rs:24-26,42-51,61-68,259-276: thread-source,
       output-schema, color, o/output-last-message, base, commit, title.
     cli/src/main.rs:867-887: enable, disable, remote, remote-auth-token-env.
     Do not add flags to this table: consuming their next token can hide -c.
     Unknown options consume no value; extra variadic values are scanned. */
  static const char *value_options[] = {
    "--image", "--model", "--profile", "--sandbox", "--cd",
    "--local-provider", "--add-dir", "--ask-for-approval",
    "--thread-source", "--output-schema", "--color", "--output-last-message",
    "--base", "--commit", "--title", "--enable", "--disable", "--remote",
    "--remote-auth-token-env", NULL
  };
  for (int i = 1; i < argc; i++) {
    const char *arg = argv[i];
    if (!strcmp(arg, "--")) break;
    if (!strcmp(arg, "--config") || !strncmp(arg, "--config=", 9)) return 1;
    if (arg[0] != '-' || !arg[1]) continue;
    if (arg[1] == '-') {
      for (int j = 0; value_options[j]; j++) {
        if (!strcmp(arg, value_options[j])) {
          /* clap takes no hyphen-led value by default: "--model -c" is -c. */
          if (i + 1 < argc && argv[i + 1][0] != '-') i++;
          break;
        }
      }
    } else {
      for (const char *option = arg + 1; *option; option++) {
        if (*option == 'c') return 1;
        if (strchr("impsCao", *option)) {
          if (!option[1] && i + 1 < argc && argv[i + 1][0] != '-') i++;
          break;
        }
      }
    }
  }
'''
        error = "Codex 설정 재정의 인자(-c/--config)는 관리 실행에서 사용할 수 없습니다."
    elif guard == "claude":
        # Commander v14.0.2: option.js:231-233 exact match; command.js:1655-1659 terminator.
        guard_code = r'''
  for (int i = 1; i < argc; i++) {
    const char *arg = argv[i];
    if (!strcmp(arg, "--")) break;
    if (!strcmp(arg, "--settings") || !strncmp(arg, "--settings=", 11)) return 1;
  }
'''
        error = "Claude 설정 지정 인자(--settings)는 관리 실행에서 사용할 수 없습니다."
    else:
        guard_code, error = "", ""
    guard_function = f"static int blocked(int argc, char **argv) {{ {guard_code} return 0; }}" if guard else ""
    guard_check = (f'if (blocked(argc, argv)) {{ '
                   f'fputs({json.dumps(error + chr(10))}, stderr); return 2; }}' if guard else "")
    source = f"""
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
{guard_function}
int main(int argc, char **argv) {{
  {arguments}
  {guard_check}
  if (clearenv()) return 125;
  setenv("PATH", "{path.parent}:/usr/bin:/bin", 1);
  setenv("HOME", "{home}", 1); setenv("USER", "{username}", 1);
  setenv("LANG", "C.UTF-8", 1); setenv("TERM", "xterm-256color", 1);
  {extra}
  args[0] = {json.dumps('-bash' if login else str(executable))};
  {forward}
  execv("{executable}", args); return 126;
}}
"""
    with tempfile.TemporaryDirectory(prefix="mcpgw-wrapper-") as folder:
        src = Path(folder) / "wrapper.c"
        src.write_text(source, encoding="utf-8", newline="\n")
        run("gcc", "-O2", "-Wall", "-Werror", str(src), "-o", str(path))
    path.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True)
    parser.add_argument("--owner-uid", type=int, help="연결을 시작할 수 있는 직원 계정 UID")
    parser.add_argument("--gateway-ip", action="append", default=[])
    parser.add_argument("--gateway-port", type=int, default=443)
    parser.add_argument("--proxy-port", type=int, help="게이트웨이 호스트의 승인 모델 프록시 포트")
    parser.add_argument("--proxy-env", default="{}", help="하네스에 넣을 프록시 환경 변수(JSON)")
    parser.add_argument("--ca", help="검증한 루트 인증서의 root 관리 경로")
    parser.add_argument("--client", action="append", default=[], help="codex=/root-owned/native/binary")
    parser.add_argument("--helper-source", help="root 소유 직원 PC 키트 mcpgw_pc.py")
    parser.add_argument("--managed-agent", help="root 관리형 엔드포인트 서비스의 header 명령")
    parser.add_argument("--broker-binding", choices=("warn", "enforce"), default="warn")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        text = nft_rules(1234, ["100.83.175.111", "fd7a:115c:a1e0::1"], 443)
        assert "tcp dport 443 accept" in text and "ip6 daddr" in text
        assert "udp" not in text and "sport 22" not in text
        assert "meta skuid 1234 counter reject" in text
        assert "tcp dport { 443, 3128 } accept" in nft_rules(1234, ["100.83.175.111"], 443, 3128)
        confined = profile("mcpgw-u", Path("/x/login-shell"), "/home/u", {"codex": Path("/opt/a/codex"), "claude": Path("/opt/a/claude")},
                           True, True, {"codex": [Path("/opt/a/codex-code-mode-host")], "claude": []})
        # only inside the codex harness profile and its tool profile
        assert confined.count("/opt/a/codex-code-mode-host mrix,") == 2
        blocks = dict(re.findall(r"profile (\S+)[^{]*\{(.*?)\n\}", confined, re.S))
        for key in ("codex", "claude"):
            harness, tool = blocks[f"mcpgw-u-{key}"], blocks[f"mcpgw-u-{key}-tool"]
            # The helper is started with `sh -c`: dash stays in the harness profile with the helper.
            assert "header-helper px -> mcpgw-u-credential" in harness and "{dash,sh," in harness
            assert "/usr/bin/bash px -> mcpgw-u-" + key + "-tool," in harness and "{bash," not in harness
            # What bash runs - sh, the helper path, the socket - never reaches the token.
            assert "header-helper" not in tool and "unix" not in tool and "credential" not in tool
            assert "{bash,dash,sh," in tool
        with tempfile.TemporaryDirectory(prefix="mcpgw-selfcheck-") as folder:
            fake = Path(folder) / "codex"
            fake.write_bytes(b"\x7fELF--no-daemon cannot be used with --remote.")
            old = Path(folder) / "old"
            old.write_bytes(b"\x7fELF no such flag")
            assert fixed_options("codex", fake) == ["--no-daemon"] and fixed_options("codex", old) == []
            assert fixed_options("claude", fake) == []
            # The launcher puts the option ahead of whatever the employee typed, one argument each.
            if subprocess.run(["which", "gcc"], capture_output=True).returncode == 0:
                built = Path(folder) / "launcher"
                wrapper(built, Path("/bin/echo"), folder, "u", environment={}, options=["--no-daemon"])
                done = subprocess.run([str(built), "exec", "say hi"], capture_output=True, text=True)
                assert done.stdout == "--no-daemon exec say hi\n", done
        print("enforcement rule self-check OK")
        return
    if args.broker_binding == "enforce" and not args.managed_agent:
        parser.error("프로세스 결속은 --managed-agent를 지정한 관리형 Linux에서만 지원합니다")
    if os.geteuid() != 0 or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", args.user):
        parser.error("root로 실행하고 실제 일반 계정 이름을 지정하세요")
    person = pwd.getpwnam(args.user)
    name = "mcpgw-" + args.user
    folder = BASE / name
    state = folder / "state.json"
    unit = "mcpgw-egress-" + args.user + ".service"
    policy = Path("/etc/apparmor.d") / name
    if args.rollback:
        prior = json.loads(state.read_text())
        if prior["uid"] != person.pw_uid:
            parser.error("계정 UID가 바뀌어 자동 원복할 수 없습니다")
        run("usermod", "--shell", prior["shell"], args.user)
        run("systemctl", "disable", "--now", unit)
        run("nft", "delete", "table", "inet", f"mcpgw_uid_{person.pw_uid}")
        run("apparmor_parser", "-R", str(policy))
        print("해당 계정의 로그인 셸·프로필·전용 방화벽 테이블을 원복했습니다")
        return
    groups = {grp.getgrgid(g).gr_name for g in os.getgrouplist(args.user, person.pw_gid)}
    if person.pw_uid < 1000 or groups & {"sudo", "wheel", "docker", "lxd", "libvirt", "root"}:
        parser.error("관리 권한이나 데몬 제어 권한이 있는 계정에는 일반 사용자 통제를 설치하지 않습니다")
    if not person.pw_dir.startswith("/home/") or not re.fullmatch(r"/[A-Za-z0-9_./-]+", person.pw_dir):
        parser.error("검토된 /home 일반 계정만 지원합니다")
    if not args.gateway_ip or not 1 <= args.gateway_port <= 65535:
        parser.error("명시적인 Gateway IP와 포트가 필요합니다")
    if args.proxy_port is not None and not 1 <= args.proxy_port <= 65535:
        parser.error("프록시 포트가 올바르지 않습니다")
    if args.owner_uid is not None:
        pwd.getpwuid(args.owner_uid)
    rendered_rules = nft_rules(person.pw_uid, args.gateway_ip, args.gateway_port, args.proxy_port, args.owner_uid)
    proxy_env = json.loads(args.proxy_env)
    if not isinstance(proxy_env, dict) or set(proxy_env) - {"HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"} or not all(
            isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9.:/,\[\]_-]{1,300}", v) for v in proxy_env.values()):
        parser.error("프록시 환경 변수가 올바르지 않습니다")
    ca = Path(args.ca).resolve(strict=True) if args.ca else None
    if ca and (not ca.is_file() or any(p.stat().st_uid != 0 or p.stat().st_mode & 0o022 for p in (ca, *ca.parents))):
        parser.error("CA 경로는 root 소유이고 사용자 쓰기가 금지돼야 합니다")
    if not Path("/sys/module/apparmor/parameters/enabled").read_text().strip().startswith("Y"):
        parser.error("이 시스템에서 AppArmor 집행을 사용할 수 없어 설치를 중단합니다")
    # The profiles tell the harness's `sh -c` (the header helper) from the model's bash by binary.
    # Where sh is bash, or /bin is not /usr/bin, that line cannot be drawn: refuse, do not weaken it.
    if (args.helper_source or args.managed_agent) and (
            Path("/bin").resolve() != Path("/usr/bin") or Path("/bin/sh").resolve().name != "dash"):
        parser.error("/bin/sh가 dash인 /usr 통합 시스템에서만 인증 헬퍼를 셸 명령과 분리할 수 있어 설치를 중단합니다")
    if run("pgrep", "-u", str(person.pw_uid), capture_output=True, check=False).returncode == 0:
        parser.error("해당 계정의 기존 프로세스를 먼저 종료하세요. 실행 중인 비관리 세션을 남기지 않습니다")
    binaries = {}
    for item in args.client:
        key, separator, raw = item.partition("=")
        if not separator or key not in {"codex", "claude"} or key in binaries:
            parser.error("고정 이름 codex·claude와 root 소유 실행 파일을 각각 지정하세요")
        binaries[key] = trusted_binary(raw)
    if not binaries:
        parser.error("검증한 native 하네스 실행 파일을 지정하세요")
    try:
        extras = {key: companions(key, binary) for key, binary in binaries.items()}
    except ValueError as exc:
        parser.error(str(exc))
    folder.mkdir(mode=0o755, parents=True, exist_ok=True)
    for node in (BASE, folder):
        if node.stat().st_uid != 0 or node.stat().st_mode & 0o022:
            parser.error("집행 프로그램 경로가 root 관리 경로가 아닙니다")
    if not state.exists():
        state.write_text(json.dumps({"uid": person.pw_uid, "shell": person.pw_shell}, indent=2))
        state.chmod(0o600)
    shell = folder / "login-shell"
    wrapper(shell, Path("/bin/bash"), person.pw_dir, args.user, login=True)
    for key, binary in binaries.items():
        environment = dict(proxy_env)
        if ca:
            environment["CODEX_CA_CERTIFICATE" if key == "codex" else "NODE_EXTRA_CA_CERTS"] = str(ca)
        wrapper(folder / key, binary, person.pw_dir, args.user, environment=environment,
                options=fixed_options(key, binary), guard=key if key in {"codex", "claude"} else None)
    if args.helper_source:
        source = trusted_binary(args.helper_source)
        helper = folder / "mcpgw_pc.py"
        helper.write_bytes(source.read_bytes())
        helper.chmod(0o644)
        wrapper(folder / "header-helper", Path("/usr/bin/python3").resolve(), person.pw_dir, args.user,
                fixed=["-I", "-S", str(helper), "--home", person.pw_dir + "/.mcpgw", "header"])
    if args.managed_agent:
        source = trusted_binary(args.managed_agent)
        wrapper(folder / "header-helper", Path("/usr/bin/python3").resolve(), person.pw_dir, args.user,
                fixed=["-I", "-S", str(source), "header", "--socket", f"/run/{name}.sock"])
    rules = folder / "egress.nft"
    rules.write_text(rendered_rules)
    run("nft", "-c", "-f", str(rules))
    policy.write_text(profile(name, shell, person.pw_dir, binaries, bool(args.helper_source or args.managed_agent),
                              bool(args.managed_agent), extras, args.broker_binding))
    # Syntax failure must occur before changing the kernel's loaded policy.
    run("apparmor_parser", "-Q", "-T", str(policy))
    run("apparmor_parser", "-r", str(policy))
    # An atomic batch replaces only this UID's table, never the host's ruleset.
    run("nft", "-f", str(rules))
    Path("/etc/systemd/system", unit).write_text(
        "[Unit]\nDescription=MCP Gateway ordinary-account egress\nBefore=ssh.service\nAfter=apparmor.service\n"
        "Requires=apparmor.service\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\n"
        f"ExecStart=/usr/sbin/nft -f {rules}\n\n[Install]\nWantedBy=multi-user.target\n")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", unit)
    run("systemctl", "start", unit)
    run("usermod", "--shell", str(shell), args.user)
    print(json.dumps({"user": args.user, "uid": person.pw_uid, "profile": name,
                      "gateway_ips": args.gateway_ip, "port": args.gateway_port, "proxy_port": args.proxy_port,
                      "ordinary_account_only": True,
                      # A managed install is removed as a whole (service, /etc files, device secret), not just this layer.
                      "rollback": (f"sudo python3 {args.managed_agent} rollback --user {args.user}" if args.managed_agent
                                   else f"sudo python3 {__file__} --user {args.user} --rollback")}))


if __name__ == "__main__":
    main()
