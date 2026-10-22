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
7. 첫 수정 push `6e46483`의 원격 정적 검사는 통과했지만 연구 CI에서 캐시 만료 시험 4개 하위 조건이 실패했다. 새 runner의 monotonic 값이 300초 미만이면 `checked=0`도 만료 시각이 아니었다. `12660fb`는 고정 시계로 299초의 캐시 유지와 300초의 재조회, 오류 및 원본 데이터 보존을 확인한다. 제품 TTL은 변경하지 않았다. 수정 전 원격과 같은 실패를 고정 시계 120으로 재현했고 수정 후 전체 32건이 통과했다.

## 원격 재검증에서 추가로 확인한 빌드 실패

`6df34f7`의 [연구 CI](https://github.com/MCP-governance/mcp-gateway/actions/runs/39583348640)는 성공했고, [전체 검증](https://github.com/MCP-governance/mcp-gateway/actions/runs/39583348818)의 정적 검사도 성공했다. 전체 검증은 `runtime.Dockerfile`의 Python 패키지 설치 단계에서 실패해 실제 스택 시험에 도달하지 못했다.

공식 PyPI의 `postgres-mcp==0.3.0` 배포 메타데이터는 `pglast==7.2.0`을 요구한다. 현재 PyPI에는 정규화된 `7.2` 배포도 없으며 Linux/Python 3.12 대상 설치 계획 검사에서 같은 의존성 오류를 재현했다. 이는 Gateway 자체의 `pglast==7.21` 고정과 별개인 upstream PostgreSQL MCP 가상환경의 문제다.

CI가 조용한 빌드만 사용해 설치기의 상세 오류가 사라졌으므로 실행 전 명시적 `--progress plain` 빌드를 추가했다. 실패를 무시하거나 검사를 제거하지 않는다. 공식 소스의 같은 7.2 판본을 별도 빌드 단계에서 wheel로 만들도록 변경했다. 최종 실행 이미지에 컴파일러를 추가하지 않으며, PostgreSQL MCP 판본과 계약, 실행 옵션은 유지한다. 실제 설치는 정상 의존성 해석을 거치고 모든 가상환경에 `pip check`, PostgreSQL 환경에 parser 판본과 `SELECT 1` 파싱 검사를 적용한다. 새 원격 실행 전에는 전체 검증 성공으로 기록하지 않는다.

- [공식 pglast v7.2 소스](https://github.com/lelit/pglast/tree/eed764e2160222e40499061b02870328e4a3ed33): commit `eed764e2160222e40499061b02870328e4a3ed33`, GPL-3.0-or-later.
- libpg_query 하위모듈 commit `27b2af9474003da843fb93bba59fe4297841291b`를 checkout 후 재확인한다.
- 빌드 도구는 setuptools 80.9.0과 wheel 0.45.1로 고정했다.
- Gateway 자체의 parser 판본과 upstream 서버 parser 판본은 서로 다른 가상환경이다. upstream 요구사항을 무시하는 설치나 최신 parser로의 임의 대체는 사용하지 않는다.

`09eb889`의 로컬 macOS/Python 3.13 소스 빌드는 최신 SDK의 `strchrnul` 선언 차이로 실패한 뒤, 로컬 빌드에만 `CPPFLAGS=-DHAVE_STRCHRNUL`을 주어 7.2 wheel 생성과 `==7.2.0` 의존성 설치, `pip check`, 정상 SQL 4종 및 잘못된 SQL 거부를 확인했다. 이 플래그는 Dockerfile에 추가하지 않았다. Dockerfile RUN 7개의 shell 구문은 통과했지만 Linux/Python 3.12 빌드 성공은 원격 CI 확인 전까지 미검증이다.

## 실제 스택 시험 도달 뒤의 보완

`05365c0`의 [원격 실행](https://github.com/MCP-governance/mcp-gateway/actions/runs/39584673772)에서 연구 CI, 정적 검사, Linux 이미지 빌드와 `console.sh up --no-llm`은 성공했다. 따라서 위 pglast 소스 빌드는 실제 CI에서도 확인됐다. 이어진 전체 시험은 `app.integrations` 자체 검사에서 멈췄다.

시험 입력이 새 command helper 확인 항목을 포함하면서 그 항목을 활성화하는 `command_settings_checked` 표식은 빠뜨려 현재 장치 판정과 일치하지 않았다. `a319286`은 실제 heartbeat가 저장하는 입력 형식에 맞춰 자체 검사만 보완했다. 제품의 만료 또는 권한 조건을 완화하지 않는다. 구형 장치와 점검 항목 누락, 179초 정상과 180초 만료 조건을 확인했고 자체 검사를 CI 정적 단계에서도 실행하도록 했다.

같은 실행의 컨테이너 로그에는 도입 검증 작업자의 `supplier_metadata` import 실패가 있었다. `0c229eb`는 이미지의 COPY 누락을 복구하고 최종 사용자/작업 경로에서 `import intake_worker`를 빌드 중 실행한다. COPY 대상만 모은 임시 디렉터리에서 정상 import와 해당 파일 제거 시 동일 실패를 재현했다. 소스 디렉터리를 통째로 시험에 연결했을 때 가려지는 패키징 누락을 잡는 검사다.

같은 원격 로그에서 등록 동기화와 스키마 적용 사이의 DB 교착이 한 번 발생했다. Gateway 재시작 후 기동 완료와 health 200을 확인했다. 이 기동 경합은 이번 자체 검사 실패의 직접 원인이 아니며, 아직 수정하거나 해소를 입증하지 않았다.

## 수용 시험의 권한 및 신청 입력 정정

`3258141`의 [원격 전체 검증](https://github.com/MCP-governance/mcp-gateway/actions/runs/39585880126)은 연구 CI, 정적 검사, 이미지 빌드 및 기동과 `integrations` 자체 검사를 통과했다. Gateway 수용 시험은 6통과/17실패/0생략으로 중단됐다. 이전 보고의 로컬 통과나 빌드 성공을 실제 기능 통과로 대체하지 않는다.

- MCP 호출 시험이 `/api/session`에서 받은 Console 전용 토큰을 재사용해 모든 MCP 요청이 403으로 거부됐다. 기존 OAuth 발급 경로로 MCP용 토큰을 별도 발급하고 MCP 요청에만 사용하도록 보완한다. 관리 API에는 Console 토큰을 유지하며 제품 scope 검사를 완화하지 않는다.
- 원격 도입 신청 두 곳은 필수 `requested_tools`를 빠뜨려 422였다. 실제 사용할 `fetch`를 명시한다. 도구 선택을 생략할 수 있도록 제품 입력 조건을 바꾸지 않는다.

대역 회귀 6건은 네 합성 사용자별 Console/OAuth 발급 분리, OAuth 거부 전파, SDK와 직접 MCP 요청의 토큰, 등록 해제 전 관리 DELETE와 후속 MCP POST의 권한 구분, 두 신청의 `requested_tools`를 확인했다. 실제 IdP와 DB, MCP 실행의 성공 증거는 아니며 원격 수용 시험 재실행이 필요하다.

## 로컬 사전 검증

- CI 전체 pyflakes 통과. 수정 import 관련 시험 48건 통과.
- 분류기 자체 검사 통과(저장소 registry 지정). SQL 응답 경계 6건과 멱등성 12건 통과. 고정 의존성 설치 계획 확인 통과.
- 결과 계약 18건, 관리형 경계 10건, 협업 콘솔 32건 통과.
- 기업 분석 0오류/0경고, 코드 참조만 갱신하는 회귀 3건 통과. 80개 요구사항과 50개 통합 조건의 비소스 필드 불변 확인.
- 시스템 지표 10, 카탈로그 4, OAuth 7, 보안 경계 6, 엔드포인트 목록 6, 모델 사전검사 5건 통과.
- Shell/JavaScript 구문과 콘솔 상태 19건, 인증 경계와 화면 문구, 배치 키트 17건, 하네스 4종의 10개 서버 렌더링 검사 통과.
- compose 구성만 읽어 34개 서비스의 망/포트/키 경계 통과. 로컬 솔루션 스택은 시작하지 않았다.

이 보고는 push 전 로컬 사전 검증 기록이다. 원격 완료 조건 전체 검증은 [해당 브랜치 Actions](https://github.com/MCP-governance/mcp-gateway/actions?query=branch%3A10%2F21-sheet-runtime-completion)의 정확한 commit과 conclusion으로 판정한다. CI 건너뛰기, continue-on-error, 알림 해제 또는 과거 독립 검토 해시 덮어쓰기는 하지 않았다. 지정 실기기 배포와 사용자 검수, 시트의 진척률은 그대로 미확인/기존 값이다.
