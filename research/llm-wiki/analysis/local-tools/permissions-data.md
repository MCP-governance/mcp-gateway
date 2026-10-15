# Windows 엔드포인트 최소 권한·실행·네트워크 정책 레퍼런스

조사일은 2026-10-14 KST다. Microsoft Learn 공식 자료 9개를 전문 확인하고 HTML 원문 snapshot을 `.task-local-20261014/data/permissions/`에 저장했다. URL, 확인 범위, SHA-256은 [permissions-data.json](permissions-data.json)에 기록했다. 기존 catalogs/solutions 검색 후 코드 공백에 연결되는 네 주제로 정리했다. 조사 중 Windows 설정·정책·방화벽은 변경하지 않았다.

## 현재 적용 우선순위

1. **실측 우선:** [managed-windows.py](../../../../endpoint-agent/managed-windows.py)의 `firewall_rules()`/`APPLY_RULES`는 계정 SID(`LocalUser`)와 Gateway 주소/포트로 egress를 제한한다. `firewall_enforcing()`는 정책 baseline을 확인한다. 이것은 계정의 모든 프로세스에 적용되는 규칙이지 앱별 sandbox가 아니다. 실제 Windows에서 effective state, WFP allow/drop, IPv4/IPv6, loopback을 먼저 검증한다.
2. **App Control for Business:** Windows 10/11 및 Server 2016+의 device-wide 실행 정책 후보. 모든 edition에서 정책이 유효하지만 Home은 PowerShell cmdlet을 제공하지 않고 per-user 정책도 없다. 조직 관리 배포, audit, 호환성, rollback을 설계한 후 `checks()`와 Gateway Windows state mapping에 effective policy를 추가하는 것이 가능한 코드 변화다.
3. **AppLocker:** 사용자별 규칙이 가능하지만 Microsoft는 강한 보호에 App Control 사용을 권고하고 AppLocker를 defense-in-depth로 설명한다. Windows 10 v2004+ 및 KB5024351, 구버전/Server edition과 GP/MDM 차이, `appidsvc`, script/DLL collection 설정을 확인해야 한다. DLL collection은 기본 off이며 사용하면 허용 앱의 모든 DLL 규칙이 필요하다.
4. **Restricted token:** `RunLevel Limited` scheduled task는 MCP 자식 프로세스의 restricted token이 아니다. Native launcher의 `CreateRestrictedToken`/`CreateProcessAsUser`와 matching ACL, handle/desktop/child process 검증이 필요하다. 현재는 설계 후보만 기록했다.

## Loopback 적용 범위

D-68/README의 “Windows 방화벽은 loopback을 거르지 않는다”는 문장을 Windows 전체에 일반화할 공식 근거는 확인하지 못했다. Microsoft WFP ALE 문서는 connection creation/listen과 app/user identity 기반 필터 계층을 설명하고, UWP 문서는 packaged-app loopback exception 절차를 설명한다. 이로써 현재 키트가 native Win32의 `127.0.0.1`, `::1`, IPv4-mapped IPv6를 막거나 허용한다고 결론 내릴 수 없다. README와 D-68에는 현재 키트의 미측정 한계로 한정해 두고, 실제 Windows에서 `netsh wfp capture start keywords=19`와 classify allow/drop event를 확인한 뒤 내용을 수정한다. Windows WFP와 Linux UID/AppArmor/nft 결과는 플랫폼별로 분리한다.

## 자료별 적용과 제한

### App Control for Business

Windows 10/11, Server 2016+에서 지원되며 모든 edition에서 정책이 유효하다. Home에는 PowerShell 관리 cmdlet이 없고 정책은 장치 전체 적용이다. 관리자 승인 실행 파일·스크립트 정책과 effective-state 확인이 후보이며, 코드 위치는 `endpoint-agent/managed-windows.py:319-331` 및 Gateway `integrations.py` Windows state mapping이다. App Control은 데이터·네트워크 sandbox나 antivirus 대체가 아니다. 잘못된 정책의 업무 영향, audit-to-enforce, 호환성, rollback이 필요하다. 실제 설치와 effective state 검증은 하지 않았다.

공식 자료: [App Control for Windows](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/appcontrol), [feature availability](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/feature-availability).

### AppLocker

Windows 10 v2004+ with KB5024351은 모든 edition에서 정책을 지원한다. 구버전/Server 2019에서는 GP와 MDM 지원 범위가 다르다. 사용자 규칙이 가능하지만 단독 강한 보안 경계로 보지 말라는 것이 Microsoft 안내다. companion 계정 정책 상태를 `managed_user()`, `install()`, `checks()`에서 보고할지 검토할 수 있다. `appidsvc`, script/EXE/DLL collection, audit/enforcement, DLL coverage/performance, rollback을 확인한다. 실제 적용은 미실행이다.

공식 자료: [AppLocker overview](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/applocker-overview), [rule collections](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/working-with-applocker-rules), [feature availability](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/feature-availability).

### Windows Firewall / WFP / loopback

`managed-windows.py:96-125`는 이미 account SID egress 규칙을 설정하고 `302-331`은 설치 baseline을 확인한다. 다음 구현 후보는 WFP 결과 증거 수집과 `endpoint-agent/README.md:65-75`, `docs/ai/DECISIONS.md:850-858`의 범위 명확화다. 실기기 시험은 일반 Win32와 UWP, 동일/다른 SID, gateway 허용 주소/포트와 거부 대상, IPv4/IPv6/mapped socket을 포함하고 WFP capture에서 appId/userId/filter와 allow/drop을 대조한다. `LocalUser`는 계정 기반이며 앱별 필터가 아니다. ALE 기능의 존재는 현재 키트가 ALE 규칙을 설정·감사한다는 뜻이 아니다.

공식 자료: [New-NetFirewallRule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule?view=windowsserver2025-ps), [WFP ALE](https://learn.microsoft.com/en-us/windows/win32/fwp/application-layer-enforcement--ale-), [UWP loopback troubleshooting](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/troubleshooting-uwp-firewall), [loopback fast path](https://learn.microsoft.com/en-us/windows/win32/winsock/sio-loopback-fast-path).

### Restricted token

`endpoint-agent/install-windows.ps1:37-43`는 scheduled task의 RunLevel을 제한하며 `managed-windows.py:345+`는 짧은 수명의 header를 중계한다. 어느 쪽도 사용자 MCP 프로세스에 `CreateRestrictedToken`을 적용하지 않는다. 미래 native launcher가 restricted SID/privilege로 자식 프로세스를 만들 수 있지만, workspace ACL과 함께 handle inheritance, UI desktop, child process, registry/device/network 접근, 실제 harness 호환성 및 fail-closed 복구를 확인해야 한다. Restricted token은 완전한 sandbox가 아니다. 격리 Windows VM에서만 prototype해야 한다.

공식 자료: [CreateRestrictedToken](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-createrestrictedtoken).

이번 단계는 공식 문서와 코드 위치만 조사했다. App Control/AppLocker 배포, 방화벽 변경, WFP capture, restricted token, 실제 Windows enforcement test는 수행하지 않았다.
