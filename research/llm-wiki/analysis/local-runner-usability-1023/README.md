# 로컬 MCP 정상 기능 결함 — 요구사항·근거·검증

W14-LOCAL-RUNNER / DEV-73 / D-192 후속 / D-199. 기준 `0f57d0c9c0994faf849544616c6e66939b113fd8`,
브랜치 `10/23-output-fp`의 미커밋 변경이다. [작업 보고](../../status/reports/2026-10-23-local-runner-usability.md).
이 문서는 구현과 오프라인 시험의 분석 정본이며 실제 MCP 실행 증거가 아니다.

## 관찰과 수정 범위

사용자가 제공한 10-23 01:50 PJ1 Docker 29.8.1 실사용 시험에서 첫 이미지 수신이 5초 수령 임대를 넘었고,
`mcp/git`·`mcp/time` 실행 파일 권한 거부가 일반 RuntimeError 문구로 사라졌다.
filesystem·memory·sequentialthinking 정상은 사용자 제공 관찰이며 이번 세션에서 재현하지 않았다.
이미지 digest·원장·컨테이너 로그 원문은 제공되지 않았으므로 이미지 이름만으로 전체 판본의 속성을 단정하지 않는다.

| 원자 요구 | 구현·이유 | 정상·음성·경계·실패·경쟁·복구 조건 | 시험·효과와 공백 |
| --- | --- | --- | --- |
| 첫 이미지 준비 동안 유효한 수령 유지 | `local_jobs.exchange`는 승인 관찰 초기화에 준비 180초를 배분. 일반 요청은 원래 전체 기한 안에서만 준비 시간을 배분. `validate_job` 제어 조회에서 실행 전 5초 임대를 갱신 | 캐시 있으면 수신 생략; 미승인 저장소·tag 거부; 절대 준비 상한 180초; 제어 장애·정책/장치/철회 변경 시 실패; 만료 임대 부활 금지 | `ExchangeBudget`, `ImagePreparation`, `GatewayControl`의 대역 시험. 기존 `dev73` 계약·철회·복구 시험 유지. 실제 느린 이미지 수신·DB 경합은 미실행 |
| 준비 후 실제 실행 제한 유지 | `local_jobs.run_seconds`에 원래 제한 저장. 시작 승인에서 deadline·lease_until을 원래 제한(최대 20초)으로 축소. 실행기는 시작 응답의 deadline 사용 | 2.5초 요청을 20초로 늘리지 않음; 일반 상태 점검 5초·호출 90초 전체 기한 보존; 중복 시작·이미 시작된 작업의 준비 임대 갱신 금지 | 원래 기한 저장·SQL 파라미터·축소 응답·실행 순서 시험. 실제 PostgreSQL 마이그레이션·타이머 정밀도 미검증 |
| 승인 저장소·digest·서명 경계 보존 | `engine_configuration`, `image_allowed`, `signed`, `check_control`; 기존 `--pull=never` 실행 플래그 유지 | 변경 tag·유사 저장소 이름 거부; 추가 VOLUME·엔진 판본 불일치 거부; 서명/세대/소유 계정 불일치 거부 | 새 음성군·기존 `dev73_rework_check` 통과. Ed25519 양쪽 검증인 `local_run_manifest_check`는 현재 환경 의존성 부재로 시작 실패 |
| 종료 진단 수집과 비밀 보호 | 표준 오류를 별도 스레드에서 4096바이트 순환 버퍼로 수집. 마지막 5줄·300자, 긴 행과 불완전 첫 행 생략. 알려진 비밀·자격 문맥을 가리고 게이트웨이 기존 출력 오염·Secret 검사 적용 | EOF·즉시 종료·권한 거부; 무개행 대량 출력; 토큰/비밀번호·제어 문자·지시문; 검사 실패는 오류 본문 숨김; 진단 조회 실패에도 제거 시도 | `DiagnosticCapture`, `GatewayControl` 통과. 검사는 대역이며 실제 Gitleaks 검증은 미실행. 알려지지 않은 자격 패턴의 검출 완전성은 보장하지 않음 |
| 게이트웨이·승인 화면까지 한국어 오류 전달 | 검사한 메시지를 `local_jobs.error`와 append-only `local_job_events.evidence.failure`에 같은 값으로 저장하고 해시. 해당 사건이 있는 오류만 `LocalExecutionError`로 전달. 콘솔은 기존 textContent 경로 사용 | 원시·이전 예외는 기존 일반 오류 경계 유지; 해시 입력과 저장 메시지 동일; 정지 미확인 결과는 거부; 화면은 HTML로 해석하지 않음 | 타입 경계·저장/해시·사건 대역 시험과 콘솔 상태 15건 통과. 실제 HTTP/브라우저 승인 화면·MCP 호출 미검증 |
| root 전용 이미지 우회 실행 금지 | 실행 권한 거부를 한국어 분류하고 모든 엔진에서 관리 UID 유지. 생성 시 자동 삭제를 빼 종료 상태를 읽은 뒤 명시적으로 제거 | Docker host·remap·Podman auto 모두 UID 0 선택 없음; 한 번만 생성/시작; 회수는 엔진 부재 확인; 재접속은 실행 재시도 없이 이전 작업 회수 | 생산 Session 코드에 엔진 대역을 연결한 즉시 실패·종료 코드 126·명시적 rm 시험. 실제 이미지의 파일 모드·rootless 실행은 미확인 |

