# D-151 Windows 설정 환경 검사 적대 검증

- 검토자: Codex sol, 2026-10-20.
- 브랜치: `10/20-windows-config-env-review`; 기준 HEAD `3d9e58ab24377f9829a0f8002929cfc5d398df5c`(Claude Sonnet). 시작 작업 트리는 깨끗했다. 커밋·푸시·배포 없음.
- 대상: `endpoint-agent/managed-windows.py:351-395`의 `checks`, `full_stack_lab/gateway/app/main.py:1357-1372` 입력 모델, HEAD의 기존 시험 대역 7줄, D-148 단계 전환.
- 원격 HEAD 재조회는 GitHub 접속 실패로 미확인이다. 현재 파일과 HEAD를 기준으로 판단했다.
- [원본 실행 출력·환경·종료 코드](d151-windows-config-env-evidence.json), [작업 보고](../../status/reports/2026-10-20-d151-windows-config-env-review.md).

## 판정: B — 기존 시험 대역은 수정 후 채택

HEAD의 7줄은 명령 헬퍼 파일 검사의 기존 기대값을 약화하지 않았다. 레지스트리 의존성을 격리하려는 목적도 타당하다. 그러나 `sys.modules['winreg']`를 불완전한 객체로 교체하면 실제 observer 모듈 import가 사용하는 표준 라이브러리까지 영향을 받는다. 이 PC의 깨끗한 Windows Python 3.10.5 프로세스에서 기존 D-148 시험은 오류 1건, D-151 시험은 오류 11건으로 실패했다. **그대로 A로 채택할 수 없다.**

또한 `OpenKey`에서 항상 `FileNotFoundError`를 던지는 대역은 「SID 하이브는 존재하고 Environment 키/값만 없음」과 「하이브 자체가 미탑재여서 확인 불가」를 구별하지 않는다. 후자를 정상으로 인증하는 제품 동작을 보강하면 파일 발견 목록의 기존 정확 일치 기대값과도 충돌한다. **기존 시험 변경 필요** 규칙에 따라 기존 파일과 제품 코드를 고치지 않고 구현을 중단했다. 새 적대 시험은 실패를 그대로 반환하며 `expectedFailure`나 성공 전환 래퍼를 사용하지 않는다.

## 원자 조건·반례·근거

