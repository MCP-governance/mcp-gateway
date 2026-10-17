param(
  [Parameter(Mandatory = $true)][string]$GatewayUrl,
  [Parameter(Mandatory = $true)][string]$EndpointId,
  [Parameter(Mandatory = $true)][string[]]$ScanPath,
  [string]$KeyFile,
  [string]$TailscaleNodeId
)
& (Join-Path $PSScriptRoot 'setup.ps1') -Observer -GatewayUrl $GatewayUrl -EndpointId $EndpointId `
    -ScanPath $ScanPath -KeyFile $KeyFile -TailscaleNodeId $TailscaleNodeId
