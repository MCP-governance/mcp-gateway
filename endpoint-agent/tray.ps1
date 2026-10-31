param([Parameter(Mandatory = $true)][string]$SettingsPath, [switch]$Show)
. (Join-Path $PSScriptRoot 'windows-common.ps1')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
try {
    Add-Type -Namespace Mint -Name Dpi -MemberDefinition '[System.Runtime.InteropServices.DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
    [void][Mint.Dpi]::SetProcessDPIAware()
} catch { }
$settings = Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$work = Join-Path $env:LOCALAPPDATA ('MCPGatewaySetup\tray-' + $settings.sid)
$created = $false
$mutex = New-Object Threading.Mutex($true, ('Local\MCPGatewayTray-' + $settings.sid), [ref]$created)
if (-not $created) {
    # The running tray opens its window on its next tick.
    if ($Show) { [IO.File]::WriteAllText((Join-Path $work 'show-status'), '', [Text.Encoding]::ASCII) }
    $mutex.Dispose(); exit 0
}
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
$script:pipeGone = $null
$script:serviceMissing = $false
try { $script:probe = Get-Content -LiteralPath $probePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }

function T([string]$Key) { return (Get-EndpointText $Key $script:lang) }
$appIcon = Set-EndpointAppIdentity
try { Add-EndpointDesktopShortcut $work $settings.directory $SettingsPath (T 'product') } catch { }

