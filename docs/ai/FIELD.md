# 솔루션 기기 배치와 직원 PC 연결

[README](../../README.md)의 실행 절차를 자세히 적은 문서입니다. 현재 상태는 [개발 현황](../../research/llm-wiki/status/current.md)을 기준으로 합니다.

## 솔루션 기기(WSL/Linux)

Tailscale과 Docker Compose가 작동하는 기기에서 다음을 실행합니다.

```bash
git clone https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/full_stack_lab
./console.sh field up
./console.sh field status
./console.sh field pc-command
```

`field up`은 Tailscale IP를 자동으로 찾고 필수 내부 비밀값을 `.env`에 생성합니다.
field 전용 DB·Gitea 볼륨을 사용하므로 기존 실습 데이터는 보존하면서 실습용 개인 이름과 MCP 10종이 기본 화면에 나타나지 않습니다. 이 기기에는
Tailscale IP가 있어야 하고, 직원·관리자 PC도 같은 tailnet에서 접속할 수 있어야 합니다.
`field status`는 현재 공개 주소의 `/api/health`를 확인합니다. 기본 `./console.sh up`은
종전의 loopback 실습용입니다.

첫 설치의 시험 계정은 **관리자 `root` / `root`**, **직원 `user` / `user`**입니다. 로그인 화면에는 계정 목록이나 미리 입력된 비밀번호가 없습니다. 별도 계정은 `/signup`에서 신청하고, 관리자가 **직원·단말 → 가입 승인**에서 처리합니다. 시험이 끝나면 `field set-password`로 비밀번호를 바꿉니다(12자 이상, 화면에 보이지 않는 입력).

```bash
./console.sh field set-password root
./console.sh field set-password user
```

관리자 PC에서 `https://<Tailscale IP>/login`에 로그인합니다. 직원도 같은 URL에
자기 계정으로 로그인해 **도입 신청 → 새 신청**에서 MCP 이름이나 GitHub 주소를 먼저 검색합니다. 기존 신청의 신청자·상태를 보고, 승인된 항목은 내부 저장소를 바로 열어 클론할 수 있습니다. 새 신청은 저장소·연결 방식·목적을 제출합니다.
접수 즉시 검증 대기열에 저장되고 관리자 목록은 열어 둔 상태에서도 5초마다 데이터만 갱신됩니다(차트는 다시 만들지 않습니다).
활동 로그의 MCP 도구 사용 기록은 도입 신청을 대신하지 않습니다.

기본 field 프로필에는 **MCP 서버가 0개**입니다(`registry/field/`). 예전 회사 시스템·MCP 10종이 필요한 실습만 `./console.sh field up --with-lab-mcp`로 켭니다. 이때는 별도 볼륨에 랩 계정(`kkg@bob.local` 등, 비밀번호는 `.env`의 `MOCK_SSO_PASSWORD`, 없으면 `test-password`)을 씁니다. 실습 직원 PC까지 필요하면 `--with-lab-workstations`를 사용합니다. 일반 field 실행은 실습 컨테이너를 중지합니다.

## 내부 Git(Gitea)

검증을 통과한 공개 GitHub 저장소는 관리자가 승인할 때 같은 솔루션의 Gitea `mcp` 조직으로 가져옵니다. 가져온 기본 브랜치 HEAD가 검증 커밋과 같을 때만 승인이 완료되며 내부 저장소 주소가 신청 목록과 검색 결과에 표시됩니다. Console 왼쪽 메뉴 **바로가기 → 내부 저장소**는 개인 홈이 아니라 조직의 저장소 목록(`https://<Tailscale IP>/git/mcp`)을 엽니다.

