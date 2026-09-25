# Endpoint Agent 설치

이 디렉터리는 **사용자 PC에 설치하는 관측 에이전트**입니다. Gateway와 OPA는 `full_stack_lab/`에서 실행합니다. 여기에는 정책 집행기나 관리자 자격이 들어 있지 않습니다. 에이전트는 승인한 MCP 설정 경로와 로컬 리스너를 읽어 Gateway에 보고하며, 설정 변경·프로세스 종료·호출 차단은 하지 않습니다.

## 준비

1. Console(관리자)의 **직원·단말 → 단말 → 장치 자격 발급**에서 고유한 `endpoint_id`와 `inventory` 권한의 장치 키를 발급합니다. 망 탐색이 필요하고 정책 범위가 승인됐다면 `netscan`도 추가합니다. 키는 한 번만 표시됩니다.
2. 대상 PC에서 Gateway에 도달할 주소를 준비합니다. 다른 PC로 연결할 때는 인증서가 유효한 HTTPS 주소를 사용합니다. 로컬 터널이나 같은 PC의 `http://127.0.0.1:8080`만 HTTP로 허용합니다. Docker의 `http://gateway:8080`은 Compose 실습 컨테이너에서만 사용합니다.
3. 해당 PC에서 **실제로 존재하는** MCP 설정 파일 또는 디렉터리 경로를 선택합니다. `env`·`headers`·파일 본문은 전송하지 않으며, stdio 명령 인자는 SHA-256 digest로 바꿔 보냅니다. URL에 직접 포함된 자격 정보는 설정에서 제거하세요.

## Linux / WSL

Python 3.10 이상이 필요합니다. 현재 사용자로 실행합니다.

```bash
./endpoint-agent/install-linux.sh \
  --gateway-url http://127.0.0.1:8080 \
  --endpoint-id endpoint-demo-001 \
  --scan-path "$HOME/.config/Claude/claude_desktop_config.json"
```

장치 키는 화면에 에코되지 않는 프롬프트로 입력합니다. `--key-file`을 쓰려면 소유자만 읽을 수 있는 `chmod 600` 파일을 준비합니다. 설치기는 `~/.local/share/mcp-gateway-endpoint/agent.py`와 `~/.config/mcp-gateway-endpoint/config.json`을 만들고 1회 보고를 검사합니다. 사용자 systemd가 있으면 자동 시작 서비스를 등록합니다. WSL처럼 사용자 systemd가 없으면 출력된 명령으로 수동 실행합니다.

```bash
systemctl --user status mcp-gateway-endpoint
python3 ~/.local/share/mcp-gateway-endpoint/agent.py \
  --config ~/.config/mcp-gateway-endpoint/config.json --once
```

## Windows

PowerShell에서 현재 사용자로 실행합니다. `-ScanPath`에는 존재하는 경로를 지정합니다.

```powershell
.\endpoint-agent\install-windows.ps1 `
  -GatewayUrl 'https://gateway.example.internal' `
  -EndpointId 'endpoint-win-001' `
  -ScanPath @("$env:APPDATA\Claude\claude_desktop_config.json")
```

설치기는 `%LOCALAPPDATA%\MCPGatewayEndpoint`의 ACL을 현재 사용자와 SYSTEM으로 제한한 뒤 장치 키와 에이전트를 저장합니다. 1회 보고가 성공해야 현재 사용자 로그온 작업 `MCPGatewayEndpoint-<endpoint_id>`를 등록합니다. 장치 키는 PowerShell 명령줄 인자로 넘기지 않습니다.

```powershell
Get-ScheduledTask -TaskName 'MCPGatewayEndpoint-endpoint-win-001'
python "$env:LOCALAPPDATA\MCPGatewayEndpoint\agent.py" --config "$env:LOCALAPPDATA\MCPGatewayEndpoint\config.json" --once
```

## 확인과 폐기

- Console의 **직원·단말** 화면에서 등록 장치, 마지막 보고 시각, `registered` / `shadow` / `retired-residue` 분류를 확인합니다. `--once`가 0으로 끝났다는 사실만으로 수집 범위가 충분하다는 뜻은 아닙니다.
- 장치 키를 잃거나 PC를 폐기하면 Console의 단말 표에서 **자격 폐기**를 누릅니다. 새 키가 필요하면 재발급 후 재설치합니다.
- Linux 제거: `systemctl --user disable --now mcp-gateway-endpoint.service` (등록돼 있을 때), 사용자 서비스 파일과 `~/.local/share/mcp-gateway-endpoint`, `~/.config/mcp-gateway-endpoint`를 제거합니다. Windows 제거: `Unregister-ScheduledTask -TaskName 'MCPGatewayEndpoint-<endpoint_id>' -Confirm:$false` 후 `%LOCALAPPDATA%\MCPGatewayEndpoint`를 제거합니다. 먼저 서버의 장치 자격을 폐기하세요.
- 코드 자체 점검: `python endpoint-agent/agent.py --self-check`. Compose 실습에서는 직원 PC 컨테이너(`ws-*`)가 이 `agent.py`를 이미지에 복사해 실행합니다(`cd full_stack_lab && ./console.sh up`).

이 패키지는 관측 전용입니다. 사용자가 Gateway를 우회해 MCP를 직접 호출하는 것을 막으려면 별도의 네트워크·클라이언트 강제 설정이 필요합니다.
