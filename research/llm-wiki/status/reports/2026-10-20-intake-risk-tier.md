# 2026-10-20 DEV-71 도입 신청의 위험 등급과 영향평가 입력 패키지

- 작업자: Claude Sonnet
- 코드 기준: 시작 commit `48eda39`(main), 브랜치 `10/20-intake-risk-tier`, 시작 시 clean. 변경 파일은 아래와 같다.
  - 새 파일: `full_stack_lab/gateway/app/risk_tier.py`, `full_stack_lab/tests/intake_risk_tier_check.py`
  - 수정: `full_stack_lab/gateway/app/agent_service.py`, `core.py`, `main.py`, `v2_tables.sql`, `agent_static/console.js`, `docs/ai/DECISIONS.md`(D-143), `docs/ai/POLICY.md`, `docs/ai/DATA_MODEL.md`, 이 보고서, `status/backlog.md`의 DEV-71 마지막 칸
- 시작 근거: DEV-71, [규제 근거 개발 계획](../../analysis/compliance/dev-plan/README.md) 2장(DEV-71 범위·수용 기준)·CAP-6·RQ-08, 관련 DEV-68(D-137). POL-02·27.
- 해결할 문제와 완료 조건: 동일 입력이 항상 같은 등급이 되고, 등급별 승인 방식이 적용되며, 필수 입력이 없으면 도입이 보류된다. 평가의 수행과 판단은 사람이 한다.

## 결과

구현·로컬 정적 검사·일회성 컨테이너 단위 시험까지 했다. 솔루션 기기 배포와 PJ1 확인은 하지 않았다.

