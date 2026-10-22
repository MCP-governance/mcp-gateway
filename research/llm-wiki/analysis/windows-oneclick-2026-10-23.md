# Windows 원클릭 설치의 신뢰·계정 경계

기준: `48bb19ec52de0e1e2198d19e75b1f62e7aab2014` + `10/23-windows-oneclick` 미커밋 변경. D-197.
실행 결과는 [작업 보고](../status/reports/2026-10-23-windows-oneclick.md)가 정본이며 실제 Windows 설치는 미실행이다.

## 기존 IT 선행 배포가 필요했던 이유

`endpoint-agent/windows-worker.ps1:42`는 관리자 프로세스일 때 `%ProgramFiles%\MCPGatewayInstaller` 외 경로를 거부한다.
`Assert-EndpointBootstrapSeed`는 helper를 읽기 전에 코드·상태·승인 JSON·상위 경로의 소유자/쓰기 권한/연결 파일과 helper 해시를 확인한다.
`windows-trust.ps1:125`의 `Get-EndpointApprovedKit`는 ZIP 안의 매니페스트 대신 보호된
`%ProgramData%\MCPGatewayInstaller\approved-windows-kit.json`의 정확한 파일 목록과 SHA-256을 권위로 사용한다.
다운로드 폴더는 직원이 쓸 수 있으므로 그 폴더의 코드·매니페스트가 관리자 실행의 신뢰 근거가 될 수 없었다.
기존 `setup.ps1`은 이 저장소가 존재하는지 확인할 뿐 최초 신뢰를 만드는 기능이 없었다.

코드의 서명 검증과 해시 검증은 구분한다. 이 기준판의 worker/trust에 `Get-AuthenticodeSignature`나 발행자 공개키 검증은 없다.
Python 배포본은 `windows-python.json`과 아카이브 SHA-256으로 고정한다. D-71도 하네스 복사본의 해시만 고정하고 공급자 서명 검증은 하지 않는다고 명시한다.
따라서 기존 최초 배포의 출처 신뢰는 조직 IT의 별도 배포 경로에 있었다. TLS 루트는 코드 서명용 신뢰 저장소가 아니며 시스템 인증서 저장소를 수정하지 않는다.

## 변경된 최초 신뢰와 유지한 통제

새 `.cmd`의 최초 신뢰 주체는 인증된 콘솔에서 받은 전체 파일을 실행하고 UAC로 승인한 관리자다.
일반 권한 loader는 경로·파일 SHA-256·직원 SID/계정만 승격 명령에 넣는다. 등록 자격은 파일 payload 안에만 있고 환경 변수나 명령행으로 전달하지 않는다.
승격 seed는 원본 파일을 쓰기/삭제 공유 없이 열고 SHA-256을 재검사한 같은 바이트에서 bootstrap과 ZIP을 읽는다.
bootstrap은 정확한 파일 목록과 각 파일 해시를 검증한 후 메모리의 검증된 helper를 읽는다. helper의 기존 BOM은 문자열로 실행할 때만 제거하고 원본/해시는 보존한다.
코드·승인 저장소는 관리자 소유, SYSTEM/Administrators 쓰기, Users 읽기로 생성한다. 기존 경로 ACL은 변경하지 않고 검증한다.
기존 승인 JSON이 있으면 주소·노드·모든 해시가 일치해야 한다. 손상/다른 승인판을 자동 덮어쓰기하지 않는다.
보호된 기존 worker의 seed/ACL/해시·포함 Python 검증을 다시 거쳐 등록한다. 등록 완료와 조직 활성화는 별개다.

SHA-256은 실행 중 교체를 검사하며 발행자 서명을 대신하지 않는다. 서명 키를 임의 생성하거나 신뢰 저장소에 등록하지 않는다.
관리자에게 적용된 `AllSigned`이면 새 경로는 파일/계정 변경 전에 중단한다. worker의 `RemoteSigned`는 해당 자식 프로세스에만 적용되며 시스템/그룹 정책은 변경하지 않는다.
출처 자체가 바뀐 설치 파일, SmartScreen/앱 제어/서명 요구 환경에서의 배포 적합성은 이 오프라인 검증으로 입증하지 않았다.

## 원자 요구사항과 증거

