# 하네스 기본 기능·기본 커넥터 통제 설계 근거 (2026-10-28, D-298)

브랜치 `10/28-windows-kit`. 소유자 지시: 「하네스 기본기능/커넥터를 웹콘솔에서 확실히 구분하고, 기본기능·기본커넥터는 기본 승인이되 관리자가 차단 가능하게」.

## 1. 우리 솔루션에서 이 항목들이 갖는 성격

- MINT는 승인 MCP 호출을 **게이트웨이에서 호출마다 판정**한다(PAC·OPA·원장). 그런데 하네스 기본 기능(웹 가져오기·웹 검색·브라우저 조작 등)과 하네스 계정 커넥터(claude.ai 커넥터·ChatGPT 앱)는 **게이트웨이를 거치지 않고 벤더로 바로** 간다. 호출별 판정·원장 기록이 없다.
- 그래서 이 항목들에 MINT가 할 수 있는 통제는 두 가지다. ① 엔드포인트 관리형 설정으로 하네스가 그 기능을 켜지 못하게 하는 것(하네스 수준 집행). ② 키트 인벤토리로 어떤 PC에서 무엇이 켜져 있는지 보는 것(관찰).
- 기본 모드는 간편 모드(D-239)다. 직원 계정과 직원 하네스를 그대로 쓰고, 보안 공백은 「타 솔루션(EDR·DLP·프록시)」이 받친다는 소유자 가정 위에 있다.
- 직원이 직접 붙이는 MCP 서버와 플러그인은 `managed-mcp.json`의 독점 통제와 Codex `requirements.toml` 허용 목록 때문에 하네스에서 아예 안 켜진다. 키트는 이것들을 섀도우로 탐지하고 보고한다(D-297 실측).

## 2. 참고한 자료

| 출처 | 확인한 사실 | 적용 |
|---|---|---|
| Claude Code, Control MCP server access (code.claude.com/docs/en/managed-mcp) | `managed-mcp.json`은 독점 통제다. 직원·플러그인 서버를 막고 claude.ai 커넥터도 끈다. `allowAllClaudeAiMcps: true`(관리형 설정에서만 유효)면 claude.ai 커넥터를 같이 싣는다. 그때도 허용·거부 목록이 커넥터에 적용된다. 거부 목록이 우선하고 `serverUrl`(와일드카드·포트 규칙) 또는 `serverName`("claude.ai Slack")으로 막는다. 이름은 바뀔 수 있으니 `serverUrl` 권장. | 기본 커넥터 허용 = `allowAllClaudeAiMcps: true` + 허용 목록에 `https://*/*`(관리형 서버는 허용 목록을 건너뜀). 개별 차단 = `deniedMcpServers`에 `*://host:*/*` + 이름. 전체 차단 = `disableClaudeAiConnectors: true`. |
| Claude Code, Configure permissions (code.claude.com/docs/en/permissions) | deny가 allow보다 우선하고, 이름만 쓴 `WebFetch` deny는 도구를 아예 뺀다. `allowManagedPermissionRulesOnly`면 관리형 규칙만 인정한다. 이름만 쓴 `WebFetch` deny는 claude.ai 아티팩트 읽기에는 적용되지 않는다. | 기본 기능 차단 = `permissions.deny`에 `WebFetch`/`WebSearch`. 직원이 다시 허용할 수 없다. 아티팩트 예외는 한계로 기록. |
| Codex, Managed configuration (learn.chatgpt.com/docs/enterprise/managed-configuration) | requirements는 「사용자가 덮어쓸 수 없는 관리자 제약」이다. `/etc/codex/requirements.toml`. `allowed_web_search_modes`(`disabled`는 늘 허용), `features.apps=false`는 앱·커넥터를 끈다. `features.plugins`, `browser_use`, `computer_use`. MCP는 이름과 identity가 모두 맞아야 켜진다. `managed_config.toml`은 시작 기본값이다. | 기능 차단 = requirements `[features]`·`allowed_web_search_modes`. 플러그인은 늘 끔. ChatGPT 앱 전체 = `features.apps`. |
| Claude Team/Enterprise 관리자 설정(support.claude.com 15537633 외) | 조직 Owner가 Admin Settings > Connectors에서 커넥터를 켜고, 구성원은 자기 계정을 연결한다. 조직 단위 인가는 베타다. | 벤더 콘솔 통제가 따로 있다. MINT 화면의 「벤더 콘솔」 칸(수동 확인)과 병행한다. |
| ChatGPT Enterprise 앱 관리자 통제(help.openai.com 11509118) | 앱은 Enterprise/Edu에서 기본 꺼짐이다. 관리자가 켜고 역할별로 배정하며, 앱별 읽기/쓰기 동작을 허용할 수 있다. | 벤더 쪽 기본값은 「꺼짐」이지만, 엔드포인트 하네스 수준의 막기는 MINT가 한다. 앱별 끄기는 `[apps.<id>] enabled=false`. |
| GitHub Copilot MCP 정책(docs.github.com, manage-mcp-usage) | 조직·엔터프라이즈가 「MCP servers in Copilot」 정책을 켜고 끈다(기본 꺼짐). 레지스트리 전용 모드가 있다. 내장 GitHub MCP는 따로 끄는 설정을 찾지 못했다. | 「조직 관리자가 범주·항목 단위로 켜고 끄는 스위치」가 업계 공통 형태다. |
| 내부: D-51·D-53(하네스 커넥터 인벤토리), D-239(간편 모드), D-297(섀도우 실측) | 인벤토리 보고는 집행 증거가 아니다. 미승인은 거부 대상이다. 간편 모드는 편의를 우선한다. | 기본 기능·기본 커넥터만 기본 승인으로 바꾸고, 플러그인·직접 추가는 기존 검토(미승인 → 14일 뒤 만료)를 유지한다. |

