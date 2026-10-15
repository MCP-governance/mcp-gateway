$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
$task = Join-Path $repo '.task-local-20261014\desktop'
$blenderProfile = Join-Path $task 'app\blender-profile'
$scripts = Join-Path $blenderProfile 'scripts'
$addons = Join-Path $scripts 'addons'
$blender = Join-Path $task 'app\blender\blender-5.2.2-windows-x64\blender.exe'
$sourceAddon = Join-Path $task 'sources\blender-mcp\src\blender_mcp\bundled\addon.py'
$portOwner = Get-NetTCPConnection -LocalPort 9876 -State Listen -ErrorAction SilentlyContinue
if ($portOwner) { throw "Port 9876 is already listening; owner PID $($portOwner.OwningProcess)." }
if (!(Test-Path $blender)) { throw "Portable Blender is missing: $blender" }
if (!(Test-Path $sourceAddon)) { throw "Pinned Blender MCP addon source is missing: $sourceAddon" }
New-Item -ItemType Directory -Force -Path $addons,(Join-Path $blenderProfile 'config'),(Join-Path $blenderProfile 'roaming'),(Join-Path $task 'log') | Out-Null
Copy-Item -LiteralPath $sourceAddon -Destination (Join-Path $addons 'blender_mcp.py') -Force
$blenderEnvironment = @{
    BLENDER_USER_SCRIPTS = $scripts
    BLENDER_USER_CONFIG = (Join-Path $blenderProfile 'config')
    APPDATA = (Join-Path $blenderProfile 'roaming')
    BLENDERMCP_TEST_LOG = (Join-Path $task 'log\blender-boot.log')
    BLENDERMCP_DISABLE_TELEMETRY = '1'
    DISABLE_TELEMETRY = '1'
    BLENDERMCP_NO_UPDATE_CHECK = '1'
}
$boot = Join-Path $blenderProfile 'blender_boot.py'
$bootSource = Join-Path $PSScriptRoot 'blender_boot.py'
Copy-Item -LiteralPath $bootSource -Destination $boot -Force
$stdout = Join-Path $task 'log\blender-stdout.log'
$stderr = Join-Path $task 'log\blender-stderr.log'
$priorEnvironment = @{}
try {
    foreach ($name in $blenderEnvironment.Keys) {
        $priorEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $blenderEnvironment[$name], 'Process')
    }
    $process = Start-Process -FilePath $blender -ArgumentList @('--factory-startup','--disable-autoexec','--python',$boot) -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
} finally {
    foreach ($name in $priorEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $priorEnvironment[$name], 'Process')
    }
}
Set-Content -LiteralPath (Join-Path $task 'log\blender.pid') -Value $process.Id -NoNewline
Write-Output "Started task-local Blender PID=$($process.Id). Bridge should bind only to 127.0.0.1:9876."
