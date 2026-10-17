# Windows 키트 검수 — pj3

이 절차는 메인이 격리 pj3 VM에서 수행한다. 이번 작업에서는 원격 접속·설치·GUI 실행·실기기 캡처를 수행하지 않았다.
단위 시험의 합성 이벤트·대역은 실제 MCP 또는 운영체제 집행 증거가 아니다.

사설 CA 배치에서는 운영자가 확인한 루트·지문을 먼저 전달한다. 키트/매니페스트를 받는 HTTPS 클라이언트도
같은 루트를 요청 범위로 지정한다(예: `curl --cacert root.crt`). 승인 매니페스트의 `files`에는
`root.crt`·`root.sha256`·`mcpgw_pc.py`가 포함되어야 하며, 기존 승인 매니페스트를 새 발급 목록으로 갱신한다.
PowerShell의 연결 검사는 요청별 CA 체인·이름·만료 검증을 사용하고 TLS 1.2로 연결한다.
관리 계정의 하네스는 `MCPGatewayManaged\launchers\<SID>\claude.cmd`·`codex.cmd`로 실행한다.
시스템 인증서 저장소와 계정의 CA 환경값은 설치 전후 같아야 한다.

## 준비

- 메인이 솔루션 기기에서 게이트웨이 이미지를 빌드·배포한다. 빌드 시 python.org에서 고정 ZIP을 받고 SHA-256을 검증한다.
- 관리자 `pj3`, 표준 사용자 `pj3user`의 프로필을 각각 만들고, 승인된 native 하네스와 같은 릴리스의 동반 실행파일을 준비한다.
- 새 Windows 키트를 콘솔에서 발급한다. 등록 토큰은 30분·1회용이다. 실패 후 소비된 토큰을 재사용하지 않는다.
- 설치 전 VM 스냅샷, 계정/SID, 프로그램·예약 작업·방화벽·하네스 설정의 기존 상태를 기록한다. 다른 설치나 다른 계정의 작업을 중지하지 않는다.
- `%ProgramFiles%\MCPGatewayManaged`에는 기존 관리형 키트가 없어야 한다. 기존 설치는 자격 폐기 후 제거한다.
- GUI 화면은 Windows 콘솔 세션 **1**에서 확인한다. SSH의 세션 0 화면은 증거로 세지 않는다.
- 키트의 `python.zip`, `windows-python.json`, 설치 PS1 전부와 `runtime-check.py`가 있는지 확인한다.

## 조직 IT의 최초 승인 배포

마법사가 다운로드 ZIP을 처음 보고 스스로 승인/승격하는 경로는 없다. 이 준비를 하지 않으면 관리형 설치는 중단되는 것이 기대값이다.

1. 신뢰되는 조직 릴리스/배포 경로에서 설치기 코드 자체를 검토·승인한다. 직원이 수정할 수 있는 스크립트를 관리자 bootstrap으로 실행하지 않는다.
   조직 배포 도구/관리 콘솔이 설치기를 미리 배포하며, 직원에게는 그 보호 위치를 가리키는 실행 진입점을 제공한다.
2. 기존 인증된 `POST /api/pc-kit?platform=windows` 응답의 `windows-kit-manifest.json`과
   `X-Windows-Kit-Manifest-SHA256`을 신뢰되는 인증 세션/릴리스 승인에서 별도로 확정한다.
   같은 다운로드 폴더에서 재계산한 해시나 ZIP 안의 값만으로 승인하지 않는다. 원본 서버·TLS 또는 고정된 조직 전송 경로를 확인한다.
3. 매니페스트의 `files`에 명시된 코드·`python.zip`·`windows-python.json`만 `%ProgramFiles%\MCPGatewayInstaller`에 배포한다.
   직원별 `enrollment.json`은 이 공용 승인 코드 폴더에 넣지 않는다. 매니페스트 파일은 별도 승인 후
   `%ProgramData%\MCPGatewayInstaller\approved-windows-kit.json`에 둔다. 이 승인 JSON에는 키/토큰/직원 SID가 없다.
