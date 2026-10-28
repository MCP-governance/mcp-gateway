#!/usr/bin/env python3
"""macOS account/pf/launchd adapter for the existing managed policy and broker loop."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import ipaddress
import json
import os
import plistlib
import pwd
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Intel Homebrew may own /usr/local; privileged service code needs a root-owned parent chain.
PROGRAMS = Path('/Library/MCPGatewayManaged')
STATE = Path('/var/db/mcpgw-managed')
LAUNCHD = Path('/Library/LaunchDaemons')
FILES = {'managed-mcp.json': Path('/Library/Application Support/ClaudeCode/managed-mcp.json'),
         'managed-settings.json': Path('/Library/Application Support/ClaudeCode/managed-settings.json'),
         'requirements.toml': Path('/etc/codex/requirements.toml'),
         'managed_config.toml': Path('/etc/codex/managed_config.toml')}
SOURCES = ('managed-macos.py', 'managed-linux.py', 'bootstrap.py', 'agent.py', 'offline_buffer.py', 'kit_screen.py')
ROLLBACK_ORDER = ('launchd', 'shims', 'wrappers', 'pf', 'settings', 'programs', 'account')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(*command, check=True):
    # Never include tool output: commands may handle enrollment or device credentials.
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        error = subprocess.CalledProcessError(result.returncode, Path(command[0]).name, stderr=result.stderr)
        core_module().diagnostic('command', error)
        if check:
            raise error
    return result


def account_name(employee):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,30}', employee or ''):
        raise ValueError('직원 계정 이름을 확인하세요')
    if pwd.getpwnam(employee).pw_uid < 501:
        raise ValueError('일반 직원 계정이 필요합니다')
    return ('managed-' + employee)[:31]


def pf_rules(uid, addresses, gateway_port, proxy_port=None):
    if type(uid) is not int or not 501 <= uid < 2**32 - 1:
        raise ValueError('일반 관리 계정 UID가 필요합니다')
    ports = [gateway_port] + ([proxy_port] if proxy_port is not None else [])
    if any(type(port) is not int or not 1 <= port <= 65535 for port in ports) or not addresses:
        raise ValueError('게이트웨이 주소와 포트가 필요합니다')
    rules = []
    for address in addresses:
        ip = ipaddress.ip_address(address)
        family = 'inet6' if ip.version == 6 else 'inet'
        rules.append(f'pass out quick {family} proto tcp from any to {ip} '
                     f'port {{ {", ".join(map(str, sorted(set(ports))))} }} user {uid} keep state')
    # PF user matching covers TCP/UDP sockets; it is not Linux AppArmor or raw-socket confinement.
    rules.append(f'block return out quick proto {{ tcp udp }} all user {uid}')
    return '\n'.join(rules) + '\n'


def daemon_plist(account, config, python):
    return plistlib.dumps({'Label': 'org.mcpgw.managed.' + account,
                          'ProgramArguments': [python, '-I', '-B', str(PROGRAMS / 'managed-linux.py'),
                                               'serve', '--config', str(config)],
                          'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
                          'WorkingDirectory': '/', 'Umask': 0o077,
                          'StandardOutPath': '/dev/null', 'StandardErrorPath': '/dev/null'})


def configure_bootstrap(account):
    boot = load('mac_bootstrap', HERE / 'bootstrap.py')
    boot.STATE, boot.PROGRAMS = STATE, PROGRAMS
    boot.APPROVED = PROGRAMS / account / 'approved'
    boot.FUNCTIONS = Path('/etc/mcpgw-managed.sh')
    boot.RC_FILES = (Path('/etc/zshrc'), Path('/etc/bashrc'))
    return boot


def configure_runtime(core):
    core.FILES = FILES
    core.STATE, core.PROGRAMS = STATE, PROGRAMS
    core.checks = checks
    core.host_report = host_report


def host_report(config):
    boot = configure_bootstrap(config['username'])
    accounts = []
    for person in pwd.getpwall():
        if person.pw_uid < 501 or person.pw_uid == config['uid'] or person.pw_shell.endswith(('false', 'nologin')):
            continue
        accounts.append({'name': person.pw_name[:64], 'uid': person.pw_uid,
                         'privileged_groups': sorted(boot.groups_of(person.pw_name) & {'admin', 'wheel'})})
    return {'kernel': os.uname().release, 'wsl': False, 'other_accounts': accounts[:64]}


def authorize_peer(connection, config):
    # Darwin's LOCAL_PEERCRED is exposed by libc getpeereid, not Linux SO_PEERCRED.
    uid, gid = ctypes.c_uint(), ctypes.c_uint()
    libc = ctypes.CDLL(None, use_errno=True)
    getpeereid = libc.getpeereid
    getpeereid.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
    getpeereid.restype = ctypes.c_int
    return getpeereid(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) == 0 and uid.value == config['uid']


def core_module():
    core = load('mac_managed_core', HERE / 'managed-linux.py')
    configure_runtime(core)
    return core


def save(core, path, value):
    core.private_write(path, json.dumps(value, ensure_ascii=False))


def anchor_name(account):
    if not re.fullmatch(r'managed-[A-Za-z0-9_-]+', account):
        raise ValueError('관리 계정 이름을 확인하세요')
    return 'com.apple/mcpgw-' + account


def apply_pf(config, core):
    parent = run('/sbin/pfctl', '-sr').stdout
    if not re.search(r'anchor\s+"com\.apple/\*"', parent):
        raise ValueError('시스템 방화벽 anchor 연결을 확인할 수 없습니다')
    rule_file = Path(config['pf_file'])
    expected = pf_rules(config['uid'], config['gateway_ips'], config['gateway_port'], config.get('proxy_port'))
    core.private_write(rule_file, expected)
    run('/sbin/pfctl', '-n', '-a', config['pf_anchor'], '-f', str(rule_file))
    run('/sbin/pfctl', '-a', config['pf_anchor'], '-f', str(rule_file))
    # Release exactly our reference on removal. After reboot the old reference no longer exists.
    boot = run('/usr/sbin/sysctl', '-n', 'kern.boottime').stdout.strip()
    if config.get('pf_boot') != boot:
        enabled = run('/sbin/pfctl', '-E')
        token = re.search(r'Token\s*:\s*(\d+)', enabled.stdout + enabled.stderr)
        if not token:
            raise ValueError('방화벽 활성화 참조를 확인할 수 없습니다')
        config.update(pf_token=token[1], pf_boot=boot)
        save(core, Path(config['config_path']), config)
    baseline = run('/sbin/pfctl', '-a', config['pf_anchor'], '-sr').stdout
    if not baseline.strip():
        raise ValueError('방화벽 규칙이 비어 있습니다')
    config['pf_baseline'] = baseline
    save(core, Path(config['config_path']), config)


def start_runtime(config, core):
    apply_pf(config, core)


def checks(config, policy, *, findings=None):
    core = core_module()
    account = pwd.getpwnam(config['username'])
    boot = configure_bootstrap(config['username'])
    commands_ok, commands = core.load_module('mac_commands', HERE / 'agent.py').user_command_settings(account.pw_dir)
    if findings is not None:
        findings.extend(commands)
    actual = run('/sbin/pfctl', '-a', config['pf_anchor'], '-sr', check=False)
    status = run('/sbin/pfctl', '-s', 'info', check=False)
    hashes = {name: hashlib.sha256(target.read_bytes()).hexdigest() for name, target in FILES.items()}
    return hashes, {'pf_enforcing': actual.returncode == 0 and status.returncode == 0
                    and 'Status: Enabled' in status.stdout and actual.stdout == config['pf_baseline'],
                    'protected_configs': all(core.protected(p) and not p.is_symlink()
                                             and p.stat().st_mode & 0o777 == 0o644 for p in FILES.values()),
                    'ordinary_account': account.pw_uid == config['uid'] and not boot.groups_of(account.pw_name) & {'admin', 'wheel'},
                    'user_command_helpers': commands_ok}


def write_wrappers(core, folder, config, boot):
    boot.SHIM_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    wrappers = folder / 'wrappers'
    wrappers.mkdir(mode=0o755)
    shell = wrappers / 'login-shell'
    core.private_write(shell, '#!/bin/bash\nexec /bin/bash "$@"\n')
    shell.chmod(0o755)
    public_env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': pwd.getpwnam(config['username']).pw_dir,
                  'USER': config['username'], 'LOGNAME': config['username'],
                  **config.get('proxy_environment', {})}
    if config.get('ca_certificate'):
        ca = str(folder / 'root.crt')
        public_env.update(SSL_CERT_FILE=ca, NODE_EXTRA_CA_CERTS=ca, REQUESTS_CA_BUNDLE=ca)
    for name in ('codex', 'claude'):
        command = ['/usr/bin/env', '-i', *[f'{key}={value}' for key, value in public_env.items()],
                   str(boot.APPROVED / name)]
        core.private_write(wrappers / name, '#!/bin/bash\nexec ' + shlex.join(command) + ' "$@"\n')
        (wrappers / name).chmod(0o755)
    helper_dir = PROGRAMS / 'enforcement' / ('mcpgw-' + config['username'])
    helper_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    helper = [sys.executable, '-I', '-B', str(PROGRAMS / 'managed-linux.py'), 'header', '--socket', config['socket']]
    core.private_write(helper_dir / 'header-helper', '#!/bin/bash\nexec ' + shlex.join(helper) + '\n')
    (helper_dir / 'header-helper').chmod(0o755)
    # Reuse the Linux replacement journal and argument quoting; only the shell location differs.
    boot.SUDOERS.write_text(f"{config['employee']} ALL=({config['username']}) NOPASSWD: {shell}\n", encoding='utf-8')
    boot.SUDOERS.chmod(0o440)
    run('/usr/sbin/visudo', '-cqf', str(boot.SUDOERS))
    for name in ('codex', 'claude'):
        boot.replace_launcher(name, config['username'], shell)
    boot.write_functions(config['employee'])


def rollback(account):
    core = core_module()
    folder = STATE / account
    journal_path = folder / 'installer.json'
    if not folder.exists() and not (LAUNCHD / ('org.mcpgw.managed.' + account + '.plist')).exists():
        return
    if journal_path.is_file():
        journal = json.loads(journal_path.read_text(encoding='utf-8'))
    else:
        # Missing ownership journal never authorizes deleting an existing account or employee files.
        journal = {'created': False, 'settings': {name: 0o644 for name in FILES
                   if (folder / (name + '.backup')).exists()}}
    config_path = folder / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    boot = configure_bootstrap(account)
    for stage in ROLLBACK_ORDER:
        if stage == 'launchd':
            label = 'org.mcpgw.managed.' + account
            run('/bin/launchctl', 'bootout', 'system/' + label, check=False)
            (LAUNCHD / (label + '.plist')).unlink(missing_ok=True)
            run('/usr/bin/pkill', '-u', account, check=False)
        elif stage == 'shims':
            boot.remove_shims(account)
        elif stage == 'wrappers':
            helper = PROGRAMS / 'enforcement' / ('mcpgw-' + account)
            shutil.rmtree(helper, ignore_errors=True)
        elif stage == 'pf':
            run('/sbin/pfctl', '-a', config.get('pf_anchor') or anchor_name(account), '-F', 'rules')
            if config.get('pf_token') and config.get('pf_boot') == run('/usr/sbin/sysctl', '-n', 'kern.boottime').stdout.strip():
                run('/sbin/pfctl', '-X', config['pf_token'])
        elif stage == 'settings':
            for name in journal.get('settings', []):
                target, backup = FILES[name], folder / (name + '.backup')
                if backup.exists():
                    core.private_write(target, backup.read_text(encoding='utf-8'))
                    target.chmod(journal['settings'][name])
                else:
                    target.unlink(missing_ok=True)
        elif stage == 'programs':
            Path(config.get('socket', '/var/run/mcpgw-' + account + '.sock')).unlink(missing_ok=True)
            shutil.rmtree(PROGRAMS / account, ignore_errors=True)
            for name in SOURCES:
                (PROGRAMS / name).unlink(missing_ok=True)
        elif stage == 'account' and journal.get('created'):
            run('/usr/bin/dscl', '.', '-delete', '/Users/' + account)
            if journal.get('home_created'):
                home = Path('/Users') / account
                if home.resolve().parent != Path('/Users').resolve():
                    raise ValueError('관리 계정 홈 경로를 확인하세요')
                shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(folder, ignore_errors=True)


def install(employee, enrollment):
    account = account_name(employee)
    core = core_module()
    bundle = json.loads(enrollment.read_text(encoding='utf-8'))
    core.verify_transport(bundle)
    if any(path.parent.name != account for path in STATE.glob('*/installer.json')):
        raise ValueError('이 PC에는 다른 직원의 관리형 연결이 있습니다')
    folder = STATE / account
    journal_path = folder / 'installer.json'
    prior = json.loads(journal_path.read_text(encoding='utf-8')) if journal_path.exists() else {}
    try:
        existing = pwd.getpwnam(account)
    except KeyError:
        existing = None
    else:
        if not prior.get('created') or prior.get('employee') != employee:
            raise ValueError('동일 이름의 기존 계정을 먼저 확인하세요')
    home = Path('/Users') / account
    if (home.exists() or home.is_symlink()) and not (existing and prior.get('home_created')):
        raise ValueError('동일 이름의 기존 홈 경로를 먼저 확인하세요')
    uid = existing.pw_uid if existing else max(500, *[p.pw_uid for p in pwd.getpwall() if 500 <= p.pw_uid < 60000]) + 1
    credentials = [bundle.get('enrollment_token'), bundle.get('device_key')]
    try:
        config, policy, enrolled = core.enroll(bundle, account, uid, platform='macos')
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        core.diagnostic('enroll', exc, credentials)
        raise ValueError('연결 등록·정책 수신에 실패했습니다. 기존 설치는 유지됩니다.') from None
    credentials.append(config['device_key'])
    core.diagnostic('prepared', None)
    rollback(account)
    boot = configure_bootstrap(account)
    folder.mkdir(mode=0o700, parents=True)
    if not core.protected(folder):
        raise ValueError('설치 상태 경로가 보호되지 않았습니다')
    journal = {'created': False, 'employee': employee, 'settings': {}}
    save(core, folder / 'installer.json', journal)
    try:
        record = '/Users/' + account
        run('/usr/bin/dscl', '.', '-create', record)
        journal['created'] = True
        save(core, folder / 'installer.json', journal)
        for key, value in {'UniqueID': str(uid), 'PrimaryGroupID': '20', 'NFSHomeDirectory': '/Users/' + account,
                           'UserShell': '/bin/bash', 'RealName': 'MCP Managed', 'IsHidden': '1', 'Password': '*'}.items():
            run('/usr/bin/dscl', '.', '-create', record, key, value)
        home.mkdir(mode=0o700)
        journal['home_created'] = True
        save(core, folder / 'installer.json', journal)
        os.chown(home, uid, 20)
        PROGRAMS.mkdir(mode=0o755, parents=True, exist_ok=True)
        if not core.protected(PROGRAMS):
            raise ValueError('프로그램 경로가 보호되지 않았습니다')
        for name in SOURCES:
            core.private_write(PROGRAMS / name, (HERE / name).read_text(encoding='utf-8'))
            (PROGRAMS / name).chmod(0o755)
        boot.place_harnesses(employee)
        config.update(endpoint_id=enrolled['endpoint_id'], username=account, uid=uid, employee=employee,
                      socket='/var/run/mcpgw-' + account + '.sock', config_path=str(folder / 'config.json'),
                      pf_anchor=anchor_name(account), pf_file=str(folder / 'egress.pf'))
        save(core, folder / 'config.json', config)
        config.update({key: policy[key] for key in ('gateway_ips', 'gateway_port', 'policy_hash')})
        config.update(proxy_port=policy.get('proxy_port'), proxy_environment=policy.get('proxy_environment', {}))
        save(core, folder / 'config.json', config)
        for name, target in FILES.items():
            if target.is_symlink():
                raise ValueError('관리형 설정 경로가 링크입니다')
            if target.exists():
                core.private_write(folder / (name + '.backup'), target.read_text(encoding='utf-8'))
            journal['settings'][name] = target.stat().st_mode & 0o777 if target.exists() else 0o644
            save(core, folder / 'installer.json', journal)
        core.apply_policy(policy)
        apply_pf(config, core)
        if config.get('ca_certificate'):
            core.private_write(PROGRAMS / account / 'root.crt', config['ca_certificate'])
            (PROGRAMS / account / 'root.crt').chmod(0o644)
        write_wrappers(core, PROGRAMS / account, config, boot)
        plist = LAUNCHD / ('org.mcpgw.managed.' + account + '.plist')
        plist.write_bytes(daemon_plist(account, folder / 'config.json', sys.executable))
        plist.chmod(0o644)
        started = core.time.time()
        run('/bin/launchctl', 'bootstrap', 'system', str(plist))
        enrollment.unlink()
        core.diagnostic('installed', None)
        summary = core.kit_screen.wait_summary(core.status_path(account, 'json'), since=started)
        return {'endpoint_id': config['endpoint_id'], 'managed_account': account, 'state': summary.get('state', 'unknown')}
    except BaseException as exc:
        core.diagnostic('install', exc, credentials)
        rollback(account)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', default=os.environ.get('SUDO_USER'))
    parser.add_argument('--enrollment', type=Path, default=HERE / 'enrollment.json')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.geteuid() != 0:
        parser.exit(2, 'macOS 관리자 권한이 필요합니다. install.sh로 실행하세요.\n')
    try:
        if args.remove:
            rollback(account_name(args.user))
        else:
            if not args.enrollment.is_file():
                account = account_name(args.user)
                if (STATE / account / 'config.json').is_file():
                    print('이미 설치됨 · 상태 확인: cat ' + shlex.quote(str(PROGRAMS / ('status-' + account + '.txt')))
                          + ' · 새로 설치하려면 콘솔에서 새 키트를 받으세요.')
                    return
                parser.exit(1, '등록 파일 없음 · 콘솔에서 새 키트를 받으세요.\n')
            result = install(args.user, args.enrollment)
            print(json.dumps(result))
            core = core_module()
            print('연결 상태: ' + core.kit_screen.STATES.get(result['state'], '확인 필요'))
            print('실행: 새 터미널에서 codex 또는 claude' if result['state'] == 'active'
                  else '상태 확인: 콘솔의 엔드포인트')
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, '설치/제거 실패: ' + type(exc).__name__ + '\n')


if __name__ == '__main__':
    main()
