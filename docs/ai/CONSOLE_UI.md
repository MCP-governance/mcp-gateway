# Console UI v3 — 구조, 디자인 시스템, 확장

> 파일: `full_stack_lab/gateway/app/agent_static/`
> `console.html`(껍데기) · `console.js`(ES 모듈, 빌드 없음) · `charts.mjs`(ECharts 래퍼) ·
> `console-state.mjs`(DOM 없는 상태·데이터 변환 — `node --test`) · `console.css`(토큰·컴포넌트) ·
> `vendor/echarts.min.js`(Apache ECharts 6.1.0, Apache-2.0, `vendor/ECHARTS-LICENSE.txt`) ·
> `login.html/js/css` · `fonts/NotoSansKR-variable.woff2`(폐쇄망에서도 같은 글꼴).
> 서빙: `agent-service`(`/login`, `/workspace`, `/static/*`). 정적 파일은 **이미지에 들어간다** —
> 바꾸면 `docker compose build -q agent-service && docker compose up -d agent-service`.
> 결정: D-01(웹은 MCP를 호출하지 않음), D-28(상태 모듈), **D-33(v3 화면 구조)**.

## 1. 원칙
- **Console은 MCP를 호출하지 않는다**(D-01). 조작은 거버넌스 절차뿐: 승인/거부, 계약 승인본 갱신, 계정 상태,
  장치 자격, 도입 신청 심사, 집행 모드, 종료 판정.
- **보이는 것은 서버가 정한다.** 메뉴 숨김은 편의다. `/auth/me`의 `pages`가 역할별 화면 목록이고
  (`agent_service.PAGES_BY_ROLE`), 데이터는 서버가 역할로 거른다(`/gw` 프록시 allowlist, Gateway의 `admin_caller`).
- **CSP same-origin**(`script-src 'self'; style-src 'self'`). 인라인 스크립트·`style=` 속성·인라인 이벤트 핸들러 금지.
  ECharts도 같은 출처에서 받는다(CDN 없음).
- **모든 데이터는 이스케이프**: `html```태그 템플릿이 보간값을 전부 이스케이프하고, `html```/`raw()`만 그대로 넣는다.
  차트 툴팁은 `renderMode: "richText"`(캔버스)라 감사 로그 문자열이 innerHTML로 가지 않는다(하네스 이름은 하네스가 스스로 댄다).
- **설명은 UI에 두지 않는다.** 화면에는 라벨·숫자·차트·짧은 상태만 둔다. 사용법과 의의는 팀 가이드라인 문서가 맡는다(D-33).
  확인 대화상자도 제목·입력·버튼 중심이고, 되돌릴 수 없는 결과만 한 줄로 적는다(예: 종료 시작 "즉시 모든 호출 차단").

## 2. 화면 구조

모든 화면이 같은 뼈대를 쓴다(`page({head, kpis, tabs, active})`):

```text
┌ 사이드바(그룹·아이콘·건수) ┬ 머리: 제목 · 상태 칩 · 동작 버튼 ───────────────────────────┐
│ 운영: 개요·활동 로그·승인  │ KPI 스트립(한 패널 안의 칸 — 카드 여섯 장이 아님)                 │
│ 자산: 서버·직원·단말·도입  │ ── 탭 · 탭 · 탭 ───────────────────────────────────────────── │
│ 전주기: 종료·폐기·정책     │ [차트 패널(주 질문에 답하는 것 하나를 크게)]                       │
│                            │ [보조 차트 | 보조 차트]                                            │
│                            │ [표 → 행을 누르면 오른쪽 드로어(드로어 안에도 탭)]                │
└────────────────────────────┴────────────────────────────────────────────────────────────────────┘
```

- 탭은 WAI-ARIA 탭 패턴(`role=tablist/tab/tabpanel`, 탭 정지 하나, ←/→/Home/End). 열린 탭은 주소에 남는다(`#/policy?t=ledger`).
- 숨은 탭의 차트는 처음 보일 때 그린다(`charts.register` → `charts.mountVisible`). 크기가 0인 패널에 그리지 않기 위해서다.
- 드로어: `openDrawer(title, head, tabs)` — 판정(요약·분류·정책·추적), 승인 요청(요청·인자·정책), 서버(개요·도구·종료 조건),
  회수 대상(대상·기준·증거), 정책(규칙·관리대장), 판정서(판정·기준·대상).

