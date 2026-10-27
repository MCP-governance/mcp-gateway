# 2026-10-27 승인 소스의 게이트웨이 배포·Linux PC 빌드

- 작업자: Codex
- 코드 기준: `7d49a873776eacaec180f5445138b76f7e4be1a7`, `10/27-kit-source-linux`. 시작 때 추적 파일은 깨끗했고 지시 파일과 실행 로그만 미추적이었다.
- 시작 근거: `BRIEF-kit-source.md`, DEV-73, D-262. 결정 D-263.
- 완료 조건: 장치 자격으로 승인 소스를 받고 트리 해시·고정 레시피를 확인해 PC에서 빌드·격리 실행; 상태 목록·재준비; 반례 시험. Windows 파일 변경·스택 기동·push·병합 금지.

## 결과

- `source` 선택 서명 매니페스트와 검증기를 추가했다. image와 동시 지정, 형식 위반, 미고정 FROM·원격 ADD를 거절한다. 관리자 입력은 레시피 본문을 받지 않고 저장소의 고정 파일을 찾는다. `markitdown-mcp`에 stdio 인자를 명시했다.
- 장치 다운로드는 기존 `authorized`와 직원 사용 대상 검사를 통과해야 한다. 관찰 전에는 관찰 장치만 허용한다. 전체 소스 수신 뒤 승인·정책 세대를 재확인하고 `local-source-download`를 기록한다. Gitea 관리 자격은 솔루션 안에 머문다. 게이트웨이의 망·자격은 기존 것을 쓰고 레시피 읽기 전용 마운트만 추가했다.
- 관리자 지정 때 검증된 내부 사본을 먼저 게시해 최초 PC 관찰의 순환 의존을 해소했다. 계약·승인을 자동으로 만들지는 않는다. 신청 커밋·출처·기존 evidence가 바뀌면 저장을 거절한다.
- Linux 실행기와 사전 준비가 같은 소스 빌드 함수를 쓴다. 트리 해시가 다르면 빌드하지 않는다. 안전한 tar 필터를 요구하며 태그·전체 라벨을 확인한 이미지 ID만 기존 격리 인자로 실행한다. 준비 상태와 `p` 재준비는 기존 상태 파일·소켓을 재사용한다.
- [원자 요구사항·근거](../../analysis/kit-source-1027/README.md), [D-263](../../../../docs/ai/decisions/D-251-300.md). 결과 요약·변경 파일·명령은 저장소 루트 `BRIEF-kit-source.result.md`에도 남긴다.

## 검증

로컬 Windows의 Python 3.10.5에서 `python -X utf8`로 실행했다. DB·HTTP·엔진은 기존 자체 시험 형식의 대역이며 실제 MCP 실행 증거가 아니다.

| 확인 종류 | 명령 | 결과 |
| --- | --- | --- |
| 새 소스 경로 | `python -X utf8 full_stack_lab/tests/local_source_check.py` | 26건 중 25 통과, tar data filter 실제 압축 해제 1 생략 |
| 실행기 회귀 | `python -X utf8 full_stack_lab/tests/dev73_rework_check.py` | 23건 중 19 통과, Linux 전용 4 생략 |
| 준비·진단·제어 | `python -X utf8 full_stack_lab/tests/local_runner_usability_check.py` | 31 통과 |
| 설치·사전 준비 | `python -X utf8 full_stack_lab/tests/kit_install_upfront_check.py` | 31건 중 27 통과, 플랫폼 4 생략 |
| 키트 연속성 | `python -X utf8 full_stack_lab/tests/kit_continuity_check.py` | 25건 중 23 통과, Linux 2 생략 |
| 상태 화면 | `python -X utf8 full_stack_lab/tests/kit_screen_check.py` | 16 통과 |
| 기존 소스 다운로드 | `python -X utf8 full_stack_lab/tests/approved_mcp_download_check.py` | 22 통과 |
| 인증 경계 | `python -X utf8 full_stack_lab/tests/open_endpoints.py` | 무인증 1·인증 103, 새 경로는 장치 자격 |
| JS | `node --check full_stack_lab/gateway/app/agent_static/console.js`; `node --test full_stack_lab/tests/console-state.test.mjs` | 구문 및 16 통과 |
| 제품 위생 | `python -X utf8 deploy/check.py` | 통과 |
| Python 정적 | 변경 Python 파일 10개에 `pyflakes.api.checkPath` | 통과; 기존 가상환경의 순수 Python 검사기만 직접 import |
| 위키·추적 | `check_wiki.py --ci-ignored-local-sources`; `check_trace.py` | 오류 0; 추적 경고 5 |
| 생성물 재생성 | `refresh_generated.py` | 실패: 미커밋 compose의 코드 위치 고정 불가·기업 분석 해시 불일치 |