4. 두 루트와 승인 파일의 소유자는 Administrators 또는 SYSTEM, 쓰기는 그 두 주체만 허용한다. 코드와 공용 승인 메타데이터는 일반 사용자가 읽을 수 있다.
   상속·기존 명시적 쓰기 ACE를 그대로 두지 않고 정확한 ACL로 교체한다. 부모/루트/파일의 reparse point는 허용하지 않는다.
   코드 폴더에 추가 실행 파일·하위 폴더를 넣지 않는다. 보호된 위치에서 각 파일 해시를 승인 JSON과 다시 대조한다.
5. 조직의 PowerShell 서명/실행 정책을 배포 과정에서 충족한다. 승격 경로는 실행 정책 Bypass를 사용하지 않는다.
   서명이 필요한 조직이면 서명된 최종 바이트를 기준으로 매니페스트를 발행한다. ZIP에서 가져온 인증서/처음 본 게시자를 자동 신뢰하지 않는다.
6. 승인물을 삭제한 상태, helper/ZIP/핀 JSON 한 바이트 변경, 추가 `powershell.exe`, 사용자 쓰기 ACE, junction 경로를 각각 시험한다.
   어느 경우에도 사용자 원본을 관리자 권한으로 대신 실행하거나 승인 파일을 자동 생성하면 안 된다.

위 배포·승인물은 이번 작업에서 실제 PC에 설치하지 않았다. 메인이 pj3의 격리 승인 배포 경로로 준비하고, 사용한 승인 해시를 시험 증거에 기록한다.

## 관리자 계정 pj3

1. `pj3user`를 로그아웃하고 pj3 콘솔에서 `install.cmd`를 연다. 시작 화면이 보이고 아직 UAC가 없어야 한다.
2. 대상 계정 `pj3user`를 입력한다. 시작 → 게이트웨이 연결 확인(TCP와 `/api/health`) → 설치 위치·관측 범위 확인 순서를 캡처한다.
3. 설치를 누를 때만 UAC가 나타나야 한다. 승인 후 실행 파일 준비·점검·관리자 등록·로그온 시작 등록·완료 결과와 로그 경로를 캡처한다.
4. 별도 Python 설치가 없는 VM에서 `%ProgramFiles%\MCPGatewayManaged\python\python.exe -X utf8 -I -S ...\runtime-check.py`를 실행한다.
   JSON의 모듈 목록과 `site_automatic:false`, 실제 3.13.16, `pythonw.exe` 존재를 기록한다. `._pth`의 `#import site`, `..` 경로와 포함 `LICENSE.txt`를 확인한다.
5. SYSTEM 서비스 작업의 실행 파일이 포함 `pythonw.exe`이고, `-I -S`·보호된 설정 경로를 쓰는지 확인한다. 프로그램과 Python의 소유자는 Administrators,
   쓰기는 SYSTEM·Administrators만, 사용자 읽기만 허용돼야 한다. 장치 키는 ProgramData의 보호된 파일에만 있어야 한다.
6. pj3user로 로그온한다. 트레이 작업은 해당 SID의 Interactive/Limited, 로그온 트리거, 한 인스턴스여야 한다.
   새 서비스 보고 후 `연결됨`, 관리 상태 `등록 대기`를 확인한다. 메인이 기존 콘솔 절차로 활성화하고 관리 상태 `활성`을 확인한다.
7. 관리자 자신의 계정 pj3를 대상으로 하는 분기도 별도 VM 스냅샷에서 시험한다. `mcpgw-pj3` 프로필이 없으면
   `대상 계정 첫 로그인 후 로그아웃 필요`와 실제 계정 이름을 표시해야 한다. 계정 첫 로그인·암호 설정·로그아웃 후 새 키트로 재시도한다.

## 표준 계정 pj3user

1. 아직 관리되지 않는 초기 VM에서 `pj3user`로 마법사를 열고 연결·위치·범위 확인까지 UAC 없이 진행한다.
2. 관리형 설치에서 UAC를 취소한다. `관리자 권한 승인 취소`, 다시 시도 버튼을 확인한다.
3. 다시 시도에서 pj3 자격으로 UAC를 승인한다. 현재 pj3user 세션이 열려 있으면 `대상 계정 로그아웃 필요`로 실패해야 한다.
   해당 경계를 완화하지 않는다. pj3user 로그아웃 후 pj3 세션에서 그 계정을 대상으로 설치를 완료한다.
