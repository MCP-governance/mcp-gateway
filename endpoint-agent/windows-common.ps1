$ErrorActionPreference = 'Stop'
$script:PowerShellExe = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Quote-EndpointArgument([string]$Value) {
    if ($Value.Contains('"') -or $Value.EndsWith('\')) { throw '경로 형식 오류' }
    return '"' + $Value + '"'
}

function Set-EndpointAcl([string]$Path, [string]$Sid, [switch]$Managed) {
    $grants = @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F')
    if ($Managed) { $grants += '*S-1-5-32-545:(OI)(CI)RX' }
    else { $grants += "*${Sid}:(OI)(CI)F" }
    & icacls.exe $Path '/inheritance:r' '/grant:r' @grants '/T' '/Q' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '설치 폴더 권한 적용 실패' }
    if ($Managed) {
        & icacls.exe $Path '/setowner' '*S-1-5-32-544' '/T' '/Q' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '설치 폴더 권한 적용 실패' }
    }
}

function Assert-EndpointTree([string]$Path) {
    $ancestor = [IO.Path]::GetFullPath($Path)
    while ($ancestor) {
        if ((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw '설치 경로 연결 파일 확인 필요'
        }
        $parent = [IO.Directory]::GetParent($ancestor)
        $ancestor = if ($parent) { $parent.FullName } else { $null }
    }
    if (Test-Path -LiteralPath $Path) {
        $items = @((Get-Item -LiteralPath $Path)) + @(Get-ChildItem -LiteralPath $Path -Force -Recurse)
        if ($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
            throw '설치 경로 연결 파일 확인 필요'
        }
    }
}

function Test-EndpointGateway([string]$Url) {
    $uri = [Uri]$Url
    if (-not $uri.IsAbsoluteUri -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') {
        throw '게이트웨이 주소 형식 오류'
    }
    if ($uri.Scheme -ne 'https') {
        $address = $null
        $httpAllowed = $uri.Host -eq 'localhost'
        if ([Net.IPAddress]::TryParse($uri.Host, [ref]$address)) {
            $bytes = $address.GetAddressBytes()
            $httpAllowed = [Net.IPAddress]::IsLoopback($address) -or ($bytes.Length -eq 4 -and $bytes[0] -eq 100 -and $bytes[1] -ge 64 -and $bytes[1] -le 127)
        }
        if ($uri.Scheme -ne 'http' -or -not $httpAllowed) { throw '암호화 연결 또는 승인된 사내망 주소 필요' }
    }
    $tcp = New-Object Net.Sockets.TcpClient
    try {
        $pending = $tcp.BeginConnect($uri.DnsSafeHost, $uri.Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(4000)) { throw '게이트웨이 연결 시간 초과' }
        try { $tcp.EndConnect($pending) } catch { throw '게이트웨이 이름 또는 포트 연결 실패' }
    } finally { $tcp.Dispose() }
    $request = [Net.HttpWebRequest]::Create($Url.TrimEnd('/') + '/api/health')
    $request.AllowAutoRedirect = $false
    $request.Proxy = $null
    $request.Timeout = 6000
    $request.ReadWriteTimeout = 6000
    try {
        $response = $request.GetResponse()
        try {
            if ([int]$response.StatusCode -ne 200) { throw '게이트웨이 상태 응답 오류' }
            $reader = New-Object IO.StreamReader($response.GetResponseStream())
            try { $health = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            if ($health.status -ne 'ok') { throw '게이트웨이 준비 상태 확인 필요' }
        } finally { $response.Dispose() }
    } catch [Net.WebException] {
        if ($_.Exception.Status -eq [Net.WebExceptionStatus]::TrustFailure -or $_.Exception.Status -eq [Net.WebExceptionStatus]::SecureChannelFailure) {
            throw '게이트웨이 인증서 확인 실패'
        }
        throw '게이트웨이 상태 조회 실패'
    }
}

function Install-EndpointRuntime([string]$Source, [string]$Target) {
    $pin = Get-Content -LiteralPath (Join-Path $Source 'windows-python.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($pin.version -ne '3.13.16' -or $pin.architecture -ne 'amd64' -or
        $pin.sha256 -ne '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297' -or $pin.pth -ne 'python313._pth') {
        throw '실행 파일 판본 확인 실패'
    }
    $zip = Join-Path $Source 'python.zip'
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin.sha256) { throw '실행 파일 무결성 확인 실패' }
    Assert-EndpointTree $Target
    $runtime = Join-Path $Target 'python'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $runtime -Force
    # Site hooks could load employee-controlled code into a credential helper.
    [IO.File]::WriteAllText((Join-Path $runtime $pin.pth), "python313.zip`n.`n..`n#import site`n", [Text.Encoding]::ASCII)
    return Join-Path $runtime 'python.exe'
}

function Stop-EndpointTask([string]$Name) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if (-not $task) { return }
    Stop-ScheduledTask -TaskName $Name
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ((Get-ScheduledTask -TaskName $Name).State -eq 'Running') {
        if ([DateTime]::UtcNow -gt $deadline) { throw '엔드포인트 종료 시간 초과' }
        Start-Sleep -Milliseconds 100
    }
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false
}

function Register-EndpointTray([string]$SettingsPath, [string]$Sid, [string]$ProgramDirectory) {
    $root = $ProgramDirectory
    $action = New-ScheduledTaskAction -Execute $script:PowerShellExe -Argument ('-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File ' +
        (Quote-EndpointArgument (Join-Path $root 'tray.ps1')) + ' -SettingsPath ' + (Quote-EndpointArgument $SettingsPath))
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $Sid
    $principal = New-ScheduledTaskPrincipal -UserId $Sid -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "MCPGatewayTray-$Sid" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
}

function Remove-EndpointFiles([string]$Root) {
    $resolved = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $machine = Join-Path $env:ProgramFiles 'MCPGatewayManaged'
    $local = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\') + '\'
    if ($resolved -ne $machine -and -not $resolved.StartsWith($local, [StringComparison]::OrdinalIgnoreCase)) { throw '제거 경로 확인 실패' }
    Assert-EndpointTree $resolved
    $manifestPath = Join-Path $resolved '.endpoint-kit'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw '설치 소유 정보 확인 실패' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.product -ne 'MCPGatewayEndpoint') { throw '설치 소유 정보 확인 실패' }
    foreach ($name in @($manifest.files) + @('.endpoint-kit')) {
        $target = [IO.Path]::GetFullPath((Join-Path $resolved $name))
        if (-not $target.StartsWith($resolved + '\', [StringComparison]::OrdinalIgnoreCase)) { throw '제거 경로 확인 실패' }
        if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
    }
    foreach ($name in @('python', 'harness')) {
        $target = Join-Path $resolved $name
        if ((Test-Path -LiteralPath $target) -and -not (Get-ChildItem -LiteralPath $target -Force)) {
            Remove-Item -LiteralPath $target
        }
    }
    if (-not (Get-ChildItem -LiteralPath $resolved -Force)) { Remove-Item -LiteralPath $resolved }
}
