# Endpoint Agent 설치

이 디렉터리는 관측 에이전트(`agent.py`)와 **관리형 설치기**(Linux `managed-linux.py`, Windows `managed-windows.py`)를 포함합니다.
macOS 관리형 설치기는 `managed-macos.py`이며 서비스 코드는 Homebrew 소유 경로를 피한 `/Library/MCPGatewayManaged`에 둡니다.
Gateway와 OPA는 `full_stack_lab/`에서 실행합니다. 아래 사용자 범위 설치기들은 관측 전용입니다.
강제 연결에는 다음 root 설치 경로를 사용합니다.

관리형 Linux·Windows는 등록 계정 홈의 Claude 설정 두 파일과 Codex `config.toml`·직계 `*.config.toml`을 읽어
「사용자 명령 헬퍼 없음」을 보고합니다(D-148). Claude `apiKeyHelper`·`otelHeadersHelper`·`awsCredentialExport`·`awsAuthRefresh`,
Codex 최상위/프로필 `notify`는 빈 값도 실패입니다. 명령 값은 보내지 않으며 읽기·파싱 실패도 준수 실패입니다.
이 검사가 없는 기존 설치는 이전 항목으로 판정되고, 새 키트로 재설치해 한 번 보고한 뒤부터 항목이 필수가 됩니다.
Windows는 계정 사용자 환경에 `CODEX_HOME`·`CLAUDE_CONFIG_DIR`가 있으면 값과 무관하게 실패로 보고합니다(D-151).
프로젝트 설정·그 밖의 대체 설정 위치·검사 사이 파일 변경은 범위 밖입니다. [범위와 전환 절차](../research/llm-wiki/analysis/user-command-settings/README.md).

## 간편 모드(기본)와 격리 계정(고급) — D-239

| | 간편 모드(기본) | 격리 계정(고급) |
| --- | --- | --- |
| 선택 | 기본 | 콘솔 「내 PC 연결 → 고급: 격리 계정」, Linux `install.sh --isolated`, Windows 마법사 체크 |
| 실행 계정 | 지금 로그인한 직원 계정(관리자·표준 모두, 로그아웃 없음) | 별도 관리 계정 `managed-<직원>`(Linux)·`mcpgw-<직원>`(Windows) |
| 하네스 | 직원이 설치한 그대로 | `/opt/mcpgw-approved`·`%ProgramFiles%\MCPGatewayManaged\harness`에 복사·SHA-256 |
| 놓는 것 | 관리형 설정, 헤더 헬퍼, 보고 서비스, `mint`, CA 환경(Linux `/etc/environment` 블록·Windows 사용자 환경) | 위 + AppArmor·nft(Windows SID 방화벽)·sudoers·shim·셸 함수·홈 런처 |
| 패키지 | curl·openssl·컨테이너 엔진을 시도만(실패해도 계속) | gcc·nftables·apparmor-utils·curl·openssl 필수 + 엔진 |
| 활성화 | 설치 점검 통과 시 자동(콘솔 「새 PC 활성화」에서 끌 수 있음) | 관리자 |
| 콘솔 통제 범위 | `observed_only` · 「간편 모드 · 게이트웨이 판정 적용」 | `endpoint_enforced`(다른 계정이 있으면 `bypass_possible`) |