- 로그인은 솔루션 계정 하나입니다. Console에 로그인한 브라우저는 그대로 Gitea에 들어가고, 아니면 로그인 화면을 거쳐 돌아옵니다. 계정을 중지하면 Gitea도 다음 요청부터 막힙니다.
- `root`를 포함한 솔루션 계정은 `mcp` 조직의 전체 저장소 읽기 팀에 동기화됩니다. 새 계정은 가입 승인 즉시 가입하며, 기존 계정은 서비스 기동 때 보정합니다. 관리자 역할은 Gitea 관리자입니다. 풀 리퀘스트는 끕니다. 고친 코드는 도입 신청을 다시 거칩니다.
- 클론은 같은 ID/PW로 합니다: `git -c http.sslCAInfo=/path/to/root.crt clone https://<Tailscale IP>/git/mcp/<저장소>.git`. Gitea 관리 자격은 솔루션 내부에만 둡니다.

## 승인한 소스 MCP 실행

소스 신청이 승인되고 그 저장소의 실행 레시피(`full_stack_lab/runtime/recipes/`)가 있으면 **도입 신청** 목록에 "실행" 버튼이 나옵니다. 누르면 `runtime-worker`가 내부 Git의 검증 커밋을 받아 해시를 대조하고, 레시피로 빌드해 전용 망에서 실행합니다(D-114). 상태는 목록과 보고서의 **실행** 탭에 보이고, 실행 중이 되면 "게이트웨이 등록"의 주소 칸이 실행 주소로 채워집니다. 실행 중인 신청은 그 주소로만 등록됩니다. 실행 중지·등록 해제·종료 절차에서는 실행이 멈추고 컨테이너와 망이 지워집니다. 레시피가 없는 저장소는 지금처럼 운영자가 띄운 주소로 등록합니다.

## 승인한 MCP를 Gateway에 등록

도입 신청이 **승인**되면 관리자가 목록의 **Gateway 등록**을 누릅니다. MCP 엔드포인트(사내가 아니면 HTTPS)를 넣으면 서버가 지금 광고하는 도구를 불러오고, 도구마다 읽기·쓰기·외부전송·실행 또는 미승인을, 서버에는 데이터 등급과 사용 기한(30일~1년)을 고릅니다. 등록하면 `/mcp/<id>/`로 바로 쓸 수 있고 직원의 **내 PC 연결** 명령에도 들어갑니다.

- 관리자가 본 도구 계약(해시)과 등록 순간 서버의 계약이 다르면 등록을 거부합니다. 고정한 계약은 이후 호출마다 다시 대조합니다.
- 도구 설명에 모델을 조종하는 문구(`<IMPORTANT>` 태그, "사용자에게 말하지 마라", `~/.ssh` 같은 경로, 보이지 않는 문자 등)가 보이면 도구 옆에 경고가 붙고, 그 도구를 고를 때는 설명을 읽고 확인했다고 표시해야 등록됩니다(D-52).
- 사용 기한이 지나면 호출이 `P-APPROVAL-EXPIRY-001`로 막힙니다. 만료 7일 전부터 승인 근거(허용 도구의 설명·스키마, 서버 정상·운영 중,
  공급망 치명 취약점 없음, 허용 목적지)가 그대로면 원래 기간만큼 자동 연장하고 레지스트리 이력에 `approval-renewed`를 남깁니다(D-70).
  근거가 하나라도 바뀌었거나 이미 만료됐으면 연장하지 않으며, 도구 계약을 바꾸려면 새 도입 신청·승인이 필요합니다(D-57·D-59). **MCP 서버** 화면에서는 등록 해제를 합니다. 해제한 서버는 기록과 함께 사용 중지로 남고, 이용 관계 `UR-<ID>`는 **종료·폐기** 절차에 올릴 수 있습니다.
- 등록은 승인된 도입 신청을 통해서만 됩니다. 신청자와 승인자는 달라야 하고, 승인 1건은 등록 1개이며, 운영 중인 다른 서버 id를 덮어쓰지 않습니다. 공급자 호스팅 서비스는 계약 검토 때 지정한 사용자만 쓰고(`MCP-REGISTRY-003`), 신청 기록이 없는 예전 직접 등록은 실행되지 않습니다.

