# Console v4 — 조직 운영 화면

2026-10-01. D-64. 소스: `full_stack_lab/gateway/app/agent_static/`.

## 화면 구성

| 화면 | 첫 화면과 주요 업무 |
| --- | --- |
| 운영 현황 | 실제 호출 KPI 6개, 24시간 호출 차트, 확인할 승인·우회·종료 항목, 최근 차단 목록 |
| 호출 로그 | 검색과 판정·서버·이벤트·실행·사용자 필터, 실시간/일시정지, 호출 표. 차트는 분석 탭 |
| 승인 대기 | 검토할 요청과 승인·거부. 이력 목록이 먼저, 집계는 펼침 영역 |
| MCP 서버 | 검색 가능한 등록 서버 표, 연결·계약 상태, 증거, 승인 기한, 도구 수. 도구·계약 탭 유지 |
| 통제 범위 | 항목 검색, 상태·종류 선택, 증거를 붙인 목록. 단말·계정, 섀도·잔존, 벤더·커넥터 탭 |
| 직원·단말 | 조직 계정 검색, 초대·가입 승인, 단말 자격·관리형 설치 및 연결 이력 |
| 도입 신청 | 신청 목록과 상태별 검토 작업, 별도 새 신청 폼. 서비스·목적과 연결 정보를 구분 |
| 종료·폐기 | 이용 관계별 회수 대상·차단 요인, 케이스 목록, 단계·회수 대상·상태 증거·판정 |
| 정책 | PAC15 승인 실행 범위, 실제 배포 확인, 관리대장, 예외. 서버와 도구를 올바른 열에 표시 |

메뉴는 **모니터링 / 접근·통제 / 수명주기**로 묶는다. 데스크톱 기본은 펼친 메뉴이고, 좁은 화면은 접힌 메뉴로 시작한다.
페이지 제목·설명·주요 작업, 탭, 목록을 같은 순서로 사용한다. 긴 목록의 차트는 분석 탭이나 native `details`로 이동했다.

## 공통 구성

- `console.css`: 밝음·어두움 색상 토큰, 14px 본문, 제목·표·폼·버튼·배지. 배지의 문구와 모양으로 상태를 구분한다.
- `head/panel/page`: 페이지 제목과 설명, 명령 영역, 목록 도구 영역을 분리한다. 목록 필터는 현재 선택 값과 함께 보인다.
- 식별자는 목록에서 말줄임과 전체 값의 `title`을 제공한다. 호출 상세에는 전체 단말 ID·해시·trace가 표시된다.
- 표는 각 패널 안에서 가로 스크롤한다. 좁은 화면에서 감사·통제 열을 숨기지 않는다.
- 호출 상세는 최대 900px native `dialog`. **출처 → Gateway 판정 → 단말 연결 → 도구 실행 → 응답 처리**를 넓은 세로 행으로 표시한다.
- 하네스 이름의 자기 신고, 호출 당시 서명 단말 결합, 현재 단말 상태를 구분한다. 응답 보류가 이미 실행된 효과를 취소한다고 표시하지 않는다.
- native modal이 배경 접근과 초점 순환을 담당한다. Enter·Space로 표의 상세를 열 때 기본 키 동작을 취소해 새로 초점이 간 닫기 버튼이 연이어 실행되지 않게 한다. Escape 이후 원래 행으로 복귀한다.
- 상세를 다시 열면 공통 `openDrawer`에서 본문 스크롤을 0으로 초기화한다. 이전 상세의 스크롤 위치로 새 호출의 요약이 가려지지 않는다.
- 확인 폼도 기존 native `dialog`를 사용한다. 상세 패널 위에서 폼을 열 때 Escape는 폼을 먼저 닫는다.
- 로그인·가입·조직 초대 화면도 같은 글꼴·색상·폼 체계를 사용한다. 기존 인증·초대·1회용 키트 흐름을 유지한다.
- 차트는 기존 ECharts를 사용한다. 숨긴 탭·닫힌 펼침 영역에서는 초기화하지 않고, 범례는 좁은 폭에서 스크롤한다.

## 참고한 공개 UI

제품 전체를 복제하거나 제품의 보안 역량이 같다고 주장하지 않는다. 고정 커밋에서 실제 UI 소스의 화면 구성만 참고했다.

