# SR6 기존 시험 세 파일 변경 적대 검토

- 작업자: Codex sol, 2026-10-20.
- 현재 브랜치 / 시작 기준: `10/20-stale-tests-review` / `07bfed8fa73ca311dfb4e707a4ad44ecb73dae2d`, 시작 시 작업 트리 clean.
- 비교 기준: `origin/main=07bfed8fa73ca311dfb4e707a4ad44ecb73dae2d` → `luna/stale=8eaff2f3892d704b7ff34da661096539a9598960`.
- 범위: 지정한 세 시험의 diff 10개 hunk와 관련 제품 경로. 코드·기존 시험·결정·현황·백로그는 수정하지 않고 이 검토서만 추가한다. 새 D-번호·커밋 없음.
- 분류 근거: `git show luna/stale:research/llm-wiki/analysis/stale-tests-1020/README.md`, 특히 마지막 「메인 반영」 절까지 확인했다. 현재 브랜치에는 이 후보 문서가 없어 일반 상대 링크 대신 ref와 경로로 고정한다.
- 재현 명령: `git diff origin/main luna/stale -- full_stack_lab/tests/oauth_rotation_check.py full_stack_lab/tests/protocol_versions_check.py full_stack_lab/tests/system_metrics_check.py`.

## 결론

**A 채택 8개, B 수정 후 채택 2개, C 거부 0개. 현재 후보 전체의 무조건 채택은 보류한다.** B는 OAuth helper import 순서와 프로토콜 기대 예외 확대다. D-123·D-116·D-149에 맞춘 보정 방향은 타당하지만, 이미지에서 세 파일이 통과했다는 보고만으로 CI 직접 실행과 입력에 답하지 않았다는 효과까지 확인되지는 않는다.

아래 행 위치는 모두 **후보 `luna/stale`** 기준이다. 제품 코드 인용은 현재 체크아웃 기준이며, 관련 `upstream.py`, `destination.py`, `idp.py`, `disposal.py`, `agent_contract.py`, `agent_service.py`, `mcp_facade.py`, `termination_lab_support.py`가 두 ref에서 같은지도 별도로 확인했다.

## Hunk별 판정

