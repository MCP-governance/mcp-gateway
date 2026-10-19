# 2026-10-20 D-150 정정 — Linux 옵션 파싱·Windows 런처 변경 철회

- 작업자: Codex sol
- 코드 기준: `10/20-launcher-pin-review`, 시작 `5859004cc4a69d4eb8f1c2bd64b4005d5bacd2d9`, 시작 작업 트리 깨끗함. 커밋·푸시 없음.
- 시작 근거: DEV-42, [LP-01~07·S1·S2·S6](../../analysis/review-1020/d150-launcher-pin.md), 소유자의 D-150 정정 지시.
- 해결할 문제와 완료 조건: Linux에서 설정 옵션과 다른 옵션 값을 구별하고 하네스 종료자를 존중한다. Windows의 D-150 변경은 철회하며 기존 시험 기대값은 보존한다. Linux C/실제 하네스 검수는 기기 실행 전까지 완료로 세지 않는다.
- 변경 범위: `endpoint-agent/enforce-linux.py`, `endpoint-agent/managed-windows.py`, 이 브랜치 신규 `full_stack_lab/tests/launcher_pin_check.py`, D-150·명령 표면/검토 이력 안내·보고서·DEV-42 마지막 상태 칸. `status/current.md`, 기존 Windows 시험과 적대 시험 코드는 변경하지 않는다.

## 결과

- Linux C 가드는 고정 Codex 0.160.0의 값 옵션 표로 argv를 순회한다. 실제 `-c`·`-cX`·`-hcX`·`--config[=…]`는 한국어 오류와 코드 2로 거부하고, `-Csrc`·`-mgpt`·`-pconfig`·`-pcnotify=[]`·`--model -c`는 원형 전달한다. 값 표 밖 옵션은 다음 argv를 소비하지 않는다. 값에 소비되지 않은 `--` 뒤는 검사하지 않는다. 예를 들어 `--model -- -cX`는 `--`를 값 슬롯으로 소비한 뒤 `-cX`를 거부한다. 이는 잘못된 CLI 입력도 원본 파서에 유효성을 맡기는 보수적 가드다.
- 짧은 값 옵션은 `i,m,p,s,C,a,o`, 긴 값 옵션은 shared/TUI/exec/feature/remote 정의에서 확인한 항목뿐이다. 생성 C 주석에 판본·파일·출처 행을 남겼다. `--search`·`--json` 등 값 없는 플래그 다음의 실제 `-c`를 놓치지 않는 음성 사례도 추가했다. 값 붙임·분리·누락·묶음·반복·종료자·차단 시 원본 미실행을 확인하는 Linux 시험을 작성했다.
- Claude는 `--settings`·`--settings=…` 정확 일치와 `--` 종료를 적용한다. `--sett`·`--settings-extra`를 설정 인자로 오인하지 않는다. 기존 환경 정리·CA/프록시·Codex 내부 `--no-daemon`은 유지한다.
- Windows 파일은 `git show 97d9d10:endpoint-agent/managed-windows.py`와 동일하다. Python `launch`/`launch_harness` 제거, 3인자 `harness_launchers`·CA 전용 `.cmd`·`setlocal`·원본 직접 실행·사용자 PATH 뒤 추가·사용자 설정 홈 환경 보존을 복구했다. LP-06 문자열 접두 필터는 그대로 두고 DEV-42 후속 후보로 남겼다.
- 새 의존성·정책 ID·DB 변경·mock MCP 없음. 기존 고정 OSS 근거를 재사용하고 SharedCliOptions·TUI·exec·루트 CLI와 Commander v14.0.2를 2026-10-20 웹으로 재조회했다. Codex Apache-2.0, Commander MIT. 태그·읽은 행은 D-150에 연결했고, 기존 짧은 commit `a956835`의 full commit은 재조회하지 못했다. 공개 스킬 S11은 기존 탐색 이력만 사용했고 새 스크립트 채택·실행은 없다. 새 원문 사본 재배포 없음.

## 검증

실행일은 2026-10-20 KST, 환경은 Windows Python 3.10.5다. [실행 원본·소스 해시](../../analysis/review-1020/d150-launcher-pin-correction-evidence.json)에 명령·종료 코드·출력을 기록한다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | `python -X utf8 -m py_compile endpoint-agent/enforce-linux.py endpoint-agent/managed-windows.py full_stack_lab/tests/launcher_pin_check.py full_stack_lab/tests/launcher_pin_adversarial_check.py` | 통과 | 실행 원본 `py_compile` |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 실행 원본 `node_check` |
| 신규 단위·기존 Linux 적대 클래스 | `python -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check full_stack_lab.tests.launcher_pin_adversarial_check.LinuxLauncherAdversarialCheck -v` | Windows 대역 4통과, Linux 6건 건너뜀 | 실행 원본 `launcher_tests` |
| 기존 CA 회귀 | `python -B -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -k managed_ca -v` | 1통과, 3인자/CA 형식 회귀 해소 | 실행 원본 `windows_ca` |
| 기존 Windows 전체 | `python -B -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -v` | 10통과·5실패·1오류. PowerShell에서 기존 `.ps1` 로딩을 실행 정책이 거부 | 실행 원본 `windows_suite` |
| Windows 복원·기존 시험 불변·UTF-8/LF | Git blob 바이트 대조, 수정 파일 인코딩·개행 검사 | 통과 | 실행 원본 `integrity` |
| 패치 공백 | `git diff --check` | 통과 | 실행 원본 `diff_check` |

