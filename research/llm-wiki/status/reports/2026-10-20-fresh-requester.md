# 2026-10-20 DEV-17 승인 실행 시 저장 요청자 토큰의 현재 유효성 재검증

- 작업자: Codex sol
- 코드 기준: `10/20-fresh-requester`, `554307444dfc8dcb91c281c1a282427ee83e2efc`. 시작 시 D-152·DEV-17 백로그·분석·이 보고서의 조사 초안이 미커밋 상태였고 이를 이어서 수정했다.
- 변경 파일: `full_stack_lab/gateway/app/core.py`, 새 `full_stack_lab/tests/fresh_requester_check.py`, `docs/ai/DECISIONS.md`의 D-152, [분석 정본](../../analysis/fresh-requester-d152/README.md), 이 보고서, `status/backlog.md` DEV-17의 마지막 상태 칸.
- 시작 근거: DEV-17, 소유자의 범위 축소 지시, D-140의 최종 dispatch 검사, authenticated_user의 기존 철회 검사, 앞선 D-152 조사.
- 해결할 문제와 완료 조건: 승인 즉시 실행 UX를 유지하면서 실행 직전에 저장 요청자 jti의 현재 철회·폐기를 확인하고 기존 만료·장치·주체 검사를 유지한다. 차단 시 도구를 실행하지 않고 원장 경로에 판정을 추가한다. 로컬 구현·단위 검증까지 수행했으며 기기 검수는 미실행이다.

## 결과

`core._call_upstream`의 도구 탐색·승인 유효성 확인 뒤에 13줄을 추가했다. 저장 transport_claims의 jti로 authenticated_user와 같은 `disposal.blocked` 및 `agent_revoked_tokens` 조회를 실행한다. DB 철회·서명 폐기 목록 차단은 기존 `P-INPUT-001`, 예상 밖 조회 예외는 `P-CONTROL-FAIL-CLOSED`다. disposal.blocked가 서명/파일 무결성·읽기 실패를 true로 돌려주는 기존 동작도 그대로 차단한다. intent 생성·tools/call 전에 멈추고 기존 DispatchRejected → execute_call → _decision_payload 경로가 차단 판정을 append한다. 승인 상태는 실행 전 차단이면 NOT_EXECUTED가 된다.

뒤이어 실행되는 managed_failure·PAC/OPA와 기존 D-140 dispatch.record의 활성 주체·권한·동의·서버·흐름·승인 소비 확인은 그대로다. 저장 device_id의 현재 상태·소유자·epoch·정책·heartbeat를 재확인한다. PAC의 `nbf <= now < exp`를 완화하지 않아 원 토큰이 먼저 만료되면 실행할 수 없다. approve_request의 즉시 execute_call 호출, 원 요청 payload·원장 보존, 직원 토큰 미전달을 유지했다.

새 시험은 실제 승인→실행→전송 직전 검사→원장 호출 함수를 AST로 읽어 실행하며 DB/HTTP만 대역 처리한다. 정상에서는 승인만으로 즉시 도구 1회 호출, 철회/격리/중지/만료/검사 실패에서는 도구·intent 0회, decision와 policy_id, 원장 함수 호출과 요청자·승인 연결, NOT_EXECUTED/EXECUTED 상태 및 저장 payload 불변을 확인한다. 실제 MCP 서버를 새로 만들지 않았다.

정책 ID·OPA·DB 스키마·라우트·콘솔·기존 시험·status/current.md는 변경하지 않았다. 커밋·푸시·배포·로컬 스택 기동은 하지 않았다. 새 의존성은 없고 기존 함수·철회 SQL·PAC를 재사용했다. 로컬 ponytail 스킬(MIT)은 최소 변경 검토에만 적용했다. 외부 공개 OSS/SDK·스킬 신규 도입·실행은 없다.

## 이전 조사와 대체 관계

앞선 초안은 요청자 재시도 모델로 해석해 기존 high_impact_check·acceptance·dispatch_effect_lab의 승인 즉시 실행 기대값과 충돌하므로 구현을 중단했다. 소유자가 이번에 UX 유지와 저장 토큰 재검증으로 범위를 확정했으므로 **그 중단 판단을 이번 범위에 한해 대체**한다. 이전 호출 경로·새 jti/PAC digest·다른 장치 결속 분석은 [분석 정본의 이전 조사 이력](../../analysis/fresh-requester-d152/README.md)에 보존했다.

## 기존 시험 변경 필요

없음. 세 기존 파일의 기대값·내용을 그대로 보존했다. 요청자 재시도 모델로 바꾸는 다음 단계에서는 즉시 실행 기대값과 UX를 별도 결정해야 하지만 이번 구현의 선행 조건은 아니다.

