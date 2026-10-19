# 2026-10-20 loopback owner replies 시험 원인 조사

- 작업자: Codex luna
- 코드 기준: `c986fdd` (`10/20-loopback-test`, 시작 시 clean, `origin/main`과 동일)
- 시작 근거: DEV-35, D-119, `tests/loopback_owner_replies_test.py`의 솔루션 기기 Python 3.12 실패 보고
- 해결할 문제와 완료 조건: 보고된 2 failures·4 errors가 제품 회귀인지 기존 시험의 환경/계약 가정 문제인지 코드와 Git 이력으로 구분한다. 기존 시험은 바꾸지 않는다.

## 결과

실패는 제품의 loopback 규칙 회귀가 아니라 D-119 시험이 이후 D-124의 설치 전송 검증 및 현재 설치 함수 호출 계약을 반영하지 못한 데서 발생한다.

1. 두 failure는 `test_bootstrap_selects_employee_uid_only_for_a_separate_managed_account`에서 발생한다. fixture는 `enrollment.json`에 `{}`를 쓰지만, `bootstrap.main()`은 D-124(`b7b3488`, 2026-10-18)부터 하네스 배치 전에 `managed-linux.verify_transport()`를 실행한다. 빈 객체에는 `gateway_url`이 없어 검증이 실패하고 `main()`이 1을 반환한다. 실제 키트의 등록 JSON은 게이트웨이 전송 설정을 포함한다. 해당 테스트는 이 전송 검증을 시험하려는 목적이 아니므로 fixture 또는 검증 대역이 필요하다.
2. 네 error는 `test_invalid_owner_fails_before_enrollment`의 mock 인자가 `SimpleNamespace(user, owner_uid)`뿐인 데서 발생한다. D-119가 추가한 잘못된 소유자 조기 거부는 `managed-linux.install()`에서 계정·OS 조건을 확인한 뒤 `enforcer.nft_rules(... owner_uid=...)`로 수행된다. D-124는 그 앞에 등록 파일 읽기와 `verify_transport()`를 추가했다. 현재 시험은 `args.enrollment`이 없어 이 선행 단계에서 `AttributeError`가 난다. 이 검증은 등록 토큰을 소비하지 않으며, 소유자 유효성 검사는 네트워크 등록 요청 전에 여전히 수행된다.
3. Git 이력으로 확인한 계약 변경은 D-119 구현 `376221a`와 D-124 구현 `b7b3488`이다. 시험 파일은 D-119 커밋에서 추가된 이후 수정되지 않았다. 이 테스트는 소유자 UID 규칙, nftables 규칙 생성, 관측 분류의 9개 케이스를 확인한다. 로컬 Windows 실행에서는 Linux 전용 `grp` import 때문에 bootstrap 하위시험 2개가 추가로 error였고, 따라서 솔루션 기기 Linux 실행 결과로 혼동하지 않는다.

기존 시험 파일 변경이 필요하다. 적대 검토를 위해 제안하는 최소 보정은 다음과 같다. 제품 동작을 바꾸지 않고 실제 설치 전송 설정 모양을 주며, 소유자 시험이 읽기/검증을 대역 처리한 뒤 토큰 소비 전 조기 거부를 확인하게 한다.

```diff
@@ test_bootstrap_selects_employee_uid_only_for_a_separate_managed_account
-            enrollment.write_text("{}")
+            enrollment.write_text('{"gateway_url":"https://gateway.example"}')
@@ test_invalid_owner_fails_before_enrollment
+                 mock.patch.object(managed, "verify_transport"), \
                  mock.patch.object(managed, "load_module", return_value=enforcer), \
                  mock.patch.object(managed, "request") as request, self.assertRaises((ValueError, KeyError)):
                 try:
-                    managed.install(SimpleNamespace(user="managed", owner_uid=owner))
+                    managed.install(SimpleNamespace(
+                        user="managed", owner_uid=owner, client=[],
+                        enrollment=SimpleNamespace(read_text=lambda: "{}")))
                 finally:
                     request.assert_not_called()
```

위 diff의 `+`/`-`는 제안 변경 표시이며 `...`는 기존 시험 본문을 뜻한다. 제안 fixture는 전송 URL 형식만 유효하게 하고 네트워크 요청을 하지 않는다. 승인 전에는 이 변경을 적용하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 실패 재현 | `python -X utf8 full_stack_lab/tests/loopback_owner_replies_test.py`, Windows, 2026-10-20 | 9 tests, 6 errors. 2건은 Windows의 `grp` 미지원, 4건은 누락된 `args.enrollment`; Linux 이미지의 보고된 2 failures·4 errors와 동일 원인을 보이는 환경 차이 | 현재 실행 출력 |
| 정적 검사 | `python -X utf8 -m py_compile endpoint-agent/bootstrap.py endpoint-agent/managed-linux.py endpoint-agent/enforce-linux.py` | 통과 | 명령 종료 코드 0 |
| 변경 공백 검사 | `git diff --check` | 통과 | 명령 종료 코드 0 |
| 실기기·게이트웨이 이미지 | 솔루션 기기 / PJ1 | 미실행 | — |