| ID | 파일 / diff hunk / 후보 위치 | 판정 | 이유와 조건 |
| --- | --- | --- | --- |
| O1 | `oauth_rotation_check.py` / `@@ -14,6 +14,7 @@` / 17행 | **B** | 기존 격리 도구 재사용은 맞지만 helper가 `from app import db`를 즉시 실행한다. 후보의 게이트웨이 경로 설정은 20행이므로 CI 직접 실행에서 `app` import가 먼저 실패한다. helper import를 환경·경로 설정 뒤로 옮긴 후 채택한다. 아래 F1 참조. |
| O2 | 같은 파일 / `@@ -21,12 +22,16 @@` / 24–33행 | **A** | `rows`와 `fetchall()`을 추가하되 기존 `row`/`fetchone()`을 유지한다. 결과는 deepcopy로 돌려줘 시험이 커서 결과를 바꿔도 대역 상태가 바뀌지 않는다. 쿼리 실패를 일반 성공으로 바꾸는 catch-all이 아니다. |
| O3 | 같은 파일 / `@@ -100,6 +105,12 @@` / 108–113행 | **A** | D-123 `_revoke_family()`가 실제 실행하는 SELECT 두 개만 지원한다. 고정 성공값 대신 해당 transaction snapshot의 발급 토큰·만료 시각·refresh digest를 `family_id`로 필터링한다. 기존 DB 철회 상태 assertion과 미지원 SQL의 실패를 유지한다. |
| O4 | 같은 파일 / `@@ -134,6 +145,7 @@` / 148행 | **A** | 임시 Ed25519 키·폐기 디렉터리에서 실제 `disposal.initialize/blocked/remember` 경로를 사용한다. 폐기를 무조건 허용하는 대역이 아니다. ExitStack 종료 시 환경·디렉터리를 원복한다. O1 import 순서는 별도 수정 조건이다. |
| P1 | `protocol_versions_check.py` / `@@ -15,6 +15,7 @@` / 18행 | **A** | P5의 범위 제한 context patch를 위한 표준 라이브러리 import다. 제품 설정이나 새 의존성을 추가하지 않는다. |
| P2 | 같은 파일 / `@@ -22,7 +23,7 @@` / 26행 | **A** | 실제 제품의 `WireRejected` 타입을 참조하기 위한 import 자체는 타당하다. 예외를 성공으로 인정하는 P4의 판정은 별도다. |
| P3 | 같은 파일 / `@@ -37,7 +38,7 @@` / 41행 | **A** | `mcp_facade._approved_tools()`의 네 번째 `protocol_version` 인자와 일치한다. 기존 `echo` 반환·양 세대 협상·목록 힌트·호출 성공 assertion은 유지한다. 이 대역이 판본별 실제 계약 필터까지 시험한다는 뜻은 아니다. |
| P4 | 같은 파일 / `@@ -113,7 +114,9 @@` / 114–122행 | **B** | 현재 `ContractClient.call_tool()`이 `ValidationError`를 `WireRejected`로 바꾸므로 예외 추가의 제품 근거는 있다. 그러나 그 타입과 `PROVIDER_CALLS == ["ask"]`만으로 입력 응답 0을 증명하지 못한다. 응답 후 오류인 반례도 통과한다. 아래 F2의 관측 보강 후 채택한다. |
| P5 | 같은 파일 / `@@ -133,7 +136,14 @@` / 139–146행 | **A** | 허용 조건은 생성한 `http://127.0.0.1:<임시 포트>/`와의 문자열 완전 일치이며 `provider_asks()` 동안만 적용된다. 다른 URL은 false다. 실제 DNS 조회·숫자 IP 연결·host/port 고정과 리디렉션 금지는 그대로다. 이 시험 자체로 운영 목적지 승인 검증을 주장하지 않는다. |
| M1 | `system_metrics_check.py` / `@@ -210,8 +210,9 @@` / 213–220행 | **A** | 필수 합성 `jti`와 폐기 아님 대역으로 D-123의 선행 검사만 통과시킨다. 실 `authenticated_user()`의 Console scope 검사와 HTTP 403, DB 조회 0회, 지표 수집 0회 assertion은 유지한다. 폐기·서명 검증 자체는 이 시험의 목적 밖이다. |

## 수정 후 채택 조건

### F1 — OAuth helper가 경로 설정보다 먼저 제품 모듈을 가져온다

- 위치: 후보 `oauth_rotation_check.py:17`, 기존 [helper](../../../../full_stack_lab/tests/termination_lab_support.py)의 22행, [CI](../../../../.github/workflows/verify.yml)의 110–114행.
- 구체적 실패 조건: requirements만 설치한 깨끗한 CI에서 `cd full_stack_lab` 후 `python3 tests/oauth_rotation_check.py`를 실행한다. Python의 스크립트 검색 경로는 `tests/`이고 제품 패키지는 `gateway/app/`에 있다. 후보는 17행 helper import 중 `from app import db`를 먼저 실행하여 `ModuleNotFoundError: No module named 'app'`가 난다. 원래 시험은 20행에 해당하는 경로 설정을 먼저 수행했다. requirements 설치가 저장소의 `gateway`를 import 경로에 넣지는 않는다.
- 확인: CI에는 이 단계의 `PYTHONPATH` 설정이 없다. 로컬에서 CI 모양의 검색 경로에 대한 `PathFinder.find_spec('app', search)`는 false, `gateway/` 추가 후 true였다. 이 PC에서는 전체 helper import가 그보다 앞의 `cryptography` 미설치에서 멈췄으므로, 위 CI 오류를 전체 시험 실행으로 재현했다고 쓰지는 않는다. import 순서와 CI 경로를 대조한 확정적 경로 결함이다.
- 최소 수정: `from termination_lab_support import isolated_disposal`을 `OTEL_SDK_DISABLED` 및 `sys.path.insert(...)` 뒤로 이동한다. helper·제품 구현과 assertion은 바꾸지 않는다. 이미지에서 `/app`이 이미 보이는 환경의 7/7 통과로 이 실패 조건을 배제할 수 없다.
- 미수정 영향: 이미지에서는 통과하더라도 기존 GitHub CI의 OAuth 시험이 시작하지 못한다.

