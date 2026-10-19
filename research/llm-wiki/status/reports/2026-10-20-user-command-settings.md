# 2026-10-20 사용자 명령 헬퍼 준수 검사

- 작업자: Codex sol
- 코드 기준: `a61c7fa71c6f3d09f624b215a582fc05e3b38e3b`, 시작 시 깨끗한 `10/20-user-command-settings`. 커밋·푸시 없음.
- 실제 변경: `endpoint-agent/{agent.py,managed-linux.py,managed-windows.py,README.md}`, `full_stack_lab/gateway/app/{endpoint_plane.py,main.py,agent_static/console.js}`, 새 `full_stack_lab/tests/user_command_settings_check.py`, D-148, 분석 정본/검증 기록, 이 보고서와 백로그 DEV-42 상태 칸. `status/current.md`·기존 시험은 변경하지 않았다.
- 시작 근거: DEV-42·RV-02, [D-147 명령 표면](../../analysis/command-surfaces/README.md), [D-148](../../../../docs/ai/DECISIONS.md).
- 해결할 문제와 완료 조건: 관리 잠금이 없는 Claude 네 명령 키와 Codex notify를 관리 계정 홈에서 찾아 값 없이 보고하고 기존 준수·격리에 연결한다. 구현·로컬 검증을 이 레인에서 끝내고 솔루션 배포·PJ1 검증은 메인 레인에 넘긴다.

## 결과

Linux 등록 계정의 `pw_dir`, Windows 등록 프로필에서 `.claude/settings.json`·`settings.local.json`, `.codex/config.toml`·직계 `*.config.toml`을 읽는다.
Claude 네 키와 Codex 최상위/`profiles.*`의 notify는 빈 값도 실패다. 프로필 확장자의 대소문자를 구분하지 않는다.
키 부재·정상 파일은 통과하고 파일/폴더 읽기·열거 실패, JSON/TOML/UTF-8 오류, 표준 파서 부재, 링크/특수 경로·입력 상한 초과는 실패한다.
실패 보고에는 홈 기준 파일명과 키 이름만 있으며 읽기/파싱 오류의 키 목록은 비운다. 명령 문자열·파서 예외 본문을 넣지 않는다.

두 플랫폼의 `user_command_helpers`를 필수 준수 항목으로 추가하고 기존 heartbeat→격리→관리자 재활성화 경로를 쓴다.
파일/키 보고가 있는데 체크가 true인 모순된 입력도 false로 저장하여 활성화 SQL의 전체 true 비교를 통과하지 못하게 한다.
최근 실패 목록은 기존 detail에 갱신하고 감사 사건은 INSERT만 한다. Windows 사용자 Codex 파일 읽기 오류도 heartbeat 실패로 보낸다.
콘솔에는 「사용자 명령 헬퍼 없음」 라벨을 추가했다. 새 라우트·DB 변경·OPA 규칙/정책 ID·의존성은 없다.

정책 version=2로 해시를 바꾼다. 메인 검토(Claude)에서 전환을 정정했다: 검사를 한 번도 보고하지 않은 구형 에이전트는 이전 항목으로 판정하고,
한 번 보고한 장치는 항목을 필수로 한다(배포 즉시 전 장치 격리 방지, 구형 키트 재설치로 검사 제거 방지).
이 레인에서 배포·재설치·활성화는 실행하지 않았다. [원자 요구사항·전환·근거·한계](../../analysis/user-command-settings/README.md).

## 검증

