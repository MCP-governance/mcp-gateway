param([Parameter(Mandatory = $true)][string]$SettingsPath)
. (Join-Path $PSScriptRoot 'windows-common.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$settings = Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$created = $false
$mutex = New-Object Threading.Mutex($true, ('Local\MCPGatewayTray-' + $settings.sid), [ref]$created)
if (-not $created) { $mutex.Dispose(); exit 0 }
$icon = New-Object Windows.Forms.NotifyIcon
$icon.Visible = $true
$menu = New-Object Windows.Forms.ContextMenuStrip
$icon.ContextMenuStrip = $menu
$script:label = '연결 끊김'
$script:blocks = @()
$script:management = '—'
$script:updated = '—'
$script:lastBlock = ''
$script:healthJob = $null
$script:healthResult = '—'
$work = Join-Path $env:LOCALAPPDATA ('MCPGatewaySetup\tray-' + $settings.sid)
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-EndpointAcl $work ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)

function Update-EndpointTray {
    $script:label = '연결 끊김'
    try {
        $snapshot = Get-Content -LiteralPath $settings.status_path -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:blocks = @($snapshot.blocks)
        $script:management = if ($snapshot.management) { $snapshot.management } else { '—' }
        $time = [DateTimeOffset]::FromUnixTimeSeconds([long]$snapshot.updated)
        $script:updated = $time.LocalDateTime.ToString('yyyy-MM-dd HH:mm:ss')
        $age = ([DateTimeOffset]::UtcNow - $time).TotalSeconds
        if ($snapshot.connected -and $age -ge 0 -and $age -le 150) {
            $script:label = '연결됨'
            if ($script:blocks.Count -gt 0) {
                $last = [DateTimeOffset]::MinValue
                if ([DateTimeOffset]::TryParse($script:blocks[-1].at, [ref]$last)) {
                    $blockAge = ([DateTimeOffset]::UtcNow - $last).TotalSeconds
                    if ($blockAge -ge 0 -and $blockAge -le 300) { $script:label = '차단 발생' }
                }
            }
        }
    } catch { }
    $icon.Icon = switch ($script:label) {
        '연결됨' { [Drawing.SystemIcons]::Information }
        '차단 발생' { [Drawing.SystemIcons]::Warning }
        default { [Drawing.SystemIcons]::Error }
    }
    $icon.Text = '엔드포인트 · ' + $script:label
    if ($script:label -eq '차단 발생' -and $script:blocks[-1].id -ne $script:lastBlock) {
        $script:lastBlock = $script:blocks[-1].id
        $icon.ShowBalloonTip(5000, '엔드포인트에서 차단', $script:blocks[-1].at, [Windows.Forms.ToolTipIcon]::Warning)
    }
}

function Show-EndpointState {
    Update-EndpointTray
    [void][Windows.Forms.MessageBox]::Show("연결 상태`t$script:label`n관리 상태`t$script:management`n최근 보고`t$script:updated`n게이트웨이`t$($settings.gateway_url)`n연결 점검`t$script:healthResult", '엔드포인트 상태')
}

$state = $menu.Items.Add('상태 보기')
$state.Add_Click({ Show-EndpointState })
$recent = $menu.Items.Add('최근 차단')
$recent.Add_Click({
    Update-EndpointTray
    $rows = @($script:blocks | Select-Object -Last 5 | ForEach-Object { "$($_.at)  엔드포인트에서 차단" })
    [void][Windows.Forms.MessageBox]::Show($(if ($rows.Count) { $rows -join "`n" } else { '—' }), '최근 차단')
})
$check = $menu.Items.Add('지금 점검')
$check.Add_Click({
    if ($script:healthJob) { return }
    $requestPath = Join-Path $work 'request.json'
    Remove-Item -LiteralPath (Join-Path $work 'result.json') -Force -ErrorAction SilentlyContinue
    [IO.File]::WriteAllText($requestPath, (@{ action = 'health'; gateway_url = $settings.gateway_url;
        ca_certificate = $settings.ca_certificate; ca_sha256 = $settings.ca_sha256 } | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + (Quote-EndpointArgument (Join-Path $PSScriptRoot 'windows-worker.ps1')) +
        ' -RequestPath ' + (Quote-EndpointArgument $requestPath)
    try {
        $script:healthJob = Start-Process -FilePath $script:PowerShellExe -ArgumentList $arguments -PassThru -WindowStyle Hidden
        $check.Enabled = $false
        $script:healthResult = '점검 중'
    } catch { $script:healthResult = '점검 실행 권한 확인 필요'; Show-EndpointState }
})
$console = $menu.Items.Add('콘솔 열기')
$console.Add_Click({ Start-Process $settings.gateway_url })
$remove = $menu.Items.Add('제거')
$remove.Add_Click({
    $arguments = '-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + (Quote-EndpointArgument (Join-Path $PSScriptRoot 'setup.ps1')) +
        ' -Remove -SettingsPath ' + (Quote-EndpointArgument $SettingsPath)
    # Explorer launches the wizard outside the scheduled task's process tree.
    $shell = New-Object -ComObject Shell.Application
    $shell.ShellExecute($script:PowerShellExe, $arguments, '', 'open', 0)
})
$icon.Add_DoubleClick({ Show-EndpointState })
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({
    Update-EndpointTray
    if ($script:healthJob -and $script:healthJob.HasExited) {
        try {
            $result = Get-Content -LiteralPath (Join-Path $work 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            $script:healthResult = if ($result.state -eq 'completed') { '연결됨' } else { $result.detail }
        } catch { $script:healthResult = '점검 응답 없음' }
        $script:healthJob.Dispose()
        $script:healthJob = $null
        $check.Enabled = $true
        Show-EndpointState
    }
})
try {
    Update-EndpointTray
    $timer.Start()
    [Windows.Forms.Application]::Run()
} finally {
    $timer.Dispose()
    if ($script:healthJob) { $script:healthJob.WaitForExit(15000) | Out-Null; $script:healthJob.Dispose() }
    $icon.Visible = $false
    $icon.Dispose()
    $menu.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    foreach ($name in @('request.json', 'result.json', 'result.json.tmp', 'setup.log')) {
        Remove-Item -LiteralPath (Join-Path $work $name) -Force -ErrorAction SilentlyContinue
    }
    if (-not (Get-ChildItem -LiteralPath $work -Force)) { Remove-Item -LiteralPath $work }
}
