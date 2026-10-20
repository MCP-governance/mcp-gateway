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
