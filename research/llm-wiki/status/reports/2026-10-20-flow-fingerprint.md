# 2026-10-20 서버 간 중요정보 전달 경계의 내용 지문 대조

- 작업자: Claude Sonnet
- 브랜치: `10/20-flow-fingerprint`
- 코드 기준: `2c01673`, 시작 시 워킹 트리 깨끗함. 변경 파일: `full_stack_lab/gateway/app/flow_fingerprint.py`(신규)·`core.py`·`v2_tables.sql`, `full_stack_lab/opa/policy.rego`(주석)·`policy_ledger.json`·`policy_test.rego`, `full_stack_lab/tests/flow_fingerprint_check.py`(신규), `full_stack_lab/eval/scenarios/controls-2026-10-20.json`·`eval/README.md`, `full_stack_lab/.env.example`, `docs/ai/DECISIONS.md`(D-142)·`POLICY.md`·`ARCHITECTURE.md`·`DATA_MODEL.md`, `research/llm-wiki/analysis/flow-fingerprint-1020/`(신규: 길이·임계값 실험 스크립트와 결과), 이 보고서, `status/backlog.md`의 DEV-59 상태 칸.
- 시작 근거: DEV-59, POL-33, D-133 한계("내용 지문 대조가 다음 단계")
- 해결할 문제와 완료 조건: 열람한 서버와 내용이 같거나 비교할 수 없는 호출만 `P-FLOW-001`로 막고, 비교해서 다르면 막지 않되 판정 기록에 남긴다. 원문은 저장하지 않고, 지문 계산·저장이 실패하면 D-133의 거친 표지로 돌아간다.

## 결과

구현·시험 단계까지다. 기기 배포와 실제 MCP 읽기 뒤 쓰기는 하지 않았다.

- **저장**: 중요 등급 읽기가 끝나 판정 기록이 남은 뒤, 클라이언트에 돌려준 본문의 모든 문자열·숫자를 NFKC → casefold → 글자·숫자만 남김으로 정규화해 16자 조각의 BLAKE2b 64비트 해시(`shingles`)와 이메일·9~32자리 숫자의 해시(`identifiers`)를 `flow_fingerprints`에 한 행 남긴다. 키는 주체별 무작위 솔트(행에 저장)에 선택 환경 변수 `FLOW_FINGERPRINT_PEPPER`를 더한 값이다. 원문 문자열은 어느 열에도 없고, 만료 10분(`CHAIN_WINDOW_MINUTES`) 뒤 다음 중요 등급 읽기 때 지운다. `decisions`는 고치지 않는다.
- **대조**: 쓰기·실행·공급자 호스팅 호출의 인자 전체(키 포함, 깊이·목록 길이 제한 없음)를 같은 방식으로 지문을 만들어 식별자 1개 또는 조각 3개 이상이 겹치면 "내용 일치"다.
- **판정 입력**: 서버별로 창 안의 모든 읽기를 대조한다. 하나라도 일치하거나 비교할 수 없으면(지문 행 없음) `request.flow_sources`에 남고, 전부 비교했는데 모두 다를 때만 빠진다. 빠진 서버는 `request.flow_observed`에 "열람 후 다른 서버 호출(내용 불일치)"로, 일치는 "…(내용 일치)", 비교 불가는 "…(내용 확인 불가)"로 `policy_input.request`에 남는다. OPA 규칙은 그대로 `flow_sources`만 읽는다. `P-FLOW-001`은 정책 관리대장 1.1.0(설명·시행일 갱신, 우선순위 47 그대로).
- **입력 → 결과(시험으로 확인한 것)**

| 상황 | 결과 |
| --- | --- |
| 읽은 문장을 그대로 다른 서버에 쓰기 | `flow_sources`에 남음 → `P-FLOW-001` 차단 |
| 같은 문장을 공백·대소문자·전각·제로폭 문자만 바꿔 쓰기 | 같음 → 차단 |
| 읽은 내용과 무관한 쓰기 | `flow_sources` 비어 있음 + `flow_observed`에 "내용 불일치" → 차단하지 않음 |
| 읽은 전화번호·이메일만 짧게 옮겨 쓰기 | 식별자 일치 → 차단 |
| 정규화 후 17자만 겹침 | 임계값 미만 → 차단하지 않음(18자부터 걸림) |
| 지문 저장 실패·결과가 4만 조각 초과·지문 행 없음 | "내용 확인 불가" → 출처로 남아 차단(거친 표지) |
| 대조 중 예외 | 창 안 모든 서버가 출처 → 차단 |
| 공급자 호스팅 수신 + 일치 | `accepts_from`으로도 못 풀고 차단(기존 규칙) |
| 공급자 호스팅 수신 + 불일치 | 차단하지 않음 |
| 지문 행의 내용 | 해시 정수와 솔트뿐, 원문 단어가 어느 열에도 없음 |

