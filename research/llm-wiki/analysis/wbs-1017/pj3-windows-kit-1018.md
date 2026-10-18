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

## 2차 시험 (02:07 재부팅 후, 02:12–02:35)

pj3는 02:07에 재부팅됨(로그온 시각). 전원 설정은 AC 절전 없음, DC 600초 — 호스트가 배터리로 보고하면 10분 뒤 절전 가능.

| 단계 | 결과 |
| --- | --- |
| 새 키트(b5e4c65) 승인 배포 → 승격 마법사 설치 | `설치 완료 · 조직 활성화 대기 · 대상 계정 로그온 시 트레이 시작`, `장치 자격` 빈 행 없음 |
| 설치 점검 | 포함 Python `-I -S` 모듈 33개·`site_automatic:false`, `._pth`=`python313.zip/./../#import site`, `pythonw.exe`·`LICENSE.txt` 있음. 폴더·파일 소유자 Administrators, SYSTEM/Administrators 전체·Users 읽기(하위 상속). SYSTEM 부팅 작업 `pythonw.exe -I -S managed-windows.py serve` 실행 중, pj3user 트레이 작업(Interactive·Limited·로그온 트리거). pj3user 아웃바운드 차단 규칙 3개. 시스템 루트 저장소·전역 CA 환경값 변경 없음 |
| 관리자 활성화 | **결함 4**: 409 — 설정 4개 중 3개 해시 불일치. `write_text`가 Windows에서 CRLF로 기록 |
| 제거 마법사(트레이의 `setup.ps1 -Remove`와 같은 명령) | `제거 완료`. 예약 작업·방화벽 규칙·프로그램 파일 정리 |
| 재설치 | **결함 5**: `다른 파일이 없는 설치 위치 필요` — SYSTEM 서비스가 남긴 `__pycache__`를 제거가 지우지 않음 |
| 결함 4·5 수정(b9b00d5) 후 재설치 | 설치 완료, 설치 증거 `match: true` |
| 관리자 활성화 | `managed-830fe5ad-…` `active`(root, 17:34:04Z) |

수정: `write_file` `newline=""`(0b61e9c), 서비스·관측 실행 `-B`, 제거 시 소유 모듈 `.pyc`만 삭제(b9b00d5). 헬퍼 명령은 게이트웨이 형식 검사(`idp.py`) 때문에 `-I -S` 유지.
1차 시험의 `managed-3f8e77a4-…`(제거됨) 행은 콘솔에 격리 상태로 남아 있음.
단위 시험 16건 통과. 파일 수정 직후 1회씩 30초 시간 초과 오류가 났다가 재실행 3회 연속 통과(간헐).

## 3차 시험 — 트레이·하네스 (12:25–13:30)

- 사용자가 `runas /user:pj3user cmd`로 로그온(보안 로그 4624 유형 2) → 로그온 트리거 트레이 작업은 실행되지 않음(마지막 실행 없음, 0x41303).
  runas는 데스크톱 로그온 세션을 만들지 않으므로 로그온 트리거 대상이 아니다. 예약 작업 조건(배터리·유휴·네트워크)은 모두 해제, 전원 AC.
- 대체 절차: 같은 명령줄(`powershell -STA … tray.ps1 -SettingsPath …`)을 pj3user 자격으로 콘솔 세션 1에서 실행(보조 로그온). 프로세스 소유자 pj3user·세션 1 확인.
- **결함 6**: 트레이 상태 창이 `연결 끊김`·오류 아이콘 — 하트비트는 정상(active)인데 프로세스 관측 `partial`(스냅숏 불완전)로 agent가 종료 코드 1,
  관리형 서비스가 이를 연결 실패로 게시. 트레이 연결 = 인증된 보고 성공으로 수정(e6b4ae9).
