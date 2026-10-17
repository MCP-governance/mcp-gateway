$ErrorActionPreference = 'Stop'

function Get-EndpointInstallerPaths {
    return @{
        code = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'MCPGatewayInstaller'
        state = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'MCPGatewayInstaller'
    }
}

function Assert-EndpointNoLinks([string]$Path) {
    $item = [IO.Path]::GetFullPath($Path)
    while ($item) {
        if ((Test-Path -LiteralPath $item) -and ((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw '승인 설치 경로 연결 파일 거부'
        }
        $parent = [IO.Directory]::GetParent($item)
        $item = if ($parent) { $parent.FullName } else { $null }
    }
}

function Assert-EndpointTrustedAcl($Acl) {
    $trusted = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    if ($Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw '승인 설치 경로 소유자 확인 실패' }
    $write = 0x2 -bor 0x4 -bor 0x10 -bor 0x40 -bor 0x100 -bor 0x10000 -bor 0x40000 -bor 0x80000 -bor 0x10000000 -bor 0x40000000
    foreach ($rule in $Acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $trusted -and
            ([long]$rule.FileSystemRights -band $write)) { throw '승인 설치 경로 쓰기 권한 거부' }
    }
}

function Assert-EndpointProtectedPath([string]$Path) {
    Assert-EndpointNoLinks $Path
    if (-not (Test-Path -LiteralPath $Path)) { throw '조직 승인 설치기 필요' }
    Assert-EndpointTrustedAcl (Get-Acl -LiteralPath $Path)
    $parent = [IO.Directory]::GetParent([IO.Path]::GetFullPath($Path))
    while ($parent) {
        $acl = Get-Acl -LiteralPath $parent.FullName
        $trusted = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
        if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw '승인 설치 상위 경로 소유자 확인 실패' }
        foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            $inheritOnly = $rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly
            if (-not $inheritOnly -and $rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $trusted -and
                ([long]$rule.FileSystemRights -band (0x40 -bor 0x10000 -bor 0x40000 -bor 0x80000 -bor 0x10000000))) {
                throw '승인 설치 상위 경로 교체 권한 거부'
            }
        }
        $parent = $parent.Parent
    }
}

function New-EndpointAccessDescriptor([string]$ReaderSid, [bool]$Directory) {
    $acl = if ($Directory) { New-Object Security.AccessControl.DirectorySecurity } else { New-Object Security.AccessControl.FileSecurity }
    $inheritance = if ($Directory) { 'ContainerInherit,ObjectInherit' } else { 'None' }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
            (New-Object Security.Principal.SecurityIdentifier($sid)), 'FullControl', $inheritance, 'None', 'Allow')))
    }
    if ($ReaderSid) {
        if ($ReaderSid -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$') { throw '대상 계정 식별자 확인 실패' }
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
            (New-Object Security.Principal.SecurityIdentifier($ReaderSid)), 'ReadAndExecute', $inheritance, 'None', 'Allow')))
    }
    return $acl
}

function New-EndpointProtectedDirectory([string]$Path, [string]$ReaderSid) {
    Assert-EndpointNoLinks $Path
    $acl = New-EndpointAccessDescriptor $ReaderSid $true
    if (Test-Path -LiteralPath $Path) { Assert-EndpointProtectedPath $Path }
    [IO.Directory]::CreateDirectory($Path, $acl) | Out-Null
    # Existing explicit grants must not survive a repair or an upgrade.
    Set-Acl -LiteralPath $Path -AclObject $acl
    Assert-EndpointProtectedPath $Path
    if ($ReaderSid) {
        foreach ($file in Get-ChildItem -LiteralPath $Path -Force) {
            if ($file.PSIsContainer) { throw '개인 상태 경로 하위 폴더 거부' }
            Assert-EndpointProtectedPath $file.FullName
            Set-Acl -LiteralPath $file.FullName -AclObject (New-EndpointAccessDescriptor $ReaderSid $false)
        }
    }
}