### F2 — 예외 발생과 입력에 답하지 않았다는 사실을 구분해야 한다

- 위치: 후보 `protocol_versions_check.py:110–122`, 관련 [제품 연결 코드](../../../../full_stack_lab/gateway/app/upstream.py)의 297–323행.
- 타당한 변경 근거: 현재 제품은 공식 SDK `session.send_request(..., CallToolResult)`를 사용하고 그 호출의 `ValidationError`를 `WireRejected`로 전환한다. 기존 공급자 대역의 `InputRequiredResult`가 이 경로에서 거부되는 것은 D-149와 일치한다. 따라서 예외를 옛 `MCPError` 하나로 제한할 이유는 없다.
- 검증 공백: `PROVIDER_CALLS`는 공급자 `provider_call()`에 전달된 **도구 이름**만 센다. 입력 해결 콜백 실행이나 입력 응답 전송을 세지 않는다. 입력 요청에 답한 뒤 같은 호출 또는 정리 과정에서 `WireRejected`가 나도 현재 assertion은 통과할 수 있다. “예외가 났으니 게이트웨이가 아무 답도 하지 않았다”는 새 주석은 관측 사실보다 강하다.
- 실행한 반례: 두 ref에서 `provider_asks()` AST만 추출해 같은 비동기 client 대역을 주입했다. 대역은 `PROVIDER_CALLS`에 `ask`를 한 번 기록하고, 별도 입력 응답 기록에 `q answered`를 넣은 뒤 `ValidationError`를 원인으로 한 `WireRejected`를 냈다. 원본은 FAIL, 후보는 PASS였다. 답 기록이 없는 같은 예외 경로도 원본 FAIL/후보 PASS였다. 예외 타입은 의존성 없는 동일 상속 형태의 단위 대역이며, HTTP·새 MCP 서버·실제 SDK는 실행하지 않았다.
- 해석: 이는 **시험 판정이 답 기록을 구별하지 못함**을 재현한 것이다. 현재 SDK 또는 제품이 실제로 답했다는 제품 결함 재현이 아니다. 기존 `MCPError` 분기에도 답 이후 예외에 대한 공백은 있었고, 이번 확대가 처음 만든 문제라고 판단하지 않는다. 다만 추가로 허용한 `WireRejected` 경로에도 같은 미관측 상태가 생기므로 변경을 그대로 승인하지 않는다.
- 최소 보강: 기존 공급자/클라이언트 시험 경계에서 입력 해결 콜백 실행 수와 입력 응답·후속 요청을 기록하고 **0회**를 확인한다. `PROVIDER_CALLS == ["ask"]`도 유지한다. 새 회귀 파일에서 “답 없음 + 정당한 WireRejected”는 통과, “답 발생 + 이후 WireRejected”는 실패하게 해 판정의 민감도를 확인한다. 새 자체 MCP 서버는 만들지 않는다.
- 예외 식별도 한정한다. `WireRejected`는 실제 wire 검증 원인을 확인하고, `MCPError`는 허용할 프로토콜 거부 코드/사유를 확인한다. `BaseExceptionGroup`은 첫 자식만 꺼내지 말고 모든 leaf를 검사해 취소·다른 오류를 성공으로 삼지 않는다. 뒤 오류 무시는 기존 코드의 한계이며 이번 검토에서 실제 ExceptionGroup 실행은 하지 않았다.
- 미수정 영향: 세 시험이 이미지에서 모두 통과해도 “공급자 입력에 대한 응답 0”을 검증 완료로 보고할 수 없다. 기기 실행이 있었다는 사실과 이 효과의 증명은 구분한다.

## 요청한 세 경계의 교차 확인

### ① 목적지 허용의 범위

