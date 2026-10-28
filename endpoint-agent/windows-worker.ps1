param([Parameter(Mandatory = $true)][string]$RequestPath, [string]$RequesterSid)
$ErrorActionPreference = 'Stop'
$administrator = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$approval = $null
$compilerTemp = $null

function Assert-EndpointBootstrapSeed([string]$CodeRoot, [string]$StateRoot) {
    $trusted = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    $approvalPath = Join-Path $StateRoot 'approved-windows-kit.json'
    $seed = @($CodeRoot, $StateRoot, $approvalPath, (Join-Path $CodeRoot 'windows-trust.ps1'), (Join-Path $CodeRoot 'windows-worker.ps1'))
    foreach ($path in $seed) {
        $cursor = [IO.Path]::GetFullPath($path)
        $direct = $true
        while ($cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '승인 설치 경로 연결 파일 거부' }
            $acl = Get-Acl -LiteralPath $cursor
            if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw '승인 설치 경로 소유자 확인 실패' }
            $mask = 0x40 -bor 0x10000 -bor 0x40000 -bor 0x80000 -bor 0x10000000
            if ($direct) { $mask = $mask -bor 0x2 -bor 0x4 -bor 0x10 -bor 0x100 -bor 0x40000000 }
            foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
                $inheritOnly = $rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly
                if (($direct -or -not $inheritOnly) -and $rule.AccessControlType -eq 'Allow' -and
                    $rule.IdentityReference.Value -notin $trusted -and ([long]$rule.FileSystemRights -band $mask)) {
                    throw '승인 설치 경로 쓰기 권한 거부'
                }
            }
            $parent = [IO.Directory]::GetParent($cursor)
            $cursor = if ($parent) { $parent.FullName } else { $null }
            $direct = $false
        }
    }
    $approved = Get-Content -LiteralPath $approvalPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($name in @('windows-trust.ps1', 'windows-worker.ps1')) {
        $expected = $approved.files.$name
        if ($expected -notmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath (Join-Path $CodeRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw '조직 승인 설치 파일 무결성 확인 실패'
        }
    }
}

