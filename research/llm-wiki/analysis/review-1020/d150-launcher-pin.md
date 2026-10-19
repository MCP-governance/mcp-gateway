# D-150 관리 하네스 런처 고정 적대 검토

- 작업자: Codex sol, 2026-10-20.
- 기준: `10/20-launcher-pin-review`, `07708a2caadf6df17ba4212c88adfd716d0374e4`, 시작 작업 트리 깨끗함.
- 판정: **병합 보류**. 정상 인자 오탐·Windows 실행 경계·기존 시험 회귀가 남았다. 기존 시험 변경 필요 규칙에 따라 제품 수정은 중단했다.
- 범위: Linux `wrapper(..., guard=)`와 생성 C, Windows `launch_harness`·`harness_launchers`·사용자 PATH, 기존 `launcher_pin_check.py` 및 연결된 Windows CA 시험.
- [실행 원본·소스 SHA-256](d150-launcher-pin-evidence.json), [새 재현 시험](../../../../full_stack_lab/tests/launcher_pin_adversarial_check.py), [작업 보고](../../status/reports/2026-10-20-d150-launcher-pin-review.md).

## 증거 수준과 판본

Windows Python 3.10.5의 격리 단위 시험과 표준 Python 자식 프로세스만 실행했다. 레지스트리·ACL·서비스는 변경하지 않았고, 실제 하네스·모델·MCP·솔루션 스택도 실행하지 않았다. Linux WSL은 `Wsl/Service/E_ACCESSDENIED`, 호스트 gcc 없음으로 생성 C 실행은 미실행이다. Linux의 결함은 생성 문자열 대조이며 Windows에서 같은 조건을 실행 재현했다. 대상 CLI 판본은 기존 명령 표면 자료의 PJ1 Codex 0.160.0·Claude Code 2.1.288이며, 현재 기기 판본을 재확인하지 않았다. 로컬 npm 메타데이터의 Claude 2.1.291은 PJ1 증거로 쓰지 않았다.

원격 HEAD 확인은 `git ls-remote --symref origin HEAD`의 GitHub 연결 실패로 미확인이다. 사용자 지정 작업 브랜치·HEAD에서만 작업했고 커밋·푸시는 하지 않았다.

## 발견

### LP-01 · 중간 · Codex의 값 붙임형 정상 옵션을 설정 주입으로 오인

- 근거: `endpoint-agent/enforce-linux.py:180`, `endpoint-agent/managed-windows.py:336`은 단일 `-`로 시작하는 토큰의 나머지 전체에서 `c`를 찾는다. 옵션과 옵션 값을 구분하지 않는다.
- 재현: `codex -Csrc`, `codex exec -mgpt-codex hello`, `codex -pconfig`는 모두 관리 런처에서 코드 2로 끝나며 원본 프로그램은 시작되지 않는다. `-C src`, `codex exec -m gpt hello`, 한 argv인 `"explain -c without executing"`는 통과한다. 실제 모델 존재나 프로필 파일 존재와 무관한 argv 전달 결함이다.
- 공식 근거: Codex 고정 소스의 `SharedCliOptions`는 `C`·`m`·`p`에 값을 받는다(S2). `-pconfig`는 이름 `config`이며 뒤의 `c`가 별도 옵션이 아니다. 기존 `-pcnotify=[]` 차단 시험도 `p`의 값 소비와 실제 `-c`를 구별하지 않는다.
- 수정안: 고정 CLI 옵션 정의에 맞춰 값을 받는 짧은 옵션에서 뒤 문자열을 값으로 소비하고, 실제 `c` 옵션만 거부한다. 임의 문자 포함 검사를 유지하면서 예외 문자열만 추가하지 않는다.
- 영향/한계: 정상 사용 중단. 현재 코드의 사용자 설정 차단 실패를 뜻하지는 않는다. 새 시험 `test_codex_attached_option_values_are_not_config_options`에서 3개 assertion 실패. 일반적인 짧은 옵션 파싱 수정은 기존 `-pcnotify=[]` 기대값과 충돌하므로 미적용이다.

### LP-02 · 중간 · `--` 뒤 프롬프트도 검사

