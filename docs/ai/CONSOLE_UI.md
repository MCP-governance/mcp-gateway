# Console UI — 구조와 확장

> 파일: `full_stack_lab/gateway/app/agent_static/`
> `console.html`(껍데기) · `console.js`(ES 모듈, 빌드 없음) · `console-state.mjs`(활동 로그 상태, DOM 없음 — `node --test`) · `console.css`(토큰·컴포넌트) ·
> `login.html/js/css` · `fonts/NotoSansKR-variable.woff2`(폐쇄망에서도 같은 글꼴).
> 서빙: `agent-service`(`/login`, `/workspace`, `/static/*`). 정적 파일은 **이미지에 들어간다** —
> 바꾸면 `docker compose build -q agent-service && docker compose up -d agent-service`.

## 1. 원칙
- **Console은 MCP를 호출하지 않는다**(D-01). 도구 실행 버튼은 없다. 여기서 하는 조작은 거버넌스
  절차뿐: 승인/거부, 계약 승인본 갱신, 계정 상태, 도입 신청 심사, 집행 모드, 종료 판정.
- **보이는 것은 서버가 정한다.** 메뉴 숨김은 편의다. `/auth/me`의 `pages`가 역할별 화면 목록이고
  (`agent_service.PAGES_BY_ROLE`), 데이터는 서버가 역할로 거른다(`/gw` 프록시 allowlist, Gateway의 `admin_caller`).
- **CSP same-origin**(`script-src 'self'; style-src 'self'`). 인라인 스크립트·`style=` 속성·인라인
  이벤트 핸들러 금지. `style=""`도 쓰지 말 것.
- **모든 데이터는 이스케이프**: `html```태그 템플릿이 보간값을 전부 이스케이프하고, `html```/`raw()`만
  그대로 넣는다. 감사 행의 인자는 프롬프트 주입된 에이전트가 쓴 문자열일 수 있다.

## 2. 뼈대 (`console.js`)

| 부분 | 설명 |
| --- | --- |
| `api(path, {method, body})` | Bearer 토큰(`localStorage["mcp-console-token"]`)을 붙인다. 401이면 토큰을 지우고 `/login`. 오류는 `detail`(문자열/FastAPI 422 목록)을 문장으로 |
| `gw(path)` | `/gw/<path>` → Gateway `/api/<path>` 프록시 |
| `ROUTES.<page>(arg)` | 해시 라우트 `#/<page>/<arg>`. `html` 또는 `{html, after}`를 돌려준다. `after`는 렌더 뒤 실행(라이브 폴링, 드로어 열기) |
| `route()` | 권한 없는 페이지면 첫 허용 페이지로. `routeSeq`로 늦게 도착한 응답이 새 화면을 덮지 않게 한다 |
| `ACTIONS[name](el)` | `data-act="name"` 요소 클릭 위임. 버튼은 처리 중 비활성. 행 안의 버튼·링크는 자기 동작만 |
| `FORMS[name](form)` | `data-form="name"` 폼 제출 위임 |
| `ask({title, body, fields, confirm, danger})` | `<dialog>` 모달, 확인 시 `FormData` 반환 |
| `openDrawer(title, body)` | 오른쪽 상세 패널(판정·서버·회수 대상·판정서·고지 요청서) |
| `toast(msg, bad)` | 결과 알림 |

키보드: 클릭 가능한 행(`li/tr[data-act]`)은 `tabindex=0`, Enter로 연다(IME 조합 중 Enter는 무시). Esc는 드로어 닫기.
접근성(D-28): 첫 Tab에 "본문으로 건너뛰기"(해시 라우팅과 충돌하지 않게 `data-act="skip"`으로 초점만 옮김),
다른 화면으로 가면 그 화면의 `h1`로 초점·`document.title` 갱신(같은 화면 재렌더는 초점 유지), 드로어는 열 때
닫기 버튼으로 초점 → 닫으면 연 요소로 복귀, 닫힌 드로어는 `inert`. 터치 기기에서 조작 요소 44px,
`prefers-reduced-motion`·`forced-colors` 대응.
테마: `localStorage["mcp-console-theme"]` 또는 시스템 설정(`prefers-color-scheme`).

## 3. 화면과 데이터

