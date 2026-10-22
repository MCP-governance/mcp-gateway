# 2026-10-22 위협 추적 변경 경계 독립 재대조

- 작업자: Codex, 제품 변경 구현과 분리된 정적 검토
- 코드 기준: 이전 검토 `204579981ac02956a3ee40301f251ee99af9de6e`, 현재 검토 `fbd1fc4c30e7cc44a543ad6a243e086362322b9f`
- 시작 근거: 원본 정책 24행 추적의 제품 및 시험 파일 해시 불일치
- 완료 조건: 변경된 함수와 시험의 의미를 검토하고 과거 검토 원본을 보존한 채 현재 매핑을 다시 고정

## 결과

[변경별 정본](../../analysis/threat-trace-review-1022/README.md)에 제품 경계와 한계를 기록했다. 6개 파일의 과거 고유 참조 25개를 재대조하고 PAC15와 PAC23의 현재 코드 및 시험 참조를 더했다. 이전 검토 JSON은 새 디렉터리에 원본 바이트로 보존했다. 현재 매핑의 `files_match_review`는 24행 모두 참이다. 제품 코드와 원본 정책표는 변경하지 않았다.

PAC15의 공급자 위치 심사는 승인 사건을 먼저 기록하고 서버와 신청, 위치, 관할 규칙 팩에 결속된 심사 표식을 저장한다. 이 표식은 비중요 등급의 국가별 승인 요구에만 한정된다. PAC23의 직원별 로컬 재개는 중지 행과 같은 거래에서 해당 직원 및 서버의 정지 표식만 지운다. 나머지 파일 해시 차이는 기존 매핑 함수의 본문을 바꾸지 않았거나 시험 준비 및 자격 경로 변경이다. 각 판단은 [JSON 근거](../../analysis/threat-trace-review-1022/delta-review.json)에 이전 및 현재 위치와 함께 남겼다.

## 검증

| 확인 종류 | 환경과 명령 | 결과 | 근거 수준 |
| --- | --- | --- | --- |
| 위협 매핑 | `map_threats.py`, `threat_trace_mapping_check.py` | 24행 생성, 4건 통과 | 정적 참조와 해시 |
| 검토 이력 | `threat_review_refresh_check.py` | 2건 통과 | 이전 원본 바이트와 대체 관계 |
| 위키 | `check_wiki.py --ci-ignored-local-sources` | 오류 0건, 무시된 로컬 원본 누락 경고 | 문서 연결과 해시 |
| 위치 심사 | `.venv/bin/python full_stack_lab/tests/residency_transfer_review_check.py`, `python3 full_stack_lab/tests/data_residency_check.py` | 10건, 8건 통과 | DB 및 등록부 대역, 위치 함수 |
| 로컬 이용 중지 | `python3 full_stack_lab/tests/user_local_suspend_check.py`, `.venv/bin/python full_stack_lab/tests/user_server_suspend_check.py`, `.venv/bin/python full_stack_lab/tests/user_suspend_all_check.py` | 12건, 24건, 14건 통과 | DB 및 실행기 대역 |
| 정책 | OPA 1.21.1 `opa test full_stack_lab/opa --count 1` | 130/130 통과 | Rego 단위 시험 |
| 실제 모델, MCP, PJ1, 기기 배포 | 실행하지 않음 | 미확인 | 과거 보고 수치를 현재 결과로 사용하지 않음 |

## 실패와 미완료

초기에는 검토 정본이 이전 파일 해시를 가리켜 매핑 시험과 위키 검사가 실패했다. 현재 정본 갱신 뒤 해시와 문서 연결을 다시 검사했다. 새 이력 적용 직후 `threat_review_refresh_check.py`가 2026-10-21 경로를 고정해 실패했으므로 현재 검토의 대체 관계를 따라 검사하도록 수정했다. 제품 배포와 실제 PostgreSQL 경합, 공개 MCP 전송 효과는 이번 검토에서 확인하지 않았다.

## 다음 작업

지정 기기와 PJ1에서 관할 규칙 활성 상태의 승인 전후 전송, 별도 외부 목적지, 중요 등급 차단, 직원별 로컬 작업의 정지 ACK와 동시 재개를 원장 및 외부 효과로 대조한다.

## 사용자에게 필요한 입력

없음. 실제 기기 검수는 별도 작업이다.
