"""Temporary ACLs and extracted PowerShell functions; never install tasks or touch the real profile."""
import base64
import os
import re
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

    def test_launcher_hosts_tray_in_its_own_process_and_shortcut_is_ours_only(self):
        self.run_ps(r"""
Set-Content -LiteralPath (Join-Path $work 'tray.ps1') -Encoding UTF8 -Value @'
param([string]$SettingsPath, [switch]$Show)
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'ran.txt'), "$SettingsPath|$Show|$([Threading.Thread]::CurrentThread.ApartmentState)|$([Diagnostics.Process]::GetCurrentProcess().ProcessName)")
'@
$files = Install-EndpointLauncher $work
if (($files -join ',') -ne 'MCPGateway.exe,MCPGateway.ico') { throw "launcher not built: $files" }
$exe = Join-Path $work 'MCPGateway.exe'
Start-Process -FilePath $exe -ArgumentList '-SettingsPath "C:\dir with space\s.json" -Show' -Wait
$ran = Get-Content -LiteralPath (Join-Path $work 'ran.txt') -Raw
if ($ran -ne 'C:\dir with space\s.json|True|STA|MCPGateway') { throw "hosted run: $ran" }
Add-Type -AssemblyName System.Drawing
if ((Set-EndpointAppIdentity).Width -ne 32) { throw 'icon' }
$profile = Join-Path $work 'profile'
New-Item -ItemType Directory -Path $profile | Out-Null
$shell = New-Object -ComObject WScript.Shell
foreach ($case in @(@('ours.lnk', $exe, $false), @('other.lnk', $env:ComSpec, $true))) {
    $path = Join-Path $profile $case[0]
    $link = $shell.CreateShortcut($path); $link.TargetPath = $case[1]; $link.Save()
    [IO.File]::WriteAllText((Join-Path $work 'shortcut.txt'), $path)
    Remove-EndpointDesktopShortcut $work $profile $work
    if ((Test-Path -LiteralPath $path) -ne $case[2] -or (Test-Path -LiteralPath (Join-Path $work 'shortcut.txt'))) { throw "shortcut $($case[0])" }
}
""")

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

    def test_stopped_service_pipe_is_noticed_without_waiting_for_the_report_to_age(self):
        # pj3 실측: 서비스 작업이 없는데 마지막 보고 뒤 150초 동안 「연결됨」이 유지됐다.
        self.run_ps(r"""
Add-Type -AssemblyName System.Drawing
Import-TestFunction 'tray.ps1' 'Update-EndpointTray'
Import-TestFunction 'tray.ps1' 'Get-EndpointNext'
function T($key) { Get-EndpointText $key }
function Start-EndpointProbe { throw 'probe ran while the service is stopped' }
$user='Kit-Test-'+[Guid]::NewGuid().ToString('N')
if (-not (Test-EndpointServicePipe '')) { throw 'unknown account counted as stopped' }
if (Test-EndpointServicePipe $user) { throw 'missing pipe reported as running' }
$SettingsPath=Join-Path $work 'settings.json'
$settings=@{mode='managed';user=$user;status_path=(Join-Path $work 'status.json')}
$icon=[pscustomobject]@{Icon=$null;Text=''}
$simple=$false
$script:pipeGone=$null; $script:serviceMissing=$false; $script:probe=$null
[IO.File]::WriteAllText($SettingsPath,'{}')
function Publish($age,$state) {
    [IO.File]::WriteAllText($settings.status_path,(@{updated=([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()-$age);connected=$true;state=$state} | ConvertTo-Json))
}
# Before the first report the service may simply not have started: not a stopped service.
$script:pipeGone=[DateTime]::UtcNow.AddSeconds(-60)
Update-EndpointTray
if ($script:label -ne 'preparing') { throw 'first start shown as stopped' }
$script:pipeGone=$null
Publish 5 'active'
Update-EndpointTray
if ($script:label -ne 'connected' -or -not $script:pipeGone) { throw 'a restart gap must not flip the label at once' }
$script:pipeGone=[DateTime]::UtcNow.AddSeconds(-11)
Update-EndpointTray
if ($script:label -ne 'service_stopped') { throw 'stopped service still connected' }
if ($icon.Text -notmatch (Get-EndpointText 'service_stopped')) { throw 'tooltip lacks the stopped label' }
if ((Get-EndpointNext) -ne (Get-EndpointText 'next_service')) { throw 'stopped service offered the wrong step' }
$script:serviceMissing=$true
if ((Get-EndpointNext) -ne (Get-EndpointText 'next_removed')) { throw 'missing task did not point to the reinstall' }
Publish 1000 'active'
Update-EndpointTray
if ($script:label -ne 'service_stopped') { throw 'stale report hid the stopped service' }
foreach ($state in @('pending','quarantined','revoked')) {
    Publish 5 $state; Update-EndpointTray
    if ($script:label -ne 'service_stopped') { throw "state $state hid the stopped service" }
}
Publish 5 'removed'; Update-EndpointTray
if ($script:label -eq 'service_stopped') { throw 'removed state reported as stopped service' }
Publish 5 'active'
$pipe=New-Object IO.Pipes.NamedPipeServerStream('mcpgw-'+$user.ToLowerInvariant())
try {
    if (-not (Test-EndpointServicePipe $user)) { throw 'live pipe not seen' }
    $script:probe=[pscustomobject]@{connection=[pscustomobject]@{service='stopped'}}
    Update-EndpointTray
    if ($script:label -ne 'connected' -or $script:pipeGone -or $script:serviceMissing) { throw 'recovery not noticed' }
    if ($script:probe) { throw 'stopped-service check result kept after recovery' }
} finally { $pipe.Dispose() }
""")

    def test_stopped_service_has_its_own_check_cell_in_both_languages(self):
        self.run_ps(r"""
Import-TestFunction 'tray.ps1' 'Get-EndpointCells'
function T($key) { Get-EndpointText $key $script:lang }
$script:probe='{"servers":2,"model":{"harness":null,"ok":false,"detail":"하네스 없음"},"connection":{"initialized":[],"failed":{},"tools":0,"service":"stopped"}}' | ConvertFrom-Json
foreach ($lang in @('ko','en')) {
    $script:lang=$lang
    $cells=Get-EndpointCells
    if ($cells[1] -ne (Get-EndpointText 'service_stopped' $lang)) { throw "stopped cell missing in $lang" }
}
if ((Get-EndpointText 'service_stopped' 'ko') -eq (Get-EndpointText 'waiting' 'ko') -or
    (Get-EndpointText 'service_stopped' 'en') -eq (Get-EndpointText 'waiting' 'en')) { throw 'stopped looks like waiting' }
if ((Get-EndpointValue (Get-EndpointText 'service_stopped' 'ko') 'en') -ne (Get-EndpointText 'service_stopped' 'en')) { throw 'cached value not translated' }
""")

    def test_reconnect_asks_the_elevated_side_whether_the_service_task_exists(self):
        tray = (ROOT / "endpoint-agent/tray.ps1").read_text(encoding="utf-8-sig")
        reconnect = tray[tray.index("function Complete-EndpointReconnect"):tray.index("function Switch-EndpointLanguage")]
        # Only the elevated command can read the task of another principal, so it reports "missing" by exit code 3.
        self.assertIn("Get-ScheduledTask -TaskName '$task'", reconnect)
        self.assertIn("else { exit 3 }", reconnect)
        self.assertIn("-PassThru -Wait", reconnect)
        self.assertIn("$restart.ExitCode -eq 3) { $script:serviceMissing = $true }", reconnect)
        self.assertIn("-in @('disconnected', 'service_stopped')", reconnect)
        self.assertEqual(reconnect.count("RunAs"), 1)

    def test_progress_steps_never_repeat_a_label(self):
        # pj3 실측: 단계 목록에 「연결 등록」이 15%와 60%에 두 번 나왔다.
        worker = (ROOT / "endpoint-agent/windows-worker.ps1").read_text(encoding="utf-8-sig")
        labels = []
        for line in worker.splitlines():
            if "Set-EndpointResult" in line and "function Set-EndpointResult" not in line:
                labels += [item for item in re.findall(r"'([^']+)'", line) if item not in ("failed", "completed", "running")]
        self.assertGreater(len(labels), 10)
        self.assertEqual(sorted(set(label for label in labels if labels.count(label) > 1)), [])

    def test_empty_folders_are_removed_and_anything_with_content_is_kept(self):
        self.run_ps(r"""
Remove-EndpointEmptyDirectory (Join-Path $work 'missing')
$empty=Join-Path $work 'empty'; $full=Join-Path $work 'full'; $nested=Join-Path $work 'nested'
New-Item -ItemType Directory -Path $empty,$full,(Join-Path $nested 'inner') | Out-Null
[IO.File]::WriteAllText((Join-Path $full 'employee.txt'),'keep')
foreach ($path in @($empty,$full,$nested)) { Remove-EndpointEmptyDirectory $path }
if (Test-Path -LiteralPath $empty) { throw 'empty folder left behind' }
if (-not (Test-Path -LiteralPath (Join-Path $full 'employee.txt'))) { throw 'folder with a file removed' }
if (-not (Test-Path -LiteralPath (Join-Path $nested 'inner'))) { throw 'folder with a subfolder removed' }
Remove-EndpointEmptyDirectory (Join-Path $nested 'inner')
Remove-EndpointEmptyDirectory $nested
if (Test-Path -LiteralPath $nested) { throw 'emptied parent left behind' }
Remove-EndpointEmptyDirectory (Join-Path $full 'employee.txt')
if (-not (Test-Path -LiteralPath (Join-Path $full 'employee.txt'))) { throw 'a file was treated as a folder' }
""")

    def test_results_keep_only_the_newest_attempts_and_never_the_approval(self):
        self.run_ps(r"""
$results=Join-Path $work 'results'
New-Item -ItemType Directory -Path $results | Out-Null
$names=@()
foreach ($i in 0..12) {
    $name=[Guid]::NewGuid().ToString('N'); $names += $name
    $folder=Join-Path $results $name
    New-Item -ItemType Directory -Path $folder | Out-Null
    [IO.File]::WriteAllText((Join-Path $folder 'result.json'),'{}')
    (Get-Item -LiteralPath $folder).LastWriteTimeUtc=[DateTime]::UtcNow.AddHours(-$i)
}
$other=Join-Path $results 'not-an-attempt'
New-Item -ItemType Directory -Path $other | Out-Null
(Get-Item -LiteralPath $other).LastWriteTimeUtc=[DateTime]::UtcNow.AddDays(-30)
[IO.File]::WriteAllText((Join-Path $work 'approved-windows-kit.json'),'{}')
Remove-EndpointOldResults $results 9
$left=@(Get-ChildItem -LiteralPath $results -Directory | Where-Object { $_.Name -match '^[a-f0-9]{32}$' } | ForEach-Object Name)
if ($left.Count -ne 9) { throw "kept $($left.Count)" }
foreach ($name in $names[0..8]) { if ($name -notin $left) { throw 'a newer attempt was removed' } }
foreach ($name in $names[9..12]) { if ($name -in $left) { throw 'an older attempt was kept' } }
if (-not (Test-Path -LiteralPath $other)) { throw 'unrelated folder removed' }
if (-not (Test-Path -LiteralPath (Join-Path $work 'approved-windows-kit.json'))) { throw 'approval removed' }
""")
        trust = (ROOT / "endpoint-agent/windows-trust.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("try { Remove-EndpointOldResults $results 9 } catch { }", trust)
        self.assertLess(trust.index("New-EndpointProtectedDirectory $results"), trust.index("Remove-EndpointOldResults $results 9"))
        self.assertLess(trust.index("Remove-EndpointOldResults $results 9"), trust.index("New-EndpointProtectedDirectory $result $request.requester_sid"))

    def test_wizard_and_removal_leave_no_empty_folder_of_their_own(self):
        setup = (ROOT / "endpoint-agent/setup.ps1").read_text(encoding="utf-8-sig")
        finish = setup[setup.rindex("try { [void]$form.ShowDialog() } finally"):]
        self.assertIn("Remove-EndpointEmptyDirectory $work", finish)
        self.assertIn("if ($script:completed) { Remove-Item -LiteralPath (Join-Path $work 'setup.log')", finish)
        self.assertIn("if ($Remove -and $script:completed) { Remove-EndpointEmptyDirectory (Split-Path $work) }", finish)
        worker = (ROOT / "endpoint-agent/windows-worker.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Remove-EndpointEmptyDirectory (Split-Path $trayWork)", worker)


if __name__ == "__main__":
    unittest.main()
