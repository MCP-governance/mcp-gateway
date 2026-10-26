# 리팩토링 1단계 착수 전 분석 — 패키지 경계·순환 import (2026-10-26)

분석: Codex(gpt-6.1-sol), 리더 검토. 기준 main `d139ee5`. 제품 코드 변경 없음. 수치는 `tools/analyze_imports.py`(표준 라이브러리 ast) 실행 결과(실측)다.


작성일: 2026-10-26. 분석 대상은 현재 워크트리의 실제 파일 바이트다. 브랜치 `10/26-stage1-boundary-analysis`, 기준 `origin/main d139ee5`, 0단계 0-2·0-3·0-4·0-7 병합 상태는 **사용자 제공 기준**이며 Git 명령으로 확인하지 않았다. 제안서·감사 입력은 `cdef0bb` 기준이다(`제안서(PR 37) README.md:3`, `제안서(PR 37) code-audit.md:1`). 과거 수치와 현재 실측을 구분한다.

**권고: 현재 경계를 고정하는 계약부터 넣고, 콘솔의 불필요한 core 의존과 6개 직접 순환을 작은 추출 PR로 제거한다. 전체 파일 이동과 execute_call 파이프라인 이식은 그 다음이다.** 현재 상태에서 `mint.gateway → mint.control` 전면 금지나 전역 비순환 계약을 켜면 통과하지 않는다. 6쌍 제거는 전역 비순환과 동치가 아니다.

제품 코드·시험·설정·위키는 변경하지 않았다. 산출물은 이 보고서와 비커밋용 `ANALYZE-s1.py`뿐이다. 입력 두 파일 및 스크립트는 커밋 대상에서 제외한다. `.importlinter` 파일은 만들지 않았다. 이번 지시의 산출물 제한에 따라 현황·백로그·결정 기록도 갱신하지 않는다.

## 1. 방법과 재현

표준 라이브러리 `ast`, `pathlib`, `hashlib`, `json`, `configparser`, `fnmatch`만 사용한다. 제품 모듈을 import하거나 실행하지 않는다. import-linter 설치·실행, 네트워크 서비스 기동, Git 명령은 하지 않았다.

```text
python -X utf8 ANALYZE-s1.py --self-test
python -X utf8 ANALYZE-s1.py --compact
python -X utf8 ANALYZE-s1.py
python -X utf8 ANALYZE-s1.py --report-tables
```

기본 출력은 전체 JSON이다. `imports`에 소스 모듈·대상·시작/끝 행·심볼·별칭·함수 범위·원문 import 문을 남긴다. `definitions`는 최상위 함수/클래스 위치, `modules`는 파일 크기·지문·이동 영향, `external_imports`는 app 밖 Python 호출자를 담는다. 부록 A~D는 `report_tables(analyze())`의 출력 그대로다. 스크립트는 stdout으로만 출력한다.

- 노드: `gateway/app/*.py` 중 `__init__.py`를 제외한 모듈. 간선 방향: importer → imported. 표준 라이브러리·외부 패키지 의존은 내부 그래프에서 제외.
- Eager(E): 함수 밖 import. 최상위 `if`/`try`와 클래스 본문도 E에 포함한다. Lazy(L): 함수·async 함수·메서드·중첩 함수 내부 import. 클래스 본문의 import는 지연으로 오분류하지 않는다.
- `from . import a,b`, `from .a import x,y`, `from app.a import x`, `import app.a as a`를 해석한다. 심볼 여러 개를 가져와도 같은 `(소스, 대상)` 간선은 하나다. 동일 문을 여러 번 방문하지 않는다.
- Tarjan SCC를 E 그래프와 E∪L 그래프에 각각 적용한다. 단일 노드 SCC도 전체 결과에 보존하며, 본문에서 “순환 SCC”는 크기 2 이상 또는 자기 고리가 있는 성분만 뜻한다.
- 2-사이클은 서로 다른 A,B에 대해 A→B와 B→A가 있고 E만으로는 쌍이 완성되지 않는 경우다. “지연으로만 닫힘”은 **양방향 모두 지연**이라는 뜻이 아니다.
- app 밖 Python 파일도 AST로 훑어 절대 경로 import를 별도 집계했다. 구문/인코딩 해석 실패는 **0개**다. Python 문자열 로더·셸·compose·패키징·AST 기반 시험의 파일 경로는 import 문 개수에 포함하지 않는다.

측정 파일 집합 지문(`파일명:원시 바이트 SHA-256` 정렬 후 재해시):

```text
860025c20f03605357284db91e206690e16770e9544efd44de4fa340cf074d12
```

이 지문은 68개 app Python 파일을 고정한다. Git commit 동일성이나 배포 상태를 입증하지 않는다. 함수별 행 번호는 이 지문 기준이며 이후 이동 시 갱신해야 한다.

## 2. 실측 결과와 감사 정정

| 항목 | 현재 AST 실측 | 감사와 비교 / 의미 |
| --- | ---: | --- |
| 파일 / 그래프 노드 | 68 / 67 | 감사와 동일 |
| 모듈 LOC 합계 | 24,507 | 감사 24,451 대비 +56. 실제 파일 줄 수이며 diff 원인은 Git 없이 특정하지 않음 |
| 내부 import 문 위치 | 170 | E 84, L 86. 감사의 “지연 57”은 문 개수가 아님 |
| E 간선 / L 간선 | 199 / 57 | 각 범위에서 모듈 쌍 중복 제거, 감사와 동일 |
| E∩L / E∪L | 3 / **253** | 199+57=256은 범위별 합. 중복 없는 전체 그래프는 253 |
| E 그래프 SCC | 67개, 전부 크기 1 | 순환 SCC 0 |
| E∪L 그래프 SCC | 37개 = 크기 31 하나 + 크기 1인 36개 | 순환 SCC 1, 감사와 동일 구성 |
| 지연 import로 닫히는 2-사이클 | **6쌍** | 감사와 동일, 추가·소멸 쌍 없음 |
| core 직접 팬아웃 | E **32**, L 2, 합집합 **33** | 감사의 “최상위 33”은 현재 값과 다름. 전체 33은 일치 |
| 콘솔 → core | 1 import 문, 2 심볼, 3 사용처 | 감사 C-3의 두 심볼 확인 |

E∩L은 `agent_service→local_jobs`(`agent_service.py:35` E, `:849,886,936` L), `core→endpoint_plane`(`core.py:29` E, `:1773,2319` L), `upstream→registry`(`upstream.py:30` E, `:300` L)다. 감사 `제안서(PR 37) code-audit.md:180`의 256은 이 3개가 두 번 계산되는 표현으로 읽어야 한다. 과거 원본 그래프를 실행한 결과는 없으므로 “0단계에서 간선 3개가 제거됐다”고 해석하지 않는다.

크기 31 SCC의 모듈:

```text
agent_contract agent_service audit automatic_suspend classify connectors consent core
decommission dispatch endpoint_plane experiments idp incidents integrations litellm_sync
local_jobs oidc ops_response pac privacy registry release retention review sbom_impact
secret_scan tool_sunset upstream user_credentials user_suspend
```

core의 E 팬아웃 32개:

```text
classify connections consent contract db destination dispatch disposal endpoint_plane
flow_fingerprint high_impact intake_proposal litellm_sync local_jobs ops_response outcomes
output_contract pac poisoning privacy registry residency retention review risk_tier
secret_scan selective supplier_assurance tool_sunset upstream user_credentials user_suspend
```

