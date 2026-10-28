"""Offline one-click checks. No elevation, profile, registry, firewall or real enrollment changes."""
import ast
import asyncio
import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]

# install() asks the status module for the first summary; the real one waits for a service that does not exist here.
INSTALL_STATUS = SimpleNamespace(screen_module=SimpleNamespace(wait_summary=lambda *a, **k: {'state': 'active'}, STATES={'active': '활성'}), publish=lambda *a: None)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OneclickTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix='.oneclick-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.builder = load('oneclick', 'full_stack_lab/gateway/app/windows_oneclick.py')
        self.managed = load('oneclick_managed', 'endpoint-agent/managed-windows.py')

    def test_single_file_roundtrip_and_cmd_length(self):
        bootstrap = (ROOT / 'endpoint-agent/windows-oneclick.ps1.in').read_text(encoding='utf-8')
        artifact = self.builder.launcher(b'synthetic ZIP', bootstrap).decode()
        command = artifact.splitlines()[3]
        self.assertLess(len(command), 8191)
        self.assertEqual(command.count('-Verb RunAs'), 1)
        self.assertNotIn('synthetic ZIP', command)
        payload = json.loads(base64.b64decode(artifact.split(':MCPGW_PAYLOAD\r\n')[1]))
        self.assertEqual(base64.b64decode(payload['archive']), b'synthetic ZIP')
        self.assertEqual(payload['bootstrap'], bootstrap)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell parser requires Windows')
    def test_result_box_frees_the_install_lock_and_stays_on_top(self):
        # pj3 실측: 상자가 상태 창 뒤에 숨은 채 설치 잠금을 쥐고 있어 다음 설치가 「다른 설치 작업이 진행 중」으로 막혔다.
        template = (ROOT / 'endpoint-agent/windows-oneclick.ps1.in').read_text(encoding='utf-8')
        lines = template.splitlines()
        calls = [i for i, line in enumerate(lines) if line.strip().startswith('Show-EndpointResult ')]
        self.assertEqual(len(calls), 2)
        for index in calls:
            self.assertIn('$mutex.ReleaseMutex(); $owns = $false', lines[index - 1])
        self.assertEqual(template.count('MessageBox]::Show('), 1)
        self.assertIn('TopMost = $true', template)

    def test_real_loader_passes_only_artifact_identity_to_one_mocked_uac(self):
        # Execute the generated loader but replace Start-Process: no UAC or child installer is launched.
        artifact = self.builder.launcher(b'synthetic ZIP', 'throw "must not run"')
        source = self.root / "employee's setup.cmd"
        source.write_bytes(artifact)
        captured = self.root / 'arguments.txt'
        command = artifact.decode().splitlines()[3].split(' -Command "', 1)[1][:-1]
        script = r'''
function Start-Process {
    param($FilePath, $ArgumentList, $Verb, $WindowStyle, [switch]$PassThru, [switch]$Wait)
    if ($Verb -ne 'RunAs') { throw 'missing elevation' }
    [IO.File]::WriteAllText($env:ONECLICK_CAPTURE, $ArgumentList)
    return [pscustomobject]@{ExitCode=0}
}
'''
        encoded = base64.b64encode((script + command).encode('utf-16le')).decode()
        done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                              capture_output=True, timeout=20,
                              env=dict(os.environ, MCPGW_SETUP_FILE=str(source), ONECLICK_CAPTURE=str(captured)))
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors='replace'))
        seed = base64.b64decode(captured.read_text().split('-EncodedCommand ')[1]).decode('utf-16le')
        self.assertNotIn('throw "must not run"', seed)
        self.assertIn("[IO.File]::Open($context.path,'Open','Read','Read')", seed)
        self.assertLess(seed.index('Installer changed'), seed.index('[scriptblock]::Create'))
        parse = self.root / 'loader.ps1'
        parse.write_text(seed, encoding='ascii')
        check = '$t=$null;$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($env:ONECLICK_PARSE,[ref]$t,[ref]$e);if($e){throw ($e|Out-String)}'
        done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', check], capture_output=True,
                              timeout=20, env=dict(os.environ, ONECLICK_PARSE=str(parse)))
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors='replace'))

    def test_standard_employee_gets_separate_standard_account_without_weakening_legacy(self):
        employee = {'sid': 'employee', 'profile': 'employee-profile', 'admin': False}
        companion = {'sid': 'companion', 'profile': None, 'admin': False}
        with mock.patch.object(self.managed, 'account', side_effect=[employee, companion]), \
                mock.patch.object(self.managed, 'powershell') as ps:
            self.assertEqual(self.managed.managed_user('employee', isolated=True), ('mcpgw-employee', companion, True))
            ps.assert_called_once_with(self.managed.CREATE_ACCOUNT, {'name': 'mcpgw-employee'})
        with mock.patch.object(self.managed, 'account', return_value=employee), mock.patch.object(self.managed, 'powershell') as ps:
            self.assertEqual(self.managed.managed_user('employee'), ('employee', employee, False))
            ps.assert_not_called()

    def test_one_click_installs_the_signed_in_account_unless_the_kit_asks_for_isolation(self):
        # D-239: the employee's own account by default; 「고급: 격리 계정」 puts "isolated": true in enrollment.json.
        template = (ROOT / 'endpoint-agent/windows-oneclick.ps1.in').read_text(encoding='utf-8')
        self.assertIn("isolated_account=$isolated", template)
        self.assertNotIn("isolated_account=$true", template)
        self.assertIn("ConvertFrom-Json).isolated -eq $true", template)
        worker = (ROOT / 'endpoint-agent/windows-worker.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn("throw '기존 엔드포인트 제거 후 재설치 필요'", worker)  # a reinstall rolls back instead
        # ...and the running service lets go of the runtime before it is replaced, then starts again (pj3 10-25).
        self.assertLess(worker.index("foreach ($name in $stoppedTasks) { Stop-ScheduledTask"), worker.index("Install-EndpointRuntime $PSScriptRoot $root"))
        self.assertIn("Start-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue", worker)
        self.assertIn("if ($isolated) { $managedArguments += '--isolated-account' }", worker)
        # A one-click approval can be updated by a newer one-click file; an IT approval (no marker) still needs IT.
        self.assertIn("$oneclickMark = Join-Path $paths.state 'approved-by-oneclick'", template)
        self.assertIn("if ($replace -and -not (Test-Path -LiteralPath $oneclickMark)) { throw 'IT must update the approved installer' }", template)

    @unittest.skipUnless(sys.version_info >= (3, 11), 'tomllib requires Python 3.11+; kit runtime is Python 3.13')
    def test_runtime_check_imports_only_what_the_embedded_python_has(self):
        # pj3 10-25: the D-232 fallbacks (tomli, toml) made every Windows install stop at 「실행 파일 준비」.
        check = load('runtime_check', 'endpoint-agent/runtime-check.py')
        modules = check.modules_of(ROOT / 'endpoint-agent')
        self.assertFalse({'toml', 'tomli', 'pwd', 'grp', 'fcntl'} & modules)
        self.assertIn('tomllib', modules)
        missing = [name for name in sorted(modules)  # the kit's own modules sit beside the script
                   if not (ROOT / 'endpoint-agent' / (name + '.py')).is_file() and importlib.util.find_spec(name) is None]
        self.assertEqual(missing, [], 'modules a standard CPython 3.12+ lacks')

    @unittest.skipUnless(os.name == 'nt', 'PowerShell required')
    def test_no_companion_to_retire_is_not_a_powershell_failure(self):
        # pj3 10-25: a PC that never had an isolated install aborted every simple install on this script.
        self.assertIsNone(self.managed.powershell(self.managed.REMOVE_COMPANION, {'name': 'mcpgw-no-such-account-s1'}))
        # Removing a simple-mode install: no firewall rule and (here) no task either is still a success.
        self.assertIsNone(self.managed.powershell(self.managed.STOP_SERVICE, {
            'name': 'MCPGatewayManaged-no-such-account-s1', 'rules': ['MCPGW-no-such-account-s1-egress']}))

    @unittest.skipUnless(os.name == 'nt', 'Windows version resources')
    def test_winget_harness_version_is_read_from_the_file_not_by_running_it(self):
        import shutil
        folder = self.root / 'profile/AppData/Local/Microsoft/WinGet/Packages/Anthropic.ClaudeCode_x'
        folder.mkdir(parents=True)
        notepad = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'notepad.exe'
        shutil.copyfile(notepad, folder / 'claude.exe')  # any PE with a version resource
        expected = self.managed.file_version(folder / 'claude.exe')
        self.assertRegex(expected, r'^\d+\.\d+\.\d+$')
        with mock.patch.object(self.managed.subprocess, 'run', side_effect=AssertionError('a harness was run')):
            self.assertEqual(self.managed.harness_versions(self.root / 'profile'), {'claude': expected})
        self.assertIsNone(self.managed.file_version(self.root / 'missing.exe'))

    def test_simple_mode_puts_its_codex_block_back_after_the_codex_app_rewrites_the_file(self):
        # pj3 10-25: the Codex app rewrote the employee's config.toml and the PC was quarantined for it.
        profile = self.root / 'profile'
        (profile / '.codex').mkdir(parents=True)
        block = '\n[mcp_servers.learn]\nurl = "https://gw.example/mcp/learn/"\n'
        path = profile / '.codex/config.toml'
        path.write_text(self.managed.with_codex_block('model = "x"\n', block), encoding='utf-8')
        config, policy = {'profile': str(profile)}, {'files': {self.managed.CODEX_BLOCK: block}}
        self.assertFalse(self.managed.restore_codex_block(config, policy))
        path.write_text(path.read_text(encoding='utf-8').replace('learn/"', 'learn/" # edited') +
                        '\n[plugins."pdf"]\nenabled = true\n', encoding='utf-8')
        self.assertTrue(self.managed.restore_codex_block(config, policy))
        text = path.read_text(encoding='utf-8')
        self.assertEqual(self.managed.codex_block(text), block)
        self.assertIn('[plugins."pdf"]', text)  # the app's own settings stay
        self.assertFalse(self.managed.restore_codex_block(config, policy))

    def test_admin_companion_is_rejected(self):
        with mock.patch.object(self.managed, 'account', side_effect=[{'admin': False}, {'admin': True}]), \
                mock.patch.object(self.managed, 'powershell'):
            with self.assertRaises(ValueError):
                self.managed.managed_user('employee', isolated=True)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell archive validation requires Windows')
    def test_archive_validation_rejects_tampering_and_extra_paths_before_any_installation(self):
        import hashlib
        tree = ast.parse((ROOT / 'full_stack_lab/gateway/app/agent_service.py').read_text(encoding='utf-8'))
        names = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
                                     and any(isinstance(t, ast.Name) and t.id == 'KIT_FILES' for t in n.targets)))['windows']
        files = {name: b'synthetic' for name in (*names, 'python.zip', 'windows-python.json', 'root.crt', 'root.sha256', 'mcpgw_pc.py')}
        files['windows-trust.ps1'] = (ROOT / 'endpoint-agent/windows-trust.ps1').read_bytes()
        manifest = {'schema': 1, 'gateway_url': 'https://gateway.example', 'tailscale_node_id': '',
                    'files': {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}
        files['windows-kit-manifest.json'] = json.dumps(manifest).encode()
        files['enrollment.json'] = b'{"enrollment_token":"synthetic"}'
        paths = []
        variants = [files, {**files, 'windows-worker.ps1': b'changed'}, {**files, 'python.zip': b'changed'},
                    {**files, '../escape': b'changed'}, {**files, 'extra.exe': b'changed'}]
        for index, variant in enumerate(variants):
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                for name, value in variant.items():
                    archive.writestr(name, value)
            path = self.root / f'archive-{index}.b64'
            path.write_bytes(base64.b64encode(output.getvalue()))
            paths.append(str(path))
        script = r'''
$ErrorActionPreference='Stop'; $t=$null; $e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:ONECLICK_TEMPLATE,[ref]$t,[ref]$e)
if ($e) {throw ($e|Out-String)}
$fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Read-EndpointOneclickArchive'},$false)
. ([scriptblock]::Create($fn.Extent.Text))
$paths=$env:ONECLICK_ARCHIVES|ConvertFrom-Json
for ($i=0; $i -lt $paths.Count; $i++) {
    $rejected=$false
    try { $files=Read-EndpointOneclickArchive ([IO.File]::ReadAllText($paths[$i])) } catch { $rejected=$true }
    if ($i -eq 0 -and ($rejected -or -not $files.ContainsKey('enrollment.json'))) {throw 'valid archive rejected'}
    if ($i -eq 0) {
        $trust=$ast.Find({param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot -and $n.Extent.Text -match 'windows-trust.ps1'},$true)
        . ([scriptblock]::Create($trust.Extent.Text))
        if (-not (Get-Command Get-EndpointApprovedKit)) {throw 'snapshot helper import failed'}
    }
    if ($i -gt 0 -and -not $rejected) {throw 'changed archive accepted'}
}
'''
        done = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                              timeout=30, env=dict(os.environ, ONECLICK_ARCHIVES=json.dumps(paths),
                                  ONECLICK_TEMPLATE=str(ROOT / 'endpoint-agent/windows-oneclick.ps1.in')))
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors='replace'))

    def test_profile_failure_does_not_return_a_ready_account(self):
        create = mock.Mock(return_value=-1)
        with mock.patch.object(self.managed.ctypes, 'WinDLL', return_value=SimpleNamespace(CreateProfile=create), create=True), \
                mock.patch.object(self.managed, 'account') as account:
            with self.assertRaisesRegex(ValueError, '프로필 생성 실패'):
                self.managed.prepare_profile('mcpgw-employee', {'sid': 'synthetic', 'profile': None})
            account.assert_not_called()

    def test_profile_created_and_existing_profile_is_reused_without_native_call(self):
        profile = self.root / 'profile'
        profile.mkdir()
        (profile / 'NTUSER.DAT').touch()
        ready = {'sid': 'synthetic', 'profile': str(profile)}
        create = mock.Mock(return_value=0)
        with mock.patch.object(self.managed.ctypes, 'WinDLL', return_value=SimpleNamespace(CreateProfile=create), create=True), \
                mock.patch.object(self.managed, 'account', return_value=ready):
            self.assertEqual(self.managed.prepare_profile('mcpgw-employee', {'sid': 'synthetic', 'profile': None}), ready)
            create.assert_called_once()
        with mock.patch.object(self.managed.ctypes, 'WinDLL', create=True) as native:
            self.assertEqual(self.managed.prepare_profile('mcpgw-employee', ready), ready)
            native.assert_not_called()

    def test_isolated_install_uses_employee_harness_and_companion_sid_and_still_blocks_live_companion(self):
        profile = self.root / 'companion'
        profile.mkdir()
        (profile / 'NTUSER.DAT').touch()
        person = {'profile': str(profile), 'sid': 'S-1-5-21-1-2-3-1002', 'admin': False}
        employee = {'profile': str(self.root / 'employee'), 'sid': 'S-1-5-21-1-2-3-1001', 'admin': False}
        enrollment = self.root / 'enrollment.json'
        enrollment.write_text(json.dumps({'gateway_url': 'https://gateway.example', 'tailscale_node_id': 'approved',
                                           'enrollment_token': 'synthetic'}))
        programs, state = self.root / 'programs', self.root / 'state'
        native = programs / 'harness'
        native.mkdir(parents=True)
        policy = {'tailscale_node_id': 'approved', 'gateway_ips': ['100.83.175.111'], 'gateway_port': 443,
                  'policy_hash': 'synthetic-policy', 'proxy_environment': {}, 'files': {'codex-config.toml': ''}}
        output = io.StringIO()
        with mock.patch.object(self.managed.ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)), create=True), \
                mock.patch.multiple(self.managed, PROGRAMS=programs, STATE=state, PROGRAM_DATA=self.root / 'data', FILES={}), \
                mock.patch.object(self.managed, 'verify_transport'), \
                mock.patch.object(self.managed, 'account', side_effect=lambda name: employee if name == 'employee' else person), \
                mock.patch.object(self.managed, 'managed_user', return_value=('mcpgw-employee', person, True)), \
                mock.patch.object(self.managed, 'prepare_profile', return_value=person), \
                mock.patch.object(self.managed, 'protected', return_value=True), \
                mock.patch.object(self.managed, 'lock_down', side_effect=lambda p, **kw: p.mkdir(parents=True, exist_ok=True)), \
                mock.patch.object(self.managed, 'powershell', return_value=0) as powershell, \
                mock.patch.object(self.managed, 'place_harnesses', return_value=(native, {'claude.exe': 'synthetic'})) as place, \
                mock.patch.object(self.managed, 'request', side_effect=[{'endpoint_id': 'synthetic-device'}, policy]) as request, \
                mock.patch.object(self.managed, 'apply_policy'), \
                mock.patch.object(self.managed, 'harness_launchers', return_value=(native, {})), \
                mock.patch.object(self.managed, 'rule_state', return_value={'rules': []}), \
                mock.patch.object(self.managed, 'set_user_environment'), mock.patch.dict(sys.modules, {'windows_status': INSTALL_STATUS}), mock.patch('sys.stdout', output):
            self.managed.install(SimpleNamespace(user='employee', enrollment=enrollment, isolated_account=True))
            place.assert_called_once_with(employee['profile'])
            self.assertEqual(powershell.call_args_list[0].args, (self.managed.OWNED_PROCESSES, {'sid': person['sid']}))
            config = json.loads((state / 'mcpgw-employee/config.json').read_text())
            self.assertEqual(config['sid'], person['sid'])
            self.assertFalse(enrollment.exists())
            self.assertIn('claude auth login', output.getvalue())
            self.assertIn('codex login --device-auth', output.getvalue())
            self.assertNotIn(config['device_key'], output.getvalue())
            request.reset_mock()
            enrollment.write_text('{"gateway_url":"https://gateway.example"}')
            powershell.return_value = 1
            with self.assertRaisesRegex(ValueError, '로그아웃'):
                self.managed.install(SimpleNamespace(user='employee', enrollment=enrollment, isolated_account=True))
            request.assert_not_called()

    def probe_connection(self, answer):
        status = self.root / 'status.json'
        status.write_text(json.dumps({'servers': ['learn'], 'state': 'pending'}), encoding='utf-8')
        settings = self.root / 'settings.json'
        settings.write_text(json.dumps({'status_path': str(status), 'gateway_url': 'https://gateway.invalid'}), encoding='utf-8')
        output = io.StringIO()
        with mock.patch.object(self.managed, 'read_broker', return_value=answer), mock.patch('sys.stdout', output):
            self.managed.probe(SimpleNamespace(settings=str(settings), skip_model=True))
        return json.loads(output.getvalue().strip().splitlines()[-1])['connection']

    def test_probe_tells_an_unreachable_service_from_one_waiting_for_activation(self):
        # pj3 실측: 서비스 작업이 없을 때 「연결 확인」이 「활성화 대기」로 보였다. 표시만 다르고 판정·헤더는 그대로다.
        stopped = self.probe_connection(None)
        self.assertEqual(stopped['service'], 'stopped')
        self.assertNotIn('waiting', stopped)
        waiting = self.probe_connection({'error': '엔드포인트 활성화·정책 연결이 필요합니다'})
        self.assertEqual(waiting['waiting'], 'pending')
        self.assertNotIn('service', waiting)
        self.assertNotIn('service', self.probe_connection({'Authorization': 'Bearer endpoint-not-active', 'extra': 1}))
        errors, output = io.StringIO(), io.StringIO()
        with mock.patch.object(self.managed, 'read_broker', return_value=None), mock.patch('sys.stdout', output), mock.patch('sys.stderr', errors):
            self.managed.header(SimpleNamespace())
        self.assertEqual(json.loads(output.getvalue()), {'Authorization': 'Bearer endpoint-not-active'})
        self.assertIn('관리형 연결 불가', errors.getvalue())

    def test_removal_prunes_only_empty_folders_the_kit_created(self):
        data, files = self.root / 'data', self.root / 'files'
        layout = {'managed-mcp.json': files / 'ClaudeCode' / 'managed-mcp.json',
                  'requirements.toml': data / 'OpenAI' / 'Codex' / 'requirements.toml'}
        patches = dict(FILES=layout, PROGRAM_DATA=data, STATE=data / 'MCPGatewayManaged')
        tray = data / 'MCPGatewayManagedTray'
        for folder in (layout['managed-mcp.json'].parent, layout['requirements.toml'].parent, tray, patches['STATE']):
            folder.mkdir(parents=True)
        with mock.patch.multiple(self.managed, **patches):
            self.managed.prune_empty_folders()
            for folder in (layout['managed-mcp.json'].parent, data / 'OpenAI', tray, patches['STATE']):
                self.assertFalse(folder.exists(), folder)
            self.assertTrue(data.is_dir())
            # Folders that still hold something (an organization's own file, another account's state) stay.
            for folder in (layout['managed-mcp.json'].parent, layout['requirements.toml'].parent, tray / 'S-1', patches['STATE'] / 'other'):
                folder.mkdir(parents=True)
            (layout['managed-mcp.json'].parent / 'organization.json').write_text('{}')
            (data / 'OpenAI' / 'Other').mkdir()
            self.managed.prune_empty_folders()
            self.assertTrue((layout['managed-mcp.json'].parent / 'organization.json').is_file())
            self.assertTrue((data / 'OpenAI' / 'Other').is_dir() and tray.is_dir() and (patches['STATE'] / 'other').is_dir())
            self.assertFalse(layout['requirements.toml'].parent.exists())
            events = []
            with mock.patch.object(self.managed, 'rollback', side_effect=lambda a: events.append('rollback')):
                with mock.patch.object(self.managed, 'prune_empty_folders', side_effect=lambda: events.append('prune')):
                    self.managed.uninstall(SimpleNamespace(user='employee'))
            self.assertEqual(events, ['rollback', 'prune'])

    def test_download_keeps_zip_default_and_mints_no_enrollment_for_missing_template(self):
        tree = ast.parse((ROOT / 'full_stack_lab/gateway/app/agent_service.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {'KIT_FILES', 'KIT_EXECUTABLE'} for t in n.targets)]
        route = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'download_managed_kit')
        route.decorator_list = []
        nodes.append(route)
        class Failure(Exception):
            pass
        enrollment = mock.AsyncMock(return_value={'enrollment_token': 'synthetic-private-enrollment'})
        namespace = dict(Path=Path, os=os, Literal=Literal, Request=SimpleNamespace, Header=lambda **kw: None, HTTPException=Failure,
                         current_identity=mock.AsyncMock(return_value={'user_id': 'synthetic', 'principal': 'synthetic'}),
                         field_ca=lambda: {'ca_certificate': 'synthetic-ca', 'ca_sha256': '0' * 64},
                         STATIC_DIR=self.root, io=io, zipfile=zipfile, hashlib=__import__('hashlib'),
                         urlsplit=__import__('urllib.parse', fromlist=['urlsplit']).urlsplit,
                         Response=lambda content, **kw: SimpleNamespace(content=content, **kw), __package__='oneclick_fixture')
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<existing-authenticated-route>', 'exec'), namespace)
        (self.root / 'kit').mkdir()
        (self.root / 'kit/mcpgw_pc.py').write_text('synthetic helper')
        source, runtime = self.root / 'source', self.root / 'runtime'
        source.mkdir(); runtime.mkdir()
        for name in namespace['KIT_FILES']['windows']:
            (source / name).write_text('synthetic')
        for name in ('python.zip', 'windows-python.json'):
            (runtime / name).write_text('synthetic')
        with mock.patch.dict(os.environ, ENDPOINT_KIT_DIR=str(source), WINDOWS_PYTHON_DIR=str(runtime), IDP_ISSUER='https://gateway.example'), \
                mock.patch.dict(sys.modules, {'oneclick_fixture': SimpleNamespace(),
                    'oneclick_fixture.endpoint_plane': SimpleNamespace(enrollment_token=enrollment),
                    'oneclick_fixture.windows_oneclick': self.builder}):
            with self.assertRaises(Failure):
                asyncio.run(namespace['download_managed_kit'](SimpleNamespace(headers={}), 'windows', authorization=None, packaging='oneclick'))
            enrollment.assert_not_awaited()
            (source / 'windows-oneclick.ps1.in').write_text('param($Context,$ArchiveBase64)')
            result = asyncio.run(namespace['download_managed_kit'](SimpleNamespace(headers={}), 'windows', authorization=None, packaging='oneclick'))
            self.assertEqual(result.media_type, 'application/octet-stream')
            self.assertIn('.cmd', result.headers['Content-Disposition'])
            self.assertEqual(result.headers['Cache-Control'], 'no-store')
            body = json.loads(base64.b64decode(result.content.decode().split(':MCPGW_PAYLOAD\r\n')[1]))
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(body['archive']))) as archive:
                kit = json.loads(archive.read('enrollment.json'))
                self.assertNotIn('enrollment_token', kit)
                self.assertNotIn('owner', kit)
                self.assertEqual(kit['gateway_url'], 'https://gateway.example')
            result = asyncio.run(namespace['download_managed_kit'](SimpleNamespace(headers={}), 'windows'))
            self.assertEqual(result.media_type, 'application/zip')
            enrollment.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
