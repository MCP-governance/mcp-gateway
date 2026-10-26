$ErrorActionPreference = 'Stop'
$script:PowerShellExe = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Quote-EndpointArgument([string]$Value) {
    if ($Value.Contains('"') -or $Value.EndsWith('\')) { throw '경로 형식 오류' }
    return '"' + $Value + '"'
}

function Protect-EndpointDiagnostic([string]$Text, [string[]]$Secrets = @()) {
    foreach ($secret in $Secrets) {
        if ($secret) { $Text = $Text.Replace($secret, '[redacted]') }
    }
    $Text = [regex]::Replace($Text, '(?im)^.*(?:authorization|bearer|password|passwd|secret|(?:device|enrollment|access|refresh)[_-]?(?:key|token)).*$', '[redacted]')
    return $Text
}

function Repair-EndpointWorkDirectory([string]$Path, [string]$Sid) {
    Assert-EndpointNoLinks $Path
    [IO.Directory]::CreateDirectory($Path) | Out-Null
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($principal in @('S-1-5-18', 'S-1-5-32-544', $Sid)) {
        $rights = if ($principal -eq $Sid) { 'Modify' } else { 'FullControl' }
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
            (New-Object Security.Principal.SecurityIdentifier($principal)), $rights, 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
    }
    # Do not reset children: the installer's credential folders must keep their protected DACLs.
    [IO.Directory]::SetAccessControl($Path, $acl)
}

function Set-EndpointAcl([string]$Path, [string]$Sid, [switch]$Managed) {
    $grants = @('*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F')
    if ($Managed) { $grants += '*S-1-5-32-545:(OI)(CI)RX' }
    else { $grants += "*${Sid}:(OI)(CI)F" }
    # icacls /T writes (OI)(CI) grants onto existing files as empty DACLs, which then block even administrators
    # (an elevated UAC token lacks the restore privilege). Grant the root only and let every child inherit it.
    & icacls.exe $Path '/inheritance:r' '/grant:r' @grants '/Q' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '설치 폴더 권한 적용 실패' }
    if (Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1) {
        & icacls.exe (Join-Path $Path '*') '/reset' '/T' '/Q' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '설치 폴더 권한 적용 실패' }
    }
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

function New-EndpointGatewayRequest([string]$Url, [string]$Certificate = '', [string]$Fingerprint = '') {
    if (-not ('EndpointKit.GatewayTls' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Net;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.RegularExpressions;
namespace EndpointKit {
    public static class GatewayTls {
        static string Digest(byte[] data) {
            using (var sha = SHA256.Create()) { return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }
        }
        public static X509Certificate2 Root(string pem, string fingerprint) {
            var match = Regex.Match(pem, @"\A\s*-----BEGIN CERTIFICATE-----([A-Za-z0-9+/=\s]+)-----END CERTIFICATE-----\s*\z");
            if (!match.Success || !Regex.IsMatch(fingerprint.Replace(":", ""), @"\A[0-9a-fA-F]{64}\z"))
                throw new ArgumentException("Invalid CA or SHA-256");
            var root = new X509Certificate2(Convert.FromBase64String(match.Groups[1].Value));
            if (Digest(root.RawData) != fingerprint.Replace(":", "").ToLowerInvariant())
                throw new ArgumentException("CA SHA-256 mismatch");
            return root;
        }
        public static bool Validate(X509Certificate certificate, X509Chain remote, SslPolicyErrors errors, X509Certificate2 root) {
            if (certificate == null || (errors & ~SslPolicyErrors.RemoteCertificateChainErrors) != 0) return false;
            using (var chain = new X509Chain()) {
                chain.ChainPolicy.ExtraStore.Add(root);
                if (remote != null) foreach (var element in remote.ChainElements) chain.ChainPolicy.ExtraStore.Add(element.Certificate);
                // Caddy's private CA publishes no revocation service. Expiry, usage and signatures remain checked.
                chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
                chain.ChainPolicy.VerificationFlags = X509VerificationFlags.AllowUnknownCertificateAuthority;
                chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
                if (!chain.Build(new X509Certificate2(certificate))) return false;
                foreach (var status in chain.ChainStatus)
                    if ((status.Status & ~X509ChainStatusFlags.UntrustedRoot) != 0) return false;
                return chain.ChainElements.Count > 0 && Digest(chain.ChainElements[chain.ChainElements.Count - 1].Certificate.RawData) == Digest(root.RawData);
            }
        }
        public static HttpWebRequest Create(string url, string pem, string fingerprint) {
            var uri = new Uri(url);
            if (uri.UserInfo.Length != 0 || (uri.Scheme != "https" && !(uri.Scheme == "http" && uri.IsLoopback)))
                throw new ArgumentException("HTTPS required");
            X509Certificate2 root = null;
            if (pem.Length != 0 || fingerprint.Length != 0) root = Root(pem, fingerprint);
            var request = (HttpWebRequest)WebRequest.Create(uri);
            request.AllowAutoRedirect = false;
            request.Proxy = null;
            request.Timeout = 6000;
            request.ReadWriteTimeout = 6000;
            // Windows PowerShell's .NET Framework selects protocols per process, not per request.
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            if (root != null) request.ServerCertificateValidationCallback = (sender, cert, chain, errors) => Validate(cert, chain, errors, root);
            return request;
        }
    }
}
'@
    }
    return [EndpointKit.GatewayTls]::Create($Url, $Certificate, $Fingerprint)
}

function Test-EndpointGateway([string]$Url, [string]$Certificate = '', [string]$Fingerprint = '') {
    $uri = [Uri]$Url
    if (-not $uri.IsAbsoluteUri -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') {
        throw '게이트웨이 주소 형식 오류'
    }
    if ($uri.Scheme -ne 'https') {
        $address = $null
        $httpAllowed = $uri.Host -eq 'localhost'
        if ([Net.IPAddress]::TryParse($uri.Host, [ref]$address)) {
            $httpAllowed = [Net.IPAddress]::IsLoopback($address)
        }
        if ($uri.Scheme -ne 'http' -or -not $httpAllowed) { throw '암호화 연결 또는 승인된 사내망 주소 필요' }
    }
    $request = New-EndpointGatewayRequest ($Url.TrimEnd('/') + '/api/health') $Certificate $Fingerprint
    $tcp = New-Object Net.Sockets.TcpClient
    try {
        $pending = $tcp.BeginConnect($uri.DnsSafeHost, $uri.Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(4000)) { throw '게이트웨이 연결 시간 초과' }
        try { $tcp.EndConnect($pending) } catch { throw '게이트웨이 이름 또는 포트 연결 실패' }
    } finally { $tcp.Dispose() }
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

function Remove-EndpointFiles([string]$Root, [string[]]$OwnedFiles = @()) {
    $resolved = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $machine = Join-Path $env:ProgramFiles 'MCPGatewayManaged'
    $local = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\') + '\'
    if ($resolved -ne $machine -and -not $resolved.StartsWith($local, [StringComparison]::OrdinalIgnoreCase)) { throw '제거 경로 확인 실패' }
    Assert-EndpointTree $resolved
    if (-not (Test-Path -LiteralPath $resolved)) { return }
    $manifestPath = Join-Path $resolved '.endpoint-kit'
    $manifest = if (Test-Path -LiteralPath $manifestPath) {
        Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } elseif ($resolved -eq $machine -and $OwnedFiles.Count) {
        @{ product = 'MCPGatewayEndpoint'; files = $OwnedFiles }
    } else { throw '설치 소유 정보 확인 실패' }
    if ($manifest.product -ne 'MCPGatewayEndpoint') { throw '설치 소유 정보 확인 실패' }
    foreach ($name in @($manifest.files) + @('.endpoint-kit')) {
        $target = [IO.Path]::GetFullPath((Join-Path $resolved $name))
        if (-not $target.StartsWith($resolved + '\', [StringComparison]::OrdinalIgnoreCase)) { throw '제거 경로 확인 실패' }
        if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
    }
    # Installs before -B left bytecode of the owned modules; anything else in the cache is not ours to delete.
    $cache = Join-Path $resolved '__pycache__'
    if (Test-Path -LiteralPath $cache) {
        $stems = @($manifest.files | Where-Object { $_ -like '*.py' } | ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_) })
        foreach ($item in Get-ChildItem -LiteralPath $cache -Force -File) {
            if ($item.Extension -eq '.pyc' -and $item.Name.Split('.')[0] -in $stems) { Remove-Item -LiteralPath $item.FullName -Force }
        }
    }
    foreach ($name in @('python', 'harness', '__pycache__')) {
        $target = Join-Path $resolved $name
        if ((Test-Path -LiteralPath $target) -and -not (Get-ChildItem -LiteralPath $target -Force)) {
            Remove-Item -LiteralPath $target
        }
    }
    if (-not (Get-ChildItem -LiteralPath $resolved -Force)) { Remove-Item -LiteralPath $resolved }
}

# Screen text of the wizard and the tray, Korean first with an English switch (D-239). Labels only.
$script:EndpointText = @{
    ko = @{ product = 'MCP 연결'; connected = '연결됨'; disconnected = '연결 끊김'; blocked = '엔드포인트에서 차단';
        preparing = '연결 준비 중'; next_preparing = '잠시 기다리세요 · 서비스가 첫 보고를 보내는 중입니다';
        status = '상태 창'; check = '연결 확인'; login = '모델 로그인'; reconnect = '다시 연결'; recent = '최근 차단';
        open_console = '콘솔 열기'; language = 'English'; remove = '제거'; close = '닫기';
        connection = '연결 상태'; management = '관리 상태'; way = '연결 방식'; servers = '승인 서버'; harness = '하네스';
        reported = '최근 보고'; model = '모델 응답'; tools = '도구'; server = '서버 연결'; gateway = '게이트웨이'; next = '다음 할 일';
        mode_simple = '간편 모드 · 게이트웨이 판정'; mode_isolated = '격리 계정'; ok = '정상'; failed = '실패';
        waiting = '활성화 대기'; not_checked = '확인 전'; checking = '확인 중'; check_failed = '확인 응답 없음 · [연결 확인]을 다시 누르세요';
        gateway_ok = '게이트웨이 응답 정상'; uac_cancelled = '관리자 권한 확인이 취소됐습니다 · [다시 연결]을 다시 누르세요';
        restart_service = '이 PC의 연결 서비스가 멈춰 있습니다. 관리자 권한으로 다시 시작할까요?';
        no_harness = '{0}을(를) 찾지 못했습니다. 설치한 뒤 다시 누르세요.';
        next_reconnect = '게이트웨이에 연결되지 않았습니다 · [다시 연결]을 누르세요';
        next_removed = '콘솔에서 새 설치 파일을 받아 실행하세요';
        next_pending = '관리자 활성화 대기 · 활성화되면 자동으로 연결됩니다';
        next_quarantined = '격리됨 · 관리자에게 해제를 요청하세요';
        next_revoked = '등록 해제됨 · [제거] 뒤 콘솔에서 새 설치 파일을 받으세요';
        next_login = '모델 응답 없음 · [모델 로그인]을 누르세요';
        next_check = '[연결 확인]을 누르세요'; next_ready = 'claude 또는 codex를 실행하세요';
        start = '시작'; install = '설치'; retry = '다시 시도'; step = '단계'; location = '설치 위치'; account = '대상 계정';
        scope = '관측 범위'; permission = '설치 권한'; progress = '진행률'; result = '결과'; log = '로그 파일';
        isolated = '고급: 격리 계정 (관리자 활성화)'; permission_simple = '관리자 권한 확인 1회 · 지금 계정 그대로';
        permission_isolated = '관리자 권한 · 격리 계정 로그아웃 필요'; title_install = '엔드포인트 설치'; title_remove = '엔드포인트 제거';
        done_install = '설치 완료'; done_remove = '제거 완료'; checking_gateway = '게이트웨이 연결 확인'; confirm = '설치 위치 · 관측 범위 확인' }
    en = @{ product = 'MCP connection'; connected = 'Connected'; disconnected = 'Disconnected'; blocked = 'Blocked on this PC';
        preparing = 'Preparing'; next_preparing = 'Wait a moment · the service is sending its first report';
        status = 'Status window'; check = 'Check connection'; login = 'Model sign-in'; reconnect = 'Reconnect'; recent = 'Recent blocks';
        open_console = 'Open console'; language = '한국어'; remove = 'Remove'; close = 'Close';
        connection = 'Connection'; management = 'Management'; way = 'Mode'; servers = 'Approved servers'; harness = 'Harnesses';
        reported = 'Last report'; model = 'Model answer'; tools = 'Tools'; server = 'Server'; gateway = 'Gateway'; next = 'Next step';
        mode_simple = 'Simple mode · decided by the gateway'; mode_isolated = 'Isolated account'; ok = 'OK'; failed = 'failed';
        waiting = 'Waiting for activation'; not_checked = 'Not checked'; checking = 'Checking'; check_failed = 'No answer · press [Check connection] again';
        gateway_ok = 'Gateway answers'; uac_cancelled = 'Administrator approval was cancelled · press [Reconnect] again';
        restart_service = 'The connection service on this PC has stopped. Restart it as administrator?';
        no_harness = '{0} was not found. Install it, then press again.';
        next_reconnect = 'Not connected to the gateway · press [Reconnect]';
        next_removed = 'Download a new installer from the console and run it';
        next_pending = 'Waiting for an administrator · connects by itself once activated';
        next_quarantined = 'Quarantined · ask an administrator to release it';
        next_revoked = 'Unregistered · [Remove], then download a new installer from the console';
        next_login = 'No model answer · press [Model sign-in]';
        next_check = 'Press [Check connection]'; next_ready = 'Run claude or codex';
        start = 'Start'; install = 'Install'; retry = 'Retry'; step = 'Step'; location = 'Location'; account = 'Account';
        scope = 'Observed'; permission = 'Permission'; progress = 'Progress'; result = 'Result'; log = 'Log file';
        isolated = 'Advanced: isolated account (administrator activation)'; permission_simple = 'One administrator approval · this account as it is';
        permission_isolated = 'Administrator · isolated account signed out'; title_install = 'Endpoint setup'; title_remove = 'Endpoint removal';
        done_install = 'Installed'; done_remove = 'Removed'; checking_gateway = 'Checking the gateway'; confirm = 'Location and scope' }
}

function Get-EndpointText([string]$Key, [string]$Language = 'ko') {
    $table = $script:EndpointText[$(if ($Language -eq 'en') { 'en' } else { 'ko' })]
    if ($table.ContainsKey($Key)) { return $table[$Key] }
    return $Key
}

# What failed is the worker's fixed reason; this is the one line of what to press next.
function Get-EndpointNextAction([string]$Reason, [string]$Language = 'ko') {
    $en = $Language -eq 'en'
    switch -Regex ($Reason) {
        '연결 시간 초과|이름 또는 포트|상태 조회|상태 응답|준비 상태' { if ($en) { return 'Check the network (VPN), then press [Retry]' } return '네트워크(VPN)를 확인하고 [다시 시도]를 누르세요' }
        '인증서' { if ($en) { return 'Ask IT about the gateway certificate' } return '조직 IT에 게이트웨이 인증서를 문의하세요' }
        '이미 연결|등록 자격|새 설치 파일|불일치' { if ($en) { return 'Download a new installer from the console and run it' } return '콘솔에서 새 설치 파일을 받아 실행하세요' }
        '직원 설정의 관리 구간' { if ($en) { return 'Ask IT to check the settings backup, then retry' } return '설정 백업을 조직 IT에 전달해 확인한 뒤 다시 실행하세요' }
        '권한 승인 취소|관리자 권한 필요' { if ($en) { return 'Press [Retry] and choose Yes on the administrator prompt' } return '[다시 시도]를 누르고 관리자 권한 확인에서 [예]를 누르세요' }
        '진행 중' { if ($en) { return 'Wait a moment, then press [Retry]' } return '잠시 뒤 [다시 시도]를 누르세요' }
        '로그아웃' { if ($en) { return 'Sign the isolated account out, then press [Retry]' } return '격리 계정을 로그아웃한 뒤 [다시 시도]를 누르세요' }
        '하네스' { if ($en) { return 'Install Claude Code or Codex, then press [Retry]' } return 'Claude Code 또는 Codex를 설치한 뒤 [다시 시도]를 누르세요' }
        default { if ($en) { return 'Press [Retry]; if it repeats, send the log file to IT' } return '[다시 시도] · 반복되면 로그 파일을 조직 IT에 전달하세요' }
    }
}