- 재설치 시 runas로 연 pj3user cmd가 남아 `대상 계정 로그아웃 필요`로 거부(설계대로). 해당 프로세스 종료 후 재설치·활성화(`managed-4cc3c869-…` active).
- 수정 후 트레이: 정보 아이콘, 툴팁 `엔드포인트 · 연결됨`, 메뉴 `상태 보기·최근 차단·지금 점검·콘솔 열기·제거`,
  상태 창 `연결 상태 연결됨 · 관리 상태 활성 · 최근 보고 13:15:59 · 게이트웨이 https://100.83.175.111:443 · 연결 점검 연결됨`.
  `지금 점검`은 pj3user 작업 폴더에 health 요청·완료 결과를 남김(키트 루트 인증서로 HTTPS 검증).
- 화면 관찰: 상태 창이 비모달이라 여러 개가 겹쳐 열린다(경미).
- **하네스 사본 손상**: 시험 준비 때 `cmd copy`로 pj3user `~\.local\bin`에 넣은 `claude.exe`(원본은 sparse 파일)가 같은 크기·다른 해시로 손상돼
  `--version`도 0xC0000005로 종료. 설치기는 이 사본을 승인 하네스로 고정함(실행 가능성은 확인하지 않음 — 사용자 소유 바이너리를 관리자 권한으로
  실행하지 않기 위해 의도된 한계). 정상 사본으로 교체 후 재설치.

### 하네스·MCP 경로 (13:30–13:45)

- 제거 마법사 후 설치 폴더 완전 삭제(`__pycache__` 정리 수정 확인) → 재설치 → `managed-c5f45cf7-…` active.
- pj3user에서 관리형 런처 `claude.cmd mcp list`: context7·github·markitdown이 `https://100.83.175.111:443/mcp/<서버>/`로 렌더링,
  키트 루트로 TLS 통과, 상태는 `Needs authentication`(목록 점검은 헤더 헬퍼를 쓰지 않는 것으로 보임 — 미확인). `codex.cmd mcp list` 동일 3개.
- pj3user 직접 인터넷(`curl https://api.github.com`) 실패(000) — 계정 단위 아웃바운드 차단 동작.
- pj3user에서 헤더 헬퍼 `managed-windows.py header` 종료 0, `Authorization` 헤더 반환(값 미출력).
- 같은 헬퍼 헤더와 키트 루트로 게이트웨이 GitHub MCP 직접 호출: `initialize 200`(mcp-governance-security-gateway 3.0.0), `tools/call get_me 200 login=pokochy`.
- `claude.cmd -p …`는 `Not logged in · Please run /login` — pj3user의 Claude/Codex 계정 로그인이 없음. 자격을 빌려 쓰지 않으므로 여기서 중단.

## 중단 지점과 해결안

| 남은 항목 | 막힌 이유 | 해결안 |
| --- | --- | --- |
| 로그온 트리거로 트레이 자동 시작 | runas는 데스크톱 로그온이 아니어서 트리거 대상 아님. Claude는 대화형 로그온을 만들 수 없음 | pj3 콘솔에서 `Ctrl+Alt+Del → 사용자 전환 → pj3user`로 로그인한 채 두기. 또는 소유자 결정으로 pj3 원격 데스크톱 허용 → Claude가 pj3user로 RDP 로그온 |
| 관리형 하네스의 모델 호출 | pj3user에 Claude Code/Codex 계정 로그인 없음 | pj3user 세션에서 소유자가 `claude`(/login) 또는 `codex login --device-auth`로 본인 계정 로그인 → Claude가 하네스 호출·차단 시험 |
| UAC "아니요" 문구 | 보안 데스크톱은 자동 조작 불가 | 콘솔에서 설치 클릭 후 UAC에서 "아니요" 1회 |

## 남은 시험

pj3user 콘솔 로그온 후 트레이(연결됨·관리 상태 활성·지금 점검·콘솔 열기)와 관리형 하네스 호출, UAC “아니요” 문구,
표준 계정 pj3user 분기, 관측 전용 설치. pj3user의 하네스는 pj3의 공식 설치 파일을 사용자 위치로 복사해 준비함.
