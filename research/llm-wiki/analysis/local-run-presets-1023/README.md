# 공식 MCP의 PC 격리 실행 기본값 — 근거와 한계

D-206 · 기준 `origin/main` `e30be96`, 브랜치 `10/23-local-run-presets`. [작업 보고](../../status/reports/2026-10-23-local-run-presets.md).
구현은 `full_stack_lab/gateway/app/intake_proposal.py`의 `LOCAL_RUN_PRESETS` 한 곳이다. 이 문서는 표의 각 값이 어느 공식 문서 어느 행에서 왔는지 남긴다.
실제 MCP 실행 증거가 아니다. 이미지 digest를 이번 작업에서 확인하지 않았고(`pinned_image`가 승인 때 Docker Hub에서 고정한다), 컨테이너를 띄우지 않았다.

## 확인한 자료

[sources.json](sources.json): `modelcontextprotocol/servers` main `51b6382a3e827aceb6bce430b1208d69b93d95ea`(2026-10-19T06:37:30Z)의
`src/<서버>/README.md` 5개, 확보 2026-10-23, SHA-256·바이트 수 기록. 원문은 ignored `local-sources/local-run-presets-1023/`에만 두고 저장소에는 해시와 행 번호만 남긴다
(문서는 CC-BY-4.0, 코드는 MIT→Apache-2.0 전환 중이라는 같은 판본 LICENSE의 문장 확인). README 안의 설치·실행 지시는 분석 데이터로만 읽었고 실행하지 않았다.

## 값과 근거

| 경로 | 기본값 | README 근거(위 판본의 행) | 우리 쪽 차이·한계 |
| --- | --- | --- | --- |
| `src/filesystem` | 이미지 `mcp/filesystem`, 인자 `/workspace/mcp-docs`, 폴더 `mcp-docs:ro` | 232~235 "허용 디렉터리는 마운트로 준다, `ro`를 붙이면 읽기 전용", 246~250 Docker 예시(`--mount … ro`, 마지막 인자가 허용 디렉터리), 374~377 `mcp/filesystem` 이미지 이름 | README는 `/projects` 아래를 쓰지만 우리 실행기는 컨테이너 안 마운트 위치를 `/workspace/<경로>`로 고정한다(D-192 후속, 10-22). 인자도 그 경로를 쓴다. 폴더 이름 `mcp-docs`는 10-22 PJ1 실측과 같은 관례 이름 |
| `src/memory` | `mcp/memory`, 인자 없음, 폴더 `mcp-memory:rw`, 환경 `MEMORY_FILE_PATH=/workspace/mcp-memory/memory.json` | 155~165 Docker 예시(영구 볼륨을 `/app/dist`에 붙임), 243 `MEMORY_FILE_PATH` 설명, 247 쓰기 잠금 파일 `<파일>.lock`이 같은 폴더에 생겨 폴더가 쓰기 가능해야 함, 359~362 `mcp/memory` | 우리 실행기는 호출마다 새 컨테이너라 볼륨 이름 대신 홈 아래 폴더를 rw로 붙인다. README 예시의 파일명은 `memory.jsonl`이고 기본값도 `memory.jsonl`이다. 표는 10-23 PJ1에서 실제로 저장·재조회가 통과한 `memory.json`을 쓴다(확장자가 달라도 JSONL로 읽히는지는 문서로 확인하지 못했고 실측에 의존) |
| `src/sequentialthinking` | `mcp/sequentialthinking`, 인자·폴더·환경 없음 | 117~133 Docker 예시(`docker run --rm -i mcp/sequentialthinking`), 135 `DISABLE_THOUGHT_LOGGING`(선택) | 상태를 저장하지 않는다. 선택 환경 변수는 제안하지 않는다 |
| `src/git` | `mcp/git`, 인자 `--repository /workspace/mcp-repo`, 폴더 `mcp-repo:ro` | 137 `--repository`가 허용 범위(밖 `repo_path`는 오류), 111 범위 밖 `repo_path` 오류 동작, 157~165 Docker 예시, 370~374 `mcp/git` | README Docker 예시는 `--repository` 없이 호출마다 `repo_path`를 받는다. 우리는 폴더를 하나로 좁힌다. 읽기 전용 마운트라 쓰기 도구(add·commit)는 실패한다. 읽기 전용에서 `git status`와 저장소 소유자·`safe.directory` 불일치 동작은 문서로 확인하지 못해 기기 시험이 필요하다 |
| `src/time` | `mcp/time`, 인자·폴더·환경 없음 | 84~95 Docker 예시(`-e LOCAL_TIMEZONE`), 211 `--local-timezone`으로 덮어쓰기, 322~326 `mcp/time` | 시간대를 지정하지 않으면 컨테이너 기준(보통 UTC)이다. 기본값으로 시간대를 정하지 않는다 |

공통: 근거 설명(`reason_text`)과 구분(`reason_kind`)도 표에 두며(예: `local_file`), 관리자가 바꾼다.

## 제안이 넓히지 않는 것

- 공식 저장소 URL(`https://github.com/modelcontextprotocol/servers`, `.git`·끝 슬래시·대소문자 무시)과 위 경로가 모두 맞을 때만 제안한다. 같은 경로의 다른 저장소는 빈 제안이다.
- 제안은 화면 초기값이다. 저장 요청은 `LocalRunSpec`과 `manifest_errors`(홈 아래·점으로 시작하지 않는 상대 경로, 로더 계열 환경 변수 거부), 허용 이미지 저장소, digest 고정, 서명 생성을 그대로 거친다.
- rw 기본값은 `src/memory` 하나이며 `local_run_presets_check.py`가 고정한다.

## 공백

`mcp/*` 이미지가 실제 digest로 고정되고 각 기본값 그대로 `initialize`·`tools/list`·대표 호출이 통과하는지, git의 읽기 전용 동작, 폴더 이름이 PC에 없을 때의 승인 실패 문구는 기기·PJ1에서 확인되지 않았다.