| ID | 조건 | 확인 결과와 코드 근거 | 새 시험 / 판단 |
| --- | --- | --- | --- |
| W151-01 | SID 하이브 미탑재 | `checks:363-371`은 전체 경로의 부재를 정상 처리한다. 깨끗한 프로필 + 없는 하이브 대역에서 `(True, [])` | `test_missing_hive_must_not_certify_environment_absence`: **실패**. 확인 불가를 정상으로 인증하는 결함 |
| W151-02 | SID는 있고 Environment 키/값만 없음 | 사용자가 두 변수를 설정하지 않은 정상 조건과 부합한다 | `test_loaded_hive_without_environment_key_is_clean`: 통과. W151-01과 구분해야 함 |
| W151-03 | `REG_EXPAND_SZ`, 빈 값·다른 자료형 | `QueryValueEx` 성공 여부만 보므로 값 확장이나 자료형 판정 전에 실패한다 | `test_case_insensitive_names_and_expand_string_are_detected`, `test_empty_and_unusual_value_types_still_count`: 통과 |
| W151-04 | `codex_home` 등 이름의 대소문자 | Windows 레지스트리 조회는 이름 대소문자를 구별하지 않는다. 대문자로 조회하는 제품 코드는 결함 아님. 기존 FakeRegistry는 Python dict의 대소문자 구별을 그대로 사용 | 대소문자 비구별 새 대역으로 통과. 실제 winreg 대소문자 시험은 미실행 |
| W151-05 | `Volatile Environment` 및 세션 하위 키 | 제품은 SID의 `Environment` 한 곳만 연다. 별도 경로에 합성 값을 둬도 정상 | `test_volatile_and_machine_environment_are_currently_unread`: **범위 관찰** 통과. 해당 임의 값이 실제 하네스에 채택되는지는 Windows 로그인/세션 실험 필요 |
| W151-06 | 시스템 환경 | `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment` 미조회. 일반 관리 계정의 쓰기 권한 밖이어도 상속 가능한 설정 경로임 | 같은 범위 관찰 시험. 관리자 설정·기존 시스템 설정과 일반 직원 우회 권한은 구별 |
| W151-07 | 이미 실행 중인 프로세스·부모 셸 환경 | 현재 레지스트리 스냅샷과 다른 상태를 가질 수 있음. Windows 런처 `harness_launchers:300-321`은 CA만 설정하고 두 변수는 지우지 않음 | `test_process_environment_is_currently_unread`, `test_registry_hit_then_removal_changes_snapshot_only`: 범위 관찰 통과. 실제 하네스 명령 실행은 미검증 |
| W151-08 | import 부재·권한·I/O 오류 | `checks:372-373`은 `ImportError`/`OSError`를 고정 `env` 실패로 변환 | import, open/query 오류 및 부분 성공 뒤 오류 시험 통과. 실제 ACL 장애 시험 아님 |
| W151-09 | 값·예외 본문 비누출 | 변수 값은 QueryValueEx 반환으로 메모리에 **읽힌다**. 보고에는 반환값을 쓰지 않고 고정 파일 표기·빈 키 목록만 보냄. 「값을 읽지 않는다」는 표현은 부정확 | 고정 표기·합성 비밀 표식 비포함 시험 통과. DB 대역의 detail/사건에도 고정 표기만 보존 |
| W151-10 | 위조 true·원장 보존 | `endpoint_plane.heartbeat:830-873`은 발견 항목이 있으면 true를 false로 정규화하고 사건 INSERT. 기존 사건 UPDATE 없음 | `test_fixed_environment_finding_overrides_true_and_is_append_only`: AsyncMock 통과 |
| W151-11 | 구형 에이전트 단계 전환 | `endpoint_plane.managed_checks:696-703`은 미보고 장치를 유예. D-148 전용 장치도 D-151 장치와 같은 검사 이름·true를 보냄 | `test_d148_latch_does_not_attest_d151_agent_version`: 통과. 표식은 D-151 코드 설치/실행 증명이 아님 |
| W151-12 | 시험 대역의 호스트 의존성 | `user_command_settings_check.py:190-195`의 대역에 `OpenKeyEx` 없음. `agent.py:827` → `platform.system()` → Python 3.10 `win32_ver()`에서 AttributeError | `test_original_registry_fixture_supports_cold_observer_import`: **오류**. Windows 전용이며 Linux에서는 이 사례만 생략 |

## 로그인 시점 반박

1. 관리 계정이 로그아웃해 SID 하이브가 올라와 있지 않다. 프로필의 `NTUSER.DAT`에는 앞서 저장된 `CODEX_HOME`이 있을 수 있다. `set_user_environment:228-267`도 로그아웃 시 파일 하이브를 직접 올리는 별도 경로를 갖고 있지만 `checks`는 이를 사용하지 않는다.
2. 서비스는 없는 하이브를 변수 없음으로 보고 정상 heartbeat를 보낼 수 있다. `serve:678-681`은 정상 응답 뒤 자격을 캐시에 최대 120초 둔다.
3. 사용자가 로그인하면 프로필과 사용자 환경이 로드되고 부모 환경을 상속한 하네스를 시작할 수 있다. 서비스의 다음 검사는 로그인 이벤트에 결속되지 않은 `time.sleep(60)` 루프(`managed-windows.py:725`)다. 정책 조회·관측 작업 시간도 더해져 정확히 60초라는 상한은 아니다.
4. `serve_pipe:437-440`은 캐시 만료만 확인하고 환경을 다시 검사하지 않는다. 따라서 로그인 **이후 첫 heartbeat에서 잡힌다**는 것은 실행 전 차단 보장이 아니다. 캐시 유무·현재 게이트웨이 상태에 따른 실제 토큰 취득·헬퍼 실행은 실기기 미실행이며 성공했다고 주장하지 않는다.

