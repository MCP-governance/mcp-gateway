미커밋 — W11-WINDOWS-ONECLICK

# 2026-10-23 Windows 원클릭 설치 구현

- 작업자: Codex / sol 구현. Agent Hub job `9d938910e0e5`.
- 기준: `48bb19ec52de0e1e2198d19e75b1f62e7aab2014` = 로컬 `origin/main`, 브랜치 `10/23-windows-oneclick`. 시작 워킹 트리는 깨끗했다.
- 원격 HEAD 재조회: `git ls-remote --symref origin HEAD`는 GitHub 연결 불가로 실패. 공용 `.git` 쓰기·커밋·보조 worktree/clone 없음.
- 시작 근거: [10-22 키트 실측](2026-10-22-kit-e2e.md), D-68·D-71·D-72·D-118. 새 결정 D-197은 `check_trace.py --next D`가 반환한 번호이며 fetch 실패/로컬 원격 ref 기준이라는 한계를 유지한다.
- CHECKED: 기준 커밋/브랜치/diff/최근 관련 커밋을 재확인했다. timeout 3600초. inbox `8234`(dispatcher/worker 소유권, 다른 작업 트리, W11 재시도 문구는 잘린 본문), `8238`(별도 antigravity 기업 사례)은 이번 파일 소유권을 변경하는 지시로 해석하지 않았다. 이번 트리의 diff는 이 작업에서 만든 변경과 일치하며 충돌/타 작업 미커밋 변경은 발견하지 못했다. 관련 최신 코드 커밋 `9ce32ae`의 관측기 분리·주기/토큰 캐시 동작은 보존했다.
- 제공된 coordinator 관측: Codex 잔여 29%, 리셋 `1793082802` = 2026-10-27 15:33:22 KST. 실시간 재조회한 값이 아니며 Claude 잔여는 미상이다.
- 요구·코드·조건·효과 정본: [원자 요구사항 분석](../../analysis/windows-oneclick-2026-10-23.md).

## 결과

콘솔 Windows 버튼은 ZIP 대신 `mcp-managed-setup-windows.cmd` 한 파일을 받는다. 기존 인증 API에 `packaging=oneclick`만 추가했고 기본 ZIP 응답은 유지했다.
파일 안의 bootstrap/ZIP을 메모리에서 검증하며 UAC 한 번으로 보호 설치기·승인 JSON 준비와 기존 worker 실행을 연결한다.
직원에게 별도 압축 해제나 IT 선행 배포를 요구하지 않는다. 기존 승인판이 있으면 내용이 완전히 같아야 하며 손상/다른 판은 덮어쓰지 않는다.

새 경로는 직원 계정 유형과 무관하게 별도 표준 관리 계정을 준비하고 CreateProfile로 프로필을 만든다.
직원 로그아웃/첫 로그인 없이 등록이 진행되는 구조다. 관리 계정에 이미 프로세스가 있으면 기존처럼 차단한다.
직원 프로필에서 공식 하네스를 복사하고 관리 계정 SID의 방화벽·보호 설정·SYSTEM 서비스·헤더 도우미·로그온 트레이 작업을 유지한다.
설치 종료는 조직 활성화 대기이고, 관리 계정에서 실행할 `claude auth login`과 `codex login --device-auth`를 결과에 표시한다.
실제 하네스 사용에는 관리 계정 로그인이 필요하다. 설치를 끝내기 위한 별도 로그인/로그아웃 조작은 추가하지 않았다.

최초 신뢰는 콘솔 다운로드와 관리자의 명시적 UAC 승인이다. SHA-256은 발행자 서명이 아니다.
새 서명 인증서/신뢰 저장소 변경은 없으며 `AllSigned`는 파일/계정 변경 전에 거부한다. worker만 프로세스 범위 RemoteSigned로 실행하고 시스템·그룹 정책은 변경하지 않는다.
기존 IT 서명·승인 배포는 선택지로 남는다. 기존 worker/trust 자체는 발행자 서명 검증을 구현하지 않았고 보호 경로·승인 JSON·해시를 검사한다는 점을 코드로 확인했다.

변경 파일: `endpoint-agent/windows-oneclick.ps1.in`, `managed-windows.py`, `windows-worker.ps1`, `tests-windows/test_windows_oneclick.py`,
`full_stack_lab/gateway/app/windows_oneclick.py`, `agent_service.py`, `agent_static/console.js`, endpoint README·CONSOLE_UI·DECISIONS·현황·백로그·이 분석/보고·저장소 스냅샷·현재 파일 해시를 반영한 `catalogs/threats.json`/`threats/control-map.md`.
기존 시험 파일과 기대값은 수정하지 않았다. 새 `.ps1.in`은 파일로 실행하지 않는 ASCII/UTF-8 BOM 없는 LF 템플릿이다.
기존 `.ps1`의 BOM·CRLF는 보존했다. 기존 Windows 시험은 모든 실행형 `.ps1`에 BOM을 요구하므로 새 템플릿을 실행형 스크립트로 추가하지 않았다.

## 검증

환경: 이 노트북의 Windows PowerShell 5.1·Python 3.10.5(`py -3`)·Node. 10-23 KST 로컬 오프라인 검사. 최종 구문/Windows 회귀 재확인: 01:56경.
아래 PowerShell 단위 시험은 해당 시험 프로세스의 `PSExecutionPolicyPreference=Bypass`만 사용했다. OS/사용자 실행 정책은 변경하지 않았다.