function Update-EndpointTray {
    $script:snapshot = $null
    $script:blocks = @()
    $script:updated = '—'
    # Right after the install the service has not written its first snapshot yet: not a lost connection (b225285).
    $script:label = if (Test-Path -LiteralPath $settings.status_path) { 'disconnected' } else { 'preparing' }
    if (-not (Test-Path -LiteralPath $SettingsPath)) {
        $script:label = 'disconnected'
        $script:probe = $null
        $icon.Icon = [Drawing.SystemIcons]::Error
        $icon.Text = (T 'product') + ' · ' + (T 'disconnected')
        return
    }
    try {
        $script:snapshot = Get-Content -LiteralPath $settings.status_path -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:blocks = @($script:snapshot.blocks)
        $time = [DateTimeOffset]::FromUnixTimeSeconds([long]$script:snapshot.updated)
        $script:updated = $time.LocalDateTime.ToString('yyyy-MM-dd HH:mm:ss')
        $age = ([DateTimeOffset]::UtcNow - $time).TotalSeconds
        if ($script:snapshot.state -eq 'removed' -or
            ($script:snapshot.state -eq 'active' -and $script:probe.connection.waiting)) { $script:probe = $null }
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
    # The service owns a per-account pipe while it runs; a missing or stopped scheduled task leaves no pipe, long
    # before the last report is 150 seconds old. A restart takes seconds, so only a pipe gone for a while counts.
    if ($settings.mode -eq 'managed' -and $script:snapshot.state -ne 'removed' -and $script:label -ne 'preparing') {
        if (Test-EndpointServicePipe $settings.user) {
            if ($script:pipeGone) { $script:pipeGone = $null; $script:serviceMissing = $false; if ($script:probe.connection.service) { $script:probe = $null } }
        } elseif (-not $script:pipeGone) { $script:pipeGone = [DateTime]::UtcNow }
        if ($script:pipeGone -and ([DateTime]::UtcNow - $script:pipeGone).TotalSeconds -ge 10) { $script:label = 'service_stopped' }
    }
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
    if ($simple -and -not $script:probe -and -not $script:probeJob -and $script:label -notin @('disconnected', 'service_stopped') -and
        $script:snapshot.state -eq 'active') { Start-EndpointProbe }
}

function Get-EndpointCells {
    $p = $script:probe
    if (-not $p) { return @((T 'not_checked'), '—', '—') }
    $model = if ($p.model.ok) { "$($p.model.harness) $(T 'ok') · $($p.model.seconds)s" }
             elseif ($p.model.harness) { "$($p.model.harness) $(T 'failed') · $(Get-EndpointValue $p.model.detail $script:lang)" }
             else { Get-EndpointValue $p.model.detail $script:lang }
    $c = $p.connection
    $tools = if ($c.service) { T 'service_stopped' }
             elseif (@($c.initialized).Count) { "$($c.tools) ($(T 'servers') $(@($c.initialized).Count)/$($p.servers))" }
             elseif ($c.waiting) { T 'waiting' } else { '—' }
    $first = if (@($c.initialized).Count) { "$(@($c.initialized)[0]) $(T 'ok')" }
             elseif ($c.failed -and @($c.failed.PSObject.Properties).Count) {
                 (T 'failed') + ' · ' + ((@($c.failed.PSObject.Properties) | Select-Object -First 2 | ForEach-Object { "$($_.Name) $($_.Value)" }) -join ', ')
             } else { '—' }
    return @($model, $tools, $first)
}

function Get-EndpointNext {
    $state = $script:snapshot.state
    if ($state -eq 'removed' -or -not (Test-Path -LiteralPath $SettingsPath)) { return T 'next_removed' }
    if ($script:label -eq 'preparing') { return T 'next_preparing' }
    if ($script:serviceMissing -and $script:label -in @('disconnected', 'service_stopped')) { return T 'next_removed' }
    if ($script:label -eq 'service_stopped') { return T 'next_service' }
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
    if ($script:snapshot.state -eq 'removed' -or -not (Test-Path -LiteralPath $SettingsPath)) {
        $script:healthResult = T 'next_removed'
        Update-EndpointWindow
        return
    }
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
    if ($script:healthResult -eq (T 'gateway_ok') -and $script:label -in @('disconnected', 'service_stopped') -and $settings.mode -eq 'managed' -and
        $script:snapshot.state -ne 'removed' -and (Test-Path -LiteralPath $SettingsPath)) {
        if ([Windows.Forms.MessageBox]::Show((T 'restart_service'), (T 'product'), 'OKCancel') -eq 'OK') {
            # A standard account cannot read the service task, so only the elevated command can tell it is gone (exit 3):
            # then restarting is pointless and the next step is the reinstall.
            $task = 'MCPGatewayManaged-' + $settings.user.ToLowerInvariant()
            $query = "if (Get-ScheduledTask -TaskName '$task' -ErrorAction SilentlyContinue) { Start-ScheduledTask -TaskName '$task' } else { exit 3 }"
            try {
                $restart = Start-Process -FilePath $script:PowerShellExe -Verb RunAs -WindowStyle Hidden -PassThru -Wait -ArgumentList (
                    '-NoProfile -NonInteractive -Command ' + (Quote-EndpointArgument $query))
                if ($restart.ExitCode -eq 3) { $script:serviceMissing = $true }
                $restart.Dispose()
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
    $servers = @($snapshot.server_names | Where-Object { $_ })
    if (-not $servers.Count) { $servers = @($snapshot.servers) }
    $versions = @()
    if ($snapshot.harnesses) { $versions = @($snapshot.harnesses.PSObject.Properties | ForEach-Object { "$($_.Name) $($_.Value)" }) }
    $cells = Get-EndpointCells
    $mode = if ($simple) { T 'mode_simple' } elseif ($settings.connection -eq 'isolated') { T 'mode_isolated' } else { '—' }
    $management = if ($snapshot.state -in @('active', 'pending', 'quarantined', 'revoked', 'removed', 'unknown')) { T $snapshot.state }
                  elseif ($snapshot.management) { Get-EndpointValue $snapshot.management $script:lang } else { '—' }
    $rows = [ordered]@{ connection = T $script:label; management = $management;
        way = $mode; servers = $(if ($servers.Count) { "$($servers.Count) · " + ($servers -join ', ') } else { '—' });
        harness = $(if ($versions.Count) { $versions -join ', ' } else { '—' }); reported = $script:updated;
        model = $(if ($script:probeJob) { T 'checking' } else { $cells[0] }); tools = $cells[1]; server = $cells[2];
        gateway = $(if ($script:healthResult) { Get-EndpointValue $script:healthResult $script:lang } else { $settings.gateway_url }); next = Get-EndpointNext }
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
    $form.Icon = $appIcon
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
    $navigation = Set-EndpointChrome $form $layout { Show-EndpointSources } { Start-EndpointLogin $(if (Get-Command claude -ErrorAction SilentlyContinue) { 'claude' } else { 'codex' }) } { Start-EndpointReconnect }
    $form.Tag.navigation = $navigation
    $script:window = $form
    Update-EndpointWindow
    $form.Show()
}


function Show-EndpointSources {
    $sourceForm = New-Object Windows.Forms.Form
    $sourceForm.Text = T 'approved'; $sourceForm.AutoScaleMode = 'Dpi'
    $sourceForm.Size = New-Object Drawing.Size(640, 420); $sourceForm.StartPosition = 'CenterScreen'
    $sourceForm.BackColor = [Drawing.Color]::White
    $sources = New-Object Windows.Forms.ListBox
    $sources.Dock = 'Fill'; $sources.DisplayMember = 'display_name'
    $download = New-Object Windows.Forms.Button
    $download.Text = T 'source'; $download.Dock = 'Bottom'; $download.Height = 44; $download.Enabled = $false
    $result = New-Object Windows.Forms.Label
    $result.Dock = 'Bottom'; $result.AutoSize = $true
    $sourceForm.Controls.AddRange(@($sources, $result, $download))
    $state = @{ job = $null; download = $false }
    $output = Join-Path $work 'sources.json'
    # GetNewClosure() keeps only this function's locals: script variables and functions are not visible inside.
    $pythonExe = $python
    $quote = ${function:Quote-EndpointArgument}
    $base = '-X utf8 -B -I -S ' + (Quote-EndpointArgument (Join-Path $settings.directory 'managed-windows.py')) +
        ' sources --settings ' + (Quote-EndpointArgument $SettingsPath)
    $text = @{ checking = T 'checking'; failed = T 'failed'; ok = T 'ok'; approved = T 'approved' }
    $start = {
        param($server)
        if ($state.job) { return }
        $arguments = $base
        if ($server) {
            $arguments += ' --server ' + (& $quote $server.server_id) + ' --commit ' + (& $quote $server.commit_sha)
        }
        $state.download = [bool]$server
        $download.Enabled = $false; $result.Text = $text.checking
        try {
            $state.job = Start-Process -FilePath $pythonExe -ArgumentList $arguments -PassThru -WindowStyle Hidden `
                -RedirectStandardOutput $output -RedirectStandardError ($output + '.err')
            # Windows PowerShell reports ExitCode only when the handle was opened before the process exits.
            [void]$state.job.Handle
        } catch { $result.Text = $text.failed }
    }.GetNewClosure()
    $sources.Add_SelectedIndexChanged({ $download.Enabled = -not $state.job -and $sources.SelectedItem.source_available }.GetNewClosure())
    $download.Add_Click({ & $start $sources.SelectedItem }.GetNewClosure())
    $timer = New-Object Windows.Forms.Timer
    $timer.Interval = 400
    $timer.Add_Tick({
        if (-not $state.job -or -not $state.job.HasExited) { return }
        try {
            if ($state.job.ExitCode -ne 0) { throw 'source' }
            $answer = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($state.download) { $result.Text = $text.ok + ' · ' + $answer.file }
            else {
                $sources.Items.Clear()
                foreach ($server in $answer.servers) { [void]$sources.Items.Add($server) }
                $result.Text = $text.approved
            }
        } catch { $result.Text = $text.failed }
        $state.job.Dispose(); $state.job = $null
        $download.Enabled = $sources.SelectedItem -and $sources.SelectedItem.source_available
    }.GetNewClosure())
    $sourceForm.Add_FormClosing({ param($sender, $event) if ($state.job) { $event.Cancel = $true } }.GetNewClosure())
    & $start $null; $timer.Start()
    try { [void]$sourceForm.ShowDialog() } finally { $timer.Dispose(); $sourceForm.Dispose() }
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
$items.terminal = $menu.Items.Add('')
$terminal = $items.terminal
$terminal.Add_Click({
    $arguments = '-X utf8 -B -I -S ' + (Quote-EndpointArgument (Join-Path $settings.directory 'windows_status.py')) +
        ' ' + (Quote-EndpointArgument $settings.status_path) + ' --settings ' + (Quote-EndpointArgument $SettingsPath) +
        ' --probe ' + (Quote-EndpointArgument $probePath) + ' --language ' + $script:lang
    Start-Process -FilePath $python -ArgumentList $arguments
})
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
    if (Test-Path -LiteralPath (Join-Path $work 'show-status')) {
        Remove-Item -LiteralPath (Join-Path $work 'show-status') -Force
        $script:probe = $null
        Show-EndpointWindow
    }
})
try {
    Update-EndpointTray
    $timer.Start()
    if ($Show) { Show-EndpointWindow }
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