이는 코드 순서와 공식 환경 상속 규칙에 근거한 시점 반례다. 하이브 부재를 `env` 실패로 바꾸면 미확인 상태를 정상 인증하는 결함은 줄지만, 로그인 후 환경 변경·셸의 직접 설정·확인 사이 변경까지 막는 시작 시점 잠금은 되지 않는다. 임의 `reg load`나 재귀 탐색을 검토 없이 추가하지 않는다. 현재 격리는 정상으로 돌아와도 관리자 재활성화가 필요하므로 미탑재 계정 처리에는 가용성 비용도 있다.

## 기존 시험 변경 필요

**다음은 수정 제안이며 이 작업에서는 적용하지 않았다.** 소유자가 적대 검증 후 결정할 변경 목록이다.

| 파일·위치 | 필요한 변경 | 유지할 검증 강도 |
| --- | --- | --- |
| `tests/user_command_settings_check.py:190-201` | 없는 하이브 대역 대신 「존재하는 SID + 변수 없는 환경」을 경로별로 표현. observer import의 호스트 조회는 레지스트리 대역과 분리하거나 필요한 API를 지원하는 대역 사용 | 등록 홈의 파일만 검사하고 서비스 HOME을 읽지 않는 조건·정확한 파일/키 발견 목록은 유지. 예외 삼키기·플랫폼 전체 생략 금지 |
| `tests/windows_config_env_check.py:103-104` | `test_signed_out_account_has_no_hive_and_no_environment_key`를 하이브 부재와 환경 키 부재로 분리. 하이브 확인 불가는 false + `env`, 실제 하이브의 환경 키/값 없음만 true | 확인 불가를 true로 기대하는 현재 조건을 보안 강화 방향으로 변경해야 함. 사람 결정 전 제품 변경 보류 |
| 같은 파일 `FakeRegistry`, import 범위 | 대소문자 비구별·자료형 반환·경로별 핸들을 표현하고 호스트 감지 import와 충돌하지 않게 격리 | REG_EXPAND_SZ·권한 오류·값 비누출을 명시적으로 시험. 테스트 순서나 `platform` 캐시 예열에 의존 금지 |

최소 제품 수정 후보는 SID 하이브 존재와 환경 키/값 부재를 분리하고, SID 하이브 확인 불능은 기존 고정 `env`로 실패시키는 것이다. 기존 기대값을 바꾸지 않고 이 수정까지 완료했다고 보고할 수 없어 적용을 멈췄다. 휘발성 환경·실제 프로세스 환경은 별도 읽기/실행 경계를 검토해야 하며 이를 모두 고쳤다고 합치지 않는다.

## 입력 모델·단계 전환

`main.py:1357-1363`은 기존 고정 표기에 `env:CODEX_HOME`, `env:CLAUDE_CONFIG_DIR`, `env`만 추가했다. JSON 값·임의 파일명·임의 env 이름을 받는 변경은 아니다. 소문자 레지스트리 이름도 에이전트 보고에서는 대문자 고정 표기가 되어야 하므로 `env:codex_home` 거부는 타당하다. 모델 실행 검증은 로컬 Pydantic 부재로 생략됐고, 원본 AST 대조까지만 확인했다.

D-148 미보고 장치의 유예와 보고 후 필수화는 유지된다. 그러나 D-151은 검사 이름·정책 버전을 따로 추가하지 않았고 Windows 에이전트 파일을 정책 해시가 증명하지도 않는다. 따라서 **D-148 이전 장치뿐 아니라 D-148만 설치된 장치도 D-151 환경 검사가 없을 수 있다.** 미보고 회귀 차단 표식으로 에이전트 판본 검증을 대신할 수 없다. 새 정책 ID·DB 변경·권한 완화는 제안하지 않았다.

## 실행 결과