## 3. 선택지

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 | 기본 기능·커넥터 전부 고정 차단(관리형 설정에 하드코딩) | 관리형 하네스 안의 게이트웨이 밖 경로가 줄어든다(다른 프로그램·계정의 직접 통신은 남는다) | 소유자 지시와 반대다. 직원이 쓰던 기본 기능이 사라지고, 관리자가 켤 방법이 없다 |
| **B. 채택** | 기본 기능·기본 커넥터는 「기본 승인」이고 관리자가 항목별로 차단한다. 플러그인·직접 추가는 검토 유지 | 벤더 관리자 콘솔(Claude·ChatGPT)과 같은 스위치 형태다. 편의(D-239)와 맞는다. 하네스가 공식 지원하는 관리형 키로 막으므로 직원이 덮어쓸 수 없다 | 기본 승인 항목은 게이트웨이 판정·원장이 없다(관찰만). 벤더 계정 설정·EDR 같은 다른 통제에 기대는 부분이 남는다 |
| C. 기본 허용 + 검토 기한 | 처음 보이면 미승인 → 기한 뒤 차단(기존 커넥터 흐름) | 관리자 검토를 강제한다 | 「기본 승인」 요구와 다르다. 기한 만료로 기능이 갑자기 꺼진다 |

## 4. 구현(B)

- 목록(카탈로그, 보고가 없어도 보임)
  - 기본 기능: Claude 웹 가져오기·웹 검색, Codex 웹 검색·브라우저 조작·컴퓨터 조작·이미지 생성·메모리.
  - 기본 커넥터 스위치: claude.ai 커넥터 전체, ChatGPT 앱 전체.
  - 보고된 개별 claude.ai 커넥터(호스트 단위)·ChatGPT 앱도 기본 승인이고 개별로 막을 수 있다.
- 상태: 결정이 없으면 `default`(기본 승인, 차단 아님), 관리자 결정은 `denied`(사유 필수)다. 「되돌리기」는 기본 승인으로 돌아간다. 카탈로그 항목에 「승인」 결정은 없다.
- 반영: 게이트웨이가 장치별 관리형 정책을 렌더링할 때 차단 목록을 읽는다. 키트는 매 주기(≤60초) 정책을 받아 적용한 뒤 heartbeat를 보낸다.
- 격리 오판 방지: 관리자가 통제를 바꾼 직후 이전 정책으로 만든 heartbeat가 도착하면 「뒤처짐」으로 본다(HEARTBEAT_SECONDS=180초 안). PJ1에서 실제로 격리가 일어나 고쳤다.
- 인벤토리: 정책이 바뀌면 6시간을 기다리지 않고 바로 다시 보고한다(새로 열린 커넥터가 콘솔에 바로 보이게).
- 콘솔: 「MCP·커넥터」 화면의 「벤더 커넥터」 탭을 「기본 기능·커넥터」로 바꾸고 표 세 개로 나눴다. ① 기본 기능 ② 기본 커넥터(전체 스위치 + 보고된 개별) ③ 플러그인·직접 추가(기존 검토).

## 5. 실측(PJ1, :8000 시험 스택)