## 검증

실행 환경: Windows, Python 3.10.5, Node v24.21.0, 2026-10-20 KST. 스택 없이 실행했다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 새 순수/대역 단위 | `python -B -X utf8 full_stack_lab/tests/fresh_requester_check.py` | 9통과. 승인 후 jti 철회·파일 폐기·장치 격리·주체 중지·기존/탐색 중 만료·철회 DB/파일 예외·정상 즉시 실행 | 해당 시험과 터미널 출력, 종료 0 |
| 기존 승인 단위 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p high_impact_check.py -v` | 17통과·이미지 전용 7생략. 즉시 실행 기대 시험 유지 | 터미널 출력, 종료 0 |
| 기존 최종 dispatch 검사 | `python -B -X utf8 full_stack_lab/tests/dispatch_recheck_check.py` | 15통과. AsyncMock/잠금 대역이며 실제 PostgreSQL 시험 아님 | 터미널 출력, 종료 0 |
| Python 구문 | `python -m py_compile full_stack_lab/gateway/app/core.py full_stack_lab/tests/fresh_requester_check.py` | 통과 | 터미널 출력 없음 |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 터미널 출력 없음 |
| 게이트웨이 직접 import 시도 | `python -B -X utf8 full_stack_lab/tests/fresh_requester_check.py --gateway` | 실행 불가. 로컬 Python 3.10에서 core.py의 datetime.UTC import 실패, 시험 통과로 세지 않음 | ImportError 터미널 출력 |
| 원격 HEAD 재조회 | `git ls-remote --symref origin HEAD` | 실패. github.com:443 연결 불가 | fatal 터미널 출력 |
| 문서·변경 범위 | `git diff --check` 및 Python 표준 라이브러리로 UTF-8/BOM/LF·상대 링크·HEAD 대조 | 통과. DEV-17 상태 칸만 변경, 기존 시험 3파일·current.md·agent_contract.py 보존, 기존 DECISIONS 본문 보존 확인 | 터미널 출력과 Git diff |

초기 새 시험 실행에서는 합성 scope에 datetime을 넣어 canonical_hash가 실패했다(1통과·8오류). 새 시험 fixture만 ISO 문자열로 고친 뒤 위 9건이 통과했다. 제품·기존 시험 기대값은 바꾸지 않았다.

## 실패·미완료·한계

새 요청자 로그인이나 JWT 재서명 검증을 하는 기능이 아니다. ingress가 이미 검증해 저장한 claims의 현재 상태를 재검사한다. 원 jti·저장 payload는 교체하지 않는다. 요청자 재시도 모델, 다른 장치의 새 토큰과 승인 결속, 새 jti와 원 PAC digest 분리는 미구현·결정 필요다.

만료 시험은 실제 pac.build의 auth.verified와 시간 경계를 확인하고 OPA HTTP 대역으로 PAC-04 차단을 반환한다. 실제 OPA가 여러 실패 중 어느 정책을 우선 선택하는지는 검증하지 않았다. 서명 파일 검사 자체와 DB 복원·실제 원장 append/체인·잠금/동시성·게이트웨이 이미지 import·프로토콜·PJ1 하네스·독립 upstream 효과·배포·정책 해시는 미검증이다. 최종 상태 조회와 intent 커밋/실제 송신 사이의 경쟁 간격은 남는다.

## 다음 작업

DEV-17 기기 검수: 사람이 솔루션 기기에서 변경 제품이 들어간 게이트웨이 이미지와 `/tests` 마운트를 준비한 뒤 다음을 실행한다. 기본 compose에는 시험 마운트가 없으므로 아래 명령은 그 이미지 내부 기준이다. 이 노트북에서는 실행하지 않는다.

```bash
python /tests/fresh_requester_check.py --gateway
python /tests/high_impact_check.py --gateway
python /tests/dispatch_recheck_check.py
```

이어 실제 PostgreSQL과 서명 폐기 목록에서 승인 후 철회·격리·중지·만료를 재현하고 Block 원장과 upstream 효과 0, 정상 승인 즉시 1회 실행을 확인한다. 제품 배포는 솔루션 기기의 `full_stack_lab`에서 `./console.sh field up`, 실제 기능 확인은 PJ1 하네스로 수행한다. 기존 acceptance/dispatch_effect_lab의 실제 MCP 회귀도 사람이 실행하며 이 보고서에서 통과로 세지 않는다.

## 사용자에게 필요한 입력

없음. 기존 기기 환경에서 수행할 검증만 남았다.

## 기존 시험 대역 보정

- 작업자·기준: Codex sol, 2026-10-20, `10/20-fresh-requester`, HEAD `e19cabaf6570378ff8faf26e382d77d7bbb0a584`(S9b). 이번 후속 작업 시작 시 미커밋 변경 없음. 커밋·푸시 없음. 원격 HEAD 재조회는 github.com:443 연결 실패다.
- 문제·완료 조건: `upstream_session_reuse_test.py`의 AST 추출은 모듈 import를 하지 않아 S9b가 사용하는 `disposal`이 없다. 기존 `fetch_one`은 승인 이외 모든 SQL에 활성 주체 행을 반환해 철회 조회에도 truthy를 반환한다. 기존 assert를 보존하고 대역·입력 fixture만 보강해 원래 세션/재시도 경로를 시험한다.
- 결과: 아래 네 줄만 추가/교체했다(행은 보정 후 파일 기준). 제품 코드 수정은 불필요했다. `core.py`, C9 제품/시험 파일, 다른 기존 시험, `status/current.md`는 HEAD와 바이트 단위로 같다. 위의 “기존 시험·내용을 그대로 보존” 기록은 S9b 당시 결과이며, 이번 후속에서 이 파일의 대역 보정에 한해 대체한다. **기존 시험 기대값 변경 필요: 없음.**

| 변경 행 — `full_stack_lab/tests/upstream_session_reuse_test.py` | 바꾼 내용 | 줄별 이유 |
| --- | --- | --- |
| 557(추가) | `if "agent_revoked_tokens" in sql:` | 철회 표 조회를 기존 활성 주체 기본 응답과 구분한다. 실제 `_call_upstream`이 쓰는 SQL의 테이블명만 판별한다. |
| 558(추가) | `return None` | 정상 세션 fixture에는 철회 행이 없다는 DB 응답을 명시한다. 활성 주체 dict 때문에 잘못된 철회로 판정되는 것을 막는다. |
| 580(추가) | `"disposal": NS(blocked=lambda **kwargs: False),` | AST 이름공간에 기존 모듈 의존성을 제공한다. 정상 서명 목록에서 요청자가 폐기되지 않은 상태를 모델링하며 실제 폐기 저장소를 읽거나 초기화하지 않는다. |
| 600(기존 597행 교체) | `pac_payload`에 `transport_claims.jti="unit-requester"` 추가 | 인증 ingress가 저장한 요청자 jti가 있는 정상 입력을 제공한다. 인자·사용자 헤더로 제품 신원을 정하는 변경은 아니다. 기존 `arguments`, 호출 대상·승인 ID·assert를 유지한다. |

정상 응답 대역이 보안을 우회하는 제품 코드가 되지 않도록, 별도 `fresh_requester_check.py`의 파일 폐기·DB 철회·조회 장애 등 음성 경로 9건을 다시 실행했다. 기존 시험 파일의 assert/단언 호출 AST **120개가 HEAD와 모두 동일**함을 확인했다. `test_T10_*`의 최초 `ValueError("expired")`는 의도한 탐색 재시도 입력이며, 수정 전에는 재시도 뒤 누락된 철회 대역에서 멈춘 것이었다. 예외 처리·재시도 횟수·기존 정책 기대값은 바꾸지 않았다.

### 후속 검증

Windows Python 3.10.5, 2026-10-20, 로컬 스택 없이 실행했다. 아래 표는 이번에 실행한 결과다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 수정 전 회귀 재현 | `python -B -X utf8 full_stack_lab/tests/upstream_session_reuse_test.py` | 40건 중 35통과·2실패·3오류. 승인 경로가 `Requester revocation check unavailable` / `P-CONTROL-FAIL-CLOSED`로 중단 | 이번 터미널 traceback, 종료 1 |
| 보정 후 기존 회귀 | 같은 명령 | **40통과**, `test_T10_*`, `test_T4_*`, 종료 정책 유지 포함 | 이번 터미널 출력 `Ran 40 tests` / `OK`, 종료 0 |
| 요청자 재검사 | `python -B -X utf8 full_stack_lab/tests/fresh_requester_check.py` | **9통과**, 정상·철회·폐기·장치·주체·만료·조회 실패 경로 | 이번 터미널 출력, 종료 0 |
| 최종 dispatch | `python -B -X utf8 full_stack_lab/tests/dispatch_recheck_check.py` | **15통과** | 이번 터미널 출력, 종료 0 |
| 승인 회귀 | `python -B -X utf8 -m unittest discover -s full_stack_lab/tests -p high_impact_check.py -v` | **17통과·이미지 전용 7생략** | 이번 터미널 출력, 종료 0 |
| Python 구문 | `python -m py_compile full_stack_lab/tests/upstream_session_reuse_test.py full_stack_lab/gateway/app/core.py full_stack_lab/tests/fresh_requester_check.py` | 통과 | 이번 터미널 출력 없음, 종료 0 |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 이번 터미널 출력 없음, 종료 0 |
| 기대값·범위 | 표준 라이브러리 `ast`·`subprocess`로 HEAD 대조 | 단언 AST 120개 동일, 제품/C9/current.md 바이트 동일 | 이번 터미널 `PASS` |
| 문서·인코딩 | `git diff --check`, 표준 라이브러리로 UTF-8/BOM/LF·추가 링크·기존 문서 접두/백로그 칸 대조 | 변경 5파일 UTF-8(BOM 없음)·LF, 추가 파일 링크 정상, 기존 보고/결정 내용 보존, DEV-17 마지막 칸만 수정 | 이번 터미널 `PASS`, 종료 0 |
| 위키 전체 | `python -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | **실패**, 매핑 해시 불일치 24건·기존 깨진 링크 3건, 원본 미보유 경고 119건. 대상 제품 코드와 링크 출처 문서는 HEAD와 동일함을 확인했다 | 이번 터미널 JSON `ok:false`, 종료 1 |

