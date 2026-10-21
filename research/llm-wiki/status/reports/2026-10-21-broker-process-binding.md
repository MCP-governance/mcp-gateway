미커밋

# DEV-81 F1 — 관리형 Linux 헤더 브로커의 AppArmor 프로세스 결속 (D-183)

- 작업자: Codex sol S3
- 시작 코드: `main`, `d86bf166b56adab401902fefd9431dbdc757d063`, 시작 작업 트리 깨끗함. fetch·브랜치 생성/전환·커밋·기기 접속·스택 기동 없음. Git은 상태·diff·HEAD 및 스냅샷 도구의 현재 브랜치 조회만 수행했다.
- 정본: [DEV-81 끝의 메인 판단](../../analysis/local-endpoints-1021/README.md#메인-판단-2026-10-21), D-147·148·149·150, [DEV-35](../../analysis/dev35-loopback/README.md), [E13 원시 인덱스](../../analysis/real-env-20261020/e13/index.jsonl).
- 완료 조건: 승인 하네스의 정상 인증 유지, 같은 UID의 다른 프로세스·셸 자식의 활성 bearer 취득 거부, 메모리 경로 차단, 레이블/프로필 미확인 시 차단, 복구 확인.
- **판정: 부분 구현·강제 승격 보류. F1과 DEV-81은 열림이다. 현재 하네스의 `sh -c` 헤더 명령을 모든 셸 자식과 함께 분리하면 정상 인증도 차단된다. 경고 단계를 기본으로 남겼으며 해결 완료로 보고하지 않는다.**

## 결과

변경 파일은 `endpoint-agent/managed-linux.py`, `endpoint-agent/enforce-linux.py`, 새 `endpoint-agent/broker_binding.py`, `full_stack_lab/gateway/app/agent_service.py`의 Linux 키트 파일 목록, 새 `full_stack_lab/tests/header_broker_label_check.py` 및 본 보고·분석 근거·D-183·보안 경계·DEV-81 백로그다. 위키 규칙에 따라 위협 카탈로그/검토 stale 표식과 로컬 코드 스냅샷도 재생성했다. 과거 독립 검토의 코드 불일치 표시는 보존하며 이번 변경을 독립 검토 완료로 올리지 않는다. 제품 화면·라우트·Windows·직원 PC 키트는 변경하지 않았다. `status/current.md`는 공통 규칙에 따라 메인 통합용으로 남겼다.

브로커는 `SO_PEERCRED`의 UID와 accepted socket의 `SO_PEERSEC`를 확인한다. PID는 감사에만 남기며 프로세스 파일 경로를 다시 열지 않는다. PID 재사용과 `/proc/<pid>/attr/current` 읽기 사이의 경쟁을 인증에 도입하지 않는다. 정확히 승인된 `-bound-codex`, `-bound-claude`, `-bound-credential`만 허용한다. 모드 접미사는 정확한 ` (enforce)`만 제거하고 complain·하위/stacked·접두 일치는 거부한다. SO_PEERSEC가 없는 Python에서도 Linux UAPI 번호 31로 호출하며 커널이 지원하지 않으면 강제 모드는 거부한다.

`-bound-credential`은 두 하네스에서만 직접 `px` 전이 가능한 root 소유 native 고정 헬퍼다. 헬퍼는 고정된 Python `-I -S` 명령으로 헤더를 하네스의 stdout 파이프에 전달하므로 이 프로세스가 토큰을 잠시 받는 최소 위임 예외가 필요하다. 임의 셸·MCP stdio 서버·companion에 이 프로필로 갈 권한은 없다. 하네스의 기존 허용 명령은 전부 `px`로 도구 프로필에 들어가고, 그 안에서 실행한 자식도 같은 제한을 유지한다. 허용 목록 밖 실행 파일은 기본 거부한다.

강제 모드는 요청마다 AppArmor enabled·전체 필수 프로필의 enforce 상태·Unix/ptrace 중재 기능을 읽는다. 실패하면 기존 메모리 캐시가 유효해도 bearer를 내지 않는다. heartbeat의 `apparmor_enforcing`도 단계별 필수 프로필을 확인한다. 강제 프로필에 ptrace의 trace/read/tracedby/readby·sys_ptrace·proc mem/environ 읽기 거부를 정의했다. Yama 전역 설정은 바꾸지 않으며 아래 절차에서 실제 값을 기록한다.

설치 시 모듈을 root 프로그램 경로로 복사하고 다운로드 키트에도 포함한다. 프로필 적용 전에 `apparmor_parser -Q -T`로 구문 실패를 확인하도록 했다. 기존 시험 파일의 기대값·AST는 수정하지 않았다. 기존 `checks` 추출 시험의 전역 이름 공간을 늘리지 않도록 그 함수의 단계별 suffix 선택은 함수 안에 두었고, 새 시험에서 기존 이름 공간만 주입해 경고·강제·도구 프로필 complain을 확인했다. 함수 참조 검색 결과와 코드 심볼/행/판본 해시는 [원시 JSON](../../analysis/local-endpoints-1021/binding-checks.json)의 `extraction_inventory`, `code_symbols`, `sha256`에 있다.

## 단계 전환과 정상군 위험

| 단계 | 설정·프로필 | bearer 응답 | 운영 판단 |
| --- | --- | --- | --- |
| 경고 | root `config.json`의 `broker_binding: "warn"`; 키 누락도 동일. 기존 프로필 렌더링 보존 | 같은 UID에는 기존처럼 응답하고 `header-broker-binding` journal에 레이블·사유 기록. 다른 UID/자격 읽기 실패는 계속 거부 | 기존 동작 보존이 목적. F1은 남음. PJ1 효과 미검증 |
| 강제 | `broker_binding: "enforce"`와 `profile(..., binding_mode="enforce")`의 전체 프로필을 함께 적용 | 정확한 승인 레이블·UID·로드 상태일 때만 응답. 잘못된 모드 값도 거부 | **현재 정상 헤더 셸 경로와 충돌하므로 운영 승격 금지** |

새 설치도 기본은 경고다. 경고는 AppArmor complain 모드가 아니라 브로커의 명시적 이행 단계다. 기존 AppArmor/nft/준수 통제를 해제하지 않는다. 경고 로그에는 커널 레이블·PID·고정 사유만 있고 bearer·장치 키·원시 예외/응답은 없다. 이 journal은 로컬 진단 기록이며 게이트웨이의 append-only 감사 원장으로 전송되는 새 기능은 아니다.

현재 `profile()`의 설명과 기존 self-check에 하네스 헤더 명령이 `sh -c`로 시작한다고 기록돼 있다. 엄격한 전이에서 이 셸은 `-bound-<하네스>-tool`로 가고 헬퍼 실행이 거부된다. **`dash ix`를 남기거나 셸 전용 프로필에 헬퍼 실행을 허용하는 것은 해결이 아니다.** AppArmor 실행 규칙은 동일 실행 파일의 인자·명령 목적을 구별하지 않으므로 같은 셸로 실행하는 명령이 다시 헬퍼에 닿는다. 정상 호출을 통과시켰다는 실기기 증거는 없다.

경고 → 강제는 메인이 공식 하네스/고정 판본의 직접 실행 인증 경로를 확보한 뒤, 별도 시험 계정에서 아래 정상·음성·실패·복구군을 모두 확인한 경우에만 한다. 자동 승격·전역 sysctl 변경·실행 중 PJ1 계정 재설치는 추가하지 않았다. 코드만 교체할 때도 서비스가 새 모듈을 읽을 수 있게 세 파일을 함께 배포해야 하며 기존 서비스는 재시작 전까지 구 코드를 쓴다.

## 검증

실행 환경: Windows, Python 3.10.5. 최종 실행 시각·정확한 명령·종료 코드·stdout/stderr·소스 SHA-256은 [binding-checks.json](../../analysis/local-endpoints-1021/binding-checks.json)에 기록한다. 재현 명령:

```powershell
python -B -X utf8 research/llm-wiki/analysis/local-endpoints-1021/verify_binding.py
```

| 확인 종류 | 결과 | 해석 |
| --- | --- | --- |
| 새 `header_broker_label_check.py` | **20/20 통과** | 실제 Header 함수 본문 + 대역 소켓/커널 상태. 일치·불일치·오류·미로드·경고·만료 캐시·UID·렌더링·키트 포함·AST 이름 공간. 실제 커널 효과 아님 |
| Python compile | 변경 Python 5파일 통과 | 문법 검사 |
| 파일/변경 범위 확인 | UTF-8 BOM 없음·LF·diff 공백 오류 0 | [최종 확인](../../analysis/local-endpoints-1021/binding-final-checks.json): 시험한 소스 해시 일치·기존 시험 및 current.md 미변경 |
| 기존 `managed_token_cache_check.py` | 1/1 통과 | 캐시 주기 AST 유지 |
| 기존 `loopback_owner_replies_test.py` | 9/9 통과 | 기존 대역/규칙 시험, 실제 netns 아님 |
| 기존 `managed_helper_unavailable_check.py` | 1 통과·Linux 1 생략 | Windows 고정 거부 bearer 회귀만 실행 |
| 기존 `launcher_pin_check.py` | 4 통과·Linux gcc 4 생략 | Windows 경로만 실행 |
| 기존 `user_command_settings_check.py` | 10 통과·오류 1·생략 4 | Windows 대역 `winreg.OpenKeyEx` 누락으로 실패, tomllib/Pydantic2/링크 환경 제약. 기존 시험 수정 안 함 |
| 기존 `managed_enforcement_check.py` | 오류 10 | Windows Python의 `grp` 모듈 부재. Linux import 회귀 미완료 |
| pyflakes | **미완료** | 모듈 미설치. 전체 수집기 종료 코드는 1이며 통과로 취급하지 않음 |
| AppArmor parser `-Q` | **미완료** | 로컬 parser 없음, `wsl.exe --list --quiet`도 `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`. 합성 경로 렌더링 [프로필](../../analysis/local-endpoints-1021/binding-profile.apparmor)은 텍스트 시험만 통과 |
| 위키 매핑·스냅샷·목록·링크 검사 | 재생성 후 오류 0·로컬 원문 누락 경고 119 | [원시 명령·시각·출력](../../analysis/local-endpoints-1021/binding-wiki-checks.json). 과거 독립 검토와 현재 코드가 다른 15파일의 stale 표시는 유지 |
| 실제 프로토콜·모델/하네스·upstream 효과·배포·PJ1 | **미실행** | 사용자 범위 밖. 이전 E13을 이번 결과로 세지 않음 |

현재 체크아웃의 E13 중 `managed-codex-fs-145132.out`에는 사용량 한도 오류가 있다. 인덱스의 rc 0만으로 정상 모델/하네스 호출 성공을 추정하지 않았다. [DEV-35](../../analysis/dev35-loopback/README.md)의 루프백/소유자 응답 분석은 설계 경계의 과거 근거로만 사용했다. D-62의 실제 제목은 강제/관찰 주체 분리이며, 관리형 계정 설치 흐름은 D-61 후속과 현재 코드도 함께 확인했다. WBS와 메인 판단의 범위 충돌은 찾지 못했다. DEV-81 상태는 계속 열림이다.

## 공식 자료·공개 스킬·OSS 검토

확인일 2026-10-21. 외부 스크립트·프로필·스킬을 실행하거나 새 의존성을 설치하지 않았다. 아래는 원문을 재배포하지 않는 URL/읽기 범위 기록이며 원문 파일 SHA-256은 확보하지 못했다.

- [AppArmor 공식 4.0 문법](https://gitlab.com/apparmor/apparmor/-/blob/v4.0.0/parser/apparmor.d.pod), [공식 렌더링](https://www.apparmor.net/man/4.0/apparmor.d/): `px`/`cx`, Unix connect/send/receive, ptrace 양방향 권한 절을 대조. v4.0.0 문서 상단 GPL v2 확인. 기존 AppArmor 의존성을 사용하고 문법만 참고했다. 별도 소스 commit과 PJ1 설치 판본은 미확인이다.
- [Linux Yama 공식 문서](https://docs.kernel.org/admin-guide/LSM/Yama.html): ptrace_scope 0~3, 1의 parent/PR_SET_PTRACER 예외, 2의 CAP_SYS_PTRACE 요건 확인. 기본값이나 PJ1 적용값을 가정하지 않는다. 이번에는 AppArmor의 trace/readby 거부를 선택했다.
- [Linux AppArmor lsm.c 고정 참조](https://code.googlesource.com/linux/torvalds/linux/+/24a0b5e196cf70ccff97bc0add6fa7178ad50cc4/security/apparmor/lsm.c): 검색에서 `apparmor_socket_getpeersec_stream`·`FLAG_SHOW_MODE`와 peer socket label 반환 본문을 확인했다. 전체 원문 재열기는 403, raw GitHub는 cache miss여서 **전문/라이선스/행 검증 완료로 세지 않는다**. 이 commit을 PJ1 커널 판본이라고 주장하지 않는다.
- [GitHub roddhjav/apparmor.d](https://github.com/roddhjav/apparmor.d): 프로필 프로젝트·GPL-2.0·기여/시험 경로와 초기 개발 상태 설명 확인. 고정 commit/API 확보는 웹 접근 실패 및 로컬 HTTPS WinError 10013으로 미완료. 코드 채택·복사 없음. 유지보수 성공이나 현재 호환성을 주장하지 않는다.
- [GitHub 공개 스킬 목록](https://github.com/openai/skills)과 `AppArmor SKILL.md` 검색: 이번 결속에 그대로 적용할 고정 스킬을 확인하지 못했다. 개별 스킬별 라이선스 방식을 확인했으며 외부 스킬 채택·설치 없음. 세션에 이미 있는 ponytail 스킬은 최소 변경·경계 검증 원칙에만 적용했다.

## PJ1 시험 절차 — 메인 실행용, 전부 미실행

**사전 조건:** 현재 PJ1 관리 계정에 강제 모드를 바로 적용하지 않는다. 별도로 승인된 시험 관리 계정에서 먼저 수행한다. 아래 `TEST_USER`는 그 계정의 실제 이름, `HARNESS_PID`는 그 UID로 실행 중인 승인 하네스 본체 PID다. 기존 다른 사용자의 세션·종료 케이스·프로필·스택은 건드리지 않는다. 예시는 PJ1 관리자 셸에서 저장소가 있는 경로를 `REPO`로 지정한 상태다.

1. 현황·백업: `id "$TEST_USER"`, `aa-status`, `cat /sys/module/apparmor/parameters/enabled`, `cat /sys/kernel/security/apparmor/features/network/af_unix`, `cat /sys/kernel/security/apparmor/features/ptrace/mask`, `cat /proc/sys/kernel/yama/ptrace_scope` 및 승인 Codex/Claude 버전·root 소유 ELF 경로를 기록한다. `/etc/apparmor.d/mcpgw-$TEST_USER`, `/usr/local/lib/mcpgw-managed/{managed-linux.py,enforce-linux.py,broker_binding.py}`, 시험 계정 config를 **root 전용 0700 디렉터리**에 백업한다. config/백업 내용을 보고서나 stdout에 출력하지 않는다. 이번 구현은 두 하네스 프로필 전체를 요구한다.
2. 경고 기준선: 세 Python 파일을 함께 설치하고 시험 계정 config에 `broker_binding: "warn"`을 원자 갱신한다(소유 root, 0600 유지). 시험 계정 서비스만 재시작한다. 기존 프로필로 Claude·Codex가 각각 기존 관리형 context7의 `resolve-library-id`를 자연어로 호출하게 한다. 실제 도구 실행 및 게이트웨이의 해당 주체 `decision`·`policy_id`·upstream 효과를 기록한다. `journalctl -u "mcpgw-managed-$TEST_USER.service" --since ...`에서 커널 레이블과 warn 사유를 확인한다. 미인증·다른 정책 차단은 정상군 통과가 아니다.
3. **강제 승격 전 필수 관문:** 직접 실행 인증 경로를 공식 하네스의 고정 판본에서 확보한다. 현재 `sh -c` 그대로면 여기서 멈추며 경고를 유지한다. 이후에만 실제 root 관리 실행 파일/companion 경로를 인자로 `enforce-linux.py`의 `profile(..., managed=True, binding_mode="enforce")`를 렌더링한다. 설치기를 재실행해 enrollment token을 소모하거나 기존 계정을 재등록하지 않는다. `apparmor_parser -Q -T <렌더링 파일>` 성공과 diff 검토 후, 시험 계정 프로세스를 로그아웃한 상태에서 해당 파일만 `apparmor_parser -r`로 로드한다. 브로커 config도 `enforce`로 바꾸고 시험 서비스만 재시작한다. 필수 8개 프로필이 전부 enforce인지 확인한다. 코드·profile·config 조합을 함께 기록한다.
4. 같은 UID 헬퍼 음성군: 아래처럼 관리자 프로세스가 stdout을 메모리에서 분류해 **bearer를 인쇄하지 않게** 한다. `sudo -iu`의 로그인 프로필과 `sudo -u`의 비관리 프로필을 각각 시험한다. 전자는 exec/socket 거부, 후자는 실행됐어도 broker 레이블 거부가 기대된다. 종료 코드만 보고 성공으로 세지 않고 같은 시각의 kernel AppArmor 거부 또는 broker `deny` 사유를 대조한다.

```bash
python3 - "$TEST_USER" <<'PY'
import json, subprocess, sys
user = sys.argv[1]
helper = '/usr/local/lib/mcpgw-enforcement/mcpgw-' + user + '/header-helper'
for route in ('-iu', '-u'):
    result = subprocess.run(['sudo', route, user, helper], capture_output=True, text=True, timeout=15)
    try:
        answer = json.loads(result.stdout)
    except ValueError:
        answer = {}
    value = answer.get('Authorization', '')
    active = isinstance(value, str) and value.startswith('Bearer ') and value != 'Bearer endpoint-not-active'
    print(json.dumps({'route': route, 'exit': result.returncode, 'active_bearer': active}))
    if active:
        raise SystemExit('FAIL: active bearer returned')
PY
```

5. 하네스 자식 음성군: 실제 Claude와 Codex의 셸 도구에서 **bash뿐 아니라 dash/sh, 절대 경로 및 명령 중첩으로** 위 고정 헬퍼 실행을 시도한다. 실제 모델의 셸 도구 거부 메시지와 `-bound-<하네스>-tool`의 exec/소켓 거부가 함께 있어야 한다. 허용된 stdio/companion도 같은 도구 프로필인지 확인한다. 임의 MCP 서버를 만들지 않는다. 필요하면 기존 E13의 실제 공개 OSS filesystem 서버를 승인 범위 안에서 사용한다. API 오류·모델 한도·검사기 종료는 통과가 아니다.
6. 정상군: 새 세션의 Claude와 Codex 각각에서 앞의 동일 context7 호출을 수행하고, broker `allow`의 정확한 레이블·활성 장치·정책 판정·실제 upstream 실행을 연결한다. **현재 코드는 헤더 명령 호환 관문을 해결하지 않아 이 정상군을 통과했다고 주장할 수 없다.** 장치 토큰이나 `Authorization`을 파일·하네스 설정·환경 변수에 넣어 통과시키지 않는다.
7. ptrace·메모리 음성군: 실제 하네스 PID/UID를 관리자가 대조한 뒤 아래를 실행한다. 실패가 AppArmor 또는 실제 Yama 설정 때문인지 로그/값을 함께 남긴다. gdb 설치 유무를 차단 효과로 세지 않는다. 이 코드는 메모리 내용을 출력하지 않는다. 잘못 허용되면 즉시 detach하고 실패로 종료한다.

```bash
sudo -u "$TEST_USER" python3 - "$HARNESS_PID" <<'PY'
import ctypes, errno, json, os, sys
pid = int(sys.argv[1])
libc = ctypes.CDLL(None, use_errno=True)
attached = libc.ptrace(16, pid, None, None) == 0
attach_errno = ctypes.get_errno()
try:
    try:
        fd = os.open('/proc/%d/mem' % pid, os.O_RDONLY)
    except PermissionError:
        memory_denied = True
    else:
        os.close(fd)
        memory_denied = False
finally:
    if attached:
        os.waitpid(pid, 0)
        if libc.ptrace(17, pid, None, None) != 0:
            raise RuntimeError('detach failed: administrator must resume test process')
print(json.dumps({'ptrace_denied': not attached, 'errno': attach_errno, 'memory_denied': memory_denied}))
assert not attached and attach_errno in (errno.EPERM, errno.EACCES) and memory_denied
PY
```

8. 미로드·오류·복구군: **호스트 AppArmor 서비스를 끄지 않는다.** 시험 계정 하네스만 종료하고 root 시험 스크립트에서 `trap 'apparmor_parser -r "$TEST_POLICY"' EXIT`를 먼저 건 뒤 시험 계정의 정책 파일만 `apparmor_parser -R "$TEST_POLICY"`로 내린다. root 브로커의 활성 캐시가 남은 상태에서 4번의 `sudo -u` 요청이 거부되고 `profiles-not-enforcing`이 기록되는지 확인한다. 이 실험은 해당 계정 **프로필 미로드**이며 AppArmor 모듈 전체 disabled 실험과 구별한다. 모듈 disabled·SO_PEERSEC 읽기 실패는 새 단위 시험에서는 확인했지만 실제 커널에서는 별도 격리 환경이 필요하다. `finally/trap`으로 프로필을 복구하고 service 상태·필수 enforce·정상 호출을 재확인한다. 제거/복구 사이 heartbeat가 격리시켰다면 기존 독립 활성화 절차로 복구하며 임의 DB/원장 수정은 하지 않는다.
9. 시험 실패/종료 시 root 백업의 **코드·정책·설정 세트**를 되돌리고 해당 서비스만 재시작한다. 새 강제 프로필을 제거해야 하면 시험 계정 프로세스가 모두 종료됐음을 확인하고 백업 정책을 다시 로드한다. 이후 두 정상 호출과 경고 상태, 다른 계정/스택에 영향 없음을 확인한다. 테스트 산출물은 토큰 없이 시간·PID·커널 레이블·decision/policy_id·효과만 보관한다.

## 실패·미완료·한계

- AppArmor parser와 실제 커널 로드는 미완료다. 렌더링 문자열 검사를 정책 문법/활성화/효과로 세지 않는다.
- **운영 가능한 강제 결속은 미완료다.** 현재 shell-based 헤더 명령과 모든 셸 자식의 분리는 동시에 정상 동작하지 않는다. 경고 모드가 이 모순을 해결하지 않는다.
- 일반 계정의 모든 기존 세션이 관리 로그인 프로필 안에 있다는 설치 가정은 유지된다. 승인 하네스 내부 코드 실행, exec 없는 fork, root 침해, 커널 결함, 모든 FD 전달 경쟁의 제거를 입증하지 않았다. SO_PEERSEC는 커널 socket label이며 응용 코드의 무결성 증명이 아니다.
- 관리형 Windows는 실측 후 별도 판단한다. 직원 PC 키트는 같은 사용자 프로세스를 막지 못한다. 이는 D-170의 조직 통제 의존으로 경계 문서에 명시했다.
- F2 브라우저 Origin·DEV-73 실행기·게이트웨이 정책·토큰 TTL은 변경하지 않았다.

## 다음 작업

DEV-81을 열림으로 유지한다. 메인은 직접 실행 인증 경로의 공식 판본/호환성을 먼저 확인하고, Linux에서 pyflakes·기존 import 회귀·AppArmor `-Q`를 완료한다. 그 다음 별도 PJ1 계정에서 위 정상·음성·실패·복구군을 실행해 근거를 붙인다. Windows·키트·웹 Origin을 합쳐 Linux 부분 구현의 성공률로 계산하지 않는다.

## 사용자에게 필요한 입력

없음. 현재 PJ1 계정에 대한 배포/실행은 수행하지 않았으며 본 보고는 메인 인계 절차다.

## 방향 제안

공식 하네스에서 **헤더 인증 명령의 argv 직접 실행**을 지원하는지 고정 소스로 먼저 확인하는 것이 다음 관문이다. 확인되면 하네스 → 고정 native 헬퍼 → 한정 자격 프로필의 직접 전이로 연결한다. 기능이 없으면 그 지원을 공식 구현에 요청하거나, bearer를 하네스에 내주지 않는 root 관리 전송 경로를 별도 설계로 검토한다. 후자는 MCP 전송·신원 결속·감사·네트워크 정책까지 범위가 넓어 이번에 구현하지 않았다. `sh` 인자 검사·PID/경로 확인·느슨한 셸 프로필을 대체 수단으로 채택하지 않는다. 채택은 메인이 판단한다.
