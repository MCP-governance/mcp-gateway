# 원본 24개 정책 → 통제·코드 후보 매핑

2026-10-13 정적 연구 매핑입니다. 코드 경로 존재와 로컬 바이트 해시를 확인했고 해당 통제의 전체 구현·실기기 집행을 증명하지 않습니다.
원본 PAC01~24와 런타임 PAC-01~15는 별도 번호 체계입니다. 50개 확장표는 별도 검토 목록으로 보존합니다.

| 원본 ID·셀 | 위협·통제 | 런타임 후보 | 코드 후보 | 남은 검증 |
| --- | --- | --- | --- | --- |
| PAC01 · A5 | 도입·공급망: 출처나 무결성이 확인되지 않은 배포물 도입 | MCP-SUPPLY-001 | [intake_validation_test.py](../../../full_stack_lab/tests/intake_validation_test.py) | 라이선스·배포처·SBOM·취약점과 실제 도입 승인 증거 필요 |
| PAC02 · A6 | 계약·권한 범위: 검토되지 않은 기능 도입과 과도한 권한 부여 | PAC-01, PAC-08 | [agent_service.py](../../../full_stack_lab/gateway/app/agent_service.py)<br>[pac.py](../../../full_stack_lab/gateway/app/pac.py) | 도구 계약과 실제 자원·인자의 승인 범위 독립 검토 |
| PAC03 · A7 | 승인·유효기간: 승인 기간이 지났거나 승인 조건 또는 사용자 동의를 확인하지 않은 연결 | P-APPROVAL-EXPIRY-001, PAC-01 | [core.py](../../../full_stack_lab/gateway/app/core.py) | 사용자 동의와 서버 사용 승인은 별도 증거 |
| PAC04 · A8 | 시험·환경: 미승인 환경 실행과 시험 환경의 운영정보 노출 | PAC-03 | [pac15.rego](../../../full_stack_lab/opa/pac15.rego) | 환경 사실 입력과 실기기 관찰값 결합 검증 |
| PAC05 · A9 | 목적지·SSRF: 승인 범위를 벗어난 서버나 OAuth 조회 주소에 접속 | MCP-EGRESS-001, MCP-EGRESS-002 | [classify.py](../../../full_stack_lab/gateway/app/classify.py)<br>[upstream.py](../../../full_stack_lab/gateway/app/upstream.py) | OAuth discovery·DNS 재결합 등 최종 접속 대상의 별도 경계 |
| PAC06 · A10 | 도구 계약: 미승인 기능 또는 다른 서버의 동명 기능 실행 | MCP-CATALOG-001, PAC-08 | [contract.py](../../../full_stack_lab/gateway/app/contract.py)<br>[core.py](../../../full_stack_lab/gateway/app/core.py) | 동명 도구·설명·스키마 변경과 승인 이후 변형 시험 |
| PAC07 · A11 | 엔드포인트 우회: 게이트웨이를 거치지 않은 직접 연결 | MCP-SHADOW-* | [enforce-linux.py](../../../endpoint-agent/enforce-linux.py)<br>[managed-linux.py](../../../endpoint-agent/managed-linux.py) | 파일 설정만으로 차단을 주장하지 않음; 현재 기기의 실제 OS 집행 미확인 |
| PAC08 · A12 | 신원: 요청 주체 사칭과 검증되지 않은 신원 수용 | PAC-04 | [idp.py](../../../full_stack_lab/gateway/app/idp.py)<br>[core.py](../../../full_stack_lab/gateway/app/core.py) | transport 신원과 사용자 자기 선언 필드 분리 |
| PAC09 · A13 | 위임: 위조되거나 만료된 위임정보를 이용한 대리 실행 | PAC-05 | [pac.py](../../../full_stack_lab/gateway/app/pac.py)<br>[pac15.rego](../../../full_stack_lab/opa/pac15.rego) | 위임 근거·교집합·철회·만료 시험; 하네스 이름은 인증 근거 아님 |
| PAC10 · A14 | 토큰: 다른 대상용 또는 만료 토큰 수용과 목적 외 전달 | PAC-06 | [idp.py](../../../full_stack_lab/gateway/app/idp.py)<br>[upstream.py](../../../full_stack_lab/gateway/app/upstream.py) | audience·scope·issuer·만료·직원 토큰 미전달의 독립 검증 |
| PAC11 · A15 | 호출별 권한: 이전 허용 결과를 범위가 다른 후속 호출에 재사용 | PAC-09 | [core.py](../../../full_stack_lab/gateway/app/core.py)<br>[pac15.rego](../../../full_stack_lab/opa/pac15.rego) | 이전 허용·캐시 결과를 범위가 다른 요청에 재사용하는지 시험 |
| PAC12 · A16 | 행위 구분: 조회 권한을 수정, 삭제, 실행 또는 전송 권한으로 확대 | PAC-09 | [classify.py](../../../full_stack_lab/gateway/app/classify.py) | 도구 이름이 아닌 실제 SQL·명령·수신자 효과로 분류 |
| PAC13 · A17 | 스키마·인자: 승인 범위를 벗어난 인자와 실제 실행 대상 사용 | P-INPUT-SCHEMA-001, PAC-10 | [core.py](../../../full_stack_lab/gateway/app/core.py)<br>[classify.py](../../../full_stack_lab/gateway/app/classify.py) | 정책 전과 실행 직전 입력 검사 및 정규화 우회 시험 |
| PAC14 · A18 | 자산·등급: 권한 밖 데이터 자산 또는 보안 등급에 접근 | P-CLASSIFICATION-001, PAC-11 | [classify.py](../../../full_stack_lab/gateway/app/classify.py)<br>[pac.py](../../../full_stack_lab/gateway/app/pac.py) | 미분류를 낮은 등급으로 허용하지 않는지 확인 |
| PAC15 · A19 | 외부 전송: 승인하지 않은 수신자에게 승인 범위 밖 데이터 전송 | MCP-DATA-EGRESS-001, PAC-12 | [classify.py](../../../full_stack_lab/gateway/app/classify.py)<br>[privacy.py](../../../full_stack_lab/gateway/app/privacy.py) | 실제 최종 목적지·데이터 조합과 프롬프트/모델 경로는 따로 검증 |
| PAC16 · A20 | 개별 승인: 다른 요청의 승인 재사용 또는 미승인 고위험 실행 | PAC-13 | [core.py](../../../full_stack_lab/gateway/app/core.py)<br>[reservation_effect_check.py](../../../full_stack_lab/tests/reservation_effect_check.py) | nonce·canonical fingerprint·자가 승인·동시 승인 재사용 시험 |
| PAC17 · A21 | 호출·동시성: 호출 폭주와 과도한 동시 실행으로 인한 자원 고갈 | P-RATE-001, P-RATE-002, P-RATE-003 | [core.py](../../../full_stack_lab/gateway/app/core.py)<br>[reservation_effect_check.py](../../../full_stack_lab/tests/reservation_effect_check.py) | 호출량 상한과 모든 upstream의 실행 시간 제한을 동일시하지 않음 |
| PAC18 · A22 | 비신뢰 콘텐츠: 외부 콘텐츠의 지시를 승인이나 권한 부여로 오인 | P-UNTRUSTED-CONTENT-001, P-UNTRUSTED-CONTENT-002 | [poisoning.py](../../../full_stack_lab/gateway/app/poisoning.py) | 패턴 검사와 의미적 주입 탐지 구분; 정상 대조군·다국어 표본 필요 |
| PAC19 · A23 | 입력 PII·Secret: 업무에 불필요한 민감정보를 Tool 인자로 전달 | P-DATA-INSPECTION-001 | [privacy.py](../../../full_stack_lab/gateway/app/privacy.py)<br>[secret_scan.py](../../../full_stack_lab/gateway/app/secret_scan.py) | 불필요 수집 제한과 탐지 성공은 다른 통제; scanner 장애 시험 |
| PAC20 · A24 | 출력 PII·Secret: Tool 응답을 통해 불필요한 정보가 모델이나 사용자에게 노출 | MCP-OUTPUT-001 | [core.py](../../../full_stack_lab/gateway/app/core.py)<br>[privacy.py](../../../full_stack_lab/gateway/app/privacy.py) | 응답 보류·마스킹은 upstream 미실행을 뜻하지 않음 |
| PAC21 · A25 | 변경 재승인: 검토하지 않은 기능이나 권한 변경을 계속 사용 | MCP-CATALOG-001, PAC-02 | [contract.py](../../../full_stack_lab/gateway/app/contract.py)<br>[core.py](../../../full_stack_lab/gateway/app/core.py) | 자동 최초 신뢰 금지; 사람이 승인한 계약과 호출 시 관찰 해시 대조 |
| PAC22 · A26 | 감사: 인가, 승인과 폐기 이력의 누락 또는 변조 | append-only audit | [audit.py](../../../full_stack_lab/gateway/app/audit.py)<br>[oss_audit_test.py](../../../full_stack_lab/tests/oss_audit_test.py) | 체인 검증과 DB 소유자의 변조 가능성·보존 정책은 별도 |
| PAC23 · A27 | 철회·종료: 중지, 철회 또는 폐기 이후 기존 연결로 재접근 | MCP-DECOMM-001, PAC-14 | [decommission.py](../../../full_stack_lab/gateway/app/decommission.py)<br>[termination_flow.py](../../../full_stack_lab/tests/termination_flow.py) | C1~C4와 자원 서버 재접근의 현재 증거 필요 |
| PAC24 · A28 | 잔존 자격: 설정 삭제 후 남은 인증정보를 이용한 재접근 | PAC-14, C3/C4 | [idp.py](../../../full_stack_lab/gateway/app/idp.py)<br>[decommission.py](../../../full_stack_lab/gateway/app/decommission.py) | 설정 삭제는 외부 토큰·키 회수 증거 아님 |

JSON에는 로컬 파일의 원래 바이트 hash와 LF 정규화 hash, HEAD의 commit 파일 hash를 함께 기록했습니다. 코드의 CRLF/LF 차이는 실제 코드 변경과 구분합니다. 자료 원본 hash는 줄바꿈까지 그대로 보존합니다. `worktree_modified=true`인 기존 미커밋 파일은 위키 커밋에 포함하지 않습니다. 다른 PC의 HEAD 코드와 이 매핑의 로컬 관찰값이 다를 수 있으므로 실제 변경 파일을 다시 확인합니다.
