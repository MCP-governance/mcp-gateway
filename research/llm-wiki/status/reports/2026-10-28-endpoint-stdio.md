# 2026-10-28 승인 stdio MCP 엔드포인트 실행

- 작업자: Codex. 기준 `91524ab5e0d53f08439e8233aa44b979ca0cfd63`, 작업 브랜치 `10/28-endpoint-stdio` 유지.
- 시작 근거: 소유자 제공 BRIEF, D-263·D-264·D-192·D-114. BRIEF는 변경·스테이징·커밋하지 않았다.
- 범위: 기존 로컬 작업 경로에 Docker 없는 소스 프로세스 모드, Windows 실행기/키트 연결, 승인·runtime 경로 정리. push·PR·병합·배포·PJ1·pj3는 하지 않았다.
- 상태: 구현과 아래 로컬 시험까지. 전체 검사·커밋·실기기 검수는 완료가 아니다.

## 결과

1. `local_sources.py`와 게이트웨이 장치 인증 API를 D-263의 `5add6ed3`에서 복구하고 Docker 레시피 대신 검증 커밋·트리·런타임·진입 파일·의존성 잠금에 결속했다. 다운로드 전후 현재 승인·직원 범위·세대·철회를 재확인하며 감사 기록은 덧붙이기만 한다.
2. `stdio_source.py`는 보호 폴더, 제한된 안전 압축 해제, 트리/잠금 해시, 준비 캐시 전체 파일 해시를 검사한다. Python은 해시 완전 잠금 wheel, Node는 integrity 잠금과 `npm ci --ignore-scripts`만 받는다. 네트워크/잠금/런타임 오류는 미실행이다. 직원/장치 자격은 실행 환경에 넣지 않는다.
3. `local-runner.py`의 `ProcessSession`이 기존 JSON-RPC·출력/큐 상한·기한·계약 대조·stderr 가림을 공유한다. Linux는 비root 계정·새 프로세스 그룹, Windows는 정지 생성→작업 개체 결속→재개·kill-on-close다. Windows는 포함 Python과 OpenSSL 3 EVP로 Ed25519를 검증한다.
4. Linux와 Windows 키트에 실행기 파일·공개 키·기존 pip 코드/라이선스를 포함했다. Windows 원클릭/조직 승인 설치기의 정확한 파일 목록과 시험 fixture도 함께 갱신했다. 프로세스 실행의 보호 폴더는 Linux 키트 관리 경로와 Windows 장치 비밀 폴더 아래의 sources다.
5. stdio 신청은 솔루션 runtime 큐잉·worker 재확인에서 거부하며 승인 미리보기는 기존 솔루션 runtime 주소를 선택하지 않는다. native HTTP의 기존 worker·중지·롤백·출구 프록시는 실제 호출처가 있어 유지했다. 공식 이미지 실행도 유지한다. 콘솔은 실행 방식/진입 파일/잠금 입력과 「엔드포인트 실행」을 제공한다.

## 변경 파일

- 엔드포인트: `local-runner.py`, `stdio_source.py`, `stdio_windows.py`, `managed-linux.py`, `managed-windows.py`, `windows-worker.ps1`, `windows-oneclick.ps1.in`, `windows-trust.ps1`.
- 게이트웨이: `local_jobs.py`, `local_sources.py`, `main.py`, `agent_service.py`, `core.py`, `release.py`, `agent_static/console.js`. 솔루션 실행기: `runtime/worker.py`.
- 시험: `endpoint_stdio_check.py`, `endpoint_source_api_check.py`, `dev73_review2_check.py`, Windows `test_endpoint_stdio.py`, `test_windows_kit.py`, `test_windows_oneclick.py`. 기존 문구 단언은 새 실행 위치 라벨로 갱신했고 다른 차단 이유를 성공으로 세지 않는다.
- 문서: D-299, ARCHITECTURE, CHANGELOG, 이 보고서·현황·백로그, `analysis/endpoint-stdio/` 원자 요구사항/시험 기록.

## 검증

정본 명령·종료 코드는 [test-results.json](../../analysis/endpoint-stdio/test-results.json), 코드 심볼·행·해시는 [requirements.json](../../analysis/endpoint-stdio/requirements.json)에 있다. Windows 로컬 Python 3.10, 일반 사용자 시험이다. 아래 수는 각 파일의 실행 수이며 생략은 통과 수에서 뺀다.