[upstream](../../../../full_stack_lab/gateway/app/upstream.py) 101–123·283–294·327–350행과 [destination](../../../../full_stack_lab/gateway/app/destination.py) 20–44행을 추적했다. P5는 `_internal_endpoint()`의 운영 레지스트리/ACTIVE 실행기 조회를 **해당 시험 URL에 한하여** 대체한다. `_client()`는 그 URL의 host/port를 `target`으로 넘기고 내부 허용 목록도 그 tuple 하나로 만든다. DNS 결과 검증과 숫자 IP 접속을 수행하고 다른 host/port는 연결 전에 거부한다. `follow_redirects=False`, `trust_env=False`도 유지된다.

분리한 실제 허용 함수에 정확한 URL, 다른 경로·query·포트·scheme·호스트·IPv6·끝 슬래시 제거의 8입력을 넣어 정확한 URL 하나만 true임을 확인했다. 실제 `PinnedBackend`와 TCP 연결 대역으로 내부 고정 loopback 정상, 다른 포트 거부, 내부 승인이 없는 loopback 거부 3조건도 확인했다. 네트워크 서비스는 띄우지 않았다. 이 확인은 재바인딩·TLS·운영 레지스트리 승인 실험이 아니다. patch는 프로세스 전역이지만 `with` 동안만 유지되고, 현 시험에는 다른 upstream 호출을 수행하는 백그라운드 작업이 추가되어 있지 않다. 병렬 upstream 작업을 나중에 넣으면 patch 범위를 다시 검토해야 한다.

### ② 예외 확대와 원래 결함 탐지

P4는 assertion AST를 실제로 바꾼다. OAuth·지표 시험의 assert AST는 두 ref에서 동일했지만 프로토콜 시험은 달랐다. 후보 README 앞부분의 “기대값·검사 범위는 변경하지 않았다”는 설명은 후속 변경 전체에는 적용할 수 없다. 마지막 「메인 반영」 절은 기대값 변경임을 따로 인정한다. 그 마지막 절까지 포함해 P4를 B로 판정했다. F2 보강 전에는 “모든 실패는 정답”이라는 주석만으로 채택하지 않는다.

### ③ claims·폐기 대역의 목적 적합성

- OAuth: [idp](../../../../full_stack_lab/gateway/app/idp.py) 216–234행의 SELECT 두 개와 새 대역이 일치한다. 시험의 connection snapshot에서 계열을 고르고, 실제 서명 파일 기록을 실행한다. 두 계열을 넣은 분리 실행에서 다른 계열 제외·transaction snapshot 사용·fetchall deepcopy·미일치 계열의 빈 목록을 확인했다. 기존 회전 경쟁·철회 대기·롤백 assertion을 제거하지 않는다. 다만 이 시험은 signed-list의 복원 방지·서명 손상·호스트 영속성까지 검증하지 않는다.
- 시스템 지표: [agent_contract](../../../../full_stack_lab/gateway/app/agent_contract.py) 153–162행은 `jti` 폐기 확인 → scope 검사 → DB 조회 순서다. 합성 UUID와 `blocked=False`는 첫 단계만 통과시킨다. 실제 scope 검사가 403을 내야 하고, 이를 없애 DB 조회로 흘러가면 기존 `fetch.assert_not_awaited()`가 실패한다. 인증 함수 자체를 성공으로 대체하지 않으므로 이 대역 때문에 scope 결함이 숨는 근거는 없다. JWT 유효성·철회 실패 차단을 검증하는 시험으로 세지는 않는다.

## 검증 기록