- **입력**: 도입 신청 양식(`POST /api/mcp-requests`의 `risk_input`)이 데이터 등급, 처리 개인정보, 외부 전송, 실행 권한(r/w/x), 예상 사용자 수, 자율성 여섯 가지를 받는다. `mcp_intake_requests.risk_input`(jsonb, `v2_tables.sql` 끝의 `ADD COLUMN IF NOT EXISTS`)에만 저장하고 등급은 저장하지 않는다. 신청 API는 이전 클라이언트를 위해 입력을 생략할 수 있고, 일부만 보내면 422다.
- **등급 산정**: `risk_tier.assess`는 외부 상태가 없는 순수 함수다. 항목별 점수 합을 낮음(0~3)·보통(4~7)·높음(8~11)·매우 높음(12~)으로 옮기고, 합과 무관한 최소 등급 규칙 세 개(민감정보 외부 전송 → 매우 높음, 중요 데이터 외부 전송·실행 권한 자율 실행 → 높음)를 얹는다. 같은 입력은 키 순서·반복과 무관하게 같은 등급·같은 `input_sha256`이다.
- **누락 보류**: 필수 입력이 없거나 값이 틀리면 등급을 만들지 않는다. 승인 요청은 `hold_intake`로 도입을 보류하고 409로 거절한다. 콘솔은 입력이 없는 요청에 「입력 필요」를 보이고 승인 단추를 숨기며, 「영향평가 입력」 단추로 관리자가 채운다(`PUT /api/mcp-requests/{id}/risk-input`, `approval_events`의 `risk-input`으로 기록).
- **등급별 승인 방식**: 낮음·보통은 신청자와 다른 관리자 1명(기존). 높음은 서로 다른 관리자 2명 또는 위험 수용 사유(10자 이상), 매우 높음은 2명과 사유 모두. 첫 번째 승인은 `approval_events`의 `intake-cosign`에 남기고 요청은 열어 두며, 두 번째 사람은 첫 번째·신청자와 모두 달라야 한다(`review.require_independent`·`same_person`). 입력이 바뀌면 이전 1차 승인은 세지 않는다. 승인 증거와 승인 기록에 등급·점수·승인자를 남긴다.
- **등록**: 게이트웨이는 DB의 입력으로 등급을 다시 계산해 승인 증거의 `input_sha256`과 같을 때만 등록하고, 신청에 적은 것보다 높은 데이터 등급으로는 등록하지 않는다. `servers.json`의 `risk_assessment`와 서버 상세에 등급·입력·승인자가 보인다.
- **영향평가 입력 자료**: 신청 보고서(`risk.package`)와 콘솔 「영향평가」 탭이 입력을 영향평가가 묻는 항목에 맞춰 보여 준다(서식 초안). 평가·판단은 하지 않는다.
- **RQ-08(기존 승인 서버)**: 입력 없는 도입 서버는 매우 높음으로 가정하고, 게이트웨이가 이 확인을 처음 돈 시각부터 30일은 기존 승인을 유지하며 콘솔에 「재평가 필요」를 보인다. 30일째에 `valid_until`을 그 시각으로 줄여 `P-APPROVAL-EXPIRY-001`이 막고 「재승인 대기」가 되며 자동 연장도 그 시각을 넘지 못한다(`core.apply_risk_grace`·`risk_tier.cap_until`). 재승인은 입력을 담은 새 신청과 등록 해제·재등록 경로이며, 입력 없는 옛 소스 승인은 같은 저장소의 새 신청을 막지 않도록 중복 신청 검사를 좁혔다. 결정과 근거는 D-143.
- 새 OPA 정책 ID·새 의존성은 없다(`policy_ledger.json`·`policy_test.rego` 변경 없음).

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m py_compile` risk_tier·agent_service·core·main·intake_risk_tier_check (이 PC, 2026-10-20) | 통과 | 종료 코드 0 |
| 정적 검사 | `node --check agent_static/console.js` | 통과 | 종료 코드 0 |
| 화면 문구 | `python -B -X utf8 tests/console_copy_check.py` | 문제 0건 | 출력 |
| 회귀 | `node --test tests/console-state.test.mjs` | 15건 통과 | 출력 |
| 인증 경로 | `python -B -X utf8 tests/open_endpoints.py` | 통과: 무인증 1·인증 필요 76 | 출력 |
| 스키마 | `python -B -X utf8 tests/schema_check.py` | 통과 | 출력 |
| 단위 시험(이 PC) | `python -B -X utf8 tests/intake_risk_tier_check.py` | 25건 중 순수 12건 통과, 게이트웨이 의존 13건은 FastAPI·psycopg 없어 건너뜀 | 출력 |
| 단위 시험(일회성 컨테이너) | WSL Docker에서 `mcpgw-oss-20261003-gateway:latest`(10-03 이미지, compose 스택 아님)로 `intake_risk_tier_check.py` 실행 | 25건 모두 통과(승인·목록·입력 정정 경로 11, 유예 2 포함) | 출력 |
| 기존 시험 회귀(같은 컨테이너, 변경 전 main 사본과 비교) | `supplier_assurance_check` 6·`intake_identity_test` 19·`remaining_controls_check` 16·`ledger_retention_check`·`mcp_result_contract_check`·`provenance_check`·`security_edges_check`·`contracts_check` | main과 같은 결과(통과) | 출력 |
| 기존 시험 기준선 | 같은 컨테이너의 `intake_validation_test`(1 실패·1 오류), `ops_response_check`(14 오류) | 변경 전 main 사본에서도 같은 결과. 이 변경과 무관(아래 「기존 시험 변경 필요」) | 출력 |
| 위키 검사 | `python research/llm-wiki/tools/check_wiki.py` | 실패: 시작 전부터 있던 local-sources 29건 외에 `agent_service.py`·`core.py` 코드 해시 변경("Code changed after mapping"). 머지 뒤 `map_threats.py` 재생성 필요 | 출력 |
| 공백 검사 | `git diff --check` | 통과 | 종료 코드 0 |
| 배포·기기 | 솔루션 기기 `field up`·PJ1 실제 하네스·`opa test` | 미실행 | — |

## 기존 시험 변경 필요

기존 시험 파일은 고치지 않았다. 아래는 승인 경로가 이제 영향평가 입력(`risk_input`)을 요구해 승인 단계에서 보류되므로, 사람이 적대 검증 뒤 입력을 싣도록 바꿔야 한다. 첫 항목은 DEV-68의 공급자 보증 필수화 때문에 main에서 이미 실패하는 것을 확인했다. 나머지는 같은 보증 필수화로도 이미 승인 단계에서 막혔을 것으로 보이나 이 PC에서 돌릴 수 없어 확인하지 못했다.

- `tests/intake_validation_test.py`의 `test_approval_publishes_verified_commit_before_state_change`(본문 없는 승인 → 200 기대): 공급자 보증에 더해 `risk_input`이 있어야 한다.
- `tests/intake_identity_pg_check.py`와 `tests/intake_register.py`, `tests/security_regression.sh`의 승인·등록 흐름: 신청 본문에 `risk_input`(필요 시 `PUT …/risk-input`)을 넣고, 높음 이상은 두 번째 관리자 또는 사유가 필요하다. 이 PG 시험은 이 PC에서 돌릴 수 없어 확인하지 않았다.

## 실패·미완료·한계

- 점수표·최소 등급 규칙·유예 30일은 정책 판단이다. 규제가 요구하는 값이 아니고 법적 영향평가를 대신하지 않는다. 입력은 신청자의 신고라 사실 확인을 하지 않는다.
- 유예 시작 시각은 이 확인이 처음 돈 때 한 번 정해진다. 서버별로 늦출 수 없다. 두 번째 승인자 구분은 계정 구분(`principals.user_id`)에 기댄다.
- 입력이 없는 요청을 승인하려다 보류된 소스 신청은 보류 상태에서 입력을 채운 뒤 「검증 시작」으로 다시 검증해야 한다(콘솔은 입력 없는 요청의 승인 단추를 숨겨 이 경로를 피한다).
- 승인은 끝났지만 아직 등록하지 않은 옛 신청은 입력 증거가 없어 등록이 막힌다(DEV-68 보증 필수화와 같은 성격). DEV-68의 지원 종료 재승인과 달리 이번 중복 신청 완화는 입력 증거가 없는 승인에만 적용한다.
- 등록부 내보내기(DEV-68)에 위험 등급 열은 넣지 않았다. 콘솔 화면은 기기에서 열어 보지 않았다(브라우저 확인 미실행). 위 컨테이너는 10-03 이미지라 기기 이미지와 의존성 판본이 다를 수 있다.
- 위험 등급이 OPA 판정에 입력되지는 않는다. 승인 방식과 유예 만료에만 쓰인다.

## 다음 작업

DEV-71: 솔루션 기기 gateway 이미지에서 `python -B -X utf8 tests/intake_risk_tier_check.py`와 기존 승인 경로 시험을 실행하고, 기존 시험의 입력 보강(위 절)을 사람이 처리한 뒤 PJ1에서 (1) 신청 양식 입력·등급 표시, (2) 높음 등급의 2명 승인과 같은 사람 재승인 차단, (3) 입력 없는 기존 서버의 「재평가 필요」와 30일 뒤 차단·재승인 대기를 확인한다. 머지 뒤 `map_threats.py`로 위협 매핑 해시를 다시 만든다.

## 사용자에게 필요한 입력

없음. 점수표·최소 등급 규칙·승인 방식 표·유예 30일을 고객 정책에 맞게 바꿀지 여부는 기기 확인 뒤 정한다.