| 검사 | 결과 |
| --- | --- |
| 신규 `endpoint_stdio_check.py` | 14/14 통과: 준비·캐시·해시·환경·경로·기한·일반 프로세스 트리 정지·동일 계약/불일치·Python 패키지 진입 |
| 신규 `endpoint_source_api_check.py` | 8/8 통과: 장치 인증·범위·다운로드 중 철회/교체·상한·기록·검증 소스 결속·stdio runtime 큐잉/재확인 거부 |
| 신규 Windows `test_endpoint_stdio.py` | 4/4 통과: OpenSSL 3 실제 서명/변조, 작업 개체 충돌·자식 트리 정리·재접속 복구·키트 연결 |
| `dev73_rework_check.py` | 23 실행, 19 통과·Linux 4 생략 |
| `dev73_review2_check.py` | 5/5 통과. 새 라벨에 맞춰 기존 단언 갱신 후 재실행 |
| `dev73_integration_check.py` / `local_runner_usability_check.py` | 각각 7/7, 33/33 통과 |
| `kit_continuity_check.py` / `kit_simple_mode_check.py` | 각각 27 실행 중 25 통과·2 생략, 14/14 통과 |
| Windows `test_windows_oneclick.py` | 17 실행, 16 통과·1 생략. 새 파일과 pip fixture 반영 후 변조/추가 경로 검사 통과 |
| Windows `test_windows_kit.py` | 18 실행, 11 통과·6 실패·1 오류. 나머지는 PowerShell 실행 정책의 dot-source 거부. 키트 내려받기/런타임 포함 시험은 통과 |
| `kit_install_upfront_check.py` | 31 실행, 24 통과·3 실패·4 생략. Python 3.10의 TOML 확인 명령이 기존 Packages 명령 목록 단언과 다름. bootstrap.py는 기준 HEAD와 동일하며 이번 변경으로 숨기지 않음 |
| `local_run_manifest_check.py` / `runtime_rollback_reconcile_check.py` | cryptography 미설치로 시작 실패. 통과로 세지 않음 |
| `intake_one_click_ast_check.py` | 기존 Python 3.11+ `datetime.UTC` import를 로컬 3.10에서 지원하지 않아 시작 실패 |
| `open_endpoints.py` | 무인증 1/인증 필요 105/장치 자격 18 일치. 신규 소스 경로는 장치 enforcement 자격 필요 |
| Node 문법 / `console-state.test.mjs` | 통과 / 16/16 통과 |
| Python 변경 코드 12개 AST 파싱 / `deploy/check.py` | 통과 / 판본·변경 기록·제품 문서/배포 위생 통과 |
| `run_local_suite.py --inventory` | 고아 시험 0. 신규 두 시험도 기존 local-suite 자동 수집 |
| `python -m pyflakes` | 미설치. 요청의 「있으면」 조건에 따라 결과를 기록하고 다른 검사로 통과를 가장하지 않음 |
| Linux WSL 프로세스 시험 | `Wsl/Service/CreateInstance/E_ACCESSDENIED`로 실행 불가 |
| 실제 Gitea·DB·OSS MCP·모델/하네스·독립 효과 | 미실행 |
| 실기기 배포·PJ1·pj3 | 소유자 지시로 미실행 |

OpenSSL 시험은 호스트 Git의 OpenSSL 3 DLL을 같은 EVP 코드에 연결했다. 키트 임베디드 Python 배포의 DLL 자체와 SYSTEM 서비스 실행을 검증한 것은 아니다. 일반 자식 프로세스 시험은 MCP 실행 증거가 아니다. 새 MCP/mock 서버는 만들지 않았고 계약/인가 시험은 기존 DEV-73의 내부 대역 패턴을 사용했다.

## 실패·미완료·한계

