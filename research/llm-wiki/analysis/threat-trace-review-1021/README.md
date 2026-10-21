# DEV-03 현 판본 추적 재대조 — 2026-10-21

기준은 `22238b54f2a5ce1a18c19e0f3968658d264c6c72`에서 `204579981ac02956a3ee40301f251ee99af9de6e`까지다. [이전 정본 바이트](review-2026-10-20.json)를 보존하고 [현재 정본](../threat-trace-review-1020/review.json)을 대체 관계로 연결했다. [변경별 정본](delta-review.json)은 20개 파일·71개 낡은 참조의 이전/현재 해시·행·AST 동일 여부·의미 검토를 가진다. 제품 코드·정책 판정·기존 시험 단언은 이번에 바꾸지 않았다.

24개 원본 요구를 다시 읽고 각 참조의 함수 본문·호출 경계와 기준 커밋 이후 diff를 대조했다. AST가 동일한 참조도 파일의 다른 함수 변경을 검토했다. 9개 정책의 한계 문장을 정정하고 새 코드 참조 11개를 연결했다. AST 동일은 호출 환경과 실행 효과 동일의 증명이 아니다. E01~E19의 과거 실행 수치는 현재 재실행으로 승격하지 않으며 회귀 소스의 `execution_in_this_review=미실행`은 기존 증거 분류를 유지한다. 이번 로컬 실행 결과는 [작업 보고](../../status/reports/2026-10-21-dev03-review-refresh.md)에서 따로 기록한다.

## 의미가 달라진 경계

| 원본 | 현재 코드·판단 | 남는 한계 |
| --- | --- | --- |
| PAC01 | `artifact_provenance.verify_source_attestation`, 별도 승인·한 화면 클릭·실행기 재조정·되돌림에서 증명 재검증 | Ed25519/DSSE·관리자 신뢰 키와 허용 builder 범위. 미제공은 차단이 아닌 확인 안 됨. 선택 OCI 조회는 소스 아카이브 digest 기준이며 허용 목록 기본은 비어 있음. 실제 이미지 digest·Cosign/Rekor·수집 성공 미확인 |
| PAC02 | `approve_and_register`가 입력·도구에서 등급/범위를 제안하고 `register_server`가 승인 입력·범위·인원 재대조 | D-189 높음 2인·매우 높음 2인/사유. 단독 표식은 사람 수 대체가 아님. 선택 공급자 보증의 빈 항목은 검증된 사실이 아님 |
| PAC06·11 | 목록/호출의 미사용 제한, 직원×서버 중지, 최종 dispatch 재확인. 집계 실패는 SAVEPOINT로 Block 원장 보존 | Resource/Prompt 지원 추가 아님. 이미 전송된 원격 호출 회수·실제 독립 효과 미확인 |
| PAC07 | AppArmor `profile`의 경고/강제 분기 추가 | 기본 경고에서 같은 UID 노출이 남음. 강제 후보의 pathname `addr` 문법 문제·헤더 `sh -c` 정상 경로는 DEV-81 보류 브랜치 `10/21-dev81-direct-helper`의 보고 `status/reports/2026-10-21-dev81-direct-helper.md` 참조. 강제 승격/커널 로드/PJ1 없음 |
| PAC15 | `residency.enabled`와 `require_location`의 관할 팩 활성 조건 | 기본 비활성은 위치 미제공 차단이 아님. LLM 경로와 제3자 SaaS outbound 검증은 별도 |
| PAC18 | E11의 후속 공개 corpus 보고 반영: catalog dev 0.5278·held-out 0.5178, D-158 전후 변화 없음. result 오탐66/3.3% | 보고서 수치를 이번 측정으로 세지 않음. 이후 BOM/건수 수정 뒤 현재 재실행 없음. catalog/result·합성/공개·의미적 주입 전체를 구분 |
| PAC23·24 | `quiesce`, `prepare_token_revocation`과 계정/장치/서버 종료 연결 | 정지 확인 불능이면 전환 보류. 로컬 실행의 실제 컨테이너·하네스·진행 중 직원 이용 중지 연결은 별도. 외부 JWT 캐시·자격 복원 보장 아님 |

`classify`의 참조 함수·`managed_failure`·Windows `checks`·기존 계약/흐름/응답 검사·종료 판정 함수 AST는 동일했다. 주변 BOM 계산·버퍼 수치·설치 파일·로컬 작업 호출·시험 이름공간은 파일별 검토 정본에 구분했다. `worker`의 세 사건 가드는 작성 경로가 없다는 기존 정정을 유지하고 서버 상태 검사와 혼동하지 않는다.

## 공개 스킬·OSS 후보 조사

[고정 판본·라이선스·유지보수 메타데이터](public-candidates.json)를 보존했다. [openai/skills의 threat-model 스킬](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/security-threat-model)은 근거 중심 위협 모델 후보, [OWASP Threat Dragon](https://github.com/OWASP/threat-dragon/tree/72ea3b18876de21831ec21c0df18a71a9a795af4)은 위협 모델 편집 도구 후보로 조사했다. 실제 읽은 범위는 각각 SKILL.md 또는 README, 라이선스와 GitHub 메타데이터다. 외부 스킬 지시 적용·스크립트 실행·설치·본문 재배포·코드 도입은 없다. 기존 24행 정본과 생성기를 유지했다. 후보 조사 자체를 도구 검증이나 이 저장소의 보안 보증으로 세지 않는다.

## 검토와 실행의 구분

새 `threat_review_refresh_check.py`는 이전 바이트 해시·대체 관계·변경 참조 수와 AST로 추출한 `render_review`의 이력/낡은 파일 표시·입력 불변성을 검사한다. 기존 `threat_trace_mapping_check.py`의 네 시험을 수정하지 않고 실행한다. 실제 실행·독립 Gemini 판정·병합 여부는 작업 보고에서 확인한다. 제품 스택·계정·PJ1·배포는 이번 범위에 없다.

## WBS 불일치

백로그의 「동결 해시 갱신」만으로는 현재 의미 변경을 표현하지 못한다. 20개 파일을 검토하고 특히 관할 팩 기본 비활성·공급자 보증 선택·출처 증명 미제공·공개 오탐 보고를 정정한 뒤 참조를 고정했다. 전체 요구 충족·배포 검수 완료는 선언하지 않는다.
