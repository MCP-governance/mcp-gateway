# Endpoint Agent 설치

이 디렉터리는 관측 에이전트(`agent.py`)와 **관리형 설치기**(Linux `managed-linux.py`, Windows `managed-windows.py`)를 포함합니다.
Gateway와 OPA는 `full_stack_lab/`에서 실행합니다. 아래 사용자 범위 설치기들은 관측 전용입니다.
강제 연결에는 다음 root 설치 경로를 사용합니다.

## 가입자용 관리형 Linux 설치

1. 가입 승인·초대 수락 → Console 로그인 → **내 PC 연결**에서 개인별 키트 다운로드. 등록 토큰은 30분·1회용입니다.
2. 조직 IT가 게이트웨이 HTTPS와 배치 루트·SHA-256 지문, 승인된 설치기, 공식 native ELF 배포판을 확인합니다.
   사용자가 수정한 스크립트를 root로 실행하지 않습니다. 관리형 배포 시스템에서 승인 출처를 검증한 설치기를 사용하세요.
3. 일반 계정 UID 1000 이상, sudo·wheel·docker·lxd·libvirt 권한 없음, 기존 세션 없음이 필요합니다.
   root가 systemd·AppArmor·nftables·gcc를 준비하고 Codex·Claude를 `/opt/mcpgw-approved/{codex,claude}`에 설치합니다.
   Codex는 같은 릴리스의 `codex-code-mode-host`를 같은 폴더에 둡니다(npm 패키지의
   `@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/`에 둘이 함께 있음). 없으면 도구 호출이 모두 실패해 설치기가 거부합니다.
   실행 파일과 상위 경로는 root 소유이며 사용자 쓰기가 금지돼야 합니다. `--client codex=/승인경로`로 경로를 지정할 수 있습니다.

```bash
unzip mcp-managed-kit-linux.zip -d mcp-managed-kit && ./mcp-managed-kit/install.sh
```

`install.sh`는 `bootstrap.py`를 sudo로 한 번 올리고, 그 안에서 필수 구성요소 설치 → 승인 하네스 배치(SHA-256 기록) →
관리 계정 결정 → `managed-linux.py install` → 실행 연결(관리자 계정일 때) → 모델 로그인을 순서대로 합니다(D-71).
실행 연결은 `/usr/local/bin`의 shim과, PATH 앞쪽 `~/.local/bin`의 하네스를 이기도록 직원 계정에만 정의되는 셸 함수
(`/etc/profile.d/mcpgw-managed.sh`, `/etc/bash.bashrc`·`/etc/zsh/zshrc`의 표식 블록)입니다(D-72). 설치 뒤 **새 터미널**에서 실행합니다.
이미 설치된 장치면 먼저 `rollback`을 돌리고 다시 설치합니다. `--remove`는 이 PC의 연결만 제거합니다(함수·블록 포함).

Linux Codex 모델 로그인은 설치기가 `codex login --device-auth`로 실행합니다. 건너뛴 경우 같은 명령으로 로그인합니다.
별도 관리 계정의 루프백 출발은 계속 차단하며, 설치를 실행한 직원 계정이 먼저 연 루프백 연결에 대한 응답만 허용합니다(D-119).
수동 `managed-linux.py install`은 관리자가 확인한 직원 UID를 `--owner-uid <UID>`로 지정합니다. 미지정이면 응답 예외도 없습니다.
직원 계정 자체가 관리 계정인 설치에는 소유자 예외를 넣지 않습니다. 현재 코드의 실기기 재검증은 남아 있습니다.
아래 수동 경로는 그 단계들을 따로 돌릴 때만 씁니다.

4. 설치기는 단말 키를 생성하여 한 번 등록하고, `/var/lib/mcpgw-managed/<계정>/config.json`(root 600)에만 저장합니다.
   `/etc/claude-code/{managed-mcp.json,managed-settings.json}`과 `/etc/codex/{managed_config.toml,requirements.toml}`은
   승인된 레지스트리에서 렌더링한 root 소유 설정입니다. 하네스·공급자 MCP 코드는 변경하지 않습니다.
5. 다른 관리자가 **단말 → 활성화**에서 실제 호스트의 일반 계정·AppArmor enforce·nft UID 규칙·보호된 설정을 확인합니다.
   자체 보고는 원격 하드웨어 attestation이 아닙니다. 확인 없이 자동 활성화하거나 자기 장치를 승인하지 않습니다.