| ID | 요구·조건 | 코드 심볼/행 | 새 시험·결과 | 남은 검증 |
| --- | --- | --- | --- | --- |
| W11-R1 | 파일 하나/UAC 한 번, ZIP 유지 | `windows_oneclick.py:5 launcher`, `agent_service.py:433 download_managed_kit`, `console.js:2670 pc-kit-download` | CMD 길이 8191 미만·payload roundtrip·mock UAC 1회·ZIP 기본 응답 통과 | 실제 파일 다운로드·UAC 1회 |
| W11-R2 | 해시·경로 권한과 외부 승인 유지 | `windows-oneclick.ps1.in:15 Read-EndpointOneclickArchive`, 기존 `windows-trust.ps1:31,125`, `windows-worker.ps1:42` | 유효 ZIP·BOM helper 로드 통과, worker/ZIP 변조·경로 이탈·추가 파일 거부 통과; 기존 승인 대체 시험 그대로 통과 | 실제 보호 경로 ACL·기존 IT 승인판 공존 |
| W11-R3 | 직원 로그아웃 없이 등록 | `managed-windows.py:497 managed_user`, `:516 prepare_profile`, `:564 install`; worker의 `isolated_account` | 표준 직원→별도 표준 계정·관리자 동반 계정 거부·프로필 생성/실패/재사용·직원 하네스 원본 선택 통과 | Windows CreateProfile·레지스트리 hive 로드 |
| W11-R4 | 기존 세션·신원·보호 설정 통제 유지 | `managed-windows.py:583 OWNED_PROCESSES`, 기존 `firewall_rules`, `apply_policy`, `serve_pipe`; worker의 SYSTEM 작업 | 관리 계정에 프로세스가 있으면 등록 호출 전에 거부, 임시 설정의 SID는 동반 계정임을 확인; 기존16 시험 통과 | 실제 SID 방화벽·파이프·활성화·정책 보고 |
| W11-R5 | 모델 로그인 안내와 비밀 경계 | `windows-worker.ps1:282 Set-EndpointResult`, `managed-windows.py install` | Claude/Codex 명령 출력·device_key 출력 부재 확인 | 관리 계정에서 공식 로그인·모델 사용 |
| W11-R6 | 실패/경쟁/복구 구분 | bootstrap mutex·기존 worker mutex·기존 승인 비교·`prepare_profile` HRESULT 확인 | missing template는 enrollment 미발급, 프로필 실패·라이브 관리 계정 거부 통과 | 실제 동시 UAC/복구는 미실행. 부분 보호 설치물은 IT 확인을 요구하며 자동 덮어쓰기 없음 |

직원 계정의 실행 중 프로세스 검사를 삭제한 것이 아니다. 새 경로가 별도 관리 계정을 준비하므로 설치 시 직원 로그아웃이 필요하지 않다.
관리 계정 사용을 위한 이후 로그인은 D-71의 계정 분리 경계다. 설치 마무리는 이미 완료되고, 기존 제한 권한의 로그온 트레이 예약 작업이 다음 로그인에 시작한다.
새 SYSTEM 예약 마무리 작업에 등록 자격이나 비밀번호를 보관하는 설계는 추가하지 않았다.

## 공개 스킬·OSS와 공식 API 비교 (10-23 열람)

| 자료 | 판본·라이선스·유지보수 확인 | 적용 범위/한계 |
| --- | --- | --- |
| [Microsoft winapp-package 공개 스킬](https://github.com/microsoft/winappCli/blob/main/plugins/winapp/skills/winapp-package/SKILL.md), [라이선스](https://github.com/microsoft/winappCli/blob/main/LICENSE) | main 문서·MIT. MSIX manifest/인증서/패키징 도구 전제 확인. 최신 commit 고정은 네트워크/API 제약으로 미확인 | 탐색·설계 비교만. 새 MSIX 도구/서명 자격을 추가하지 않았고 외부 스크립트 실행/스킬 설치 없음 |
| [Microsoft winget-cli](https://github.com/microsoft/winget-cli/releases/tag/v1.29.380), [라이선스](https://github.com/microsoft/winget-cli/blob/v1.29.380/LICENSE) | 릴리스 `v1.29.380`, 릴리스 페이지 commit `000f6b5`, MIT. 9-21 servicing 릴리스 확인 | UAC 집계 방식 비교. 실행/코드 재사용/새 의존성 없음. 전체 commit SHA/API 확보 실패를 짧은 SHA 이상의 검증으로 세지 않음 |
| [CreateProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createprofile) | Microsoft Win32 문서 본문·관리자 요구/HRESULT 확인. OS 제공 Userenv.dll | 기존 Python ctypes로 호출. 비밀번호/로그인 토큰 불필요. 실제 OS 호출은 미실행 |
| [Claude CLI reference](https://code.claude.com/docs/en/cli-reference), 기존 `bootstrap.py:376 LOGINS` | 공식 `claude auth login` 확인. Codex 명령은 저장소 Linux bootstrap의 `codex login --device-auth` 재사용 | 안내만 추가. 공급자 자격/기존 로그인 파일을 읽거나 복사하지 않음 |

외부 원문은 재배포하지 않았고 명령을 실행하지 않았다. 버전 고정되지 않은 공개 스킬은 구현 근거의 한계로 표시했다.
