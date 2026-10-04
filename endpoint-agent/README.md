# Endpoint Agent 설치

이 디렉터리는 관측 에이전트(`agent.py`)와 **관리형 설치기**(Linux `managed-linux.py`, Windows `managed-windows.py`)를 포함합니다.
Gateway와 OPA는 `full_stack_lab/`에서 실행합니다. 아래 사용자 범위 설치기들은 관측 전용입니다.
강제 연결에는 다음 root 설치 경로를 사용합니다.

## 가입자용 관리형 Linux 설치

1. 가입 승인·초대 수락 → Console 로그인 → **내 PC 연결**에서 개인별 키트 다운로드. 등록 토큰은 30분·1회용입니다.
2. 조직 IT가 Gateway의 고정 Tailscale 노드 또는 신뢰되는 HTTPS, 승인된 설치기, 공식 native ELF 배포판을 확인합니다.
   사용자가 수정한 스크립트를 root로 실행하지 않습니다. 관리형 배포 시스템에서 승인 출처를 검증한 설치기를 사용하세요.
3. 일반 계정 UID 1000 이상, sudo·wheel·docker·lxd·libvirt 권한 없음, 기존 세션 없음이 필요합니다.
   root가 systemd·AppArmor·nftables·gcc를 준비하고 Codex·Claude를 `/opt/mcpgw-approved/{codex,claude}`에 설치합니다.
   Codex는 같은 릴리스의 `codex-code-mode-host`를 같은 폴더에 둡니다(npm 패키지의
   `@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/`에 둘이 함께 있음). 없으면 도구 호출이 모두 실패해 설치기가 거부합니다.
   실행 파일과 상위 경로는 root 소유이며 사용자 쓰기가 금지돼야 합니다. `--client codex=/승인경로`로 경로를 지정할 수 있습니다.

