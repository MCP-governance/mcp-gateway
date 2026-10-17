# 2026-10-17 upstream-session-reuse-stage2

- 작업자: Codex, 작업 B
- 코드 기준: `9537c0b494a0c4d45c615caa4797674f273d270f`, 시작 시 clean. 현재 워크트리 하나에서만 수정, 브랜치 변경·커밋·푸시 없음.
- 시작 근거: DEV-29 [설계 비교](../../analysis/upstream-session-reuse/README.md), [10-15 보고](2026-10-15-upstream-session-reuse-design.md), D-110, 사용자의 10-17 2단계까지 채택 지시, 지정 결정 D-115.
- 해결할 문제와 완료 조건: 구형 MCP의 주체/대화 결속 세션 재사용과 오류/폐기/기한/경합 처리. 호출별 계약/정책 재확인과 마지막 전송 확인은 유지. 3단계 목록 캐시는 구현하지 않는다. 네트워크 없는 단위 시험을 수행하고 실제 시험을 메인에게 인계한다.

## 결과

### 메인 리뷰 후속 및 A 통합 (10-17)

이 절은 아래 최초 구현 기록을 정정·대체한다. **파일 통합은 수행했으나 실제 Git 병합과 커밋은 권한 문제로 실패했다.**

- 검토 1: foreground `session()`의 `_dispatch_allowed()` 사전 검사를 제거했다. 이 함수는 감시에서 세션 폐기에만 사용한다. 종료/주체/공급망/승인 만료의 판정·감사 정책 ID는 기존 core 정책과 `dispatch.record()` 경로가 결정한다. 실제 session 래퍼를 거쳐 `record='terminated'`인 회귀 시험은 `DispatchRejected(Block/MCP-DECOMM-001)`, 도구 전송 0을 확인했다. 종료 산정 C1~C4/T1~T3와 collect의 판단 조건은 변경하지 않았다.
- 검토 2: 첫 `_sweep()`는 잠금 안에서 `max(id)`를 초기 커서로 잡는다. 모든 dispatch가 세션 생성 전 같은 잠금을 기다려 시작 이전 이벤트가 이후 세션에 적용되지 않는다. 초기화 실패는 새 연결을 거부한다. 동시 초기화 1회/후속 이벤트 적용/폐기 실패 후 커서 유지 회귀를 추가했다.
- 검토 3: `changed.wait()`는 core의 dispatch_budget으로 제한됨을 코드 주석에 명시했다.
- A: 기준 `9537c0b`와 `e53e229`로 파일별 `git merge-file` 3-way 내용을 통합했다. `upstream.py`의 db/registry/upstream_sessions/pin_transport import를 모두 유지하고 `_client(timeout, headers, endpoint, internal)`·`_dispatch_client(..., internal)`·B의 `_session(..., headers, internal)`을 연결했다. `internal = await _internal_endpoint(endpoint)`는 바깥 session에서 계산하고 HTTP/MCP 풀 키에도 반영했다. 해시는 `credential_hash()`로 통일했고 `_dispatch_client`의 sweep은 복원하지 않았다.
- A/B 공통 변경인 main import와 facade의 A 고정 오류 문구/B ContextVar finally 해제도 양쪽 동작을 살렸다. D-115·D-116·D-117, A/B 보고·백로그 내용을 보존했다. 정적 위협 매핑과 코드 증거는 통합된 현재 바이트로 재생성했다.

요청한 Git 작업의 실제 오류:

```text
git add ...
fatal: Unable to create 'C:/Users/bobysg/bob/프로젝트/mcp-gateway-pdf-integration/.git/worktrees/mcp-gateway-codex-b/index.lock': Permission denied
git merge 10/17-dest-transport
fatal: update_ref failed for ref 'ORIG_HEAD': cannot lock ref 'ORIG_HEAD': .../ORIG_HEAD.lock: Permission denied
git commit -m 'fix(v2): preserve dispatch denial evidence and integrate pinned session transport' ...
fatal: Unable to create '.../index.lock': Permission denied
```