| 화면 | 역할 | 데이터 | 조작 |
| --- | --- | --- | --- |
| `#/overview` 개요 | 관리자 | `/gw/overview`, `/gw/activity?limit=8` | — (프로브 호출은 숫자에서 제외, D-12) |
| `#/activity` 활동 로그 | 전원(비관리자는 자기 것만) | `/gw/activity?decision&server&person&after&limit` | 서버 필터(판정·서버·사람) + 불러온 기록 검색(사람·단말·도구·대상·정책·trace), 3초 폴링(일시정지 중에도 새 판정 수를 셈), 상태 줄(마지막 성공·실패), 판정 상세 드로어, 감사 체인 검증 |
| `#/approvals` 승인 대기 | 관리자 | `/approvals` | 승인하고 실행 / 거부(사유) |
| `#/servers[/id]` MCP 서버 | 관리자 | `/gw/registry` | 계약 다시 확인, DRIFT면 승인본 갱신(검토 내용 필수) |
| `#/people` 직원·단말 | 관리자 | `/api/accounts`, `/gw/endpoint/inventory` | 계정 상태(본인 제외) |
| `#/intake` 도입 신청 | 전원 | `/api/mcp-requests` | 신청(저장소·목적만), 관리자: 검증 시작·**종료 조건 검증**(원격만, HTTPS 근거)·승인(원격은 검증 뒤에만 보임)·거부 |
| `#/termination` 종료·폐기 | 관리자 | `/gw/termination/relationships`, `/gw/termination/cases` | 종료 시작(차단) |
| `#/termination/<caseId>` 케이스 | 관리자 | `/gw/termination/cases/<id>` | 증거 수집·판정·조직 권한 폐기·상태 기록·대상 추가·증거 등록·판정서·고지 요청서·종결(위험 수용)·재개·실습 복원 |
| `#/policy` 정책 | 관리자 | `/gw/enforcement`, `/gw/policy/matrix`, `/gw/policy/ledger` | 집행/관찰 모드 전환. 27칸(지금 번들로 OPA 질의)·권한 번들 grant 목록·관리대장·예외 |

활동 로그 한 줄은 `activity.describe()`의 필드로 만든다: 시각 · 판정 칩 · 누가(부서·단말) ·
`server.tool → 대상` · 행위·등급 · 정책 id — 사유 · 실행 결과. 개인정보가 검출되면 "개인정보 KR_RRN · 마스킹" 칩,
열람→반출 연쇄면 "열람→외부 전송 연쇄" 칩이 붙고, 상세 드로어에 위험 점수(조사용)·개인정보 유형·연쇄 표지가 나온다. 종료 절차의 프로브 호출은
"종료 절차의 차단 확인 · 관리자 실행" 칩으로 구분한다.

케이스 화면의 7단계 표시는 `procedureState()`가 케이스 상태에서 계산한다(→ [TERMINATION_MODEL.md](TERMINATION_MODEL.md) 3절).
증거 카드는 종류가 **증명하는 것/못 하는 것**(서버의 `meaning`)과 **이번 관찰 결과**(`evidenceResult()`:
자격 없음/아직 있음, 실행 전 차단 등)를 같이 보여 준다.

## 4. 스타일 (`console.css`)
- 색은 의미에만: 판정(허용 초록·경보 주황·제한 청록·승인 보라·차단 빨강)과 등급(T1 초록·T2 주황·T3 빨강).
- 토큰은 `:root`(라이트)와 `:root[data-theme="dark"]`에. 컴포넌트: `.card`, `.kpi`, `.chip.<tone>`,
  `table.data`, `.feed`, `.servers`, `.stepper`/`.step.done|now|gap`, `.crit`, `.cdots`, `.evidence`, `.drawer`, `dialog`.
- 반응형: ≤1100px 한 열, ≤760px 사이드바가 상단 가로 메뉴(테마·로그아웃은 계속 보임).

## 5. 새 화면을 추가하려면
1. `PAGES`에 `{id, label, group}` 추가, `agent_service.PAGES_BY_ROLE`에 역할별로 추가.
2. `ROUTES.<id> = async (arg) => html\`…\``.
3. Gateway API가 필요하면 `GATEWAY_PROXY_PREFIXES`에 접두사를 넣고, 비관리자가 봐도 되는 것만
   `EMPLOYEE_PROXY_PREFIXES`에. Gateway 쪽 라우트에 `Depends(caller|admin_caller)`를 반드시 붙인다
   (`tests/open_endpoints.py`가 무인증 라우트를 잡는다).
4. 조작은 `ACTIONS`/`FORMS`에, 되돌릴 수 없는 조작은 `ask({danger: true})`로 확인.
5. `node --check console.js`, 브라우저에서 콘솔 오류 확인(인라인 스타일을 쓰면 CSP 위반이 콘솔에 뜬다).