실제 코드 심볼·행·파일 해시와 실행 결과는 옆의 [구조화 검증 기록](evidence.json)에 둔다.
소유자 요구의 원자 추적용 문서이며 새 정책 ID나 실기기 통과 건수를 만들지 않는다.

## 공식 문서·공개 OSS·스킬 대조 (확인 2026-10-23)

| 자료·판본 | 확인 범위·라이선스·유지보수 | 적용과 한계 |
| --- | --- | --- |
| [Docker userns-remap](https://docs.docker.com/engine/security/userns-remap/) | 공식 운영 문서의 UID 범위·데몬 설정·기존 저장소 영향·바인드 권한 부분. 문서 최신 경로이며 commit 미확인, 전문 재배포 없음 | 컨테이너 내부 root와 호스트 root 분리 원리·설치 선택지 설명에만 사용. 호스트 설정을 자동 수정하거나 root 재시도를 구현하지 않음 |
| [Podman v5.6.2 rootless 튜토리얼](https://github.com/containers/podman/blob/v5.6.2/docs/tutorials/rootless_tutorial.md), [공식 rootless 설명](https://docs.podman.io/en/latest/markdown/podman.1.html#rootless-mode) | v5.6.2 태그의 관리자 준비·subuid/subgid와 rootless 사용자 범위, 공식 CLI 설명을 대조. Apache-2.0 저장소, commit SHA 조회는 실패하여 태그 수준 고정. 실행 판본의 권고가 아니라 의미 확인용 참고 | root 서비스의 `podman --userns=auto`를 rootless라고 부르지 않음. 별도 엔진 계정·저장소·마운트·회수 경로가 필요한 한계를 설치 문서에 명시. 코드 복사·설치·엔진 전환 없음 |
| [docker/skills](https://github.com/docker/skills), [카탈로그](https://raw.githubusercontent.com/docker/skills/main/catalog.yaml) | 공개 스킬 우선 탐색. 카탈로그 0.3.1·Apache-2.0·활성 이슈/변경 이력 표시를 확인했으나 특정 스킬 본문과 commit SHA는 확보하지 못함. 유지보수 표시를 독립 품질 증거로 세지 않음 | Docker/Compose·디버깅 워크플로 후보를 찾았지만 이번 수정은 기존 CLI·Python 표준 라이브러리 연동 범위. 외부 스킬 설치·스크립트 실행·코드 도입 없음 |

새 의존성과 자체 MCP 서버는 추가하지 않았다. Python subprocess·threading·queue와 기존 게이트웨이 Secret 검사·
장치 인증 경로를 재사용했다. 과거 검토 해시는 보존하고 현재 후보 매핑만 재생성하며, 독립 검토 완료로 승격하지 않는다.

## 미해결 범위

실제 Docker 29.8.1·공식 이미지의 느린 수신/즉시 종료와 실제 PostgreSQL의 임대·시작·회수 경쟁 검증은 리더에게 남긴다.
일반 요청은 원래 전체 기한을 넘겨 대기하지 않으므로 그 안에 이미지를 받지 못하면 차단된다.
rootless Podman은 설치 안내 선택지이며 현재 root 서비스의 실제 지원 경로가 아니다. 사용자 재매핑을 켜도
관리 UID를 그대로 쓰기 때문에 root 전용 이미지가 자동 실행되지는 않는다. 기존 경로 마운트의 생성~시작 교체 경쟁과
이미지 서명 미확인 등 D-192의 한계도 해결했다고 주장하지 않는다.