설치는 파일 하나 실행·관리자 확인 1회·질문 0개다. 끝에 세 칸을 실측해 보인다: **모델 응답**(하네스가 실제로 답하는지), **도구**
(직원 하네스와 같은 헤더로 승인 서버의 `tools/list` 도구 수), **서버 연결**(승인 서버 1건 `initialize`). 자격 파일이 있다는 것만으로
성공 처리하지 않는다. Linux는 터미널이면 curses 풀화면(단계·소요·세 칸·다음 할 일), 아니면 한 줄씩 출력한다.
`mint`도 터미널이면 2초마다 갱신되는 화면(`q` 닫기, `c` 연결 확인), `mint --check`는 세 칸 중 두 칸을 다시 잰다.
Linux 상태 화면의 「다음 할 일」은 설치 점검에서 로그인이 필요했던 하네스의 로그인 명령을 표시한다. 모델 로그인 값은 마지막 설치 점검의 관측이며, 상태 명령은 모델 인증을 다시 검사하지 않는다.
설치 전 연결 거부·임시 DNS 오류와 정책 수신의 일시 오류는 단계별 최대 3회(1·2초 간격, 요청당 15초 제한) 시도한다. 인증 거부·인증서 오류는 즉시 실패한다.
등록 요청의 응답 시간 초과·응답 유실·HTTP 오류는 등록 토큰이 이미 소모됐을 수 있어 다시 보내지 않는다. 실패 문구와 보호된 설치 로그에는 HTTP 상태 또는 오류 종류만 남긴다.
설치 결과의 관리 상태는 서비스 시작 뒤 최대 60초 동안 받은 최신 보고를 따른다. 확인되지 않으면 「확인 필요」이며, 등록 응답만으로 활성이라 표시하지 않는다.
재설치·복구·모드 전환에는 콘솔에서 새 키트를 받는다. 등록·정책 수신에 성공한 뒤 기존 설치를 원복하며, 간편 모드로 바꾸면 키트가 만든 격리 계정을
지운다(홈·프로필 폴더는 남김). Linux·macOS에서 등록 파일을 소모한 폴더를 다시 실행하면 현재 직원의 기존 설치 기록과 상태 확인 명령을 안내하고 끝난다.
등록 토큰은 다시 쓰지 않는다. 간편 모드가 포기하는 것은 [SECURITY_BOUNDARIES](../docs/ai/SECURITY_BOUNDARIES.md)에 있다.

Windows 트레이: 상태 창(연결·관리 상태·모드·승인 서버·하네스 판본·세 칸·다음 할 일), 연결 확인, 모델 로그인(Claude·Codex),
다시 연결(게이트웨이 점검, 서비스가 멈췄으면 관리자 권한으로 다시 시작), 콘솔 열기, English/한국어, 제거. 처음 활성화되면 한 번 스스로
연결을 확인한다. 콘솔에서는 `python.exe windows_status.py <status.json>`이 같은 상태를 글로 보인다.

## 가입자용 관리형 Linux 설치

아래 3~5와 관리 계정·실행 연결·AppArmor 설명은 **격리 계정(`--isolated`) 기준**이다. 간편 모드는 위 절.

1. 가입 승인·초대 수락 → Console 로그인 → **내 PC 연결**에서 개인별 키트 다운로드. 등록 토큰은 30분·1회용입니다.
2. 조직 IT가 게이트웨이 HTTPS와 배치 루트·SHA-256 지문, 승인된 설치기, 공식 native ELF 배포판을 확인합니다.
   사용자가 수정한 스크립트를 root로 실행하지 않습니다. 관리형 배포 시스템에서 승인 출처를 검증한 설치기를 사용하세요.
3. 일반 계정 UID 1000 이상, sudo·wheel·docker·lxd·libvirt 권한 없음, 기존 세션 없음이 필요합니다.
   root가 systemd를 확인하고 gcc·nftables·AppArmor 도구·curl·openssl과 로컬 MCP용 컨테이너 엔진(apt `docker.io`·dnf `podman`·pacman `docker`)을
   한 번에 설치하며(D-225), Codex·Claude를 `/opt/mcpgw-approved/{codex,claude}`에 설치합니다.
   Codex는 같은 릴리스의 `codex-code-mode-host`를 같은 폴더에 둡니다(npm 패키지의
   `@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/`에 둘이 함께 있음). 없으면 도구 호출이 모두 실패해 설치기가 거부합니다.
   실행 파일과 상위 경로는 root 소유이며 사용자 쓰기가 금지돼야 합니다. `--client codex=/승인경로`로 경로를 지정할 수 있습니다.

