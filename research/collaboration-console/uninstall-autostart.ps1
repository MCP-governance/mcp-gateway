<#
.SYNOPSIS
  Removes the scheduled task created by install-autostart.ps1.
  Does not touch any firewall rule -- remove that separately if you created one with -OpenFirewall.

.EXAMPLE
  powershell -File uninstall-autostart.ps1
  powershell -File uninstall-autostart.ps1 -Port 1000   # also prints the matching firewall rule name to remove
#>
param(
    [string]$TaskName = "MINT-CollaborationConsole",
    [int]$Port = 1000
)

foreach ($removeTask in @($TaskName, 'Local-Agent-Hub') | Select-Object -Unique) {
    if (Get-ScheduledTask -TaskName $removeTask -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $removeTask -Confirm:$false
        Write-Host "제거 완료: 예약 작업 $removeTask"
    } else {
        Write-Host "등록된 예약 작업이 없습니다: $removeTask"
    }
}

$firewallName = "MINT 협업 콘솔 ($Port)"
if (Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue) {
    Write-Host "방화벽 규칙이 남아 있습니다. 제거하려면 관리자 권한에서:"
    Write-Host "  Remove-NetFirewallRule -DisplayName '$firewallName'"
} else {
    Write-Host "방화벽 규칙 없음(또는 이미 제거됨): $firewallName"
}
