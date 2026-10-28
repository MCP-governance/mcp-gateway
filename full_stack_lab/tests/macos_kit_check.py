#!/usr/bin/env python3
"""Offline macOS kit checks. No account, firewall, launchd or network commands execute."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import ipaddress
import json
import plistlib
import shlex
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / 'endpoint-agent'
APP = ROOT / 'full_stack_lab/gateway/app'


def definitions(path, names, namespace=None):
    """Run only selected pure functions/constants, without importing platform-specific modules."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            selected.append(node)
    scope = namespace if namespace is not None else {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), scope)
    return scope


spec = importlib.util.spec_from_file_location('kit_commands', APP / 'kit_commands.py')
commands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(commands)


class MacOSKitCheck(unittest.TestCase):
    def test_pf_dual_stack_allowlist(self):
        render = definitions(AGENT / 'managed-macos.py', {'pf_rules'}, {'ipaddress': ipaddress})['pf_rules']
        rules = render(502, ['192.0.2.10', 'fd7a:115c:a1e0::1'], 443, 3128).splitlines()
        self.assertEqual(len(rules), 3)
        self.assertIn('inet proto tcp from any to 192.0.2.10 port { 443, 3128 } user 502', rules[0])
        self.assertIn('inet6 proto tcp from any to fd7a:115c:a1e0::1', rules[1])
        self.assertEqual(rules[-1], 'block return out quick proto { tcp udp } all user 502')
        self.assertNotIn('3128', render(502, ['127.0.0.1'], 443))
        for args in [(0, ['127.0.0.1'], 443), (502, [], 443), (502, ['bad\npass out all'], 443),
                     (502, ['::1'], 0), (502, ['::1'], 443, 65536), (True, ['::1'], 443)]:
            with self.assertRaises(ValueError):
                render(*args)

    def test_daemon_uses_private_config_without_secrets(self):
        render = definitions(AGENT / 'managed-macos.py', {'daemon_plist'},
                             {'plistlib': plistlib, 'PROGRAMS': PurePosixPath('/usr/local/lib/mcpgw-managed')})['daemon_plist']
        body = plistlib.loads(render('managed-staff', PurePosixPath('/var/db/mcpgw-managed/managed-staff/config.json'), '/trusted/python3'))
        self.assertTrue(body['KeepAlive'])
        self.assertEqual(body['ProgramArguments'][-2:], ['--config', '/var/db/mcpgw-managed/managed-staff/config.json'])
        self.assertNotIn('EnvironmentVariables', body)
        self.assertEqual(body['StandardOutPath'], '/dev/null')
        self.assertIn('-I', body['ProgramArguments'])

    def test_download_credentials_are_file_mediated(self):
        ticket = 'x' * 43
        script = commands.macos_bootstrap('https://192.0.2.10', ticket, 'certificate\n')
        self.assertNotIn(ticket, commands.MACOS_COMMAND)
        self.assertIn('set +x', script)
        self.assertLess(script.index('rm -f -- "$0"'), script.index('/usr/bin/curl'))
        self.assertIn('header = "Authorization: Bearer kit-download.' + ticket + '"', script)
        curl = next(line for line in script.splitlines() if line.startswith('/usr/bin/curl'))
        self.assertNotIn(ticket, curl)
        self.assertNotIn('--location', curl)
        self.assertIn('--cacert "$work/root.crt" --config "$work/request.conf"', curl)
        self.assertIn('umask 077', script)
        self.assertIn('rm -f -- "$work/request.conf"', script)
        self.assertIn('trap ', script)
        for public in ['http://localhost', 'https://host/path', 'https://u:p@host', 'https://host\nurl=x']:
            with self.assertRaises(ValueError):
                commands.macos_bootstrap(public, ticket, 'certificate')

    def test_platform_detection_and_check_sets(self):
        names = {'MANAGED_CHECKS', 'MANAGED_CHECKS_BY_PLATFORM', 'managed_platform', 'managed_checks', 'managed_mode', 'SIMPLE_CHECKS'}
        scope = definitions(APP / 'endpoint_plane.py', names)
        self.assertEqual(scope['managed_platform']({'platform': 'Darwin', 'detail': {'managed_platform': 'macos'}}), 'macos')
        self.assertEqual(scope['managed_platform']({'detail': {'local_sid': 'S-1-5-21-1'}}), 'windows')
        self.assertEqual(scope['managed_platform']({'platform': 'macos'}), 'linux')
        required = scope['managed_checks']({'detail': {'managed_platform': 'macos'}}, {'user_command_helpers': True})
        self.assertEqual(required, {'pf_enforcing', 'protected_configs', 'ordinary_account', 'user_command_helpers'})
        self.assertIn('apparmor_enforcing', scope['MANAGED_CHECKS_BY_PLATFORM']['linux'])

    def test_kit_sources_and_launch_path(self):
        scope = definitions(APP / 'agent_service.py', {'KIT_FILES', 'KIT_EXECUTABLE'})
        self.assertIn('macos', scope['KIT_FILES'])
        for name in scope['KIT_FILES']['macos']:
            self.assertTrue((AGENT / name).is_file(), name)
        entry = (AGENT / 'install.sh').read_text(encoding='utf-8')
        mac = (AGENT / 'install-macos.sh').read_text(encoding='utf-8')
        self.assertIn('== Darwin', entry)
        self.assertIn('exec /bin/bash "$HERE/install-macos.sh"', entry)
        self.assertEqual(mac.count('exec /usr/bin/sudo '), 1)
        self.assertIn('pkgutil --check-signature', mac)
        self.assertIn('Python Software Foundation (BMM5U3QVKW)', mac)
        self.assertIn('spctl --assess --type install', mac)
        self.assertIn('"$PYTHON" -I -B', mac)
        self.assertLess(mac.index('umask 022'), mac.index('"$PYTHON" -I -B'))
        idp = (APP / 'idp.py').read_text(encoding='utf-8')
        self.assertIn('Literal["linux", "windows", "macos"]', idp)
        self.assertIn('self.local_uid < 1000', idp)

    def test_macho_and_linux_magic(self):
        platform = SimpleNamespace(platform='darwin')
        native = definitions(AGENT / 'bootstrap.py', {'native'}, {'Path': Path, 'sys': platform})['native']
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / 'binary'
            binary.write_bytes(b'\xcf\xfa\xed\xfe')
            self.assertTrue(native(binary))
            binary.write_bytes(b'\x7fELF')
            self.assertFalse(native(binary))
            platform.platform = 'linux'
            self.assertTrue(native(binary))

    def test_rollback_executes_reverse_order_and_restores_settings(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            account = 'managed-staff'
            state, programs, launchd = root / 'state', root / 'programs', root / 'launchd'
            folder = state / account
            folder.mkdir(parents=True)
            launchd.mkdir()
            settings = root / 'managed-settings.json'
            settings.write_text('installed')
            (folder / 'managed-settings.json.backup').write_text('original')
            (folder / 'installer.json').write_text(json.dumps({'created': True, 'settings': {'managed-settings.json': 0o644}}))
            (folder / 'config.json').write_text(json.dumps({'pf_anchor': 'com.apple/test', 'pf_token': '123', 'pf_boot': 'boot',
                                                           'socket': str(root / 'broker.sock')}))
            def fake_run(*args, **kwargs):
                events.append(args[0:2])
                return SimpleNamespace(stdout='boot\n')
            def private_write(path, value):
                events.append(('settings',))
                path.write_text(value)
            namespace = {'Path': Path, 'STATE': state, 'PROGRAMS': programs, 'LAUNCHD': launchd,
                         'SOURCES': (), 'FILES': {'managed-settings.json': settings}, 'json': json,
                         'core_module': lambda: SimpleNamespace(private_write=private_write),
                         'configure_bootstrap': lambda account: SimpleNamespace(remove_shims=lambda account: events.append(('shims',))),
                         'run': fake_run,
                         'shutil': SimpleNamespace(rmtree=lambda path, **kwargs: events.append(('rmtree', str(path))))}
            definitions(AGENT / 'managed-macos.py', {'ROLLBACK_ORDER', 'rollback'}, namespace)['rollback'](account)
            self.assertEqual(settings.read_text(), 'original')
            def index(event):
                return next(i for i, item in enumerate(events) if item[:len(event)] == event)
            self.assertLess(index(('/bin/launchctl', 'bootout')), index(('shims',)))
            self.assertLess(index(('shims',)), index(('/sbin/pfctl', '-a')))
            self.assertLess(index(('/sbin/pfctl', '-X')), index(('settings',)))
            self.assertLess(index(('settings',)), index(('/usr/bin/dscl', '.')))
            self.assertEqual(events[-1], ('rmtree', str(folder)))

    def test_wrappers_keep_arguments_and_credentials_out_of_environment(self):
        text = (AGENT / 'managed-macos.py').read_text(encoding='utf-8')
        wrappers = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'write_wrappers')
        body = ast.get_source_segment(text, wrappers)
        self.assertIn("'/usr/bin/env', '-i'", body)
        self.assertNotIn('device_key', body)
        self.assertNotIn('access_token', body)
        self.assertIn("' \"$@\"\\n'", body)
        self.assertEqual(shlex.split(shlex.join(['exec', 'say "hello world"'])), ['exec', 'say "hello world"'])

    def test_ticket_is_atomic_scoped_and_distinct_from_enrollment(self):
        source = (APP / 'agent_service.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'download_managed_kit')
        body = ast.get_source_segment(source, node)
        self.assertIn('consumed_at IS NULL AND expires_at>now()', body)
        self.assertIn('kit_download_hash(ticket, platform, delivery, packaging, isolated)', body)
        self.assertIn('kit_download_hash(ticket, "macos", "zip", "zip", isolated)', body)
        self.assertIn('await current_identity(authorization)', body)
        self.assertNotEqual(hashlib.sha256(b'x' * 43).digest(), hashlib.sha256(b'kit-download:' + b'x' * 43).digest())
        self.assertIn('timedelta(minutes=5)', body)
        digest = definitions(APP / 'agent_service.py', {'kit_download_hash'}, {'hashlib': hashlib})['kit_download_hash']
        legacy = hashlib.sha256(b'kit-download:' + b'x' * 43).hexdigest()
        self.assertEqual(digest('x' * 43, 'macos', 'zip', 'zip', False), legacy)
        for scope in [('linux', 'zip', 'zip', False), ('macos', 'command', 'zip', False),
                      ('macos', 'zip', 'oneclick', False), ('macos', 'zip', 'zip', True)]:
            self.assertNotEqual(digest('x' * 43, *scope), legacy)

    def test_console_puts_windows_first(self):
        # D-239: Windows is the main target, selected first whatever browser opened the Console.
        console = (APP / 'agent_static/console.js').read_text(encoding='utf-8')
        self.assertIn('function preferredKitPlatform() {\n  return "windows";\n}', console)
        self.assertIn('Number(b === preferredKitPlatform()) - Number(a === preferredKitPlatform())', console)
        self.assertIn('mcp-connect-macos.command', console)
        self.assertIn('&delivery=command', console)

    def test_macos_control_state_uses_actual_pf_checks(self):
        scope = definitions(APP / 'endpoint_plane.py',
                            {'MANAGED_CHECKS', 'MANAGED_CHECKS_BY_PLATFORM', 'managed_platform', 'managed_checks',
                             'managed_mode', 'SIMPLE_CHECKS'})
        scope.update(datetime=datetime, HEARTBEAT_SECONDS=180,
                     host_report=lambda device, now: device['detail'].get('host'),
                     os_telemetry=lambda device, now: 'unknown')
        definitions(APP / 'integrations.py', {'PLATFORM_LABEL', 'platform_of', 'device_state'}, scope)
        now = datetime.now(timezone.utc)
        device = {'endpoint_id': 'offline-fixture', 'platform': 'macos', 'device_epoch': 'offline-epoch',
                  'status': 'active', 'managed_state': 'active', 'heartbeat_at': now,
                  'detail': {'managed_platform': 'macos', 'command_settings_checked': True,
                             'host': {'other_accounts': [{'name': 'staff', 'uid': 501, 'privileged_groups': ['admin']}]}},
                  'enforcement_checks': dict.fromkeys(scope['MANAGED_CHECKS_BY_PLATFORM']['macos'], True)}
        result = scope['device_state'](device, now)
        self.assertEqual(result['platform'], 'macos')
        self.assertEqual(result['account_state'], 'endpoint_enforced')
        self.assertEqual(result['state'], 'bypass_possible')
        device['enforcement_checks']['pf_enforcing'] = False
        self.assertEqual(scope['device_state'](device, now)['account_state'], 'bypass_possible')


if __name__ == '__main__':
    unittest.main(verbosity=2)