기존 Windows 전체 시험 실패는 숨기지 않았다. 5건은 `running scripts is disabled on this system`이고, ACL 1건은 같은 로딩 단계에서 종료 코드 1이다. 시스템/사용자 실행 정책을 바꾸지 않았다. Windows 제품 파일은 D-150 전 blob과 동일하며 이 작업에서 해당 `.ps1`·기존 시험은 바꾸지 않았다.

## 기존 시험 변경 필요

없음. 사용자가 수정하도록 지정한 이 브랜치 신규 `launcher_pin_check.py`만 현재 결정에 맞췄다. `endpoint-agent/tests-windows/test_windows_kit.py`와 `launcher_pin_adversarial_check.py`는 시작 커밋과 동일하다. 후자의 Windows 클래스는 철회된 Python API 검토 이력이라 현재 검증 명령에서 선택하지 않는다. Linux 두 메서드는 변경하지 않았다.

## 실패·미완료·한계

- Linux gcc 부재와 `wsl.exe -d kali-linux -- uname -s`의 `Wsl/Service/E_ACCESSDENIED` 때문에 C 컴파일·실행 6건은 미실행이다. 건너뜀을 통과로 세지 않는다. 보강 시험의 Linux 입력 기대가 실제 C에서 통과하는지 기기에서 확인해야 한다.
- 원격 HEAD 확인은 `git ls-remote --symref origin HEAD`의 GitHub 연결 실패로 미확인이다. 지정 브랜치를 유지했고 `.git` 쓰기·커밋·푸시는 하지 않았다.
- 표는 전체 clap 파서가 아니다. 미등록 옵션은 값을 받지 않는 것으로 처리하므로 오탐 가능성이 남고, 잘못 등록한 값 옵션은 실제 `-c`를 숨길 수 있어 판본 변경 시 출처/음성 시험을 재검토해야 한다. `--model -c` 통과는 가드 전달 결과이며 해당 모델 값의 CLI 유효성/실행 성공을 뜻하지 않는다.
- Claude의 다른 옵션 값 소비는 모델링하지 않아 값 자체가 `--settings`인 입력은 보수적으로 거부할 수 있다. Commander 근거와 Claude 실제 포함 판본/파서 검증을 구별한다.
- Windows 원본 직접 실행 차단에는 WDAC/AppLocker 등 조직 응용 프로그램 제어가 필요하다. 이 작업은 이를 구현하지 않는다. 사용자 `CODEX_HOME`·`CLAUDE_CONFIG_DIR` 탐지는 다음 엔드포인트 준수 검사 작업으로 남는다. LP-06 PATH 접두 필터 결함도 미수정이다.
- 솔루션 배포·PJ1·실제 CLI·Windows Ctrl+C/ACL·모델/MCP·upstream 효과는 미실행이다. 위키 전체 재생성/검사는 이전 검토의 기존 불일치 범위이며 이번에는 실행하지 않았다. `status/current.md`는 지시대로 보존했다.

## 다음 작업

DEV-42: 솔루션 기기의 저장소 루트에서 gcc를 확인하고 다음 명령을 실행한다. Linux 6건이 건너뛰면 검수 통과가 아니다.

```bash
command -v gcc
python3 -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check full_stack_lab.tests.launcher_pin_adversarial_check.LinuxLauncherAdversarialCheck -v
python3 -B -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -v
```

게이트웨이 이미지에서 돌릴 파일은 `full_stack_lab/tests/launcher_pin_check.py`, `full_stack_lab/tests/launcher_pin_adversarial_check.py`(Linux 클래스 선택), `endpoint-agent/tests-windows/test_windows_kit.py`다. 솔루션 기기의 `full_stack_lab`에서:

```bash
docker compose run --rm --no-deps -v "$PWD/..:/repo:ro" -w /repo gateway python -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check full_stack_lab.tests.launcher_pin_adversarial_check.LinuxLauncherAdversarialCheck -v
docker compose run --rm --no-deps -v "$PWD/..:/repo:ro" -w /repo gateway python -B -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -v
```

이미지에 gcc가 없으면 호스트에서 C 시험을 수행한다. Windows 전용 PowerShell/ACL 사례는 승인된 Windows 시험 기기의 실행 정책 환경에서 별도 수행한다. 이후 메인이 솔루션 기기의 `field up` 배포 → PJ1 새 관리 셸에서 실제 Codex/Claude 정상·차단·`--` 프롬프트·환경 정리와 기존 MCP 동작을 대조한다. Windows 설정 홈 준수 검사 탐지와 LP-06 정확한 경로 경계 비교는 별도 DEV-42 후속 후보이며 이번 완료 범위에 넣지 않는다.

## 사용자에게 필요한 입력

없음.

## 메인 검토 반영 (Claude, 2026-10-20)

- 값 받는 옵션 뒤 토큰이 `-`로 시작하면 값으로 소비하지 않는다. 실제 Codex(0.153.4·0.163.0-alpha)는 `--model -c`, `-m -c`, `--model --`에서 모두 "a value is required for '--model <MODEL>'"로 시작하지 않는다(clap은 하이픈 값을 받지 않음). 그래서 `--model -c`는 차단 쪽으로, `--model -- -cX`는 Codex 자체가 거부하므로 통과 쪽으로 시험을 옮겼다.
- `launcher_pin_adversarial_check.py`는 철회한 Windows `launch_harness`를 대상으로 한 재현 시험이라 지웠다. 재현 근거는 검토 문서와 증거 JSON에 남는다.
- 시험: WSL(gcc) `launcher_pin_check.py` 통과, Windows `endpoint-agent/tests-windows/test_windows_kit.py` 통과.