- 근거: Linux C의 모든 argv 순회와 Windows `any(...)`는 옵션 종료자를 보지 않는다. Windows 함수 맨 앞의 `--` 제거는 Python 런처 자체의 전달 구분자 제거이며, 사용자가 준 두 번째 구분자는 남는다.
- 재현: Linux 런처 `codex -- -c`, `claude -- --settings`; Windows 직접 함수 인자는 각각 `["--", "--", "-c"]`, `["--", "--", "--settings"]`. 모두 리터럴 프롬프트여야 하나 코드 2로 거부된다. Windows 두 사례를 새 시험에서 재현했다.
- 수정안: 런처의 내부 구분자와 하네스의 구분자를 분리하고, 실제 옵션 값 소비를 추적한 뒤 하네스의 `--` 이후 검사를 끝낸다. 예를 들어 `--model -- -c ...`에서 첫 `--`가 옵션 값으로 소비될 수 있는지도 고정 파서와 대조해야 한다. 무조건 첫 `--`에서 멈추는 패치는 채택하지 않는다.
- 영향/한계: 설정 옵션을 설명하는 정상 프롬프트 거부. Commander의 `parseOptions`는 종료자 뒤를 operand로 남긴다(S6). Codex 각 서브명령의 추가 파서까지 모두 실측한 것은 아니다.

### LP-03 · 높음 · Windows 런처 진입점에서 등록 프로필을 다시 선택할 수 있음

- 근거: `managed-windows.py:332-356,815-821`은 CLI의 `--profile`·`--native`·`--ca`를 그대로 받는다. `launch`에서 현재 SID의 등록 설정을 조회하거나 인자와 대조하는 코드가 없다.
- 재현: 보호된 Python으로 `managed-windows.py launch --profile C:\UnregisteredProfile --native "C:\Program Files\MCPGatewayManaged\harness\codex.exe" codex -- exec hello`를 시작하면 `CODEX_HOME`은 미등록 프로필의 `.codex`가 된다. 새 시험은 `main()`부터 실행해 잘못된 프로필인데도 자식 생성 함수에 도달함을 재현했다. 실제 Codex의 설정 로딩·헬퍼 실행은 미실행이다.
- 수정안: SID에 결속한 보호 설정에서 실행 파일·프로필·CA를 읽거나 검증하는 진입점으로 바꾼다. 호출자가 지정한 값 자체를 등록 근거로 사용하지 않는다. `--profile`을 숨기는 것만으로는 해결되지 않는다.
- 영향/한계: D-148의 등록 홈 파일 검사와 다른 홈을 선택할 수 있는 구조적 공백. Windows 원본 실행도 가능한 LP-04와 함께 해결해야 하며, 이 재현만으로 토큰 접근·게이트웨이 정책 우회 성공을 주장하지 않는다.

### LP-04 · 높음 · Windows 읽기·실행 권한과 PATH는 런처 경유를 강제하지 않음

- 근거: `managed-windows.py:173-184`의 `lock_down(readers=True)`는 Users에 `RX`를 주며 `place_harnesses`(530-557)는 `%ProgramFiles%\MCPGatewayManaged\harness`에 공식 원본을 둔다. `harness_launchers`는 별도의 `.cmd`만 만든다. 코드 자체도 Windows 제한 단위가 실행 파일이 아니라 계정 SID임을 명시한다.
- 재현 절차(기기 미실행): 일반 관리 계정에서 `icacls "C:\Program Files\MCPGatewayManaged\harness\codex.exe"`와 `where.exe codex`를 확인한 뒤 원본 절대 경로로 `--config`를 전달한다. 원본 실행을 막는 ACL/응용 프로그램 제어가 없다면 Python 검사는 실행되지 않는다. 사용자 셸에서 PATH 재정의, cmd의 현재 디렉터리 우선 검색도 같은 한계를 갖는다(S9). 경로의 쓰기 금지는 직접 실행 금지가 아니다.
- 수정안: 기존 관리형 요구사항을 실질 경계로 두고, Windows의 임의 원본 실행을 제한하려면 조직의 응용 프로그램 제어/프로세스 식별 경계를 설계·실측한다. 파일 이름 변경이나 PATH 강화만으로 해결했다고 기록하지 않는다.
- 영향/한계: 런처를 경유하는 실행에 한정한 보호다. SID 방화벽·하네스 관리형 요구사항·게이트웨이 인가는 계속 적용될 수 있으므로 모든 통제가 우회된다는 의미가 아니다. Linux 관리 셸은 원본 대신 entry 프로필로 전환하는 래퍼만 실행 허용하고 원본에는 별도 실행 규칙이 없다(`enforce-linux.py:119-146`). 이 차이는 코드 근거이며 실제 AppArmor 효과 재확인은 미실행이다.

