# 2026-11-01 엔드포인트 터미널 화면·CLI를 사용자 웹 콘솔과 같은 기능·디자인으로

- 브랜치 `10/31-overhaul`(PR #71, 미병합). 시작 `bce75c80` → 이 보고 시점 `70f3623e` 이후. 기기 :8000·pj1·pj3 키트 반영.
- 소유자 지시: 서버 OS(데스크톱 없음)에서도 웹 콘솔 기능을 CLI로, CLI에서 웹 콘솔 열기, 시험은 pj3(Windows)·pj1(Linux)에서 세부 화면 캡처로 보고 → root 콘솔 기록과 대조 → sol UI 검수, 상용 레퍼런스·디자인 스킬 활용.

## 무엇을 바꿨나
| 영역 | 이전 | 지금 | 근거·시험 |
| --- | --- | --- | --- |
| `mint` 대화형 화면 | 상태 카드만, 청록 그라디언트 블록 로고, 화살표 무시 | 앱바(MINT 타일)·탭 1 상태·2 MCP 서버·3 호출 기록·4 도입 요청, ↑↓ Enter Esc n s o r, 콘솔 다크 토큰 색 | `kit_screen.live/console_page/tab_bar`, `tests/mint_cli_check.py` TerminalPages |
| 하위 명령 | servers·logs·request·login·ui | + `logs [번호]` 상세, `requests`, `sources [서버]`, `console [페이지]`, `--json`, 한국어 오류·도움말 | `kit_access.mint_command` |
| PC 호출 기록 | 게이트웨이가 막은 호출 누락(Codex 훅은 돌아온 호출만 보고) | 판정 원장에서 이 PC(workstation) 호출을 합침, 짝지어진 판정은 한 번 | `endpoint_plane.self_summary` |
| 서버 상태 | 동의 대기 서버도 「사용 가능」 | 「동의 필요」, 다음 할 일 `mint console consent` | `kit_access.sections` |
| Linux 서버 이름 | 내부 ID | 표시 이름(`server_names`) | `managed-linux.py` |
| Windows 깨진 관리 구간 | 10초마다 실패·백업 누적(1,087개) | 같은 내용 백업은 한 번 | `managed-windows.keep_backup`, `test_windows_kit` |
| 웹 콘솔 | sol 측정 업무 흐름 5개의 문제 18개 | 18개 안 전부(D-307): 처리할 일 우선, 새 신청 먼저, 경보 같은 기간·묶음, 기기 검색, 뒤로가기 복원, 필드 오류, 도구별 동의 등 | Node 111, `research/llm-wiki/status/reports/2026-11-01-console-ux-2.md` |
| 문서 | README 10-25~10-31 판, 구조도 10-23판 | README 13개, 구조도 2판 29쪽·생성기 | `deploy/check.py`, 링크 검사 |

## 시험
- terra(pj3, 캡처 43장)·Sonnet(pj1, 캡처 80장) → 결함 B-1~B-12 등 수정 후 재배포. pj1 대화형 화면은 PC 안 PTY 실행기(`ptydrive.py`)로 탭별 캡처.
- root 콘솔 대조: 판정 #243(경보·MCP-SHADOW-002)·#244(차단·P-CONSENT-001)·#247(차단·P-RATE-003)이 PC 상세와 같은 값, 엔드포인트 요청(Semgrep) 표시.
- 전후 비교: `tmp/e2e-1101/evidence/`(저장소 밖), 공개 페이지는 Artifact.

## 한계·남은 것
- 새 아이콘 58개의 iconify 원본 대조 미실행(요청 제한), `icons/sources.json` 비고에 표시.
- 로컬에서 실패하는 기존 시험(cp949·TLS 등 환경 의존)은 CI에서 확인.
- 터미널 새 요청(n) 입력은 대체 화면을 떠나 질문 3개 — pj3 실제 창 확인은 이 보고 뒤 캡처로.