실행일 2026-10-20 KST, Windows(검증 기록의 `recorded_at`은 UTC). 기본 Python은 3.10.5라서 TOML 시험에 기존 캐시의 Python 3.12.14를 사용했다.
아래 `python312`는 `C:/Users/bobysg/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`다.
새 시험은 실제 제품 함수 본문·표준 파서·임시 HOME·AsyncMock DB를 사용한다. MCP 서버 대역은 만들지 않았다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 순수/입력/DB 대역 | `python312 -B -X utf8 full_stack_lab/tests/user_command_settings_check.py` | 14통과, 실제 링크 생성 1미실행 | [시험 로그](../../analysis/user-command-settings/new-tests.log), [코드 해시·행·명령](../../analysis/user-command-settings/verification.json) |
| Python 구문 | `python -m py_compile` 및 python312, 제품 Python 5파일+새 시험 | 통과 | [구문 로그](../../analysis/user-command-settings/compile.log) |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | [구문 로그](../../analysis/user-command-settings/js-syntax.log) |
| 기존 D-147 | `python312 -B -X utf8 full_stack_lab/tests/command_surfaces_check.py` | 3통과 | [실행 기록](../../analysis/user-command-settings/verification.json) |
| 기존 콘솔 상태 | `node --test full_stack_lab/tests/console-state.test.mjs` | 15통과 | 같은 기록 |
| 기존 인증 경계 | `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 무인증 1·인증 84개 검사 통과 | 같은 기록 |
| 기존 관측 자체 검사 | `python312 -B -X utf8 endpoint-agent/agent.py --self-check` | 통과 | 같은 기록 |
| 기존 Windows 키트 | `python312 -B -X utf8 endpoint-agent/tests-windows/test_windows_kit.py` | 16개 중 10통과, PowerShell 실행 정책으로 5실패·1오류 | 같은 기록, `running scripts is disabled`·`UnauthorizedAccess` |
| 위키 목록 | `python312 -B -X utf8 research/llm-wiki/tools/build_wiki.py` | 통과 | [로그](../../analysis/user-command-settings/wiki-build.log) |
| 위키 전체 검사 | `python312 -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 미통과, 기존/변경 코드의 위협 매핑 해시 불일치 22건. 새 문서 링크 오류 없음 | [로그](../../analysis/user-command-settings/wiki-check.log) |
| 패치 공백 | `git diff --check` | 통과 | [로그](../../analysis/user-command-settings/diff-check.log) |

## 실패·미완료·한계

- 기존 시험 변경 필요: **없음**. 기존 시험의 코드·기대값은 변경하지 않았다. Windows 키트 실패는 현재 실행 정책이 스크립트 로드를 거부한 결과이며 정책도 바꾸지 않았다. 전체 회귀 통과로 표시하지 않는다.
- 실제 심볼릭 링크 시험은 Windows 링크 생성 권한 부족으로 미실행이다. Linux `managed_enforcement_check.py` 전체와 새 시험의 링크 사례는 기기 이미지에서 실행한다.
- pyflakes는 설치되지 않았다. 게이트웨이 전체 import는 로컬 psycopg·pglast 부재로 하지 않았다. WSL Python 실행은 `Wsl/Service/E_ACCESSDENIED`, 원격 HEAD 재확인은 GitHub 연결 실패다.
- 위키의 기존 위협 매핑에는 변경 전부터 다른 파일의 해시 불일치가 있고 이번 제품 파일도 매핑 해시가 달라졌다. 전체 매핑/상태 스냅샷은 이 레인의 범위 밖이라 재생성하지 않았다. 새 분석의 현재 코드 해시·행은 별도로 기록했다.
- 프로젝트 폴더 설정·대체 설정 홈/인자·클라우드 실행은 모집단 밖이다. 60초 스냅샷 사이의 파일 변경·동일 inode 쓰기/실행 경쟁은 막지 못한다. 원격 증명이나 실행 시점 잠금이 아니다.
- 실제 PostgreSQL, HTTP heartbeat 통합, 정책 hash 전환·구형 에이전트 격리, 관리자 재활성화, 하네스 프로필·독립 효과, 브라우저 렌더링·솔루션 배포·PJ1은 **미실행**이다.

## 다음 작업

솔루션 기기에서 저장소 루트 기준으로 새 시험과 기존 Linux 회귀를 이미지에서 실행한다. 로컬 스택을 띄우지 않는다.
`full_stack_lab`에서 다음 두 명령을 쓴다.

```bash
docker compose run --rm --no-deps -v "$PWD/..:/repo:ro" -w /repo gateway python -B -X utf8 full_stack_lab/tests/user_command_settings_check.py
docker compose run --rm --no-deps -v "$PWD/..:/repo:ro" -w /repo gateway python -B -X utf8 full_stack_lab/tests/managed_enforcement_check.py
```

메인이 `./console.sh field up`으로 배포하고 승인된 새 키트로 재설치·정상 보고·관리자 재활성화를 확인한다.
PJ1의 실제 관리 하네스에서 정상군, 각 키 추가 후 실패/격리·토큰 발급/기존 토큰 호출 거부, 제거 후 재활성화·정상 호출 복구를 검증한다.
다른 실행 중 랩/종료 케이스는 건드리지 않는다. 프로젝트 설정·검사 사이 경쟁은 DEV-42의 남은 경계로 유지한다.

## 사용자에게 필요한 입력

없음. 솔루션 배포·PJ1 검증은 기존 메인 레인의 절차와 권한으로 진행한다. 자격증명 값을 수집하지 않았다.