### LP-05 · 중간 · Ctrl+C가 대화형 하네스를 강제 종료할 수 있음

- 근거: Windows `launch_harness:356`의 `subprocess.call`은 CPython 3.13.16 `Lib/subprocess.py:355-368`에서 `wait`가 던진 예외에 `kill()` 후 재발생한다(S8). 로컬 3.10에서도 같은 구현을 확인했다. 새 프로세스 그룹이나 콘솔 이벤트 처리기는 두지 않는다.
- 재현: 새 시험은 `Popen` 대역의 `wait`가 `KeyboardInterrupt`를 던지게 하고, 자식의 `kill`이 호출됨을 확인했다. Ctrl+C를 처리하고 세션을 계속하는 대화형 하네스라면 Python 부모의 중단이 그 하네스를 죽일 수 있다. 실제 Windows 콘솔 이벤트를 보내지는 않았다.
- 수정안: `Popen`으로 자식 수명을 직접 관리하고 동일 콘솔의 첫 Ctrl+C를 자식이 처리할 동안 부모는 대기를 유지한다. 두 번째 중단·자식 종료·로그오프·종료 코드를 별도 정해야 한다. 다른 프로세스 그룹에 무차별 신호를 보내지 않는다.
- 영향/한계: 정상 종료의 기다림과 코드 7 반환은 표준 Python 자식으로 통과했다. 이 결과는 Ctrl+C·Ctrl+Break·자식의 손자 프로세스 종료 검증을 대신하지 않는다. 기존 시험이 `subprocess.call` 호출 자체를 요구하므로 수정 전 시험 검토가 필요하다.

### LP-06 · 중간 · 무관한 사용자 PATH 항목도 삭제

- 근거: `set_user_environment:262`는 경로 포함 관계가 아니라 문자열 `startswith(str(PROGRAMS).lower())`를 사용한다. 이 필터는 D-150 전에도 존재했으며 이번 재설치 경로에서 재현된다.
- 재현: 사용자 PATH의 `C:\Program Files\MCPGatewayManagedTools;C:\Other`에서 첫 항목이 사라진다. 새 레지스트리 대역 시험은 의도한 런처 선두 삽입과 함께 이 손실을 재현한다. 실제 레지스트리는 변경하지 않았다.
- 수정안: 정규화한 Windows 경로의 정확한 일치 또는 디렉터리 경계를 비교한다. 보호 루트와 이름 앞부분만 같은 프로그램은 보존한다.
- 영향/한계: 무관한 프로그램 검색 실패. 선두에 새로 추가하는 디렉터리에는 두 하네스 `.cmd`와 선택적 `root.crt`만 생성하므로 현재 코드상 다른 이름의 실행 파일을 새로 가리는 것은 아니다. 시스템 PATH·별칭·함수·현재 디렉터리·기존 셸 환경까지 순서를 강제하지는 않는다.

### LP-07 · 병합 차단 · 기존 Windows CA 시험 회귀

- 재현: `python -B -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -k managed_ca -v`는 171행에서 `harness_launchers() missing 1 required positional argument: 'python'`으로 실패한다. 기존 `launcher_pin_check.py` 4통과/1건너뜀만으로 전체 호출자 호환성을 확인할 수 없다.
- 추가 근거: 같은 기존 시험은 `profile` 없는 config로 함수를 부르며 `setlocal`과 직접 CA 환경 설정이 `.cmd`에 있어야 한다고 요구한다(171-175행). D-150은 보호 Python 런처로 그 책임을 옮겼다.
- 수정안: 사람이 기존 시험의 보안 의도를 적대 검증한 뒤 새 등록 프로필·보호 Python 경로를 fixture에 주고, 자식 범위 CA 적용과 부모 환경 불변을 검증하도록 승인한다. 인자 기본값만 주거나 검증을 생략해 통과시키지 않는다.
- 조치: 아래 「기존 시험 변경 필요」에 따라 제품 코드는 수정하지 않았다. 새 시험은 실패를 `expectedFailure`로 숨기지 않는다.