function Assert-EndpointInstalledRuntime([string]$Root) {
    $paths = Get-EndpointInstallerPaths
    $runtime = Join-Path $Root 'python'
    Assert-EndpointProtectedPath $runtime
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead((Join-Path $paths.code 'python.zip'))
    try {
        $names = @($archive.Entries.FullName)
        if (Compare-Object ($names | Sort-Object) (@(Get-ChildItem -LiteralPath $runtime -Force | ForEach-Object Name) | Sort-Object)) {
            throw '설치 실행 파일 목록 확인 실패'
        }
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -notmatch '^[A-Za-z0-9_.-]+$') { throw '실행 파일 이름 거부' }
            $path = Join-Path $runtime $entry.FullName
            Assert-EndpointProtectedPath $path
            if ($entry.FullName -eq 'python313._pth') {
                if ([IO.File]::ReadAllText($path) -cne "python313.zip`n.`n..`n#import site`n") { throw '실행 경로 설정 확인 실패' }
            } else {
                $sha = [Security.Cryptography.SHA256]::Create()
                $stream = $entry.Open()
                try { $expected = ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '') }
                finally { $stream.Dispose(); $sha.Dispose() }
                if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $expected) { throw '설치 실행 파일 무결성 확인 실패' }
            }
        }
    } finally { $archive.Dispose() }
}

function Assert-EndpointFileHashes([string]$Root, $Approval, [string[]]$Names) {
    foreach ($name in $Names) {
        if ($name -notmatch '^[A-Za-z0-9_.-]+$') { throw '승인 설치 파일 이름 거부' }
        $path = Join-Path $Root $name
        Assert-EndpointProtectedPath $path
        $expected = $Approval.files.$name
        if ($expected -notmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw '조직 승인 설치 파일 무결성 확인 실패'
        }
    }
}

function Get-EndpointApprovedKit {
    $paths = Get-EndpointInstallerPaths
    Assert-EndpointProtectedPath $paths.code
    Assert-EndpointProtectedPath $paths.state
    $approvalPath = Join-Path $paths.state 'approved-windows-kit.json'
    Assert-EndpointProtectedPath $approvalPath
    $approval = Get-Content -LiteralPath $approvalPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $required = @('install.cmd', 'setup.ps1', 'windows-common.ps1', 'windows-worker.ps1', 'windows-trust.ps1', 'tray.ps1',
        'runtime-check.py', 'windows_status.py', 'install.py', 'install-windows.ps1', 'managed-windows.py',
        'agent.py', 'os-observer-windows.py', 'python.zip', 'windows-python.json')
    $names = @($approval.files.PSObject.Properties.Name)
    $caFiles = @('root.crt', 'root.sha256', 'mcpgw_pc.py')
    if (@($names | Where-Object { $_ -in $caFiles }).Count) { $required += $caFiles }
    if ($approval.schema -ne 1 -or (Compare-Object ($required | Sort-Object) ($names | Sort-Object)) -or -not $approval.gateway_url) {
        throw '조직 승인 설치 목록 확인 실패'
    }
    foreach ($item in Get-ChildItem -LiteralPath $paths.code -Force) {
        if ($item.PSIsContainer -or $item.Name -notin ($required + @('windows-kit-manifest.json'))) { throw '승인 설치 경로 추가 파일 거부' }
        Assert-EndpointProtectedPath $item.FullName
    }
    Assert-EndpointFileHashes $paths.code $approval $required
    return $approval
}

