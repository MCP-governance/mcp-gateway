# MCP 서버 10종 — 무엇을, 어떻게 띄우고, 무엇을 조심하나

> 정본: `full_stack_lab/registry/catalog.toml`(승인 도구·r/w/x·배치 형태·종료 조건),
> `full_stack_lab/mcp/runtime.Dockerfile`(설치), `full_stack_lab/mcp/run-server.sh`(실행 플래그),
> `full_stack_lab/registry/contracts.lock.json`(도구 설명·스키마 해시). 이 문서는 그 요약과 함정 모음이다.

## 1. 한눈에

| id | 패키지 | 버전 | 실행 | 승인 도구(r/w/x) | 하위 시스템 | 배치 |
| --- | --- | --- | --- | --- | --- | --- |
| filesystem | @modelcontextprotocol/server-filesystem | 2026.8.31 | mcp-proxy | 10/4/0 | `/shared` 공유 드라이브 | 사내 |
| git | mcp-server-git (PyPI) | 2026.8.18 | mcp-proxy | 7/5/0 | `/repos` 저장소 볼륨 | 사내 |
| fetch | mcp-server-fetch (PyPI) | 2026.8.18 | mcp-proxy | 1/0/0 | 인트라넷·외부 웹 | 사내 |
| memory | @modelcontextprotocol/server-memory | 2026.8.31 | mcp-proxy | 3/6/0 | 지식 그래프 파일 | 사내 |
| desktop | @wonderwhy-er/desktop-commander | 0.2.51 | mcp-proxy | 11/6/2 | `/workspace` 샌드박스 | 사내 |
| postgres | postgres-mcp (PyPI) | 0.3.0 | mcp-proxy | 9/0/0 | `corp-db` | 사내 |
| redis | redis-mcp-server (PyPI) | 0.5.1 | mcp-proxy | 14/12/0 | `corp-redis` | 사내 |
| email | mcp-email-server (PyPI) | 1.9.1 | 네이티브 HTTP | 8/9/0 | `corp-mail`(GreenMail) | **제공자(MailOps)** |
| gitea | gitea-mcp-server | 1.7.0 | 네이티브 HTTP | 29/10/0 | `corp-git`(Gitea) | **제공자(DevHub)** |
| playwright | @playwright/mcp | 0.0.82 | 네이티브 HTTP(MS 이미지) | 13/6/1 | 인트라넷·외부 웹 | 사내 |

- 도구 이름은 Gateway에서 `<id>__<tool>`로 보인다. 카탈로그에 없는 광고 도구는 `enabled=false`로
  숨겨지고 호출하면 `MCP-REGISTRY-002`.
- `postgres`는 모든 도구가 r이다. `execute_sql`의 실효 행위는 `classify.py`가 SQL을 보고 정한다
  (`SELECT`→r, `INSERT/UPDATE/DELETE`→w, DDL→x).
- "제공자" 배치는 논문의 **원격 MCP 서비스**를 모사한다. 서버가 하위 시스템에 대한 자격을 들고 있고,
  조직은 그 서버를 직접 운영하지 않는다는 뜻이다. 종료 조건(`exit_terms`)이 여기서만 의미가 있다.

## 1-1. 하네스가 서버에 닿는 법
직원 PC의 하네스(Claude Code·Codex·Gemini CLI·OpenCode)는 각 서버를 Gateway의 `/mcp/<server>/`로 본다 —
하네스 관리형 설정에 서버 하나당 URL 하나가 있고, 도구 이름도 그 서버 고유 이름 그대로라 직접 붙은 것처럼
보인다(판정 경로는 집계 엔드포인트 `/mcp/`의 `<server>__<tool>`과 같다. 집계 엔드포인트도 유지됨).
관리형 설정 파일(Claude Code `/etc/claude-code/managed-mcp.json`, Codex `/etc/codex/managed_config.toml`,
Gemini CLI `/etc/gemini-cli/settings.json`, OpenCode `/etc/opencode/opencode.json`)은 `registry/catalog.toml`에서
워크스테이션 이미지 **빌드 때** `workstation/managed/render.py`가 만든다. 그래서 서버를 추가·바꾸는 절차는
"카탈로그를 고치고 워크스테이션 이미지를 다시 빌드"로 끝난다 — 컨테이너 안의 설정 파일은 손으로 고치지 않는다.

