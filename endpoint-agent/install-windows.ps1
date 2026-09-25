param(
  [Parameter(Mandatory = $true)][string]$GatewayUrl,
  [Parameter(Mandatory = $true)][string]$EndpointId,
  [Parameter(Mandatory = $true)][string[]]$ScanPath,
  [string]$KeyFile
)
$ErrorActionPreference = 'Stop'
$python = (Get-Command python.exe -ErrorAction Stop).Source
$directory = Join-Path $env:LOCALAPPDATA 'MCPGatewayEndpoint'
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $directory '/inheritance:r' '/grant:r' "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '/T' | Out-Null
if ($LASTEXITCODE -ne 0) { throw '설치 경로 ACL 적용에 실패했습니다.' }
$arguments = @((Join-Path $PSScriptRoot 'install.py'), '--gateway-url', $GatewayUrl,
               '--endpoint-id', $EndpointId, '--no-verify', '--windows-wrapper')
foreach ($path in $ScanPath) { $arguments += @('--scan-path', $path) }
if ($KeyFile) { $arguments += @('--key-file', $KeyFile) }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw '엔드포인트 설치가 실패했습니다.' }

& icacls.exe $directory '/inheritance:r' '/grant:r' "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '/T' | Out-Null
if ($LASTEXITCODE -ne 0) { throw '설정 파일 ACL 적용에 실패했습니다.' }

$agent = Join-Path $directory 'agent.py'
$config = Join-Path $directory 'config.json'
& $python $agent '--config' $config '--once'
if ($LASTEXITCODE -ne 0) { throw '엔드포인트 1회 보고가 실패했습니다. Gateway 경로·장치 키를 확인하세요.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$agent`" --config `"$config`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$name = "MCPGatewayEndpoint-$EndpointId"
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $name
Write-Host "엔드포인트 작업 등록 완료: $name"