합계 로컬 단위 81통과·7생략이다. 게이트웨이 이미지 import·실제 DB/서명 파일·기기 배포·PJ1·독립 upstream 효과는 미실행이다. 정상 입력 대역은 실제 인증 검증/파일 무결성의 증거가 아니다. Codex luna의 적대 검증은 이 작업에서 수행하지 않았으며 검토 대기다. 새 정책·DB·라우트·의존성·mock MCP는 없다.

위키 실패의 링크 3건은 기존 D-150 분석의 미보유 `launcher_pin_adversarial_check.py`와 기존 S7 보고의 `../analysis/...` 상대 경로 2건이다(후자는 실제 파일이 있지만 보고서 기준 경로가 틀림). 이를 이번 신규 문서의 오류로 세거나 전체 검사를 통과로 보고하지 않는다. 작업 범위 밖 문서·매핑을 수정하거나 재생성하지 않았다.

### C9 읽기 전용 검토와 결정 연결

[C9/D-154 정본](../../analysis/review-1020/c9-d154.md)에 시험 변경 두 건을 각각 **A(목록 격리 채택)**, **B(401/403 확대는 수정 후 채택)**로 판정했다. `git show claude/c9`의 커밋은 `5a8bcc18af6934aecea2fc836abf752da52d8e33`이다. 후보 파일은 수정하지 않았다. HEAD/후보 `token` AST와 메모리 DB/파일 대역으로 정상·발급 예외·기록 예외의 6조건을 실행해 순서를 대조했다. 실제 DB 복원이 아닌 메모리 상태 복원에서, 후보의 커밋 후 기록 누락 뒤 회전 전 상태로 돌아가면 옛 토큰의 첫 재사용이 발급에 성공했다. 상세 관측값·해시·복원/경쟁/계정·장치 비대칭 한계는 정본에 기록했다. 후보의 22/22 보고는 여기서 재현하지 않았다.