## 실패·미완료·한계

기존 시험 파일을 바꾸지 말라는 작업 규칙에 따라 코드 수정은 중단했다. 따라서 솔루션 기기에서 보고된 전체 실패를 직접 재현하거나 제안 diff를 검증하지 않았다. 현장 nftables 동작과 D-119 실제 OS 효과도 이 조사 범위에서 확인하지 않았다. D-119 제품 함수의 계약은 코드에서 확인했으나 실기기 정상군·음성군 통과를 새로 주장하지 않는다.

## 다음 작업

기존 시험 수정 제안을 사람이 적대 검증하고 승인하면 `tests/loopback_owner_replies_test.py`만 보정한 뒤 솔루션 기기 게이트웨이 이미지에서 `python /repo/full_stack_lab/tests/loopback_owner_replies_test.py`를 실행한다. 이어 루트 규칙에 따라 솔루션 기기 배포 및 PJ1 실험은 별도 순서로 수행한다.

## 사용자에게 필요한 입력

없음. 기존 시험 변경 적용은 승인된 별도 작업으로 남긴다.

## 2026-10-20 적대 검증 및 최종 적용 — Codex sol

- 판정: **B — 수정 후 채택**. 위 luna 조사와 미적용 제안은 이력으로 보존한다. 이 절의 최종 diff와 검증 결과가 앞 절의 승인 대기·미검증 상태를 대체한다.
- 검증자: Codex sol. 브랜치 `10/20-loopback-test`, 시작 commit `f6c3071535e5f49231cff5b43e140182779700ac`. 시작 시 위 보고서만 미추적 상태였으며 본문을 덮어쓰지 않고 덧붙였다. luna의 `c986fdd`는 이전 조사 시점의 기준이다.
- 변경 범위: `full_stack_lab/tests/loopback_owner_replies_test.py`와 이 보고서만. 제품 코드·기존 nft/관측 기대값·정책·DB·백로그·현황·설계 결정 파일은 변경하지 않았다. 별도 D-번호는 지정되지 않았고 제품 설계 변경도 없어, 시험 변경 채택 근거를 이 절에 기록한다.
- 원격 HEAD: `git ls-remote --symref origin HEAD` 실행은 GitHub 연결 실패로 미확인. 기존 작업 브랜치를 그대로 사용했다. 커밋·푸시·스택 기동·원격 변경은 하지 않았다.

### 문제·결정·근거

현재 commit의 실제 경로를 대조했다.

1. `endpoint-agent/bootstrap.py:504–525`: 등록 파일 존재 확인 → `managed-linux.py` 동적 import → 등록 JSON의 실제 `verify_transport` → 직원/관리 계정 선택 → 패키지·하네스 준비 → 별도 관리 계정일 때만 **직원** 계정의 `pw_uid`를 `install_managed`에 전달한다. `install_managed`는 같은 파일 362–368행에서 `--owner-uid`를 명시하고 환경의 `SUDO_UID`로 보충하지 않는다.
2. `endpoint-agent/managed-linux.py:165–215`: root 확인 → 등록 JSON 읽기 → `verify_transport` → 관리 계정·그룹·세션·필수 도구·AppArmor 확인 → 실제 `enforcer.nft_rules(... owner_uid=...)` → 지정 소유자 `pwd.getpwuid` → 바이너리/설치 경로 준비 → `request(..., "/oauth/device-enroll", ..., credential=False)`. JSON을 읽고 전송 설정을 검증하는 행위와 서버에 일회용 등록 토큰을 보내는 행위는 다르다. D-119의 조기 거부 경계는 후자 이전이며 D-124가 앞의 로컬 검증을 추가한 것은 이 경계를 바꾸지 않는다.
3. `endpoint-agent/managed-linux.py:79–89`, `endpoint-agent/agent.py:721–738,876–882`: `verify_transport`는 실제 agent의 URL 검증과 SSLContext 생성/CA 지문 검증을 호출한다. 이 fixture의 HTTPS URL은 네트워크 접속을 만들지 않는다. 사설 CA 필드가 없는 fixture는 URL·기본 TLS 컨텍스트 경로만 통과하며 현장 키트 전체의 대용이 아니다.
4. D-119·D-124, `analysis/dev35-loopback/README.md`, `analysis/field-tls-d124/README.md`의 범위와 일치한다. 기존 stdlib `unittest.mock`·`json`·`ssl`만 사용했다. 새로운 기능·의존성·외부 스킬 도입 작업이 아니므로 추가 OSS를 도입하지 않았다.