개요의 허용·경보·차단 수치를 누르면 해당 활동 로그로 이동합니다. 직원·단말은 폐기 자격과 발급만 되고 보고하지 않은 장치를 기본 목록에서 제외합니다. 도입 신청의 검증은 [아래 절](#mcp-도입-신청-자동-검증)을 봅니다. 원격 MCP 후보와 취약 버전·엣지 케이스는 [field 후보 목록](FIELD_MCP_CANDIDATES.md)을 참조합니다.

직원·단말 → 계정에서 사용·중지·잠김 중 하나를 라디오 버튼으로 고릅니다. 상태 변경 후 목록 갱신이 끝나면 완료 메시지를 표시하며, 갱신 중에는 상태 변경 버튼을 다시 누를 수 없습니다.
관리자는 다른 계정을 **삭제**할 수도 있습니다. 삭제 즉시 기존 토큰·Git 접근이 차단되고 조직 멤버십이 제거됩니다. 감사 기록과 아이디 중복 방지용 신원 행은 남기며, 본인과 `root` 계정은 삭제할 수 없습니다.

## 직원 PC의 Claude Code·Codex CLI 연결

웹 Console 가입·로그인과 MCP 실행 인증을 구분합니다. field 일반 계정은 관리형 연결이 필수입니다.
가입 승인·초대 수락 후 **내 PC 연결**에서 개인별 ZIP을 받습니다. 가입자에 묶인 등록 토큰은 30분 동안 한 번만
사용할 수 있습니다. 단말이 활성화되지 않았으면 로그인 직후 설치 안내가 열립니다. MCP 서버가 없어도 설치할 수 있습니다.

받은 파일을 풀고 **설치 파일 하나를 실행한 뒤 OS 권한 확인에 한 번 응하면** 끝납니다(D-71). 필수 구성요소 설치, 승인 하네스 배치,
관리 계정 결정, 관리형 설정·프록시 구성, 모델 로그인까지 설치기가 합니다. 이미 설치돼 있으면 같은 파일이 재설치·복구 경로입니다.

```bash
unzip mcp-managed-kit-linux.zip -d mcp-managed-kit && ./mcp-managed-kit/install.sh
```

Windows는 `mcp-managed-kit-windows.zip`을 풀고 `install.cmd`를 두 번 눌러 실행합니다. Python 3.10 이상이 모든 사용자용
(Program Files)으로 설치돼 있어야 합니다. Linux는 Python 3.10 이상과 systemd가 필요하고, gcc·nftables·AppArmor 도구는 설치기가 깝니다.

직원 계정이 **관리 권한이 있는 계정**이면 자기가 지울 수 있는 규칙으로 자기를 통제할 수 없으므로, 설치기가 관리 계정을 따로 만듭니다.
Linux는 평소 계정에서 `codex`·`claude`를 그대로 치면 그 계정의 로그인 셸을 거쳐 실행되고(AppArmor·방화벽 동일 적용),
Windows는 만들어진 계정으로 로그인해 쓰라고 안내합니다. 관리 계정은 홈이 달라 평소 계정의 파일은 읽지 못합니다.

Linux 설치기는 root 비밀 경로에 단말 키를 저장하고, 레지스트리에서 만든 시스템 설정 4개·AppArmor·UID 방화벽·root 서비스를
설치합니다. Windows 설치기는 `%ProgramData%` 관리자 전용 경로에 단말 키를 두고, 관리형 하네스 설정(Claude Code
`C:\Program Files\ClaudeCode\`, Codex `%ProgramData%\OpenAI\Codex\requirements.toml`과 계정 `config.toml`의 표식 블록)·
계정 SID 범위의 Windows 방화벽 차단 규칙·SYSTEM 예약 작업을 설치합니다. Console의 **직원·단말 → 단말**에서 다른 관리자가 실제 호스트 집행을 확인한 뒤 활성화해야 MCP 인증이 열립니다.
root·SYSTEM 서비스만 장기 단말 키를 보유합니다. 하네스 헬퍼는 UID가 일치하는 Unix 소켓(Windows는 계정 SID만 열 수 있는
명명 파이프)에서 5분짜리 단말·정책 결합 JWT만 받습니다.
사용자 비밀번호 grant와 기존 refresh grant로 관리형 조건을 우회할 수 없습니다.

정책 확인은 60초마다 합니다. 180초 동안 보고가 없거나 설정·OS 집행이 불일치하거나 단말 자격이 폐기되면,
아직 만료되지 않은 JWT도 MCP 진입과 도구 실행 직전에 거부합니다. 정상 보고만으로 격리를 풀지 않습니다.
설치·연결 거부와 실제 커널 차단은 직원·단말의 별도 이력에, 실제 도구 실행 판정은 활동 로그에 기록합니다.

이 프로필은 관리 계정의 바깥 통신을 솔루션 기기의 게이트웨이 포트와 모델 프록시 포트(기본 3128)로만 묶습니다.
하네스는 `HTTPS_PROXY`로 프록시에 접속하고, 프록시(tinyproxy)는 `full_stack_lab/model-proxy/model-domains.txt`의
모델 도메인만 허용합니다(TLS 터널은 443만, D-67). MCP 호출은 `NO_PROXY`로 게이트웨이에 직접 갑니다. 하네스의 모델 로그인(`codex login`·
`claude` 로그인)은 관리 계정에서 직원이 한 번 합니다. 재설치·제거 절차와 실측 증거는 [Endpoint Agent](../../endpoint-agent/README.md),
설계 결정은 [D-61](DECISIONS.md#d-61-가입을-관리형-단말-연결의-시작점으로-2026-10-01)·D-67·D-68을 봅니다.

`field/pc/mcpgw_pc.py`의 비관리 setup은 기존 랩·관측용으로 남습니다. field 일반 계정의 실행 인증을 발급하지 않습니다.

## 누가 무엇을 강제하는가 (D-62)

Console **통제 범위**와 `GET /api/integrations`는 MCP·커넥터·플러그인·stdio·섀도를 다섯 분류
(`gateway_mcp`·`gateway_backend_connector`·`vendor_native_connector`·`local_plugin_or_stdio`·`shadow_or_unknown`)로
나누고, 관리 주체와 상태를 증거와 함께 보입니다.

| 상태 | 뜻 | 근거 |
| --- | --- | --- |
| Gateway 강제 | 이 경로의 호출은 Gateway가 실행 전에 판정 | 원장 행·실행 시각 |
| Endpoint 강제 | 관리 계정의 실행·egress를 OS가 제한 | 180초 안의 heartbeat, AppArmor·UID nft(Windows는 SID 방화벽 규칙)·보호 설정 일치 |
| Vendor 강제(수기 확인) | 벤더 관리 콘솔에서 차단 | 관리자가 기록한 콘솔 상태·scope·역할 |
| 관찰만 | 보고는 있으나 막는 주체 없음 | 키트·관측 에이전트 보고 |
| 미등록·알 수 없음 | 관리형 단말 없음 | 가입자 단말 등록 부재 |
| 우회 가능 | 직접 경로가 열려 있음 | 같은 단말의 다른 계정(관리자 그룹 포함)·WSL·관리형 설치 없는 Windows·비관리 단말 |

섀도 MCP **발견**은 차단이 아닙니다. 관리 단말에서 커널 규칙이 확인될 때만 Endpoint 강제로 표시합니다.
활동 로그의 각 호출은 출처·Gateway 통과·강제 주체·upstream 시도/실행·응답 처리(반환·마스킹·실행 후 보류)·
PAC 실패와 다른 해당 정책을 함께 보여 줍니다. 응답 보류는 이미 실행된 쓰기·전송을 되돌리지 않습니다.
감사 원장에는 응답 원문 대신 해시·크기·형식·마스킹 유형만 남습니다.
상태는 커널 heartbeat·원장·수기 기록·자체 보고와 짝으로 표시하고 만료된 근거로 강제 완료를 표시하지 않습니다.
실기기 원장, 등록 해제 시험에서 찾은 복구 결함과 UI 배포 기록은
[통제 범위 검증](CONTROL_PLANES_2026-10-01.md)(D-62/D-63)을 따릅니다.

## 하네스가 기본으로 붙이는 커넥터(claude.ai 커넥터·ChatGPT 앱·기본 기능)

Claude Code는 claude.ai 계정에 연결한 커넥터(`claude.ai Notion` 등)와 플러그인 서버를, Codex는 ChatGPT 앱과 웹 검색·브라우저·
컴퓨터 조작 같은 기본 기능을 Gateway를 거치지 않고 씁니다. 키트가 이것들을 모아 보고합니다 — setup·doctor 끝에, 그리고
하네스가 연결할 때 6시간에 한 번(`python3 ~/.mcpgw/mcpgw_pc.py report`로 바로 보낼 수도 있음). 보내는 것은 이름과 목적지
호스트뿐입니다.

- 관리자는 **직원·단말 → 하네스 커넥터**에서 예외 승인·거부를 기록합니다. 벤더 출처와 무관하게 **미승인 항목은 처음부터
  거부 정책 대상**입니다. `CONNECTOR_REVIEW_DAYS`(기본 14일)는 검토 기한이며 사용 유예가 아닙니다(D-53).
- 관리형 단말은 키트 없이 서비스가 직접 보고합니다: 관리 계정의 `claude mcp list`·`claude plugin list`, Codex 앱·기능·웹 검색 유효값을
  6시간마다 장치 자격(`POST /api/endpoint/harness-inventory`)으로 보내고, 보고 항목은 소유자의 관리 단말 상태로 판정합니다(D-220).
- 관리형 Claude Code는 계정 동기화 플러그인·스킬(`syncClaudeAiPlugins`·`syncClaudeAiSkills`)과 WebFetch·WebSearch(`permissions.deny`,
  `allowManagedPermissionRulesOnly`)도 닫습니다(D-219). 특정 벤더 커넥터를 열어 주는 경로는 설계만 있습니다(D-222).
- 사용자 설정 적용은 보조 조치입니다. 목록에서 사라져도 실제 차단이 입증되지 않아 화면에는 **차단 미검증**으로 표시합니다.
- `mcpgw_pc.py managed …`는 항상 세 파일을 만듭니다. Claude Code는 Gateway 서버만 고정하고 계정 커넥터·새 마켓플레이스를
  제한합니다. Codex는 `requirements.toml`의 서버 이름·URL 제약과 Apps·플러그인·웹 검색·브라우저/컴퓨터 사용 제한을 받습니다.
  IT가 시스템 위치에 배포하고 직원이 파일을 바꾸지 못하게 보호해야 합니다. 예외 승인으로 이 프로필이 자동 확장되지 않습니다.
- 이 범위는 **지원 버전의 관리형 CLI**입니다. Desktop·웹·다른 클라이언트·셸의 직접 API 호출에는 별도 조직 설정·단말 실행 통제·
  egress·상위 자격 통제가 필요합니다. 비교 조사·위협 모델·실측과 남은 일은 [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md).

### 현장 TLS와 루트 배포(D-124)

Caddy는 **Tailscale IP의 443에 HTTPS만** 게시합니다. `tls internal`의 루트·개인 키는 배치의
`field_caddy_data` 볼륨에 유지됩니다. TLS 1.2·1.3과 ECDHE/ECDSA AEAD 암호군을 사용하며,
HTTP 리디렉션과 시스템 신뢰 저장소 자동 등록은 끕니다. 평문 요청은 프록시하지 않습니다.
클라이언트도 원격 HTTP URL을 거부하므로 인증 토큰을 보내기 전에 멈춥니다.
기본 loopback 실습의 내부 HTTP는 현장 게시와 별개입니다.

브라우저 콘솔은 같은 Tailscale IP의 `http://…:8000`으로도 엽니다(D-129). 이 포트는 콘솔·내부 Git만 제공하고 하네스·키트·장치 보고 경로는 421로 거절합니다.

```bash
cd full_stack_lab
./console.sh field up
./console.sh field ca
openssl x509 -in field/ca/root.crt -noout -fingerprint -sha256
curl --cacert field/ca/root.crt https://100.83.175.111/api/health
```

`field ca`는 공개 루트와 DER 기준 SHA-256 지문만 내보냅니다. 개인 키는 꺼내지 않습니다.
루트를 인증된 조직 배포 경로로 전달하고, 지문은 운영자와 별도로 대조합니다. ZIP 안의 지문만으로
키트 발행자의 진위를 입증하지 않습니다. Console이 발급하는 ZIP에는 `root.crt`, `root.sha256`,
동일한 `ca_certificate`·`ca_sha256`을 담은 `enrollment.json`, 직원 PC 도구가 들어갑니다.
Linux 설치기는 지문 불일치·다중 인증서를 등록 요청과 설치 변경 전에 거부합니다.
처음 브라우저에 표시되는 사설 루트 경고는 키트 설치 전에 별도로 처리합니다.
`field status`·`field pc-command`에 표시된 지문을 운영자와 대조한 뒤, 별도 Firefox 프로필의
**설정 → 개인 정보 및 보안 → 인증서 보기 → 인증 기관 → 가져오기**에서 `root.crt`를 선택하고 웹사이트 식별 신뢰를 지정합니다.
이 프로필에만 적용하며 Windows 인증서 관리자나 시스템 전체 저장소에는 추가하지 않습니다.

관리형 Linux 실행기는 root 소유 공개 CA 파일을 Claude Code의 `NODE_EXTRA_CA_CERTS`, Codex의
`CODEX_CA_CERTIFICATE`로 전달합니다. 직원 PC 도구를 별도로 쓰는 경우 다음처럼 실행합니다.

```bash
python3 mcpgw_pc.py setup --url https://100.83.175.111 --servers 승인서버 --ca root.crt --ca-sha256 운영자가확인한지문
python3 ~/.mcpgw/mcpgw_pc.py harness claude
python3 ~/.mcpgw/mcpgw_pc.py harness codex
```

환경값은 해당 실행 프로세스에만 들어갑니다. 이미 열린 하네스는 종료 후 다시 실행해야 합니다.
`agent.py`와 이를 공유하는 `os-observer.py`도 동일한 CA·지문으로 HTTPS를 검증합니다.
`/api/endpoint/*`는 게이트웨이로 연결되므로 이전 HTTP 배치의 원격 보고 제한은 제거됩니다.
이는 구현 범위이며 현재 기기의 HTTPS 보고 성공은 [실기기 시험](../../research/llm-wiki/status/reports/2026-10-18-field-tls-d124.md) 후 판정합니다.
Windows 관리형 설치도 등록 전에 같은 CA·지문을 대조하고 서비스·관측기에 보존합니다.
관리자 단계는 보호된 승인 매니페스트의 파일 해시를 확인한 루트로 사용자 요청의 CA를 대체합니다.
Claude·Codex는 `%ProgramFiles%\MCPGatewayManaged\launchers\<SID>\`의 `.cmd` 실행기를 사용합니다.
실행기의 `setlocal`이 CA 환경값을 해당 하네스 프로세스에만 전달하며 계정 레지스트리에 CA 환경값을 저장하지 않습니다.
설치 위치에 같은 이름의 다른 하네스가 있으면 위 실행기 경로를 직접 사용합니다. PowerShell 연결 확인은 TLS 1.2와 요청별 CA 검증을 사용합니다.

공개 이름을 추가하려면 `.env`의 `FIELD_PUBLIC_NAME=mint.example.internal`을 지정하고 `field up`을 실행합니다.
IP와 해당 이름을 각각 인증서 발급 대상으로 관리하고, IP 연결의 빈 SNI에는 IP 인증서를 선택합니다.
공개 URL·키트는 계속 Tailscale IP를 사용합니다. `*.ts.net` 공개 인증서 발급에는 의존하지 않습니다.
루트 볼륨을 지우거나 새 배치로 옮기면 새 CA가 발급되므로, 기존 연결은 실패하고 지문 확인·키트 재설치가 필요합니다.

## MCP 도입 신청 자동 검증

공급자 호스팅 MCP(엔드포인트 신청)는 구현 소스를 검사할 수 없으므로 검증 대기열에 들어가지 않고 **검토 대기**로 시작해,
관리자가 실제 광고 도구 계약·사용 주체·기한을 검토한 뒤 다른 관리자가 승인합니다(D-57).
구현 저장소 신청을 제출하면 격리 워커(`intake-worker`)의 검증 대기열에 자동 등록됩니다. 워커는 저장소를 고정 커밋으로 받아
Syft(CycloneDX SBOM)·Trivy·Semgrep을 돌리고, 문서에서 C1~C4 종료 조건의 근거 후보를 찾습니다. 관리자는 도입 신청의
**검증 보고서**에서 취약점·코드 검사, SBOM 구성요소와 라이선스, 종료조건 조사를 확인하고 원본 JSON을 내려받을 수
있습니다. 검사 실패 사유와 성공한 단계의 보고서는 함께 보존되며 재검증할 수 있습니다.

**종료 조건**은 검증 보고서의 **종료 조건** 탭에 조건마다 충족·미충족·불명확과 근거 문장(파일·줄 링크), 예상 등급이 나옵니다.
C1(제공자가 쥔 자격을 밝혔는가)이 없으면 T3, 폐기 방법(C2)이나 종료 후 감사 기록(C4)이 없으면 T2입니다. `.env`의
`TYPESAFE_API_KEY`가 있으면 TypeSafe Jev가 판정하고, 없으면 규칙으로 판정합니다. 원격 서버는 결론이 T1이면 바로, 아니면
**위험 수용 사유**(10자 이상)를 적거나 제공자 문서로 확인한 기록을 남겨야 승인됩니다. 결론은 제공자의 실제 회수나 계약을
검증한 것이 아니며 최종 도입 승인은 관리자가 합니다.

## SIEM 연동

판정(`decisions`)·승인 이력(`approval_events`)·실제 경보(`ops_alerts`)는 같은 트랜잭션에서 `siem_outbox`에 참조가 쌓이고, `siem-worker`가 OCSF JSON 한 건씩 HTTPS로 보냅니다. 합성 경보는 보내지 않습니다. 받는 쪽이 `Idempotency-Key`(=`metadata.uid`)로 중복을 합치고, 2xx는 저장이 끝난 뒤에만 돌려줘야 합니다. 응답이 없거나 5xx이면 outbox가 5초 간격으로 시작해 최대 1시간까지 늘려 가며 다시 보냅니다.

SIEM 제품은 제품 스택과 다른 compose 프로젝트로 세웁니다(`full_stack_lab/siem/`: OpenSearch · Dashboards · Vector 수신 앞단, Tailscale IP에만 게시). 켜는 순서는 다음과 같습니다.

1. SIEM 쪽: `SIEM_BIND=<Tailscale IP> full_stack_lab/siem/setup.sh <제품 siem-secrets 절대경로>` — 난수 토큰·사설 CA를 만들고 `ca.pem`·`token`을 제품 `siem-secrets/`에 둡니다.
2. 토큰 파일 소유자를 워커 UID(10001)로 바꾸고 0600으로 둡니다(`sudo chown 10001:10001 siem-secrets/token`).
3. `.env`에 `SIEM_URL=https://<Tailscale IP>:8688/ingest`, `SIEM_TOKEN_FILE=/run/siem/token`, `SIEM_CA_FILE=/run/siem/ca.pem`.
4. `./console.sh field siem up` — 워커 컨테이너만 만들고 게이트웨이 등 나머지는 다시 만들지 않습니다. `field siem status`는 대기열(전달·대기·최대 시도), `field siem down`은 워커만 멈춥니다. 값이 빠져 있으면 `up`과 `field up --with-siem`이 시작 전에 거절합니다.

`field up`(옵션 없음)은 워커를 건드리지 않아 켜 둔 워커가 그대로 남습니다. 토큰·CA 파일은 매 전송마다 다시 읽으므로 교체에 재시작이 필요 없습니다(수신 쪽 Vector는 토큰을 설정 시점에 읽으므로 재시작).