| 확인 종류 | 실제 명령/조건 | 결과 |
| --- | --- | --- |
| PowerShell 구문 | `[System.Management.Automation.Language.Parser]::ParseFile` 기존 `.ps1` 6개 + 새 `.ps1.in`, 생성 loader/seed는 새 시험에서도 검사 | 통과 |
| Python 구문 | `py -3 -m py_compile` managed-windows·agent_service·windows_oneclick·새 시험 | 통과 |
| 기존 Windows 키트 | `py -3 -X utf8 -m unittest discover -s endpoint-agent/tests-windows -p test_windows_kit.py -q` | 16 통과 |
| 새 원클릭 시험 | 같은 discover의 `-p test_windows_oneclick.py` | 9 통과. mock UAC·합성 ZIP·대역 Win32/등록이며 실설치 아님 |
| Windows 설정 | 직접 실행은 platform.win32_ver가 FakeRegistry에 `OpenKeyEx`를 호출해 실패. `platform.uname()`을 먼저 호출한 뒤 `runpy.run_path(...,run_name='__main__')`로 동일 파일 재실행 | 7 통과/1 생략(Pydantic 2 부재). 기대값 무변경 |
| Windows 관측 | `py -3 -X utf8 full_stack_lab/tests/windows_os_observer_check.py` | 7 통과 |
| field 키트 | 직접 실행은 Python3.10 `tomllib` 부재로 import 실패. 기존 설치된 `pip._vendor.tomli`를 `sys.modules['tomllib']`로 제공하고 같은 파일을 runpy로 실행 | 16 통과/1 생략(Docker CLI 부재). 의존성 설치/기대값 변경 없음 |
| 콘솔 구문/상태 | `node --check full_stack_lab/gateway/app/agent_static/console.js`; `node --test full_stack_lab/tests/console-state.test.mjs` | 구문 통과, 15 통과 |
| 무인증 경로 | `py -3 -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 무인증 1개·인증 필요 97개 |
| 추적 | `py -3 -X utf8 research/llm-wiki/tools/check_trace.py --no-fetch` | 오류 0/기존 경고 6 |
| 위키 목록/매핑 | `build_wiki.py`; 코드 변경 후 `map_threats.py` | 670문서/24정책, 과거 독립 검토 stale 표시를 보존 |
| 위키 검사 | 기본 `check_wiki.py`는 제외된 로컬 provenance29개 누락과 변경 코드 해시3건으로 실패. 매핑 재생성 후 `--ci-ignored-local-sources` | 오류 0, 제외된 로컬 원문 부재는 경고로 유지 |
| 추가 lint | `py -3 -m pyflakes ...` | 실패: pyflakes 미설치. 새 의존성 설치 없음 |
| WSL Python 확인 | `wsl.exe -d kali-linux -- python3 --version` | 접근 거부. WSL 작업/스택/원격 접속 없음 |
| 실제 Windows 실설치·UAC·프로필·GUI·방화벽·활성화·모델 로그인 | 미실행 | 리더가 pj3에서 확인 |
| 솔루션 배포·PJ1/기기 접속·실제 MCP/upstream 효과 | 미실행 | 이번 범위 밖 |

## 실패·미완료·한계

초기 실행에서 시스템 Restricted 정책 때문에 기존 시험 일부가 차단됐고, 새 템플릿 구문/인코딩 및 BOM 문자열 로드 문제를 수정한 뒤 재검증했다.
새 템플릿의 BOM 없는 파일을 기존 `.ps1` 시험에 넣으면 기존 BOM 기대값이 실패한다는 사실도 확인했다. 기대값을 바꾸지 않고 메모리용 ASCII 템플릿으로 분리했다.
기존 Windows 설정/field 키트의 직접 실행 실패와 위 표의 준비 조건을 숨기지 않는다. 검사기 미설치도 통과로 세지 않는다.

공식 하네스가 직원 프로필의 기존 탐색 위치에 있어야 한다. 설치기는 인터넷에서 새 하네스를 받지 않는다.
다운로드된 파일을 브라우저·SmartScreen·앱 제어가 허용하는지, 실제 UAC 횟수·CreateProfile 결과·로그온 환경 반영·모델 로그인은 미검증이다.
서명 발행자/조직 서명 키는 추가하지 않았고 서명 강제 환경을 우회하지 않는다. 최초 다운로드 출처의 진위는 파일 자체 해시만으로 증명하지 못한다.
부분 실패로 남은 보호 설치물이나 기존 다른 승인판은 자동 제거/덮어쓰기하지 않는다. 복구는 기존 IT 경로의 확인이 필요하며 실기기 복구/경쟁 시험은 미실행이다.
직원 계정 자체의 도구 실행은 여전히 통제 범위 밖이다. 설치 완료를 전체 PC 통제나 활성화/모델 로그인 완료로 표시하지 않는다.

## 다음 작업

리더가 미커밋 변경을 독립 검토한다. pj3 수용 기준은 실제 파일 실행→UAC 1회→직원 로그아웃 없는 등록→활성화 대기/관리 계정·모델 로그인 안내이며 현재 미실행이다.

## 사용자에게 필요한 입력

없음. 기기 접속·배포·실설치는 이 작업에서 수행하지 않았다.
