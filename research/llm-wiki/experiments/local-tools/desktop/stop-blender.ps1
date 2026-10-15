$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..\..')).Path
$task = Join-Path $repo '.task-local-20261014\desktop'
$pidPath = Join-Path $task 'log\blender.pid'
if (!(Test-Path $pidPath)) { Write-Output 'No recorded task-local Blender PID.'; exit 0 }
$processId = [int](Get-Content -Raw $pidPath)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
$expected = Join-Path $task 'app\blender\blender-5.2.2-windows-x64\blender.exe'
if ($process -and $process.ExecutablePath -eq $expected) {
  Stop-Process -Id $processId -Force
  Wait-Process -Id $processId -Timeout 15 -ErrorAction SilentlyContinue
  Write-Output "Stopped task-local Blender PID=$processId."
} else {
  Write-Output 'Recorded PID no longer identifies the task-local Blender executable; left it untouched.'
}
Remove-Item -LiteralPath $pidPath -Force