## 3. 화면과 데이터

| 화면 | 탭 | 차트 | 데이터 |
| --- | --- | --- | --- |
| `#/overview` 개요 | 트래픽 · 하네스·서버 · 위험 | 시간대별 판정(24시간 누적 막대) · 판정 비율(도넛) · 서버별 호출(판정 누적 가로 막대, 누르면 활동 로그 필터) · **하네스 → MCP 서버 → 판정 Sankey** · 많이 걸린 정책 · 종료·폐기 현황 | `/gw/overview`(`series`, `flows`, `workstations[].harness/calls`), `/gw/activity?decision=Block` |
| `#/activity` 활동 로그 | 호출 · 분석 | 불러온 호출의 시간 분포(자동 버킷 1~180분) · 서버별 · 하네스별 · 사람별 | `/gw/activity` 3초 폴링(일시정지 중에도 새 판정 수를 셈), 필터는 주소 쿼리(`?server=git&decision=Block`)로도 |
| `#/approvals` 승인 대기 | 대기 · 처리 이력 | 결과 비율 · 서버별 요청 | `/approvals` → `{approvals, history}` |
| `#/servers[/id]` MCP 서버 | 서버 · 도구 · 계약 | 서버별 호출 · 서버별 도구(읽기/쓰기/실행) · 도구 계약 일치 | `/gw/registry`, `/gw/overview` |
| `#/people` 직원·단말 | 단말 · MCP 설정 · 계정 | 단말별 호출 · 하네스 비율 · 설정 분류 · 설정 파일별 항목 | `/api/accounts`, `/gw/endpoint/inventory`, `/gw/overview` |
| `#/intake` 도입 신청 | 신청 · 새 신청 | 상태별 건수 | `/api/mcp-requests` |
| `#/termination` 종료·폐기 | 이용 관계 · 케이스 | 최선 도달 등급 · 케이스 등급 | `/gw/termination/relationships`, `/gw/termination/cases` |
| `#/termination/<caseId>` 케이스 | 판정 · 회수 대상 · 증거 · 허용 자원 | 기준별 충족 대상 | `/gw/termination/cases/<id>` |
| `#/policy` 정책 | 판정 행렬 · 권한 번들 · 관리대장 · 예외 | 역할 × (등급·행위) 판정 히트맵 · 결과별 정책 수 | `/gw/enforcement`, `/gw/policy/matrix`, `/gw/policy/ledger` |

활동 로그 한 행: 시각 · 판정 칩 · 사람(단말) · **하네스**(clientInfo를 사람이 읽는 이름으로: Claude Code, Codex CLI, Gemini CLI,
OpenCode, MCP Inspector) · `server.tool` · 대상 · 정책 id. 종료 절차의 프로브 호출은 "종료 점검" 칩.
케이스 화면의 7단계는 `procedureState()`가 케이스 상태에서 계산한다(→ [TERMINATION_MODEL.md](TERMINATION_MODEL.md) 3절).

## 4. 디자인 시스템 (`console.css`)

- **방향**: AI 도구 호출의 관제실. 브랜드는 팀 보고서의 네이비(`--brand #1f4287`), **채도는 판정 5색에만** — 차트의 빨간 막대는
  차단 외의 뜻이 없다. 평면 패널·단일 테두리, 그림자는 떠 있는 것(드로어·대화상자·토스트)에만.
- **판정 색**: 허용 `--allow`, 경보 `--alert`, 제한 `--restrict`, 승인 대기 `--approval`, 차단 `--block`(라이트·다크 각각).
  칩은 점과 단어를 함께 써서 색만으로 의미를 싣지 않는다. 차트 색은 마운트 시점에 같은 CSS 토큰을 읽는다(`charts.color`).
- **글꼴**: Noto Sans KR 하나(한글 필수), 식별자(도구·정책 id·trace)만 monospace. 크기 단계 13·14·**16(본문)**·18·22·28·36(KPI),
  v2보다 두 단계 크다. 숫자는 `tabular-nums`.
