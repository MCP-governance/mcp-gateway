# 2026-10-17 windows-kit-wizard-tray

- 작업자: Codex
- 코드 기준: 시작 `0eb013b37864e27bcb041145c9b9cea928f03d8d`, 시작 작업 트리 clean. 최종 변경은 미커밋 작업 트리이며 파일별 SHA-256은 [원자 요구사항](../../analysis/windows-kit-wizard-tray/requirements.json)에 기록했다.
- 시작 근거: DEV-25·DEV-26, G08.04·G05.04, 사용자 결정 D-118(2026-10-17), 기존 D-68·권한 레퍼런스.
- 해결할 문제와 완료 조건: 별도 Python 설치 없는 Windows 마법사·트레이, 단계별 한국어 오류/재시도, 권한 분리, 안전한 제거와 report.log 경합 회귀. 구현/로컬 검사는 수행했으며 실제 VM 검수는 메인에게 인계한다.

## 결과

Windows ZIP 생성 경로는 `full_stack_lab/gateway/app/agent_service.py`의 기존 인증된 `/api/pc-kit`이다.
이미지 빌드 시 python.org 공식 amd64 embeddable 3.13.16을 SHA-256 고정으로 받도록 Dockerfile을 연결했고,
실행 중에는 캐시만 ZIP에 넣는다. 캐시가 없으면 503으로 실패하며 등록 토큰을 소비하지 않는다.
공식 릴리스의 SHA와 배포 조건은 [공식 근거 기록](../../analysis/windows-kit-wizard-tray/references.json)에 남겼다.
원래 ZIP과 `LICENSE.txt`를 보존하며 설치 시 `._pth`에는 표준 ZIP·런타임 폴더·키트 부모만 둔다.
`import site` 자동 실행은 끄고 `-I -S`로 실행한다. `runtime-check.py`는 실제 설치 전 AST에서 도출한 표준 모듈과 고정 판본·격리 플래그를 검사한다.

`install.cmd`는 비관리 권한으로 마법사를 연다. 시작 → TCP·health → 위치·관측 범위 → 진행률/단계 결과 → 완료 순서다.
관리형 등록/제거만 별도 UAC를 사용하며, 일반 계정·로그아웃·보호된 Python/프로그램 경계를 유지한다.
2026-10-18 검토 이후에는 조직이 별도 승인·배포한 보호 설치기/매니페스트가 필수다. 승격 작업자는 고정 승인 위치에서만 실행하며
사용자 폴더의 코드·ZIP·핀 JSON을 관리자 권한으로 읽어 실행하지 않는다. ZIP 자체 해시만으로 설치기 코드의 출처를 보증하던 전제는 폐기했다.
표준 사용자의 로그인 상태가 관리형 등록에 맞지 않으면 실패 단계·대상 계정·한국어 사유·재시도·로그 위치를 표시한다.
관리형 대상이 로그아웃 상태이므로 트레이는 그 계정의 다음 로그온에 실행된다. 관측 전용은 현재 사용자 설치·트레이 시작 경로를 사용한다.
새 GUI 라이브러리·새 Gateway API·자체 MCP 서버는 추가하지 않았다.

트레이는 기존 SYSTEM 서비스가 작성한 자격정보 없는 로컬 상태만 읽는다.
연결됨·연결 끊김·차단 발생, 상태 보기·최근 차단 5건·지금 점검·콘솔 열기·제거를 제공한다.
최근 차단은 기존 Windows 관측기가 정확한 SID에 귀속시킨 실제 이벤트에서 가져오며 세부 원문·키를 복제하지 않는다.
설정·상태·교체 파일은 Program Files 대신 `%ProgramData%\MCPGatewayManagedTray\<SID>`에 두며, 대상 SID 읽기·관리자/SYSTEM 쓰기 ACL을 사용한다.
연결 점검은 TCP·health와 보고 시각 확인이며 새 정책 승인이나 서비스 재시작을 뜻하지 않는다.

제거는 예약 작업 종료를 기다리고 키트 소유 파일 목록만 지운다. 설치 위치 안에 추가된 사용자 파일과 현재 Codex 관리 블록 밖 설정은 보존한다.
직원 PC 키트의 report 예약/실행/제거는 같은 잠금으로 직렬화했다. 자식이 잠금을 얻은 뒤 로그를 열어 WinError32 원인을 제거하고,
제거 뒤 늦게 실행된 report는 설정이 없으면 쓰지 않는다. 잠금 분리를 막는 `report.lock`과 진단 `setup.log`는 의도적으로 남긴다.

변경 파일:

- 설치/화면: `endpoint-agent/install.cmd`, `install-windows.ps1`, `setup.ps1`, `windows-worker.ps1`, `windows-common.ps1`, `windows-trust.ps1`, `tray.ps1`, `install.py`.
- 런타임/상태: `endpoint-agent/runtime-check.py`, `windows_status.py`, `agent.py`, `managed-windows.py`, `os-observer-windows.py`.
- 키트 생성: `full_stack_lab/gateway/Dockerfile`, `windows-python.json`, `prepare-windows-python.py`, `app/agent_service.py`.
- 경합/시험: `full_stack_lab/field/pc/mcpgw_pc.py`, `full_stack_lab/tests/field_kit_check.py`, `endpoint-agent/tests-windows/test_windows_kit.py`.
- 문서: `endpoint-agent/README.md`, `endpoint-agent/tests-windows/README.md`, `docs/ai/DECISIONS.md`(D-118),
  `research/llm-wiki/analysis/windows-kit-wizard-tray/{README.md,security-review.md,requirements.json,references.json,validation.json}`,
  `research/llm-wiki/status/backlog.md`, 본 보고서.

`status/current.md`는 사용자 지시대로 변경하지 않았다. 커밋·푸시·브랜치 변경·원격 기기 접속·compose 실행은 하지 않았다.
원격 HEAD read-only 조회는 네트워크 차단으로 실패해 갱신하지 못했다.

## 검증

명령별 실제 exit code·stdout/stderr는 [validation.json](../../analysis/windows-kit-wizard-tray/validation.json)에 있다.
실제 Windows 설치·GUI·MCP 실행 증거로 확대하지 않는다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | Windows Python3.10, `python -X utf8 -m compileall -q endpoint-agent full_stack_lab/field/pc/mcpgw_pc.py full_stack_lab/gateway/prepare-windows-python.py full_stack_lab/gateway/app/agent_service.py full_stack_lab/tests/field_kit_check.py` | exit 0 | validation.json checks |
| 새 키트 단위 | `python -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -v` | 11/11, exit 0 | validation.json checks |
| PowerShell 정적 | 위 단위 시험이 PS1 6개를 `Parser::ParseFile`로 검사; UTF-8 BOM·인자/URL 경계·시험 디렉터리 제거 목록도 확인 | 통과, 실제 설치/GUI 실행 없음 | test_powershell_scripts_parse_and_input_boundaries_fail_without_host_changes |
| 기존 수집기 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p endpoint_collector_check.py -v` | 8/8, exit 0 | validation.json checks |
| 기존 Windows 관측기 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p windows_os_observer_check.py -v` | 7/7, exit 0 | validation.json checks |
| 관리형 self-check | `python -X utf8 endpoint-agent/managed-windows.py self-check` | exit 0 | validation.json checks |
| diff | `git diff --check` | exit 0 | validation.json checks |
| 무인증 API 정적 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | exit 0, 무인증 1·인증 필요 70개 문서 일치 | validation.json checks |
| pyflakes | `python -X utf8 -m pyflakes` + 변경 Python 파일 | 미설치 오류, 검사 미수행 | validation.json earlier_attempts |
| 기존 직원 키트 전체 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p field_kit_check.py -v` | import 실패: Python3.10에 tomllib 없음 | validation.json earlier_attempts |
| Linux/Windows 공용 집행 시험 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p managed_enforcement_check.py -v` | 10개 setUp 오류: Windows에 grp 없음 | validation.json earlier_attempts |
| 관측기 self-check | `python -X utf8 endpoint-agent/agent.py --self-check` | tomllib import 실패 | validation.json earlier_attempts |
| 실제 ZIP 확보 | `python -X utf8 full_stack_lab/gateway/prepare-windows-python.py full_stack_lab/gateway/windows-python.json .task-local-windows-kit/runtime` | WinError10013, 외부 소켓 차단 | validation.json earlier_attempts |
| 위키 전체 | `python -X utf8 research/llm-wiki/tools/check_wiki.py` | 실패: 기존 local-sources 원문 provenance 29개 누락, 변경 코드 3개의 기존 매핑 hash 갱신 필요 | validation.json wiki_check |
| 프로토콜 | 실제 MCP·새 API 시험 | 미실행 | pj3 절차 |
| 실제 모델·하네스 | PJ1/pj3 | 미실행 | pj3 절차 |
| upstream 효과 | 실제 MCP/OS 차단 | 미확인 | pj3 절차 |
| 배포·정책 해시 | 솔루션 이미지 빌드/field up | 미실행 | pj3 절차 |

## 실패·미완료·한계

- 실제 Python ZIP을 받지 못했으므로 포함 인터프리터·`._pth`·표준 모듈이 작동한다고 확인한 상태가 아니다. 설치 전 점검 코드는 준비했고 메인이 실제 ZIP에서 실행해야 한다.
- 실제 GUI·DPI·UAC·표준 계정 예약 작업 ACL·Task Scheduler의 자식 프로세스 종료·차단 아이콘/알림·제거/재설치는 미실행이다.
- 기존 관리형 계정은 로그아웃을 요구한다. 표준 사용자가 자기 열린 세션을 유지한 채 설치를 완결하는 경로를 추가하지 않았다.
  관리자 계정의 별도 일반 계정 생성·프로필 준비도 기존 요건이며, 실패 시 해당 계정과 원인을 표시한다.
