"""Temporary ACLs and extracted PowerShell functions; never install tasks or touch the real profile."""
import base64
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell required")
class WindowsReinstall(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT, prefix=".winkit-ps-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_ps(self, script):
        prefix = r"""
$ErrorActionPreference='Stop'
$root=$env:WINKIT_ROOT
$work=$env:WINKIT_TEMP
. (Join-Path $root 'endpoint-agent/windows-common.ps1')
. (Join-Path $root 'endpoint-agent/windows-trust.ps1')
function Import-TestFunction($file, $name) {
    $t=$null; $e=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root ('endpoint-agent/' + $file)),[ref]$t,[ref]$e)
    if ($e) { throw ($e | Out-String) }
    $fn=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
    if (-not $fn) { throw 'missing function' }
    . ([scriptblock]::Create('function script:' + $fn.Name + $fn.Extent.Text.Substring(('function ' + $fn.Name).Length)))
}
"""
        encoded = base64.b64encode((prefix + script).encode("utf-16le")).decode()
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-EncodedCommand", encoded], capture_output=True, timeout=40,
                              env=dict(os.environ, WINKIT_ROOT=str(ROOT), WINKIT_TEMP=str(self.root), WINKIT_PYTHON=sys.executable))
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))

    def test_fresh_and_legacy_parent_allow_employee_without_opening_private_children(self):
        self.run_ps(r"""
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
foreach ($legacy in @($false,$true)) {
    $base=Join-Path $work ([Guid]::NewGuid().ToString('N'))
    $private=$null
    try {
    if ($legacy) {
        New-Item -ItemType Directory -Path $base | Out-Null
        $private=Join-Path $base 'private'
        New-Item -ItemType Directory -Path $private | Out-Null
        # Restricted test process cannot transfer ownership to Administrators. The DACL matches the old failure.
        $protected=New-EndpointAccessDescriptor '' $true
        $protected.SetOwner((New-Object Security.Principal.SecurityIdentifier($sid)))
        Set-Acl -LiteralPath $private -AclObject $protected
        $before=(Get-Acl -LiteralPath $private).Sddl
        Set-Acl -LiteralPath $base -AclObject $protected
    }
    Repair-EndpointWorkDirectory $base $sid
    $acl=Get-Acl -LiteralPath $base
    $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
    if (-not @($rules | Where-Object { $_.IdentityReference.Value -eq $sid -and
        ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Modify) -eq [Security.AccessControl.FileSystemRights]::Modify }).Count) {
        throw 'employee cannot modify tray parent'
    }
    $allowed=@('S-1-5-18','S-1-5-32-544',$sid)
    if (@($rules | Where-Object { $_.IdentityReference.Value -notin $allowed }).Count) { throw 'unrelated account admitted' }
    if ($legacy -and (Get-Acl -LiteralPath $private).Sddl -ne $before) { throw 'private child ACL changed' }
    New-Item -ItemType Directory -Path (Join-Path $base ('tray-' + $sid)) | Out-Null
    } finally {
        if (Test-Path -LiteralPath $base) { Repair-EndpointWorkDirectory $base $sid }
        if ($private -and (Test-Path -LiteralPath $private)) { Repair-EndpointWorkDirectory $private $sid }
    }
}
""")

    def test_child_stderr_is_saved_redacted_and_not_overwritten_by_result(self):
        child = self.root / "child.py"
        child.write_text('import sys\nprint("permission denied", file=sys.stderr)\n'
                         'print("PRIVATE-ONE-USE", file=sys.stderr)\n'
                         'print("PRIVATE-DEVICE", file=sys.stderr)\n'
                         'print("password=PRIVATE-PASSWORD", file=sys.stderr)\n'
                         'print("Authorization: Bearer PRIVATE-BEARER", file=sys.stderr)\nsys.exit(1)\n', encoding="utf-8")
        self.run_ps(r"""
Import-TestFunction 'windows-worker.ps1' 'Invoke-EndpointPython'
Import-TestFunction 'windows-worker.ps1' 'Set-EndpointResult'
$script:logPath=Join-Path $work 'setup.log'
$script:resultPath=Join-Path $work 'result.json'
$script:diagnosticSecrets=@('PRIVATE-ONE-USE')
$script:registration=Join-Path $work 'registration.json'
[IO.File]::WriteAllText($registration,'{"config":{"device_key":"PRIVATE-DEVICE"}}')
$script:history=New-Object Collections.Generic.List[string]
Set-EndpointResult 5 'start'
$failed=$false
try { Invoke-EndpointPython $env:WINKIT_PYTHON @((Join-Path $work 'child.py')) | Out-Null } catch { $failed=$true }
if (-not $failed) { throw 'child failure passed' }
Set-EndpointResult 0 'finish' 'failed' 'safe reason'
$log=[IO.File]::ReadAllText($logPath)
if ($log -notmatch 'permission denied' -or $log -notmatch 'safe reason') { throw 'diagnostic lost' }
if ($log -match 'PRIVATE-ONE-USE|PRIVATE-BEARER|PRIVATE-DEVICE|PRIVATE-PASSWORD') { throw 'credential leaked' }
$result=Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($result.state -ne 'failed' -or $result.detail -ne 'safe reason') { throw 'bad failure result' }
""")

    def test_removed_snapshot_or_settings_file_cannot_keep_connected_state(self):
        self.run_ps(r"""
Add-Type -AssemblyName System.Drawing
Import-TestFunction 'tray.ps1' 'Update-EndpointTray'
Import-TestFunction 'tray.ps1' 'Get-EndpointNext'
function T($key) { Get-EndpointText $key }
function Start-EndpointProbe { throw 'probe ran after removal' }
$SettingsPath=Join-Path $work 'settings.json'
$settings=@{status_path=(Join-Path $work 'status.json')}
$icon=[pscustomobject]@{Icon=$null;Text=''}
$simple=$true
[IO.File]::WriteAllText($SettingsPath,'{}')
[IO.File]::WriteAllText($settings.status_path,(@{updated=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds();connected=$false;state='removed';management='removed'} | ConvertTo-Json))
$script:probe=@{tools=40}
Update-EndpointTray
if ($script:label -ne 'disconnected' -or $script:probe) { throw 'removed state stayed connected' }
if ((Get-EndpointNext) -ne (Get-EndpointText 'next_removed')) { throw 'removed state offered reconnect' }
Remove-Item -LiteralPath $SettingsPath
$script:snapshot=@{state='active';connected=$true}
$script:probe=@{tools=40}
Update-EndpointTray
if ($script:snapshot -or $script:probe -or $script:label -ne 'disconnected') { throw 'stale state retained' }
""")

    def test_manifestless_removal_keeps_unowned_files(self):
        self.run_ps(r"""
$env:ProgramFiles=Join-Path $work 'programs'
$machine=Join-Path $env:ProgramFiles 'MCPGatewayManaged'
New-Item -ItemType Directory -Path $machine -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $machine 'agent.py'),'kit')
[IO.File]::WriteAllText((Join-Path $machine 'employee.txt'),'employee')
Remove-EndpointFiles $machine @('agent.py')
if (Test-Path -LiteralPath (Join-Path $machine 'agent.py')) { throw 'kit file left behind' }
if (-not (Test-Path -LiteralPath (Join-Path $machine 'employee.txt'))) { throw 'employee file removed' }
""")

    def test_activation_rechecks_cached_waiting_once_and_keeps_new_result(self):
        self.run_ps(r"""
Add-Type -AssemblyName System.Drawing
Import-TestFunction 'tray.ps1' 'Update-EndpointTray'
function T($key) { Get-EndpointText $key }
$script:starts=0
function Start-EndpointProbe { $script:starts++; $script:probeJob=@{running=$true} }
$SettingsPath=Join-Path $work 'settings.json'
$settings=@{status_path=(Join-Path $work 'status.json')}
$icon=[pscustomobject]@{Icon=$null;Text=''}
$simple=$true
[IO.File]::WriteAllText($SettingsPath,'{}')
$script:probe=@{connection=@{waiting='pending'}}
foreach ($state in @('pending','active','active')) {
    [IO.File]::WriteAllText($settings.status_path,(@{updated=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds();connected=$true;state=$state} | ConvertTo-Json))
    Update-EndpointTray
    if ($state -eq 'pending' -and ($script:starts -ne 0 -or -not $script:probe)) { throw 'pending started a check' }
}
if ($script:starts -ne 1 -or $script:probe) { throw 'cached waiting was retained or check duplicated' }
$script:probeJob=$null
$script:probe=@{connection=@{initialized=@('learn');tools=40}}
Update-EndpointTray
if ($script:starts -ne 1 -or $script:probe.connection.tools -ne 40) { throw 'fresh result was discarded' }
""")

    def test_language_switch_translates_existing_values_without_mutating_snapshot(self):
        self.run_ps(r"""
Import-TestFunction 'tray.ps1' 'Get-EndpointCells'
Import-TestFunction 'tray.ps1' 'Update-EndpointWindow'
function T($key) { Get-EndpointText $key $script:lang }
function Get-EndpointNext { T 'next_ready' }
$keys=@('connection','management','way','servers','harness','reported','model','tools','server','gateway','next')
$captions=@{};$values=@{}
foreach ($key in $keys) { $captions[$key]=[pscustomobject]@{Text=''}; $values[$key]=[pscustomobject]@{Text=''} }
$script:window=[pscustomobject]@{IsDisposed=$false;Text='';Tag=@{captions=$captions;values=$values;buttons=@()}}
$script:snapshot=@{state='active';management='활성';servers=@('docs-mcp-cloudflare-c-681a2b17');harnesses=@{claude='2.1.302'}}
$script:healthResult=Get-EndpointText 'gateway_ok' 'ko'
$script:probe=@{model=@{detail='하네스 없음'};connection=@{initialized=@();waiting='pending'}}
$script:label='connected'; $simple=$true; $script:updated='—'
foreach ($lang in @('en','ko','en')) {
    $script:lang=$lang
    Update-EndpointWindow
    if ($values.management.Text -ne (Get-EndpointText 'active' $lang)) { throw 'management language stale' }
    if ($values.gateway.Text -ne (Get-EndpointText 'gateway_ok' $lang)) { throw 'cached gateway language stale' }
    if ($values.model.Text -ne (Get-EndpointText 'no_harness_probe' $lang)) { throw 'model language stale' }
    if ($values.tools.Text -ne (Get-EndpointText 'waiting' $lang)) { throw 'tools language stale' }
    if ($values.servers.Text -ne '1 · docs-mcp-cloudflare-c-681a2b17') { throw 'server id guessed' }
}
if ($script:snapshot.management -ne '활성') { throw 'display translation mutated status' }
foreach ($state in @('active','pending','quarantined','revoked','removed','unknown')) {
    $script:snapshot.state=$state
    Update-EndpointWindow
    if ($values.management.Text -match '[가-힣]' -or $values.management.Text -ceq $state) { throw 'untranslated state' }
}
""")

    def test_registration_precedes_installed_mutations_and_one_failure_dialog(self):
        worker = (ROOT / "endpoint-agent/windows-worker.ps1").read_text(encoding="utf-8-sig")
        enroll = worker.index("Invoke-EndpointPython $stagePython $enrollArguments")
        for mutation in ("Set-EndpointAcl $root $sid", "foreach ($name in $stoppedTasks) { Stop-ScheduledTask",
                         "Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $root $name)"):
            self.assertLess(enroll, worker.index(mutation))
        template = (ROOT / "endpoint-agent/windows-oneclick.ps1.in").read_text(encoding="ascii")
        self.assertIn("Repair-EndpointWorkDirectory $workBase $Context.sid", template)
        self.assertIn("if ($process.ExitCode -ne 0 -or $result.state -ne 'completed') { exit 1 }", template)
        self.assertNotIn("throw 'Installation did not complete'", template)
        self.assertIn("Join-Path $trayWork 'show-status'", worker)
        cleanup = worker.index("foreach ($name in @('probe.json', 'probe.json.tmp', 'probe.err'))")
        self.assertLess(cleanup, worker.index("Join-Path $trayWork 'show-status'"))
        self.assertLess(cleanup, worker.index('Start-ScheduledTask -TaskName "MCPGatewayTray-$person"'))

    def test_remove_wizard_can_resolve_user_without_settings_json(self):
        self.run_ps(r"""
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$targetSid=$identity.User.Value
$env:ProgramData=Join-Path $work 'state'
$SettingsPath=Join-Path $env:ProgramData ('MCPGatewayManagedTray\' + $targetSid + '\settings.json')
$targetUser='wrong-user'
$directory='installation'
$Remove=$true
$t=$null;$e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'endpoint-agent/setup.ps1'),[ref]$t,[ref]$e)
$branch=@($ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.IfStatementAst] -and
    $_.Clauses[0].Item1.Extent.Text -eq '$Remove' })[0]
if (-not $branch) { throw 'missing removal preamble' }
. ([scriptblock]::Create($branch.Extent.Text))
if ($targetUser -ne $identity.Name.Split('\')[-1] -or $mode -ne 'managed') { throw 'missing settings picked wrong account' }
if ($directory -ne 'installation') { throw 'wrong removal directory' }
""")


if __name__ == "__main__":
    unittest.main()