제안의 전송 검증 무동작 대역은 소유자 시험만 분리하는 용도로 가능하지만, 그 자체가 조기 거부의 원인을 입증하지는 않는다. 특히 `(ValueError, KeyError)`만 받고 `request.assert_not_called()`만 검사하면 다른 선행 오류도 소유자 검사 성공으로 오인할 수 있다. 또한 기존 UID fixture는 어느 계정을 조회해도 `1000`을 반환하므로 `pwd.getpwnam(employee)`를 `pwd.getpwnam(account)`로 잘못 바꾸는 회귀를 구분하지 못했다. 따라서 원안 그대로 A를 주지 않고 다음과 같이 보강했다.

- bootstrap fixture에 HTTPS URL을 제공하고 실제 전송 검증을 유지한다. 기존 `load()`가 Windows에 제공하는 `pwd`·`grp` 모듈 대역을 **해당 with 범위에서만** 재사용해 동적 import의 `grp` 오류를 해소한다. 직원 UID `1000`과 관리 UID `1001`을 구분하고 직원 계정 조회 여부·설치 호출 1회를 추가 확인한다. 기존 성공 반환값·전달 UID 기대값은 그대로다.
- managed fixture에 `enrollment`·`client`를 제공한다. `load_module`은 미리 로드한 실제 enforce/agent 모듈을 선택하도록 제한한다. `verify_transport`와 `nft_rules`는 `wraps`로 **실제 구현을 실행하면서** 호출 인자를 검사한다. 무동작 대역을 쓰지 않는다.
- `0`, 관리 UID `1001`, 상한 초과 `2**32`는 실제 nft 소유자 검사에서 `ValueError`, 존재하지 않는 일반 UID `1002`는 nft 검사 후 설치기의 계정 조회 대역에서 `KeyError`여야 한다. 검증 함수·nft 함수 도달과 UID별 계정 조회 여부를 finally에서 확인하므로 다른 선행 예외로 통과할 수 없다.
- 바이너리 검사·등록 요청에 도달하면 `AssertionError`로 즉시 실패시킨다. 소유자 검사 누락/순서 회귀가 실제 바이너리 탐색·설치 쓰기·토큰 전송으로 진행되는 것을 막고, 기존 `request.assert_not_called()`도 유지한다.
- nft 표식·허용 목록·차단 순서·관측 분류 5개 시험과 장치 코드·환경 신원 배제 시험의 기대값은 변경하지 않았다.

### 검증

모두 2026-10-20, 이 작업 트리의 Windows / Python 3.10.5에서 실행했다. 아래 메모리 변이는 `inspect.getsource` → 한 곳 치환 → `compile/exec` → 실제 해당 unittest 실행으로 수행했으며 제품 파일에는 쓰지 않았다. 실패가 검출되어야 하는 변이 시험은 검출 수와 시험 오류 수를 함께 기록한다.

| 확인 종류 | 실행 명령·방법 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 수정 전 재현 | `python -X utf8 full_stack_lab/tests/loopback_owner_replies_test.py` | 9개 실행, 하위사례 오류 6건: bootstrap 동적 import `grp` 2건, `args.enrollment` 누락 4건 | 이번 검증자의 명령 출력 |
| 중간 보강안 실행 | 동일 명령 | 하위사례 실패 4건. `subprocess.run` 공용 대역 아래 실제 agent를 새로 import하면 Windows `platform.system()` 내부 호출과 충돌 | 명령 출력의 `stdout` 누락·nft 호출 0회; 실제 모듈을 대역 적용 전에 로드해 해결 |
| 최종 단위 회귀 | `python -X utf8 full_stack_lab/tests/loopback_owner_replies_test.py` | **9/9 통과**, 오류·건너뜀 없음 | `Ran 9 tests` / `OK`, 종료 코드 0 |
| 적대 변이 | PowerShell here-string을 `python -X utf8 -`로 전달, 아래 6개 변이를 각각 메모리에만 적용 | **6/6 검출**, 각 실행 오류 0건 | 아래 표 및 명령 출력 `6/6 in-memory mutations detected; production files unchanged` |
| 구문 검사 | `python -X utf8 -m py_compile full_stack_lab/tests/loopback_owner_replies_test.py` | 통과 | 종료 코드 0 |
| 공백·범위·인코딩 | `git diff --check`, `git status --short`, 변경 두 파일 UTF-8 decode/BOM/CR 검사 | 통과. 시험 1개+보고서만 변경, BOM·CR 없음 | 명령 출력·바이트 검사 |

