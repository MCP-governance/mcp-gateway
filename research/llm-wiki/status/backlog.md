# 개발 백로그

완료 조건이 있는 개발 작업을 이 목록에만 유지합니다. 지금의 상태는 연구·시험 설계 기준이며 솔루션 코드·운영 시험 완료를 뜻하지 않습니다.

| ID | 작업 | 근거 | 완료 조건 | 상태 |
| --- | --- | --- | --- | --- |
| WIKI-01 | 개발 위키와 공유 보고 체계 | [위키](../README.md) | 자료 분류·원본·해시·MD·웹·Claude 규칙·검사 통과 | 구축 완료, 검증은 작업 보고 참조 |
| DEV-01 | 실제 관리형 하네스 증거 연결 | [통제 증거](../methodology/control-design.md) | 활성화 상태와 fresh 신원, model→MCP→원장 IDs, 정상/차단의 독립 효과 | 실기기 미실행 |
| DEV-02 | 계약 변경·오염 탐지 코퍼스 | [분석](../solutions/README.md), [실험](../experiments/README.md) | 다국어 정상/공격/인코딩 표본, 오탐·미탐 및 계약 diff, 검사기 장애 차단 | 조사·설계 |
| DEV-03 | 원본 위협표와 구현 추적 검토 | [위협 매핑](../threats/README.md) | 24개 정책의 통제 위치·코드·실험·한계별 리뷰와 근거 | 매핑 초안, 독립 리뷰 필요 |
| DEV-04 | 승인 재사용·경쟁 조건 | [PAC 설계](../../../docs/ai/PAC_RUNTIME_2026-10-01.md) | 변형 요청·중복 동시 호출·철회 경쟁의 정확한 효과 수와 판정 | 설계·새 실험 미실행 |
| DEV-05 | OAuth 대상·scope·철회 검증 | [논문·명세](../papers/README.md) | 다른 audience·scope·만료·철회 입력의 전송 전 차단과 정상군 | 조사·설계 |
| DEV-06 | 응답 통제와 실행 증거 분리 | [통제 설계](../methodology/control-design.md) | masked/held/released 결과와 upstream 실제 실행을 별도 보고 | 설계·새 실험 미실행 |
| DEV-07 | 상용·OSS 비교 재현 | [제품 분석](../solutions/README.md) | 같은 도구·정상군·공격군·검사기 장애·독립 효과의 비교표 | 소스/문서 분석 완료, 실행 미실행 |
| DEV-08 | 종료 C3/C4의 자원 서버 차이 | [종료 모델](../../../docs/ai/TERMINATION_MODEL.md) | introspection TTL·캐시·발급 토큰의 재접근과 T1~T3 증거 | 문서·설계 |
| DEV-09 | 한국어 PII/Secret 평가 | [PII/Secret 도입](../../../docs/ai/OSS_ADOPTION_2026-10-03.md) | 합성 한국어 표본의 탐지·마스킹·성능·scanner fail closed | 설계 |

변경할 때 작업 보고서를 연결하고 `완료`의 검증 층을 함께 씁니다. 소스·문서 확인만 끝났으면 실행 검증 완료로 올리지 않습니다.