## 반박 목표별 판정

| 표면 | 저장소/공식 근거 | 판정과 남은 확인 |
| --- | --- | --- |
| Codex `--profile`+임의 경로 | S2의 `ProfileV2Name::from_str`는 ASCII 영숫자·`_`·`-`만 허용 | 0.160.0에서 `../outside`·절대 경로 주입은 소스상 거부. 정상 이름은 등록 `.codex/<name>.config.toml`이고 D-148 검사 범위다. 파일 교체 경쟁·하드 링크 등은 D-148의 별도 경계이며 런처가 시작 시 파일을 잠그지는 않는다. |
| Codex `--enable/--disable` | S1 `FeatureToggles::to_overrides`는 알려진 feature만 `features.<name>`으로 변환 | 런처가 통과시킴을 재현. 임의 `notify` 설정 주입과 같지 않다. 생성 `requirements.toml`은 apps/plugins/browser/computer와 관리 훅 제약을 별도로 가짐(`endpoint_plane.py:798-803`). 강제 요구사항 위반 옵션의 실제 거부는 PJ1 미실행. |
| Codex 기타 설정 파일 플래그 | S1·S2·S3의 고정 CLI 필드 | 읽은 CLI 정의에서 임의 설정 파일 경로를 받는 별도 옵션은 확인하지 못함. 모든 내부/미래 CLI 표면이 없다는 증명은 아님. `--remote` 등 별도 실행 경로의 실효성은 이번 시작 옵션 필터 검증 밖. |
| Linux `CODEX_*`·`CLAUDE_*` | `clearenv()` 후 HOME·USER·PATH·LANG·TERM·관리 environment만 설정(199-204행) | 호출자 환경이 남는다는 주장은 코드상 기각. 관리 설치가 지정한 CA 변수는 의도적으로 다시 설정된다. 새 Linux env 시험은 gcc/WSL 제약으로 미실행. |
| Windows `CODEX_HOME` | 340행 등록 프로필로 덮어씀 | 정상 `.cmd` 경유는 단위 통과. LP-03·04의 다른 실행 경로는 남음. |
| Windows `CLAUDE_CONFIG_DIR`, 기타 환경 | 345행은 변수를 **제거**하며 `profile`을 Claude 홈으로 설정하지 않음 | `HOME`·`USERPROFILE`·합성 `CODEX_*`·`CLAUDE_CODE_EXTRA_BODY` 상속을 대역에서 확인. 공식 기본 설정 위치는 `~/.claude`(S5). 홈 재지정의 실제 로딩 성공은 미검증 후보이며 확정 우회로 세지 않는다. `.claude.json` 로그인 위치 이동 때문에 변수를 제거했다는 HEAD 커밋 본문과 D-150 초기 문구는 다르다. |
| Claude `--setting-sources` | S4에서 값은 user/project/local | 런처 통과. 새 임의 JSON 주입 옵션이 아니며 관리 소스를 끈다는 근거 없음. D-148가 검사하지 않는 프로젝트 helper 키는 기존 D-147/D-148 한계이고 시작 시 검사까지 보장하지 않는다. |
| Claude `--mcp-config` | S7: 읽기/파싱 가능한 managed-mcp.json을 배치한 워크스테이션은 동적 MCP 인자를 거부 | 런처 통과 자체를 MCP 우회 성공으로 세지 않음. 파일 배치·판본·실제 서버 미실행을 PJ1에서 대조해야 함. 새 mock MCP는 만들지 않음. |
| Claude `--plugin-dir`·`--add-dir` | S4, 기존 관리 allowManagedHooksOnly·strictKnownMarketplaces·MCP 잠금 | 런처는 통과. 추가 디렉터리/플러그인 표면이며 설정 홈 자체를 바꾸는 옵션은 아님. 훅 잠금 외 플러그인의 모든 확장·로드를 막았다고 주장하지 않음. 설치 제한과 세션 로드 제한은 구별해야 함. |
| `--sett`·Codex `--conf` 축약 | S6 Commander `Option.is`는 정확히 비교. S10 clap 부분 일치는 명시 옵션이며 기본 꺼짐, S1 루트 derive에는 활성화 없음 | 필터가 두 문자열을 통과시키는 것은 재현. 이 사실만으로 우회가 아님. clap 소스상 Codex 축약은 거부 예상. Claude 배포판이 해당 Commander 구현을 그대로 쓴다는 고정 소스 근거는 미확보이므로 실제 2.1.288 파서 동작은 **추정/미실행**. |
| `--` 뒤 인자 | LP-02·S6 | 옵션이 아닌 리터럴까지 거부하는 오탐을 재현. |