| 메모리 변이 | 검출해야 할 회귀 | 결과 |
| --- | --- | --- |
| `transport_wrong_valueerror` | 전송 검증 위치에서 무관한 `ValueError`를 발생시켜 조기 거부로 오인 유도 | 하위사례 실패 4, 오류 0: nft 도달 검사로 검출 |
| `skip_owner_nft_check` | 설치기의 소유자 nft 검증 호출 삭제 | 하위사례 실패 4, 오류 0 |
| `skip_owner_account_check` | `pwd.getpwuid(args.owner_uid)`를 `pass`로 대체 | 하위사례 실패 1, 오류 0: UID 1002가 다음 단계에 도달하면 실패 |
| `enroll_before_owner_check` | nft 검사 앞에 `/oauth/device-enroll` 요청 삽입 | 하위사례 실패 4, 오류 0: 요청 가드·미호출 단언으로 검출 |
| `select_managed_uid` | bootstrap의 `getpwnam(employee)`를 `getpwnam(account)`로 대체 | 하위사례 실패 1, 오류 0: 1001 전달 검출 |
| `always_forward_owner` | `if companion else None`을 삭제해 같은 계정에도 소유자 전달 | 하위사례 실패 1, 오류 0 |

### 기존 시험 변경 필요 여부

**필요하며 이번 적대 검증에서 B로 채택한 최종안만 적용했다.** 기대값을 회귀 동작에 맞춰 낮추지 않았다. 잘못된 소유자에 대한 예외 종류를 좁히고, 실제 검사 도달·직원 계정 선택·토큰 미전송 검증을 추가했다. 앞 절의 미적용 제안은 이 최종안으로 대체한다.

### 실패·미완료·한계 및 다음 작업

- 로컬 통과는 오프라인 Python 함수·fixture 검증이다. Linux Python 3.12 이미지, 실기기 nft 적용, 실제 현장 CA/인증서 핸드셰이크, PJ1 하네스·E13·R1~R9·재부팅은 **미실행**이다. DB·OS·HTTP 대역이나 이 결과를 실제 MCP/독립 효과 증거로 올리지 않는다.
- 이 시험은 TLS 전체 부정 사례를 검증하지 않는다. CA 필드가 없는 HTTPS fixture에서 실제 검증 함수를 실행한 것이며, 실제 키트의 CA 지문 검증 및 장애 조건은 D-124의 `field_tls_check.py` 검증 범위다.
- DEV-35의 기기 후속: 솔루션 기기에서 검토된 작업 트리의 파일을 `/repo`로 전달/마운트한 **게이트웨이 이미지 안에서** `python /repo/full_stack_lab/tests/loopback_owner_replies_test.py`를 실행한다. `/repo`는 이번 시험 파일과 endpoint-agent가 함께 있는 저장소 마운트 경로여야 한다. 오래된 이미지 내장 파일만 돌린 결과를 이번 변경 검증으로 세지 않는다.
- 제품 배포나 PJ1 재설치가 필요한 DEV-35 실기기 검증은 기존 D-119 보고의 별도 절차를 따른다. 이번에는 제품 코드가 바뀌지 않아 배포하지 않았다.
- 사용자에게 필요한 입력: 없음. 커밋은 사람이 수행한다. 초안: `test(v2): 루프백 소유자 시험 적대 검증 및 설치 fixture 보강`.

### 최종 diff

아래는 검토 기준 `f6c3071` 대비 시험 파일의 전체 diff다. 이 보고서 추가분은 제외한다.