root 서비스 `mcpgw-managed-<계정>.service`는 실제 커널 규칙과 파일 해시를 활성화 전에는 10초, 활성화 뒤에는 60초마다 보고합니다.
AppArmor 프로필은 계정의 정확한 이름과 enforce 행을 대조합니다. 비슷한 다른 계정의 프로필명으로 정상 처리하지 않습니다.
`mcpgw-egress-<계정>.service`는 부팅 후에도 UID별 방화벽을 유지합니다. 180초 heartbeat 만료·격리·폐기는
아직 만료되지 않은 JWT도 Gateway에서 거부합니다. 설정이 복구돼도 독립 관리자 활성화가 다시 필요합니다.
단말 키 대신 짧은 JWT만 UID가 일치하는 로컬 인증 헬퍼에 전달하며, 시스템 설정·argv·환경에 토큰을 넣지 않습니다.

이 프로필은 **Linux SSH 일반 계정**의 실행과 UID 전체 IP egress를 제한합니다. 다른 로그인 경로·root·관리자·커널 침해를
통제했다고 주장하지 않습니다. UID 규칙은 솔루션 기기의 게이트웨이 포트와 **모델 프록시 포트**(D-67), 위의 소유자 시작 루프백 응답(D-119)을 허용합니다.
하네스 실행기는 `HTTPS_PROXY`·`HTTP_PROXY`를 프록시로, `NO_PROXY`를 게이트웨이 주소로 고정합니다. 프록시는
`full_stack_lab/model-proxy/model-domains.txt`의 모델 도메인만 허용하고(TLS 터널은 443만), 임의 외부 주소를 열지 않습니다.
프록시 이전에 설치한 장치는 그대로 동작하지만 모델에 닿지 않습니다. 자격 폐기 → 롤백 → 새 키트로 재설치합니다.
관리 계정의 하네스 모델 로그인은 직원이 한 번 합니다. 설치 끝에 `codex login --device-auth`와 `claude auth login`을
안내하고(Ctrl+C로 건너뜀), 건너뛰면 첫 실행 때 하네스가 묻습니다.

## 가입자용 관리형 Windows 설치 (D-68)

Windows 10/11 amd64의 **Administrators가 아닌 계정**을 관리형으로 연결합니다. `install.cmd`는 일반 권한으로 설치 마법사를 엽니다.
Python 3.13.16 공식 embeddable 배포판은 키트에 포함됩니다. 관리형 등록 단계만 별도 UAC 프로세스로 실행합니다. 대상 계정은
한 번 로그인해 프로필이 있어야 하고, 설치할 때는 로그아웃 상태여야 합니다.