## 2. 설치·실행 구조

- **런타임 이미지 하나**(`mcp/runtime.Dockerfile`)에 9종이 들어 있다: python:3.12-slim + Node 22.
  - npm 패키지는 `--ignore-scripts`로 설치한다(설치 스크립트 실행 금지).
  - PyPI 서버는 서버별 venv(`/opt/venvs/<id>`)에 `pip install "<pkg>==<ver>" "mcp>=1.17,<2"`.
  - `gitea-mcp`는 공식 이미지에서 바이너리만 복사한다.
  - desktop-commander 설정에서 `telemetryEnabled=false`.
- Playwright는 Microsoft 공식 이미지를 그대로 쓴다(Chromium 포함).
- compose의 MCP 서비스는 `x-mcp` 앵커를 공유한다: `restart: unless-stopped`, `hostname: mcp-<id>`
  (D-13), `tools` 망 + 필요한 경우 `corp`/`internet`, 호스트 포트 없음, healthcheck.
- 모든 서버는 컨테이너 안 `:8000/mcp`로 Streamable HTTP를 연다. Gateway는 `registry`의 `endpoint`로 붙는다.

## 3. 서버별 메모

### filesystem
- 루트는 `/shared`(corp-seed가 채운 볼륨). 분류: `/shared/public`·`/shared/partners` 공개,
  `/shared/team` 내부, `/shared/confidential` 중요. 소관 부서는 `[classification.owners]`.
- 협력사 직원이 `/shared/confidential/audit/external-audit-copy-2026.md`를 읽는 것은 예외 EXC-001로 경보 허용.

### git
- `/repos/handbook`(공개), `/repos/payment-service`(내부, **과거 커밋에 유출된 비밀** 포함),
  `/repos/infra-secrets`(중요). 인자 `repo_path`가 자원이다.

### fetch
- 한 도구(`fetch`)가 인트라넷·외부 웹·회사 시스템 관리 API까지 닿는다 → SSRF 정책 `MCP-EGRESS-002`.
- **함정**: readabilipy가 첫 실행 때 `npm install`을 한다. 폐쇄망에서는 멈춘다 → 이미지 빌드 때
  readabilipy의 JS 의존성을 미리 설치한다.
- **함정**: Readability가 숨김 텍스트를 지운다. 그래서 `intranet/vendor-faq.html`에는 숨김 영문 주입과
  **보이는 한국어 주입 문단**이 둘 다 있다(간접 프롬프트 주입 시나리오).

### memory
- `MEMORY_FILE_PATH=/data/memory.jsonl`. 카탈로그에서 `data_class = "nonimportant"`로 고정.

### desktop (desktop-commander)
- 작업 디렉터리 `/workspace`(샌드박스). `start_process`·`interact_with_process`는 x.
- 플랫폼개발팀의 `start_process`는 예외 EXC-002로 **건별 관리자 승인** 후 실행.
- **함정**: `start_process` 설명에 `Container: <hostname>`이 들어간다 → hostname 고정(D-13).
  고정 전에는 컨테이너 재생성마다 DRIFT.

### postgres (postgres-mcp)
- `--access-mode=unrestricted` — 제한은 서버가 아니라 Gateway가 한다(그게 이 실습의 요점).
- 테이블 분류: `public.products` 공개, `sales.orders`·`hr.employees` 내부, `sales.customers`(PII)·
  `hr.salaries` 중요. 카탈로그 뷰는 메타데이터로 공개.

### redis
- 키 접두사 분류: `cache:` 공개, `feature:` 내부, `session:` 중요.

### email (mcp-email-server)
- `MCP_ALLOWED_HOSTS: mcp-email:8000` 필요(없으면 421 Misdirected Request).
- 서버가 `ai-assistant@bob.local` 메일함 비밀번호를 **보유**한다. `exit_terms`가 전부 false →
  종료 시 모집단을 열거할 수 없어 최선 등급 **T3** (논문의 "고지 없는 제공자").
- 외부 수신자 메일은 x로 승격, 저널 BCC(`compliance@bob.local`) 제한 실행(`P-X-RESTRICT-001`).
- 세션을 발급한다(E2): DELETE 200 후 같은 세션 404.