지연 import 대상은 `endpoint_plane`, `mcp_sessions`다. 전자는 E에도 있으므로 순증은 `mcp_sessions` 1개다. 근거는 `core.py:29`~`:38`과 부록 B의 전체 위치 목록이다.

### 2.1 6쌍과 끊을 방향

아래 파일은 모두 `full_stack_lab/gateway/app/` 아래다. L/E는 위 정의를 따른다.

| 쌍 | 정방향 근거 | 역방향 근거 | 우선 제거할 직접 간선 |
| --- | --- | --- | --- |
| agent_contract ↔ oidc | agent_contract.py:185,189 L (`end_session`, `validate_session`) | oidc.py:22 E | agent_contract → oidc |
| agent_service ↔ idp | agent_service.py:34,42 E | idp.py:99 L (`login_allowed`, `record_failed_login`) | idp → agent_service |
| endpoint_plane ↔ local_jobs | endpoint_plane.py:629 L (`revoke_device`) | local_jobs.py:269,588 L | endpoint_plane → local_jobs |
| endpoint_plane ↔ idp | endpoint_plane.py:642 L (`revoke_device`) | idp.py:113,186,200,346,375 L | endpoint_plane → idp |
| incidents ↔ ops_response | incidents.py:13 E, 사용 :271 | ops_response.py:238 L, 사용 :240 | incidents → ops_response |
| registry ↔ upstream | registry.py:295 L (`build_lock`) | upstream.py:30 E、:300 L | registry → upstream |

선택한 6방향만 삭제한 **간선 제거 모델**에서는 다음 16개 모듈이 여전히 하나의 SCC다(스크립트의 `planned_edge_removal_only`). 새 추출 모듈은 이 모델에 추가하지 않았으므로 구현 후 SCC 수의 예측은 아니다.

```text
agent_contract audit consent core decommission dispatch endpoint_plane experiments idp
incidents local_jobs oidc ops_response pac upstream user_suspend
```

따라서 직접 6쌍 제거만으로 패키지 DAG를 선언하지 않는다. 예를 들어 `core→ops_response→incidents→core`는 `core.py:29`, `ops_response.py:238`, `incidents.py:13`에 남는다. 이 반례 때문에 중간 계약은 직접 의존만 금지하는 항목을 명시적으로 사용한다.

### 2.2 콘솔이 실제 사용하는 core 심볼

| 심볼 | 실제 사용처 | 현재 정의 / 재노출 | 조치 |
| --- | --- | --- | --- |
| registration_endpoint | agent_service.py:1256, `remote-endpoint` 도입 미리보기 | core.py:554~561 | 순수 URL 검사와 아래 의존을 함께 기존 destination.py로 추출하고 직접 import |
| canonical_hash | agent_service.py:1808,2599, 검토값 digest 생성 | contract.py:43 정의, core.py:34~37 재노출 | contract에서 직접 import |

`registration_endpoint`는 혼자 옮기면 작동하지 않는다. `transport_secure`(`core.py:1314~1322`), `_endpoint_host`(`:1304~1311`), `LOCAL_HOSTS`(`:1301`)가 필요하다. 이 묶음은 8+9+8+1=26개 소스 행이다. `urlsplit`도 가져오며 기존 URL 검사 순서·메시지·내부 HTTP 허용 규칙을 보존한다. 기존 `destination.py:1`~`:57`은 app 내부 import가 없어 역의존을 만들지 않는다. 최종 논리 배치는 `mint.shared`의 URL 규칙과 `mint.gateway.transport`의 DNS 고정 어댑터로 나눌 수 있으나, 첫 PR은 기존 파일을 재사용한다.

다른 호출자는 `main.py:894`, `core.py:591~592,632,635`다. core의 기존 재노출은 이행 중 유지할 수 있다. **제안서 §2.3의 “콘솔은 contract.canonical_hash만”은 현재 기능 전체를 설명하지 못한다.** URL 검사 호출도 하위 모듈로 바꿔야 직접 core 의존이 사라진다. 콘솔의 나머지 upstream 의존과 간접 경로까지 없어졌다는 뜻은 아니다(`agent_service.py:34`).

## 3. 최소 추출안과 목표 배치

“최소”는 위 직접 간선을 끊는 데 필요한 함수와 그 전역 의존의 닫힘이다. 전체 그래프의 최소 피드백 간선 집합을 최적화했다는 주장은 하지 않는다. 전체 67개 모듈의 배치·이동 영향은 부록 A, 실제 import 그래프는 부록 B에 둔다.

| 추출 단위 / 근거 | 이동 대상(초기 app 경로 → 최종 논리 패키지) | 함께 옮길 것 / 깨지는 의존 | 한계 |
| --- | --- | --- | --- |
| registration_endpoint 및 URL 규칙, core.py:554~561,1301~1322 | 기존 app.destination → mint.shared의 URL 규칙 | 위 26행 + urlsplit. 콘솔 import 1문과 사용 3곳 변경(해시 2곳 포함) | DNS 고정 정책을 바꾸거나 강화하지 않음 |
| login_allowed·record_failed_login, agent_service.py:58~70 | app.login_throttle → mint.identity | `_login_attempts`, 제한·기간 설정 :49~54, defaultdict/time. agent_service와 idp.py:99가 같은 모듈 상태 사용 | 사본을 두면 한 프로세스 내 제한을 우회하므로 금지 |
| OIDC client/settings/crypto, oidc.py:42~109 | app.oidc_client → mint.identity | `oauth` :26와 PinnedOAuthClient/App, settings/configured/local_login_allowed/cipher/seal/unseal/http_transport/client. 기존 oidc에서 재노출 | 세션 함수가 다시 oidc를 import하면 추출 효과 없음 |
| _refresh_upstream, oidc.py:234~282 | app.identity_sessions → mint.identity | 행 락·회전·예외 처리 49행. ADMIN_IDLE/REFRESH_EARLY_SECONDS 등 공유 상수의 단일 소유 | FOR UPDATE와 외부 HTTP 순서 유지, R-17/P3와 섞지 않음 |
| validate_session·touch_session·end_session, oidc.py:285~378 | app.identity_sessions → mint.identity | 53+10+27=90행, ADMIN_IDLE/MAX 등 사용 상수. CONSOLE_SCOPE는 agent_contract에서 독립한 상수 모듈로 이동 | agent_contract→identity_sessions→agent_contract 새 2-사이클 금지 |
| revoke_device, endpoint_plane.py:628~647 | app.endpoint_lifecycle → mint.endpoint의 수명주기 조정 | 20행 전체(로컬 정지→DB 변경→토큰 철회→풀 해제→세션 종료). local_jobs/idp/mcp_sessions/upstream import는 조정 모듈이 소유 | 6쌍 중 2쌍을 한 번에 제거. wrapper 경유 3-사이클은 별도 측정 |
| emit_alert, ops_response.py:37~40 | app.alert_store → mint.control | 4행 + db/Jsonb. incidents.py:271을 직접 소비자로, ops_response는 동일 함수 재노출 가능 | incidents→alert_store→ops_response 역참조 금지 |
| build_lock, registry.py:293~307 | app.registry_lock → mint.control의 등록 검사 | 15행 + UTC/datetime/Any, registry 조회 함수와 upstream.discover. registry.py:310~315 CLI는 위임 | 기존 `python -m app.registry lock` 인터페이스 유지. 간접 순환은 남을 수 있음 |
| _policy, core.py:1668~1679 | 추후 mint.policy 어댑터 | 12행, OPA_URL·connections 등 의존 확인 후 이동 | 이번 6쌍 해소 필수 아님; 판정 횟수·실패 정책 유지 |
| _record_decision, core.py:2055~2172 | 추후 mint.ledger append | 118행 외에도 `_audit_payload` :2035~2049, `_storable` :1897~1905, `response_disposition` :157~163 및 설정/모듈 의존 필요 | 함수만 add/delete하면 236행; 부품 31행까지 합치면 298행에 import조차 못 넣는다. 선행 부품 PR 없이 300행 이하 완료 주장 금지 |
| _contract, core.py:1174~1237 | 추후 mint.registry 조회 경계 | 64행, registry/DB/기한·계약·분류 의존 | 제어 평면 쓰기와 읽기 모델 분리는 후속 설계 |
| execute_call, core.py:2255~2640 | 추후 mint.gateway.decision | 386행, 제안서 §2.2의 단계들 | 통째 이동은 add/delete 772행. 첫 경계 PR에서 제외; 순차 추출은 R-15 별도 작업 |

