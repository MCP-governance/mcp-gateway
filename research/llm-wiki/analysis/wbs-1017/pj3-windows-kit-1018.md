# pj3 Windows 키트 실기기 시험 (2026-10-18 01:30–02:10)

- 대상: `pj3@100.80.43.21` Windows 11 Pro 10.0.26300, 콘솔 세션 1(pj3 관리자), 대상 계정 `pj3user`(표준).
- 키트: 기기 `https://100.83.175.111:443`에서 `user` 계정으로 발급(`POST /api/pc-kit?platform=windows`, 11.5MB, 18개 파일).
  응답 헤더 `X-Windows-Kit-Manifest-SHA256 = bef52451…c1bc7e`와 ZIP 안 매니페스트 해시 일치, 18개 파일 해시 불일치 0.
- 조직 승인 배포: 관리자 SSH(High 무결성)에서 매니페스트 파일만 `%ProgramFiles%\MCPGatewayInstaller`에 복사,
  승인 JSON을 `%ProgramData%\MCPGatewayInstaller\approved-windows-kit.json`에 배치, 소유자 Administrators·쓰기 SYSTEM/Administrators·Users 읽기.
  `Get-EndpointApprovedKit` 통과(18개 파일).
- 조작: 콘솔 세션 1의 대화형 예약 작업이 UIA로 창을 찾고 창 핸들에 `WM_SETTEXT`·`BM_CLICK`을 보냄(UIA는 WinForms 컨트롤을 Pane으로만 노출).
  캡처는 같은 작업의 `CopyFromScreen`. UAC 보안 데스크톱은 캡처되지 않음(“핸들이 잘못되었습니다”).

## 결과

| 단계 | 결과 |
| --- | --- |
| 비승격 마법사 시작 화면 | 게이트웨이 주소(HTTPS)·설치 위치·대상 계정·관측 범위·설치 권한 표시, UAC 없음 |
| 연결 확인 | 통과(UAC 없음, 키트 루트 인증서 고정 HTTPS) → `설치 위치 · 관측 범위 확인` |
| 설치 클릭 | 이때만 `consent.exe`(세션 1) 생성 — UAC가 설치 단계에서만 뜸 |
| UAC 프롬프트 강제 종료 | `조직 승인 설치기·무결성·실행 권한 확인 필요`, 다시 시도 활성. 사용자의 “아니요” 클릭(1223) 문구는 미확인 |
| 승격된 마법사(UAC 승인 상태 대용, `schtasks /rl highest`) | **결함 1**: 연결 확인 실패 — 승격 프로세스는 비보호 작업기를 쓸 수 없고 승인 요청은 health를 거부 |
| 설치(결함 1 수정 후) | **결함 2**: `설치 폴더 권한 적용 실패` — `icacls /T`가 (OI)(CI) 권한을 기존 파일에 빈 DACL로 남겨, UAC 승격 토큰(SeRestore/SeTakeOwnership 비활성)의 `/setowner`가 액세스 거부 |
| 설치(결함 2 수정 후) | 실행 파일 준비·점검(포함 Python) 통과 → **결함 3**: `승인된 하네스 설치 확인 필요` — Claude Code 공식 설치 위치(`~\.local\bin`, `WinGet\Packages`) 탐색 누락 |
| 결함 3 수정·재승인 중 | pj3가 Tailscale(디스코 ping 포함)에서 응답 없음 — 방화벽 변경 단계 이전에 끊김, VM 절전/중지 추정 |

화면 결함: 관리형 모드에서 값 없는 `장치 자격` 행이 표시됨 → 관측 모드에서만 표시.

## 수정 (main `b5e4c65`, 브랜치 `10/18-windows-kit-elevated`)

- `windows-common.ps1` `Set-EndpointAcl`, `managed-windows.py` `lock_down`: 루트에만 상속 권한, 하위는 `icacls <root>\* /reset /T`.
- `setup.ps1`: 승격된 마법사는 연결 확인도 승인 작업기 사용. `windows-trust.ps1`: 승인 요청 범위에 `health` 허용.
- `managed-windows.py` `place_harnesses`: `~\.local\bin`, `AppData\Local\Microsoft\WinGet\Packages` 추가.
- 단위 시험 `test_acl_reaches_existing_files_through_inheritance`(수정 전 코드에서 실패 확인), 전체 15건 통과.

## 남은 시험

pj3 복구 후: 재발급 키트로 승인 배포 → 관리형 설치 완료 → 서비스·트레이(pj3user 로그온)·활성화·하네스 호출, UAC “아니요” 문구,
표준 계정 pj3user 분기, 관측 전용 설치. pj3user의 하네스는 pj3의 공식 설치 파일을 사용자 위치로 복사해 준비함.
