# 2026-10-26 Windows 키트 화면·진단 수정

- 작업자: Codex
- 코드 기준: `b9274e38e9713852954bdd27b53c0112dd2bfe78`, 시작 시 깨끗함. `10/26-windows-tray-ux`, PR #59 수정 포함.
- 시작 근거: 소유자 요청 P2-7·P3-8, DEV-84·DEV-89, D-255.
- 완료 조건: 상태값 번역·대기 진단 재확인·부분 관측의 진단 소음 제거, 오프라인 회귀 검사, 로컬 커밋. 배포·push·PR 제외.

## 결과

- `windows-common.ps1`·`tray.ps1`: 상태 enum 대신 현재 언어의 값 표시, 저장된 게이트웨이 정상 결과·하네스 없음·건너뜀 재번역. 터미널 메뉴도 번역하고 선택 언어를 넘긴다.
- `windows_status.py`·`kit_screen.py`: 영문 라벨·상태·단위. 서버 ID·이름과 하네스 판본은 그대로 유지.
- `tray.ps1:Update-EndpointTray`: active인데 cached probe의 connection.waiting이 남으면 비우고 기존 자동 점검을 시작. pending·제거·중복 점검 방지는 유지. PR #59의 probe 파일 삭제와 상태 창 자동 열기도 유지.
- `agent.py:main`: partial 종료 코드는 0, 실제 실패·인가 실패는 1. `once`의 partial/incomplete_snapshot 보고는 유지. `managed-windows.py:serve.observe`는 관측 결과를 읽어 service.log에 partial로 기록하고 자식 실패·시간 초과·잘못된 출력은 계속 오류로 기록한다.
- 표시 이름 조사: `endpoint_plane.managed_policy`의 servers는 ID 목록이고 `local_jobs.device_manifests`의 응답·서명 manifest에는 표시 이름 필드가 없다. `pac.harness_guidance`의 display_name은 정제·길이 제한한 하네스용 Markdown 문장으로만 정책 파일에 들어간다. 이를 역파싱하지 않고 소유자 지정 대안대로 ID를 유지했다. 이름을 추측하거나 게이트웨이 계약·해시를 바꾸지 않았다.

## 검증

Windows / Python 3.10.5 / Windows PowerShell, 2026-10-26. 임시 프로필·임시 ACL·대역을 사용한 오프라인 시험이다.

| 확인 종류 | 명령·환경 | 결과 |
| --- | --- | --- |
| Windows 전체 | `python -X utf8 -m unittest discover -s endpoint-agent/tests-windows` | 39건: 38 통과, 기존 tomllib 시험 1 생략(Python 3.11+ 필요) |
| Windows 로컬 검사 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p 'windows_*_check.py'` | 26건: 25 통과, 기존 Pydantic 2 시험 1 생략(패키지 미설치) |
| 터미널 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p kit_screen_check.py` | 15 통과 |
| 관측기 | `python -X utf8 -m unittest discover -s full_stack_lab/tests -p endpoint_collector_check.py` | 9 통과 |
| 구문·인코딩 | 변경 Python 8개 compile/ast.parse, PowerShell 2개 Parser.ParseFile, BOM/CRLF, diff --check | 통과 |
| 정적 도구 | `python -m pyflakes` | 미실행: 설치되지 않음. 새 의존성을 넣지 않음 |
| 실제 모델·MCP·배포 | 솔루션 기기·지정 시험 PC | 미실행 |

PowerShell 시험은 프로세스 환경의 `PSExecutionPolicyPreference=Bypass`로 실행했다. 새 시험은 언어 왕복·상태 6종·서버 ID 보존·대기→활성 재점검·부분 관측 보고/종료·자식 오류 보존을 확인한다. 위키 생성물 검사 결과는 아래 작업 종료 기록에 남긴다.

작업 종료 검사: `refresh_generated.py` 완료. 위키 검사·ID 추적·기업 분석 해시 오류 0. 기존 ID 참조 경고 5건·신선도 경고 4건·낡은 정적 검토 파일 31건은 남으며 실제 실험 결과를 수정하지 않았다. `python -X utf8 deploy/check.py`도 통과했다. 루트 REPORT-TRAYUX.md는 Git 제외 상태로 유지한다.

## 실패·미완료·한계

새 구문·오프라인 회귀 검사는 통과했으나 기존 2건은 환경 제약으로 미실행이다. 원격 HEAD 재확인도 GitHub 연결 불가로 실패했다. 실제 창 배치·UAC·재설치·로그·하네스 호출은 확인하지 않았다. 화면의 서버 ID는 명시적으로 유지했다. 과거 PJ3 시험을 이번 코드의 실측으로 쓰지 않는다.

로컬 커밋은 미완료: git add가 공용 Git 메타데이터의 index.lock 생성 권한 거부로 실패했다. 허용된 작업 폴더 밖 Git 메타데이터의 쓰기는 이 환경에서 불가하다. 변경 파일·생성물은 보존했고 push·PR은 수행하지 않았다. 예정 첫 줄은 `fix(v2): Windows 키트 상태 번역과 부분 관측 진단 수정`이며 이유 본문은 커밋 제외 보고서에 준비했다.

## 다음 작업

DEV-84·DEV-89: 지정 시험 PC에서 재설치 후 상태 창 자동 열기, 낡은 대기 probe 교체, 한국어/영어 창·터미널, 실제 process 부분 관측과 service.log·게이트웨이 관측 상태를 대조한다. 숨은 아이콘은 OS 설정을 유지한다. 표시 이름은 구조화된 응답 계약을 별도 검토한다.

## 사용자에게 필요한 입력

현재 수정·로컬 커밋에는 없음. 실기기 검수에는 지정 시험 PC와 로그인된 실제 하네스가 필요하다. 자격 값은 기록하지 않는다.