if ($administrator) {
    $expectedRoot = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'MCPGatewayInstaller'
    if ([IO.Path]::GetFullPath($PSScriptRoot) -ne $expectedRoot) { throw '조직 승인 설치기 경로 필요' }
    $env:SystemRoot = [Environment]::GetFolderPath('Windows')
    $env:ProgramFiles = [Environment]::GetFolderPath('ProgramFiles')
    $env:ProgramData = [Environment]::GetFolderPath('CommonApplicationData')
    $env:PSModulePath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules'
    $env:PATH = (Join-Path $env:SystemRoot 'System32') + ';' + (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0')
    Set-Location -LiteralPath (Join-Path $env:SystemRoot 'System32')
    # The helper cannot authenticate itself before it has been loaded.
    Assert-EndpointBootstrapSeed $expectedRoot (Join-Path $env:ProgramData 'MCPGatewayInstaller')
    Set-Location -LiteralPath $expectedRoot
    . (Join-Path $expectedRoot 'windows-trust.ps1')
    $approval = Get-EndpointApprovedKit
    $paths = Get-EndpointInstallerPaths
    $compilerTemp = Join-Path $paths.state ('temp-' + [Guid]::NewGuid().ToString('N'))
    try {
        New-EndpointProtectedDirectory $compilerTemp
        $env:TEMP = $compilerTemp
        $env:TMP = $compilerTemp
        $tailscale = Join-Path $env:ProgramFiles 'Tailscale'
        if (Test-Path -LiteralPath $tailscale) { Assert-EndpointProtectedPath $tailscale; $env:PATH += ';' + $tailscale }
        . (Join-Path $expectedRoot 'windows-common.ps1')
        $request = Read-EndpointManagedRequest $RequestPath $approval $RequesterSid
        $resultDirectory = $request.result_directory
    } catch {
        Remove-EndpointCompilerTemp $compilerTemp
        throw '조직 승인 설치 요청 확인 실패'
    }
} else {
    $request = Get-Content -LiteralPath $RequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $resultDirectory = Split-Path $RequestPath
}
. (Join-Path $PSScriptRoot 'windows-common.ps1')
$resultPath = Join-Path $resultDirectory 'result.json'
$logPath = Join-Path $resultDirectory 'setup.log'
$history = New-Object Collections.Generic.List[string]
$stage = '준비'
$installMutex = $null
$ownsMutex = $false
$stoppedTasks = @()
$diagnosticSecrets = @()
if ($request.enrollment -and (Test-Path -LiteralPath $request.enrollment)) {
    $bundle = Get-Content -LiteralPath $request.enrollment -Raw -Encoding UTF8 | ConvertFrom-Json
    $diagnosticSecrets += $bundle.enrollment_token
}

function Set-EndpointResult([int]$Percent, [string]$Label, [string]$State = 'running', [string]$Detail = '') {
    $script:stage = $Label
    if ($State -ne 'failed') { $script:history.Add($Label) }
    $result = @{ percent = $Percent; stage = $Label; state = $State; detail = $Detail; steps = @($script:history.ToArray()); log = $logPath }
    if ($script:settingsPath) { $result.settings = $script:settingsPath }
    if ($script:detailAccount) { $result.account = $script:detailAccount }
    $text = $result | ConvertTo-Json -Depth 5
    [IO.File]::AppendAllText($logPath, $text + "`r`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($resultPath + '.tmp', $text, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath ($resultPath + '.tmp') -Destination $resultPath -Force
}

function Invoke-EndpointPython([string]$Python, [string[]]$Arguments) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Python
    $info.Arguments = '-X utf8 -B -I -S ' + (($Arguments | ForEach-Object { Quote-EndpointArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::Start($info)
    try {
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $timedOut = -not $process.WaitForExit(180000)
        if ($timedOut) { $process.Kill(); $process.WaitForExit() }
        $output = $stdout.Result
        $errorText = $stderr.Result
        if ($script:registration -and (Test-Path -LiteralPath $script:registration)) {
            $receipt = Get-Content -LiteralPath $script:registration -Raw -Encoding UTF8 | ConvertFrom-Json
            $script:diagnosticSecrets += $receipt.config.device_key
        }
        if ($errorText) {
            [IO.File]::AppendAllText($logPath, (Protect-EndpointDiagnostic $errorText $script:diagnosticSecrets) + "`r`n", [Text.UTF8Encoding]::new($false))
        }
        if ($timedOut) { throw '엔드포인트 처리 시간 초과' }
        if ($process.ExitCode -ne 0) {
            # Raw diagnostic text stays out of the UI.
            if ($errorText -match '이미 연결되어 있습니다') { throw '이미 연결되어 있습니다' }
            if ($errorText -match '직원 설정의 관리 구간') { throw '직원 설정의 관리 구간 확인 필요' }
            if ($errorText -match '([A-Za-z0-9_][A-Za-z0-9._-]{0,31}) 계정') { $script:detailAccount = $Matches[1] }
            if ($errorText -match '한 번 로그인|프로필') { throw '대상 계정 첫 로그인 후 로그아웃 필요' }
            if ($errorText -match '설치 키트와 정책|노드') { throw '설치 파일과 게이트웨이 불일치 · 콘솔에서 새 설치 파일 받기' }
            if ($errorText -match '로그아웃') { throw '대상 계정 로그아웃 필요' }
            if ($errorText -match '공식 Codex|Claude 설치|동반|릴리스') { throw '승인된 하네스 설치 확인 필요' }
            if ($errorText -match '401|403|409|410|enrollment') { throw '등록 자격 확인 필요 · 새 키트로 다시 시도' }
            if ($errorText -match 'CERTIFICATE_VERIFY_FAILED|certificate verify') { throw '게이트웨이 인증서 확인 실패' }
            if ($errorText -match 'timed out|timeout|시간 초과') { throw '게이트웨이 연결 시간 초과' }
            if ($errorText -match 'urlopen error|URLError|WinError 100') { throw '게이트웨이 이름 또는 포트 연결 실패' }
            if ($errorText -match 'ACL|보호된|권한|PermissionError|Access.*denied|액세스') { throw '설치 폴더 또는 계정 권한 확인 필요' }
            throw '엔드포인트 처리 실패 · 게이트웨이 연결 또는 등록 자격 확인 필요'
        }
        return $output
    } finally { $process.Dispose() }
}

try {
    Set-EndpointResult 5 '준비'
    if ($request.action -eq 'health') {
        Test-EndpointGateway $request.gateway_url $request.ca_certificate $request.ca_sha256
        Set-EndpointResult 100 '게이트웨이 연결 확인' 'completed'
        exit 0
    }
    $managed = $request.mode -eq 'managed'
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($managed -and -not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw '관리자 권한 필요'
    }
    if ($managed) {
        $root = Join-Path $env:ProgramFiles 'MCPGatewayManaged'
        if ($request.user -notmatch '^[A-Za-z0-9_][A-Za-z0-9._-]{0,31}$') { throw '대상 계정 이름 확인 필요' }
    } else {
        $root = [IO.Path]::GetFullPath($request.directory).TrimEnd('\')
        $local = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\') + '\'
        if (-not $root.StartsWith($local, [StringComparison]::OrdinalIgnoreCase)) { throw '사용자 설치 위치 확인 필요' }
    }
    $installMutex = New-Object Threading.Mutex($false, 'Global\MCPGatewayWindowsKit')
    try { $ownsMutex = $installMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { throw '다른 설치 작업 진행 중' }
    Assert-EndpointTree $root
    $codeFiles = @('agent.py', 'managed-windows.py', 'os-observer-windows.py', 'offline_buffer.py', 'windows_status.py', 'kit_screen.py', 'kit_access.py', 'install.py',
        'runtime-check.py', 'setup.ps1', 'tray.ps1', 'windows-common.ps1', 'windows-worker.ps1', 'windows-trust.ps1')
    if ($managed) {
        # Registration and removal work even if the old runtime is missing; nothing installed is touched here.
        $stageRoot = Join-Path $compilerTemp 'kit'
        New-EndpointProtectedDirectory $stageRoot
        $stagePython = Install-EndpointRuntime $PSScriptRoot $stageRoot
        foreach ($name in $codeFiles) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $stageRoot $name) }
        Assert-EndpointFileHashes $stageRoot $approval $codeFiles
        Assert-EndpointInstalledRuntime $stageRoot
        Invoke-EndpointPython $stagePython @((Join-Path $stageRoot 'runtime-check.py')) | Out-Null
    }
    if ($request.action -eq 'remove') {
        Set-EndpointResult 20 '엔드포인트 종료'
        if ($managed) {
            $person = (New-Object Security.Principal.NTAccount($request.user)).Translate([Security.Principal.SecurityIdentifier]).Value
            $trayDirectory = Join-Path $env:ProgramData ("MCPGatewayManagedTray\" + $person)
            if ([IO.Path]::GetFullPath($request.settings) -ne (Join-Path $trayDirectory 'settings.json')) { throw '제거 설정 경로 거부' }
            $settings = @{ sid = $person }
            if (Test-Path -LiteralPath $request.settings) {
                Assert-EndpointProtectedPath $request.settings
            }
            Invoke-EndpointPython $stagePython @((Join-Path $stageRoot 'managed-windows.py'), 'rollback', '--user', $request.user) | Out-Null
        } else {
            $settings = Get-Content -LiteralPath $request.settings -Raw -Encoding UTF8 | ConvertFrom-Json
            Stop-EndpointTask ("MCPGatewayEndpoint-" + $settings.endpoint_id)
        }
        Stop-EndpointTask ("MCPGatewayTray-" + $settings.sid)
        $profile = (Get-ItemProperty -LiteralPath ("HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\" + $settings.sid)).ProfileImagePath
        $trayWork = [IO.Path]::GetFullPath((Join-Path $profile ("AppData\Local\MCPGatewaySetup\tray-" + $settings.sid)))
        $profileRoot = [IO.Path]::GetFullPath($profile).TrimEnd('\') + '\'
        if (-not $trayWork.StartsWith($profileRoot, [StringComparison]::OrdinalIgnoreCase)) { throw '제거 경로 확인 실패' }
        Assert-EndpointTree $trayWork
        foreach ($name in @('request.json', 'result.json', 'result.json.tmp', 'setup.log', 'lang.txt', 'probe.json', 'probe.json.tmp', 'probe.err', 'show-status')) {
            $item = Join-Path $trayWork $name
            if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Force }
        }
        Remove-EndpointEmptyDirectory $trayWork
        Remove-EndpointEmptyDirectory (Split-Path $trayWork)
        Set-EndpointResult 65 '설정 제거'
        if ($managed) {
            foreach ($name in @('settings.json', 'status.json', 'status.tmp')) {
                $item = Join-Path $trayDirectory $name
                if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Force }
            }
            if ((Test-Path -LiteralPath $trayDirectory) -and -not (Get-ChildItem -LiteralPath $trayDirectory -Force)) { Remove-Item -LiteralPath $trayDirectory }
            $stateRoot = Join-Path $env:ProgramData 'MCPGatewayManaged'
            if (-not (Get-ChildItem -LiteralPath $stateRoot -Filter 'config.json' -Recurse -ErrorAction SilentlyContinue)) {
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                $archive = [IO.Compression.ZipFile]::OpenRead((Join-Path $PSScriptRoot 'python.zip'))
                try { $ownedFiles = $codeFiles + @($archive.Entries | ForEach-Object { 'python\' + $_.FullName }) }
                finally { $archive.Dispose() }
                $ownedFiles += @('config.json', 'status.json', 'status.tmp', 'tray-settings.json',
                    'harness\codex.exe', 'harness\codex-code-mode-host.exe', 'harness\claude.exe')
                Remove-EndpointFiles $root $ownedFiles
            }
        } else {
            Remove-Item -LiteralPath $request.settings -Force
            Remove-EndpointFiles $root
        }
        Set-EndpointResult 100 '제거 완료' 'completed'
        exit 0
    }
    if ((Test-Path -LiteralPath $root) -and (Get-ChildItem -LiteralPath $root -Force) -and
        -not (Test-Path -LiteralPath (Join-Path $root '.endpoint-kit'))) { throw '다른 파일이 없는 설치 위치 필요' }
    Test-EndpointGateway $request.gateway_url $request.ca_certificate $request.ca_sha256
    if ($managed) {
        $isolated = $request.isolated_account -eq $true
        Set-EndpointResult 15 '게이트웨이 등록'
        $registration = Join-Path $compilerTemp 'registration.json'
        $enrollArguments = @((Join-Path $stageRoot 'managed-windows.py'), 'enroll', '--user', $request.user,
            '--enrollment', $request.enrollment, '--registration', $registration)
        if ($isolated) { $enrollArguments += '--isolated-account' }
        Invoke-EndpointPython $stagePython $enrollArguments | Out-Null
    }
    Set-EndpointResult 15 '설치 위치 확인'
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    Set-EndpointAcl $root $sid -Managed:$managed
    # The managed path has already enrolled without changing the previous installation.
    if (-not $managed) { Stop-EndpointTask ("MCPGatewayEndpoint-" + $request.endpoint_id) }
    Set-EndpointResult 30 '실행 파일 준비'
    $reuseRuntime = $false
    if ($managed -and (Test-Path -LiteralPath (Join-Path $root 'python'))) {
        try { Assert-EndpointInstalledRuntime $root; $reuseRuntime = $true } catch { }
    }
    if ($managed -and -not $reuseRuntime) {
        # The runtime is replaced in place: a running service or helper keeps its files open, and the half-extracted
        # runtime then had no python.exe (pj3 10-25). Stop them first; finally starts them again.
        $stoppedTasks = @(Get-ScheduledTask -TaskName 'MCPGatewayManaged-*' -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq 'Running' } | ForEach-Object { $_.TaskName })
        foreach ($name in $stoppedTasks) { Stop-ScheduledTask -TaskName $name }
        $runtime = (Join-Path $root 'python') + '\'
        Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($runtime, [StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    $python = if ($reuseRuntime) { Join-Path $root 'python\python.exe' } else { Install-EndpointRuntime $PSScriptRoot $root }
    foreach ($name in $codeFiles) {
        if ((Join-Path $PSScriptRoot $name) -ne (Join-Path $root $name)) {
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $root $name) -Force
        }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead((Join-Path $PSScriptRoot 'python.zip'))
    try { $runtimeFiles = @($archive.Entries | ForEach-Object { 'python\' + $_.FullName }) } finally { $archive.Dispose() }
    $owned = @{ product = 'MCPGatewayEndpoint'; files = @($codeFiles) + $runtimeFiles + @('config.json', 'status.json', 'status.tmp', 'tray-settings.json') }
    $manifestPath = Join-Path $root '.endpoint-kit'
    [IO.File]::WriteAllText($manifestPath, ($owned | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    Set-EndpointAcl $root $sid -Managed:$managed
    if ($managed) { Assert-EndpointFileHashes $root $approval $codeFiles }
    if ($managed) { Assert-EndpointInstalledRuntime $root }
    Invoke-EndpointPython $python @((Join-Path $root 'runtime-check.py')) | Out-Null
    Set-EndpointResult 50 '실행 파일 점검'
    if ($managed) {
        $isolated = $request.isolated_account -eq $true
        Set-EndpointResult 60 $(if ($isolated) { '격리 계정 준비 · 등록' } else { '연결 등록' })
        $managedArguments = @((Join-Path $root 'managed-windows.py'), 'install', '--user', $request.user,
            '--enrollment', $request.enrollment, '--registration', $registration)
        if ($isolated) { $managedArguments += '--isolated-account' }
        $text = Invoke-EndpointPython $python $managedArguments
        $summary = ($text -split "`n" | Where-Object { $_.StartsWith('{') } | Select-Object -Last 1) | ConvertFrom-Json
        $user = $summary.managed_account
        $person = (New-Object Security.Principal.NTAccount($user)).Translate([Security.Principal.SecurityIdentifier]).Value
        $trayDirectory = Join-Path $env:ProgramData ("MCPGatewayManagedTray\" + $person)
        Assert-EndpointProtectedPath $trayDirectory
        $script:settingsPath = Join-Path $trayDirectory 'settings.json'
        $statusPath = Join-Path $trayDirectory 'status.json'
        $owned.files += @($summary.harnesses.PSObject.Properties.Name | ForEach-Object { 'harness\' + $_ })
        $owned.files += @($summary.launcher_files.PSObject.Properties.Name)
    } else {
        Set-EndpointResult 60 '엔드포인트 등록'
        $arguments = @((Join-Path $root 'install.py'), '--gateway-url', $request.gateway_url, '--endpoint-id', $request.endpoint_id,
            '--no-verify', '--windows-wrapper', '--install-dir', $root, '--key-file', $request.key_file)
        foreach ($path in $request.scan_paths) { $arguments += @('--scan-path', $path) }
        if ($request.tailscale_node_id) { $arguments += @('--tailscale-node-id', $request.tailscale_node_id) }
        if ($request.ca_certificate) {
            [IO.File]::WriteAllText((Join-Path $root 'root.crt'), $request.ca_certificate, [Text.UTF8Encoding]::new($false))
            $owned.files += 'root.crt'
            $arguments += @('--ca', (Join-Path $root 'root.crt'), '--ca-sha256', $request.ca_sha256)
        }
        Invoke-EndpointPython $python $arguments | Out-Null
        $statusPath = Join-Path $root 'status.json'
        $configPath = Join-Path $root 'config.json'
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $config | Add-Member -NotePropertyName ENDPOINT_TRAY_STATUS -NotePropertyValue $statusPath -Force
        [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
        Invoke-EndpointPython $python @((Join-Path $root 'agent.py'), '--config', $configPath, '--once') | Out-Null
        $action = New-ScheduledTaskAction -Execute (Join-Path $root 'python\pythonw.exe') -Argument ('-B -I -S ' +
            (Quote-EndpointArgument (Join-Path $root 'agent.py')) + ' --config ' + (Quote-EndpointArgument $configPath))
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $sid
        $principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
        $taskSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
        Register-ScheduledTask -TaskName ("MCPGatewayEndpoint-" + $request.endpoint_id) -Action $action -Trigger $trigger -Principal $principal -Settings $taskSettings -Force | Out-Null
        Start-ScheduledTask -TaskName ("MCPGatewayEndpoint-" + $request.endpoint_id)
        $person = $sid
        $user = $env:USERNAME
        $script:settingsPath = Join-Path $root 'tray-settings.json'
    }
    Set-EndpointResult 85 '로그온 시작 등록'
    $settings = @{ mode = $request.mode; directory = $root; gateway_url = $request.gateway_url; user = $user;
        ca_certificate = $request.ca_certificate; ca_sha256 = $request.ca_sha256;
        sid = $person; status_path = $statusPath; endpoint_id = $request.endpoint_id;
        connection = $(if ($managed -and -not $isolated) { 'simple' } elseif ($managed) { 'isolated' } else { 'observer' }) }
    [IO.File]::WriteAllText($script:settingsPath, ($settings | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($manifestPath, ($owned | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    Set-EndpointAcl $root $sid -Managed:$managed
    Stop-EndpointTask ("MCPGatewayTray-" + $person)
    Register-EndpointTray $script:settingsPath $person $root
    $profile = (Get-ItemProperty -LiteralPath ('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $person)).ProfileImagePath
    $trayWork = Join-Path $profile ('AppData\Local\MCPGatewaySetup\tray-' + $person)
    Assert-EndpointTree $trayWork
    New-Item -ItemType Directory -Path $trayWork -Force | Out-Null
    # Repair both the legacy protected parent and the tray child, leaving private install folders protected.
    $workBase = Split-Path $trayWork
    if ($managed) { Repair-EndpointWorkDirectory $workBase $person }
    Set-EndpointAcl $trayWork $person
    foreach ($name in @('probe.json', 'probe.json.tmp', 'probe.err')) {
        Remove-Item -LiteralPath (Join-Path $trayWork $name) -Force -ErrorAction SilentlyContinue
    }
    [IO.File]::WriteAllText((Join-Path $trayWork 'show-status'), '', [Text.Encoding]::ASCII)
    # Simple mode: the employee is signed in now, so the tray starts in their session at once (also when UAC ran as
    # another administrator). A companion account has no session until it signs in.
    if ($person -eq $sid -or ($managed -and -not $isolated)) { Start-ScheduledTask -TaskName "MCPGatewayTray-$person" }
    $management = '확인 필요'
    if ($managed) {
        $management = @{ active='활성'; pending='활성화 대기'; quarantined='격리됨'; revoked='철회됨' }[$summary.state]
        if (-not $management) { $management = '확인 필요' }
    }
    Set-EndpointResult 100 '설치 완료' 'completed' $(if ($managed -and -not $isolated) {
        "연결 상태`t$management`r`n지금 계정 그대로 사용`r`n연결 확인`t트레이 아이콘 > 연결 확인`r`n모델 로그인`t트레이 아이콘 > 모델 로그인"
    } elseif ($managed) {
        "연결 상태`t$management`r`n관리 계정`t$user`r`n모델 로그인`t관리 계정에서 실행`r`nClaude`tclaude auth login`r`nCodex`tcodex login --device-auth"
    } else { '트레이 실행' })
} catch {
    $known = @('경로 형식 오류', '설치 폴더 권한 적용 실패', '설치 경로 연결 파일 확인 필요', '게이트웨이 주소 형식 오류',
        '암호화 연결 또는 승인된 사내망 주소 필요', '게이트웨이 연결 시간 초과', '게이트웨이 이름 또는 포트 연결 실패',
        '게이트웨이 상태 응답 오류', '게이트웨이 준비 상태 확인 필요', '게이트웨이 인증서 확인 실패', '게이트웨이 상태 조회 실패',
        '실행 파일 판본 확인 실패', '실행 파일 무결성 확인 실패', '엔드포인트 종료 시간 초과', '제거 경로 확인 실패',
        '설치 소유 정보 확인 실패', '엔드포인트 처리 시간 초과', '대상 계정 로그아웃 필요', '대상 계정 첫 로그인 후 로그아웃 필요',
        '승인된 하네스 설치 확인 필요', '등록 자격 확인 필요 · 새 키트로 다시 시도', '설치 폴더 또는 계정 권한 확인 필요',
        '엔드포인트 처리 실패 · 게이트웨이 연결 또는 등록 자격 확인 필요', '관리자 권한 필요', '대상 계정 이름 확인 필요',
        '사용자 설치 위치 확인 필요', '다른 파일이 없는 설치 위치 필요', '기존 엔드포인트 제거 후 재설치 필요', '다른 설치 작업 진행 중',
        '설치 파일과 게이트웨이 불일치 · 콘솔에서 새 설치 파일 받기', '이미 연결되어 있습니다', '직원 설정의 관리 구간 확인 필요')
    $reason = $_.Exception.Message
    if ($reason -notin $known) { $reason = '파일 접근 또는 예약 작업 권한 확인 필요' }
    Set-EndpointResult 0 $stage 'failed' $reason
    exit 1
} finally {
    foreach ($name in $stoppedTasks) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { Start-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue }
    }
    if ($ownsMutex) { $installMutex.ReleaseMutex() }
    if ($installMutex) { $installMutex.Dispose() }
    if ($administrator -and $request.private_directory) {
        foreach ($name in @('request.json', 'enrollment.json')) {
            $item = Join-Path $request.private_directory $name
            if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Force }
        }
        if (-not (Get-ChildItem -LiteralPath $request.private_directory -Force)) { Remove-Item -LiteralPath $request.private_directory }
    }
    if ($compilerTemp) {
        Remove-EndpointCompilerTemp $compilerTemp
    }
}
