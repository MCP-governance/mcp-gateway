# 2026-10-20 관리 하네스 런처 설정 경로 고정 (D-150)

- 담당: Codex luna
- 기준: 브랜치 `10/20-launcher-pin`, 시작 HEAD `97d9d10` (dirty 변경 없음)
- 시작 근거: DEV-42, D-147·D-148, S6-03 [적대 검토](../../analysis/review-1020/s6-user-command-settings.md)
- 완료 조건: 관리 Codex·Claude 런처가 설정 재정의 인자를 차단하고, Windows는 등록 프로필 설정 홈을 사용한다. 회귀 시험·D-150·위키 상태를 기록한다.

## 결과

- Linux C 래퍼는 Codex `-c`·`--config`(값 분리·`=`·짧은 옵션 묶음 포함)와 Claude `--settings`(분리·`=`)를 하네스 시작 전에 거부한다. 오류는 한국어, 종료 코드는 2다. 기존 내부 고정 옵션은 Codex `--no-daemon`뿐이며 차단 옵션을 포함하지 않는다.
- Windows는 CA 인증서 유무와 무관하게 보호된 `.cmd` 런처를 만들고 Python 런처에서 같은 옵션을 거부한다. 정상 인자는 원래 순서로 실행 파일에 전달한다. 실행 때 `CODEX_HOME=<등록 프로필>\.codex`, `CLAUDE_CONFIG_DIR=<등록 프로필>\.claude`를 덮어쓰고 사용자 레지스트리의 두 값을 제거한다. 계정 PATH의 보호된 shim은 기존 사용자 PATH보다 앞선다.
- 새 시험 `full_stack_lab/tests/launcher_pin_check.py`를 추가했다. 기존 시험 파일과 기대값은 수정하지 않았다.
- D-150에 설계·근거·한계를 기록했고, `command-surfaces/README.md`에 적용 상태를 추가했다. DEV-42에서는 상태 칸만 로컬 구현·검증 완료, PJ1 대기로 갱신했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 근거 |
| --- | --- | --- | --- |
| Python 구문 | `python -m py_compile endpoint-agent/enforce-linux.py endpoint-agent/managed-windows.py full_stack_lab/tests/launcher_pin_check.py` (Windows Python, 2026-10-20 KST) | 통과 | 로컬 실행 |
| 신규 단위 시험 | `python -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check -v` (Windows Python, 2026-10-20 KST) | 4통과, Linux gcc 사례 1건 건너뜀 | 로컬 실행 |
| Linux 래퍼 실행 시험 | WSL `wsl.exe -d kali-linux -- bash -lc "cd /mnt/c/Users/bobysg/bob/프로젝트/mcp-gw-codex-luna && python3 -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check -v"` | 미실행: WSL 서비스 `E_ACCESSDENIED` | 실행 오류 출력 |
| 패치 공백 | `git diff --check` (2026-10-20 KST) | 통과 | 로컬 실행 |
| 솔루션 배포·하네스·PJ1 | Linux·Windows 실기기 | 미실행 | 사용자 실행 필요 |

기존 시험 변경 필요: 없음.

## 실기기 확인 명령

솔루션 기기에서 저장소 루트 기준으로 이미지 시험을 실행한다. 로컬 PC에서는 compose 스택을 시작하지 않는다.

```bash
cd full_stack_lab
docker compose run --rm --no-deps -v "$PWD/..:/repo:ro" -w /repo gateway python -B -X utf8 full_stack_lab/tests/launcher_pin_check.py
```

PJ1 Linux 관리 계정에서 런처의 차단·통과를 확인한다. 차단 사례는 한국어 오류와 0이 아닌 종료 코드를, 도움말은 정상 전달을 기대한다.

```bash
codex -c notify=[]
codex --config notify=[]
codex --config=notify=[]
codex -pcnotify=[]
codex --help
claude --settings '{}'
claude --settings='{}'
claude --help
```

Windows 실기기에서는 관리 계정의 새 셸에서 `where codex`·`where claude`로 보호된 shim의 PATH 우선 순위를 확인한 다음 위의 Codex·Claude 차단 인자와 `codex --help`·`claude --help`를 실행한다. 로그아웃 전후의 프로필 경로 고정과 실제 CLI 판본 동작도 함께 대조한다.

## 실패·미완료·한계

- 로컬이 Windows라 Linux C 래퍼 실행 사례는 건너뛰었다. WSL은 접근 오류로 실행되지 않았다. 새 시험 파일의 Linux 사례는 솔루션 이미지에서 실행한다.
- PJ1 배포, Linux·Windows CLI 실제 실행, Windows 레지스트리 값 제거와 셸 PATH 우선 순위는 확인 전이다.
- Codex 짧은 옵션 묶음에 `c`가 있으면 보수적으로 차단할 수 있다. Windows 보호 shim을 통하지 않는 절대 경로 직접 실행은 범위 밖이다.

## 다음 작업

PJ1에서 이미지 시험과 위의 managed Codex·Claude 차단/통과 사례를 실행하고, Windows 셸 경로·환경 적용은 Windows 관리 기기에서 별도로 검증한다.

## 사용자 입력

없음.
