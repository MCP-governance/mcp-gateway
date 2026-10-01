# Endpoint Agent 설치

이 디렉터리는 관측 에이전트(`agent.py`)와 **관리형 Linux 설치기**(`managed-linux.py`)를 포함합니다.
Gateway와 OPA는 `full_stack_lab/`에서 실행합니다. 아래 사용자 범위 설치기들은 관측 전용입니다.
강제 연결에는 다음 root 설치 경로를 사용합니다.

## 가입자용 관리형 Linux 설치

1. 가입 승인·초대 수락 → Console 로그인 → **내 PC 연결**에서 개인별 키트 다운로드. 등록 토큰은 30분·1회용입니다.
2. 조직 IT가 Gateway의 고정 Tailscale 노드 또는 신뢰되는 HTTPS, 승인된 설치기, 공식 native ELF 배포판을 확인합니다.
   사용자가 수정한 스크립트를 root로 실행하지 않습니다. 관리형 배포 시스템에서 승인 출처를 검증한 설치기를 사용하세요.
3. 일반 계정 UID 1000 이상, sudo·wheel·docker·lxd·libvirt 권한 없음, 기존 세션 없음이 필요합니다.
   root가 systemd·AppArmor·nftables·gcc를 준비하고 Codex·Claude를 `/opt/mcpgw-approved/{codex,claude}`에 설치합니다.
   실행 파일과 상위 경로는 root 소유이며 사용자 쓰기가 금지돼야 합니다. `--client codex=/승인경로`로 경로를 지정할 수 있습니다.

```bash
unzip mcp-managed-kit.zip -d mcp-managed-kit
cd mcp-managed-kit
sudo python3 managed-linux.py install --user 일반사용자계정
```

4. 설치기는 단말 키를 생성하여 한 번 등록하고, `/var/lib/mcpgw-managed/<계정>/config.json`(root 600)에만 저장합니다.
   `/etc/claude-code/{managed-mcp.json,managed-settings.json}`과 `/etc/codex/{managed_config.toml,requirements.toml}`은
   승인된 레지스트리에서 렌더링한 root 소유 설정입니다. 하네스·공급자 MCP 코드는 변경하지 않습니다.
5. 다른 관리자가 **단말 → 활성화**에서 실제 호스트의 일반 계정·AppArmor enforce·nft UID 규칙·보호된 설정을 확인합니다.
   자체 보고는 원격 하드웨어 attestation이 아닙니다. 확인 없이 자동 활성화하거나 자기 장치를 승인하지 않습니다.

root 서비스 `mcpgw-managed-<계정>.service`는 60초마다 실제 커널 규칙과 파일 해시를 보고합니다.
`mcpgw-egress-<계정>.service`는 부팅 후에도 UID별 방화벽을 유지합니다. 180초 heartbeat 만료·격리·폐기는
아직 만료되지 않은 JWT도 Gateway에서 거부합니다. 설정이 복구돼도 독립 관리자 활성화가 다시 필요합니다.
단말 키 대신 짧은 JWT만 UID가 일치하는 로컬 인증 헬퍼에 전달하며, 시스템 설정·argv·환경에 토큰을 넣지 않습니다.

이 프로필은 **Linux SSH 일반 계정**의 실행과 UID 전체 IP egress를 제한합니다. 다른 로그인 경로·root·관리자·커널 침해를
통제했다고 주장하지 않습니다. Windows 관측 설치에는 같은 강제성이 없습니다. 기본 UID 규칙은 Gateway 목적지만 허용하므로
LLM·일반 인터넷 작업은 사내 승인 프록시 경로를 별도로 설계해야 합니다. 임의 외부 모델 주소를 예외로 열지 않습니다.

### 확인·격리·제거

- Console 단말 표의 상태·정책 확인 시각과 **OS 차단 / 설치·연결 이력**을 확인합니다. MCP 도구 실행 기록과 섞지 않습니다.
- 설치 실패나 이미 설치된 장치는 새 등록 토큰을 재사용하지 않습니다. 먼저 기존 단말 자격을 폐기하고 IT가 아래 절차로 제거한 뒤 새 키트를 받습니다.
- 관리형 제거: 서버에서 **자격 폐기** → 해당 계정 세션 종료 → root 서비스 disable/stop →
  `sudo python3 /usr/local/lib/mcpgw-managed/enforce-linux.py --user <계정> --rollback`.
  root가 원래 설정의 private `.backup`을 확인해 복구하고 해당 계정의 `/var/lib/mcpgw-managed/<계정>`을 제거합니다.
  공용 프로그램과 다른 계정의 방화벽·장치 자격은 제거하지 않습니다.
- PJ1 재검증: root가 Console 직원·독립 관리자 신원을 stdin으로 제공하고
  `python3 full_stack_lab/tests/managed_kernel_proof.py --config /var/lib/mcpgw-managed/<계정>/config.json` 실행.
  실제 185초 보고 중단·보호 파일 변조·복구·검증용 추가 자격 폐기를 수행하고 `finally`에서 원래 서비스와 파일을 복구합니다.
  이 검사는 모델이나 공급자 MCP를 모사하지 않습니다. 실제 native MCP 호출은 별도 실행 증거로 확인합니다.

인벤토리 대상 설정 파일명: `claude_desktop_config.json`·`claude_config.json`, `.claude.json`(Claude Code —
user scope와 `projects.<디렉터리>.mcpServers`를 `이름@디렉터리`로 병합), `managed-mcp.json`(Claude Code
IT 관리형), `.mcp.json`·`mcp.json`·`mcp_settings.json`·`cline_mcp_settings.json`, `settings.json`(Gemini CLI —
`httpUrl` 키도 읽음 — 와 VS Code), `mcp_config.json`(Antigravity), `opencode.json`(배열형 `command`도 처리),
`config.toml`·`managed_config.toml`(Codex, IT 관리형은 후자). `node_modules`는 뒤지지 않습니다.

## 준비

1. Console(관리자)의 **직원·단말 → 단말 → 장치 자격 발급**에서 고유한 `endpoint_id`와 `inventory` 권한의 장치 키를 발급합니다. 망 탐색이 필요하고 정책 범위가 승인됐다면 `netscan`도 추가합니다. 키는 한 번만 표시됩니다.
2. 대상 PC에서 Gateway 주소를 준비합니다. 유효한 HTTPS 또는 명시적으로 고정한 Tailscale Gateway 노드를 사용합니다.
   field의 Caddy는 `/api/endpoint/*`를 게시하고 각 API에서 장치 범위 또는 관리자 권한을 검증합니다.
   `./console.sh field register-pc <이름>`은 관측 자격 발급이며, 관리형 MCP 실행 권한을 활성화하지 않습니다.
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

`agent.py`와 사용자 범위 설치기는 관측 전용입니다. 위 관리형 설치 경로만 OS 집행을 구성합니다.
