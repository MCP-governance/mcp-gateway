# 2026-11-02 PC 설치 파일을 실행 파일로

- 작업자: Claude Code
- 코드 기준: main `69e76116` → 브랜치 `11/02-kit-exe`(PR #78). 변경: `full_stack_lab/gateway/native/setup/`(신규), `Dockerfile`, `app/agent_service.py`, `app/windows_oneclick.py`, `agent_static/console.js`·`i18n-en.mjs`, 시험 4개, 키트·현장 문서
- 시작 근거: 소유자 지시(11-02) 「키트 설치 때 받는 파일이 cmd·sh가 아니라 exe 같은 실행 파일로」
- 해결할 문제와 완료 조건: 콘솔 **PC 연결 설정**의 Windows·Linux 받기가 실행 파일 하나를 내려주고, 그 파일로 기존 설치가 끝까지 진행된다.

## 결과

- 게이트웨이 이미지의 Go 빌드 단계가 고정 설치 프로그램 `windows-amd64.exe`(GUI 서브시스템)·`linux-amd64`(정적)를 만들어 `/opt/mcp-setup`에 둔다. 다운로드마다 직원 자격 없는 기존 키트를 뒤에 붙인다(D-338).
- Windows `mcp-managed-setup-windows.exe`: 붙은 `:MCPGW_COMMAND` 줄의 PowerShell 명령을 창 없이 실행한다. 그 뒤 UAC·파일 해시 재확인·ZIP 검증·설치는 D-197 `.cmd`와 같은 코드다.
- Linux `mcp-managed-setup-linux`: 붙은 ZIP을 `~/mcp-managed-kit`에 새로 풀고(평면 목록만) `install.sh`를 실행한다. 콘솔 안내는 `f="$(ls -t ~/Downloads/mcp-managed-setup-linux* | head -1)" && chmod +x "$f" && "$f"`.
- macOS는 그대로 `.command`. 프로그램이 없으면 원클릭 받기는 503, ZIP 받기는 그대로.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `kit_download_check.py`(10)·`macos_kit_check.py`·Node `notion-bugs-ui`·`kit-download-console`·`tests-windows/test_windows_oneclick.py`(17, Windows)·pyflakes·`deploy/check.py`, 11-02 | 통과 | 로컬 출력 |
| 빌드 | WSL Go 1.26 `go vet`(windows/linux)·두 실행 파일 빌드, 결과물에 `:MCPGW_PAYLOAD` 없음 | 통과 | 로컬 출력 |
| 실행 파일 단독 | Linux: 임시 HOME 풀기·인자 전달·이전 폴더 교체·`../` 거부·단독 실행 거부. Windows(노트북): 공백 경로에서 붙은 명령 실행·`MCPGW_SETUP_FILE`·종료 코드 | 통과 | 로컬 출력 |
| 배포 | 기기 시험 스택(:8000)에 PR 브랜치 `field up`, 컨테이너 `/opt/mcp-setup` 두 파일 확인, 15:40 | 통과 | 기기 출력 |
| 실제 다운로드 | 기기 API 일회용 티켓→폼 POST(콘솔과 같은 흐름): `mcp-managed-setup-windows.exe` 25.4MB, `mcp-managed-setup-linux` 4.4MB | 통과 | 응답 헤더 |
| Windows 실기기 | pj3: MOTW 붙인 exe를 셸 실행 → 「파일 열기 - 보안 경고」(알 수 없는 게시자) → 실행 → UAC → 설치기 15:48:57~15:50:31 파일 교체·서비스 기동, 게이트웨이 새 장치 `managed-33d16640` active 하트비트 15:50:34(이전 기록 revoked). Defender 탐지 없음 | 통과 | 화면 캡처·DB 조회 |
| Linux 실기기 | pj1: 콘솔 안내 명령을 PTY에서 실행 → 실제 키트 18개 파일 풀림(install.sh 755) → install.sh가 sudo 암호를 물음 | 부분 | 실행 기록 |

## 실패·미완료·한계

- pj3의 「실행」·UAC 「예」는 콘솔 세션에서 사람이 눌렀다(자동화로 보안 데스크톱을 누르지 않았다). 설치 중 MINT 로그인 단계는 관찰하지 못했다.
- pj1은 sudo 암호 단계에서 멈췄다. 이후 단계는 기존 `install.sh` 그대로이며 이번에 재설치하지 않았다.
- 코드 서명이 없어 Windows가 「알 수 없는 게시자」 경고를 보인다. Linux 실행 파일은 x86-64만이다.

## 다음 작업

- 서명 인증서가 생기면 Go 빌드 단계에서 Authenticode 서명.

## 사용자에게 필요한 입력

없음