결정은 `docs/ai/DECISIONS.md` 끝의 D-152 후속·D-154 후보 적대 검토에 연결했다. DEV-17 백로그의 마지막 상태 칸만 갱신했다. 상태 생성기·위키 생성기는 실행하지 않아 `current.md`나 파생 파일을 변경하지 않았다.

### 기기 후속 명령·한계

사람이 변경된 게이트웨이 이미지와 `/tests` 마운트를 준비한 뒤 이미지 내부에서 실행한다. 기본 compose의 시험 마운트 부재는 앞선 보고와 같다.

```bash
python /tests/upstream_session_reuse_test.py
python /tests/fresh_requester_check.py --gateway
python /tests/high_impact_check.py --gateway
python /tests/dispatch_recheck_check.py
```

C9는 후보 및 B 판정 수정이 들어간 별도 검토 트리에서 격리 실험실 준비 상태를 확인한 뒤 `cd full_stack_lab` → `tests/termination_dispatch_lab.sh run token_revocation_pg_check.py`를 실행한다. 이번 트리에는 D-154를 병합하지 않았으므로 이 명령의 후보 검증 성공을 주장하지 않는다. 기록 예외·프로세스 장애·감시 전 DB 복원·다중 워커 경쟁의 추가 신규 검증은 남아 있다. 다른 작업자의 실험실을 재시작하거나 종료하지 않았다.
