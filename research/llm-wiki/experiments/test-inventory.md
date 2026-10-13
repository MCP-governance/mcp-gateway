# 기존 솔루션 테스트 지도

확인일: 2026-10-13. 경로는 현재 checkout에서 존재·주요 입력/단언을 정적으로 읽었다. **이 문서 작성 중 어느 테스트도 실행하지 않았다.** 테스트 파일의 이름이나 PASS 문자열을 실제 통과 증거로 쓰지 않는다.

| 기존 경로 | 확인한 역할 | 실행 범위·주의 |
| --- | --- | --- |
| [opa/policy_test.rego](../../../full_stack_lab/opa/policy_test.rego) | policy_id, 중복·상한·종료·기본 허용 등 정책 단언 | 모델·MCP 실행을 증명하지 않는 정책 단위 테스트 |
| [schema_check.py](../../../full_stack_lab/tests/schema_check.py) | 기동 SQL 파일 사이 CHECK 제약 일치 검사 | 로컬 정적 검사, DB 불필요 |
| [contracts_check.py](../../../full_stack_lab/tests/contracts_check.py) | package/version/description/schema 잠금 diff | self-check는 정적; fresh lock 수집은 실제 서버 필요 |
| [credential_binding_check.py](../../../full_stack_lab/tests/credential_binding_check.py) | 정확한 resource·principal·기한·권한·header 형식 | 정적 trust boundary 검사; 실제 vendor 호출은 별도 |
| [adversarial_check.py](../../../full_stack_lab/tests/adversarial_check.py) | SSRF, SQL 효과, 주입 인자, PII·비밀 반출, traversal | 실제 Gateway 필요; policy_id와 사전 미실행 검증이 포함됨 |
| [plane_sequence.py](../../../full_stack_lab/tests/plane_sequence.py) | 실제 하네스·정해진 도구 호출·후속 결과 수집 | PJ1/승인된 실제 환경에서 사용; CLI·대상 확인 필요 |
| [plane_evidence.py](../../../full_stack_lab/tests/plane_evidence.py) | 요청별 평면·판정·원장 증거 대조 | evidence 형식·실행 경로 확인 후 재사용 |
| [plane_cases_lab.json](../../../full_stack_lab/tests/plane_cases_lab.json) | 공개 읽기·PII 마스킹·반출·범위·중복 입력 | lab fixture 기준; field 서버와 혼동하지 않음 |
| [plane_cases_field.json](../../../full_stack_lab/tests/plane_cases_field.json) | GitHub 읽기·외부 전송·응답·직접 연결 사례 | 계정·공급자 승인·관리형 조건 필요 |
| [plane_cases_field_other_identities.json](../../../full_stack_lab/tests/plane_cases_field_other_identities.json) | 다른 주체의 `MCP-REGISTRY-003` 기대값 | 시험 주체가 실제로 승인되지 않았는지 먼저 확인 |
| [managed_enrollment_check.py](../../../full_stack_lab/tests/managed_enrollment_check.py) | 관리형 등록·설정 경계 검사 | 실제 환경 요건·입력 확인, 설치와 활성 구분 |
| [managed_kernel_proof.py](../../../full_stack_lab/tests/managed_kernel_proof.py) | 설치 collector·커널 규칙·설정·heartbeat 입구 검사 | PJ1 root 필요; service 정지는 시험 기기만, finally 복구 |
| [termination_flow.py](../../../full_stack_lab/tests/termination_flow.py) | 종료 C1~C4/T1~T3·자격 회수·잔존 설정 | lab 상태·자격 변경; 공유 관계에 그대로 실행하지 않음 |
| [security_regression.sh](../../../full_stack_lab/tests/security_regression.sh) | 격리·HTTP·감사 체인·계약·전반 회귀 | Docker lab용; 노트북 실행 금지, field에 무조건 복사하지 않음 |

새로운 테스트를 무조건 추가하기보다 기존 의미 있는 단언과 fixture를 재사용한다. 미완료 카드의 mock 지연·계약 변경·PDP 장애 주입은 아직 자동 실행 가능한 환경으로 제공하지 않았으며 카드에 준비 필요로 표시했다.
