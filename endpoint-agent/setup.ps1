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
    $installed = Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $mode = $installed.mode
    $directory = $installed.directory
    $GatewayUrl = $installed.gateway_url
    $targetUser = $installed.user
} elseif (-not $Observer) {
    try {
        $bundle = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'enrollment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $GatewayUrl = $bundle.gateway_url
    } catch { $GatewayUrl = '' }
}
$work = Join-Path $env:LOCALAPPDATA ('MCPGatewaySetup\' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-EndpointAcl $work $identity.User.Value
$script:step = 0
$script:job = $null
$script:jobAction = ''
$script:completed = $false
$script:resultPath = Join-Path $work 'result.json'
$script:jobStarted = [DateTime]::MinValue

$form = New-Object Windows.Forms.Form
$form.Text = if ($Remove) { '엔드포인트 제거' } else { '엔드포인트 설치' }
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

function Add-EndpointRow([string]$Label, [Windows.Forms.Control]$Control) {
    $row = $layout.RowCount
    $layout.RowCount++
    $caption = New-Object Windows.Forms.Label
    $caption.Text = $Label
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
Add-EndpointRow '단계' $title
$url = New-Object Windows.Forms.TextBox
$url.Text = $GatewayUrl
$url.ReadOnly = $mode -eq 'managed' -or $Remove
Add-EndpointRow '게이트웨이' $url
$location = New-Object Windows.Forms.TextBox
$location.Text = $directory
$location.ReadOnly = $mode -eq 'managed' -or $Remove
Add-EndpointRow '설치 위치' $location
$user = New-Object Windows.Forms.TextBox
$user.Text = $targetUser
$user.ReadOnly = $Remove -or $mode -eq 'observer'
Add-EndpointRow '대상 계정' $user
$scope = New-Object Windows.Forms.TextBox
$scope.Multiline = $true
$scope.Height = 65
$scope.ScrollBars = 'Vertical'
$scope.ReadOnly = $mode -eq 'managed' -or $Remove
$scope.Text = if ($mode -eq 'managed') { '대상 계정의 하네스 설정 · 실행 중인 도구 · 운영체제 차단 기록' } else { $ScanPath -join "`r`n" }
Add-EndpointRow '관측 범위' $scope
$permission = New-Object Windows.Forms.Label
$permission.AutoSize = $true
$permission.Text = if ($mode -eq 'managed') { '관리자 권한 · 대상 계정 로그아웃 필요' } else { '현재 사용자' }
Add-EndpointRow '설치 권한' $permission
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
Add-EndpointRow '진행률' $progress
$results = New-Object Windows.Forms.TextBox
$results.Multiline = $true
$results.ReadOnly = $true
$results.ScrollBars = 'Vertical'
$results.Height = 135
Add-EndpointRow '결과' $results
$log = New-Object Windows.Forms.TextBox
$log.ReadOnly = $true
$log.Text = Join-Path $work 'setup.log'
Add-EndpointRow '로그 파일' $log
$buttons = New-Object Windows.Forms.FlowLayoutPanel
$buttons.AutoSize = $true
$next = New-Object Windows.Forms.Button
$next.AutoSize = $true
$next.Text = '시작'
$retry = New-Object Windows.Forms.Button
$retry.AutoSize = $true
$retry.Text = '다시 시도'
$retry.Enabled = $false
$close = New-Object Windows.Forms.Button
$close.AutoSize = $true
$close.Text = '닫기'
$close.Add_Click({ $form.Close() })
$buttons.Controls.AddRange(@($next, $retry, $close))
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
        requester_sid = $identity.User.Value }
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
            $retry.Enabled = $true
            $next.Enabled = $false
        } elseif ($script:jobAction -eq 'health') {
            $script:step = 2
            $title.Text = '설치 위치 · 관측 범위 확인'
            $next.Text = if ($Remove) { '제거' } else { '설치' }
            $next.Enabled = $true
        } else {
            $script:completed = $true
            $title.Text = if ($Remove) { '제거 완료' } else { '설치 완료' }
            $next.Enabled = $false
            $retry.Enabled = $false
        }
    }
})
$next.Add_Click({
    if ($script:step -eq 0) {
        $script:step = 1
        $title.Text = '게이트웨이 연결 확인'
        if ($Remove) {
            $script:step = 2
            $title.Text = '엔드포인트 제거 확인'
            $next.Text = '제거'
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
