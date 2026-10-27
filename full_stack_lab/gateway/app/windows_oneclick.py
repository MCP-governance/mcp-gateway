"""Package the existing Windows ZIP with a single, explicitly elevated entry point."""
import base64


def launcher(archive: bytes, bootstrap: str) -> bytes:
    # CMD stays below its command length limit; the payload is read as data, never as batch commands.
    import json
    payload = base64.b64encode(json.dumps({
        "archive": base64.b64encode(archive).decode("ascii"), "bootstrap": bootstrap,
    }, separators=(",", ":")).encode()).decode("ascii")
    seed = (
        "$ErrorActionPreference='Stop';"
        "$context=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('@CTX@'))|ConvertFrom-Json;"
        "$stream=[IO.File]::Open($context.path,'Open','Read','Read'); try {"
        "$memory=New-Object IO.MemoryStream; $stream.CopyTo($memory); $bytes=$memory.ToArray();"
        "$sha=[Security.Cryptography.SHA256]::Create();"
        "if (([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','') -cne $context.hash) { throw 'Installer changed' };"
        "$body=([Text.Encoding]::UTF8.GetString($bytes) -split '(?m)^:MCPGW_PAYLOAD\\r?$',2)[1].Trim();"
        "$payload=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($body))|ConvertFrom-Json;"
        "& ([scriptblock]::Create($payload.bootstrap)) $context $payload.archive"
        "} catch { Add-Type -AssemblyName System.Windows.Forms;"
        "[void][Windows.Forms.MessageBox]::Show([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"
        + base64.b64encode('설치 실패 · 새 설치 파일 또는 조직 IT 확인 필요'.encode()).decode()
        + "')),'MCP'); exit 1"
        "} finally { if ($stream) { $stream.Dispose() } }"
    )
    encoded_seed = base64.b64encode(seed.encode()).decode("ascii")
    command = (
        "$ErrorActionPreference='Stop';"
        "$path=$env:MCPGW_SETUP_FILE;"
        "$bytes=[IO.File]::ReadAllBytes($path);"
        "$sha=[Security.Cryptography.SHA256]::Create();"
        "$context=@{path=$path;hash=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','');"
        "sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;user=$env:USERNAME};"
        "$ctx=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($context|ConvertTo-Json -Compress)));"
        f"$seed=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_seed}')).Replace('@CTX@',$ctx);"
        "$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($seed));"
        "$exe=Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\\WindowsPowerShell\\v1.0\\powershell.exe';"
        # No wait: the console that opened the .cmd (Windows Terminal on Windows 11) closes once UAC is approved.
        "try {Start-Process -FilePath $exe -ArgumentList ('-NoProfile -STA -NonInteractive -WindowStyle Hidden -EncodedCommand '+$encoded) -Verb RunAs -WindowStyle Hidden | Out-Null; exit 0} catch {exit 1}"
    )
    return ("@echo off\r\nsetlocal\r\nset \"MCPGW_SETUP_FILE=%~f0\"\r\n"
            '"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden -Command "'
            + command + '"\r\nexit /b %errorlevel%\r\n:MCPGW_PAYLOAD\r\n' + payload + '\r\n').encode("utf-8")