`mint.shared`는 “다른 MINT 패키지에 의존하지 않음”으로 해석한다. 제안서 `제안서(PR 37) README.md:144`의 “shared는 아무도 import 안 함”은 반대로 해석하면 `:142`의 공통 DB/해시 배치와 충돌한다. DB·HTTP 클라이언트·스캐너 등 외부 라이브러리 의존과 app 내부 역의존은 구분한다.

목표 이름에 대한 추가 판단:

- `contract`는 현재 `contract.py:1`부터의 순수 계약/해시 정의를 유지한다. 승인·탐지 코드를 넣는 범용 폴더로 만들지 않는다.
- `registry`는 카탈로그/계약 읽기 책임을 독립 표시했다. 현재 쓰기·발견/승인 경로를 한꺼번에 이 이름 아래 옮기면 gateway→control 역의존이 숨는다(`registry.py:175`의 sync, `:293`의 build_lock).
- `decision`은 `mint.gateway` 내부 파이프라인 책임이다. `core.py`의 등록·운영·원장 함수를 전부 decision으로 옮기는 안은 보류한다.
- `main`은 현재 관리 라우트와 판정 입구가 함께 있다(`main.py:22,40`의 control 모듈 import). 부록 A는 판정 입구의 최종 주책임을 배정한 것이며, 이 파일 그대로 gateway에 옮겨 최종 forbidden 계약을 통과할 수 있다는 뜻은 아니다.
- `audit`의 현재 투영/읽기 로직도 ledger 읽기 API로 배치하되 core 재참조를 없애야 한다(`audit.py`의 import는 부록 B). retention→review, review→endpoint_plane 등도 최종 계층 전환 전 분리 대상이다.
- 새 스냅숏·SSO 체계·Settings·패키징 의존성을 이번 첫 항목에 추가하지 않는다. 보안 기능·기본값 변경 없이 경계만 드러낸다.

## 4. 이동 영향과 호환성 범위

부록 A의 수치는 **가상 단독 이동 시 고칠 import 문 위치**다. 패키지 이름만 바꾼 실제 diff 행 수나 런타임 장애 수가 아니다. `from . import db, registry, core`처럼 한 문이 여러 대상에 걸치면 각 행의 영향 수에 동시에 잡힌다. 묶음 이동의 총량은 합집합으로 다시 계산해야 한다.

특히 core 전체 이동은 app 내 18문 위치 + app 밖 37문 위치에 영향을 준다. `db`는 46+28, `registry`는 26+12다. 이 정도 팬인이 있는 모듈은 기존 import 이름·전역 상태를 먼저 유지하고 함수 단위로 옮기는 편이 안전하다. 복사한 구현 두 벌이나 서로 다른 DB 풀/상태 객체를 만들지 않는다.

import 문 외에 반드시 포함할 호출자·시험·설정:

| 범위 | 현재 근거 | 변경 시 필요한 처리 |
| --- | --- | --- |
| 프로세스 진입점 | gateway/Dockerfile:35 `app.main:app`; deploy/compose.yaml:152 `app.agent_service:app`; :336 `app.siem`; full_stack_lab/compose.yaml:200,223,240 | 첫 PR에서는 진입점을 유지. 최종 mint root 전환 시 이미지 COPY/PYTHONPATH와 같이 변경 |
| registry CLI | full_stack_lab/console.sh:175,540; tests/security_regression.sh:220 | 기존 `python -m app.registry lock` 유지 또는 모든 호출자·도움말을 함께 이행. 사람이 승인하는 lock 파일을 자동 교체하지 않음 |
| 로그인 상태 monkeypatch | tests/oauth_rotation_check.py:223~225 | agent_service.login_allowed 패치가 idp 새 경로까지 영향 주는지 재검토. 새 소유 모듈을 패치하되 제한 검증은 유지 |
| 사건 경보 monkeypatch | tests/incident_pack_check.py:276~279,291 | ops_response.emit_alert 패치가 새 alert_store 호출을 덮지 못할 수 있음. 패치 소유자만 변경, 실패·heartbeat assertions 유지 |
| 함수 AST 추출·직접 경로 | tests/managed_policy_gap_check.py:71; tests/intake_one_click_ast_check.py:102; tests/auto_suspend_record_path_check.py:3 | 새 파일/심볼을 따라가도록 로더만 수정. 기대 정책·효과를 변경하지 않음 |
| 파일명에 묶인 AST 허용 목록 | tests/nested_tx_check.py:19,157의 oidc._refresh_upstream | 추출 뒤 새 파일·함수 쌍으로 이동. 예외 근거(회전 직렬화) 보존, 새로운 무조건 면제 금지 |
| 엔드포인트 종료·재등록 | endpoint_plane.py:861; main.py:1592; tests/managed_enrollment_check.py:77; tests/token_revocation_pg_check.py:152 | 기존 revoke_device API 위임 유지, quiesce/DB/철회/풀/세션 순서 동일 |
| 저장소 밖 소비자 가능성 | core.py:34의 명시적 re-export 주석 | core의 호환 재노출을 소비자 전수 전환 전 제거하지 않음. 저장소 외 사용 여부는 미확인 |

핵심 판정 불변식은 신원의 transport 토큰 단일성, 직원 토큰 업스트림 전달 금지, OPA 불능 차단, 계약 TOFU 금지, append-only 원장, 전송 직전 재확인, 종료 순서다. 이번 이동에서 기본값·락 범위·예외 변환·검사 횟수·반환 메시지를 바꾸지 않는다. 정책 입력/응답의 의미가 바뀌면 경계 PR을 중단하고 원인을 분리한다.

## 5. import-linter 계약 두 판

**부록 C는 첫 PR용**, **부록 D는 6쌍과 콘솔 직접 core 의존 제거 후용**이다. 두 판 모두 현재 실제 root인 `app`를 쓴다. 존재하지 않는 `mint`를 root로 지정하거나 optional layer로 숨겨 통과시키지 않는다. 실행 위치는 `full_stack_lab/gateway` 또는 여기가 import 경로에 들어간 환경이다. 이번에는 INI를 보고서 안에만 두었다.

현재 고정 판의 범위:

- layers: `main` 위에 역방향 의존이 생기지 않게 하고, core/콘솔 아래 순수 leaf 5개의 방향을 고정한다. `:`는 같은 계층의 상호 의존을 허용한다. `|`로 쓰면 현재 core↔콘솔의 간접 경로 때문에 불필요하게 실패한다.
- forbidden: leaf 5개는 다른 app 모듈을 가져오지 못한다. core는 현재 33개 직접 의존만 **정확한 간선 예외**로 허용한다. 새 모듈 직접 import는 실패한다.
- 콘솔→core는 현재 한 간선만 예외 처리한다. 심볼 추가 사용까지 import-linter가 막지는 못한다. `console_core_uses` 출력으로 두 심볼·세 위치 기준선도 리뷰한다.
- `unmatched_ignore_imports_alerting = error`로 제거된 예외가 남으면 실패시킨다. 예외는 정상 추출 시 삭제/치환하며 wildcard 예외를 늘리지 않는다. 이 판이 67개 모듈의 모든 신규 간선을 막는 것은 아니다.

6쌍 제거 후 판은 해당 **직접** 간선 6개와 콘솔→core를 예외 없이 막는다. `allow_indirect_imports = True`를 의도적으로 둔다. 새 조정 모듈을 경유하는 간접 경로는 허용하므로 전역 비순환·평면 독립을 보증하지 않는다. 가짜 동작 변경 없이 기존 registry CLI와 endpoint API를 위임으로 보존하는 이행 단계에 맞춘 계약이다. 기존 core 팬아웃 고정 계약은 실제 추출 대상의 새 경로로 예외를 재계산해 유지한다(부록 D의 최소 초안에서는 변경 전 33개 목록을 그대로 재사용하지 않았다).

최종 §2.3 패키지로 강화하려면 `mint.gateway`에서 core의 등록/운영 작업과 main의 제어 라우트를 먼저 빼고, identity↔endpoint의 세션·철회 의존, ledger→control·gateway 역참조도 제거해야 한다. 그때의 layers는 위에서부터 `mint.control`, `mint.gateway`, `mint.policy : mint.identity : mint.endpoint : mint.registry : mint.ledger : mint.snapshot`, `mint.shared`로 설계하되 **중간 계층 간 방향도 실측 후 분해**한다. forbidden은 `mint.gateway → mint.control`, `mint.shared → 나머지 모든 mint 패키지`를 **간접 경로까지** 금지하는 기본값으로 둔다. 지금 이 최종 계약의 통과를 주장하지 않는다. snapshot 발행/구독 책임도 2단계 설계와 함께 확정한다.

계약 검증 실측:

| 검사 | 결과 | 증거 범위 |
| --- | --- | --- |
| 부록 C를 현재 E∪L 그래프에 대입 | 위반 0 | 스크립트의 제한된 INI/그래프 검사 |
| 부록 D를 현재 그래프에 대입 | 위반 7 | 위 6방향 + agent_service→core, 음성 검증 |
| 위 7직접 간선을 제거한 그래프에 부록 D 대입 | 위반 0 | 간선 제거 모델. 새 파일의 간선/초기화는 포함하지 않음 |
| import-linter 엔진으로 실행 | **미실행** | 설치 금지. 실제 PR에서의 엔진 통과를 대신하지 않음 |

### 5.1 최종 패키지 이름으로 전환할 때의 계약 치환 초안

다음은 부록 D의 직접 순환 제거 계약 이후 사용할 **최종 패키지용 강화안**이다. 앞서 설명한 추가 분리와 모든 `mint.*` 패키지 실체가 생긴 뒤 적용하며, 6쌍 제거만으로 통과 가능한 계약으로 제시하지 않는다. 초기 두 판은 부록 C/D이고, 이 조각은 최종 제안서 경계가 어떤 INI가 되는지 명확히 하기 위한 별도 치환 초안이다. 이 초안은 AST 대입 검증 대상이 아니다.

```ini
[importlinter]
root_package = mint

[importlinter:contract:planes-and-foundation]
name = Planes depend on foundation
type = layers
layers =
    mint.control
    mint.gateway
    mint.policy : mint.identity : mint.endpoint : mint.registry : mint.ledger : mint.snapshot
    mint.shared

[importlinter:contract:gateway-no-control]
name = Gateway cannot depend on control
type = forbidden
source_modules =
    mint.gateway
forbidden_modules =
    mint.control

[importlinter:contract:shared-no-domain]
name = Shared cannot depend on domain packages
type = forbidden
source_modules =
    mint.shared
forbidden_modules =
    mint.control
    mint.gateway
    mint.policy
    mint.identity
    mint.endpoint
    mint.registry
    mint.ledger
    mint.snapshot
    mint.testing

[importlinter:contract:console-no-decision]
name = Console cannot depend on decision implementation
type = forbidden
source_modules =
    mint.control.agent_service
forbidden_modules =
    mint.gateway.decision
```

### 5.2 공식 OSS 근거와 사용 범위