- 커밋: 명시한 변경 경로만 `git add -- ...` 했으나 공용 worktree의 `.git/worktrees/stdio/index.lock` 생성이 `Permission denied`로 거부됐다. HEAD는 시작값 그대로이며 스테이징/커밋은 미완료다. 권한 우회·별도 Git 저장소·다른 브랜치 갱신은 하지 않았다. BRIEF는 미추적 상태 그대로다.
- 원격 기본 브랜치: `git ls-remote --symref origin HEAD`는 github.com:443 연결 실패. 원격 HEAD 재확인 불가를 기존 main 정보로 대체하지 않았다.
- Windows는 제한 토큰/별도 로컬 계정을 구현하지 않았다. 서비스 SYSTEM 권한이 남고 공유 Python 방화벽 차단은 heartbeat까지 끊어 자동 적용하지 않았다. Job Object는 계정/파일/네트워크 격리 수단이 아니다. `NtResumeProcess` 경로의 지원 대상 Windows/포함 Python 조합 검수도 남는다.
- Linux 프로세스 모드는 Popen의 신원/그룹 설정을 지원하는 Python 3.9 이상이 필요하다. 3.8은 설치를 느슨하게 실행하지 않고 거부한다. Linux의 그룹/보호 PID 시작시각 복구는 Windows에서 실행 검증하지 못했다. 새 세션으로 이탈하는 악성 자식까지 격리하는 경계가 아니며 procfs/신원/정지가 불명확하면 정지 영수증을 내지 않는다.
- 승인 커밋에 완전 잠금이 없으면 설치하지 않는다. MarkItDown의 실제 승인 커밋과 Windows/Linux별 wheel 잠금, ffmpeg 등 비Python 프로그램, 디스크 사용량은 확보/검증하지 않았다. 소스 디렉터리의 src 패키지 진입을 지원하지만 실제 MarkItDown 성공은 주장하지 않는다.
- Node는 신뢰된 node 실행 파일과 npm CLI를 서비스 설정에 제공해야 하며 자동 설치·TypeScript 빌드·npm lifecycle script는 지원하지 않는다. 대용량/동시 준비·실제 패키지 네트워크 설치·OS 강제 종료 경합은 후속이다.
- 호스트 네트워크를 사용한다. 기존 목적지 입증 정책을 완화하지 않아 URL 업무는 별도 정책 때문에 계속 막힐 수 있다. 프로세스 모드를 컨테이너와 동등하다고 표시하지 않는다.
- 위키 재생성/검사 결과와 패치 경로는 아래 후속 검증 기록에 남긴다. 코드 전용 PR에 위키 생성물을 넣지 않는 소유자 규칙에 따라 광범위 생성물은 별도 커밋 대상으로 삼지 않는다.

## 다음 작업·필요한 환경

DEV-83/D-299: 공용 Git 메타데이터를 쓸 수 있는 정상 환경에서 이 변경만 검토·커밋하고 기존 PR #68 작업 줄기에 통합한다. 지정 시험 PC에서 포함 Python/실제 승인 OSS의 해시 잠금·정상/음성/철회/복구, 실제 모델 도구 호출과 원장/효과를 확인한다. Windows 계정 축소와 전용 실행 파일 네트워크 규칙은 실제 파일 접근·서비스 통신을 함께 검증한 뒤 도입한다. 새 업무 권한이나 실사용 자격 값은 이 작업에서 요구·저장하지 않는다.


## 후속 검증 기록

- `refresh_generated.py`: 실패. map_threats·snapshot·보고서/결정 색인은 생성했으나 `build_enterprise_analysis.py --refresh-code-only`가 미커밋 `core.py`를 거부했다. `check_enterprise_analysis.py`도 실패했다. 정상 권한 환경에서 코드 커밋 후 재생성이 필요하다.
- 재생성 상태의 `check_wiki.py --ci-ignored-local-sources`는 errors 0, `check_trace.py`는 오류 0·경고 5였다. freshness는 9개 중 5개 낡음 경고다. 실제 배포·시험의 최신성 증명이 아니다.
- 코드 전용 PR의 위키 생성물 충돌 방지 규칙에 맞춰 이번 재생성만 변경한 기존 파일은 기준 상태로 되돌렸다. 수동 현황·백로그·작업 보고·새 요구사항/시험 정본은 보존했다. 생성물의 갱신 완료나 전체 위키 검사 통과를 주장하지 않는다.
- `endpoint-stdio.patch`: 기준 HEAD에 대한 코드·시험·설계·작업 기록의 패치다. BRIEF, 이 패치 자체, 광범위 위키 생성물은 제외한다. 원격 push·PR·병합은 하지 않았다.

## 2차 작업 — 2026-10-28