function Remove-EndpointCompilerTemp([string]$Path) {
    if (-not $Path) { return }
    $Path = [IO.Path]::GetFullPath($Path)
    if ((Split-Path $Path) -ne (Get-EndpointInstallerPaths).state -or (Split-Path $Path -Leaf) -notmatch '^temp-[a-f0-9]{32}$') {
        throw '설치 임시 경로 제거 거부'
    }
    if (Test-Path -LiteralPath $Path) {
        Assert-EndpointProtectedPath $Path
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Read-EndpointDataFile([string]$Path, [int]$Maximum) {
    $Path = [IO.Path]::GetFullPath($Path)
    Assert-EndpointNoLinks $Path
    if (-not ('EndpointKit.NativePath' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
namespace EndpointKit {
    public static class NativePath {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        public static extern uint GetFinalPathNameByHandle(SafeFileHandle handle, StringBuilder path, uint length, uint flags);
    }
}
'@
    }
    $inputFile = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    try {
        $buffer = New-Object Text.StringBuilder(32768)
        $length = [EndpointKit.NativePath]::GetFinalPathNameByHandle($inputFile.SafeFileHandle, $buffer, 32768, 0)
        if ($length -eq 0 -or $length -ge 32768 -or $buffer.ToString() -ne ('\\?\' + $Path)) { throw '설치 요청 경로 변경 거부' }
        if ($inputFile.Length -gt $Maximum) { throw '설치 요청 크기 초과' }
        $reader = New-Object IO.StreamReader($inputFile, [Text.Encoding]::UTF8)
        try {
            try { return $reader.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop }
            catch { throw '설치 요청 형식 확인 실패' }
        } finally { $reader.Dispose() }
    } finally { $inputFile.Dispose() }
}

function Read-EndpointManagedRequest([string]$RequestPath, $Approval, [string]$RequesterSid) {
    $RequestPath = [IO.Path]::GetFullPath($RequestPath)
    Assert-EndpointNoLinks $RequestPath
    if ($RequesterSid -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$') { throw '설치 요청 계정 확인 실패' }
    $profile = (Get-ItemProperty -LiteralPath ('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\' + $RequesterSid)).ProfileImagePath
    $work = Split-Path $RequestPath
    $id = Split-Path $work -Leaf
    if ($id -notmatch '^[a-f0-9]{32}$' -or $RequestPath -ne (Join-Path $profile "AppData\Local\MCPGatewaySetup\$id\request.json")) {
        throw '설치 요청 경로 거부'
    }
    $request = Read-EndpointDataFile $RequestPath 32768
    if ($request.requester_sid -isnot [string] -or $request.mode -isnot [string] -or $request.action -isnot [string] -or
        $request.user -isnot [string] -or $request.user -notmatch '^[A-Za-z0-9_][A-Za-z0-9._-]{0,31}$' -or
        $request.requester_sid -ne $RequesterSid -or $request.mode -ne 'managed' -or
        $request.action -notin @('install', 'remove')) { throw '설치 요청 범위 거부' }
    $paths = Get-EndpointInstallerPaths
    $certificate = ''; $fingerprint = ''
    if ($Approval.files.'root.crt') {
        $certificate = [IO.File]::ReadAllText((Join-Path $paths.code 'root.crt'))
        $fingerprint = [IO.File]::ReadAllText((Join-Path $paths.code 'root.sha256')).Trim()
        $null = New-EndpointGatewayRequest ($Approval.gateway_url.TrimEnd('/') + '/api/health') $certificate $fingerprint
    }
    $request | Add-Member -NotePropertyName ca_certificate -NotePropertyValue $certificate -Force
    $request | Add-Member -NotePropertyName ca_sha256 -NotePropertyValue $fingerprint -Force
    $requests = Join-Path $paths.state 'requests'
    New-EndpointProtectedDirectory $requests
    $private = Join-Path $requests $id
    if (Test-Path -LiteralPath $private) { throw '중복 설치 요청 거부' }
    New-EndpointProtectedDirectory $private
    $complete = $false
    try {
    $request | Add-Member -NotePropertyName private_directory -NotePropertyValue $private -Force
    if ($request.action -eq 'install') {
        $source = [IO.Path]::GetFullPath($request.enrollment)
        if (-not $source.StartsWith(([IO.Path]::GetFullPath($profile).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path $source -Leaf) -ne 'enrollment.json') { throw '등록 파일 경로 거부' }
        Assert-EndpointNoLinks $source
        $bundle = Read-EndpointDataFile $source 16384
        $bundle.gateway_url = $Approval.gateway_url
        $bundle.tailscale_node_id = $Approval.tailscale_node_id
        $bundle | Add-Member -NotePropertyName ca_certificate -NotePropertyValue $certificate -Force
        $bundle | Add-Member -NotePropertyName ca_sha256 -NotePropertyValue $fingerprint -Force
        $request.enrollment = Join-Path $private 'enrollment.json'
        [IO.File]::WriteAllText($request.enrollment, ($bundle | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    }
    $request.gateway_url = $Approval.gateway_url
    $request.tailscale_node_id = $Approval.tailscale_node_id
    [IO.File]::WriteAllText((Join-Path $private 'request.json'), ($request | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
    $results = Join-Path $paths.state 'results'
    New-EndpointProtectedDirectory $results
    $result = Join-Path $results $id
    New-EndpointProtectedDirectory $result $request.requester_sid
    $request | Add-Member -NotePropertyName result_directory -NotePropertyValue $result -Force
    $complete = $true
    return $request
    } finally {
        if (-not $complete) {
            foreach ($name in @('request.json', 'enrollment.json')) {
                $item = Join-Path $private $name
                if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Force }
            }
            if (-not (Get-ChildItem -LiteralPath $private -Force)) { Remove-Item -LiteralPath $private }
        }
    }
}