```bash
unzip mcp-managed-kit.zip -d mcp-managed-kit
sudo python3 mcp-managed-kit/managed-linux.py install --user 일반사용자계정
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
통제했다고 주장하지 않습니다. UID 규칙은 솔루션 기기의 게이트웨이 포트와 **모델 프록시 포트**만 엽니다(D-67).
하네스 실행기는 `HTTPS_PROXY`·`HTTP_PROXY`를 프록시로, `NO_PROXY`를 게이트웨이 주소로 고정합니다. 프록시는
`full_stack_lab/model-proxy/model-domains.txt`의 모델 도메인만 허용하고(TLS 터널은 443만), 임의 외부 주소를 열지 않습니다.
프록시 이전에 설치한 장치는 그대로 동작하지만 모델에 닿지 않습니다. 자격 폐기 → 롤백 → 새 키트로 재설치합니다.
관리 계정의 하네스 모델 로그인(`codex login --device-auth`, `claude` 첫 실행)은 직원이 그 계정에서 한 번 합니다.

## 가입자용 관리형 Windows 설치 (D-68)

Linux와 같은 키트로 Windows 10/11의 **Administrators가 아닌 계정**을 관리형으로 연결합니다. 조직 IT가 관리자 권한
PowerShell에서 실행합니다. Python 3.10 이상은 모든 사용자용(`C:\Program Files\Python3xx`)이어야 합니다. 대상 계정은
한 번 로그인해 프로필이 있어야 하고, 설치할 때는 로그아웃 상태여야 합니다.

```powershell
Expand-Archive mcp-managed-kit.zip mcp-managed-kit
py -3 mcp-managed-kit\managed-windows.py install --user 일반사용자계정
```

| 구성 | 위치 |
| --- | --- |
| 단말 키·설정·방화벽 기준선·서비스 로그 | `%ProgramData%\MCPGatewayManaged\<계정>\`(SYSTEM·Administrators만) |
| 프로그램 | `%ProgramFiles%\MCPGatewayManaged\`(사용자 읽기 전용) |
| Claude Code 관리형 설정 | `C:\Program Files\ClaudeCode\managed-mcp.json`·`managed-settings.json`(프록시 `env` 포함) |
| Codex 강제 설정 | `%ProgramData%\OpenAI\Codex\requirements.toml`. Windows Codex는 `managed_config.toml`을 읽지 않으므로 서버 정의는 계정 `%USERPROFILE%\.codex\config.toml` 끝의 표식 블록에 두고 해시로 점검 |
| 방화벽 | 계정 SID(`LocalUser`) 범위 차단 규칙 3개 `MCPGW-<계정>-*`: 게이트웨이 호스트 밖 전부, 게이트웨이 호스트의 다른 TCP 포트, UDP |
| 프록시 환경 변수 | 그 계정의 `HKCU\Environment`(`HTTPS_PROXY`·`HTTP_PROXY`·`NO_PROXY`) |
| 서비스 | SYSTEM 예약 작업 `MCPGatewayManaged-<계정>`(부팅 시 시작, 실패 시 1분 뒤 재시작) |
| 헤더 전달 | `\\.\pipe\mcpgw-<계정>` — DACL이 그 계정 SID에 읽기만 허용 |

60초마다 보고하는 점검은 `firewall_enforcing`(모든 프로필 켜짐·규칙이 설치 기준선과 같음), `protected_configs`(설정·프로그램·
Python 경로의 소유자와 쓰기 권한이 SYSTEM·Administrators·TrustedInstaller뿐), `ordinary_account`(Administrators 직접 구성원 아님)입니다.
방화벽 규칙은 프로그램 경로가 아니라 계정에 걸리므로 하네스를 복사해도 같은 제한을 받습니다. 그 계정에서는 브라우저를 포함한
모든 프로그램이 게이트웨이 호스트 밖으로 나가지 못합니다. AI 작업 전용 계정으로 운영하세요.

한계: Windows 방화벽은 loopback을 거르지 않습니다. 도메인 그룹을 거친 Administrators 구성원은 점검하지 않습니다.
같은 PC의 다른 계정은 통제 범위에 우회 경로로 표시합니다. OS 차단 이벤트(WFP 감사)는 아직 수집하지 않습니다.
제거: Console에서 자격 폐기 → 계정 로그아웃 → `py -3 "%ProgramFiles%\MCPGatewayManaged\managed-windows.py" rollback --user <계정>`.

### 같은 단말의 다른 계정(D-62)

heartbeat는 `host`로 커널 버전·WSL 여부·관리 계정 밖의 로그인 계정(uid ≥ 1000, nologin 제외)과 그 계정의 특권 그룹
(sudo·wheel·docker·lxd·libvirt·root)을 함께 보냅니다. 이 계정들은 AppArmor·UID 방화벽이 가두지 않으므로 Console
**직원·단말 → 통제 범위**에서 관리 계정의 커널 강제(`account_state: endpoint_enforced`)와 별도로 단말 상태를
`bypass_possible`로 표시합니다. 다른 계정을 보고하지 않는 구버전 에이전트, 관리형 설치 없는 Windows·WSL도 같은 상태입니다.
이 보고는 격리 판정에 쓰지 않습니다. 다른 계정이 있다고 관리 계정의 MCP 인증을 끊지 않습니다.

Gateway가 먼저 이 필드를 받도록 배포된 뒤에 에이전트를 갱신합니다. 이전 Gateway는 알 수 없는 필드를 거부합니다.

### 확인·격리·제거

- Console 단말 표의 상태·정책 확인 시각과 **OS 차단 / 설치·연결 이력**을 확인합니다. MCP 도구 실행 기록과 섞지 않습니다.
- 설치 실패나 이미 설치된 장치는 새 등록 토큰을 재사용하지 않습니다. 먼저 기존 단말 자격을 폐기하고 IT가 아래 절차로 제거한 뒤 새 키트를 받습니다.
- 관리형 제거: 서버에서 **자격 폐기** → 해당 계정 세션 종료 →
  `sudo python3 mcp-managed-kit/managed-linux.py rollback --user <계정>`(새 키트의 설치기).
  서비스를 멈추고 로그인 셸·AppArmor·UID 방화벽을 원복한 뒤, 원래 설정의 private `.backup`을 복구하고(없으면 관리형 파일 삭제)
  해당 계정의 `/var/lib/mcpgw-managed/<계정>`을 제거합니다. 그 뒤 같은 키트로 재설치할 수 있습니다.
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

설치기는 `%LOCALAPPDATA%\MCPGatewayEndpoint`의 ACL을 현재 사용자와 SYSTEM으로 제한한 뒤 장치 키와 에이전트를 저장합니다. 1회 보고가 성공해야 현재 사용자 로그온 작업 `MCPGatewayEndpoint-<endpoint_id>`를 등록합니다(창 없이 `pythonw.exe`로 실행). 장치 키는 PowerShell 명령줄 인자로 넘기지 않습니다. Tailscale HTTP 주소를 쓰면 `-TailscaleNodeId`로 관리자가 확인한 노드 ID를 지정합니다. Windows에서는 프로세스 명령줄(CIM)로 stdio MCP 서버를 추정하고, 명령줄은 SHA-256 digest로만 보냅니다.

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