- 기준 `0c0bb1512865ff72a53fb120a7442ad7a17b0ff0`(1차와 PR #68 병합 후), 기존 `10/28-endpoint-stdio` 줄기를 유지했다. 시작 미커밋 항목은 BRIEF 하나다. 2차 지시대로 Git 메타데이터를 쓰거나 커밋·push·PR·배포·실기기 시험을 하지 않았다. 원격 HEAD 조회는 GitHub TCP 연결 실패다.
- 위 1차 결과 중 SYSTEM 실행·완전 잠금 부재·native HTTP runtime 유지 및 Windows 검증 완료 주장은 아래 현재 결과로 대체한다. 과거 시험 결과는 당시 이력이다.

### 변경

1. 직원 SID와 일치하는 WTS 토큰→기본 토큰 복제→CreateProcessAsUserW(정지 생성, Unicode 허용 목록 환경, 파이프 핸들 목록)→Job Object 결속→ResumeThread로 변경했다. 일치 로그온 세션이 없으면 미실행이며 다른 직원/SYSTEM Popen으로 우회하지 않는다. 실패 자원 정리·SID 불일치 대역 시험을 추가했다. Windows 소스/설치 의존성은 보호 프로그램 폴더 아래로 옮기고 등록 직원 RX만 준다. Linux 간편 모드는 이미 등록 직원 username/uid를 쓰고 execute_job이 작업 UID와 대조하므로 계정 변경은 불필요했다(정적 확인).
2. 도입 공급망 워커가 승인 커밋에서 플랫폼별 wheel을 해석·수신·해시 잠금한다. 소스와 확정 requirements/패키지 메타데이터를 Syft·Trivy 입력에 함께 넣고 SBOM 이름·판본 포함을 강제한다. 잠금 SHA-256과 대상 Python 조건을 서명 매니페스트에 넣고 같은 장치 인증 소스 API의 lock 질의로 제공한다. 다운로드 전후 승인을 다시 검사한다. 원본 커밋 트리 해시는 잠금을 덧붙여 바꾸지 않는다.
3. 솔루션 runtime 워커·이미지 검사기·레시피와 Dockerfile·compose 서비스/엔진 소켓/캐시·도입 실행/중지/되돌리기 API·콘솔 조작 및 그 전용 시험을 제거했다. MarkItDown 기본 실행은 같은 커밋의 src 패키지/빈 인자 stdio다. 원격 공급자 MCP는 URL 중계이며 `_internal_endpoint`의 runtime 예외도 제거했다. 과거 감사 사건의 파서/조회와 테이블은 보존한다. 기본 랩의 고정 실제 MCP 시험 서비스는 도입 runtime 워커가 아니다.
4. 예전 runtime 등록은 실행·허용 목적지 목록에서 제외하고 재승인 상태로 표시한다. 관리자 재검증은 과거 승인 commit을 고정하며 실패 재시도/lease 회수에서도 보존한다. 최종 계약은 기존 사람 승인 경로로만 등록한다. 과거 출구 프록시 설정을 최종 목적지 증거로 쓰지 않으므로 입증 없는 외부 전송 차단은 유지된다.
5. D-299 2차, D-114/120/132/155/180/264 대체 주석, 아키텍처·미배포 변경 기록·현황·백로그·원자 요구사항을 갱신했다. BRIEF의 D-158은 실제로 계약 오염 정규화 결정이므로 관련 실행 되돌리기 결정 D-180을 정정했다. D-158 본문은 바꾸지 않았다.

### 근거와 적용 범위

- Microsoft 공식 WTSQueryUserToken 문서는 SYSTEM/SE_TCB_NAME 요구와 핸들 회수를 명시한다. CreateProcessAsUserW 문서의 STARTUPINFOEX/핸들 목록을 적용했다. 실제 사용자 토큰 호출은 이 일반 사용자 환경에서 실행하지 않았다.
- [uv 0.9.5](https://github.com/astral-sh/uv/commit/d5f39331a73d5042e70ab770463dff632e20c127), MIT/Apache-2.0: 고정 CLI 소스의 플랫폼/Python/해시/마커 제거 옵션을 확인했다. 저장소 코드 실행 없이 교차 플랫폼 마커를 해석하기 위해 검사기 이미지에만 추가했다. pip는 기존 도구를 재사용한다. 최신 릴리스·취약점 전체 평가나 실제 이미지 빌드 증거는 아니다.
- [MarkItDown pyproject](https://github.com/microsoft/markitdown/blob/main/packages/markitdown-mcp/pyproject.toml)·공식 README/진입 파일은 stdio 기본값, 동일 저장소 내부 패키지, Hatch 버전 상수를 확인하는 참고다. 현재 main 웹 읽기이며 실제 승인 commit 확보·배포 증거로 세지 않는다. 구현은 도입 워커가 받은 고정 commit의 파일만 읽는다.
- 공개 ToolHive 스킬/OSS를 재탐색하고 기존 D-299의 고정 ToolHive 비교를 재사용했다. 컨테이너 기동 스킬은 기존 장치별 승인/실행 경로를 대체하지 않아 실행·설치하지 않았다.

### 남은 한계·운영 이행

- 실제 SYSTEM CreateProcessAsUserW·세션 간 파이프 접근·준비 폴더 ACL·포함 Python·Job 복구와 Linux UID 실행 효과는 지정 PC에서 검수해야 한다. Windows 일반 사용자에서 기존 직접 Popen 수명 시험을 서비스 토큰 시험으로 통과 처리하지 않고 생략했다.
- 현재 새 Python 잠금은 Windows x86_64/3.13(키트 3.13.16), Linux x86_64/3.12/glibc>=2.28이다. 다른 Python/OS, 동적 의존성, 직접 URL, 소스 빌드, Node 런타임 자동 설치는 지원하지 않으며 실패한다. 실제 MarkItDown wheel 해석·네트워크 설치·ffmpeg 등 외부 프로그램은 미실행이다.
- wheel 미러는 잠금과 달리 저장·보존·회수·용량·오프라인 설치까지 필요하므로 구현을 보류했다. 잠금만 검사 보고 볼륨에 보관하고 wheel은 해시로 다시 받는다. 오프라인 PC/배포물 소실은 준비 실패다. 호스트 네트워크·직원 권한의 별도 격리를 주장하지 않는다.
- compose 파일에서 서비스를 빼는 것만으로 이미 떠 있는 고아 워커/동적 MCP/프록시/망이 지워지지는 않는다. 운영자는 이전 판본에서 해당 배치의 실행을 중지하고 `mcpgw.runtime`·`mcpgw.intake` 표식 및 DB 이력을 대조해 자기 배치 자원만 회수해야 한다. 신규 코드는 이를 자동 제거하거나 다른 랩을 만지지 않는다. 이 작업에서는 배포·자원 정리를 실행하지 않았다.
- 전체 로컬 스위트 최초 실행은 파일 단위 통과 72·실패 62·생략 18이다. 환경 미설치(httpx/pydantic/cryptography/pglast 등), Python 3.10의 datetime.UTC, 기존 설치 명령 단언, dirty 코드의 위협 매핑 해시 불일치를 포함한다. 이 변경으로 드러난 과거 runtime 분류 단언은 수정 후 별도 재검사했다. 전체 스위트 통과로 보고하지 않는다.

최종 명령·종료 코드·개별 통과/생략·위키 검사 결과는 [2차 검증 정본](../../analysis/endpoint-stdio/test-results-round2.json)에 기록한다.


### 2차 최종 로컬 검증

| 검사 | 결과 |
| --- | --- |
| 소스 프로세스·장치 API·잠금 생성·Windows ctypes 핵심 | 39통과·Windows 직원 토큰 실제 수명 2생략. 준비/잠금 변조·SID 불일치·세션 부재·정지 생성→결속→재개·결속 실패 정리 포함 |
| 기존 관련 Python 선택 검사 | 파일별 명령/통과/생략을 검증 JSON에 보존. 실행 건수는 공유 fixture로 중복될 수 있어 고유 사례 수로 합산하지 않음 |
| 콘솔 상태·도입 승인·승인 목록 Node | 32/32 통과, 문법 검사 통과 |
| API 인증 경계·스키마·감사 라벨·배포 위생 | 통과 |
| 변경 Python AST·셸 문법·git diff --check | 통과 |
| pyflakes | 미설치로 실행 실패. AST 검사를 pyflakes 통과로 바꾸지 않음 |
| 도입 승인 현대 Python fixture | runtime 대신 local 명세를 쓰도록 고침. 실제 앱/AST 실행은 pydantic 미설치와 Python 3.10 datetime.UTC로 시작 실패 |
| 생성물 재생성·위키·기업 분석 | 실패. 고정 독립 검토의 삭제된 runtime 코드 후보와 미커밋 코드 해시가 불일치한다. 체크를 완화하거나 옛 검토 해시를 현재 검증으로 덮어쓰지 않음 |
| ID 추적·신선도 | ID 오류 0·경고 5, 신선도는 낡음 5/9 경고. 현재 실기기 증거를 뜻하지 않음 |
| compose 해석·스캐너 이미지·실제 OSS/기기 | Docker CLI 부재 또는 소유자 금지 범위로 미실행 |

공급망 영향 조회는 제거한 실행 세대 대신 등록 버전=검사 소스 커밋을 확인하여 엔드포인트 소스도 판정한다. 과거 원본/독립 검토의 Markdown 링크는 삭제 전 시작 커밋에 고정하고 역사 자료임을 표시했다. 구조화된 고정 독립 매핑은 재검토 대상 그대로 보존하므로 전체 위키 검증은 미완료다. 최종 제품/시험 변경은 커밋 없이 이 작업 트리에만 있다.