브랜치는 `10/17-session-reuse`, HEAD는 여전히 `9537c0b494a0c4d45c615caa4797674f273d270f`다. Git 인덱스/공용 메타데이터는 이 워크트리 밖 읽기 전용 경로여서 쓰기가 거부됐다. 새 커밋 해시는 없으며 merge ancestry도 생기지 않았다. 원격 접속·푸시·다른 워크트리 쓰기·Git 전역 설정 변경은 하지 않았다. 파일 통합에 쓴 임시 파일은 이 워크트리의 git 제외 runtime 안에만 둔다. 쓰기 가능한 메인 환경에서 파일 검토 후 실제 Git 병합/커밋을 마쳐야 한다.

| 병합 후 요청 검사 | 실제 결과 |
| --- | --- |
| `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p upstream_session_reuse_test.py -v` | **40건 통과**. 종료 정책 ID 회귀·시작 커서/동시 초기화·internal 값 전달/교체로 구형 세션 분리 포함 |
| `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p dest_pin_credential_redaction_check.py -v` | **16건 통과** |
| `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p dest_pin_transport_check.py -v` | **2건 skip**: httpx/httpx2 제품 의존성 필요, 사용자 skip 허용 범위 |
| `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p mcp_result_contract_check.py -v` | **실패(exit 1)**: import 단계 `ModuleNotFoundError: No module named 'mcp'`, 시험 본문 미실행 |
| `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 무인증 1개·인증 70개(장치 8개) |
| `git diff --check` | 통과 |

추가 변경 파일은 A 커밋의 전체 24개 경로(추가/수정)를 포함한다. 특히 `destination.py`, `decommission.py`, `experiments.py`, `oidc.py`, `secret_scan.py`, 정책 원장, A의 두 시험과 분석/보고, `PAC_MAPPING.md`, 매핑 생성기를 기존 B 변경과 함께 보존했다. 실제 SDK/DB·TLS·배포·종료 수집기/PJ1 실기기 검증은 여전히 미실행이다. 원본 명령 출력과 exit code는 [통합 검증 기록](../../analysis/upstream-session-reuse/review-integration-validation.json)에 남겼다. 최초 보고의 34건 수치·처음부터 과거 이벤트를 재생하던 설계·A 미통합 표기는 이 후속 절로 대체한다.

**로컬 구현과 단위 시험까지 반영했다. 배포·제품 SDK 실행·DB·실제 MCP/모델/실기기 효과 검증은 미실행이다. 위키 전체 검사는 실패 상태다.**

- `upstream_sessions.py`로 풀/소유 태스크/대기 직렬화/유휴 60초·최대 600초/전체 상한/폐기/오류 수명을 분리했다. 같은 키는 1개 세션을 직렬 사용한다. 설계 제안의 키당 최대 4개는 상태가 갈라지므로 더 엄격한 1개를 채택했다.
- 키는 `(주체, (다운스트림 세션, 검증한 jti), 서버, 운영자 자격 해시, endpoint, 승인 프로토콜 판, timeout)`이다. 추가 요소별 근거와 권한을 키에 저장하지 않는 이유는 [원자 요구/시험 대응](../../analysis/upstream-session-reuse/stage2.md)에 있다. 바인딩은 facade가 전송 신원 확인 후 ContextVar로 설정하며 요청 본문/감사 client/저장된 승인 payload로 복원하지 않는다.
- 신형 규격 `2026-07-28`, 미확인 판, 다운스트림 세션/`jti` 없음, 메타데이터 조회, Console 승인 재실행은 MCP 세션을 재사용하지 않는다. 직원 토큰을 업스트림으로 보내지 않는 운영자 자격 경로는 유지했다.
- `Client(cache=None)`과 모든 `tools/list` 페이지의 `cache_mode="bypass"`를 함께 적용했다. `list`→계약/인자→개별 승인→주체/관리형 장치→OPA→`dispatch.record`→도구 호출 순서를 유지한다.
- 기존 주체 중지/서버 종료 `release_pool`에 세션 폐기를 연결하고 등록 교체/해제·계약 드리프트/재승인·승인 요청 거부·재확인 실패도 폐기한다. 자격은 대여와 SDK 요청 직전에 다시 읽는다. 다운스트림 DELETE 성공은 해당 대화만 폐기하고 해시 신호를 프로세스에 전파한다.
- 무호출 상태에도 2초 간격 감시가 이벤트·주체/등록/도입 승인/기한·자격·세션 수명을 확인한다. 최초 이벤트 건너뛰기와 폐기 실패 전에 커서를 전진시키던 동작을 제거했다. 시작 중 폐기·대기 중 중지·자격 교체/유휴 축출 정리 중 중지에서도 새 세션을 열지 않도록 했다.
- 목록 단계의 SDK 세션 404만 한 번 재연결한다. 도구 실행 뒤 오류는 재시도하지 않고 기존 `upstream_attempted`/실행 여부 불명 처리를 유지한다. 도구 오류 응답도 세션을 폐기하되 이미 받은 응답은 확정 결과로 반환한다.
- `D-115`를 기록하고 D-79 세션 부분, D-110 후속 상태, 정본 아키텍처/시험 안내, DEV-29 백로그를 갱신했다. `status/current.md`는 지시대로 변경하지 않았다. 시간 구간명/숫자 형식은 그대로라 콘솔·`/api/latency` 변경은 없고, 재사용은 감사 `client.upstream_session_reused`로 구분한다.

### 바꾼 파일

| 파일 | 변경 |
| --- | --- |
| `full_stack_lab/gateway/app/upstream_sessions.py` (신규) | 세션 키·수명·소유 태스크·직렬 대여·폐기 |
| `full_stack_lab/gateway/app/upstream.py` | 풀 연결·감시·이벤트·자격/등록 확인·캐시 우회·세션 404 판별 |
| `full_stack_lab/gateway/app/core.py` | 서버/승인 변경 시 폐기·서버 ID 전달·재사용 감사 표식·목록 단계 제한 재연결 |
| `full_stack_lab/gateway/app/mcp_facade.py` | 검증 신원/구형 대화 ContextVar 바인딩과 해제 |
| `full_stack_lab/gateway/app/main.py` | DELETE 성공 시 대화 폐기·감시 태스크 수명/종료 |
| `full_stack_lab/tests/upstream_session_reuse_test.py` (신규) | 순수 단위 시험 34건, SDK/DB/OPA 대역 |
| `full_stack_lab/tests/mcp_result_contract_check.py` | 기존 페이지 대역의 bypass 인자/검증 정합 |
| `docs/ai/DECISIONS.md`, `ARCHITECTURE.md`, `TESTING.md` | D-115·D-79 개정·현재 동작/검증 경계 |
| `research/llm-wiki/analysis/upstream-session-reuse/README.md`, `stage2.md`, `code-evidence.json` | 비교 이력 보존·원자 요구/코드/시험/기기 목록·심볼/행/판본/해시 |
| `research/llm-wiki/status/backlog.md`, 이 보고서 | DEV-29의 로컬 구현/미검증 상태 |
| `research/llm-wiki/catalogs/threats.json`, `threats/control-map.md` | 기존 정적 후보 매핑의 현재 해시 재생성, HEAD 해시/미검증 표기 유지 |
| `research/llm-wiki/status/repository-snapshot.json`, `repository-snapshot.md` | 규칙의 로컬 코드/워킹 트리 스냅샷 재생성 |

코드 심볼·행·SHA-256은 [code-evidence.json](../../analysis/upstream-session-reuse/code-evidence.json)에 정본으로 남겼다.
종료 판정 C1~C4/T1~T3 규칙, 감사 append-only, 전송 신원/직원 토큰 비전달 경계는 변경하지 않았다.

## 검증

2026-10-17, 이 Windows 노트북의 Python 3.10/Node에서 실행했다. 제품 스택·네트워크 서버를 띄우지 않았다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수 단위 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p upstream_session_reuse_test.py -v` | **34건 통과**, 약 0.7초. 실제 풀과 선택한 제품 함수 본문/대역 SDK·DB·OPA | 명령 출력, [시험 파일](../../../../full_stack_lab/tests/upstream_session_reuse_test.py) |
| 구문 | `python -X utf8 -c "import ast; from pathlib import Path; [ast.parse(p.read_text(encoding='utf-8')) for p in Path('full_stack_lab/gateway/app').glob('*.py')]; print('syntax OK')"` | 통과. 변경 7개 Python 파일은 코드 증거 생성 때도 AST 파싱 | 명령 출력·code-evidence.json |
| 정적 분석 | `python -m pyflakes full_stack_lab/gateway/app/upstream.py full_stack_lab/gateway/app/upstream_sessions.py full_stack_lab/gateway/app/core.py full_stack_lab/gateway/app/main.py full_stack_lab/gateway/app/mcp_facade.py full_stack_lab/tests/upstream_session_reuse_test.py full_stack_lab/tests/mcp_result_contract_check.py` | **미실행**: 실행 시도했으나 `No module named pyflakes` | 명령 출력 |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | exit 0 |
| 콘솔 단위 | `node --test full_stack_lab/tests/console-state.test.mjs` | **15건 통과** | Node TAP 출력 |
| 공개 API 정적 | `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 무인증 1개·인증 70개(장치 8개) 문서 일치 | 명령 출력 |
| 차이 형식 | `git diff --check` | 통과 | exit 0 |
| 위키 목록 | `python -B -X utf8 research/llm-wiki/tools/build_wiki.py` | 목록 생성 통과, 웹/코드 생성 없음 | JSON 출력 |
| 정적 매핑 | `python -B -X utf8 research/llm-wiki/tools/map_threats.py` | 24개 정적 후보 매핑 재생성. 현재/HEAD 해시를 따로 보존, runtime 검증은 pending 그대로 | 생성 출력·catalogs/threats.json |
| 위키 전체 | `python -B -X utf8 research/llm-wiki/tools/check_wiki.py` | **실패**: 별도 보관 `local-sources/compliance/*/provenance.json` 29건 없음. 처음 발견한 core/upstream 매핑 hash 차이 11건은 정적 매핑 재생성 후 해소, 새 보고/증거 링크 오류 없음 | 검사 JSON 출력 |
| 로컬 스냅샷 | `python -B -X utf8 research/llm-wiki/tools/capture_status.py` | 재생성, 배포/활성화 증거 아님 | repository-snapshot.json/md |
| 원격 기준 확인 | `git ls-remote --symref origin HEAD` | 실패: 이 샌드박스에서 GitHub 443 접속 불가. 브랜치 변경 없음 | 명령 출력 |
| 고정 SDK 소스 | `git -c safe.directory=C:/Users/bobysg/bob/프로젝트/ref-src/mcp-python-sdk -C ../ref-src/mcp-python-sdk rev-parse HEAD`, 소스·LICENSE 읽기 | `9972c21aa42054fb1450c5fc614761ed11847ec6`, MIT. 전역 설정 변경 없음 | 명령 출력, [근거](../../analysis/upstream-session-reuse/stage2.md#근거와-통합-주의) |
| 프로토콜 | 실제 SDK 2.2.0·기존 `mcp_result_contract_check.py`/`protocol_versions_check.py`, 실제 MCP | **미실행**: 로컬에 mcp/httpx2/제품 의존성 없음 | — |
| 실제 모델·하네스 | PJ1·pj3 | **미실행**, 접속하지 않음 | — |
| upstream 효과 | 공개 OSS MCP의 상태/쓰기·수신 헤더 | **미확인** | — |
| 배포·정책 해시 | 솔루션 기기·compose·OPA | **미실행**, 기기 접속/스택 기동/정책 변경 없음 | — |

## 실패·미완료·한계

- 전체 위키 검사는 실패다. 별도 보관 원문 29건은 이 워크트리에 없다. 기존 위협 매핑은 정적 후보임을 검토하고 재생성해 코드 해시 차이 11건을 해소했으며, 과거 시험 해시/실행 결과는 새 통과 근거로 덮어쓰지 않았다. 메인이 원문 경로를 갖춘 환경에서 재검사해야 한다.
- SDK/DB가 설치되지 않아 단위 시험은 실제 제품 모듈 전체 import가 아닌 순수 풀 + 선택한 제품 함수 AST 본문/대역을 실행한다. 실제 SDK의 AnyIO·SQL·취소/DELETE·프로세스 간 전파는 통과했다고 주장하지 않는다. `pyflakes`도 메인 환경에서 실행해야 한다.
- 같은 키 직렬화는 한 대화 상태를 보존하지만 병렬 호출의 대기 지연을 늘린다. 폐기와 겹친 다른 키의 대기 호출도 세대 보호로 거부될 수 있다. 시간 예산/전체 상한/대기 부하는 실제 SDK에서 검수한다.
- 논리 폐기는 즉시지만 이미 전송된 호출은 되돌리지 못한다. 다른 프로세스/자격 파일 변경은 감시 또는 다음 대여/전송 전 검사에서 관찰한다. 2초는 감시 간격이며 DB/종료 응답이 늦을 때의 실제 상한은 미검증이다. 폐기 중 서버 세션/transport는 정리 완료 전까지 남을 수 있다. 서비스 자격 회수를 증명하지 않는다.
- `jti`가 바뀌면 같은 대화라도 새 키다. 하네스 토큰 refresh 때 탭 상태가 이어지지 않을 수 있다. Console 승인 후 재실행은 원래 대화 바인딩을 복원하지 않아 새 세션으로 실행한다.
- D-110의 현재 코드는 승인 판 변경 시 실패 후 카탈로그 재검토다. 설계 당시 T12의 자동 `auto` 1회 복구 제안은 이번 범위에 추가하지 않았다. T12 전체 성공으로 올리지 않는다. T8은 3단계 미채택으로 제외다.
- 목적지 DNS/IP 고정은 작업 A 범위다. 충돌 후보는 `upstream.py` import, `_dispatch_client`의 sweep 이동, 기존 `session`→`_session` 분리와 `Client(cache=None)`. `_client`/`streamable_http_client`의 transport 생성 인자는 바꾸지 않았다. A가 고친 transport를 `_session` 안에 보존해야 하며 재사용 연결의 DNS/IP 수명은 통합 검토가 필요하다.

## 다음 작업

DEV-29의 상세 [T1–T12 기기 시험 목록](../../analysis/upstream-session-reuse/stage2.md#기기에서-메인이-실행할-t1t12)을 메인이 실행한다.

1. 제품 Python/SDK 환경에서 pyflakes, 기존 SDK 결과/프로토콜 시험을 먼저 실행하고 A의 transport 변경과 통합 검토한다.
2. 솔루션 기기에서만 `field up` 배포. 사람이 이미 승인한 구형 OSS MCP로 T1 연속 20회, T2·T3 주체/대화 탭 분리·상태 유지, 실제 헤더/원장/효과 확인. Gitea 신형은 비재사용 대조군이다.
3. T4·T5 주체 중지/서버 종료/승인 철회/등록 해제/기한 만료 경합, T6 공급자 자격 회전/제거, T7 TTL/페이지 이후 계약 변경 차단, T9 동일 키 10호출/다른 키 병렬/상한을 실행한다.
4. T10 목록/실행 단계 OSS 재시작·응답 유실·DELETE 미지원·정리 취소의 복구/실행 여부 불명과 부작용 0/중복 0을 확인한다. T11 2프로세스 신호·유휴 폐기·실측 지연, T12 판 변경 실패/재검토 후 복구를 확인한다. T8은 실행하지 않는다.
5. PJ1 실제 관리 하네스로 GitHub·Context7 지연을 원장 `timings`·재사용 표식·`GET /api/latency`와 비교한다. 실제 다운스트림 판/세션 ID/`jti`를 기록해 비재사용 fallback을 재사용 성공으로 세지 않는다. 기존 C1~C4/T1~T3 종료 회귀도 수행한다.
6. 통합 뒤 정적 위협 매핑을 다시 생성하고 원문이 있는 환경에서 위키 검사를 실행한 뒤 `status/current.md`를 메인이 갱신한다.

## 사용자에게 필요한 입력

없음. 기기·격리 계정·승인 대상·실제 하네스 시험은 메인이 기존 권한 범위에서 수행한다. 자격증명 값은 보고서에 남기지 않았다.
