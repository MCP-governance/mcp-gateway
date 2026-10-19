# S6(D-148) 사용자 명령 설정 검사 적대 검증

- 검토일: 2026-10-20, Codex luna
- 기준: 시작 HEAD `9e597acb13157186a83f6e7fba09eac5090b8258`, 브랜치 `10/20-user-command-settings-review`
- 범위: `endpoint-agent/agent.py:user_command_settings`, 두 관리 에이전트 checks/heartbeat, `endpoint_plane.managed_checks`·`heartbeat`·`activate_managed`, 입력 모델, D-147 명령 표면 근거
- 현재 작업 트리 수정을 포함한 파일 해시·행·실행 결과는 별도 작업 보고에 기록한다. 이 검토는 root/SYSTEM의 보고가 원격 증명이라고 간주하지 않는다.

## 판정 요약

| ID | 심각도 | 판정 | 상태 |
| --- | --- | --- | --- |
| S6-01 | 높음 | 디렉터리 검사와 파일 열기 사이 경로 교체로 링크 밖 파일 접근 가능 | Linux 수정(Claude): `/`부터 각 단계를 `O_DIRECTORY|O_NOFOLLOW`·`dir_fd`로 열고 그 핸들로 열거·열기. Windows는 경로 검사라 남음 |
| S6-02 | 중간 | 일반 파일 하드 링크를 허용해 선택 경로 밖 inode를 읽음 | 수정: 열린 파일의 `st_nlink == 1` 요구 |
| S6-03 | 높음 | `CODEX_HOME`·`CLAUDE_CONFIG_DIR` 및 Codex `--config` 우회 | 현재 입력만으로 차단 불가, 실제 실행 환경별 보강 필요 |
| S6-04 | 중간 | Codex 프로필 파일의 사용자 지정 이름이 보고·DB·감사 사건에 저장됨 | 수정(Claude): 보고는 고정 표기 `.codex/*.config.toml`, 입력 모델은 고정 7개 값만 허용. S6 시험은 병합 전 새 파일이라 기대값을 맞췄다 |
| S6-05 | 중간 | 최초 보고 전까지 구형/미보고 장치는 새 검사를 건너뛸 수 있음 | 전환 설계대로; 레거시 장치 검증 공백을 유지 |

## S6-01 — 디렉터리 경로 교체 경쟁

- 재현: `.claude` 또는 `.codex`를 `lstat()` 한 뒤, `iterdir()`·후속 파일 `lstat()`·`os.open(path)` 전에 직원이 해당 디렉터리를 다른 곳으로 바꾸거나 junction/symlink로 교체한다. 파일 경로 열기는 `dir_fd`에 고정되지 않는다. 교체된 대상에 같은 이름의 일반 파일이 있으면 최종 `lstat`과 `fstat`의 inode/device가 서로 일치해도 처음 검사한 홈 하위 디렉터리였다는 보장은 없다. 파일 링크 금지와 Windows 재분석 지점 확인은 이 경쟁을 닫지 않는다.
- 영향: privileged 에이전트가 등록 홈에서 선택한 두 설정 디렉터리 바깥 경로를 열 수 있다. 반환 값에는 내용이 아니라 발견된 키 이름만 포함되지만, root/SYSTEM 읽기 범위 불변식을 깬다.
- 수정안: POSIX는 홈·설정 디렉터리를 `O_DIRECTORY|O_NOFOLLOW`와 `dir_fd`로 열고 핸들 기준으로 열거·파일 열기를 한다. Windows는 재분석 지점을 거부하는 핸들 열기 및 최종 경로/파일 ID 확인을 구현한다. 단순 사전 `lstat`을 추가하는 방식은 경쟁을 제거하지 않는다.
- 검증 한계: 정적 코드 경로로 확인. 경쟁 재현을 이 Windows 작업 트리에서 실제 junction으로 실행하지 않았다. 기기 전용 시험 필요.

## S6-02 — 하드 링크

- 재현: 임시 홈 밖에 JSON 설정을 만들고 `.claude/settings.json`으로 `os.link()` 한다. 기존 코드는 일반 파일·동일 inode를 확인한 뒤 내용을 읽었다. 파일 링크 수는 검사하지 않는다.
- 영향: 에이전트가 검사 대상 경로 이름과 다른 직원 소유 inode를 읽는다. 명령 원문은 반환하지 않지만 설정 키 이름과 고정 설정 파일 이름은 발견값으로 올라갈 수 있다.
- 수정: `fstat()` 후 읽기 전에 `st_nlink != 1`이면 실패. `agent.py`에 이 검사를 넣었고 새 S6 시험에서 실제 하드 링크를 확인했다. 심볼릭 링크 시험 권한과 무관하다.
- 한계: 링크 수 확인은 열기 시점만 보장한다. 이후 동일 inode 쓰기 경쟁이나 OS별 파일 ID/reparse 의미는 해결하지 않는다.

## S6-03 — 검사되지 않는 실제 설정 선택 경로

