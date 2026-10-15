# 개발 작업별 레퍼런스 읽기 지도

2026-10-15 현재의 [연구 목록](README.md)은 167건이다. 자료 수·초록 대조·코드 존재를 제품 검증으로 세지 않는다. 아래는 기존 자료를 다음 개발 작업에 연결한 탐색 지도이며 원문 전문을 새로 정독했다는 뜻은 아니다. 새로 확인한 공식 문서의 판본·읽은 절은 [참고 자료 목록](../analysis/review-2026-10-15/references.json)에 기록한다.

| 개발 질문 | 기존 자료 | 함께 확인할 공식 자료/코드 | 결과로 남길 것 |
| --- | --- | --- | --- |
| 승인한 것과 실행한 것이 같은가 | [T15](T15.md), [LIB-J01](LIB-J01.md), J 공급망·감사 묶음 | SLSA v1.2, BuildKit provenance, [ToolHive](../solutions/toolhive-runtime.md) | source→build→image→endpoint 검증, DEV-38 |
| 요청의 신원·자격은 누구의 것인가 | [T01](T01.md), [T10](T10.md), [T11](T11.md), [T12](T12.md), E 인증 묶음 | transport 토큰·upstream 별도 자격·DB 상태 경계 | audience/scope/철회·중지 경쟁, DEV-43 |
| 스키마·프로토콜 변경을 어떻게 다룰까 | [T02](T02.md), A 명세·SDK 묶음 | 2025-11-25와 2026-07-28 차이, JSON Schema 참조 | outputSchema·배열·`$defs`·pagination, DEV-44 |
| 호스트 이름 검사로 충분한가 | [T21](T21.md), [E05](../experiments/E05-ssrf-normalization.md) | OWASP SSRF, MCP OAuth SSRF 절, 실제 서버 outbound | 빈 목적지·redirect·DNS·IPv6, DEV-41 |
| 하네스 설정만으로 우회를 막는가 | [E13](../experiments/E13-local-bypass.md), [권한 근거](../catalogs/endpoint-permission-references.json) | Claude managed hooks·AppArmor 전환·UID 방화벽 | 정상 실행과 훅/셸·비관리 계정 반례, DEV-42·35 |
| 탐지 규칙 점수가 방어 효과인가 | [P38](P38.md), [P39](P39.md), [P43](P43.md), [P60](P60.md), B/C/F 묶음 | [실제 코퍼스 평가](../status/reports/2026-10-15-inspection-corpus.md) | 출처별 분리·독립 한국어·정상 성공·공격 효과, DEV-46 |
| PII 저지연화가 탐지를 보존하는가 | H 개인정보 묶음, [한국어 평가](../status/reports/2026-10-15-inspection-corpus.md) | 실제 Presidio/Gitleaks 판본·지원 entity별 정상/음성군 | 사람명·주소 등 포함 지원범위와 탐지/마스킹 손실 |
| 종료를 완료했다고 말할 수 있는가 | [T19](T19.md), [T20](T20.md), [T22](T22.md) | [종료 모델](../../../docs/ai/TERMINATION_MODEL.md), provider 자원 거부 | 차단·세션/프로세스 정지·자격 회수·백업 복원 반례 |
| 어떤 호출이 실제 효과를 냈는가 | J 관측·감사 묶음 | OpenTelemetry MCP, [증거 계약](../methodology/evidence-contract.md) | run/request/decision/intent/endpoint/외부 효과, DEV-39·45 |
| 외부 LLM Gateway·비밀 저장소와 연결되는가 | [기업 연동](../integrations/README.md), [연동 조건](../analysis/integration-cases.json) | 제품 edition·공식 SDK·LLM 경로와 MCP 경로 분리 | 회전·철회·스트림·장애를 포함한 실제 연동 |

법령·인증이 적힌 자료는 I 묶음과 원문 적용 조건을 따로 검토한다. 국내 모델 여부나 GS·CSAP 같은 표기만으로 실제 처리 위치·MCP 실행 경로·해당 배포의 보안 승인을 추정하지 않는다. 이번 기술 위키 보강에서는 법적 적합성 판단을 하지 않았다.