- 설치 도중 등록 토큰이 소비됐다면 새 키트가 필요하다. 실행 중인 관리형 키트는 덮어쓰지 않고 기존 제거 후 재설치한다.
- Windows loopback·실행/파일 정책 범위는 DEV-25의 별도 검수이며 이번 GUI 구현으로 해결됐다고 표시하지 않는다.
- 전체 기존 회귀와 pyflakes는 적합한 Python3.11+·Linux 검사 환경에서 재수행해야 한다. 코드 증거 매핑 hash 갱신과 로컬 원문 누락은 메인이 통합한다.
- 최초 PS1 구문 검사에서 PowerShell5.1이 BOM 없는 한글을 ANSI로 읽는 문제가 나타나 UTF-8 BOM으로 고쳤고, BOM 회귀 검사를 남겼다.

### 2026-10-18 검토의 정정·한계

- 앞 구현의 UAC 원본 교체 위험을 인정하고 경로를 교체했다. 새 `windows-trust.ps1`은 조직이 승인·배포하는 신뢰 근거의 일부이며,
  사용자 ZIP이 자기 스크립트를 승인하거나 최초 bootstrap으로 승격하는 경로는 없다. 승인물 자체는 이번 노트북에 배포하지 않았다.
- 기존 인증된 키트 응답은 코드/런타임 전체 매니페스트와 헤더 SHA-256을 제공한다. 새 라우트는 없으며 출처 신뢰는 관리자 별도 승인으로 확립한다.
  관리자/SYSTEM 이외 쓰기·상위 경로 교체 권한·reparse·추가 파일·해시 불일치는 거부한다. 설치 목적지의 코드/런타임도 실행 전 검사한다.
- 요청 JSON은 프로필 범위를 열기 전에 제한하고 실제 열린 파일 경로·크기를 확인한다. 등록 자격은 보호된 데이터 사본으로만 전달하고,
  게이트웨이/노드 ID는 별도 승인물에서 고정한다. 파싱 실패에 자격 본문을 출력하지 않는다. 요청 SID는 로컬 파일 범위이며 Gateway 신원을 대체하지 않는다.
- 승격 프로세스의 환경/작업/임시 경로를 제한했고, 승격 명령의 `ExecutionPolicy Bypass`를 제거했다. 조직 서명/실행 정책을 우회해 설치하지 않는다.
- `test_doctor_and_uninstall_against_the_fake`는 `report.lock` 하나만 남고 빈 파일이어야 하는 조건으로 정정했다.
  이 기존 전체 시험은 tomllib/네트워크 제약으로 재실행하지 못했다. 별도의 순수 Windows 로컬 파일/잠금 시험으로 정확한 잔여 파일·지연 보고를 확인했다.
- 변조·ACL·데이터 사본 시험은 총 11개 키트 단위에 포함된다. ACL 조회/생성의 일부는 대역이며 실제 다른 표준 계정의 읽기 거부나 UAC 통과 증거가 아니다.
- Linux `install.sh`→직원 폴더 `bootstrap.py`의 최초 sudo 출처 문제는 [잔여 위험](../../analysis/windows-kit-wizard-tray/security-review.md)에 별도로 남겼다.
  Linux 파일은 변경하지 않았고 해결됐다고 표시하지 않는다.

## 다음 작업

메인은 [pj3 절차](../../../../endpoint-agent/tests-windows/README.md)에 따라 다음을 확인한다.

1. 신뢰되는 조직 경로에서 최초 승인 설치기와 별도 매니페스트를 배포한 뒤, 솔루션 기기에서 이미지 빌드·SHA 검증 → Windows 키트 생성 → 실제 포함 Python 점검과 라이선스 확인.
2. pj3 관리 계정/별도 일반 계정, pj3user 표준 계정에서 시작·연결·범위·UAC 취소/승인·실패/재시도·설치를 확인한다.
3. 대상 계정 로그온 트레이, 정상/연결 끊김/정확한 SID의 실제 차단 5건·알림·메뉴·DPI를 확인한다.
4. 자격 폐기 → 트레이/마법사 제거 → 프로세스/예약 작업/설정/임시 파일 제거와 사용자 파일 보존 → 새 키트 재설치를 확인한다.
5. 실제 background report 중 제거와 지연 report의 설정 재생성 회귀, 180초 이상 뒤 재생성 없음, 세션1 예약 작업 캡처를 남긴다.
6. 다른 표준 계정의 개인 트레이 JSON/임시 파일/작업 결과 읽기 거부, 실행 전 원본/목적지 변조 거부, 서명 정책·상위 경로 교체·reparse 경쟁을 확인한다.
7. Python3.11+ 기존 전체 키트 회귀·pyflakes, 변경 코드 매핑·위키 전체 검사 후 통합한다. Linux 최초 설치 출처는 별도 후속으로 유지한다.

## 사용자에게 필요한 입력

추가 설계 결정 없음. 메인에게 실제 빌드 가능한 솔루션 기기·pj3 콘솔 세션1·pj3/pj3user·새 등록 키트·기존 승인 하네스·시험 소유 장치의 활성화/폐기 권한이 필요하다.
조직이 별도로 승인한 설치기 배포물·매니페스트가 필요하며, ZIP 안의 값만으로 그 승인을 대신하지 않는다.
자격증명 값은 저장하거나 요청하지 않았다.
