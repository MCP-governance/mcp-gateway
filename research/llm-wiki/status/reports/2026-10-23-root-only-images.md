# 2026-10-23 루트 전용 공식 이미지(git·time) 격리 실행 불가 — W14

- 작업자: Claude Code (Sonnet 5.5, 서브에이전트)
- 코드 기준: `origin/main` `5d4c832`, 브랜치 `10/23-root-only-images`
- 시작 근거: 10-23 PJ1 실측에서 `mcp/git`·`mcp/time`이 러너 조건(관리 계정 UID)으로 실행되지 않음. D-206 표가 두 이미지도 제안하고 있었다.
- 해결할 문제와 완료 조건: 정확한 실패 지점을 실측하고, 루트 실행 없이 가능한 최소 수정을 고른다. 불가능하면 제안에서 빼고 승인 화면에 짧은 상태 문구를 보인다.

## 원인 (PJ1 실측, 2026-10-23, Docker 29.8.1, SecurityOptions apparmor·seccomp·cgroupns = 사용자 재매핑 없음)

| 이미지 | digest | 정의 | 실행 결과(러너 옵션 + `--user 1001:1001`) |
| --- | --- | --- | --- |
| mcp/time | `sha256:9c46a918…ebfcf` | USER 없음(root), Entrypoint `mcp-server-time`, WD `/app`, PATH `/app/.venv/bin:…` | `exec /app/.venv/bin/mcp-server-time: permission denied` (종료 255) |
| mcp/git | `sha256:ad6af958…03a2c` | 동일 구조, Entrypoint `mcp-server-git` | `exec /app/.venv/bin/mcp-server-git: permission denied` (종료 255) |
| mcp/filesystem | `sha256:35fcf021…b3f67` | node 22 | initialize 통과(대조군) |

- `/app/.venv/bin/mcp-server-*`는 `-rwxr-xr-x root`로 실행 권한이 있다. 그러나 shebang이 가리키는 `/app/.venv/bin/python`은 링크이고 대상이
  `/root/.local/share/uv/python/cpython-3.10.18-linux-x86_64-gnu/bin/python3.10`이다. `/root`가 `drwx------ root root`라 UID 1001의 `ls /root/.local`은 `Permission denied`.
  UID 1001에서 `/app/.venv/bin/python --version`도 `Permission denied`다. 즉 실행 파일이 아니라 인터프리터 경로의 `/root` 통과 권한이 원인이다.
- 쓰기 경로(캐시·HOME)가 원인이 아니다: 실패는 프로세스 시작 전 `exec` 단계다. 따라서 tmpfs나 `HOME`·`XDG_CACHE_HOME`·`UV_CACHE_DIR` 지정으로 풀리지 않는다(HOME은 러너가 금지).
- 우회도 막힌다: 시스템 `/usr/local/bin/python3.12`(UID 1001에서 실행됨)에 `PYTHONPATH=/app/.venv/lib/python3.10/site-packages`를 주면
  `No module named 'pydantic_core._pydantic_core'`(패키지는 cp310 확장 모듈). 매니페스트는 entrypoint를 바꿀 수 없다(`command`는 인자만).
- 진단 전용 확인(컨테이너 안에서만, `--rm`, 이미지·호스트 변경 없음): `chmod 711 /root && chmod -R go+rX /root/.local` 뒤 `setpriv --reuid=1001`로 `mcp-server-time`을 실행하면
  `initialize`가 정상 응답한다. 원인이 `/root` 통과 권한 하나임을 확인한 것이며, 해결책으로 root 실행을 쓴 것이 아니다.

## 선택한 수정

환경 변수·tmpfs·허용 범위 확대로는 풀 수 없고, 루트 실행·capability 추가는 허용하지 않으므로(재매핑 없는 호스트에서 탈출 시 호스트 root) 제안에서 뺀다.