- **길이·임계값 근거**: 저장소 문서로 쟀다(한국어 64건·영어 34건, `analysis/flow-fingerprint-1020/threshold_experiment.txt`). 무관한 쌍에서 조각 3개 이상 겹침: 12자 7.4%, 16자 0.5%, 20자 0.1%. 변형 복사본이 걸리는 비율(16자): 공백·대소문자 98~100%, 단어 5개마다 교체 97%, 문장 건너뜀 98%, 글자 삽입·base64·역순 0%. 선택 이유와 미탐 위험은 D-142에 있다.
- **되돌리기**: `execute_call`이 `_flow_sources`에 호출 내용을 넘기지 않으면 D-133 동작이다. 표는 그대로 둬도 된다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m pyflakes gateway/app/{flow_fingerprint,core}.py tests/flow_fingerprint_check.py`, `python -m py_compile` 같은 파일, Windows Python 3.12.10, 2026-10-20 | 통과 | — |
| 단위 시험(순수 부분) | `python tests/flow_fingerprint_check.py`, psycopg 없음 | 27건 중 16 통과, 11 건너뜀(원장 질의·`execute_call` 연결) | 정규화·지문·대조·원문 미저장·ReDoS 방지 |
| 단위 시험(전체) | 같은 파일, psycopg·fastapi·mcp 등을 빈 대역으로 채운 임시 폴더를 `PYTHONPATH`에 두고 실행(저장소 밖, 게이트웨이 이미지 아님) | 27건 통과 | 같은 문장 차단·무관 쓰기 기록·변형 차단·저장 실패 거친 표지·원문 미저장·`execute_call`이 호출 내용을 넘기고 중요 읽기 뒤에만 보관 |
| 기존 시험(같은 대역) | `remaining_controls_check.py`(POL-33 3건 포함), `high_impact_check.py --gateway`, `ledger_retention_check.py`, `tests/open_endpoints.py` | 16·24·12건 통과, 통과 | 기대값 변경 없음 |
| 정책 시험 | WSL kali `opa test`(OPA 1.20.2), `full_stack_lab/opa` | 117/117 통과(기존 111 + 신규 6) | 불일치 기록 시 비차단, 일치·확인 불가 차단, 관찰값만으로는 출처 아님, 공급자 호스팅 불일치 비차단·일치 차단 |
| 평가 사례 | 신규 2건을 `opa eval -d .`로 직접 판정, `python eval/before_after.py --self-test` | 일치 사례 `Block P-FLOW-001`, 불일치 사례 `Allow`, 자체 시험 통과 | Docker 전후 비교(`before_after.py` 본 실행)는 미실행 |
| 길이·임계값 실험 | `python research/llm-wiki/analysis/flow-fingerprint-1020/threshold_experiment.py` | 실행함 | `threshold_experiment.txt` |
| 실제 PostgreSQL | `flow_fingerprints` 생성·삽입·조인 | 미실행 | — |
| 게이트웨이 이미지 안 시험 | 아래 "사용자에게 필요한 입력" | 미실행 | — |
| 실제 MCP 읽기 뒤 쓰기(PJ1) | — | 미실행 | — |
| 배포·정책 해시 | — | 미확인 | — |

## 기존 시험 변경 필요 여부

없음. `remaining_controls_check.py`·`high_impact_check.py`의 기대값을 바꾸지 않았다. `_flow_sources`는 호출 내용을 넘기지 않은 호출(기존 시험 포함)에서 예전처럼 창 안 모든 서버를 돌려주고, 시험이 보는 질의 조건(`server_id<>%s`, 첫 두 인자)도 그대로다.

## 실패·미완료·한계

- **줄어드는 차단은 미탐 위험과 맞바꾼 것이다.** 의역·번역·인코딩(base64·역순·글자 사이 삽입·동형 문자)·정규화 후 18자 미만 조각·여러 호출로 나눈 전달은 못 잡는다. 에이전트가 읽은 것을 그대로 옮겨 쓰는 경우를 겨냥한 지문이라 고의적 우회는 `accepts_from` 심사·외부 전송 통제가 맡는다. 소유자 확인이 필요한 정책 완화다(D-142).
- `P-CHAIN-001`(열람 뒤 외부 전송)과 `MCP-DATA-EGRESS-001`은 이 변경과 무관하게 그대로다.
- `FLOW_FINGERPRINT_PEPPER`를 compose가 컨테이너에 넘기지 않아 기본은 솔트만 쓴다. DB만 읽은 사람이 추측한 문장을 확인할 수 있다.
- 만료 행 삭제는 다음 중요 등급 읽기 때만 일어난다. 읽기가 없으면 만료 행이 남는다(조회는 만료 행을 무시한다).
- 읽기 결과가 정규화 4만 자를 넘으면 지문이 없어 거친 표지로 남는다. 행 조회가 배열을 내려받아 비교하므로 창 안 읽기가 많은 주체는 SQL 교집합으로 옮겨야 한다.
- 결과가 `MCP-OUTPUT-001`로 보류된 읽기는 지문이 없다(거친 표지 유지, D-133과 같음).
- 판정과 실제 전송 사이에 새로 생긴 읽기는 반영하지 않는다(D-133 sol 6번과 같음).
- 길이·임계값 실험은 이 저장소의 한국어·영어 문서로 쟀다. 고객 업무 문서의 거짓 일치·미탐은 다를 수 있다.

## 다음 작업

- 기기 배포 후 PJ1에서 중요 등급 서버 읽기 → 같은 내용 쓰기(차단)와 무관한 쓰기(허용, `flow_observed` 확인)를 실제 MCP로 시험, `flow_fingerprints` 행 수와 만료 삭제 확인.
- 소유자 결정: 위 미탐 위험을 받아들일지, `FLOW_FINGERPRINT_PEPPER`를 compose에 넘길지.
- 필요하면 SQL 교집합 비교, 만료 행의 주기 삭제, 콘솔 판정 상세에 `flow_observed` 표시(제품 문구로 다듬어서).

## 사용자에게 필요한 입력

- 기기 `full_stack_lab`에서 게이트웨이 이미지로 시험:
  - `docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" gateway /tests/flow_fingerprint_check.py` (27건, 건너뜀 0 기대)
  - 같은 방식으로 `/tests/remaining_controls_check.py`(16건), `/tests/high_impact_check.py --gateway`(24건)
  - `docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy` (117건)
- 게이트웨이를 다시 띄운 뒤 `SELECT count(*) FROM flow_fingerprints;`와 첫 중요 등급 읽기 뒤 행이 생기는지 확인(psycopg의 정수 배열 삽입이 이 PC에서는 실행되지 않았다).
