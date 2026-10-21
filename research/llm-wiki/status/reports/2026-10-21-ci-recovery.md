# 2026-10-21 GitHub CI 실패 진단과 수정

## 확인한 실패

사용자의 실패 메일 제보 뒤 실제 Actions 기록을 확인했다. 앞선 작업 종료 때 원격 CI 결과를 확인하지 않은 누락을 정정한다. 로컬 회귀와 push 성공은 CI 성공을 의미하지 않는다.

- 작업 브랜치 `262f5eb`: [정적 검사 실패](https://github.com/MCP-governance/mcp-gateway/actions/runs/39581739693), [연구 검사 실패](https://github.com/MCP-governance/mcp-gateway/actions/runs/39581739702).
- 시작 main `2045799`: [정적 검사 실패](https://github.com/MCP-governance/mcp-gateway/actions/runs/39556298220), [연구 검사 실패](https://github.com/MCP-governance/mcp-gateway/actions/runs/39556298129).
- 앞선 두 번의 push에서 워크플로 두 개씩 실패했다. 원본 main에서도 같은 단계가 실패했다는 사실은 수정이나 확인을 생략할 근거가 아니다.

## 수정

1. CI와 같은 전체 pyflakes 명령에서 나온 미사용 import 두 개와 중복 import 한 개를 수정했다. 이전에는 변경 파일만 확인해서 이 오류를 놓쳤다.
2. `pglast==7.11`은 공식 PyPI 버전 조회가 404이고 설치할 수 없다. 동일 주버전의 [7.21](https://pypi.org/project/pglast/7.21/)로 고정했다. 이미 사용한 로컬 판본과 일치하며, 제품 requirements도 이제 이 판본을 사용한다. 이전 보고의 '제품 의존성 무변경'은 이 수정 전 기록이다.
3. 기업 분석의 현재 구조 참조 153개가 오래된 소스 해시와 행을 가리켰다. 현재 코드 참조만 갱신하고 과거 시험/실행/상태 필드는 보존했다. [별도 보고](2026-10-21-enterprise-source-refresh.md).
4. 결과 계약 시험은 사용자 중지 만료 처리의 DB 호출 때문에 원래 주입한 조회 예외까지 도달하지 못했다. 해당 경계를 대역하고 의도한 조회와 예외 도달을 단언했다. 이제 로컬 회귀의 외부 DB 생략 목록에서 제외했다.
5. 협업 콘솔 시험은 원본 snapshot에 이미 있는 빈 owner 필드를 없어야 한다고 가정했다. 입력 snapshot 전체의 호출 전후 불변성을 검사하도록 바꿨다. 제품 overlay는 변경하지 않았다.
6. 관리형 경계 시험의 임시 루트만 정규화했다. macOS의 `/var` 별칭 때문에 정상 경로 시험이 먼저 실패하던 문제이며, 시험이 만든 심볼릭 링크 거부는 유지한다.

## 로컬 사전 검증

- CI 전체 pyflakes 통과. 수정 import 관련 시험 48건 통과.
- 분류기 자체 검사 통과(저장소 registry 지정). SQL 응답 경계 6건과 멱등성 12건 통과. 고정 의존성 설치 계획 확인 통과.
- 결과 계약 18건, 관리형 경계 10건, 협업 콘솔 32건 통과.
- 기업 분석 0오류/0경고, 코드 참조만 갱신하는 회귀 3건 통과. 80개 요구사항과 50개 통합 조건의 비소스 필드 불변 확인.
- 시스템 지표 10, 카탈로그 4, OAuth 7, 보안 경계 6, 엔드포인트 목록 6, 모델 사전검사 5건 통과.
- Shell/JavaScript 구문과 콘솔 상태 19건, 인증 경계와 화면 문구, 배치 키트 17건, 하네스 4종의 10개 서버 렌더링 검사 통과.
- compose 구성만 읽어 34개 서비스의 망/포트/키 경계 통과. 로컬 솔루션 스택은 시작하지 않았다.

이 보고는 push 전 로컬 사전 검증 기록이다. 원격 완료 조건 전체 검증은 [해당 브랜치 Actions](https://github.com/MCP-governance/mcp-gateway/actions?query=branch%3A10%2F21-sheet-runtime-completion)의 정확한 commit과 conclusion으로 판정한다. CI 건너뛰기, continue-on-error, 알림 해제 또는 과거 독립 검토 해시 덮어쓰기는 하지 않았다. 지정 실기기 배포와 사용자 검수, 시트의 진척률은 그대로 미확인/기존 값이다.