- `intake_proposal.py`: `LOCAL_RUN_PRESETS`에서 `src/git`·`src/time` 삭제. `ROOT_ONLY_IMAGES`·`local_run_status(row)` 추가(공식 저장소의 두 경로만 「관리 계정으로 실행할 수 없는 이미지」, 그 외 빈 문자열).
- `agent_service.py`: `approval-preview` 응답에 `local_run_status`.
- `console.js`: `askLocalRun`이 상태가 있으면 경고 칩으로 문구를 보이고 이미지 입력란을 `mcp/<이름>`으로 미리 채우지 않는다. 설명 문단 없음.
- 러너·`LocalRunSpec`·`manifest_errors`·허용 환경 변수는 변경 없음(범위 확대 없음). 관리자가 비루트로 재빌드한 사내 미러 이미지를 직접 입력하는 길은 열려 있다.
- `docs/ai/DECISIONS.md` D-207(D-206 git·time 정정), `analysis/local-run-presets-1023/README.md` 정정 표시.

## 남은 3개 기본값 PJ1 실측 (러너와 같은 옵션, 시험 데이터)

`docker run --rm -i --pull=never --network=none --read-only --tmpfs /tmp:rw,size=64m --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=128 --memory=512m --cpus=1 --user 1001:1001 [-e …] [-v 시험폴더:/workspace/…:ro|rw] <이미지@digest> [인자]`,
표준 입력에 `initialize`·`notifications/initialized`·`tools/list` 한 줄씩. 임시 폴더(권한 777, 문서 1개 "시험 데이터")는 실험 뒤 삭제.

| 기본값 | initialize | tools/list |
| --- | --- | --- |
| filesystem (`/workspace/mcp-docs`, `mcp-docs:ro`) | 통과(secure-filesystem-server) | 11개 |
| memory (`mcp-memory:rw`, `MEMORY_FILE_PATH`) | 통과(memory-server) | 9개 |
| sequentialthinking | 통과(sequential-thinking-server) | 1개 |

## 검증

| 확인 종류 | 명령·환경 | 결과 |
| --- | --- | --- |
| 새·수정 시험 | `python full_stack_lab/tests/local_run_presets_check.py` (7건) | 통과 |
| 기존 시험 | `local_runner_usability_check.py` 28건, `intake_one_click_ast_check.py` 12건, `node --test console-state.test.mjs` 15건, `intake_one_click_ui_check.mjs` 6건 | 통과 |
| 정적 | `node --check console.js`, pyflakes `intake_proposal.py` | 통과 |
| 위키 CI | 아래 「위키 검사」 | 아래 |
| 승인 화면 실제 표시·하네스 호출·기기 배포 | — | 미실행(리더) |

## 위키 검사

`map_threats.py`·`build_enterprise_analysis.py --refresh-code-only`로 재생성한 뒤 2026-10-23 로컬 Windows·Python 3.12에서 실행:
`check_wiki.py --ci-ignored-local-sources` 오류 0(무시된 로컬 원본 부재 경고만), `check_trace.py --self-test` 통과, `check_trace.py` 오류 0·경고 6,
`check_enterprise_analysis.py` 오류 0·경고 0, `test_enterprise_code_refresh.py` 3건 통과, `PYTHONUTF8=1 test_console.py` 32건 통과.

## 실패·미완료·한계

- 재빌드한 비루트 이미지는 만들지 않았고 digest·서명·미러 반입 흐름은 검증하지 않았다. 진단 확인은 컨테이너 안 임시 변경이다.
- 같은 uv 방식으로 빌드된 다른 공식 파이썬 이미지(예: fetch)가 같은 증상일 가능성이 있으나 이미지를 받지 않아 확인하지 못했다. 현재 표에는 들어 있지 않다.
- git·time의 기능 자체(읽기 전용 `git status`, 시간대 변환)는 실행되지 않아 확인하지 못했다.
- 이 PJ1은 사용자 재매핑이 없다. 재매핑(`userns-remap`)이나 podman rootless에서는 컨테이너 root가 호스트 비루트로 매핑돼도 `--user 1001`은 같은 `/root` 권한 때문에 실패하므로 결과는 같다고 보이지만 시험하지 않았다.

## 다음 작업

- 리더: 기기 배포 후 git·time 신청의 승인 창에 「관리 계정으로 실행할 수 없는 이미지」 칩이 보이고 이미지 칸이 비어 있는지, filesystem·memory·sequentialthinking은 그대로 미리 채워지는지 확인.
- 필요하면 `/root` 통과 권한을 연 사내 재빌드 이미지를 별도 작업으로 만들어 서명 흐름과 함께 시험.

## 사용자에게 필요한 입력

없음