4. 관측 전용 별도 검수는 발급된 장치 키 파일과 제한된 합성 관측 디렉터리를 지정해 `install-windows.ps1`을 연다.
   `%LOCALAPPDATA%` 아래 공백·한글 포함 설치 위치, 관측 범위, 장치 키 파일 선택을 확인한다. 표준 권한으로 1회 보고·예약 작업·트레이까지 완료하거나,
   조직의 예약 작업 ACL이 거부하면 `파일 접근 또는 예약 작업 권한 확인 필요`와 실패 단계가 보여야 한다. 관리형 등록 성공으로 세지 않는다.

## 트레이·차단·실패·복구

| 조건 | 확인 화면·기대값 |
| --- | --- |
| 새 보고 | 정보 아이콘·연결됨. 상태 보기의 게이트웨이·최근 보고·관리 상태가 한국어이며 값이 없으면 `—` |
| 서비스/게이트웨이 연결 실패 | 새 실패 보고 또는 최종 보고 150초 초과 뒤 연결 끊김. 단순 TCP 성공으로 에이전트 상태를 연결됨으로 덮지 않음 |
| 실제 차단 관측 | 격리 VM의 승인된 감사 설정에서 정확한 관리 SID의 실제 WFP/AppLocker 차단을 발생시킴. 차단 발생 아이콘·알림·최근 차단 최대 5건 |
| SID 없음·다른 계정·감사 비활성 | 실제 차단 목록에 추가하지 않음. 수집기의 partial/disabled를 성공으로 세지 않음 |
| 차단 표시 경과 | 최근 5분 뒤 새 보고가 있으면 연결됨, 최근 차단 목록에는 기록 유지 |
| 지금 점검 | UI가 응답하며 TCP·`/api/health` 결과를 표시. 정책 승인·서비스 재시작이 발생하지 않음 |
| 콘솔 열기 | 키트의 게이트웨이 주소가 기본 브라우저에서 열림. 장치 키·토큰이 URL에 없음 |
| 연결 실패 분기 | DNS/포트 실패, TCP 시간 초과, 신뢰되지 않는 HTTPS 인증서, health 비정상, HTTP redirect에서 한국어 실패 단계·재시도·로그 위치 |
| 변조 ZIP | `python.zip` 한 바이트 변경 시 실행 파일 무결성 확인 실패. 임의 Python으로 대체 실행하지 않음 |
| 승인 코드/ZIP 동반 교체 | ZIP 옆 매니페스트도 공격자가 다시 계산한 경우까지 거부. UAC 대상은 고정 승인 위치이며 다운로드 원본을 읽어 실행하지 않음 |
| 승인물 없음 | 조직 승인 설치기·무결성·실행 권한 확인 필요. 최초 관찰 자동 승인·사용자 원본 fallback 없음 |
| 중복 설치 | 동시에 두 설치 시 둘 중 하나는 다른 설치 작업 진행 중. 실행 중 관리형 설치 위에 덮어쓰지 않음 |
| 고DPI | 100/150/200%, 한글·공백 경로, 작은 해상도에서 라벨·값·진행률·결과·닫기/재시도 버튼이 잘리지 않음 |

차단 재현은 기존 상용/OSS MCP와 운영체제의 실제 감사 이벤트를 사용한다. 새 mock MCP 서버를 만들지 않는다.
감사 설정·방화벽을 시험이 변경했으면 원래 값으로 복구하고, 공급자 효과·실제 MCP 판정은 로컬 트레이 표시와 별도로 기록한다.

## 제거 → 재설치 (두 계정 경로 모두)

1. 시험 소유 장치만 콘솔에서 자격 폐기한다. 설치 위치와 하네스 설정에 사용자 합성 파일·사용자 설정 키를 추가해 hash를 기록한다.
2. 트레이 **제거**를 누른다. 마법사 제거 확인 → 관리형이면 UAC → 엔드포인트 종료 → 설정 제거 → 제거 완료를 캡처한다.
3. 예약 작업·해당 프로세스·트레이가 사라지고, 키트 설정·포함 Python·키트 임시 파일이 제거됐는지 확인한다. 사용자가 추가한 파일·Codex의 관리 블록 밖 설정은 보존돼야 한다.
   `%ProgramData%\MCPGatewayManagedTray\<SID>`의 개인 파일만 제거하고 다른 SID의 상태는 보존한다. 조직 공용 승인 설치기/매니페스트는 직원 제거가 지우지 않는다.
