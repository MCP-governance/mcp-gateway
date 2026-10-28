# Windows 키트 실측 결과 (pj3, :8000 시험 스택)

- 브랜치 `10/28-windows-kit`, 배포 커밋 `e62183b7`(그 앞 병합 `df20e87b` = 10/27-internal-repo-console-only 5d7b1937 포함)
- 시험 PC: pj3 (Windows 11, 관리자 계정 pj3, 간편 모드), 하네스 Claude Code 2.1.302(모델 로그인 유효), 2026-10-28 12:40~13:46
- 게이트웨이: https://100.83.175.111:8000 (compose `mcpgw-0c527e096b`). 443 메인 스택은 건드리지 않음
- 화면 증거는 세션 1 자동화로 찍은 스크린샷(`C:\Users\bobysg\AppData\Local\Temp\s_<태그>.png`). 시험 중 다른 에이전트도 같은 pj3 화면에서 Codex를 돌렸다(원장에 MCP-SHADOW-002 호출이 섞인 것은 그쪽)
- 하네스 호출은 모두 실제 `claude -p`(대신 직접 클라이언트를 쓴 곳 없음)

## 구역별 결과

| 구역 | 결과 | 증거 |
| --- | --- | --- |
| 1 설치 | 통과(UAC 제외) | 옛 443 키트를 마법사 **제거**로 제거 → :8000 원클릭 `.cmd` 설치 → 활성(자동 활성화) → 트레이 상태 창 `연결됨·활성·간편 모드·승인 서버 6·claude 2.1.302·모델 응답 claude 정상 4.8s·도구 23(승인 서버 6/6)·서버 연결 정상`(s_re1.png). 설치 약 60초 안. UAC: 제한 권한으로 실행하면 `consent.exe`가 세션 1 보안 화면에 뜸(캡처는 흰 화면, 입력 불가) → 사람이 눌러야 함 |
| 2 트레이 | 통과 | 상태 창 항목 전부 표시(s_tr4.png), **연결 확인**(모델 응답 4.1s 갱신), **다시 연결**(「게이트웨이 응답 정상」, s_tr5.png), 서버 목록 변경 시 60초 안 반영. 모델 로그인·콘솔 열기 버튼은 누르지 않음(로그인 창을 띄움). 승인 서버 칸은 표시 이름이 아니라 서버 ID |
| 3.1 동의→재호출 | 통과(판정은 Alert) | Learn 첫 호출 원장 148·149 `Block P-CONSENT-001` → 동의 허용 → 150·151 `Alert MCP-SHADOW-001`(upstream 실행됨), 한 줄 요약 정상. DeepWiki 162, Cloudflare 163 동일. 정책 ID가 매뉴얼의 `P-AUTHZ-ALLOW-001`이 아닌 이유: pj3 사용자 Codex 설정의 `cua_repl`·`node_repl`(stdio)이 섀도로 보고됨(`endpoint_inventory`, 설계대로) |
| 3.2 GitHub | 미실행(사람 필요) | GitHub MCP는 도구 목록을 받는 데도 토큰이 필요해 도입 신청 discover가 502. 실제 GitHub 개인 액세스 토큰이 있어야 서버 등록·연결·`MCP-CREDENTIAL-001` 시험 가능 |
| 3.3 출력 통제 | 통과 | DeepWiki read_wiki_contents(flask) 원장 168 `Block MCP-OUTPUT-001`(262144 byte 상한, upstream 실행됨, 정상), Cloudflare 검색 163 실행됨(타임스탬프 숫자 오탐 없음) |
| 3.4 허용 주소 | 통과(매뉴얼 정정) | MarkItDown convert_to_markdown raw.githubusercontent.com 원장 166 `Alert MCP-SHADOW-001` 실행됨, example.com 167 `Block PAC-01`. AWS read_documentation은 허용 주소 docs.aws.amazon.com을 기록해도 161·164 `Block PAC-12`(원격 서버 주소 인자, D-132 설계) |
| 3.5 동시 사용 | 통과 | DeepWiki(169)·Learn(170) 두 호출이 13:07:12~34에 겹쳐 둘 다 도구를 찾고 실행됨 |
| 3.6 정책 변경 중 | 통과 | 첫 시도 원장 173 `Block P-RATE-003`(flask 중복 호출). DeepWiki 도구가 쓰기로 제안돼서였고, 관리자가 승인 때 읽기로 낮춘 새 서버로 재시험: 호출 195~198 전부 실행됨, 그 사이 13:18:17~29에 GitMCP 승인 → 트레이 60초 안 반영 |
| 4 수명주기 | 통과 | GitMCP 신청→승인→직원 동의→호출 실행(원장 176) → 철회 → 1분 안에 트레이·`managed-mcp.json`에서 제거, 하네스 답 「도구를 찾지 못했다」 |
| 5 재설치·재부팅·제거 | 재설치·제거 통과 / 재부팅은 사람 | 재설치(업데이트): 새 `.cmd`로 덮어설치 3회, 이전 엔드포인트는 자동 폐기되고 새 엔드포인트 즉시 활성. 같은 `.cmd` 재실행은 「엔드포인트 처리 실패 · … 새 설치 파일을 받아 실행하세요」(1회용 자격, 정상). 제거: `Program Files\MCPGatewayManaged`·`ClaudeCode\managed-*.json`·예약 작업·바탕화면 바로가기·Codex requirements 모두 사라짐, 제거 뒤 `claude -p`는 게이트웨이 없이 정상. 재부팅 대용: SYSTEM 작업(부팅 트리거)과 트레이 작업(로그온 트리거)을 정지·재시작 → 14초 만에 보고 재개·호출 실행. 실제 재부팅은 자동 로그온이 없고 같은 화면을 다른 에이전트가 쓰고 있어 하지 않음 |

