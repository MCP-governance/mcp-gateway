<#
.SYNOPSIS
  Registers the MINT development hub (collaboration console + WBS board) as a Windows scheduled task:
  starts pythonw directly without a console window, and lets Task Scheduler retry when it exits.

.DESCRIPTION
  This script never touches the firewall. Opening an inbound port needs administrator elevation and is a
  visible host change, so it is kept as a separate function (Open-ConsoleFirewallRule) that normal execution
  never calls. Run the script with -OpenFirewall, from an elevated PowerShell, when you have decided to let
  Tailscale teammates reach the port.

.EXAMPLE
  powershell -File install-autostart.ps1
  powershell -File install-autostart.ps1 -BindHost 100.111.15.33 -Port 1000
  powershell -File install-autostart.ps1 -OpenFirewall -Port 1000   # run elevated, separately, when approved
#>
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 1000,
    [string]$TaskName = "MINT-CollaborationConsole",
    [switch]$OpenFirewall
)

function Open-ConsoleFirewallRule {
    <#
    Admin-only and never called by a normal run of this script. Opens inbound TCP $Port, restricted to the
    Tailscale CGNAT range (100.64.0.0/10), so only tailnet teammates can reach the read-only viewer.
    #>
    param([int]$Port = 1000, [string]$RemoteRange = "100.64.0.0/10")
    $name = "MINT 협업 콘솔 ($Port)"
    if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
        Write-Host "이미 있음: $name"
        return
    }
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $Port -RemoteAddress $RemoteRange -Action Allow | Out-Null
    Write-Host "방화벽 인바운드 허용 생성: $name (원격 $RemoteRange만)"
}

if ($OpenFirewall) {
    Open-ConsoleFirewallRule -Port $Port
    return
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConsolePy = Join-Path $Root "console.py"
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $Pythonw)) {
    throw '협업 콘솔 .venv에 requirements.txt를 먼저 설치하세요.'
}
$RuntimeDir = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

# pythonw를 직접 추적해 PowerShell 콘솔 생성과 중간 실행기를 없앤다.
$action = New-ScheduledTaskAction -Execute $Pythonw `
    -Argument "-X utf8 `"$ConsolePy`" serve --host $BindHost --port $Port" -WorkingDirectory $Root
$currentUser = "$env:USERDOMAIN\$env:USERNAME"
# A logon trigger without -User means "any user" and needs elevation; this hub runs for the current user only.
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$triggerDaily = New-ScheduledTaskTrigger -Daily -At "09:00"
$triggerWatch = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 2)
# IgnoreNew keeps Task Scheduler itself from double-starting; RestartCount covers a launch that fails outright.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -Hidden

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($triggerLogon, $triggerDaily, $triggerWatch) -Settings $settings -User $currentUser -ErrorAction Stop `
    -Force -Description "MINT 개발 협업 콘솔 + WBS 현황판. 창 없이 실행하며 로그온·매일 09:00·장애 시 재시작." | Out-Null

$workerAction = New-ScheduledTaskAction -Execute $Pythonw -Argument "-X utf8 `"$ConsolePy`" worker" -WorkingDirectory $Root
Register-ScheduledTask -TaskName 'Local-Agent-Hub' -Action $workerAction -Trigger @($triggerLogon, $triggerWatch) -Settings $settings -User $currentUser -ErrorAction Stop `
    -Force -Description "MINT 계층 협업 실행기. 기존 1000번 콘솔과 SQLite 상태를 사용합니다." | Out-Null

$dispatchAction = New-ScheduledTaskAction -Execute $Pythonw -Argument "-X utf8 `"$(Join-Path $Root 'dispatcher.py')`"" -WorkingDirectory $Root
$dispatchTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'MINT-AutoDispatch' -Action $dispatchAction -Trigger @($triggerLogon, $dispatchTrigger) -Settings $settings -User $currentUser -ErrorAction Stop `
    -Force -Description '기존 큐 선제 배정·사용량 보고. 1분 확인, 실제 모델 호출은 작업당 제한.' | Out-Null

Write-Host "등록 완료: $TaskName (호스트 $BindHost, 포트 $Port)"
Write-Host "등록 완료: Local-Agent-Hub (모델 호출·한도·체크포인트 관리)"
Write-Host "지금 바로 실행: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "방화벽은 이 실행에서 건드리지 않았습니다. 팀원 접속을 열기로 했다면 관리자 권한에서 별도로:"
Write-Host "  powershell -File install-autostart.ps1 -OpenFirewall -Port $Port"
