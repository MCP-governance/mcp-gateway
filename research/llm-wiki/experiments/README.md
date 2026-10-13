# 세팅 후 실험 자료

확인일: 2026-10-13. 아래 13개 카드는 **설계·미실행**이다. 최초 위키 구축 시 12개를 만들었고 팀 개발 계획에서 PJ1 로컬 stdio·loopback 우회 E13을 추가했다. 이후 제품 배포와 PJ1 실제 호출 표본은 [실기기 보고](../status/reports/2026-10-13-development-results.md)에 별도로 기록했다. 해당 표본은 이 카드의 입력·완료 조건 전체를 충족하지 않아 카드 상태를 통과로 바꾸지 않는다.

먼저 [사전 조건 및 증거 규칙](preflight.md), [시험 대상](targets.md), [기존 테스트 지도](test-inventory.md)를 읽는다. 입력은 [cases.json](fixtures/cases.json)에 기계가 읽을 수 있게 저장했다. `catalogs/experiments.json`이 카드의 목록이다.

| ID | 실험 | 준비 상태 | 실행 상태 |
| --- | --- | --- | --- |
| [E01](E01-approved-read.md) | 승인된 공개 파일 읽기 | 기존 입력 재사용 | 미실행 |
| [E02](E02-pii-result-masking.md) | 개인정보 결과 마스킹 | 기존 입력 재사용 | 미실행 |
| [E03](E03-pii-external-egress.md) | 개인정보 외부 반출 차단 | 기존 입력 재사용 | 미실행 |
| [E04](E04-untrusted-argument.md) | 인자의 주입 표지와 승인 대기 | 기존 입력 재사용 | 미실행 |
| [E05](E05-ssrf-normalization.md) | IP 표기 우회·내부 목적지 차단 | 기존 입력 재사용 | 미실행 |
| [E06](E06-input-schema.md) | 승인 입력 스키마 위반 | 입력 준비 | 미실행 |
| [E07](E07-contract-drift.md) | 승인 후 도구 설명·스키마 변경 | 격리 mock 서버 준비 필요 | 미실행 |
| [E08](E08-pdp-failure.md) | 정책 엔진 실패 시 차단 | 격리 장애 주입 준비 필요 | 미실행 |
| [E09](E09-principal-binding.md) | 승인되지 않은 주체의 공급자 서버 호출 | 시험 계정 준비 필요 | 미실행 |
| [E10](E10-concurrent-duplicate.md) | 동시 중복 호출의 실행 억제 | 지연 mock 서버 준비 필요 | 미실행 |
| [E11](E11-termination-evidence.md) | 종료 즉시 차단 및 회수 증거 판정 | 전용 이용 관계 준비 필요 | 미실행 |
| [E12](E12-managed-admission.md) | 관리형 활성 상태와 MCP 입구 인가 | PJ1 관리자·시험 계정 필요 | 미실행 |
| [E13](E13-local-bypass.md) | PJ1 로컬 stdio·loopback 우회 | 전용 무해 fixture·실제 보호 launcher 필요 | 미실행 |

정책 우선순위·최근 호출 이력·역할이 예상과 달라 다른 정책이 먼저 적용되면 통과로 세지 않는다. 원인을 기록하고 선행 조건을 고친다. 판정이 Block이라는 사실만으로 실행 예방을 입증하지 않는다. `decision`, `policy_id`, `upstream_attempted`, `upstream_executed`, 실제 효과를 함께 확인한다.

새 실험 결과는 이 디렉터리에 `runs/<실행일>/<실험ID>/report.md`와 비밀을 제거한 증거 목록을 만들고, 위키의 상태 보고 규칙에 따라 기록한다. 실패·미실행·제약도 결과로 남긴다. 현재 카탈로그의 `status=not_run`을 실제 실행 증거 없이 바꾸지 않는다.
