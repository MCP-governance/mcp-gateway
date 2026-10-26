param(
    [switch]$Observer,
    [switch]$Remove,
    [string]$SettingsPath,
    [string]$GatewayUrl,
    [string]$EndpointId,
    [string[]]$ScanPath,
    [string]$KeyFile,
    [string]$TailscaleNodeId
)
. (Join-Path $PSScriptRoot 'windows-common.ps1')
. (Join-Path $PSScriptRoot 'windows-trust.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$mode = if ($Observer) { 'observer' } else { 'managed' }
$directory = if ($Observer) { Join-Path $env:LOCALAPPDATA 'MCPGatewayEndpoint' } else { Join-Path $env:ProgramFiles 'MCPGatewayManaged' }
$targetUser = $env:USERNAME
if ($Remove) {
    $installed = if ($SettingsPath -and (Test-Path -LiteralPath $SettingsPath)) {
        Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        if ($SettingsPath) {
            $targetSid = Split-Path (Split-Path $SettingsPath) -Leaf
            $expected = Join-Path $env:ProgramData ('MCPGatewayManagedTray\' + $targetSid + '\settings.json')
            if ($targetSid -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$' -or [IO.Path]::GetFullPath($SettingsPath) -ne $expected) {
                throw '제거 설정 경로 확인 필요'
            }
            $targetUser = (New-Object Security.Principal.SecurityIdentifier($targetSid)).Translate([Security.Principal.NTAccount]).Value.Split('\')[-1]
        }
        @{ mode = 'managed'; directory = $directory; user = $targetUser; gateway_url = '' }
    }
    $mode = $installed.mode
    $directory = $installed.directory
    $GatewayUrl = $installed.gateway_url
    $targetUser = $installed.user
    if (-not $SettingsPath) {
        $SettingsPath = Join-Path $env:ProgramData ('MCPGatewayManagedTray\' + $identity.User.Value + '\settings.json')
    }
} elseif (-not $Observer) {
    try {
        $bundle = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'enrollment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $GatewayUrl = $bundle.gateway_url
    } catch { $GatewayUrl = '' }
}
$work = Join-Path $env:LOCALAPPDATA ('MCPGatewaySetup\' + [Guid]::NewGuid().ToString('N'))
try { New-Item -ItemType Directory -Path $work -Force | Out-Null } catch [UnauthorizedAccessException] {
    # The legacy bootstrap could deny even the removal wizard its request folder. Use only the approved wizard for UAC.
    if (-not $Remove -or ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw }
    $null = Get-EndpointApprovedKit
    $approvedSetup = Join-Path (Get-EndpointInstallerPaths).code 'setup.ps1'
    $arguments = '-NoProfile -STA -WindowStyle Hidden -File ' + (Quote-EndpointArgument $approvedSetup) +
        ' -Remove -SettingsPath ' + (Quote-EndpointArgument $SettingsPath)
    Start-Process -FilePath $script:PowerShellExe -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden | Out-Null
    return
}
Set-EndpointAcl $work $identity.User.Value
$script:step = 0
$script:job = $null
$script:jobAction = ''
$script:completed = $false
$script:resultPath = Join-Path $work 'result.json'
$script:jobStarted = [DateTime]::MinValue
$script:lang = 'ko'
function T([string]$Key) { return (Get-EndpointText $Key $script:lang) }

$form = New-Object Windows.Forms.Form
$form.Text = if ($Remove) { T 'title_remove' } else { T 'title_install' }
$form.Font = New-Object Drawing.Font('맑은 고딕', 10)
$form.AutoScaleMode = 'Dpi'
$form.AutoSize = $true
$form.AutoSizeMode = 'GrowAndShrink'
$form.AutoScroll = $true
$screenSize = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Size
$form.MaximumSize = $screenSize
$form.MinimumSize = New-Object Drawing.Size([Math]::Min(620, $screenSize.Width), [Math]::Min(480, $screenSize.Height))
$form.StartPosition = 'CenterScreen'
$form.MaximizeBox = $false
$layout = New-Object Windows.Forms.TableLayoutPanel
$layout.Dock = 'Top'
$layout.AutoSize = $true
$layout.Padding = New-Object Windows.Forms.Padding(20)
$layout.ColumnCount = 2
$layout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('AutoSize'))) | Out-Null
$layout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent', 100))) | Out-Null
$form.Controls.Add($layout)

$script:captions = @{}
function Add-EndpointRow([string]$Label, [Windows.Forms.Control]$Control) {
    $row = $layout.RowCount
    $layout.RowCount++
    $caption = New-Object Windows.Forms.Label
    if ($Label) { $script:captions[$Label] = $caption }
    $caption.Text = if ($Label) { T $Label } else { '' }
    $caption.AutoSize = $true
    $caption.Margin = New-Object Windows.Forms.Padding(3, 7, 12, 7)
    $Control.Dock = 'Fill'
    $Control.Margin = New-Object Windows.Forms.Padding(3, 5, 3, 5)
    $layout.Controls.Add($caption, 0, $row)
    $layout.Controls.Add($Control, 1, $row)
}

$title = New-Object Windows.Forms.Label
$title.AutoSize = $true
$title.Font = New-Object Drawing.Font('맑은 고딕', 14, [Drawing.FontStyle]::Bold)
Add-EndpointRow 'step' $title
$url = New-Object Windows.Forms.TextBox
$url.Text = $GatewayUrl
$url.ReadOnly = $mode -eq 'managed' -or $Remove
Add-EndpointRow 'gateway' $url
$location = New-Object Windows.Forms.TextBox
$location.Text = $directory
$location.ReadOnly = $mode -eq 'managed' -or $Remove
Add-EndpointRow 'location' $location
$user = New-Object Windows.Forms.TextBox
$user.Text = $targetUser
$user.ReadOnly = $Remove -or $mode -eq 'observer'
Add-EndpointRow 'account' $user
$scope = New-Object Windows.Forms.TextBox
$scope.Multiline = $true
$scope.Height = 65
$scope.ScrollBars = 'Vertical'
$scope.ReadOnly = $mode -eq 'managed' -or $Remove
$scope.Text = if ($mode -eq 'managed') { '대상 계정의 하네스 설정 · 실행 중인 도구 · 운영체제 차단 기록' } else { $ScanPath -join "`r`n" }
Add-EndpointRow 'scope' $scope
$permission = New-Object Windows.Forms.Label
$permission.AutoSize = $true
function Set-EndpointPermissionText {
    $permission.Text = if ($mode -ne 'managed') { '—' } elseif ($isolatedBox.Checked) { T 'permission_isolated' } else { T 'permission_simple' }
}
Add-EndpointRow 'permission' $permission
# Simple mode is the default (D-239): the signed-in account as it is. The companion account is the advanced option.
$isolatedBox = New-Object Windows.Forms.CheckBox
$isolatedBox.AutoSize = $true
$isolatedBox.Text = T 'isolated'
$isolatedBox.Visible = $mode -eq 'managed' -and -not $Remove
$isolatedBox.Add_CheckedChanged({ Set-EndpointPermissionText })
if ($isolatedBox.Visible) { Add-EndpointRow '' $isolatedBox }
Set-EndpointPermissionText
$key = New-Object Windows.Forms.Button
$key.AutoSize = $true
$key.Text = if ($KeyFile) { '장치 키 파일 선택 완료' } else { '장치 키 파일 선택' }
$key.Visible = $mode -eq 'observer' -and -not $Remove
$script:keyPath = $KeyFile
$key.Add_Click({
    $dialog = New-Object Windows.Forms.OpenFileDialog
    if ($dialog.ShowDialog() -eq 'OK') { $script:keyPath = $dialog.FileName; $key.Text = '장치 키 파일 선택 완료' }
    $dialog.Dispose()
})
if ($mode -eq 'observer' -and -not $Remove) { Add-EndpointRow '장치 자격' $key }
$progress = New-Object Windows.Forms.ProgressBar
Add-EndpointRow 'progress' $progress
$results = New-Object Windows.Forms.TextBox
$results.Multiline = $true
$results.ReadOnly = $true
$results.ScrollBars = 'Vertical'
$results.Height = 135
Add-EndpointRow 'result' $results
$log = New-Object Windows.Forms.TextBox
$log.ReadOnly = $true
$log.Text = Join-Path $work 'setup.log'
Add-EndpointRow 'log' $log
$buttons = New-Object Windows.Forms.FlowLayoutPanel
$buttons.AutoSize = $true
$next = New-Object Windows.Forms.Button
$next.AutoSize = $true
$next.Text = T 'start'
$retry = New-Object Windows.Forms.Button
$retry.AutoSize = $true
$retry.Text = T 'retry'
$retry.Enabled = $false
$close = New-Object Windows.Forms.Button
$close.AutoSize = $true
$close.Text = T 'close'
$close.Add_Click({ $form.Close() })
$language = New-Object Windows.Forms.Button
$language.AutoSize = $true
$language.Text = T 'language'
$language.Add_Click({
    $script:lang = if ($script:lang -eq 'ko') { 'en' } else { 'ko' }
    foreach ($key in $script:captions.Keys) { $script:captions[$key].Text = T $key }
    $retry.Text = T 'retry'; $close.Text = T 'close'; $language.Text = T 'language'; $isolatedBox.Text = T 'isolated'
    $form.Text = if ($Remove) { T 'title_remove' } else { T 'title_install' }
    Set-EndpointPermissionText
})
$buttons.Controls.AddRange(@($next, $retry, $close, $language))
Add-EndpointRow '' $buttons
$form.AcceptButton = $next

function Start-EndpointJob([string]$Action) {
    $script:jobAction = $Action
    $requestPath = Join-Path $work 'request.json'
    Remove-Item -LiteralPath (Join-Path $work 'result.json') -Force -ErrorAction SilentlyContinue
    $request = @{ action = $Action; mode = $mode; gateway_url = $url.Text; directory = $location.Text; user = $user.Text;
        ca_certificate = $bundle.ca_certificate; ca_sha256 = $bundle.ca_sha256;
        endpoint_id = $EndpointId; scan_paths = @($scope.Lines | Where-Object { $_.Trim() }); key_file = $script:keyPath;
        tailscale_node_id = $TailscaleNodeId; enrollment = (Join-Path $PSScriptRoot 'enrollment.json'); settings = $SettingsPath;
        requester_sid = $identity.User.Value; isolated_account = [bool]$isolatedBox.Checked }
    [IO.File]::WriteAllText($requestPath, ($request | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    try {
        $worker = Join-Path $PSScriptRoot 'windows-worker.ps1'
        $script:resultPath = Join-Path $work 'result.json'
        # An elevated wizard (run as administrator) cannot use the unprotected worker: the worker refuses it.
        $elevated = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        $privileged = $mode -eq 'managed' -and ($Action -ne 'health' -or $elevated)
        if ($privileged) {
            $null = Get-EndpointApprovedKit
            $paths = Get-EndpointInstallerPaths
            $worker = Join-Path $paths.code 'windows-worker.ps1'
            $script:resultPath = Join-Path $paths.state ('results\' + (Split-Path $work -Leaf) + '\result.json')
        }
        $args = '-NoProfile -NonInteractive -WindowStyle Hidden -File ' + (Quote-EndpointArgument $worker) +
            ' -RequestPath ' + (Quote-EndpointArgument $requestPath)
        if ($privileged) { $args += ' -RequesterSid ' + (Quote-EndpointArgument $identity.User.Value) }
        if (-not $privileged) { $args = '-ExecutionPolicy Bypass ' + $args }
        $options = @{ FilePath = $script:PowerShellExe; ArgumentList = $args; PassThru = $true; WindowStyle = 'Hidden' }
        if ($privileged) { $options.Verb = 'RunAs' }
        $log.Text = Join-Path (Split-Path $script:resultPath) 'setup.log'
        $script:jobStarted = [DateTime]::UtcNow
        $script:job = Start-Process @options
        $next.Enabled = $false
        $retry.Enabled = $false
        $close.Enabled = $false
        $url.Enabled = $false
        $location.Enabled = $false
        $user.Enabled = $false
        $scope.Enabled = $false
        $key.Enabled = $false
        $timer.Start()
    } catch {
        $results.Text = '조직 승인 설치기·무결성·실행 권한 확인 필요'
        if ($_.Exception.NativeErrorCode -eq 1223 -or $_.Exception.InnerException.NativeErrorCode -eq 1223) {
            $results.Text = '관리자 권한 승인 취소'
        }
        $results.AppendText("`r`n" + (T 'next') + ': ' + (Get-EndpointNextAction $results.Text $script:lang))
        $retry.Enabled = $true
    }
}

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 300
$timer.Add_Tick({
    $result = $null
    try {
        if ((Get-Item -LiteralPath $script:resultPath).LastWriteTimeUtc -ge $script:jobStarted) {
            $result = Get-Content -LiteralPath $script:resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
    } catch { }
    if ($result) {
        $progress.Value = [Math]::Max(0, [Math]::Min(100, [int]$result.percent))
        $results.Text = (@($result.steps) + @($result.detail | Where-Object { $_ })) -join "`r`n"
        if ($result.account) { $results.AppendText("`r`n대상 계정`t" + $result.account) }
    }
    if ($script:job -and $script:job.HasExited) {
        $timer.Stop()
        $exitCode = $script:job.ExitCode
        $script:job.Dispose()
        $script:job = $null
        $close.Enabled = $true
        $url.Enabled = $true
        $location.Enabled = $true
        $user.Enabled = $true
        $scope.Enabled = $true
        $key.Enabled = $true
        Remove-Item -LiteralPath (Join-Path $work 'request.json') -Force -ErrorAction SilentlyContinue
        if ($exitCode -ne 0 -or -not $result -or $result.state -ne 'completed') {
            if (-not $result) { $results.Text = '조직 승인 설치기 검증 또는 실행 권한 확인 필요' }
            # What failed, then the one thing to press next.
            $results.AppendText("`r`n" + (T 'next') + ': ' + (Get-EndpointNextAction $(if ($result) { $result.detail } else { $results.Text }) $script:lang))
            $retry.Enabled = $true
            $next.Enabled = $false
        } elseif ($script:jobAction -eq 'health') {
            $script:step = 2
            $title.Text = T 'confirm'
            $next.Text = if ($Remove) { T 'remove' } else { T 'install' }
            $next.Enabled = $true
        } else {
            $script:completed = $true
            $title.Text = if ($Remove) { T 'done_remove' } else { T 'done_install' }
            $next.Enabled = $false
            $retry.Enabled = $false
            if (-not $Remove -and $result.settings) {
                try {
                    $installed = Get-Content -LiteralPath $result.settings -Raw -Encoding UTF8 | ConvertFrom-Json
                    $terminalArgs = '-X utf8 -B -I -S ' + (Quote-EndpointArgument (Join-Path $installed.directory 'windows_status.py')) +
                        ' ' + (Quote-EndpointArgument $installed.status_path) + ' --settings ' + (Quote-EndpointArgument $result.settings)
                    Start-Process -FilePath (Join-Path $installed.directory 'python\python.exe') -ArgumentList $terminalArgs
                } catch { $results.AppendText("`r`n터미널 화면: 트레이에서 열기") }
            }
        }
    }
})
$next.Add_Click({
    if ($script:step -eq 0) {
        $script:step = 1
        $title.Text = T 'checking_gateway'
        if ($Remove) {
            $script:step = 2
            $title.Text = '엔드포인트 제거 확인'
            $next.Text = T 'remove'
            $results.Text = '예약 작업 · 엔드포인트 설정 제거'
        } else { Start-EndpointJob 'health' }
    } elseif ($script:step -eq 2) {
        if ($mode -eq 'observer' -and -not $Remove -and (-not $script:keyPath -or -not $EndpointId -or -not $scope.Text.Trim())) {
            $results.Text = '장치 자격 · 엔드포인트 식별자 · 관측 범위 확인 필요'
            return
        }
        $title.Text = if ($Remove) { '제거 진행' } else { '설치 진행' }
        Start-EndpointJob $(if ($Remove) { 'remove' } else { 'install' })
    }
})
$retry.Add_Click({ Start-EndpointJob $script:jobAction })
$form.Add_FormClosing({ param($sender, $event) if ($script:job) { $event.Cancel = $true } })
$title.Text = '시작'
try { [void]$form.ShowDialog() } finally {
    $timer.Dispose()
    $form.Dispose()
    foreach ($name in @('request.json', 'result.json', 'result.json.tmp')) {
        Remove-Item -LiteralPath (Join-Path $work $name) -Force -ErrorAction SilentlyContinue
    }
}