- **밀도**: 표 행 44px 안팎(15px), 패널 여백 20px, 그리드 간격 20px. 1200px 이하에서 2열, 800px 이하에서 1열·가로 메뉴.
- **접근성**: 본문 건너뛰기, 화면 이동 시 `h1`로 초점, 드로어 열고 닫을 때 초점 이동·`inert`, 차트 컨테이너 `role="img"` +
  `aria-label`, `prefers-reduced-motion`(차트 애니메이션 끔), `forced-colors`, 터치 기기 44px.
- **테마**: `localStorage["mcp-console-theme"]` 또는 시스템 설정. 테마를 바꾸면 차트를 새 토큰으로 다시 그린다(`charts.redrawAll`).

### 레퍼런스와 디자인 스킬 (조사: 2026-09-25)

| 출처 | 가져온 것 |
| --- | --- |
| Datadog Cloud SIEM — Signals Explorer | 목록 위 히스토그램 + 조밀한 표 + 측면 패널 안의 탭(활동 로그·드로어) |
| Elastic Security — Overview·Alerts | KPI → 시계열 → 분포/Top-N 3단 그리드(개요), 행 → flyout |
| Tines — Cases | 케이스 전용 화면, 단계 파이프라인 + 탭(종료 케이스) |
| Portkey · Langfuse (LLM 게이트웨이·관측) | 트래픽·분포 차트 중심 대시보드, 표와 차트가 같은 필터를 공유 |
| anthropics/skills `frontend-design` | 한 곳에만 대담하게(개요의 트래픽 차트), 카드마다 같은 그림자·장식 그라디언트·대문자 라벨 금지 |
| vercel-labs/agent-skills `web-design-guidelines` | `tabular-nums`, `color-scheme`, 말줄임 `…`, 긴 값 말줄임, reduced-motion |
| nextlevelbuilder/ui-ux-pro-max-skill | `--design-system "security operations dashboard SIEM monitoring" --density 8 --motion 2`: Swiss 미니멀, 도넛은 5범주 이하, 범례는 차트 옆, 색+텍스트 |

## 5. 뼈대 (`console.js`)

| 부분 | 설명 |
| --- | --- |
| `api(path, {method, body})` / `gw(path)` | Bearer 토큰(`localStorage["mcp-console-token"]`), 401이면 `/login`. `gw`는 `/gw/<path>` 프록시 |
| `ROUTES.<page>(arg, tab, query)` | `{html, charts, after}`를 돌려준다. `charts`는 `{요소 id: () => ECharts 옵션}` |
| `page()`·`head()`·`kpiStrip()`·`panel()`·`chartBox()`·`tabBar()`·`tabPanel()` | 화면 조립 조각 |
| `ACTIONS[name](el)` / `FORMS[name](form)` | `data-act`·`data-form` 위임. 되돌릴 수 없는 조작은 `ask({danger: true})` |
| `charts.mjs` | `decisionColumns`·`stacked`·`donut`·`bars`·`columns`·`sankey`·`decisionGrid`, `register/mountVisible/redraw/redrawAll/disposeAll` |
| `console-state.mjs` | `mergeRows`·`searchRows`·`liveLabel`·`hourBuckets`·`splitBy`·`sankeyData`·`harnessLabel` (`tests/console-state.test.mjs` 7건) |

## 6. 새 화면을 추가하려면
1. `PAGES`에 `{id, label, group}`과 `ICON[id]`(Lucide, ISC) 추가, `agent_service.PAGES_BY_ROLE`에 역할별로 추가.
2. `ROUTES.<id> = async (arg, tab, query) => ({ html: page({...}), charts: {...} })`. 주 질문에 답하는 차트 하나를 첫 탭 맨 위에.
3. 데이터 변환(버킷·집계)은 DOM 없는 함수로 `console-state.mjs`에 두고 `node --test`로 확인한다.
4. Gateway API가 필요하면 `GATEWAY_PROXY_PREFIXES`에 접두사를 넣고, 비관리자가 봐도 되는 것만 `EMPLOYEE_PROXY_PREFIXES`에.
   Gateway 쪽 라우트에 `Depends(caller|admin_caller)`를 반드시 붙인다(`tests/open_endpoints.py`).
5. `node --check console.js charts.mjs`, 브라우저 콘솔에서 CSP 위반이 없는지 확인한다.
