"""Offline regressions only: no installation, live network, MCP or Windows policy changes."""
import hashlib
import ast
import asyncio
import importlib.util
import io
import json
import os
import ssl
import sys
import subprocess
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

# install() asks the status module for the first summary; the real one waits for a service that does not exist here.
INSTALL_STATUS = SimpleNamespace(screen_module=SimpleNamespace(wait_summary=lambda *a, **k: {'state': 'active'}, STATES={'active': '활성'}), publish=lambda *a: None)


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsKitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT, prefix='.windows-kit-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def ca_fixture(self):
        ca = self.root / 'root.crt'
        openssl = 'C:/Program Files/Git/mingw64/bin/openssl.exe' if os.name == 'nt' else 'openssl'
        subprocess.run([openssl, 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
                        '-nodes', '-days', '1', '-subj', '/CN=Offline Windows TLS CA', '-addext', 'basicConstraints=critical,CA:TRUE',
                        '-keyout', str(self.root / 'root.key'), '-out', str(ca)], check=True, capture_output=True)
        pem = ca.read_text()
        return {'ca_certificate': pem, 'ca_sha256': hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()}

    def test_pin_rejects_changed_download_without_publishing_archive(self):
        builder = load('runtime_builder', 'full_stack_lab/gateway/prepare-windows-python.py')
        manifest = self.root / 'pin.json'
        manifest.write_text(json.dumps({'url': 'https://www.python.org/fixture', 'sha256': '0' * 64}), encoding='utf-8')
        with mock.patch.object(builder.urllib.request, 'urlopen', return_value=io.BytesIO(b'changed')):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                builder.prepare(manifest, self.root / 'cache')
        self.assertFalse((self.root / 'cache/python.zip').exists())
        self.assertFalse((self.root / 'cache/python.download').exists())

    def test_build_cache_includes_original_license_and_both_executables(self):
        builder = load('runtime_builder', 'full_stack_lab/gateway/prepare-windows-python.py')
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            for name in ('python.exe', 'pythonw.exe', 'python313.zip', 'python313._pth', 'LICENSE.txt'):
                archive.writestr(name, 'synthetic build fixture')
        pin = {'url': 'https://www.python.org/fixture', 'sha256': hashlib.sha256(content.getvalue()).hexdigest(), 'pth': 'python313._pth'}
        manifest = self.root / 'pin.json'
        manifest.write_text(json.dumps(pin), encoding='utf-8')
        with mock.patch.object(builder.urllib.request, 'urlopen', return_value=io.BytesIO(content.getvalue())):
            builder.prepare(manifest, self.root / 'cache')
        self.assertEqual((self.root / 'cache/python.zip').read_bytes(), content.getvalue())
        self.assertEqual(json.loads((self.root / 'cache/windows-python.json').read_text()), pin)

    def test_download_includes_runtime_and_missing_runtime_does_not_consume_enrollment(self):
        tree = ast.parse((ROOT / 'full_stack_lab/gateway/app/agent_service.py').read_text(encoding='utf-8'))
        names = {'KIT_FILES', 'KIT_EXECUTABLE'}
        nodes = [node for node in tree.body if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names for target in node.targets)]
        download = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'download_managed_kit')
        download.decorator_list = []
        nodes.append(download)

        class Failure(Exception):
            def __init__(self, status, detail):
                self.status_code, self.detail = status, detail

        identity = mock.AsyncMock(return_value={'user_id': 'fixture', 'principal': 'fixture'})
        enrollment = mock.AsyncMock(return_value={'enrollment_token': 'synthetic-one-use-token'})
        response_headers = {}
        ca = self.ca_fixture()
        static = self.root / 'static'
        (static / 'kit').mkdir(parents=True)
        (static / 'kit/mcpgw_pc.py').write_text('fixture', encoding='utf-8')

        def response(content, **kwargs):
            response_headers.update(kwargs['headers'])
            return content
        namespace = {'Path': Path, 'os': os, 'io': io, 'json': json, 'hashlib': hashlib, 'zipfile': zipfile, 'Literal': Literal, 'Request': SimpleNamespace,
                     'Header': lambda **kwargs: None, 'HTTPException': Failure, 'current_identity': identity,
                     'urlsplit': __import__('urllib.parse', fromlist=['urlsplit']).urlsplit,
                     'Response': response, 'field_ca': lambda: ca, 'STATIC_DIR': static, '__package__': 'windows_kit_fixture'}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<existing-kit-route>', 'exec'), namespace)
        source, runtime = self.root / 'source', self.root / 'runtime'
        source.mkdir()
        runtime.mkdir()
        for name in namespace['KIT_FILES']['windows']:
            (source / name).write_text('fixture', encoding='utf-8')
        environment = {'ENDPOINT_KIT_DIR': str(source), 'WINDOWS_PYTHON_DIR': str(runtime),
                       'IDP_ISSUER': 'https://gateway.example', 'ENDPOINT_TAILSCALE_NODE_ID': ''}
        with mock.patch.dict(os.environ, environment), mock.patch.dict(sys.modules, {
            'windows_kit_fixture': SimpleNamespace(), 'windows_kit_fixture.endpoint_plane': SimpleNamespace(enrollment_token=enrollment)}):
            with self.assertRaises(Failure) as failure:
                asyncio.run(namespace['download_managed_kit'](SimpleNamespace(headers={}), 'windows'))
            self.assertEqual(failure.exception.status_code, 503)
            enrollment.assert_not_awaited()
            (runtime / 'python.zip').write_bytes(b'synthetic archive content')
            (runtime / 'windows-python.json').write_text('{}', encoding='utf-8')
            content = asyncio.run(namespace['download_managed_kit'](SimpleNamespace(headers={}), 'windows'))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(set(archive.namelist()), set(namespace['KIT_FILES']['windows']) | {'enrollment.json', 'python.zip', 'windows-python.json', 'windows-kit-manifest.json', 'root.crt', 'root.sha256', 'mcpgw_pc.py'})
            self.assertEqual(archive.read('python.zip'), b'synthetic archive content')
            manifest = json.loads(archive.read('windows-kit-manifest.json'))
            self.assertEqual(response_headers['X-Windows-Kit-Manifest-SHA256'],
                             hashlib.sha256(archive.read('windows-kit-manifest.json')).hexdigest())
            self.assertEqual(manifest['gateway_url'], 'https://gateway.example')
            self.assertNotIn('enrollment.json', manifest['files'])
            self.assertTrue({'root.crt', 'root.sha256', 'mcpgw_pc.py'} <= set(manifest['files']))
            self.assertEqual(json.loads(archive.read('enrollment.json'))['ca_sha256'], ca['ca_sha256'])
            for name, expected in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)

    def test_tray_snapshot_bounds_deduplicates_and_never_copies_private_event_fields(self):
        status = load('windows_status_test', 'endpoint-agent/windows_status.py')
        path = self.root / 'status.json'
        blocks = [{'event_id': str(i), 'observed_at': '2026-10-17T12:00:00Z', 'kind': 'execution-denied',
                   'details': {'secret': 'never-publish'}, 'device_key': 'never-publish'} for i in range(8)]
        status.publish(path, True, blocks, '활성')
        status.publish(path, False, [blocks[-1], {'kind': 'process-started', 'event_id': 'ignore'}], '확인 필요')
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual([row['id'] for row in snapshot['blocks']], ['3', '4', '5', '6', '7'])
        self.assertFalse(snapshot['connected'])
        self.assertNotIn('never-publish', path.read_text(encoding='utf-8'))
        self.assertFalse(path.with_suffix('.tmp').exists())
        path.write_text('[]', encoding='utf-8')
        status.publish(path, True, [blocks[-1], {**blocks[0], 'observed_at': '2026-10-17T13:00:00Z'}])
        self.assertEqual([row['id'] for row in json.loads(path.read_text(encoding='utf-8'))['blocks']], ['7', '0'])

    def test_managed_ca_is_verified_before_enrollment_and_kept_out_of_global_environment(self):
        managed = load('windows_tls_test', 'endpoint-agent/managed-windows.py')
        ca = self.ca_fixture()
        config = {'gateway_url': 'https://gateway.example', 'tailscale_node_id': '',
                  'sid': 'S-1-5-21-1-2-3-1001', **ca}
        context = managed.verify_transport(config)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        bad = {**config, 'ca_sha256': '0' * 64}
        enrollment = self.root / 'enrollment.json'
        enrollment.write_text(json.dumps(bad), encoding='utf-8')
        admin = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True))
        with mock.patch.object(managed.ctypes, 'windll', admin, create=True), \
                mock.patch.object(managed, 'managed_user') as account, \
                mock.patch.object(managed.urllib.request, 'build_opener') as opener:
            with self.assertRaises(ValueError):
                managed.install(SimpleNamespace(user='fixture', enrollment=enrollment))
            with self.assertRaises(ValueError):
                managed.request(bad, '/oauth/device-enroll', {}, credential=False)
            account.assert_not_called()
            opener.assert_not_called()
        before = dict(os.environ)
        programs = self.root / 'programs'
        native = programs / 'harness'
        native.mkdir(parents=True)
        with mock.patch.object(managed, 'PROGRAMS', programs), \
                mock.patch.object(managed, 'lock_down', side_effect=lambda p: p.mkdir(parents=True, exist_ok=True)):
            launchers, owned = managed.harness_launchers(config, native, {'codex.exe': 'fixture', 'claude.exe': 'fixture'})
            for name, variable in (('codex', 'CODEX_CA_CERTIFICATE'), ('claude', 'NODE_EXTRA_CA_CERTS')):
                script = (launchers / (name + '.cmd')).read_text(encoding='utf-8')
                self.assertIn('setlocal\n', script)
                self.assertIn('set "' + variable + '=%~dp0root.crt"', script)
                self.assertNotIn('setx', script.lower())
            for path, digest in owned.items():
                self.assertEqual(hashlib.sha256((programs / path).read_bytes()).hexdigest(), digest)
        self.assertEqual(os.environ, before)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell .NET validation requires Windows')
    def test_powershell_private_ca_validates_chain_pin_name_expiry_and_never_sets_global_callback(self):
        ca = self.ca_fixture()
        (self.root / 'root.sha256').write_text(ca['ca_sha256'])
        openssl = 'C:/Program Files/Git/mingw64/bin/openssl.exe'
        subprocess.run([openssl, 'req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256', '-nodes',
                        '-subj', '/CN=gateway.example', '-keyout', str(self.root / 'leaf.key'), '-out', str(self.root / 'leaf.csr')],
                       check=True, capture_output=True)
        (self.root / 'extensions').write_text('basicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:gateway.example\n')
        for label, days in [('leaf', '1')]:
            subprocess.run([openssl, 'x509', '-req', '-in', str(self.root / 'leaf.csr'), '-CA', str(self.root / 'root.crt'),
                            '-CAkey', str(self.root / 'root.key'), '-set_serial', '2', '-days', days,
                            '-extfile', str(self.root / 'extensions'), '-outform', 'DER', '-out', str(self.root / (label + '.der'))],
                           check=True, capture_output=True)
        (self.root / 'index.txt').write_text('')
        (self.root / 'serial').write_text('10\n')
        (self.root / 'ca.cnf').write_text('[ca]\ndefault_ca=local\n[local]\ndatabase=index.txt\nserial=serial\n'
                                        'new_certs_dir=.\nprivate_key=root.key\ncertificate=root.crt\ndefault_md=sha256\n'
                                        'policy=names\n[names]\ncommonName=supplied\n')
        subprocess.run([openssl, 'ca', '-batch', '-config', 'ca.cnf', '-in', 'leaf.csr', '-startdate', '20200101000000Z',
                        '-enddate', '20200102000000Z', '-out', 'expired.pem'], cwd=self.root, check=True, capture_output=True)
        subprocess.run([openssl, 'x509', '-in', 'expired.pem', '-outform', 'DER', '-out', 'expired.der'],
                       cwd=self.root, check=True, capture_output=True)
        script = r'''
$ErrorActionPreference='Stop'
. (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-common.ps1')
$pem=[IO.File]::ReadAllText((Join-Path $env:KIT_TEST_TEMP 'root.crt'))
$pin=[IO.File]::ReadAllText((Join-Path $env:KIT_TEST_TEMP 'root.sha256'))
$before=[Net.ServicePointManager]::ServerCertificateValidationCallback
$request=New-EndpointGatewayRequest 'https://gateway.example/api/health' $pem $pin
$root=[EndpointKit.GatewayTls]::Root($pem,$pin)
$leaf=New-Object Security.Cryptography.X509Certificates.X509Certificate2((Join-Path $env:KIT_TEST_TEMP 'leaf.der'))
$expired=New-Object Security.Cryptography.X509Certificates.X509Certificate2((Join-Path $env:KIT_TEST_TEMP 'expired.der'))
$chainError=[Net.Security.SslPolicyErrors]::RemoteCertificateChainErrors
if (-not $request.ServerCertificateValidationCallback.Invoke($request,$leaf,$null,$chainError)) { throw 'valid private chain rejected' }
if ($request.ServerCertificateValidationCallback.Invoke($request,$leaf,$null,[Net.Security.SslPolicyErrors]::RemoteCertificateNameMismatch)) { throw 'name mismatch accepted' }
if ([EndpointKit.GatewayTls]::Validate($expired,$null,$chainError,$root)) { throw 'expired certificate accepted' }
if ([EndpointKit.GatewayTls]::Validate($leaf,$null,$chainError,$leaf)) { throw 'wrong root accepted' }
foreach ($case in @(@($pem,('0'*64)),@(($pem+$pem),$pin),@($pem,''))) {
    $failed=$false; try { $null=New-EndpointGatewayRequest 'https://gateway.example/' $case[0] $case[1] } catch { $failed=$true }
    if (-not $failed) { throw 'invalid pin or root accepted' }
}
$failed=$false; try { $null=New-EndpointGatewayRequest 'http://100.83.175.111/api/health' $pem $pin } catch { $failed=$true }
if (-not $failed) { throw 'remote plaintext accepted' }
if ($request.AllowAutoRedirect -or $request.Proxy -or [Net.ServicePointManager]::SecurityProtocol -ne [Net.SecurityProtocolType]::Tls12) { throw 'request protections changed' }
if ([Net.ServicePointManager]::ServerCertificateValidationCallback -ne $before) { throw 'global trust changed' }
$request.Abort()
Write-Output 'Per-request CA verification OK'
'''
        process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                                 env=dict(os.environ, KIT_TEST_ROOT=str(ROOT), KIT_TEST_TEMP=str(self.root)), timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))

    def test_removal_also_takes_the_launcher_an_older_manifest_never_listed(self):
        # pj3 10-28: a kit without the launcher reinstalled over one with it; its manifest lacked MCPGateway.exe/.ico,
        # so removal left them and the next install stopped at "다른 파일이 없는 설치 위치 필요".
        programs = self.root / 'Program Files'
        root = programs / 'MCPGatewayManaged'
        root.mkdir(parents=True)
        (root / '.endpoint-kit').write_text(json.dumps({'product': 'MCPGatewayEndpoint', 'files': ['agent.py']}), encoding='utf-8')
        for name in ('agent.py', 'MCPGateway.exe', 'MCPGateway.ico'):
            (root / name).write_bytes(b'x')
        (root / 'mine.txt').write_text('keep', encoding='utf-8')
        script = "$env:ProgramFiles = $env:KIT_TEST_PF; . (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent\windows-common.ps1'); Remove-EndpointFiles (Join-Path $env:ProgramFiles 'MCPGatewayManaged')"
        process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                                 env=dict(os.environ, KIT_TEST_ROOT=str(ROOT), KIT_TEST_PF=str(programs)), timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))
        self.assertEqual(sorted(p.name for p in root.iterdir()), ['mine.txt'])

    def test_managed_install_carries_ca_to_private_service_and_observers(self):
        managed = load('windows_tls_install_test', 'endpoint-agent/managed-windows.py')
        ca = self.ca_fixture()
        enrollment = self.root / 'enrollment.json'
        enrollment.write_text(json.dumps({'gateway_url': 'https://gateway.example', 'tailscale_node_id': 'approved',
                                          'enrollment_token': 'synthetic', **ca}), encoding='utf-8')
        profile = self.root / 'profile'
        profile.mkdir()
        (profile / 'NTUSER.DAT').touch()
        programs, state = self.root / 'programs', self.root / 'state'
        native = programs / 'harness'
        native.mkdir(parents=True)
        policy = {'tailscale_node_id': 'approved', 'gateway_ips': ['100.83.175.111'], 'gateway_port': 443,
                  'policy_hash': 'fixture-policy', 'proxy_environment': {}, 'files': {'codex-config.toml': ''}}
        def request(config, path, *args, **kwargs):
            self.assertEqual(config['ca_certificate'], ca['ca_certificate'])
            self.assertEqual(config['ca_sha256'], ca['ca_sha256'])
            return {'endpoint_id': 'fixture'} if path == '/oauth/device-enroll' else policy
        admin = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True))
        with mock.patch.object(managed.ctypes, 'windll', admin, create=True), \
                mock.patch.multiple(managed, PROGRAMS=programs, STATE=state, PROGRAM_DATA=self.root / 'data', FILES={}), \
                mock.patch.object(managed, 'managed_user', return_value=('fixture', {'sid': 'S-1-5-21-1-2-3-1001', 'profile': str(profile)}, False)), \
                mock.patch.object(managed, 'account', return_value={'sid': 'S-1-5-21-1-2-3-1001', 'profile': str(profile), 'admin': False}), \
                mock.patch.object(managed, 'prepare_profile', side_effect=lambda name, person: person), \
                mock.patch.object(managed, 'protected', return_value=True), \
                mock.patch.object(managed, 'lock_down', side_effect=lambda p, **kw: p.mkdir(parents=True, exist_ok=True)), \
                mock.patch.object(managed, 'powershell', return_value='0'), \
                mock.patch.object(managed, 'place_harnesses', return_value=(native, {'codex.exe': 'fixture'})), \
                mock.patch.object(managed, 'request', side_effect=request), mock.patch.object(managed, 'apply_policy'), \
                mock.patch.object(managed, 'rule_state', return_value={'rules': []}), \
                mock.patch.object(managed, 'set_user_environment') as environment, mock.patch.dict(sys.modules, {'windows_status': INSTALL_STATUS}), mock.patch('sys.stdout', io.StringIO()):
            # The isolated account carries the CA in its launchers, never in the account environment.
            managed.install(SimpleNamespace(user='fixture', enrollment=enrollment, isolated_account=True))
            config_path = state / 'fixture/config.json'
            saved = json.loads(config_path.read_text(encoding='utf-8'))
            self.assertEqual(saved['ca_certificate'], ca['ca_certificate'])
            self.assertEqual(saved['ca_sha256'], ca['ca_sha256'])
            self.assertEqual(saved['harness_paths'], [str(native / 'codex.exe')])
            values = environment.call_args.args[1]
            self.assertNotIn('NODE_EXTRA_CA_CERTS', values)
            self.assertNotIn('CODEX_CA_CERTIFICATE', values)
            with mock.patch.object(managed, 'FILES', {'managed-mcp.json': programs / 'claude/settings.json', 'requirements.toml': programs / 'codex/requirements.toml'}), \
                    mock.patch.object(managed.threading, 'Thread'), \
                    mock.patch.dict(sys.modules, {'windows_status': SimpleNamespace(publish=lambda *a: None)}), \
                    mock.patch.object(managed, 'request', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
                managed.serve(SimpleNamespace(config=config_path))
            observer = json.loads(config_path.with_name('observer.json').read_text(encoding='utf-8'))
            self.assertEqual(observer['ENDPOINT_CA_CERTIFICATE'], ca['ca_certificate'])
            self.assertEqual(observer['ENDPOINT_CA_SHA256'], ca['ca_sha256'])
            self.assertEqual(observer['ENDPOINT_HARNESS_PATHS'], saved['harness_paths'])

    def test_simple_install_keeps_the_signed_in_admin_account_and_names_the_ca_in_its_environment(self):
        managed = load('windows_simple_install_test', 'endpoint-agent/managed-windows.py')
        ca = self.ca_fixture()
        enrollment = self.root / 'enrollment.json'
        enrollment.write_text(json.dumps({'gateway_url': 'https://gateway.example', 'tailscale_node_id': 'approved',
                                          'enrollment_token': 'synthetic', **ca}), encoding='utf-8')
        profile = self.root / 'profile'
        (profile / '.local/share/claude/versions/2.1.9').mkdir(parents=True)
        (profile / '.local/share/claude/versions/2.1.10').mkdir()
        (profile / 'NTUSER.DAT').touch()
        programs, state = self.root / 'programs', self.root / 'state'
        policy = {'tailscale_node_id': 'approved', 'gateway_ips': ['100.83.175.111'], 'gateway_port': 443,
                  'policy_hash': 'fixture-policy', 'proxy_environment': {'HTTPS_PROXY': 'http://proxy:3128'}, 'files': {'codex-config.toml': ''}}
        sent = []

        def request(config, path, body=None, **kwargs):
            sent.append((path, body))
            return {'endpoint_id': 'fixture', 'state': 'pending'} if path == '/oauth/device-enroll' else policy
        admin = SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True))
        person = {'sid': 'S-1-5-21-1-2-3-1001', 'profile': str(profile), 'admin': True}  # a signed-in administrator
        with mock.patch.object(managed.ctypes, 'windll', admin, create=True), \
                mock.patch.multiple(managed, PROGRAMS=programs, STATE=state, PROGRAM_DATA=self.root / 'data', FILES={}), \
                mock.patch.object(managed, 'account', return_value=person), \
                mock.patch.object(managed, 'managed_user') as companion, \
                mock.patch.object(managed, 'protected', return_value=True), \
                mock.patch.object(managed, 'lock_down', side_effect=lambda p, **kw: p.mkdir(parents=True, exist_ok=True)), \
                mock.patch.object(managed, 'powershell', return_value=None) as powershell, \
                mock.patch.object(managed, 'place_harnesses') as place, \
                mock.patch.object(managed, 'request', side_effect=request), mock.patch.object(managed, 'apply_policy'), \
                mock.patch.object(managed, 'set_user_environment') as environment, \
                mock.patch.object(managed, 'broadcast_environment') as broadcast, mock.patch.dict(sys.modules, {'windows_status': INSTALL_STATUS}), mock.patch('sys.stdout', io.StringIO()) as out:
            managed.install(SimpleNamespace(user='fixture', enrollment=enrollment))
        companion.assert_not_called()
        place.assert_not_called()
        scripts = [call.args[0] for call in powershell.call_args_list]
        self.assertNotIn(managed.OWNED_PROCESSES, scripts)  # the employee stays signed in
        self.assertNotIn(managed.APPLY_RULES, scripts)  # no account firewall in simple mode
        self.assertIn(managed.REMOVE_COMPANION, scripts)  # an earlier isolated companion is retired
        enroll = dict(sent)['/oauth/device-enroll']
        self.assertEqual((enroll['mode'], enroll['local_sid'], enroll['local_username']), ('simple', person['sid'], 'fixture'))
        values = environment.call_args.args[1]
        self.assertEqual(set(values), {'NODE_EXTRA_CA_CERTS', 'CODEX_CA_CERTIFICATE'})
        self.assertEqual(Path(values['NODE_EXTRA_CA_CERTS']).read_text(encoding='utf-8'), ca['ca_certificate'])
        broadcast.assert_called_once()
        summary = json.loads(out.getvalue().splitlines()[0])
        self.assertEqual((summary['mode'], summary['versions']), ('simple', {'claude': '2.1.10'}))
        self.assertEqual(json.loads((state / 'fixture/config.json').read_text(encoding='utf-8'))['mode'], 'simple')
        status = load('windows_status_render', 'endpoint-agent/windows_status.py')
        text = status.render({'updated': 100, 'connected': True, 'management': '활성', 'mode': 'simple',
                              'servers': ['learn', 'deepwiki'], 'harnesses': {'claude': '2.1.10'}}, now=110)
        self.assertIn('승인 서버: 2개 · learn, deepwiki', text)
        self.assertIn('간편 모드', text)

    def test_tray_snapshot_retries_windows_sharing_violation(self):
        status = load('windows_status_test', 'endpoint-agent/windows_status.py')
        replace = status.os.replace
        calls = []

        def sharing(source, target):
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError(32, 'sharing violation')
            replace(source, target)
        with mock.patch.object(status.os, 'replace', sharing), mock.patch.object(status.time, 'sleep'):
            status.publish(self.root / 'status.json', True)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(OSError):
            status.publish(self.root / 'not-provisioned/status.json', True)
        self.assertFalse((self.root / 'not-provisioned').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows ACL descriptors require Windows')
    def test_approved_payload_rejects_script_zip_manifest_and_destination_substitution(self):
        code, policy = self.root / 'approved', self.root / 'policy'
        code.mkdir()
        policy.mkdir()
        names = ('install.cmd', 'setup.ps1', 'windows-common.ps1', 'windows-worker.ps1', 'windows-trust.ps1', 'tray.ps1',
                 'runtime-check.py', 'windows_status.py', 'kit_screen.py', 'install.py', 'install-windows.ps1', 'managed-windows.py',
                 'agent.py', 'os-observer-windows.py', 'offline_buffer.py', 'python.zip', 'windows-python.json', 'root.crt', 'root.sha256', 'mcpgw_pc.py')
        for name in names:
            (code / name).write_bytes(('synthetic, never executed: ' + name).encode())
        manifest = {'schema': 1, 'gateway_url': 'https://approved.example', 'tailscale_node_id': '',
                    'files': {name: hashlib.sha256((code / name).read_bytes()).hexdigest() for name in names}}
        (policy / 'approved-windows-kit.json').write_text(json.dumps(manifest), encoding='utf-8')
        script = r'''
$ErrorActionPreference='Stop'
. (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-trust.ps1')
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-worker.ps1'),[ref]$tokens,[ref]$errors)
$seed=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-EndpointBootstrapSeed'},$false)
. ([scriptblock]::Create($seed.Extent.Text))
$script:testPaths=@{ code=(Join-Path $env:KIT_TEST_TEMP 'approved'); state=(Join-Path $env:KIT_TEST_TEMP 'policy') }
function Get-EndpointInstallerPaths { return $script:testPaths }
# Only ACL lookup is a unit double; hashes use real fixture file bytes.
$script:testAcl=New-EndpointAccessDescriptor '' $true
function Get-Acl { param([string]$LiteralPath) return $script:testAcl }
$approval=Get-EndpointApprovedKit
Assert-EndpointBootstrapSeed $script:testPaths.code $script:testPaths.state
foreach ($name in @('windows-worker.ps1','windows-trust.ps1','windows-common.ps1','python.zip','windows-python.json')) {
    $file=Join-Path $script:testPaths.code $name
    $original=[IO.File]::ReadAllBytes($file)
    [IO.File]::WriteAllText($file, 'throw "substituted fixture must never execute"')
    $fake=Get-Content -LiteralPath (Join-Path $script:testPaths.state 'approved-windows-kit.json') -Raw | ConvertFrom-Json
    $fake.files.$name=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    $fake | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $script:testPaths.code 'windows-kit-manifest.json')
    $rejected=$false; try { $null=Get-EndpointApprovedKit } catch { $rejected=$true }
    if (-not $rejected) { throw 'same-folder manifest became its own authority' }
    if ($name -in @('windows-trust.ps1','windows-worker.ps1')) {
        $rejected=$false; try { Assert-EndpointBootstrapSeed $script:testPaths.code $script:testPaths.state } catch { $rejected=$true }
        if (-not $rejected) { throw 'bootstrap imported an unverified helper' }
    }
    [IO.File]::WriteAllBytes($file,$original)
}
$target=Join-Path $env:KIT_TEST_TEMP 'installed'
New-Item -ItemType Directory -Path $target | Out-Null
[IO.File]::WriteAllText((Join-Path $target 'windows-common.ps1'),'changed after copy')
$rejected=$false; try { Assert-EndpointFileHashes $target $approval @('windows-common.ps1') } catch { $rejected=$true }
if (-not $rejected) { throw 'destination was executed before verification' }
$extra=Join-Path $script:testPaths.code 'powershell.exe'
[IO.File]::WriteAllText($extra,'unlisted executable fixture')
$rejected=$false; try { $null=Get-EndpointApprovedKit } catch { $rejected=$true }
if (-not $rejected) { throw 'unlisted executable accepted' }
Remove-Item -LiteralPath $extra
$script:testAcl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
    (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')),'Write','ContainerInherit,ObjectInherit','None','Allow')))
$rejected=$false; try { $null=Get-EndpointApprovedKit } catch { $rejected=$true }
if (-not $rejected) { throw 'writable approval root accepted' }
$script:testAcl=New-EndpointAccessDescriptor '' $true
Remove-Item -LiteralPath (Join-Path $script:testPaths.state 'approved-windows-kit.json')
$rejected=$false; try { $null=Get-EndpointApprovedKit } catch { $rejected=$true }
if (-not $rejected) { throw 'missing approval accepted' }
if (Test-Path -LiteralPath (Join-Path $script:testPaths.state 'approved-windows-kit.json')) { throw 'untrusted kit approved itself' }
Write-Output 'Approved payload substitution and ACL checks OK'
'''
        process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                                 env=dict(os.environ, KIT_TEST_ROOT=str(ROOT), KIT_TEST_TEMP=str(self.root)), timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))

    @unittest.skipUnless(os.name == 'nt', 'Windows ACL descriptors require Windows')
    def test_tray_acl_has_only_target_admin_system_and_data_read_is_bounded(self):
        (self.root / 'request.json').write_text('{"synthetic":true}', encoding='utf-8')
        script = r'''
$ErrorActionPreference='Stop'
. (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-trust.ps1')
$sid='S-1-5-21-1-2-3-1001'
foreach ($directory in @($true,$false)) {
    $acl=New-EndpointAccessDescriptor $sid $directory
    if (-not $acl.AreAccessRulesProtected) { throw 'inherited read grants remain' }
    $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    $allowed=@($rules | ForEach-Object { $_.IdentityReference.Value } | Sort-Object)
    if (Compare-Object @('S-1-5-18','S-1-5-21-1-2-3-1001','S-1-5-32-544') $allowed) { throw 'cross-user read grant' }
    $reader=$rules | Where-Object { $_.IdentityReference.Value -eq $sid }
    if ([long]$reader.FileSystemRights -band 0xD0156) { throw 'target user can change SYSTEM-owned status' }
    Assert-EndpointTrustedAcl $acl
}
$file=Join-Path $env:KIT_TEST_TEMP 'request.json'
$env:TEMP=$env:KIT_TEST_TEMP
$env:TMP=$env:KIT_TEST_TEMP
$value=Read-EndpointDataFile $file 1024
if (-not $value.synthetic) { throw 'data snapshot failed' }
$rejected=$false; try { $null=Read-EndpointDataFile $file 2 } catch { $rejected=$true }
if (-not $rejected) { throw 'oversized request accepted' }
[IO.File]::WriteAllText($file,'{"enrollment_token":"synthetic-secret"')
$rejected=$false; try { $null=Read-EndpointDataFile $file 1024 } catch {
    $rejected=$true
    if ($_.Exception.Message -match 'synthetic-secret') { throw 'credential echoed in parse error' }
}
if (-not $rejected) { throw 'invalid JSON accepted' }
$rejected=$false; try { Remove-EndpointCompilerTemp $env:SystemRoot } catch { $rejected=$true }
if (-not $rejected) { throw 'compiler cleanup escaped its protected root' }
Write-Output 'Per-user ACL and bounded data snapshot OK'
'''
        process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                                 env=dict(os.environ, KIT_TEST_ROOT=str(ROOT), KIT_TEST_TEMP=str(self.root)), timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))

    @unittest.skipUnless(os.name == 'nt', 'Windows file handles require Windows')
    def test_managed_request_is_snapshotted_as_data_and_gateway_is_from_external_approval(self):
        ca = self.ca_fixture()
        (self.root / 'root.sha256').write_text(ca['ca_sha256'])
        profile = self.root / 'profile'
        work = profile / 'AppData/Local/MCPGatewaySetup' / ('a' * 32)
        work.mkdir(parents=True)
        enrollment = profile / 'Downloads/enrollment.json'
        enrollment.parent.mkdir()
        enrollment.write_text(json.dumps({'gateway_url': 'https://changed.example', 'tailscale_node_id': 'changed',
                                          'ca_certificate': 'caller changed root', 'ca_sha256': '0' * 64,
                                          'enrollment_token': 'synthetic-enrollment'}), encoding='utf-8')
        # The one-click template's request: no gateway_url/tailscale_node_id of its own (pj3 10-25 failed on that).
        (work / 'request.json').write_text(json.dumps({'mode': 'managed', 'action': 'install', 'user': 'fixture',
            'requester_sid': 'S-1-5-21-1-2-3-1001', 'isolated_account': False, 'enrollment': str(enrollment)}), encoding='utf-8')
        script = r'''
$ErrorActionPreference='Stop'
. (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-trust.ps1')
. (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-common.ps1')
$script:testProfile=Join-Path $env:KIT_TEST_TEMP 'profile'
$script:state=Join-Path $env:KIT_TEST_TEMP 'policy'
New-Item -ItemType Directory -Path $script:state | Out-Null
function Get-EndpointInstallerPaths { return @{ state=$script:state; code=$env:KIT_TEST_TEMP } }
function Get-ItemProperty { param([string]$LiteralPath) return [pscustomobject]@{ProfileImagePath=$script:testProfile} }
# Creation/ACL application is doubled; file reads, kernel paths and snapshot bytes are real.
$script:readers=@{}
function New-EndpointProtectedDirectory { param([string]$Path,[string]$ReaderSid)
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    $script:readers[$Path]=$ReaderSid
}
$env:TEMP=$env:KIT_TEST_TEMP
$env:TMP=$env:KIT_TEST_TEMP
$input=Join-Path $script:testProfile ('AppData\Local\MCPGatewaySetup\' + ('a'*32) + '\request.json')
$approved=[pscustomobject]@{gateway_url='https://approved.example';tailscale_node_id='approved-node';files=[pscustomobject]@{'root.crt'='unit-already-verified'}}
$request=Read-EndpointManagedRequest $input $approved 'S-1-5-21-1-2-3-1001'
$bundle=Get-Content -LiteralPath $request.enrollment -Raw | ConvertFrom-Json
if ($request.gateway_url -ne $approved.gateway_url -or $bundle.gateway_url -ne $approved.gateway_url) { throw 'caller chose privileged destination' }
if ($bundle.tailscale_node_id -ne 'approved-node') { throw 'caller changed transport pin' }
if ($bundle.ca_sha256 -ne [IO.File]::ReadAllText((Join-Path $env:KIT_TEST_TEMP 'root.sha256'))) { throw 'caller chose privileged root' }
if ($request.ca_certificate -ne $bundle.ca_certificate -or $request.ca_sha256 -ne $bundle.ca_sha256) { throw 'CA not carried to privileged request' }
[IO.File]::WriteAllText((Join-Path $script:testProfile 'Downloads/enrollment.json'),'{"enrollment_token":"later replacement"}')
$copy=Get-Content -LiteralPath $request.enrollment -Raw | ConvertFrom-Json
if ($copy.enrollment_token -ne 'synthetic-enrollment') { throw 'mutable source was reread' }
if ($script:readers[$request.result_directory] -ne 'S-1-5-21-1-2-3-1001') { throw 'result readable by wrong user' }
if ($script:readers[$request.private_directory]) { throw 'private enrollment readable by caller' }
$rejected=$false; try { $null=Read-EndpointManagedRequest $input $approved 'S-1-5-21-1-2-3-1001' } catch { $rejected=$true }
if (-not $rejected) { throw 'live request replay accepted' }
$invalid=Get-Content -LiteralPath $input -Raw | ConvertFrom-Json
$invalid.user=@('fixture','another')
$invalid | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $input -Encoding UTF8
$rejected=$false; try { $null=Read-EndpointManagedRequest $input $approved 'S-1-5-21-1-2-3-1001' } catch {
    $rejected=$_.Exception.Message -eq '설치 요청 범위 거부'
}
if (-not $rejected) { throw 'array bypassed account validation' }
Write-Output 'Managed request data snapshot and approved destination OK'
'''
        process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                                 env=dict(os.environ, KIT_TEST_ROOT=str(ROOT), KIT_TEST_TEMP=str(self.root)), timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))

    def test_managed_rollback_waits_for_service_and_preserves_new_user_settings(self):
        managed = load('windows_rollback_test', 'endpoint-agent/managed-windows.py')
        folder = self.root / 'state/fixture'
        folder.mkdir(parents=True)
        profile = self.root / 'profile'
        (profile / '.codex').mkdir(parents=True)
        (folder / 'config.json').write_text(json.dumps({'profile': str(profile), 'sid': 'S-1-5-21-1-2-3-1001'}), encoding='utf-8')
        (folder / 'config.toml.backup').write_text('model = "before"\n', encoding='utf-8')
        current = managed.with_codex_block('model = "user-changed"\nkeep = true\n', '[mcp_servers.fixture]\nurl="synthetic"\n')
        (folder / managed.CODEX_BLOCK).write_text('[mcp_servers.fixture]\nurl="synthetic"\n', encoding='utf-8')
        path = profile / '.codex/config.toml'
        path.write_text(current, encoding='utf-8')
        powershell = mock.Mock()
        with mock.patch.object(managed, 'STATE', self.root / 'state'), mock.patch.object(managed, 'FILES', {}), \
             mock.patch.object(managed.ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)), create=True), \
             mock.patch.object(managed, 'powershell', powershell), mock.patch.object(managed, 'set_user_environment'):
            managed.rollback(SimpleNamespace(user='fixture'))
        self.assertEqual(path.read_text(encoding='utf-8').rstrip(), 'model = "user-changed"\nkeep = true')
        script = powershell.call_args.args[0]
        self.assertLess(script.index('Stop-ScheduledTask'), script.index('Unregister-ScheduledTask'))
        self.assertIn('종료 시간 초과', script)
        self.assertFalse(folder.exists())

    def test_uninstall_waits_for_report_log_and_late_report_does_not_recreate_settings(self):
        kit = load('pc_kit_race', 'full_stack_lab/field/pc/mcpgw_pc.py')
        config = self.root / 'config.json'
        config.write_text('{}', encoding='utf-8')
        (self.root / 'notes.txt').write_text('employee file', encoding='utf-8')
        entered, release, removed = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def reporting(settings):
            entered.set()
            if not release.wait(5):
                raise AssertionError('test did not release report')
            config.write_text('{}', encoding='utf-8')
            return '보고 완료'

        def runner(action):
            try:
                action()
            except BaseException as error:
                errors.append(error)

        with mock.patch.dict(os.environ, {'MCPGW_HOME': str(self.root), 'CODEX_HOME': str(self.root / 'codex')}), \
             mock.patch.object(kit, 'report_and_apply', reporting), mock.patch.object(kit, 'claude_path', return_value=None):
            report = threading.Thread(target=lambda: runner(lambda: kit.cmd_report(SimpleNamespace(background=True))))
            uninstall = threading.Thread(target=lambda: runner(lambda: (kit.cmd_uninstall(None), removed.set())))
            report.start()
            try:
                self.assertTrue(entered.wait(3))
                uninstall.start()
                self.assertFalse(removed.wait(0.15), 'uninstall must wait until the report closes its log')
            finally:
                release.set()
                report.join(5)
                if uninstall.ident:
                    uninstall.join(5)
            self.assertFalse(report.is_alive())
            self.assertFalse(uninstall.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(removed.is_set())
            kit.cmd_report(SimpleNamespace(background=True))
            with mock.patch.object(kit.subprocess, 'Popen', side_effect=AssertionError('late report spawned')):
                kit.report_in_background({'harnesses': ['claude']})
        self.assertFalse(config.exists())
        self.assertFalse((self.root / 'report.log').exists())
        self.assertEqual((self.root / 'notes.txt').read_text(), 'employee file')
        self.assertTrue((self.root / 'report.lock').exists())
        self.assertEqual((self.root / 'report.lock').stat().st_size, 0)
        self.assertEqual({path.name for path in self.root.iterdir()}, {'notes.txt', 'report.lock'})

    def test_rendered_config_bytes_match_gateway_hash(self):
        # pj3: CRLF translation made three of four managed configs mismatch, so activation was refused.
        managed = load('windows_write_test', 'endpoint-agent/managed-windows.py')
        content = '{\n  "a": 1\n}\n'
        managed.write_file(self.root / 'managed-settings.json', content)
        self.assertEqual(hashlib.sha256((self.root / 'managed-settings.json').read_bytes()).hexdigest(),
                         hashlib.sha256(content.encode()).hexdigest())

    def test_acl_reaches_existing_files_through_inheritance(self):
        # pj3: icacls /T left existing files with empty DACLs, so the elevated installer could not take ownership.
        managed = load('windows_acl_test', 'endpoint-agent/managed-windows.py')
        kit = self.root / 'kit'
        kit.mkdir()
        (kit / 'a.py').write_text('x', encoding='utf-8')
        with mock.patch.object(managed.subprocess, 'run') as run:
            managed.lock_down(kit)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertNotIn('/T', commands[1])
        self.assertEqual(commands[2][1:3], [str(kit / '*'), '/reset'])
        if os.name != 'nt':
            return
        script = r'''
$ErrorActionPreference='Stop'
. (Join-Path $env:KIT_TEST_ROOT 'endpoint-agent/windows-common.ps1')
Set-EndpointAcl $env:KIT_ACL_DIR ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
$file = Join-Path $env:KIT_ACL_DIR 'a.py'
if (-not @((Get-Acl -LiteralPath $file).Access).Count) { throw 'empty file DACL' }
Get-Content -LiteralPath $file | Out-Null
'''
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], check=True, capture_output=True,
                       env={**os.environ, 'KIT_TEST_ROOT': str(ROOT), 'KIT_ACL_DIR': str(kit)})

    def test_powershell_scripts_parse_and_input_boundaries_fail_without_host_changes(self):
        if os.name != 'nt':
            self.skipTest('PowerShell 5.1 parser requires Windows')
        script = r'''
$ErrorActionPreference='Stop'
$root=$env:KIT_TEST_ROOT
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'endpoint-agent') -Filter '*.ps1') {
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors) | Out-Null
    if ($errors) { throw ($errors | Out-String) }
    if ([IO.File]::ReadAllBytes($file.FullName)[0] -ne 239) { throw 'PowerShell 5.1 requires UTF-8 BOM' }
}
. (Join-Path $root 'endpoint-agent/windows-common.ps1')
if ((Quote-EndpointArgument 'C:\Program Files\kit\agent.py') -ne '"C:\Program Files\kit\agent.py"') { throw 'quoting failed' }
foreach ($path in @('C:\bad"path', 'C:\ends\')) {
    $rejected=$false; try { Quote-EndpointArgument $path } catch { $rejected=$true }
    if (-not $rejected) { throw 'argument validation failed' }
}
foreach ($url in @('http://8.8.8.8', 'https://user:secret@example.com', 'https://example.com/query?secret=x')) {
    $rejected=$false; try { Test-EndpointGateway $url } catch { $rejected=$true }
    if (-not $rejected) { throw 'URL validation failed' }
}
$rejected=$false; try { Remove-EndpointFiles $env:SystemRoot } catch { $rejected=$true }
if (-not $rejected) { throw 'uninstall boundary failed' }
$env:LOCALAPPDATA=$env:KIT_TEST_TEMP
$target=Join-Path $env:KIT_TEST_TEMP 'kit'
New-Item -ItemType Directory -Path (Join-Path $target 'python') -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $target 'config.json'), '{}')
[IO.File]::WriteAllText((Join-Path $target 'notes.txt'), 'employee file')
[IO.File]::WriteAllText((Join-Path $target 'python/keep.txt'), 'employee file')
[IO.File]::WriteAllText((Join-Path $target 'python/owned.exe'), 'synthetic executable fixture')
[IO.File]::WriteAllText((Join-Path $target '.endpoint-kit'), '{"product":"MCPGatewayEndpoint","files":["config.json","python/owned.exe"]}')
Remove-EndpointFiles $target
if (Test-Path -LiteralPath (Join-Path $target 'config.json')) { throw 'owned config remained' }
if (Test-Path -LiteralPath (Join-Path $target 'python/owned.exe')) { throw 'owned executable remained' }
if (-not (Test-Path -LiteralPath (Join-Path $target 'notes.txt'))) { throw 'employee file removed' }
if (-not (Test-Path -LiteralPath (Join-Path $target 'python/keep.txt'))) { throw 'employee runtime file removed' }
Write-Output 'PowerShell parser and boundaries OK'
'''
        process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                 capture_output=True, env=dict(os.environ, KIT_TEST_ROOT=str(ROOT), KIT_TEST_TEMP=str(self.root)), timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
