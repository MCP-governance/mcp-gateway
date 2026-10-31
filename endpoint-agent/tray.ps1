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
$script:ui = $null
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
        $icon.ShowBalloonTip(8000, (T 'reconnect'), (T 'next_removed'), [Windows.Forms.ToolTipIcon]::Warning)
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
    $icon.ShowBalloonTip(8000, (T 'reconnect'), ((Get-EndpointValue $script:healthResult $script:lang) + "`n" + (Get-EndpointNext)),
        [Windows.Forms.ToolTipIcon]::Info)
}

# The status window is the local page (`mint ui`, the console's design): reopened while it runs, started otherwise.
# It closes itself after 30 idle minutes.
function Show-EndpointWindow {
    $urlPath = Join-Path $work 'ui.url'
    if ($script:ui -and -not $script:ui.HasExited) {
        try {
            $url = (Get-Content -LiteralPath $urlPath -TotalCount 1).Trim()
            if ($url -match '^http://127\.0\.0\.1:\d+/[A-Za-z0-9_-]+/$') { Start-Process $url; return }
        } catch { }
    }
    $arguments = '-X utf8 -B -I -S ' + (Quote-EndpointArgument (Join-Path $settings.directory 'windows_status.py')) + ' ui'
    try {
        $script:ui = Start-Process -FilePath $python -ArgumentList $arguments -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $urlPath -RedirectStandardError (Join-Path $work 'ui.err')
    } catch { [void][Windows.Forms.MessageBox]::Show((T 'check_failed'), (T 'product')) }
}

function Switch-EndpointLanguage {
    $script:lang = if ($script:lang -eq 'ko') { 'en' } else { 'ko' }
    try { [IO.File]::WriteAllText((Join-Path $work 'lang.txt'), $script:lang) } catch { }
    Set-EndpointMenuText
    Update-EndpointTray
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
    if ($script:ui) { $script:ui.Dispose() }
    $icon.Visible = $false
    $icon.Dispose()
    $menu.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
    foreach ($name in @('request.json', 'result.json', 'result.json.tmp', 'setup.log', 'probe.json.tmp', 'probe.err')) {
        Remove-Item -LiteralPath (Join-Path $work $name) -Force -ErrorAction SilentlyContinue
    }
}