## 기존 시험 변경 필요

**필요, 승인 전 수정 중단.** 사용자 규칙의 “기존 시험 파일의 기대값을 바꾸지 않는다 … 이유를 적어 멈춘다”를 적용했다.

1. `endpoint-agent/tests-windows/test_windows_kit.py:171-175`: 3인자 API·profile 없는 fixture·CA 설정의 기존 스크립트 형식이 새 설계와 충돌한다. 현재 코드 그대로 실행 오류를 재현했다.
2. `full_stack_lab/tests/launcher_pin_check.py:35,98`: `-pcnotify=[]`를 실제 설정 옵션 묶음처럼 거부하도록 고정한다. 고정 Codex에서 `p`가 값을 받으므로 정상 옵션 값 파싱과 대조가 필요하다. 이 문자열 자체도 올바른 프로필 이름이 아니므로 “관리 런처가 차단했다”와 “원본 CLI가 잘못된 프로필을 거부했다”를 구별해야 한다.
3. 같은 파일 52-55행은 `subprocess.call`을 정확히 호출하도록 고정한다. Ctrl+C를 보존하는 수명 관리로 교체할 때 부모 대기·종료 코드·자식 환경이라는 동작 중심 검증으로 바꿀 필요가 있다.

이 기록은 기존 시험 변경 승인이 아니다. 제품 소스 두 파일·기존 시험은 시작 SHA-256과 동일하다. 최소 수정안은 각 발견에 남겼으며 구현 완료로 보고하지 않는다.

## 실행 결과

| 검사 | 결과 | 범위 |
| --- | --- | --- |
| 기존 launcher_pin_check | 4통과, Linux 1건너뜀 | 원래 제한된 argv·생성 스크립트 |
| 새 launcher_pin_adversarial_check | 12개 메서드: 5통과·5실패·Linux 2건너뜀, 실패 assertion 8개 | 값 붙임 3·리터럴 2·중단 1·PATH 1·미등록 홈 1. 실패 종료 코드 1 |
| 기존 Windows CA 선택 시험 | 오류 1, 종료 코드 1 | API 회귀 재현 |
| Python py_compile | 통과 | 제품 두 파일·새 시험 |
| 위키 전체 검사 | 실패 | 기존 코드/위협 매핑 불일치 23개·ignored 원본 누락 경고 119개. 원문 결과는 실행 JSON의 wiki_check |
| Linux C/실제 콘솔 Ctrl+C/ACL/CLI/모델/MCP/배포 | 미실행 | WSL 접근 제한·실기기 검수 전 |

## 기기 확인 순서

솔루션 기기의 저장소 루트에서(호스트 gcc가 있어야 Linux 두 시험이 실행됨):

```bash
python3 -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check full_stack_lab.tests.launcher_pin_adversarial_check -v
```

게이트웨이 이미지에서는 `full_stack_lab`에서 아래 명령으로 Python/Windows 대역 부분을 확인한다. 이미지에 gcc가 없으면 Linux 부분의 건너뜀을 통과로 세지 않는다.

```bash
docker compose run --rm --no-deps -v "$PWD/..:/repo:ro" -w /repo gateway python -B -X utf8 -m unittest full_stack_lab.tests.launcher_pin_check full_stack_lab.tests.launcher_pin_adversarial_check -v
```

수정·기존 시험 승인 전에는 새 시험의 실패를 예상한다. 실제 PJ1에서는 새 관리 셸·현재 실행 경로·실제 CLI 버전을 확인하고 LP-01/02 정상 argv, 차단 인자와 축약 인자, `--profile ../outside`, 관리 요구사항과 충돌하는 feature를 대조한다. Windows 대상에서는 별도 관리 테스트 계정에서 원본 절대 경로·현재 디렉터리/시스템 PATH·미등록 프로필·Ctrl+C 1회/2회·Ctrl+Break·종료 코드까지 확인한다. 관측·원장만으로 헬퍼/외부 효과의 부재를 주장하지 않는다. 기존 업무 세션과 설정은 변경하지 않는다.