관련 OSS는 [seddonym/import-linter v2.15, commit 31927f1](https://github.com/seddonym/import-linter/commit/31927f1)로 고정해 문서만 검토했다. 2026-09-04 릴리스와 [2.15 공식 릴리스 이력](https://import-linter.readthedocs.io/en/stable/release_notes/)이 확인돼 유지보수 중인 후보로 판단한다. 라이선스는 BSD-2-Clause다([고정 commit의 LICENSE](https://github.com/seddonym/import-linter/blob/31927f1/LICENSE)). 인기 수치는 선택 기준에 넣지 않았다.

문법 근거는 [v2.15 layers 공식 원문](https://raw.githubusercontent.com/seddonym/import-linter/v2.15/docs/contract_types/layers.md), [v2.15 forbidden 공식 원문](https://raw.githubusercontent.com/seddonym/import-linter/v2.15/docs/contract_types/forbidden.md), [공통 옵션](https://import-linter.readthedocs.io/en/stable/contract_types/)이다. layers의 간접 경로 포함과 `:` 계층 문법, forbidden의 `allow_indirect_imports`·`as_packages`, 정확한 `ignore_imports`를 확인했다. 라이선스 본문·외부 스크립트를 복사하거나 실행하지 않았다. 신규 의존성과 공개 스킬은 도입하지 않는다. 이번 AST 스크립트는 제품용 import-linter 대체품이 아니라 분석용이며, 엔진/Grimp의 모든 해석 규칙을 구현하지 않는다.

## 6. 300행 이하의 첫 PR 순서

제품 코드 예산은 **추가+삭제 물리 행 합계**로 보수적으로 잡았다. 함수 이동도 두 번 센다. 표의 예산은 실행된 diff의 실측이 아니라 소스 함수 길이에 기초한 **상한 계획**이다. 각 PR 구현 때 실제 diff가 300을 넘으면 다음 PR로 나누며 시험·설정 변경을 숨기지 않는다. 모든 PR은 동작 불변이며 전송/쓰기 부작용을 실제로 두 번 실행하는 그림자 모드는 사용하지 않는다.

공통 합격선 G: 변경 Python 구문/pyflakes, import 그래프 및 해당 계약, 기존 로컬 시험 실행기, `open_endpoints.py`, `nested_tx_check.py`; CI 일회용 스택의 기존 인수·적대·Rego·PG 회귀 전부 통과. 정책 검증은 decision과 policy_id를 함께 확인하고 실패를 skip/통과로 세지 않는다. 기기 검증이 필요하면 솔루션 기기 배포→지정 시험 PC 하네스로 진행한다. 로컬 compose는 띄우지 않는다. 이번 분석에서는 아래 제품 시험을 실행하지 않았다.

| 순서 / PR | 옮길 것·바뀌는 import | 제품 add+delete 예산 | 주된 위험 | 합격 시험(각 행에 G 공통) |
| --- | --- | ---: | --- | --- |
| S1-01 현재 계약 | 부록 C를 향후 CI에 도입. 제품 이동 없음. 분석 스크립트 대신 관리되는 AST 검사 채택 여부도 이 PR에서 결정 | 0 | 지연 import 누락·새 root 경로 오설정 | 현재 0위반 + 금지 간선 삽입 시 실패 + 기존 CI. import-linter 실제 사용은 이 작업 밖의 의존성 승인/정책에 맞춤 |
| S1-02 콘솔 core 분리 | core URL 검사 26행을 기존 destination로 이동, core는 호환 재노출. 콘솔은 contract.canonical_hash와 destination.registration_endpoint 직접 사용 | ≤100 | HTTP/TLS 허용 범위·기존 monkeypatch | intake_validation_test, address_destinations_check, security_edges_check, intake_one_click_ast_check, 도입 인수. console_core_uses=0 및 새 URL 거절/허용 경계 동등 |
| S1-03 로그인 제한 | login_throttle에 함수 11행+설정/상태 약 6행 이동. idp와 콘솔이 같은 함수/상태 import | ≤80 | 상태 이중화·oauth_rotation monkeypatch | oauth_rotation_check, oauth_negative_pg_check, 로그인 인수. 같은 key의 두 진입 경로에서 제한 누적, 시간창 복구 |
| S1-04 경보 저장 | emit_alert 4행을 alert_store로 이동. incidents 직접 import, ops_response 재노출 | ≤50 | 실패 전파·알림 중복·synthetic 플래그 | incident_pack_check, ops_response_check, siem_queue_pg_check. 경보 실패→timer failure 기록 유지 |
| S1-05 등록 발견 | build_lock 15행을 registry_lock로 이동. registry CLI/함수는 위임, upstream은 registry 읽기 유지 | ≤100 | CLI 출력·호출 순서·잠금 파일 승인 | contracts_check, security_regression의 lock 대조. 실제 승인 OSS MCP에서 JSON 키/도구 해시 동일; generated_at만 정규화해서 비교 |
| S1-06 엔드포인트 철회 | revoke_device 20행을 endpoint_lifecycle로 이동, endpoint_plane의 public API는 위임. 두 직접 역간선 제거 | ≤100 | 중지/철회/풀 해제 순서·재설치 경합 | managed_enrollment_check, token_revocation_pg_check, restore_residual_pg_check, local_jobs_pg_check. 실패 시 기존 미완료/차단 상태 보존 |
| S1-07 OIDC 하위 client | oidc.py:42~109의 68행과 oauth 객체를 oidc_client로 이동. 기존 oidc API 재노출. 세션 상수/CONSOLE_SCOPE는 단일 하위 소유로 연결 | ≤210 | OAuth client 인스턴스 이중화·SSRF 전송 설정·환경변수 평가 시점 | oss_audit_test, oauth_negative_pg_check, OIDC 로그인/차단 인수. 동일 설정·토큰 endpoint·암호 seal/unseal 동등 |
| S1-08 OIDC refresh | _refresh_upstream 49행을 identity_sessions로 이동, oidc는 재노출. oidc_client와 세션 상수만 하위 의존 | ≤160 | 행 락·refresh 재사용·nested_tx 허용 목록 파일 경로 | nested_tx_check의 기존 회전 예외 위치만 이전, oauth_rotation_pg_check, OIDC refresh 성공/invalid_grant/503. 락·예외 분기 동일 |
| S1-09 OIDC 검증/종료 | validate 53+touch 10+end 27=90행 이동. agent_contract/idp 직접 identity_sessions 사용, oidc는 재노출 | ≤260 | 계정 중지·idle/max·introspection 장애·폐기 HTTP | resource_residual_check, system_metrics_check, oauth_negative_pg_check, oauth_rotation_pg_check, 실제 OIDC 세션 인수. 401/403/503·헤더·철회 순서 동일 |
| S1-10 직접 순환 계약 강화 | 부록 D의 6방향 + 콘솔 core 금지 적용. core 팬아웃 계약 예외는 새 경로에 맞춰 갱신. 남은 SCC 재보고 | 0 | 6쌍 제거를 전체 분리 완료로 오인 | 현재 계약과 새 간선 음성 검사, 새 파일 포함 SCC 실측. G 및 정상/적대 결과 유지 |

위 10개는 대규모 패키지 이름 변경 없이 수행할 수 있는 첫 묶음이다. 새 파일 배치가 각 책임을 드러내면 그때 `app.<책임>/` 패키지로 승격하고 최종 `mint.*` 이름은 별도 이행한다. 143행 contract 전체를 삭제/추가하면 286행이므로, 모든 import를 한 PR에서 바꾸는 “contract 폴더 만들기”도 300행을 넘기기 쉽다. 이름 변경을 0행으로 계산해 예산을 우회하지 않는다.

후속 경계 PR은 (a) 원장용 순수 payload 부품 먼저 추출, (b) `_record_decision` 118행과 필요 import를 ≤280행 안에서 이동, (c) `_policy` 어댑터, (d) `_contract` 조회 API 순으로 각각 별도 범위를 잡는다. `_record_decision`이 사용하는 자동 중지/예약/설정까지 포함한 실제 의존 폐쇄를 먼저 다시 읽고 300행을 지킬 수 있을 때 진행한다. `execute_call` 분해·P3 중복 제거·P4 병렬화·Settings·스냅숏은 이 첫 경계 묶음에 섞지 않는다.

인수 시험의 기대값은 오라클로 유지한다(`제안서(PR 37) README.md:311`, `full_stack_lab/console.sh:606~624`). 내부 경로/monkeypatch/AST 로더만 바뀌는 시험은 같은 PR에서 이행할 수 있지만 기대 decision·policy_id·DB 효과·실패·복구 기준을 완화하지 않는다. 기존 CI는 로컬 실행기와 PG 실행기를 이미 호출한다(`.github/workflows/verify.yml:228,295`); 감사 시점의 “CI 미연결”을 현재 상태로 반복하지 않는다.

## 7. 검증과 남은 한계

실행 완료: 68개 app 파일 AST 해석, 67노드 전체 그래프, E/L 분리, SCC·6쌍·core 팬아웃·콘솔 심볼 추적, app 밖 Python import 조사, INI 파싱 및 위 3종 계약 그래프 검사, 분석기 자체 점검. 부록 표·계약은 같은 분석 결과에서 생성했다. 자체 점검은 별칭·상대/절대 import·클래스 eager·함수 lazy·SCC·직접/간접 forbidden 차이를 확인한다. 독립적인 Kosaraju 계산으로 Tarjan의 전체 SCC 구성을 대조했고, core→acceptance 및 contract→core 간선 삽입이 현재 고정 계약에서 실패하는 것도 확인했다. 최종 app 파일 집합 지문은 최초 측정과 동일하다.

동적 한계: `globals().get`는 core.py:890,914,2272와 ops_response.py:76에 있다. 현재 import된 모듈을 선택하는 사용으로 검토했지만, 동적 심볼 선택은 import-linter의 심볼 단위 보증이 아니다. Python 파일 안의 모든 문자열 기반 import·패키지 re-export·실행 중 별칭 변경을 일반적으로 증명하지 않는다. 지연 import 포함은 “실제 호출 시 전부 실행된다”는 뜻도 아니다.

미실행: 제품 import/startup, import-linter 엔진, 로컬 제품 시험 전체, Rego/PG/인수·적대 회귀, CI, 솔루션 기기 배포·지정 PC 실험. 따라서 이 보고서는 구조 분석·PR 계약 초안이며 동작 동등성·실기기 성공을 입증하지 않는다. 신규 모듈의 import-time 초기화와 기존 단일 상태 객체 보존이 가장 큰 이행 위험이다.

## 부록 A. 모듈 배치와 이동 영향 실측

단독으로 한 단계 아래 패키지에 옮기며 구 경로를 제거할 때의 수치다. `I`는 app 내 inbound import 문 위치 수, `R`은 옮기는 모듈의 상대 import 문 위치 수, `I∪R`은 둘의 합집합, `E`는 app 밖 Python inbound 문 위치 수다. 모든 수는 `(파일, 시작 행)`으로 중복 제거했다. 같은 문이 여러 모듈을 가져오면 행별 수치를 합산할 수 없다. 심볼만 추출하거나 re-export를 유지하면 실제 수정 수는 달라진다. 셸·compose·문자열 로더는 이 수에서 제외하며 §4에서 별도 다룬다.

`mint.*`는 최종 논리 이름이다. 첫 PR은 `app.*`를 유지하고 하위 모듈부터 추출한다. `core` 행은 최종 주책임이며 등록/정책/원장 함수는 별도 추출한다. 현재 `registry.py`는 패키지와 이름이 겹치므로 `mint.registry` 전환은 초기 PR 범위 밖이다.

| 현재 모듈 / 근거 | 목표 패키지 | LOC | I | R | I∪R | E |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `full_stack_lab/gateway/app/acceptance.py:1` | `mint.testing` | 1347 | 0 | 3 | 3 | 2 |
| `full_stack_lab/gateway/app/activity.py:1` | `mint.control` | 276 | 1 | 2 | 3 | 2 |
| `full_stack_lab/gateway/app/addon.py:1` | `mint.gateway.transport` | 62 | 1 | 2 | 3 | 1 |
| `full_stack_lab/gateway/app/agent_contract.py:1` | `mint.identity` | 200 | 11 | 7 | 18 | 9 |
| `full_stack_lab/gateway/app/agent_service.py:1` | `mint.control` | 2878 | 1 | 19 | 20 | 16 |
| `full_stack_lab/gateway/app/artifact_provenance.py:1` | `mint.control` | 232 | 1 | 0 | 1 | 2 |
| `full_stack_lab/gateway/app/audit.py:1` | `mint.ledger` | 96 | 2 | 3 | 5 | 4 |
| `full_stack_lab/gateway/app/automatic_suspend.py:1` | `mint.gateway.decision` | 78 | 1 | 1 | 2 | 0 |
| `full_stack_lab/gateway/app/classify.py:1` | `mint.gateway.decision` | 1003 | 5 | 1 | 6 | 10 |
| `full_stack_lab/gateway/app/connections.py:1` | `mint.shared` | 31 | 3 | 0 | 3 | 0 |
| `full_stack_lab/gateway/app/connectors.py:1` | `mint.control` | 268 | 3 | 2 | 5 | 0 |
| `full_stack_lab/gateway/app/consent.py:1` | `mint.gateway.decision` | 165 | 3 | 2 | 5 | 2 |
| `full_stack_lab/gateway/app/contract.py:1` | `mint.shared` | 143 | 8 | 0 | 8 | 4 |
| `full_stack_lab/gateway/app/core.py:1` | `mint.gateway.decision` | 2907 | 9 | 9 | 18 | 37 |
| `full_stack_lab/gateway/app/db.py:1` | `mint.shared` | 112 | 46 | 0 | 46 | 28 |
| `full_stack_lab/gateway/app/decommission.py:1` | `mint.control` | 986 | 2 | 7 | 9 | 5 |
| `full_stack_lab/gateway/app/destination.py:1` | `mint.gateway.transport` | 57 | 3 | 0 | 3 | 1 |
| `full_stack_lab/gateway/app/dispatch.py:1` | `mint.gateway.decision` | 206 | 3 | 2 | 5 | 7 |
| `full_stack_lab/gateway/app/disposal.py:1` | `mint.ledger` | 290 | 10 | 3 | 13 | 6 |
| `full_stack_lab/gateway/app/endpoint_plane.py:1` | `mint.endpoint` | 1552 | 17 | 6 | 23 | 19 |
| `full_stack_lab/gateway/app/event_correlation.py:1` | `mint.endpoint` | 42 | 1 | 0 | 1 | 1 |
| `full_stack_lab/gateway/app/experiments.py:1` | `mint.control` | 233 | 1 | 5 | 6 | 1 |
| `full_stack_lab/gateway/app/flow_fingerprint.py:1` | `mint.gateway.decision` | 109 | 1 | 0 | 1 | 2 |
| `full_stack_lab/gateway/app/high_impact.py:1` | `mint.gateway.decision` | 52 | 4 | 0 | 4 | 1 |
| `full_stack_lab/gateway/app/idp.py:1` | `mint.identity` | 388 | 5 | 14 | 19 | 6 |
| `full_stack_lab/gateway/app/incident_pack.py:1` | `mint.control` | 125 | 1 | 0 | 1 | 1 |
| `full_stack_lab/gateway/app/incidents.py:1` | `mint.control` | 285 | 2 | 1 | 3 | 1 |
| `full_stack_lab/gateway/app/intake_proposal.py:1` | `mint.control` | 141 | 2 | 0 | 2 | 3 |
| `full_stack_lab/gateway/app/integrations.py:1` | `mint.control` | 380 | 1 | 5 | 6 | 0 |
| `full_stack_lab/gateway/app/keygen.py:1` | `mint.identity` | 29 | 0 | 0 | 0 | 0 |
| `full_stack_lab/gateway/app/kit_commands.py:1` | `mint.endpoint` | 41 | 1 | 0 | 1 | 0 |
| `full_stack_lab/gateway/app/litellm_sync.py:1` | `mint.control` | 649 | 7 | 6 | 13 | 1 |
| `full_stack_lab/gateway/app/local_jobs.py:1` | `mint.endpoint` | 784 | 16 | 12 | 28 | 6 |
| `full_stack_lab/gateway/app/main.py:1` | `mint.gateway` | 1942 | 0 | 8 | 8 | 7 |
| `full_stack_lab/gateway/app/mcp_facade.py:1` | `mint.gateway.transport` | 294 | 3 | 3 | 6 | 11 |
| `full_stack_lab/gateway/app/mcp_sessions.py:1` | `mint.gateway.transport` | 67 | 9 | 1 | 10 | 2 |
| `full_stack_lab/gateway/app/oidc.py:1` | `mint.identity` | 428 | 5 | 3 | 8 | 2 |
| `full_stack_lab/gateway/app/ops_response.py:1` | `mint.control` | 264 | 4 | 6 | 10 | 4 |
| `full_stack_lab/gateway/app/outcomes.py:1` | `mint.gateway.decision` | 74 | 3 | 0 | 3 | 1 |
| `full_stack_lab/gateway/app/output_contract.py:1` | `mint.gateway.decision` | 97 | 4 | 1 | 5 | 2 |
| `full_stack_lab/gateway/app/pac.py:1` | `mint.policy` | 389 | 6 | 3 | 9 | 6 |
| `full_stack_lab/gateway/app/poisoning.py:1` | `mint.gateway.decision` | 485 | 2 | 1 | 3 | 5 |
| `full_stack_lab/gateway/app/privacy.py:1` | `mint.gateway.decision` | 271 | 3 | 2 | 5 | 6 |
| `full_stack_lab/gateway/app/provenance.py:1` | `mint.control` | 114 | 2 | 0 | 2 | 4 |
| `full_stack_lab/gateway/app/registry.py:1` | `mint.registry` | 315 | 23 | 3 | 26 | 12 |
| `full_stack_lab/gateway/app/release.py:1` | `mint.control` | 94 | 3 | 1 | 4 | 0 |
| `full_stack_lab/gateway/app/replay.py:1` | `mint.policy` | 112 | 0 | 2 | 2 | 1 |
| `full_stack_lab/gateway/app/residency.py:1` | `mint.gateway.decision` | 114 | 5 | 0 | 5 | 5 |
| `full_stack_lab/gateway/app/retention.py:1` | `mint.ledger` | 109 | 3 | 3 | 6 | 2 |
| `full_stack_lab/gateway/app/review.py:1` | `mint.control` | 425 | 15 | 2 | 17 | 12 |
| `full_stack_lab/gateway/app/risk_tier.py:1` | `mint.control` | 171 | 3 | 0 | 3 | 6 |
| `full_stack_lab/gateway/app/sbom_impact.py:1` | `mint.control` | 148 | 1 | 1 | 2 | 1 |
| `full_stack_lab/gateway/app/secret_scan.py:1` | `mint.gateway.decision` | 112 | 4 | 2 | 6 | 8 |
| `full_stack_lab/gateway/app/selective.py:1` | `mint.gateway.decision` | 34 | 2 | 0 | 2 | 1 |
| `full_stack_lab/gateway/app/server_egress.py:1` | `mint.endpoint` | 99 | 1 | 1 | 2 | 0 |
| `full_stack_lab/gateway/app/siem.py:1` | `mint.ledger` | 177 | 1 | 2 | 3 | 4 |
| `full_stack_lab/gateway/app/sse_entry.py:1` | `mint.gateway.transport` | 30 | 0 | 1 | 1 | 0 |
| `full_stack_lab/gateway/app/stdio_entry.py:1` | `mint.gateway.transport` | 15 | 0 | 1 | 1 | 0 |
| `full_stack_lab/gateway/app/supplier_assurance.py:1` | `mint.control` | 144 | 3 | 0 | 3 | 3 |
| `full_stack_lab/gateway/app/system_metrics.py:1` | `mint.control` | 118 | 1 | 0 | 1 | 1 |
| `full_stack_lab/gateway/app/textscan.py:1` | `mint.shared` | 311 | 1 | 0 | 1 | 3 |
| `full_stack_lab/gateway/app/tool_sunset.py:1` | `mint.gateway.decision` | 226 | 3 | 1 | 4 | 2 |
| `full_stack_lab/gateway/app/upstream.py:1` | `mint.gateway.transport` | 506 | 7 | 8 | 15 | 10 |
| `full_stack_lab/gateway/app/upstream_sessions.py:1` | `mint.gateway.transport` | 189 | 2 | 0 | 2 | 0 |
| `full_stack_lab/gateway/app/user_credentials.py:1` | `mint.identity` | 279 | 4 | 1 | 5 | 1 |
| `full_stack_lab/gateway/app/user_suspend.py:1` | `mint.gateway.decision` | 164 | 2 | 1 | 3 | 0 |
| `full_stack_lab/gateway/app/windows_oneclick.py:1` | `mint.endpoint` | 43 | 1 | 0 | 1 | 0 |

`__init__.py`는 패키지 표식으로 위 표에서 제외했다. `mint.snapshot`은 현재 대응 모듈이 없으며 2단계 과제다. `mint.registry`와 `mint.testing`은 제안서 표의 누락 책임을 명시하기 위한 추가 묶음이다. `textscan`은 제안서의 gateway 배치 대신 내부 의존이 없는 공통 검사기로 shared에 둔다. gateway의 입력/출력 검사에서 계속 호출한다.

## 부록 B. 전체 import 인접 목록

E=모듈 실행 시 import(클래스 본문 포함), L=함수/메서드 내부 지연 import. `대상@행` 표기는 같은 대상의 여러 위치를 쉼표로 묶었다. 외부 패키지 import는 제외한다.

| 모듈 | E | L |
| --- | --- | --- |
| `acceptance` | core@43; db@42; registry@42; review@42 | endpoint_plane@759 |
| `activity` | db@12; outcomes@13; review@12 | — |
| `addon` | agent_contract@13; core@12; db@12; review@12 | — |
| `agent_contract` | db@16 | disposal@166; endpoint_plane@192; high_impact@61; oidc@185,189; residency@37 |
| `agent_service` | agent_contract@38; artifact_provenance@34; connections@34; connectors@40; consent@34; core@34; db@34; idp@34,42; intake_proposal@35; integrations@41; local_jobs@35; oidc@34; provenance@34; registry@34; release@36; residency@35; review@34; risk_tier@35; sbom_impact@35; supplier_assurance@35; system_metrics@37; upstream@34; user_credentials@34 | disposal@118,562; endpoint_plane@459,936; kit_commands@501; litellm_sync@116; local_jobs@849,886,936; mcp_sessions@870,902; windows_oneclick@547 |
| `artifact_provenance` | — | — |
| `audit` | db@9; outcomes@10; review@9 | core@85 |
| `automatic_suspend` | db@4; review@4 | — |
| `classify` | registry@32 | — |
| `connections` | — | — |
| `connectors` | agent_contract@18; db@17 | — |
| `consent` | contract@15; db@14; pac@14; registry@14; review@14 | — |
| `contract` | — | — |
| `core` | classify@29; connections@29; consent@29; contract@33; db@29; destination@30; dispatch@29; disposal@29; endpoint_plane@29; flow_fingerprint@32; high_impact@32; intake_proposal@38; litellm_sync@38; local_jobs@29; ops_response@29; outcomes@31; output_contract@32; pac@29; poisoning@29; privacy@29; registry@29; residency@32; retention@29; review@38; risk_tier@29; secret_scan@29; selective@32; supplier_assurance@29; tool_sunset@32; upstream@29; user_credentials@29; user_suspend@29 | endpoint_plane@1773,2319; mcp_sessions@919 |
| `db` | — | — |
| `decommission` | db@40; dispatch@40; disposal@40; registry@40; secret_scan@40; upstream@40; user_credentials@40 | core@476; experiments@556; litellm_sync@281,834; local_jobs@244; mcp_sessions@283 |
| `destination` | — | — |
| `dispatch` | consent@15; contract@16; db@15; high_impact@15 | — |
| `disposal` | — | db@191,214,262 |
| `endpoint_plane` | db@37; event_correlation@38; server_egress@37 | decommission@403; idp@642; local_jobs@629; mcp_sessions@642; pac@868; upstream@642 |
| `event_correlation` | — | — |
| `experiments` | db@35; registry@35; upstream@35 | agent_contract@60,72; idp@81,182 |
| `flow_fingerprint` | — | — |
| `high_impact` | — | — |
| `idp` | agent_contract@34; db@33; disposal@33 | agent_service@99; endpoint_plane@113,186,200,346,375; local_jobs@235,255,279,306; oidc@91,349 |
| `incident_pack` | — | — |
| `incidents` | audit@13; core@13; db@13; incident_pack@13; ops_response@13 | — |
| `intake_proposal` | — | — |
| `integrations` | agent_contract@33; classify@32; connectors@34; db@32; endpoint_plane@35,330; registry@32 | — |
| `keygen` | — | — |
| `kit_commands` | — | — |
| `litellm_sync` | — | db@431,438,449,497,522,600; registry@449,522; review@522 |
| `local_jobs` | db@26 | disposal@576; endpoint_plane@269,588; output_contract@477; pac@251,774; poisoning@70; registry@251,459,489,594,686,774; secret_scan@70 |
| `main` | activity@40; addon@22; agent_contract@38; audit@40; connectors@22; core@22,23; db@22; decommission@22; dispatch@22; disposal@22; endpoint_plane@22; incidents@40; local_jobs@22; mcp_facade@37; ops_response@22; privacy@22; registry@40; release@39; residency@40; retention@40; review@40; risk_tier@40; secret_scan@22; siem@40; supplier_assurance@40; tool_sunset@40; upstream@22; user_suspend@22 | litellm_sync@293,479 |
| `mcp_facade` | agent_contract@33; core@34; db@32; local_jobs@32; output_contract@32; pac@32; registry@32; tool_sunset@32; upstream_sessions@32 | — |
| `mcp_sessions` | db@6 | — |
| `oidc` | agent_contract@22; db@21; destination@23 | — |
| `ops_response` | contract@14; db@13; local_jobs@13; release@13; review@13; selective@15 | disposal@138; incidents@238; litellm_sync@103 |
| `outcomes` | — | — |
| `output_contract` | contract@6 | — |
| `pac` | agent_contract@19; contract@20; db@18; registry@18; residency@18 | — |
| `poisoning` | textscan@42 | — |
| `privacy` | classify@25; connections@24 | — |
| `provenance` | — | — |
| `registry` | contract@32; db@31 | upstream@295 |
| `release` | — | registry@70 |
| `replay` | contract@14; db@13 | — |
| `residency` | — | — |
| `retention` | disposal@13 | db@89,98; review@98 |
| `review` | classify@21; db@20; high_impact@20; provenance@20 | — |
| `risk_tier` | — | — |
| `sbom_impact` | db@7; ops_response@7 | — |
| `secret_scan` | classify@21; privacy@20 | — |
| `selective` | — | — |
| `server_egress` | — | db@87 |
| `siem` | — | db@115,152 |
| `sse_entry` | mcp_facade@14 | — |
| `stdio_entry` | mcp_facade@5 | — |
| `supplier_assurance` | — | — |
| `system_metrics` | — | — |
| `textscan` | — | — |
| `tool_sunset` | db@9; registry@9; retention@9; review@9 | — |
| `upstream` | db@30; destination@31; output_contract@30; registry@30; upstream_sessions@30; user_credentials@30 | local_jobs@395; mcp_sessions@226,232,237,243; registry@300 |
| `upstream_sessions` | — | — |
| `user_credentials` | db@23; review@23 | — |
| `user_suspend` | automatic_suspend@14; db@14; local_jobs@14; review@14 | — |
| `windows_oneclick` | — | — |

## 부록 C. 현재 고정 계약 초안

```ini
[importlinter]
root_package = app

[importlinter:contract:entry-and-leaves]
name = Preserve entry and leaf directions
type = layers
layers =
    app.main
    app.agent_service : app.core
    app.contract : app.db : app.connections : app.destination : app.textscan

[importlinter:contract:leaf-boundary]
name = Leaves have no internal imports
type = forbidden
source_modules =
    app.contract
    app.db
    app.connections
    app.destination
    app.textscan
forbidden_modules =
    app.*
as_packages = False

[importlinter:contract:console-core]
name = Console uses narrow shared helpers
type = forbidden
source_modules =
    app.agent_service
forbidden_modules =
    app.core
allow_indirect_imports = True
ignore_imports =
    app.agent_service -> app.core
unmatched_ignore_imports_alerting = error

[importlinter:contract:core-fanout]
name = Freeze current direct core dependencies
type = forbidden
source_modules =
    app.core
forbidden_modules =
    app.*
as_packages = False
allow_indirect_imports = True
ignore_imports =
    app.core -> app.classify
    app.core -> app.connections
    app.core -> app.consent
    app.core -> app.contract
    app.core -> app.db
    app.core -> app.destination
    app.core -> app.dispatch
    app.core -> app.disposal
    app.core -> app.endpoint_plane
    app.core -> app.flow_fingerprint
    app.core -> app.high_impact
    app.core -> app.intake_proposal
    app.core -> app.litellm_sync
    app.core -> app.local_jobs
    app.core -> app.mcp_sessions
    app.core -> app.ops_response
    app.core -> app.outcomes
    app.core -> app.output_contract
    app.core -> app.pac
    app.core -> app.poisoning
    app.core -> app.privacy
    app.core -> app.registry
    app.core -> app.residency
    app.core -> app.retention
    app.core -> app.review
    app.core -> app.risk_tier
    app.core -> app.secret_scan
    app.core -> app.selective
    app.core -> app.supplier_assurance
    app.core -> app.tool_sunset
    app.core -> app.upstream
    app.core -> app.user_credentials
    app.core -> app.user_suspend
unmatched_ignore_imports_alerting = error
```

## 부록 D. 6쌍 제거 및 콘솔 직접 의존 제거 후 계약 초안

```ini
[importlinter]
root_package = app

[importlinter:contract:entry-and-leaves]
name = Preserve entry and leaf directions
type = layers
layers =
    app.main
    app.agent_service : app.core
    app.contract : app.db : app.connections : app.destination : app.textscan

[importlinter:contract:leaf-boundary]
name = Leaves have no internal imports
type = forbidden
source_modules =
    app.contract
    app.db
    app.connections
    app.destination
    app.textscan
forbidden_modules =
    app.*
as_packages = False

[importlinter:contract:console-core]
name = Console uses narrow shared helpers
type = forbidden
source_modules =
    app.agent_service
forbidden_modules =
    app.core
allow_indirect_imports = True

[importlinter:contract:cut-1]
name = No return edge agent_contract to oidc
type = forbidden
source_modules =
    app.agent_contract
forbidden_modules =
    app.oidc
allow_indirect_imports = True

[importlinter:contract:cut-2]
name = No return edge endpoint_plane to idp
type = forbidden
source_modules =
    app.endpoint_plane
forbidden_modules =
    app.idp
allow_indirect_imports = True

[importlinter:contract:cut-3]
name = No return edge endpoint_plane to local_jobs
type = forbidden
source_modules =
    app.endpoint_plane
forbidden_modules =
    app.local_jobs
allow_indirect_imports = True

[importlinter:contract:cut-4]
name = No return edge idp to agent_service
type = forbidden
source_modules =
    app.idp
forbidden_modules =
    app.agent_service
allow_indirect_imports = True

[importlinter:contract:cut-5]
name = No return edge incidents to ops_response
type = forbidden
source_modules =
    app.incidents
forbidden_modules =
    app.ops_response
allow_indirect_imports = True

[importlinter:contract:cut-6]
name = No return edge registry to upstream
type = forbidden
source_modules =
    app.registry
forbidden_modules =
    app.upstream
allow_indirect_imports = True
```
