# 개발 백로그

완료 조건이 있는 개발 작업을 이 목록에만 유지합니다. 지금의 상태는 연구·시험 설계 기준이며 솔루션 코드·운영 시험 완료를 뜻하지 않습니다.

| ID | 작업 | 근거 | 완료 조건 | 상태 |
| --- | --- | --- | --- | --- |
| WIKI-01 | 개발 위키와 공유 보고 체계 | [위키](../README.md), [협업 콘솔](../../collaboration-console/README.md) | 자료 분류·원본·해시·MD·Claude 규칙·실제 협업 기록·검사 통과 | MD 정본·협업 콘솔 구축, 실제 Claude 분석 수신; 수정 후 Claude 리뷰는 계정 한도로 미완료 |
| DEV-01 | 실제 관리형 하네스 증거 연결 | [실기기 결과](reports/2026-10-13-development-results.md), [통제 증거](../methodology/control-design.md) | 활성화 상태와 fresh 신원, model→MCP→원장 IDs, 정상/차단의 독립 효과 | 새 PJ1 Codex 세션2개·원장3건 일치. 공급자 quota 응답·PII 차단 확인; 정상 문서·독립 수신 trace는 미완료 |
| DEV-02 | 계약 변경·오염 탐지 코퍼스 | [분석](../solutions/README.md), [실험](../experiments/README.md) | 다국어 정상/공격/인코딩 표본, 오탐·미탐 및 계약 diff, 검사기 장애 차단 | 조사·설계 |
| DEV-03 | 원본 위협표와 구현 추적 검토 | [위협 매핑](../threats/README.md) | 24개 정책의 통제 위치·코드·실험·한계별 리뷰와 근거 | 매핑 초안, 독립 리뷰 필요 |
| DEV-04 | 승인 재사용·경쟁 조건 | [PAC 설계](../../../docs/ai/PAC_RUNTIME_2026-10-01.md) | 변형 요청·중복 동시 호출·철회 경쟁의 정확한 효과 수와 판정 | 설계·새 실험 미실행 |
| DEV-05 | OAuth 대상·scope·철회 검증 | [논문·명세](../papers/README.md) | 다른 audience·scope·만료·철회 입력의 전송 전 차단과 정상군 | 조사·설계 |
| DEV-06 | 응답 통제와 실행 증거 분리 | [통제 설계](../methodology/control-design.md) | masked/held/released 결과와 upstream 실제 실행을 별도 보고 | 설계·새 실험 미실행 |
| DEV-07 | 상용·OSS 비교 재현 | [제품 분석](../solutions/README.md) | 같은 도구·정상군·공격군·검사기 장애·독립 효과의 비교표 | 소스/문서 분석 완료, 실행 미실행 |
| DEV-08 | 종료 C3/C4의 자원 서버 차이 | [종료 모델](../../../docs/ai/TERMINATION_MODEL.md) | introspection TTL·캐시·발급 토큰의 재접근과 T1~T3 증거 | 문서·설계 |
| DEV-09 | 한국어 PII/Secret 평가 | [PII/Secret 도입](../../../docs/ai/OSS_ADOPTION_2026-10-03.md) | 합성 한국어 표본의 탐지·마스킹·성능·scanner fail closed | 설계 |
| DEV-10 | field 포트 배치와 CI 기대값 대조 | [실패 CI](https://github.com/MCP-governance/mcp-gateway/actions/runs/38346569656), [이전 동일 실패](https://github.com/MCP-governance/mcp-gateway/actions/runs/37201934077) | Caddy+모델 프록시의 정확한 서비스·Tailnet 주소·포트·프로토콜 집합, 임의 게시 거부 | 수정·양/음성 포함 17건 로컬 통과; 새 CI 결과는 작업 보고 참조 |
| DEV-11 | CPU·메모리·연결 지연 | [설계](reports/2026-10-13-feature-design.md) | 관리자·Console scope, 실제 /proc·고정 TCP 경로, 결측·오래된 값·CPU 긴 간격 제외 | API/UI 구현·백엔드/표시 회귀 통과, 실기기 결과는 작업 보고 참조 |
| DEV-12 | 계약 A→B→A 관측값 일관성 | [코드](../../../full_stack_lab/gateway/app/core.py), [회귀](../../../full_stack_lab/tests/catalog_refresh_check.py) | 복귀 시 관측값 A, 재승인도 A, 동일 연속 조회 최적화·서버 격리 | 수정 전 2/4 실패 재현, 수정 후 4/4 통과 |
| DEV-13 | 새 감사 기록 시각 무결성 | [회귀](../../../full_stack_lab/tests/security_edges_check.py) | 새 v7의 created_at 변조 검출·UTC 정규화, 기존 v1~6 검증 유지 | 수정·회귀 통과; 과거 체인의 시각 무결성은 소급 보장 불가 |
| DEV-14 | 결과의 디코딩된 줄바꿈 검사 | [회귀](../../../full_stack_lab/tests/security_edges_check.py) | MCP text와 structuredContent의 위조 대화록, 정상 로그·크기/형식 대조 | 수정 전 우회 재현, 수정 후 통과 |
| DEV-15 | 목적지 정책 데이터 실패 차단 | [회귀](../../../full_stack_lab/tests/security_edges_check.py) | None/결측/잘못된 타입은 거부, 명시적 빈 목록·허용 호스트 정상군 | 수정 전 잘못된 허용 재현, 수정 후 통과 |
| DEV-16 | refresh 회전·계열 철회 경쟁 | [실기기 결과](reports/2026-10-13-development-results.md), [Claude 후보 B5](reports/2026-10-13-claude-code-review.md) | 동일 계열의 회전·발급·재사용/철회를 트랜잭션 안에서 직렬화, 실패 롤백 | 수정·단위7건·솔루션 실제 PostgreSQL3건·전체CI 통과 |
| DEV-17 | 승인 후 신선한 요청자 인증 | [Claude 후보 B2](reports/2026-10-13-claude-code-review.md) | 만료 검증을 완화하지 않고 승인과 새 요청자의 실행을 연결, 현재 권한·철회 재검증 | 설계; 만료 토큰 거부는 유지 |
| DEV-18 | 엔드포인트 수집 신선도·전체 집계 | [Claude 후보 B7](reports/2026-10-13-claude-code-review.md) | 최근 200건 목록과 전체 집계를 구분, 수집기 마지막 성공·실패·감사 경로 표시 | 목록·범례를 수신/최근 200건으로 수정; 전체 집계·수집 신선도는 후속 |

변경할 때 작업 보고서를 연결하고 `완료`의 검증 층을 함께 씁니다. 소스·문서 확인만 끝났으면 실행 검증 완료로 올리지 않습니다.