## 공식 자료·OSS·스킬 검토

조회일은 2026-10-20. 웹에서 읽은 범위만 사용했고 원문 바이트 사본을 확보하지 않아 원문 SHA-256은 미확보다. 표의 판본 태그와 줄은 해당 판본에 한정한다. 외부 코드·스킬 스크립트는 실행/도입하지 않았다. [기존 명령 표면 출처](../command-surfaces/README.md)는 과거 근거로 구별했다.

| ID | 원문·고정 판본 | 읽은 범위/라이선스/적용 |
| --- | --- | --- |
| S1 | [Codex CLI rust-v0.160.0](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/cli/src/main.rs) (기존 위키 commit `a956835`) | 107-133 루트 clap·867-907 FeatureToggles. Apache-2.0. 관리 제한과 CLI 설정 변환을 구별. full commit 재조회 미확인. |
| S2 | [SharedCliOptions](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/utils/cli/src/shared_options.rs), [ProfileV2Name](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/protocol/src/config_types.rs) | 각각 19-68, 108-149. Apache-2.0. 프로필 이름 검증·짧은 값 옵션. |
| S3 | [OpenAI 공식 CLI 명령](https://developers.openai.com/codex/cli/reference/) | 현재 learn.chatgpt.com으로 리다이렉트. 프로필·config·features·exec 옵션. 현재 문서와 고정 소스를 혼동하지 않음. OpenAI Docs 스킬은 문서 조회에만 사용. |
| S4 | [Claude 공식 CLI](https://code.claude.com/docs/en/cli-reference) | settings·setting-sources·mcp-config·plugin-dir·add-dir. 상용 제품 문서, 재배포 없음. |
| S5 | [Claude 환경 변수](https://code.claude.com/docs/en/env-vars) | CLAUDE_CONFIG_DIR·CLAUDE_CODE_EXTRA_BODY·추가 디렉터리 메모리 로딩. 문서 미등재 변수를 우회로 발명하지 않음. |
| S6 | [Commander v14.0.2 Option.is](https://github.com/tj/commander.js/blob/v14.0.2/lib/option.js#L231), [parseOptions](https://github.com/tj/commander.js/blob/v14.0.2/lib/command.js#L1629) | 정확 일치·`--`·짧은 옵션 값 소비. MIT. Claude 실제 포함 판본은 미확인. |
| S7 | [Claude 관리 MCP](https://code.claude.com/docs/en/managed-mcp), [관리 설정](https://code.claude.com/docs/en/managed-settings) | 동적 MCP와 관리 소스·허용 목록 잠금. 실제 설치 효과와 문서상 동작을 분리. |
| S8 | [CPython v3.13.16 subprocess](https://github.com/python/cpython/blob/v3.13.16/Lib/subprocess.py#L355), [Python subprocess 공식 문서](https://docs.python.org/3.10/library/subprocess.html#subprocess.call) | call 예외의 kill·wait·Windows 신호. PSF. 저장소 Windows Python 고정 판본과 대조, 새 의존성 없음. |
| S9 | [Microsoft path](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/path), [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw) | 현재 디렉터리/검색 순서·환경 상속·새 프로세스 그룹의 Ctrl+C. 실제 기기 PATH는 미실행. |
| S10 | [clap v4.5.60 Command::infer_long_args](https://github.com/clap-rs/clap/blob/v4.5.60/clap_builder/src/builder/command.rs#L1696) | 부분 일치 기본값 꺼짐·명시 활성화. MIT/Apache-2.0. Codex 정확한 clap lock 판본은 이번에 미확인. |
| S11 | [공개 Codex 스킬 카탈로그](https://github.com/openai/skills) | 공개 저장소·README만 탐색. 정확한 검토 대상 스킬 commit·라이선스·유지보수는 미확인, 채택/실행 없음. 런처 보안 로직에 외부 스킬을 가져오지 않음. |

새 의존성·정책 ID·DB 변경·mock MCP는 없다. 현재 저장소 코드/시험의 전체 해시는 실행 원본 JSON에 보존했다.
