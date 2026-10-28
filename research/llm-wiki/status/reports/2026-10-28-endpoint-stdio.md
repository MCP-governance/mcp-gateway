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
