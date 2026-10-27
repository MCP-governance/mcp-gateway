# 승인 소스의 Linux PC 빌드 — DEV-73 / D-263

기준 `7d49a873776eacaec180f5445138b76f7e4be1a7`, 브랜치 `10/27-kit-source-linux`, 2026-10-27.
구현 정본은 게이트웨이 `local_jobs.py`·`local_sources.py`·`agent_service.py`와 `endpoint-agent/local-runner.py`다.
[원자 요구사항](requirements.json)은 코드 심볼·현재 행·판본과 독립 시험을 연결한다.
대역 시험을 실제 MCP·빌드·네트워크 격리의 효과 증거로 세지 않는다. [결과 보고](../../status/reports/2026-10-27-kit-source-linux.md)

| 조건 | 검증 경로 | 확인 범위 |
| --- | --- | --- |
| 정상 | 검증한 저장소 → 고정 레시피 → source 서명 → 장치 수신 → 트리 해시 → 빌드 → 이미지 ID | 함수 단위/DB·HTTP·엔진 대역 |
| 음성·경계 | image+source, 커밋·해시·레시피 ID 형식, 16,384자 초과, 미고정 FROM, 원격 ADD, 잘못된 태그/라벨, 크기 상한 | 양쪽 검증기와 실행기 |
| 실패 | 해시 불일치, 레시피 없음·교체, 빌드 실패·시간 초과·취소, 구형 Python | 빌드 호출 없음 또는 클라이언트 kill/wait |
| 경쟁 | 다운로드 중 승인 철회·정책 세대 교체, 승인 직전 소스/레시피 교체 | 전후 재확인 및 intake FOR SHARE 경로; 실제 PostgreSQL 경합 미실행 |
| 복구 | 캐시 재사용, p 준비 요청, 기존 사전 준비 함수 재사용 | 전체 라벨과 ID 확인, UID 제한, 재조회 경로; 실제 서비스 소켓 미실행 |

## 재사용 근거와 외부 조사

- 기존 `runtime/worker.py::load_recipes`, `runtime/recipes/markitdown-mcp.*`, `provenance.py::archive_digest`를 위 기준 커밋에서 읽었다. 레시피 해시는 기존 TOML+NUL+Dockerfile 알고리즘을 재사용한다. 장치 코드는 표준 라이브러리와 기존 엔진 CLI만 사용하며 새 SDK/의존성은 없다. MarkItDown은 기존 MIT OSS 대상이며 새 MCP나 모의 MCP 서버를 만들지 않았다.
- [Python 3.10 tarfile 공식 문서](https://docs.python.org/3.10/library/tarfile.html): 데이터 필터는 보안 업데이트로 역이식되므로 버전 숫자 대신 `data_filter` 존재를 확인한다. 필터가 없으면 중단한다. 새 임시 폴더·크기·파일 수 제한을 별도로 적용한다. 보관본과 트리의 바이트 해시는 별개다.
- [Dockerfile 공식 명세](https://docs.docker.com/reference/dockerfile/): FROM의 digest 고정, ADD의 URL 입력, 다단계 FROM을 확인했다. 임의 프런트엔드·escape 지시자는 검증기 해석을 바꾸므로 이 경로에서 거절한다.
- 공개 스킬 후보 [docker/skills](https://github.com/docker/skills), `docker-build-strategies/SKILL.md`: Apache-2.0 표기와 공개 내용만 검토했다. 최신 commit과 현재 유지보수 상태는 원격 Git/API/커밋 조회 실패로 고정하지 못했다. 스킬 설치·스크립트 실행·코드 복사는 하지 않았다. 외부 프런트엔드 지시자나 로컬 스택 기동 지시는 이 작업에 적용하지 않았다.
- OSS 후보 [docker/build-push-action](https://github.com/docker/build-push-action): Apache-2.0 표기와 Buildx 기반 CI 역할을 확인했다. 제공된 커밋 페이지는 2026-03-05 캐시여서 최신성 근거가 아니며 최신 commit 미확인으로 기록한다. 장치 런타임에는 채택하지 않았고 기존 엔진 CLI를 유지했다.

## 남은 검증

실제 Gitea 다운로드, FastAPI 의존성까지 포함한 요청, Ed25519 서명 왕복, 안전한 tar 필터의 실제 압축 해제, Docker/Podman 빌드·취소·라벨/ID·실행 격리, Linux 소켓과 하네스, PostgreSQL 경쟁은 지정 환경에서 확인해야 한다. 로컬은 Python 3.10.5이며 CPython 3.12용 기존 가상환경은 실행할 수 없었다. 구형 Python에서 필터 없는 압축 해제를 거부하는 것은 시험했다.