```diff
diff --git a/full_stack_lab/tests/loopback_owner_replies_test.py b/full_stack_lab/tests/loopback_owner_replies_test.py
index f70fb72..73e5093 100644
--- a/full_stack_lab/tests/loopback_owner_replies_test.py
+++ b/full_stack_lab/tests/loopback_owner_replies_test.py
@@ -1,6 +1,7 @@
 """Offline D-119 checks. No kernel rules, credentials, network or MCP server are used."""
 import importlib.util
 import io
+import json
 import os
 import re
 import sys
@@ -89,19 +90,27 @@ class Installer(unittest.TestCase):
         b = self.bootstrap
         with tempfile.TemporaryDirectory() as folder:
             enrollment = Path(folder) / "enrollment.json"
-            enrollment.write_text("{}")
+            enrollment.write_text('{"gateway_url":"https://gateway.example"}', encoding="utf-8")
             for companion in (True, False):
                 with self.subTest(companion=companion), \
                      mock.patch.object(sys, "argv", ["bootstrap.py", "--skip-login", "--enrollment", str(enrollment)]), \
                      mock.patch.object(b, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)), \
                      mock.patch.object(b, "employee_account", return_value="owner"), \
                      mock.patch.object(b, "managed_account", return_value=("managed", companion)), \
-                     mock.patch.object(b.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=1000), create=True), \
+                     mock.patch.dict(sys.modules, {"pwd": b.pwd, "grp": b.grp}), \
+                     mock.patch.object(b.pwd, "getpwnam", side_effect=lambda name:
+                                       SimpleNamespace(pw_uid={"owner": 1000, "managed": 1001}[name]),
+                                       create=True) as getpwnam, \
                      mock.patch.object(b, "ensure_packages"), mock.patch.object(b, "place_harnesses", return_value={}), \
                      mock.patch.object(b, "installed", return_value=False), mock.patch.object(b, "write_shims", return_value=[]), \
                      mock.patch.object(b, "install_managed", return_value={}) as install, redirect_stdout(io.StringIO()):
                     self.assertEqual(b.main(), 0)
+                    install.assert_called_once()
                     self.assertEqual(install.call_args.args[-1], 1000 if companion else None)
+                    if companion:
+                        getpwnam.assert_called_once_with("owner")
+                    else:
+                        getpwnam.assert_not_called()
 
     def test_device_code_command_on_success_failure_and_interrupt(self):
         with tempfile.TemporaryDirectory() as folder:
@@ -122,22 +131,36 @@ class Installer(unittest.TestCase):
     def test_invalid_owner_fails_before_enrollment(self):
         managed = load("managed-linux")
         enforcer = load("enforce-linux")
+        modules = {"enforcer": enforcer, "transport_observer": load("agent")}
+        bundle = {"gateway_url": "https://gateway.example", "enrollment_token": "unit-enrollment"}
         person = SimpleNamespace(pw_uid=1001, pw_gid=1001, pw_dir="/home/managed", pw_name="managed")
         for owner in (0, 1001, 2**32, 1002):
             with self.subTest(owner=owner), \
                  mock.patch.object(managed.os, "geteuid", return_value=0, create=True), \
                  mock.patch.object(managed.os, "getgrouplist", return_value=[], create=True), \
                  mock.patch.object(managed.pwd, "getpwnam", return_value=person, create=True), \
-                 mock.patch.object(managed.pwd, "getpwuid", side_effect=KeyError(owner), create=True), \
+                 mock.patch.object(managed.pwd, "getpwuid", side_effect=KeyError(owner), create=True) as getpwuid, \
                  mock.patch.object(managed.subprocess, "run", return_value=SimpleNamespace(returncode=1)), \
                  mock.patch.object(managed.shutil, "which", return_value="/installed"), \
                  mock.patch.object(Path, "read_text", return_value="Y"), \
-                 mock.patch.object(managed, "load_module", return_value=enforcer), \
-                 mock.patch.object(managed, "request") as request, self.assertRaises((ValueError, KeyError)):
+                 mock.patch.object(managed, "load_module", side_effect=lambda name, path: modules[name]), \
+                 mock.patch.object(managed, "verify_transport", wraps=managed.verify_transport) as verify_transport, \
+                 mock.patch.object(enforcer, "nft_rules", wraps=enforcer.nft_rules) as nft_rules, \
+                 mock.patch.object(enforcer, "trusted_binary", side_effect=AssertionError("owner check was bypassed")), \
+                 mock.patch.object(managed, "request", side_effect=AssertionError("enrollment was reached")) as request, \
+                 self.assertRaises(KeyError if owner == 1002 else ValueError):
                 try:
-                    managed.install(SimpleNamespace(user="managed", owner_uid=owner))
+                    managed.install(SimpleNamespace(
+                        user="managed", owner_uid=owner, client=[],
+                        enrollment=SimpleNamespace(read_text=lambda: json.dumps(bundle))))
                 finally:
                     request.assert_not_called()
+                    verify_transport.assert_called_once_with(bundle)
+                    nft_rules.assert_called_once_with(1001, [], 443, owner_uid=owner)
+                    if owner == 1002:
+                        getpwuid.assert_called_once_with(owner)
+                    else:
+                        getpwuid.assert_not_called()
 
 
 class Observer(unittest.TestCase):
```
