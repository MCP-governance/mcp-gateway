$ErrorActionPreference = 'Stop'

# Map the Korean workspace path to a temporary ASCII drive because PyGhidra's
# launcher decodes child output as UTF-8. The mapping is removed on every exit.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../../../../')).Path
$localRoot = Join-Path $repoRoot '.task-local-20261014'
$driveLetter = @('R','S','T','U','V','W','X','Y','Z') |
    Where-Object { -not (Test-Path ("${_}:\")) } |
    Select-Object -First 1
if (-not $driveLetter) { throw 'No free drive letter is available for a temporary subst mapping.' }

$drive = "${driveLetter}:"
subst $drive $localRoot
if ($LASTEXITCODE -ne 0) { throw "Could not map $drive to the task-local directory." }
try {
    $python = "$drive\reverse\venv\Scripts\python.exe"
    # The script itself is reached through the alias only if the workspace is
    # Use the real path for the Python source; PyGhidra inputs use ASCII
    # drive paths through the temporary mapping.
    $script = Join-Path $PSScriptRoot 'probe_ghidra_mcp.py'
    $pythonArgs = @(
        $script,
        '--python', "$drive\reverse\venv\Scripts\python.exe",
        '--ghidra-install-dir', "$drive\reverse\ghidra\ghidra_12.1.4_PUBLIC",
        '--extension-jar', "$drive\reverse\plugin\extension\GhidraMCP\lib\GhidraMCP.jar",
        '--java-home', "$drive\reverse\jdk21\jdk-21.0.12.1+1",
        '--work-dir', "$drive\reverse\run21",
        '--output', "$drive\reverse\run21\mcp-evidence.json"
    )
    & $python @pythonArgs
    exit $LASTEXITCODE
}
finally {
    subst $drive /d | Out-Null
}
