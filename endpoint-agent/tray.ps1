param([Parameter(Mandatory = $true)][string]$SettingsPath)
. (Join-Path $PSScriptRoot 'windows-common.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$settings = Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$created = $false
$mutex = New-Object Threading.Mutex($true, ('Local\MCPGatewayTray-' + $settings.sid), [ref]$created)
if (-not $created) { $mutex.Dispose(); exit 0 }
$work = Join-Path $env:LOCALAPPDATA ('MCPGatewaySetup\tray-' + $settings.sid)
New-Item -ItemType Directory -Path $work -Force | Out-Null
Set-EndpointAcl $work ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
$script:lang = 'ko'
try { if ((Get-Content -LiteralPath (Join-Path $work 'lang.txt') -Raw).Trim() -eq 'en') { $script:lang = 'en' } } catch { }
$simple = $settings.connection -eq 'simple'
$python = Join-Path $settings.directory 'python\python.exe'
$probePath = Join-Path $work 'probe.json'

$icon = New-Object Windows.Forms.NotifyIcon
$icon.Visible = $true
$menu = New-Object Windows.Forms.ContextMenuStrip
$icon.ContextMenuStrip = $menu
$script:label = 'disconnected'
$script:snapshot = $null
$script:blocks = @()
$script:updated = '—'
$script:lastBlock = ''
$script:healthJob = $null
$script:healthResult = ''
$script:probeJob = $null
$script:probe = $null
$script:window = $null
try { $script:probe = Get-Content -LiteralPath $probePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }

function T([string]$Key) { return (Get-EndpointText $Key $script:lang) }

function Update-EndpointTray {
    # Right after the install the service has not written its first snapshot yet: not a lost connection (b225285).
    $script:label = if (Test-Path -LiteralPath $settings.status_path) { 'disconnected' } else { 'preparing' }
    try {
        $script:snapshot = Get-Content -LiteralPath $settings.status_path -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:blocks = @($script:snapshot.blocks)
        $time = [DateTimeOffset]::FromUnixTimeSeconds([long]$script:snapshot.updated)
        $script:updated = $time.LocalDateTime.ToString('yyyy-MM-dd HH:mm:ss')
        $age = ([DateTimeOffset]::UtcNow - $time).TotalSeconds
        if ($script:snapshot.connected -and $age -ge 0 -and $age -le 150) {
            $script:label = 'connected'
            if ($script:blocks.Count -gt 0) {
                $last = [DateTimeOffset]::MinValue
                if ([DateTimeOffset]::TryParse($script:blocks[-1].at, [ref]$last)) {
                    $blockAge = ([DateTimeOffset]::UtcNow - $last).TotalSeconds
                    if ($blockAge -ge 0 -and $blockAge -le 300) { $script:label = 'blocked' }
                }
            }
        }
    } catch { }
    $icon.Icon = switch ($script:label) {
        'connected' { [Drawing.SystemIcons]::Information }
        'blocked' { [Drawing.SystemIcons]::Warning }
        default { [Drawing.SystemIcons]::Error }
    }
    $icon.Text = (T 'product') + ' · ' + (T $script:label)
    if ($script:label -eq 'blocked' -and $script:blocks[-1].id -ne $script:lastBlock) {
        $script:lastBlock = $script:blocks[-1].id
        $icon.ShowBalloonTip(5000, (T 'blocked'), $script:blocks[-1].at, [Windows.Forms.ToolTipIcon]::Warning)
    }
    # The first time the PC is active, check it once by itself: model answer, tools, one server (D-239).
    if ($simple -and -not $script:probe -and -not $script:probeJob -and $script:label -ne 'disconnected' -and
        $script:snapshot.state -eq 'active') { Start-EndpointProbe }
}

function Get-EndpointCells {
    $p = $script:probe
    if (-not $p) { return @((T 'not_checked'), '—', '—') }
    $model = if ($p.model.ok) { "$($p.model.harness) $(T 'ok') · $($p.model.seconds)s" }
             elseif ($p.model.harness) { "$($p.model.harness) $(T 'failed') · $($p.model.detail)" } else { $p.model.detail }
    $c = $p.connection
    $tools = if (@($c.initialized).Count) { "$($c.tools) ($(T 'servers') $(@($c.initialized).Count)/$($p.servers))" }
             elseif ($c.waiting) { T 'waiting' } else { '—' }
    $first = if (@($c.initialized).Count) { "$(@($c.initialized)[0]) $(T 'ok')" }
             elseif ($c.failed -and @($c.failed.PSObject.Properties).Count) {
                 (T 'failed') + ' · ' + ((@($c.failed.PSObject.Properties) | Select-Object -First 2 | ForEach-Object { "$($_.Name) $($_.Value)" }) -join ', ')
             } else { '—' }
    return @($model, $tools, $first)
}

function Get-EndpointNext {
    $state = $script:snapshot.state
    if ($script:label -eq 'preparing') { return T 'next_preparing' }
    if ($script:label -eq 'disconnected') { return T 'next_reconnect' }
    if ($state -eq 'pending') { return T 'next_pending' }
    if ($state -eq 'quarantined') { return T 'next_quarantined' }
    if ($state -eq 'revoked') { return T 'next_revoked' }
    $p = $script:probe
    if ($p -and $p.model.harness -and -not $p.model.ok) { return T 'next_login' }
    if ($p -and -not @($p.connection.initialized).Count -and $p.servers -gt 0 -and -not $p.connection.waiting) { return T 'next_reconnect' }
    if (-not $p -and $simple) { return T 'next_check' }
    return T 'next_ready'
}

function Start-EndpointProbe([switch]$Show) {
    if ($script:probeJob -or -not (Test-Path -LiteralPath $python)) { return }
    Remove-Item -LiteralPath ($probePath + '.tmp') -Force -ErrorAction SilentlyContinue
    $arguments = '-X utf8 -B -I -S ' + (Quote-EndpointArgument (Join-Path $settings.directory 'managed-windows.py')) +
        ' probe --settings ' + (Quote-EndpointArgument $SettingsPath)
    try {
        $script:probeJob = Start-Process -FilePath $python -ArgumentList $arguments -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput ($probePath + '.tmp') -RedirectStandardError (Join-Path $work 'probe.err')
        $script:probeShow = [bool]$Show
        Update-EndpointWindow
    } catch { $script:probeJob = $null }
}

function Complete-EndpointProbe {
    try {
        $lines = @(Get-Content -LiteralPath ($probePath + '.tmp') -Encoding UTF8 | Where-Object { $_.StartsWith('{') })
        $script:probe = $lines[-1] | ConvertFrom-Json
        Move-Item -LiteralPath ($probePath + '.tmp') -Destination $probePath -Force
        $cells = Get-EndpointCells
        $icon.ShowBalloonTip(8000, (T 'check'), ((T 'model') + ' ' + $cells[0] + "`n" + (T 'tools') + ' ' + $cells[1] + "`n" + (T 'server') + ' ' + $cells[2]),
            [Windows.Forms.ToolTipIcon]::Info)
    } catch { $script:healthResult = T 'check_failed' }
    $script:probeJob.Dispose()
    $script:probeJob = $null
    Update-EndpointWindow
    if ($script:probeShow) { Show-EndpointWindow }
}

function Start-EndpointLogin([string]$Harness) {
    $command = if ($Harness -eq 'codex') { 'codex login --device-auth' } else { 'claude auth login' }
    if (-not (Get-Command $Harness -ErrorAction SilentlyContinue)) {
        [void][Windows.Forms.MessageBox]::Show((T 'no_harness') -f $Harness, (T 'product'))
        return
    }
    Start-Process -FilePath (Join-Path ([Environment]::GetFolderPath('System')) 'cmd.exe') -ArgumentList @('/k', $command)
}

function Start-EndpointReconnect {
    if ($script:healthJob) { return }
    $requestPath = Join-Path $work 'request.json'
    Remove-Item -LiteralPath (Join-Path $work 'result.json') -Force -ErrorAction SilentlyContinue
    [IO.File]::WriteAllText($requestPath, (@{ action = 'health'; gateway_url = $settings.gateway_url;
        ca_certificate = $settings.ca_certificate; ca_sha256 = $settings.ca_sha256 } | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + (Quote-EndpointArgument (Join-Path $PSScriptRoot 'windows-worker.ps1')) +
        ' -RequestPath ' + (Quote-EndpointArgument $requestPath)
    try {
        $script:healthJob = Start-Process -FilePath $script:PowerShellExe -ArgumentList $arguments -PassThru -WindowStyle Hidden
        $script:healthResult = T 'checking'
    } catch { $script:healthResult = T 'check_failed' }
    Update-EndpointWindow
}

function Complete-EndpointReconnect {
    try {
        $result = Get-Content -LiteralPath (Join-Path $work 'result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:healthResult = if ($result.state -eq 'completed') { T 'gateway_ok' } else { $result.detail + ' · ' + (Get-EndpointNextAction $result.detail $script:lang) }
    } catch { $script:healthResult = T 'check_failed' }
    $script:healthJob.Dispose()
    $script:healthJob = $null
    Update-EndpointTray
    # The Gateway answers but this PC's service stopped reporting: restarting the service needs an administrator.
    if ($script:healthResult -eq (T 'gateway_ok') -and $script:label -eq 'disconnected' -and $settings.mode -eq 'managed') {
        if ([Windows.Forms.MessageBox]::Show((T 'restart_service'), (T 'product'), 'OKCancel') -eq 'OK') {
            $task = 'MCPGatewayManaged-' + $settings.user.ToLowerInvariant()
            try {
                Start-Process -FilePath $script:PowerShellExe -Verb RunAs -WindowStyle Hidden -ArgumentList (
                    '-NoProfile -NonInteractive -Command Start-ScheduledTask -TaskName ' + (Quote-EndpointArgument $task))
            } catch { $script:healthResult = T 'uac_cancelled' }
        }
    }
    Update-EndpointWindow
}

function New-EndpointButton([string]$Key, [scriptblock]$Action) {
    $button = New-Object Windows.Forms.Button
    $button.AutoSize = $true
    $button.Tag = $Key
    $button.Text = T $Key
    $button.Add_Click($Action)
    return $button
}

function Update-EndpointWindow {
    $form = $script:window
    if (-not $form -or $form.IsDisposed) { return }
    $form.Text = T 'product'
    $snapshot = $script:snapshot
    $servers = @($snapshot.servers)
    $versions = @()
    if ($snapshot.harnesses) { $versions = @($snapshot.harnesses.PSObject.Properties | ForEach-Object { "$($_.Name) $($_.Value)" }) }
    $cells = Get-EndpointCells
    $mode = if ($simple) { T 'mode_simple' } elseif ($settings.connection -eq 'isolated') { T 'mode_isolated' } else { '—' }
    $rows = [ordered]@{ connection = T $script:label; management = $(if ($snapshot.management) { $snapshot.management } else { '—' });
        way = $mode; servers = $(if ($servers.Count) { "$($servers.Count) · " + ($servers -join ', ') } else { '—' });
        harness = $(if ($versions.Count) { $versions -join ', ' } else { '—' }); reported = $script:updated;
        model = $(if ($script:probeJob) { T 'checking' } else { $cells[0] }); tools = $cells[1]; server = $cells[2];
        gateway = $(if ($script:healthResult) { $script:healthResult } else { $settings.gateway_url }); next = Get-EndpointNext }
    foreach ($key in $rows.Keys) {
        $form.Tag.captions[$key].Text = T $key
        $form.Tag.values[$key].Text = [string]$rows[$key]
    }
    foreach ($button in $form.Tag.buttons) { $button.Text = T $button.Tag }
}

function Show-EndpointWindow {
    Update-EndpointTray
    if ($script:window -and -not $script:window.IsDisposed) { $script:window.Activate(); Update-EndpointWindow; return }
    $form = New-Object Windows.Forms.Form
    $form.Font = New-Object Drawing.Font('맑은 고딕', 10)
    $form.AutoScaleMode = 'Dpi'
    $form.AutoSize = $true
    $form.AutoSizeMode = 'GrowAndShrink'
    $form.StartPosition = 'CenterScreen'
    $form.MaximizeBox = $false
    $form.MinimumSize = New-Object Drawing.Size(560, 0)
    $layout = New-Object Windows.Forms.TableLayoutPanel
    $layout.AutoSize = $true
    $layout.Dock = 'Fill'
    $layout.Padding = New-Object Windows.Forms.Padding(16)
    $layout.ColumnCount = 2
    $layout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('AutoSize'))) | Out-Null
    $layout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle('Percent', 100))) | Out-Null
    $form.Controls.Add($layout)
    $captions = @{}; $values = @{}
    foreach ($key in @('connection', 'management', 'way', 'servers', 'harness', 'reported', 'model', 'tools', 'server', 'gateway', 'next')) {
        $caption = New-Object Windows.Forms.Label
        $caption.AutoSize = $true
        $caption.Margin = New-Object Windows.Forms.Padding(3, 6, 12, 6)
        $value = New-Object Windows.Forms.Label
        $value.AutoSize = $true
        $value.MaximumSize = New-Object Drawing.Size(520, 0)
        $value.Margin = New-Object Windows.Forms.Padding(3, 6, 3, 6)
        if ($key -eq 'next') { $value.Font = New-Object Drawing.Font('맑은 고딕', 10, [Drawing.FontStyle]::Bold) }
        $row = $layout.RowCount; $layout.RowCount++
        $layout.Controls.Add($caption, 0, $row); $layout.Controls.Add($value, 1, $row)
        $captions[$key] = $caption; $values[$key] = $value
    }
    $buttons = New-Object Windows.Forms.FlowLayoutPanel
    $buttons.AutoSize = $true
    $list = @(
        (New-EndpointButton 'check' { Start-EndpointProbe -Show }),
        (New-EndpointButton 'login' { Start-EndpointLogin $(if (Get-Command claude -ErrorAction SilentlyContinue) { 'claude' } else { 'codex' }) }),
        (New-EndpointButton 'reconnect' { Start-EndpointReconnect }),
        (New-EndpointButton 'open_console' { Start-Process $settings.gateway_url }),
        (New-EndpointButton 'language' { Switch-EndpointLanguage }),
        (New-EndpointButton 'remove' { Start-EndpointRemove }),
        (New-EndpointButton 'close' { $script:window.Close() }))
    $buttons.Controls.AddRange($list)
    $row = $layout.RowCount; $layout.RowCount++
    $layout.Controls.Add($buttons, 0, $row); $layout.SetColumnSpan($buttons, 2)
    $form.Tag = @{ captions = $captions; values = $values; buttons = $list }
    $script:window = $form
    Update-EndpointWindow
    $form.Show()
}