### gitea (gitea-mcp)
- 토큰은 corp-seed가 `mcp-bot`(Owners 팀)으로 발급해 `/run/corp-secrets/gitea-mcp.token`에 쓴다.
  Gateway를 거치지 않는다. `server_held_credentials`에 고지되어 있고 `verify = "gitea-token"`이라
  조직(=Gitea 관리자)이 직접 폐기·확인할 수 있다 → 최선 등급 **T1**.
- E3: 상위 토큰을 완전히 폐기해도 이 PAT로의 접근은 200, 제공자 쪽 폐기(204) 뒤에야 401.
- 종료 케이스가 PAT를 폐기하면 `./console.sh restore-token gitea`로 재발급해야 도구가 다시 동작한다.

### playwright
- headless Chromium, 세션 발급(E2). `browser_evaluate`는 x. 페이지 내용이 도구 결과로 돌아오므로
  간접 주입 경로다(`request.untrusted_markers`).

## 3-1. 출력 마스킹이 서버 결과에 미치는 영향
모든 실행 결과는 Presidio를 거친다(D-23). 가려지는 것: 주민번호, 휴대전화, **외부 도메인** 이메일, 카드·IBAN·SSN,
`password=`류 자격 문자열. 가려지지 않는 것: 날짜·이름·URL·IP, 사내(`bob.local`) 주소, 호출의 수신자 주소.
그래서 postgres의 `sales.customers` 조회는 이름만 보이고 전화·주민번호·이메일이 `[REDACTED]`가 된다.

## 4. 발견한 함정 (다시 밟지 말 것)

| 증상 | 원인 | 조치 |
| --- | --- | --- |
| mcp-proxy·postgres-mcp가 import에서 죽음 | MCP SDK 2.x | venv마다 `mcp>=1.17,<2` |
| 잠금의 `server_version`이 전부 1.30.0 | mcp-proxy가 자기 SDK 버전을 보고 | 패키지 버전은 `package` 필드로 확인 |
| fetch 첫 호출이 멈춤 | readabilipy 런타임 npm install | 빌드 때 설치 |
| desktop 계약이 재생성마다 DRIFT | 설명에 컨테이너 id | `hostname` 고정 |
| email 421 | 허용 호스트 | `MCP_ALLOWED_HOSTS` |
| 옛 `UNSAFE_METADATA`가 email 설명의 "credential"을 오탐 | 단어 목록 방식 | 지시문 패턴(영·한) 방식으로 교체, 222개 도구 오탐 0 |
| 업스트림 결과 거부가 `MCP-UPSTREAM-001`로 기록 | 클라이언트 TaskGroup 안에서 예외 → ExceptionGroup | `_call_upstream`이 컨텍스트를 닫은 뒤 판단, `_root_cause` |

## 5. 서버를 추가·교체하는 법

1. `mcp/runtime.Dockerfile`에 설치(버전 고정), `mcp/run-server.sh`에 실행 줄.
2. `compose.yaml`에 `mcp-<id>` 서비스(`<<: *x-mcp`, 필요한 망만).
3. `registry/catalog.toml`에 `[servers.<id>]`(package·version·endpoint·deployment·downstream·
   source_url·supplier·license, 제공자면 `exit_terms`·`server_held_credentials`)와 `[servers.<id>.tools]`.
4. 분류 규칙이 필요하면 `[classification.*]`와 `gateway/app/classify.py`의 추출기, `python -m app.classify`.
5. 띄운 뒤 `./console.sh contracts --update` → `registry/contracts.lock.json` diff를 **읽고** 커밋.
6. 이용 관계가 있으면 `[[usage_relationships]]`, 시나리오가 있으면 `workstation/scenarios/*.toml`.
7. 하네스가 새 서버를 보게 워크스테이션 이미지도 다시 빌드(`./console.sh up`이 이미지 빌드를 포함) — 관리형
   설정은 카탈로그에서 렌더링되므로 이 단계를 건너뛰면 하네스가 새 서버를 못 본다.
8. `./console.sh test`(`harnesses`로 하네스 4종이 새 서버에 붙는지도 같이 확인).