4. `setup.log`는 표시된 진단 로그 위치에 남는다. 로그에 장치 키·enrollment/직원 토큰·비밀번호·원본 subprocess 응답이 없는지 안전한 검사로 확인한다(값은 보고서에 복사하지 않음).
5. DEV-26은 별도 임시 `MCPGW_HOME`·`CODEX_HOME`에서 직원 PC 키트의 보고와 제거를 겹쳐 재현한다. 실제 report가 `report.log`를 연 상태에서 제거는 기다려야 하고,
   보고 종료 뒤 WinError32 없이 제거돼야 한다. 뒤늦게 실행한 `report --background`는 설정·로그를 재생성하면 안 된다.
   `report.lock` 한 파일은 대기 프로세스의 잠금 분리를 막기 위해 유지한다. 사용자 파일은 보존한다.
6. 180초 이상 기다려 서비스·보고·설정·트레이가 다시 생기지 않는지 확인한다. 새 키트로 설치 → 활성화 → 트레이 → 실제 차단 → 제거를 다시 수행한다.
7. 중간 실패(프로필 없음·하네스 없음·등록 토큰 만료·보고 실패) 후에도 단계가 보이고, 필요한 원복·새 키트 발급 후 재시도가 가능한지 확인한다.

## 다중 사용자 읽기 경계

관리형 설치 후 대상 SID 계정에서 개인 `settings.json`·`status.json`을 읽고, 다른 표준 계정에서는 같은 파일을 직접 열어 접근 거부를 확인한다.
SYSTEM/관리자만 상태·교체용 `.tmp` 파일을 쓸 수 있어야 한다. 단순히 상위 경로가 안 보이는 것과 파일 자체 읽기 거부를 구분한다.
상태 갱신을 반복하는 동안 `.tmp`와 교체 뒤 JSON의 ACL도 확인한다. Program Files에는 사용자명·SID·endpoint_id·차단 내역이 담긴 개인 JSON이 없어야 한다.
승격 결과 폴더도 해당 요청자만 읽고 다른 표준 계정은 읽지 못해야 한다. 실제 계정 접근 검수는 단위 ACL 기술자 검사와 별도 증거로 남긴다.

## 세션 1 화면 캡처 예약 작업

메인이 VM 콘솔에서 현재 화면을 연 계정으로 실행할 캡처 스크립트를 VM의 시험 전용 디렉터리에 둔다. 예:

```powershell
if ((Get-Process -Id $PID).SessionId -ne 1) { throw '콘솔 세션 1 필요' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($bounds.Location, [Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save('C:\kit-test\capture.png', [Drawing.Imaging.ImageFormat]::Png)
} finally { $graphics.Dispose(); $bitmap.Dispose() }
```

작업은 콘솔 세션 1의 실제 로그인 계정(`pj3` 또는 `pj3user`)을 UserId로 지정하고 `LogonType Interactive`·`RunLevel Limited`로 등록한다.
실행 파일은 Windows PowerShell 5.1, 인자는 `-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\kit-test\capture.ps1`이다.
`Start-ScheduledTask`로 실행하고 `LastTaskResult=0`, PNG 생성 시각·크기·내용을 확인한다. 세션 번호 검사가 실패하면 캡처 성공으로 세지 않는다.
시험이 만든 캡처 작업만 제거한다. UAC 보안 데스크톱은 일반 캡처에 보이지 않을 수 있으므로 승인/취소 결과와 실제 보안 프롬프트 확인을 구분한다.

## 로컬 단위 시험

```powershell
python -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -v
python -X utf8 -m unittest discover -s full_stack_lab/tests -p windows_os_observer_check.py -v
```

검사 결과·미실행 항목은 [작업 보고](../../research/llm-wiki/status/reports/2026-10-17-windows-kit-wizard-tray.md)에 기록한다.