function Switch-EndpointLanguage {
    $script:lang = if ($script:lang -eq 'ko') { 'en' } else { 'ko' }
    try { [IO.File]::WriteAllText((Join-Path $work 'lang.txt'), $script:lang) } catch { }
    Set-EndpointMenuText
    Update-EndpointTray
    Update-EndpointWindow
}

function Start-EndpointRemove {
    $arguments = '-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + (Quote-EndpointArgument (Join-Path $PSScriptRoot 'setup.ps1')) +
        ' -Remove -SettingsPath ' + (Quote-EndpointArgument $SettingsPath)
    # Explorer launches the wizard outside the scheduled task's process tree.
    $shell = New-Object -ComObject Shell.Application
    $shell.ShellExecute($script:PowerShellExe, $arguments, '', 'open', 0)
}

$items = [ordered]@{}
$items.status = $menu.Items.Add(''); $items.status.Add_Click({ Show-EndpointWindow })
$items.check = $menu.Items.Add(''); $items.check.Add_Click({ Start-EndpointProbe -Show })
$items.login = New-Object Windows.Forms.ToolStripMenuItem
[void]$menu.Items.Add($items.login)
$claudeLogin = $items.login.DropDownItems.Add('Claude'); $claudeLogin.Add_Click({ Start-EndpointLogin 'claude' })
$codexLogin = $items.login.DropDownItems.Add('Codex'); $codexLogin.Add_Click({ Start-EndpointLogin 'codex' })
$items.reconnect = $menu.Items.Add(''); $items.reconnect.Add_Click({ Start-EndpointReconnect })
$items.recent = $menu.Items.Add('')
$items.recent.Add_Click({
    Update-EndpointTray
    $rows = @($script:blocks | Select-Object -Last 5 | ForEach-Object { "$($_.at)  " + (T 'blocked') })
    [void][Windows.Forms.MessageBox]::Show($(if ($rows.Count) { $rows -join "`n" } else { '—' }), (T 'recent'))
})
$items.open_console = $menu.Items.Add(''); $items.open_console.Add_Click({ Start-Process $settings.gateway_url })
$items.language = $menu.Items.Add(''); $items.language.Add_Click({ Switch-EndpointLanguage })
$items.remove = $menu.Items.Add(''); $items.remove.Add_Click({ Start-EndpointRemove })

function Set-EndpointMenuText {
    foreach ($key in $items.Keys) { $items[$key].Text = T $key }
}
Set-EndpointMenuText
$icon.Add_DoubleClick({ Show-EndpointWindow })
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({
    Update-EndpointTray
    if ($script:healthJob -and $script:healthJob.HasExited) { Complete-EndpointReconnect }
    if ($script:probeJob -and $script:probeJob.HasExited) { Complete-EndpointProbe }
    Update-EndpointWindow
})
try {
    Update-EndpointTray
    $timer.Start()
    [Windows.Forms.Application]::Run()
} finally {
    $timer.Dispose()
    if ($script:healthJob) { $script:healthJob.WaitForExit(15000) | Out-Null; $script:healthJob.Dispose() }
    if ($script:probeJob) { $script:probeJob.Dispose() }
    if ($script:window -and -not $script:window.IsDisposed) { $script:window.Dispose() }
    $icon.Visible = $false
    $icon.Dispose()
    $menu.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    foreach ($name in @('request.json', 'result.json', 'result.json.tmp', 'setup.log', 'probe.json.tmp', 'probe.err')) {
        Remove-Item -LiteralPath (Join-Path $work $name) -Force -ErrorAction SilentlyContinue
    }
}