```bash
rm -rf mcp-managed-kit && unzip -q mcp-managed-kit-linux.zip -d mcp-managed-kit && ./mcp-managed-kit/install.sh
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
보고하는 `policy_hash`는 게이트웨이가 내려 준 값을 그대로 돌려 주며, 게이트웨이는 그 값과 파일 해시로 현재 통제 설정(`control_hash`)으로
렌더링된 파일인지 계산합니다. 서버 승인·철회나 활성화로 바뀌는 서버 목록·안내문은 통제 해시에 들어가지 않아 격리 사유가 아닙니다.
통제 설정이 다르거나 파일이 바뀌면 지금처럼 차단·격리합니다(D-238). 이 방식은 키트 변경 없이 게이트웨이 배포만으로 적용됩니다.
AppArmor 프로필은 계정의 정확한 이름과 enforce 행을 대조합니다. 비슷한 다른 계정의 프로필명으로 정상 처리하지 않습니다.
`mcpgw-egress-<계정>.service`는 부팅 후에도 UID별 방화벽을 유지합니다. 180초 heartbeat 만료·격리·폐기는
아직 만료되지 않은 JWT도 Gateway에서 거부합니다. 설정이 복구돼도 독립 관리자 활성화가 다시 필요합니다.
단말 키 대신 짧은 JWT만 UID가 일치하는 로컬 인증 헬퍼에 전달하며, 시스템 설정·argv·환경에 토큰을 넣지 않습니다.

이 프로필은 **Linux SSH 일반 계정**의 실행과 UID 전체 IP egress를 제한합니다. 다른 로그인 경로·root·관리자·커널 침해를
통제했다고 주장하지 않습니다. UID 규칙은 솔루션 기기의 게이트웨이 포트와 **모델 프록시 포트**(D-67), 위의 소유자 시작 루프백 응답(D-119)을 허용합니다.
하네스 실행기는 `HTTPS_PROXY`·`HTTP_PROXY`를 프록시로, `NO_PROXY`를 게이트웨이 주소로 고정합니다. 프록시는
`full_stack_lab/model-proxy/model-domains.txt`의 모델 도메인만 허용하고(TLS 터널은 443만), 임의 외부 주소를 열지 않습니다.
프록시 이전에 설치한 장치는 그대로 동작하지만 모델에 닿지 않습니다. 자격 폐기 → 롤백 → 새 키트로 재설치합니다.
같은 직원이 같은 PC에 키트를 다시 설치하면(업데이트) 직전 활성 장치를 대체하고 활성화를 이어받습니다(D-217). 격리되거나 중지된 장치는 이어받지 않고 다른 PC는 새 활성화가 필요합니다.
직원은 `mint`로 장치 상태·게이트웨이 연결·마지막 보고·승인 서버 수·로컬 MCP 준비(n/m)·직원 문서 폴더·키트 판본을 봅니다(제한된 계정은 `cat /usr/local/lib/mcpgw-managed/status-<계정>.txt`). 활성화 대기 중에는 하네스의 401 줄에 대기 사유가 나옵니다.
관리 계정의 하네스 모델 로그인은 직원이 한 번 합니다. 설치 끝에 `codex login --device-auth`와 `claude auth login`을
안내하고(Ctrl+C로 건너뜀), 건너뛰면 첫 실행 때 하네스가 묻습니다.

## 가입자용 관리형 Windows 설치 (D-68)

간편 모드(기본)는 로그인 중인 직원 계정에 그대로 설치한다(관리자 직원도 별도 계정 없이, 실행 중인 세션 유지). 방화벽 규칙·하네스 복사·
PATH 변경이 없고 CA 경로만 사용자 환경 변수(`NODE_EXTRA_CA_CERTS`·`CODEX_CA_CERTIFICATE`)로 둔다. 아래 계정·방화벽·로그아웃 설명은
**「고급: 격리 계정」 기준**이다.

콘솔의 **내 PC 연결 → Windows**는 `mcp-managed-setup-windows.cmd` 한 파일을 내려줍니다(D-197).
실행 후 UAC 한 번을 승인하면 포함된 ZIP을 메모리에서 검증하고 보호된 승인 설치기를 준비한 뒤 등록까지 실행합니다.
별도 압축 해제·IT 선행 배포·직원 계정 로그아웃은 필요하지 않습니다. 기존에 설치된 공식 Claude 또는 Codex 실행 파일은 필요합니다.
직원 계정과 별도의 표준 관리 계정 `mcpgw-<직원>`을 준비하고 Windows `CreateProfile`로 프로필을 생성하므로 첫 로그인 없이 설치가 끝납니다.
기존 관리 계정에 실행 중인 프로세스가 있으면 계속 거부합니다. 직원 계정의 세션을 종료하거나 방화벽 통제를 완화하지 않습니다.
등록 후 조직 활성화는 기존처럼 관리자가 수행합니다. 설치 결과에 관리 계정과 `claude auth login`, `codex login --device-auth`를 표시합니다.
모델 로그인은 이후 관리 계정에서 수행하며, 트레이는 이미 등록된 로그온 예약 작업으로 시작됩니다. 직원 계정에서 직접 실행한 도구까지 관리된다는 뜻은 아닙니다.

최초 신뢰 주체는 인증된 콘솔에서 받은 전체 파일을 실행하고 UAC로 승인하는 관리자입니다. 파일 SHA-256은 실행 중 교체를 검사하며
발행자 서명이 아닙니다. 새 서명 인증서나 인증서 신뢰 저장소 변경은 추가하지 않습니다. `AllSigned` 환경에서는 조직 서명 배포를 요구하며 중단합니다.
작업자만 프로세스 범위 `RemoteSigned`로 실행하고 시스템 실행 정책·그룹 정책은 바꾸지 않습니다. 기존 IT 승인물이 있으면 해시·주소·노드가
전부 같은 경우에만 사용하고, 다른 승인물을 다운로드 키트로 교체하지 않습니다. 실설치 검증 상태는 [작업 보고](../research/llm-wiki/status/reports/2026-10-23-windows-oneclick.md)를 따릅니다.

### 조직 IT의 선택 배포 경로

Windows 10/11 amd64의 **Administrators가 아닌 계정**을 관리형으로 연결합니다. `install.cmd`는 일반 권한으로 설치 마법사를 엽니다.
Python 3.13.16 공식 embeddable 배포판은 키트에 포함됩니다. 관리형 등록 단계만 별도 UAC 프로세스로 실행합니다. 대상 계정은
한 번 로그인해 프로필이 있어야 하고, 설치할 때는 로그아웃 상태여야 합니다.

이 ZIP 경로에서는 조직 IT가 먼저 보호된 승인 설치기와 ZIP 밖의 승인 매니페스트를 배포해야 합니다.
승격되는 작업자는 `%ProgramFiles%\MCPGatewayInstaller\windows-worker.ps1` 고정 경로이며, 다운로드 폴더의 작업자/common/ZIP을 관리자 권한으로 사용하지 않습니다.
이 경로의 승인 설치기 자체의 최초 배포도 신뢰되는 조직 배포 경로에서 해야 합니다. 기존 작업자는 다운로드 ZIP의 자기 해시로 승인하지 않습니다.
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

하네스 명령줄의 프롬프트는 MCP 서버 기동 증거로 쓰지 않는다(D-273, D-269의 제외 범위 정정). Node/Bun은 Claude Code의 `@anthropic-ai/claude-code/cli.js` 또는 Codex의 `@openai/codex/bin/codex.js`로 끝나는 진입 파일만 제외한다. native 실행 파일은 설치기가 `harness_paths`로 기록하고 서비스가 보호된 관측 설정 `ENDPOINT_HARNESS_PATHS`로 전달한 경로와 실경로가 같을 때 제외한다. 하위 패키지의 서버 스크립트·다른 경로의 동명 실행 파일은 계속 검사하며, MCP initialize 응답은 제외 조건과 관계없이 확정 증거다. 경로 목록이 없는 기존 설치·관측 전용 설치는 native 이름만으로 제외하지 않는다. 관리형 키트를 재설치하면 경로가 기록된다. 이는 파일 서명·내용 검증이나 변조 방지 증명이 아니다.

npm Codex는 진입 링크의 실경로를 확인하고, 설치 시 해당 `bin/codex.js`를 기준으로 Node 모듈 해석기가 선택한 플랫폼 패키지의 실행 파일도 같은 목록에 기록한다(D-276). 플랫폼 패키지가 없으면 공식 래퍼와 같이 해당 Codex 패키지의 `vendor` 경로를 확인한다. 래퍼나 하네스를 실행하지 않고 경로만 확인하며, 확인 실패·파일 누락이면 별도 경로를 제외하지 않는다. 패키지 하위 전체나 다른 위치의 동명 파일을 허용하지 않는다.

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
## macOS 직원 PC 키트 (2026-10-22)

콘솔 「내 PC 연결」은 브라우저 운영체제의 연결 파일을 먼저 표시한다. macOS 연결 파일을 받은 뒤
터미널에서 `/bin/bash "$HOME/Downloads/mcp-connect-macos.command"` 한 줄을 실행하고 관리자 암호를 한 번 입력한다.
다운로드 자격은 5분·1회용이며 파일 안에서 curl 설정 파일로 전달하고 즉시 삭제한다. URL query·명령 인자·환경 변수에
토큰을 넣지 않는다. Gatekeeper의 더블클릭 허용이나 quarantine 해제 명령은 필요하지 않다.

`install.sh` → `install-macos.sh` → `managed-macos.py`가 설치한다. Python 3.14 framework가 없으면 공식
3.14.9 universal2 pkg를 받아 pkgutil·PSF 서명자·spctl 확인 후 같은 관리자 권한 안에서 설치한다.
공식 Codex·Claude 설치본은 미리 있어야 한다(D-71과 동일). npm·Homebrew·사용자 native 설치 위치에서 Mach-O를 찾아
승인 경로에 복사하고 해시를 기록한다. 새 하네스나 MCP 구현을 만들지 않는다.

dscl로 `managed-<직원>` 일반 계정과 별도 홈을 만들고, 기존 Linux 정책 전송·파일 렌더링·토큰 브로커를 재사용한다.
Claude 관리 설정은 `/Library/Application Support/ClaudeCode`, Codex는 `/etc/codex`에 둔다.
`/usr/local/bin` shim과 bash/zsh 함수가 관리 계정의 실행기로 연결한다. 모델 프록시와 CA의 공개 값만 실행 환경에 넣고,
장치 비밀은 root 전용 `/var/db/mcpgw-managed` 파일에 보관한다. 헤더 헬퍼는 Darwin getpeereid UID를 확인하는 소켓을 사용한다.
launchd root 서비스가 정책·heartbeat·잠금 안 토큰 갱신을 담당한다. 조직 관리자의 독립 활성화는 그대로 필요하다.

pf는 기존 `com.apple/*` anchor 참조를 확인하고 하위 전용 anchor에 관리 UID의 게이트웨이·모델 프록시 TCP만 허용한다.
그 외 TCP/UDP는 차단한다. Linux의 모든 IP 프로토콜 차단·AppArmor 프로세스 격리와 동등하지 않으며 같은 UID의
헬퍼 호출·관리자 우회는 남는다. Apple은 PF를 안정된 API로 보장하지 않는다. root 규칙 전체를 다시 로드하지 않는다.

제거는 키트 폴더에서 `bash install.sh --remove`로 실행한다. launchd → shim/셸 함수 → 실행기/헬퍼 → pf anchor/활성화 참조
→ 기존 관리 설정 복원 → 프로그램 → 관리 계정/홈 순서로 되돌린다. 재설치도 기존 연결부터 제거한다.
키트를 지운 뒤에는 `sudo /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 -I -B /Library/MCPGatewayManaged/managed-macos.py --remove`를 사용한다.
공유 Python 런타임은 남기며, 서버의 기존 엔드포인트 자격 폐기는 콘솔의 기존 관리 경로를 따른다.

**macOS 실설치·활성화·MCP 호출·제거는 미실행**이다. Windows에서 오프라인 코드 검사만 수행했다.
[보고](../research/llm-wiki/status/reports/2026-10-22-kit-macos.md) · [D-196](../docs/ai/DECISIONS.md).

## 로컬 MCP 이미지 준비와 엔진 선택 (D-200, 2026-10-23)

실행기는 서명된 매니페스트의 허용 저장소·sha256 digest만 받는다. 승인 관찰 초기화의 이미지 준비는 최대 180초이며
기존 제어 조회에서 승인·철회·정책·장치 상태를 확인하고 5초 수령 임대를 갱신한다. 수신 중 조회 실패·철회·
기한 초과가 나면 수신 프로세스를 종료하고 컨테이너를 시작하지 않는다. 실제 시작은 준비 이후이며 요청의 원래 실행
제한(최대 20초)을 적용한다. 실행 후에는 종료 상태를 읽고 명시적으로 컨테이너를 제거한다.
일반 호출과 상태 점검은 호출자가 지정한 전체 기한 안에서만 준비 시간을 배분하며, 짧은 상태 점검의 기한이나
호출 예약의 유효 기간을 늘리지 않는다. 승인 관찰은 기존 240초 콘솔 프록시 기한 안에서 수행한다.

공식 카탈로그 이미지도 일반 UID 실행을 보장하지 않는다. 10-23 PJ1 Docker 29.8.1 실측에서 `mcp/git`·
`mcp/time`은 `/app/.venv/bin` 실행 권한 거부가 보고됐다. 이 판본·digest의 관찰이며 이미지 이름 전체에 대한
영구 판정이 아니다. 실행기는 관리 계정 UID를 유지하고 root로 재시도하지 않는다. 승인 미리보기와 호출 오류에는
한국어 사유·확인된 종료 코드·비밀을 숨긴 표준 오류 마지막 5줄(최대 300자)을 전달한다.
권한 거부는 이미지 파일 권한·상위 디렉터리·보안 정책 등 여러 원인이 가능하므로 root 전용이라고 단정하지 않는다.

설치기는 엔진이 없으면 배포판 패키지를 설치하고 docker 서비스를 켠다(D-225, 실패해도 원격 MCP 설치는 계속). 활성화된 장치는 승인된 로컬 서버의 폴더와
digest 고정 이미지를 첫 호출 전에 백그라운드로 준비한다(D-226). 설치기는 호스트의 Docker 설정(`daemon.json` 등)을 자동 변경하지 않는다.
설치 전 관리자가 선택할 엔진 구성은 다음과 같다.

| 선택 | 관리자 준비 | 현재 실행기와 한계 |
| --- | --- | --- |
| Docker 사용자 재매핑 | [공식 userns-remap 절차](https://docs.docker.com/engine/security/userns-remap/)에 따라 별도 subordinate UID/GID 범위와 `daemon.json`을 구성하고 변경 영향·복구를 검토 | 엔진 보안 옵션에서 사용자 재매핑을 감지하며 실행 후 실제 UID 매핑을 검증. 기존 이미지·컨테이너 저장소가 가려질 수 있고 홈 바인드 권한을 별도 검증. 관리 UID는 유지하므로 root 전용 실행 파일이 자동 호환되지는 않음 |
| rootless Podman | [공식 rootless 설명](https://docs.podman.io/en/latest/markdown/podman.1.html#rootless-mode)에 따라 별도 엔진 계정·subuid/subgid·저장소·cgroup 조건을 준비 | 현재 root 서비스의 `podman --userns=auto`는 rootless가 아님. 전용 계정 실행·마운트 매핑·복구/회수 어댑터 검증 전에는 설치만으로 지원된다고 보지 않음 |
| 사용자 재매핑 없는 Docker | 기존 위험 수용과 관리 UID 실행을 유지 | 실행 권한 거부 이미지는 차단된 상태로 유지. `--user 0`, `--privileged`, 사용자 공간 비활성화, 파일 권한 수정으로 우회하지 않음 |

Docker 데몬 재설정·rootless 전환은 별도 운영 변경이다. 이번 수정에서는 실행하지 않았다.
이번 로컬 검증과 실기기 재측정 공백은 [작업 보고](../research/llm-wiki/status/reports/2026-10-23-local-runner-usability.md)에 둔다.