- 재현 A(Codex): Windows 관리 계정 환경에 `CODEX_HOME`을 두고, Codex CLI가 그 디렉터리의 `config.toml` 및 `profile-name.config.toml`을 읽게 한다. 관리형 Windows 실행은 현재 사용자 환경을 그대로 상속하며, `set_user_environment()`는 프록시·PATH_APPEND만 수정한다. 검사기는 등록 프로필의 기본 `.codex`만 읽는다.
- 재현 B(Codex CLI): 고정 Linux 래퍼는 `clearenv()`를 실행하지만 사용자 인자를 그대로 전달한다. 공식 Codex 구성 설명은 CLI `--config` 오버라이드를 우선순위 최상단에 둔다. 실제 notify 실행/차단 효과는 PJ1에서 재현 전이므로, 파일 검사 우회는 확정이고 독립 집행 효과는 미확인이다.
- 재현 C(Claude): 공식 문서의 `CLAUDE_CONFIG_DIR`는 기본 `~/.claude`를 바꾸며 설정·자격·기록·플러그인 경로로 쓰인다. 사용자별 Windows 환경은 관리 런처에서 지워지지 않는다. 따라서 그 변수가 설정된 세션은 스캔한 두 파일과 다른 설정 홈을 읽을 수 있다. `--settings`도 인자가 전달되는지와 이 판본에서 해당 키를 적용하는지는 실제 기기 검증이 필요하다.
- 근거: [Codex 구성 우선순위 및 프로필 파일](https://learn.chatgpt.com/docs/config-file/config-basic), [Codex 구성 레퍼런스](https://learn.chatgpt.com/docs/config-file/config-reference), [Claude 환경 변수](https://code.claude.com/docs/ko/env-vars); 저장소 실행 경로 `endpoint-agent/enforce-linux.py:164-193`, `endpoint-agent/managed-windows.py:228-245,300-315`, `endpoint-agent/agent.py:101-167`.
- 수정안: 관리 하네스가 실제로 받은 환경·선택 인자를 privileged 검사에 같은 값으로 보고하게 하지 말고, 런처에서 설정 홈과 인자를 root 관리 정책으로 고정한다. 또는 모든 지원 경로를 하네스 판본별 공식 근거로 열거해 검사한다. 사용자 입력으로 선택한 임의 설정 홈을 root가 재귀 탐색하는 변경은 범위를 늘리므로 별도 위협 검토가 필요하다.
- 한계: 로컬 저장소는 CODEX_HOME 강제 설정을 Windows 런처에 보이지 않으며, Linux 환경은 초기화된다. 대체 홈 설정이 즉시 “명령 실행”을 보장한다는 뜻은 아니다. 명령 표면 D-147이 가리키는 실제 실행 호환성·프로필/AppArmor 효과는 PJ1 확인 전까지 추정이다.

## S6-04 — 사용자 지정 파일 이름의 값 노출

- 재현: `.codex/`에 `api-key-command-secret.config.toml` 같은 유효 접미사 파일을 만들고 `notify`를 둔다. 검사 결과의 `file`에는 `path.relative_to(home)` 전체가 들어가며, 엄격 모델도 이 파일 이름을 허용한다. 게이트웨이는 이 값을 `detail.user_command_settings`와 격리 사건에 저장한다. 이름 자체에 명령·자격 값을 넣으면 원문 키/값을 보내지 않는다는 보호를 우회한다.
- 수정안: 프로필 파일은 보고 시 고정 식별자(예: `.codex/*.config.toml`)로 치환하고 감사 사건·콘솔도 같은 안전한 값만 받게 한다.
- 상태: 미수정. 기존 `tests/user_command_settings_check.py`는 입력 모델과 DB 보고에서 `.codex/work.config.toml` 같은 정확한 파일명을 기대한다. 기대값을 변경하지 말라는 지시에 따라 기존 시험은 수정하지 않았으며, 안전한 익명화 적용에는 **기존 시험 변경 필요**가 남는다.

## S6-05 — 전환 표식 및 활성화 경로

- 최초 미보고 장치: `managed_checks(device, reported)`는 `detail.command_settings_checked`와 현재 `checks` 양쪽에 표식이 없으면 새 항목을 제외한다. 이전 에이전트는 그 상태로 계속 정상 보고할 수 있으며, 검사를 자동으로 받지 않는다. 이는 D-148의 배포 즉시 전 장치 격리 방지 선택과 일치하지만, 구형 설치를 재설치할 때까지 탐지 공백이다.
- 표식 생성/삭제: heartbeat 입력은 직원 임의 JSON 필드를 받지 않고 인증된 장치 자격을 요구한다. 하지만 장치 heartbeat는 서명된 검사 증명이 아니라 `checks` 자기 보고다. 토큰을 가진 호출자는 `user_command_helpers: true`를 넣어 표식을 만들 수 있으며, 그 값은 실제 스캔 완료를 증명하지 않는다. 정상 새 에이전트는 검사를 실행하고 값을 보고한다. 장치 토큰 경계가 침해되면 기존 모든 검사도 위조할 수 있다.
- 삭제: DB 식 `detail=(detail - 'host') || %s`는 새 JSON을 기존 detail에 병합한다. 새 보고에서 키를 생략해도 기존 `command_settings_checked=true`는 보존된다. 모델은 임의 detail 조작을 허용하지 않으므로 직원은 직접 지울 수 없다. 이미 표식이 생긴 장치에서 구형 checks만 보내면 필수 항목 누락으로 heartbeat가 비준수 처리되어 격리된다.
- 활성화/화면: `activate_managed`는 저장된 표식을 포함한 `managed_checks(device)` 전부 true인 최신 heartbeat만 조건부 활성화한다. `integrations.device_state`는 저장된 `managed_state`를 사용하므로 heartbeat의 격리와 화면 상태는 같은 상태 필드를 본다. 미표식 구형 장치는 기존 항목만으로 재활성화될 수 있어 검토자에게 검사 생략 사실이 명확히 보이는지 별도 화면 검증이 필요하다. 이 검토에서는 DB/브라우저 동작은 미실행이다.

## 회피 점검 결과

- Claude JSON 키 대소문자/중첩 위치: 대상 키는 정확한 대소문자의 최상위 키만 검사한다. 공식 설정 키 표기는 대소문자 구분 이름이며, `env.apiKeyHelper` 같은 중첩은 동일 설정으로 취급하지 않는 범위다. D-147의 지정 키에 해당하는 표기 회피는 재현되지 않았다.
- JSON 중복 키: `json.loads`의 기본 마지막 값 우선과 무관하게 문서에 해당 키가 있으면 최종 객체에 키가 존재하는 경우 실패한다. 두 번째 복제 키로 정상 설정을 가장하는 회피는 재현되지 않았다. 중복 키 전체를 거부하진 않지만 이 다섯 대상 키의 존재 검사는 우회되지 않는다.
- Codex TOML: `tomllib`가 점 표기(`profiles.work.notify`)와 인라인/테이블 구조를 같은 객체로 파싱한다. 중복 TOML 키는 파싱 오류로 실패한다. 기존 시험은 표기 사례를 포함한다.
- 깊은 JSON/TOML·UTF-8·크기: 파일은 1 MiB+1 바이트에서 실패, UTF-8·JSON 상수·TOML 오류는 값 없는 파일 실패로 귀결, `RecursionError`도 실패한다. 1 MiB 입력이 파서 CPU/메모리 상한을 완전히 보장하지는 않는다.
- FIFO·기타 특수 파일: `lstat`의 정규 파일 검사와 `O_NONBLOCK`/열린 FD `fstat`로 FIFO는 읽기 전에 거부한다. 실제 FIFO 시험은 이 Windows 작업 트리에서 수행 불가이며 Linux 이미지에서 확인할 것.
- 파일 이름 규칙: 직계 `.codex`의 대소문자 무관 `*.config.toml`만 후보로 고른다. Codex 공식 문서는 `$CODEX_HOME/profile-name.config.toml`을 읽는다고 설명하며 임의 profile name을 쓸 수 있어 접미사와 디렉터리 위치는 맞다. 세션이 `--profile`로 선택하지 않은 파일까지 검사하는 것은 보수적 과탐이지 우회가 아니다.
- 미검사 경로: 프로젝트 `.codex`/`.claude`와 Claude 설정 디렉터리 별칭, Codex 홈 환경변수·CLI 오버라이드는 현재 기본 홈 스캔 밖이다. 실제 지원 여부를 문서로 확인한 대체 홈/CLI 경로는 S6-03에 기록했다. 자체 앱/GUI의 다른 Claude Desktop 설정 파일은 Claude Code와 다른 설정 표면이므로 이 기능의 근거로 섞지 않았다.

## 결정 및 남은 한계

하드 링크는 심볼릭 링크·특수 파일과 같이 거부한다. 명령 값, JSON/TOML 예외, 셸 명령을 에이전트에 보내지 않는 기존 계약은 유지한다. 파일 경로 경쟁, 실제 설정 홈 고정, 동적 이름 익명화는 해결되지 않았다. 이름 익명화는 기존 시험 기대값 변경이 필요해 사람 적대 검증 후 별도 적용해야 한다. 기존 시험 기대값은 수정하지 않았다.

실제 Windows junction, Linux FIFO·교체 경쟁, Codex/Claude 실제 프로필과 `--config`·환경 변수, PostgreSQL heartbeat/activation, 화면 렌더링, 솔루션 배포와 PJ1 효과는 미실행이다.

## 메인 반영 (Claude, 2026-10-20)

- S6-01: Linux는 핸들 기준 열기로 교체 경쟁을 구조적으로 없앴다. 링크로 바뀐 `.claude`는 `{"file": ".claude"}` 실패(새 시험 `DirectorySwapReview`, 기기 Linux 이미지 통과). Windows SYSTEM 경로는 재분석 지점 사전 검사만 있어 교체 경쟁이 남는다.
- S6-03: 런처 인자·환경(`-c/--config`, `CODEX_HOME`, `CLAUDE_CONFIG_DIR`) 고정은 별도 작업으로 넘긴다(대기열).
- S6-05: 단계 전환은 설계대로 유지한다. 재설치 전 장치는 검사를 받지 않는다.