- 기본값: claude.ai 커넥터(Google Docs·Slides·Sheets)가 게이트웨이 MCP 2개와 함께 `✔ Connected`로 보였다. `permissions.deny=[]`, Codex는 `plugins=false`만 남았다.
- 차단(claude.ai 커넥터 전체·Claude 웹 가져오기·Codex 웹 검색): 1분 안에 `disableClaudeAiConnectors: true`, `deny: ["WebFetch"]`, Codex `allowed_web_search_modes=["disabled"]`로 바뀌었다. 되돌리면 원상으로 돌아왔다.
- 카탈로그 항목에 「승인」을 보내면 422로 거절된다.

## 6. 한계·미확인

- 기본 승인 항목은 벤더로 직접 가서 게이트웨이 호출별 판정·원장이 없다. 콘솔의 통제 상태는 「벤더 통제/관찰」로 남는다.
- 이름만 쓴 `WebFetch` deny는 claude.ai 아티팩트 읽기에는 적용되지 않는다(공식 문서).
- Codex `features.image_generation`·`memories`와 `[apps.<id>] enabled=false`는 이번에 읽은 공식 관리형 설정 페이지에서 확인하지 못했다. 기존 키트 코드의 키를 그대로 썼다.
- Windows Codex는 `managed_config.toml`을 읽지 않아 앱별 끄기를 `config.toml` 블록에 쓴다. 실기기 확인 전이다.
- 실습 워크스테이션 이미지(`workstation/managed/render.py`)와 옛 PC 키트(`field/pc/mcpgw_pc.py`)는 여전히 고정 차단이다(이번 범위는 엔드포인트 키트).

## 7. 검토 반영 (Codex sol·astra, 같은 날)

sol(gpt-6.1-sol, 배치·정확성·시험)과 astra(gpt-6-astra, 판단)에 이 문서와 레퍼런스, 변경 코드를 주고 읽기 전용으로 검토받았다.

| 지적 | 반영 |
|---|---|
| [높음] 같은 호스트로 플러그인이 보고되면 관리자의 호스트 차단이 렌더링에서 빠진다(직원 보고가 관리자 결정을 무력화) | 차단 키 자체로 렌더링한다(`controls_from`). 종류 혼합과 무관하다. 콘솔·통제 지도 계산도 같은 그룹 기준을 쓴다 |
| [높음] 유예가 「직전 정상 정책」으로 한정되지 않는다. 거절·무변경 요청도 시각을 갱신하고, 격리하지 않으면서 격리 이벤트를 남긴다 | 마지막 정상 heartbeat와 같은 해시·파일, 모든 점검 통과일 때만 유예한다. 실제 변경만 같은 트랜잭션으로 시각을 갱신하고, 유예 중에는 이벤트를 남기지 않는다. 변조·점검 실패는 즉시 격리하는 시험을 추가했다 |
| [높음] Codex 앱별 차단이 사용자가 덮어쓸 수 있는 설정(`managed_config.toml`·Windows `config.toml`)에 있다. Windows는 해제 잔류 위험이 있다 | `requirements.toml`의 `[apps.<id>] enabled=false`로 옮겼다(Codex 소스: 어느 계층이든 false가 이김) |
| CI 시험 `managed_policy_gap_check`가 새 의존성으로 깨진다 | 대역을 추가했다. 로컬 전체 묶음은 기준(67e8950c)보다 새 실패 0, 고친 것 5 |
| 화면: 전체 스위치와 개별 행의 모순, 「사용 엔드포인트」는 보고 수, 「허용/되돌리기」 문구 불일치, 0이 「—」, 중복 부제 | 「전체 차단」 표시, 「보고 엔드포인트」, 「차단 해제」 통일, 0 그대로 표시, 부제 삭제, 경로 「게이트웨이 외부」 열 |
| (astra) Claude in Chrome도 기본 기능인데 관리형 독점 통제가 말없이 막는다 | 「브라우저 연동」으로 목록에 넣고 기본 승인(`allowClaudeInChromeWithManagedMcp`), 차단 시 `claude-in-chrome` 거부 |
| (astra) 「기본 승인」보다 「기본 허용」이 정확하다 | 소유자 용어를 유지하고 한계에 기록 |
| (sol) 상위 메뉴 「MCP 서버」를 「MCP·커넥터」로 | 메뉴 전체 이름 변경은 범위가 넓어 보류했다. 후속 검토 |
| (sol·astra) 실제 도구 실행 수준의 차단 효과(이미지 생성·메모리·브라우저 조작), 기존 세션, 이름·포트 변경 | 실기기 미확인으로 남김 |