## 발견한 결함과 수정

| 결함 | 근본 원인 | 수정 |
| --- | --- | --- |
| 제거가 「제거 완료」인데 `MCPGateway.exe`·`.ico`가 남고 다음 설치가 「다른 파일이 없는 설치 위치 필요」로 멈춤 | `endpoint-agent/windows-common.ps1` `Remove-EndpointFiles`(≈390행)가 설치 때 쓴 `.endpoint-kit` 소유 목록만 지움. 런처 없는 키트가 런처 있는 설치 위에 깔리면 목록에 두 파일이 없음 | 기계 설치 폴더 제거는 두 파일을 항상 소유로 취급(commit e62183b7, D-280). 시험 `test_removal_also_takes_the_launcher_an_older_manifest_never_listed`는 수정 전 실패·후 통과. pj3에서 매니페스트를 일부러 옛 형태로 만든 뒤 제거 → 폴더 전체 삭제 → 재설치 활성 확인 |
| `tests-windows` 설치 시험 3건이 `ModuleNotFoundError: windows_status` | D-271이 `managed-windows.py install` 끝에서 `windows_status`를 가져오게 한 뒤 시험이 상태 모듈 대역 없이 `install()`을 호출 | 시험 3건에 대역 추가(e62183b7). 이후 50건 통과 |

코드를 바꾸지 않은 관찰(결정 필요, D-280에 기록): 승인 서버 칸이 표시 이름이 아닌 서버 ID, Windows에도 PC 격리 서버(Memory)가 승인 서버로 나오고 호출은 `MCP-CATALOG-001`(「로컬 실행을 맡을 활성 관리형 엔드포인트가 없습니다」), 주석 없는 원격 MCP는 쓰기로 제안돼 반복 호출이 `P-RATE-003`, 사용자 Codex 설정의 MCP는 모든 호출에 `MCP-SHADOW-001` 경보.

## 실행한 시험

- `python -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p "test_*.py"` — 50건 통과(2회)
- `full_stack_lab/tests/windows_config_env_check.py` 8건, `windows_kit_reinstall_check.py` 10건, `windows_os_observer_check.py` 8건 통과
- 실기기: 위 구역 1~5

## 사람이 할 일

1. UAC: 일반 사용자 또는 제한 권한으로 `.cmd`를 더블클릭해 UAC 보안 화면의 **예**(표준 사용자는 관리자 자격)를 누르고 설치가 이어지는지, **아니오**일 때 안내 문구를 확인. 이번 시험은 이미 관리자 권한인 자동화 창에서 설치해 UAC 없이 지나갔다.
2. 3.2: 실제 GitHub 개인 액세스 토큰으로 GitHub MCP(`https://api.githubcopilot.com/mcp/`)를 도입 신청·승인하고, 연결 전 `MCP-CREDENTIAL-001` → **내 연결**에서 토큰 연결 → 호출 실행 → 해제.
3. 재부팅: pj3를 재시작하고 pj3로 로그인(자동 로그온 없음) → 1분 안에 트레이 「연결됨」, `claude -p` 호출 실행.
4. 모델 로그인 버튼, 콘솔 열기 버튼 동작(로그인 창·브라우저를 띄우므로 사람이 확인).

## 매뉴얼 정정(`MANUAL_TEST_WINDOWS.md`)

화면 이름을 실제 콘솔(**호출·감사 기록**)로, 설치 결과(별도 마법사 없음·세 칸은 트레이 창·1회용 자격·UAC는 사람), 3.1(동의는 서버마다 한 번 차단을 겪어야 생성, 섀도 Codex 설정이면 Alert, 원격 도구는 읽기로 낮춰 승인), 3.3(flask는 MCP-OUTPUT-001이 정상), 3.4(허용 주소는 MarkItDown, 원격 AWS는 PAC-12), 3.2·3.5·3.6·4·5(철회 후 새 서버 ID, Start-Job 한글 깨짐, 재부팅 조건, 제거 확인 목록)를 고쳤다.

## 시험 상태 복원

- 내가 도입한 DeepWiki·Microsoft Learn·Cloudflare Docs·AWS Knowledge·GitMCP는 모두 철회(MarkItDown·Memory 유지). 트레이 승인 서버 목록은 2개로 돌아옴
- pj3는 :8000 키트가 설치·활성(엔드포인트 `managed-10de258a-38e4-44ad-8f86-9013bfeab8fb`, 트레이 작업 실행 중). 사용자 동의 기록은 시험 서버 것이 남아 있다
- 시험 보조 파일: pj3 `C:\ProgramData\mcpgw-test\ui.ps1`, `C:\Users\pj3\Downloads\mcp-*.cmd`(1회용·소비됨)
