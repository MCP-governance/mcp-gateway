param(
  [Parameter(Mandatory = $true)][string]$GatewayUrl,
  [Parameter(Mandatory = $true)][string]$EndpointId,
  [Parameter(Mandatory = $true)][string[]]$ScanPath,
  [string]$KeyFile,
  [string]$TailscaleNodeId
)
$ErrorActionPreference = 'Stop'
# The WindowsApps python.exe is a Store installer stub, not an interpreter.
$python = Get-Command python.exe -All -ErrorAction SilentlyContinue |
  Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1 -ExpandProperty Source
if (-not $python) { throw 'Python 3.10 이상을 설치하세요.' }
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }
$directory = Join-Path $env:LOCALAPPDATA 'MCPGatewayEndpoint'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $directory '/inheritance:r' '/grant:r' "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '/T' | Out-Null
if ($LASTEXITCODE -ne 0) { throw '설치 경로 ACL 적용에 실패했습니다.' }
$arguments = @((Join-Path $PSScriptRoot 'install.py'), '--gateway-url', $GatewayUrl,
               '--endpoint-id', $EndpointId, '--no-verify', '--windows-wrapper')
foreach ($path in $ScanPath) { $arguments += @('--scan-path', $path) }
if ($KeyFile) { $arguments += @('--key-file', $KeyFile) }
if ($TailscaleNodeId) { $arguments += @('--tailscale-node-id', $TailscaleNodeId) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw '엔드포인트 설치가 실패했습니다.' }

& icacls.exe $directory '/inheritance:r' '/grant:r' "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '/T' | Out-Null
if ($LASTEXITCODE -ne 0) { throw '설정 파일 ACL 적용에 실패했습니다.' }

$agent = Join-Path $directory 'agent.py'
$config = Join-Path $directory 'config.json'
& $python $agent '--config' $config '--once'
if ($LASTEXITCODE -ne 0) { throw '엔드포인트 1회 보고가 실패했습니다. 게이트웨이 주소·장치 키를 확인하세요.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
# pythonw: no console window at every logon.
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$agent`" --config `"$config`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$name = "MCPGatewayEndpoint-$EndpointId"
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $name
Write-Host "엔드포인트 작업 등록 완료: $name"
