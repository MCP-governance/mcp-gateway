# 2026-10-27 Windows GUI 별도 프로그램 실행·바탕화면 바로가기

- 작업자: Claude Code (Opus 5.5)
- 코드 기준: main `1d22361`, 브랜치 `10/27-win-gui-launcher`. 변경 `endpoint-agent/windows-common.ps1`·`tray.ps1`·`setup.ps1`·`windows-worker.ps1`·`install.cmd`, `full_stack_lab/gateway/app/windows_oneclick.py`, 시험 `tests-windows/test_windows_reinstall.py`
- 시작 근거: 소유자 지시(10-27) — 「바탕화면에 GUI 바로가기, GUI가 PowerShell로 뜨는 것 같은데 별도 프로그램으로 잡히게」. 결정 D-260.
- 완료 조건: 설치 뒤 바탕화면 바로가기, 트레이·상태 창이 PowerShell이 아닌 별도 프로그램으로 표시, 설치 중 빈 터미널 창 없음.

## 결과

- 트레이는 설치 때 만들어지는 `MCPGateway.exe`(콘솔 없는 실행 파일, 방패 아이콘)가 같은 폴더의 `tray.ps1`을 자기 프로세스에서 실행한다. 작업 표시줄·작업 관리자에 MCPGateway로 따로 잡힌다.
- 트레이가 처음 뜰 때 바탕화면에 「MCP 연결」 바로가기를 만든다. 바로가기는 상태 창을 연다(이미 떠 있으면 기존 트레이가 창을 연다). 제거하면 바로가기도 지운다.
- 설치 마법사 창도 같은 아이콘으로 PowerShell과 따로 묶인다.
- ZIP 키트 `install.cmd`와 원클릭 `.cmd`가 Windows Terminal 창을 남기지 않는다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Windows 단위 시험 | 개발 노트북 Windows 11, `python -m unittest test_windows_kit test_windows_oneclick test_windows_reinstall`(10-27) | 50건 통과(새 시험: 실행 파일이 인자·STA로 tray.ps1을 실행, 바로가기 제거는 우리 `.lnk`만) | 로컬 실행 |
| 키트 다운로드 회귀 | `python full_stack_lab/tests/kit_download_check.py` | 8건 통과 | 로컬 실행 |
| 실기기 트레이 | pj3(관리자 pj3, 간편 모드 기존 설치)에 바뀐 세 파일을 넣고 `Install-EndpointLauncher`·`Register-EndpointTray` 실행(10-27 12:4x) | 예약 작업 실행 파일 = `MCPGateway.exe`, 세션 1에서 실행, 바탕화면 `MCP 연결.lnk` 생성, 바로가기 실행 → 상태 창(제목 표시줄·작업 표시줄 방패 아이콘, 프로세스 MCPGateway) | 세션 1 화면 캡처 |
| 실기기 설치 진입점 | pj3 세션 1에서 탐색기로 `install.cmd` 실행(마법사는 대역 창), 이전 판본과 비교 | 이전: 마법사 + WindowsTerminal「powershell.exe」 창. 이후: 마법사 창만 | 세션 1 창 목록 |
| 원클릭 `.cmd` | pj3 세션 1 승격 작업으로 실행(대역 부트스트랩) | 승격 창만 뜨고 `.cmd` 종료 | 세션 1 창 목록 |
| 배포 | 기기 배포·새 키트 다운로드→원클릭 전 과정 | 미실행 | — |

## 실패·미완료·한계

- 새 키트를 기기에서 받아 처음부터 원클릭 설치하는 전 과정은 기기 배포 뒤 확인한다(이번에는 pj3 기존 설치에 파일을 넣어 확인).
- pj3 프로그램 폴더의 세 PS1은 지금 브랜치 판본이다(원본은 `C:\Users\pj3\mcpgw-wingui\backup`). 다음 main 원클릭 설치가 덮어쓴다.
- 원클릭 `.cmd`의 종료 코드는 이제 「승격 실행 시작」만 뜻한다(설치 결과는 완료 대화 상자).
- 바로가기는 AppUserModelID가 없어 작업 표시줄 고정이 실행 파일 기준이다.

## 다음 작업

- 병합 뒤 기기 배포 → pj3에서 새 원클릭 설치·제거로 바로가기 생성·삭제와 트레이 실행 파일 재확인.

## 사용자에게 필요한 입력

없음