| 확인 종류 | 실행 명령·환경 | 결과 |
| --- | --- | --- |
| 범위·판본 | 위 diff, `git rev-parse origin/main luna/stale`, 관련 제품·helper의 두 ref diff | 10개 hunk 확인. 인용한 관련 제품·helper 차이 없음. 범위 밖 변경은 채택 대상에서 제외 |
| 후보 Python 구문 | `git show luna/stale:<시험 경로>`를 Python 3.10 `compile(source, path, 'exec')`로 검사 | 3파일 통과. 후보를 checkout하거나 pyc를 만들지 않음 |
| assertion 보존 | 두 ref의 `assert` 및 `assert*()` AST 비교 | OAuth·지표 동일, 프로토콜 다름 |
| import 검색 경계 | 표준 `importlib.machinery.PathFinder`로 CI 검색 경로와 gateway 추가 경로 비교 | `app`: 설정 전 false / 설정 후 true. 전체 CI 실행은 미실행 |
| 목적지 순수 조건 | 후보 `allow_test_provider()` AST 추출, 실제 `destination.PinnedBackend` + TCP 대역 | 완전 일치 조건 8/8, 목적지 조건 3/3 통과 |
| 신규 DB 조회 | 후보 `Cursor`·`RotationDB.query()` AST 추출, 두 계열·connection snapshot 입력 | 계열 필터·snapshot·deepcopy·빈 목록 확인 |
| 기대 예외 판정 반례 | 두 ref의 `provider_asks()` AST + 비동기 client 대역, 답 기록 유/무 비교 | 후보는 두 입력 모두 PASS. 원본은 두 입력 모두 FAIL. 입력 응답 구별 공백 확인 |
| JavaScript 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 |
| CI Python lint | `cd full_stack_lab` 후 `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` | 실행 불가: `No module named pyflakes`. 경고 0으로 보고하지 않음 |
| 위키 검사 | `python -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 종료 0, `ok: true`, `errors: []`. 전체 검사 경고 119개는 남아 있음 |
| 변경·인코딩 | `git diff --check`, 검토서 바이트·UTF-8/개행·상대 링크 확인 | 통과. BOM·CR·대체 문자 없음, 상대 링크 7개 존재 확인, 작업 트리는 이 검토서 추가만 표시 |

위 검증은 실행한 소스 분리 검사다. 세 시험 전체, 실제 DB·OPA·SDK HTTP 세대 협상·공개 OSS MCP·배포·PJ1은 이번에 **미실행**이다. 로컬 Python은 3.10이고 `starlette`, `cryptography`, `psycopg`, `pglast`, `httpx2`, `mcp`, `pyflakes`도 없다. 사용자 전달 및 후보 README의 기기 결과(OAuth 7/7, 지표 10/10, 프로토콜 정상 종료)는 외부 보고로만 인용하며, 이 검토에서 독립 재실행하거나 실행 이미지의 소스 해시와 대응시키지 않았다. 고정 SDK 원본의 위키 등록 로컬 경로도 이 클론 환경에는 없어 SDK 내부는 재검토하지 않았다.

원격 HEAD 확인 `git ls-remote --symref origin HEAD`는 GitHub:443 연결 실패로 미완료다. 지정받은 fetch 완료 ref를 사용했으며 새 fetch·브랜치 전환·스택 기동·커밋은 하지 않았다. 제품·엔드포인트 코드를 변경하지 않아 `map_threats.py` 재생성은 대상 밖이다.

## 기존 시험 변경 필요

**있음.** O1의 import 순서 수정과 P4의 기대 예외/무응답 검증 보강 후 채택한다. 기존 시험은 한 줄도 수정하지 않았다. 수정 작업은 이 읽기 전용 검토 범위 밖이다. A hunk도 후보의 다른 변경 전체를 승인한다는 뜻은 아니다.

## 기기에서 확인할 파일·명령

F1·F2 반영 후, 솔루션 기기의 검토 대상 제품 코드와 시험 파일을 함께 고정해 실행한다. `protocol_versions_check.py`는 `/app`을 우선 import하므로 mount한 시험과 이미지 코드의 commit·소스 해시·실제 import 경로를 먼저 맞춘다.

```bash
cd full_stack_lab
docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/oauth_rotation_check.py
docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/system_metrics_check.py
docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/protocol_versions_check.py
```

F1은 이미지 실행과 별도로 CI와 같은 깨끗한 Python 3.12 환경에서 requirements 설치 후 `cd full_stack_lab && python3 tests/oauth_rotation_check.py`로 확인해야 한다. F2의 추가 순수 회귀는 무응답 정상군과 답 이후 오류 음성군을 함께 실행해야 한다. 위 기기/CI 명령은 이 검토에서 실행하지 않았다. 사용자에게 필요한 추가 입력은 없다.