| 출처 | 확인한 소스 | 반영 |
| --- | --- | --- |
| [Microsoft MCP Gateway](https://github.com/microsoft/mcp-gateway/tree/3594c4eee36308ac131aad1c946ea14140b4353d/portal) | `Layout.tsx`, `PageHeader.tsx`, `AdaptersPage.tsx`, `styles.css` | 펼친 메뉴, 활성 항목 표시, 제목·설명·명령 영역, 검색 가능한 서버 표 |
| [IBM ContextForge](https://github.com/IBM/mcp-context-forge/tree/0d269c38dc8b1d149c4aee78002431b0eaf63290/mcpgateway) | `templates/admin.html`, `static/admin.css` | 관리 항목 그룹, 일관된 목록과 상태 표시, 어두운 테마 |
| [LiteLLM](https://github.com/BerriAI/litellm/tree/72049427569f314a23d743dca05d735b611e60b5/ui/litellm-dashboard) | `RequestLogsPanel.tsx`, `LogsTableToolbar.tsx`, `LogDetailsDrawer`, `MCPSubmissionsTab.tsx` | 로그 필터·실시간 상태·목록·상세 분리, 신청·처리 이력 |
| [LiteLLM 공식 UI 안내](https://docs.litellm.ai/docs/proxy/ui) | 공식 관리 화면 예시 | 문맥을 유지하는 표와 페이지 내 작업 배치 |

추가 분석 범위와 사용자 등록 비교는 [BENCHMARK_UI_ONBOARDING_2026-10-01.md](BENCHMARK_UI_ONBOARDING_2026-10-01.md)를 따른다.
세 제품을 직접 기동한 비교 시험은 수행하지 않았다.

## 검증

실제 Gateway/Console과 기존 MCP 서버가 동작하는 로컬 스택에서 9개 페이지의 29개 탭을 열고 분석 펼침을 확인했다.
데스크톱 DOM 검사에서 페이지 전체 가로 넘침 0, 이름 없는 보이는 버튼 0, 브라우저 error/warn 0을 확인했다.
서버 검색은 공백·대소문자·빈 결과를 확인했고, 호출 상세는 Enter 열기·닫기 버튼 초점·Escape 원래 행 복귀를 확인했다.

색상 토큰의 텍스트 18쌍은 WCAG 대비 4.5 이상(최저 5.69), 입력·버튼 경계 2쌍은 3 이상이다.
390px 화면은 viewport 적용 후 렌더링과 DOM 크기가 일치한 상태에서 메뉴 열기·이동 후 닫기, 호출 필터 재배치, 상세 Enter 열기·닫기 버튼 초점·Escape 복귀를 확인했다. 호출 목록과 상세의 페이지 전체 가로 넘침은 0이다.
스크린 리더 사용 시험이나 WCAG 전체 인증을 주장하지 않는다.

필수 회귀: `./full_stack_lab/console.sh test` 종료 0, Rego 103/103, 공격 42/42 탐지·정상 16/16 통과, E1·E2·E3 통과.
상세 키보드·빈 목록 처리·상세 스크롤 초기화까지 반영한 최종 소스로 전체 필수 시험을 재실행해 종료 0을 확인했다. JavaScript 구문 검사·기존 상태 시험 8/8·실제 브라우저 키보드 검수도 통과했다.
실제 공급자 MCP의 실행 증거와 이번 UI 렌더링 검수는 별개이며, UI 검수를 위해 공급자 서버나 실행 로그를 만들지 않는다.

기존 직원 데이터 제한, 승인·검증·활성화 분리, PAC 인가, OPA fail-closed, 감사 원장과 OS 집행 경계는 바꾸지 않는다.
Console는 MCP를 직접 호출하지 않는다. 공격자 입력은 `html` tagged template으로 escape하고 CSP의 same-origin 자산만 사용한다.

### 상세 키보드 회귀 확인

이미 로그인한 `tab`을 사용하는 `cua_repl`에서 실행한다. 최신 호출 목록이 있는 화면에서 실시간 갱신을 먼저 일시정지한다.

```javascript
await tab.playwright.locator('#feed tr[data-act="decision"]').first().press('Enter');
await tab.playwright.getByRole('dialog', {name: /호출 #/}).waitFor({state: 'visible'});
if (!(await tab.playwright.getByRole('dialog', {name: /호출 #/}).isVisible())) throw Error('Enter must leave the drawer open');
const state = await tab.getAXState({emit: false});
if (!/focused UI element.*button 닫기/.test(state)) throw Error('close button must receive focus');
if ((await tab.playwright.evaluate(() => document.querySelector('#drawer-body').scrollTop)) !== 0) throw Error('new detail must start at the top');
await tab.pressKey(null, 'Escape');
if (await tab.playwright.getByRole('dialog', {name: /호출 #/}).isVisible()) throw Error('Escape must close the drawer');

// 세로 스크롤이 생기는 상세를 1280px 데스크톱에서 열고 재진입한다.
await tab.playwright.locator('#feed tr[data-act="decision"]').first().press('Enter');
await tab.playwright.getByRole('dialog', {name: /호출 #/}).waitFor({state: 'visible'});
await tab.getAXState({emit: false});
await tab.scroll([720, 560], 'down', 1);
await tab.getAXState({emit: false});
if ((await tab.playwright.evaluate(() => document.querySelector('#drawer-body').scrollTop)) <= 0) throw Error('use a scrollable call detail');
await tab.pressKey(null, 'Escape');
await tab.getAXState({emit: false});
await tab.playwright.locator('#feed tr[data-act="decision"]').first().press('Enter');
await tab.playwright.getByRole('dialog', {name: /호출 #/}).waitFor({state: 'visible'});
if ((await tab.playwright.evaluate(() => document.querySelector('#drawer-body').scrollTop)) !== 0) throw Error('new detail must reset previous scroll');
```

## 수정 지침

기존 `PAGES`·`ROUTES`·안전 HTML 조립·공통 컴포넌트를 사용한다. 새 프런트엔드 프레임워크나 원격 자산은 필요하지 않다.
탭은 패널을 직접 이웃으로 유지한다. 도입 목록 갱신은 차트 노드·열린 탭·미제출 폼·열린 상세/검토를 보존한다.
권한에 따른 메뉴는 서버의 `PAGES_BY_ROLE`을 따른다. 메뉴를 숨기는 것만으로 API 권한을 구현하지 않는다.