조직 IT가 먼저 보호된 승인 설치기와 ZIP 밖의 승인 매니페스트를 배포해야 합니다.
승격되는 작업자는 `%ProgramFiles%\MCPGatewayInstaller\windows-worker.ps1` 고정 경로이며, 다운로드 폴더의 작업자/common/ZIP을 관리자 권한으로 사용하지 않습니다.
승인 설치기 자체의 최초 배포도 신뢰되는 조직 배포 경로에서 해야 합니다. 다운로드 ZIP이 자기 해시를 승인하는 경로는 없습니다.
승인물이 없거나 변조/권한 문제가 있으면 설치가 중단됩니다. [승인 배포·검수 조건](tests-windows/README.md#조직-it의-최초-승인-배포)을 따르세요.

```powershell
Expand-Archive mcp-managed-kit-windows.zip mcp-managed-kit
.\mcp-managed-kit\install.cmd
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
| 포함 Python | `%ProgramFiles%\MCPGatewayManaged\python\`(고정 URL·SHA-256 검증, `pythonw.exe`로 서비스 실행) |
| 트레이 | `MCPGatewayTray-<SID>` 예약 작업, 대상 계정 로그온 시 시작 |
| 개인 트레이 파일 | `%ProgramData%\MCPGatewayManagedTray\<SID>\settings.json`·`status.json`·`status.tmp`: 해당 SID 읽기, 관리자·SYSTEM 쓰기 |
| 헤더 전달 | `\\.\pipe\mcpgw-<계정>` — DACL이 그 계정 SID에 읽기만 허용 |

60초마다 보고하는 점검은 `firewall_enforcing`(모든 프로필 켜짐·규칙이 설치 기준선과 같음), `protected_configs`(설정·프로그램·
Python 경로의 소유자와 쓰기 권한이 SYSTEM·Administrators·TrustedInstaller뿐), `ordinary_account`(Administrators 직접 구성원 아님)입니다.
방화벽 규칙은 프로그램 경로가 아니라 계정에 걸리므로 하네스를 복사해도 같은 제한을 받습니다. 그 계정에서는 브라우저를 포함한
모든 프로그램이 게이트웨이 호스트 밖으로 나가지 못합니다. AI 작업 전용 계정으로 운영하세요.
프로필3개가 모두 boolean true이고 예상 차단 규칙3개의 이름·상태·방향·계정 SID가 일치해야 합니다. 비어 있거나 잘못된 설치 기준선은 정상으로 처리하지 않습니다.

한계: 현재 키트의 규칙으로 native Win32 loopback(127.0.0.1·::1·IPv4-mapped IPv6) 차단을 실측하지 않았습니다. WFP 기능과 UWP 예외를 이 키트의 집행 결과로 일반화하지 않습니다. 도메인 그룹을 거친 Administrators 구성원은 점검하지 않습니다.
Windows 키트는 실행파일·스크립트·DLL 통제 정책을 설치하지 않습니다. App Control/AppLocker/격리 계정·파일권한의 별도 설계와 실기기 검증이 필요합니다.
같은 PC의 다른 계정은 통제 범위에 우회 경로로 표시합니다. 기존 Windows 관측기는 활성화된 감사 채널에서 정확한 대상 SID가 있는 차단만 읽습니다.
감사 정책은 자동 활성화하지 않으며, 이벤트가 없거나 SID를 확인할 수 없으면 트레이에 차단 기록을 만들지 않습니다.
제거: Console에서 자격 폐기 → 트레이 **제거** → 제거 마법사(UAC). CLI 복구는
`& "$env:ProgramFiles\MCPGatewayManaged\python\python.exe" -I -S "$env:ProgramFiles\MCPGatewayManaged\managed-windows.py" rollback --user <계정>`입니다.

마법사 단계는 시작 → TCP·상태 조회 → 설치 위치·관측 범위 → 설치 진행 → 완료입니다. 실패 단계·한국어 사유·다시 시도·로그 경로를 표시합니다.
대상 계정이 로그인 중이면 관리형 등록은 거부하며, 그 계정을 로그아웃한 뒤 관리자 세션에서 다시 진행합니다.
관리자 계정을 지정하면 기존 방식대로 별도 일반 계정을 만들 수 있으며, 최초 로그인·로그아웃이 필요하면 해당 계정 이름을 표시합니다.
설치 완료는 조직 활성화 완료를 뜻하지 않습니다. 활성화는 기존 관리자 콘솔 절차를 따릅니다.

트레이 상태는 연결됨·연결 끊김·차단 발생입니다. 150초보다 오래된 보고는 연결 끊김, 최근 5분 내 실제 관측 차단은 차단 발생으로 표시합니다.
최근 차단은 5건까지이며, **지금 점검**은 TCP·`/api/health`와 로컬 보고 시각을 다시 확인합니다. 정책 재승인·서비스 재시작 기능은 아닙니다.
트레이용 파일은 장치 키·직원 토큰 없이 시각·상태·차단 기록 식별자만 저장하며 인가에 사용하지 않습니다.
이 파일들은 Users가 읽을 수 있는 공용 프로그램 폴더에 저장하지 않습니다. 다른 표준 계정에는 읽기 권한을 부여하지 않습니다.
설치기는 설치 파일 목록만 제거해 설치 경로에 추가된 사용자 파일을 보존합니다. 실패 진단용 `setup.log`는 사용자 설치 로그 위치에 남습니다.
실제 화면·UAC·재설치 검수는 [pj3 시험 절차](tests-windows/README.md)를 따릅니다.

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
2. 대상 PC에서 Gateway 주소를 준비합니다. 유효한 HTTPS와 배치 루트·SHA-256 지문을 사용합니다.
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

포함 Python과 마법사 파일을 담은 키트에서 현재 사용자로 실행합니다. 관측 전용이며 관리형 설치의 대체가 아닙니다.
`-ScanPath`에는 존재하는 경로를 지정하고, 장치 키 파일은 마법사의 파일 선택으로 지정하거나 `-KeyFile`에 경로를 전달합니다.

```powershell
.\endpoint-agent\install-windows.ps1 `
  -GatewayUrl 'https://gateway.example.internal' `
  -EndpointId 'endpoint-win-001' `
  -ScanPath @("$env:APPDATA\Claude\claude_desktop_config.json")
```

설치기는 `%LOCALAPPDATA%\MCPGatewayEndpoint` 아래 설치 위치와 파일의 ACL을 현재 사용자·SYSTEM·Administrators로 제한합니다. 1회 보고가 성공해야 현재 사용자 로그온 작업 `MCPGatewayEndpoint-<endpoint_id>`와 트레이를 등록합니다(포함 `pythonw.exe`, 추가 런타임 없음). 장치 키 값은 명령줄·환경·로그로 넘기지 않습니다. Tailscale HTTP에는 `-TailscaleNodeId`로 관리자가 확인한 노드 ID를 지정합니다.

```powershell
Get-ScheduledTask -TaskName 'MCPGatewayEndpoint-endpoint-win-001'
& "$env:LOCALAPPDATA\MCPGatewayEndpoint\python\python.exe" -I -S "$env:LOCALAPPDATA\MCPGatewayEndpoint\agent.py" --config "$env:LOCALAPPDATA\MCPGatewayEndpoint\config.json" --once
```

## 확인과 폐기

- Console의 **직원·단말** 화면에서 등록 장치, 마지막 보고 시각, `registered` / `shadow` / `retired-residue` 분류를 확인합니다. `--once`가 0으로 끝났다는 사실만으로 수집 범위가 충분하다는 뜻은 아닙니다.
- 장치 키를 잃거나 PC를 폐기하면 Console의 단말 표에서 **자격 폐기**를 누릅니다. 새 키가 필요하면 재발급 후 재설치합니다.
- Linux 제거: `systemctl --user disable --now mcp-gateway-endpoint.service` (등록돼 있을 때), 사용자 서비스 파일과 `~/.local/share/mcp-gateway-endpoint`, `~/.config/mcp-gateway-endpoint`를 제거합니다. Windows는 먼저 서버의 장치 자격을 폐기한 뒤 트레이 **제거**를 사용합니다. 예약 작업 종료를 기다린 뒤 키트 소유 파일만 제거합니다.
- 코드 자체 점검: `python endpoint-agent/agent.py --self-check`. Compose 실습에서는 직원 PC 컨테이너(`ws-*`)가 이 `agent.py`를 이미지에 복사해 실행합니다(`cd full_stack_lab && ./console.sh up`).

`agent.py`와 사용자 범위 설치기는 관측 전용입니다. 위 관리형 설치 경로만 OS 집행을 구성합니다.

## 관측 보고 계약 (D-83, 2026-10-14)

3.1 수집기는 `ENDPOINT_PROCESS_SCAN`과 `ENDPOINT_NETSCAN`을 분리한다. 관리형 Linux 서비스는 process=1, network=0, process UID=등록된 일반 계정으로 설정한다. Windows는 process SID를 사용한다. 직접 프로세스/네트워크 positive 보고에는 장치 netscan scope, OS positive 보고에는 enforcement scope가 필요하다. 범위를 벗어난 계정은 자동 수집하지 않는다.

설정·프로세스·네트워크·OS 각 채널은 state/서버 수신시각/마지막 성공/건수를 기록한다. disabled·unauthorized·partial·failed·unsupported·unknown은 성공0건과 다르다. collector JSON은 supervisor 로그에 채널별로 남으며 collector 오류만으로 정상 기기 자격을 끊지 않는다. 실제 집행 점검 오류는 기존 자격 중단 경계를 유지한다.

inventory/listener `complete` 기본은 False다. 정보원 오류나500건 초과는 partial이다. 명시적 complete 성공에서만 기존 미관측 행을 지우며 process-only 보고는 stdio-process 범위만 삭제한다. 네트워크/local-socket 결과는 보존한다. 과거 shadow를 stale 때문에 정상0으로 바꾸지 않는다. Console은 listener fresh/stale/unknown과 별도 수집상태를 표시하고, 목록은 서버가 센 전체 건수와 반환 창을 따로 보이며 커서로 200건 너머를 넘긴다(D-85).

Windows의 `os-observer-windows.py`는 보호된 collector다. AppLocker event TargetUser가 정확한 관리SID인 차단만 보며, WFP event-time SID가 없으면 partial/sid_unavailable로 제외한다. 감사/방화벽/실행 정책을 자동 활성화하지 않는다. Windows 실제 이벤트 전달 시험은 미실행이다.

[PJ1 Linux 실제 검증과 로그](../research/llm-wiki/status/reports/2026-10-14-endpoint-telemetry-fix.md). 키트 설치·합성 marker 관측·실제 OS 이벤트·SDK/MCP 호출·모델 turn은 다른 검증 층이다.

## 증거 계약 (D-86 – D-89)

- **출처 해시.** 수집기는 레코드마다 `provenance`를 붙인다: `raw_sha256`(원본 레코드: 설정 항목은 `env`·`headers`를 뺀 설정, 커널 이벤트는 저널 한 줄, 프로세스는 명령줄), `projection_sha256`(보내는 필드만의 정규 JSON), `transformations`(적용한 변환 이름), `collector`. 정규 JSON은 키 정렬·공백 없음·UTF-8, 시각은 UTC 마이크로초 `…Z`이며 서버의 `endpoint_plane.canonical_sha256`과 같은 바이트여야 한다. 서버는 **저장한 필드만으로** projection 해시를 다시 계산해 `일치`/`불일치`를 남기고, 에이전트가 해시를 보내지 않은 옛 보고는 `미보고`다. 원본 해시는 서버가 검증할 수 없고 단말의 원본과 나중에 대조하기 위해서만 보관한다.
- **수집 출처.** 관리형 서비스는 `observer.json`의 `ENDPOINT_ORIGIN=automatic`으로 수집기를 띄운다. 이 값이 없으면 계속 도는 서비스는 `automatic`, `--once`로 손수 돌린 실행·업로드는 `manual`이다. OS 이벤트는 항상 `os_event`다. 같은 원본 해시를 7일 안에 다시 받으면 새 행을 만들지 않는다.
- **OS 거부 분류.** `os-observer.py`는 AppArmor 거부에서 실행 시도 프로세스(`comm`)·프로파일·대상 파일명을 보내고 `harness_startup`(Claude Code·Codex가 자기 기동 중 부르는 `git`·`claude`·`codex`를 시스템 경로에서 실행하려다 거부됨) / `blocked_attempt`(그 밖의 거부된 exec) / `unknown`(프로세스 또는 작업을 알 수 없음, 네트워크 거부)으로 나눈다. 프로파일과 nft 규칙은 바꾸지 않는다.
- **게이트웨이 지연.** 관리형 서비스는 하트비트마다 설정된 Gateway 주소(다른 대상 없음)에 TCP 연결 5회와 `GET /api/health` 1회를 하고 p50·p95·지터(연속 표본 차이의 평균)·실패율을 `network_quality`로 보낸다. 지연은 TCP 연결 시간이며 실패율은 프로브 실패 비율이지 패킷 손실이 아니다.
- `python endpoint-agent/agent.py --self-check`, `tests/endpoint_evidence_check.py`(단위), `tests/endpoint_evidence_pg_check.py`(격리 PostgreSQL)로 확인한다.

## 현장 사설 CA(D-124)

Linux 관리형 ZIP의 `enrollment.json`에는 `ca_certificate`(단일 PEM 루트), `ca_sha256`(DER SHA-256)이 있습니다.
설치 전 지문을 검증하고 시스템 신뢰 저장소 대신 root 소유 CA 파일을 하네스 실행 프로세스에만 전달합니다.
Claude Code는 `NODE_EXTRA_CA_CERTS`, Codex는 `CODEX_CA_CERTIFICATE`를 사용합니다.
관측 전용 `install.py`에는 `--ca root.crt --ca-sha256 지문`을 지정합니다. 에이전트와 Linux OS 관측기는 같은 HTTPS 검증 경로를 씁니다.
Windows도 등록 전 지문 검사와 서비스·관측기 CA 전달을 적용합니다. 관리자 단계는 보호된 승인 키트의 루트로 고정합니다.
`%ProgramFiles%\MCPGatewayManaged\launchers\<SID>\claude.cmd`·`codex.cmd`가 CA를 하네스 프로세스에만 전달합니다.
키트 승인 목록에는 `root.crt`·`root.sha256`·`mcpgw_pc.py`의 해시도 포함해야 합니다. 기존 승인 목록은 새 ZIP의 목록으로 교체해야 합니다.
[배포 절차](../docs/ai/FIELD.md#현장-tls와-루트-배포d-124) · [검증과 인계](../research/llm-wiki/status/reports/2026-10-18-field-tls-d124.md).