Python 174건 중 163 통과·11 생략, JavaScript 16 통과다. 실행 로그는 `research/collaboration-console/runtime/kit-source-validation/`에 보존했다(로컬 전용·Git 제외). 신규 시험은 `run_local_suite.py --inventory`의 local-suite에 포함되며 고아 시험은 0이다. 위키 검사·추적은 재생성 시점에서 오류 0이었다. 코드 줄기에서 위키 생성물을 제외하라는 소유자 규칙에 따라 생성된 6개 파일은 기준 커밋의 내용으로 되돌렸다. 결정 색인 생성 명령은 실행했으며 통합 커밋에서 다시 생성해야 한다.

## 실패·미완료·한계

- 커밋 불가: `git add`가 워크트리 Git 관리 디렉터리의 `index.lock` 생성에서 `Permission denied`로 실패했다. 허용된 작업 폴더 밖 Git 디렉터리를 변경할 권한은 없으며, 권한 우회나 별도 Git 저장소 생성은 하지 않았다. 생성 커밋은 없다. 원격 HEAD 조회는 GitHub 연결 실패다.
- 기업 분석 갱신기는 미커밋 `full_stack_lab/compose.yaml`의 판본 고정을 거절했다. 해시 검사는 5건 불일치이며 변경된 compose와 이번에 변경하지 않은 기존 `console.sh` 포인터도 포함한다. 커밋 뒤 통합 시점에 생성물을 갱신하고 재검사해야 하므로 위키 전체 검증 완료로 보지 않는다. 신선도 검사에는 낡음 6건이 남았다.
- WSL 접근 거부, 기존 CPython 3.12 가상환경의 인터프리터 부재/바이너리 의존성 불일치로 실환경 시험과 전체 게이트웨이 import 시험을 실행하지 못했다. `local_run_manifest_check.py`, `local_run_presets_check.py`, `local_job_control_check.py` 등 의존성이 필요한 시험은 미실행이다. 실제 tar data filter 시험 1건은 Python 보안 업데이트 환경에서 다시 실행해야 한다.
- 실제 Gitea·PostgreSQL 경쟁·Linux Docker/Podman·소켓·하네스·브라우저 조작은 미실행이며 배포하지 않았다. 소스의 최초 관찰만 30분 준비 기한과 프록시 대기를 확보하고 일반 호출의 실행 기한은 유지한다. 빌드가 로그인 기한을 넘기면 로그인 갱신 뒤 미리보기를 다시 열어야 한다.
- 고정 레시피가 없는 저장소에는 소스 빌드를 제공하지 않는다. 기본 이미지·소스 고정은 전이 의존성의 재현성까지 보증하지 않는다. 빌드 중 패키지 수신은 허용될 수 있으며 실행 중 네트워크 없음과 구분한다. 엔진 클라이언트 종료만으로 원격 빌더 잔여 작업의 취소를 증명하지 않는다.
- 기존 패키지 시험의 가짜 호스트가 Python 3.10에서 TOML 가용성 검사를 패키지 조작으로 잘못 세던 부분을 고쳐 동일 조건으로 검사했다. 제품 설치 코드는 바꾸지 않았다.

## 다음 작업

DEV-73: 쓰기 가능한 원래 Git 워크트리에서 패치를 검토·커밋하고, 동일 레시피를 게이트웨이·콘솔에 배포한다. 지정 Linux PC의 실제 키트에서 승인→사전 준비→실제 MCP 도구 호출→승인 철회 뒤 차단·정지 영수증을 확인한다. 배포 묶음과 실제 tar 필터는 GitHub CI에서 확인한다. 통합 시 생성물을 한 번 재생성한다.

## 사용자에게 필요한 입력

새 업무 권한·실사용 데이터·자격증명은 필요하지 않다. 커밋을 위해 원래 Git 관리 디렉터리에 쓸 수 있는 실행 환경이 필요하다. 실제 검증은 지정 시험 PC와 솔루션 기기의 기존 절차를 따른다.