Windows Python 3.10.5, 2026-10-20. 각 명령은 별도 프로세스로 실행했다. [증거 JSON](d151-windows-config-env-evidence.json)에 명령·종료 코드·stdout/stderr를 보존했다.

| 검사 | 결과 |
| --- | --- |
| 새 `windows_config_env_review_check.py` | 14건: 12통과·1실패(하이브 미탑재)·1오류(기존 winreg 대역). 종료 1 |
| 기존 `windows_config_env_check.py` | 8건 실행, 하위 사례 포함 오류 11·Pydantic 1생략. 종료 1 |
| 기존 `user_command_settings_check.py` | 15건: 10통과·1오류·4생략(Pydantic·tomllib·링크 권한). 종료 1 |
| `python -m py_compile` 제품 2파일·새 시험 | 통과 |
| `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과. JS 변경 없음 |
| 위키 목록 검사 | 통과 |
| 위키 전체 검사 `--ci-ignored-local-sources` | 기존 코드 매핑 해시 등 오류 22·경고 119로 실패. 이번 판정 문서 작성 전 실행 결과이며 새 문서 링크 검사는 별도 수행 |
| 게이트웨이 이미지·실제 DB·Windows 레지스트리 변경·PJ1 실제 하네스·배포 | 미실행 |

새 시험의 통과 중 W151-05~07은 **현재 검사 범위를 재현한 것**이다. 보안 차단 성공 건수에 넣지 않는다. 입력 모델·레지스트리 대역·DB 대역은 실제 MCP 실행 증거가 아니다.

## 공식 근거와 외부 코드 검토 범위

- [Microsoft CreateEnvironmentBlock](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createenvironmentblock): 사용자 프로필 로드와 사용자 환경, 상속 옵션. 로그인 시점 반례에 사용했다.
- [Microsoft Environment Variables](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables), [Changing Environment Variables](https://learn.microsoft.com/en-us/windows/win32/procthread/changing-environment-variables): 프로세스별 환경과 자식의 복사 상속. 레지스트리 스냅샷을 현재 프로세스 환경으로 볼 수 없다는 근거다.
- [Microsoft Registry.GetValue](https://learn.microsoft.com/en-us/dotnet/api/microsoft.win32.registry.getvalue?view=net-10.0): 값 이름의 대소문자 비구별. [Registry value types](https://learn.microsoft.com/en-us/windows/win32/sysinfo/registry-value-types): REG_EXPAND_SZ 의미.
- [Microsoft 레지스트리 키 예제](https://learn.microsoft.com/en-us/powershell/scripting/samples/working-with-registry-keys?view=powershell-7.6): `Environment`와 `Volatile Environment`가 별도 키임을 확인. 임의 변수의 하네스 상속까지 증명하는 자료는 아니다.
- [CPython 3.13.16 winreg](https://docs.python.org/3.13/library/winreg.html): OpenKey·QueryValueEx의 반환값/예외. 배포 고정 버전은 `full_stack_lab/gateway/windows-python.json`의 3.13.16이며 이번 실제 실행은 로컬 3.10.5다.
- 관련 GitHub 공개 스킬·`python/cpython` winreg/시험을 검색했다. 외부 스킬은 관련성·고정 commit·유지보수 범위를 확인하지 못해 채택/실행하지 않았다. CPython 고정 3.13.16의 [LICENSE](https://github.com/python/cpython/blob/v3.13.16/LICENSE)에서 PSF License Version 2를 확인했고, 고정 소스 `PC/winreg.c` 및 Git 원격 commit 조회는 접근 실패였다. 가변 main 검색 결과를 고정 소스 검증으로 세지 않는다. 새 의존성·외부 코드 복사 없음.

공식 페이지는 2026-10-20 해당 절을 열람했으며 원문 전체를 재배포하지 않는다. 하이브·세션·실제 하네스 효과를 보장하는 독립 실험은 남아 있다. 기존 D-151의 정상·오류·비누출 구현을 전부 거부하는 C 판정은 아니지만, 현재 시험 대역과 정상 인증 범위를 그대로 채택할 근거도 없다.
