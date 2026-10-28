# npm Codex 경로·실행 장애·토큰 갱신 실패 수정 — 2026-10-28

- 작업자: Codex
- 코드 기준: `10/27-bugfix-round1`, 시작·최종 HEAD `5d7b1937c81e666cb78cd86893f18bd0b0b07ab6`. 같은 키트 작업 줄기이므로 새 브랜치·PR을 만들지 않았다. 원격 HEAD는 GitHub 443 연결 실패로 확인하지 못했다.
- 시작 근거: `BRIEF-fix4.md`, `BRIEF-fix.md`, `R5-REVIEW.md`, D-273~D-275. 제공된 검토와 이번 실행 증거를 구분한다.
- 완료 조건: 세 결함의 수정 전 실패·수정 후 통과, D-273 미탐 반례 유지, 관련 시험·정적 검사와 결정·현황·결과 파일 기록, 작업 단위 커밋. **코드·반례 검증은 완료했으나 커밋은 권한 오류로 미완료다.**
- 보존: 시작부터 있던 current·backlog의 변경을 유지하고 새 항목만 추가했다. `2026-10-28-fix3-entry-auth.md`와 다른 미추적 파일은 수정·스테이징하지 않았다. push·병합·솔루션 기동·위키 일괄 재생성은 하지 않았다.

## 결과

| 요구 | 기준 코드의 원인 | 변경·시험 위치 | 수정 결과 |
| --- | --- | --- | --- |
| npm Codex 오탐 | `managed-linux.py:480`은 npm 진입 경로만 저장, `agent.py:711`은 native 자식과 대조 실패 | `managed-linux.py:65`, `:514`, `managed-macos.py:330`, `agent.py:718`, `linux_kit_reinstall_check.py:169`, `:192`, `endpoint_collector_check.py:144` | 정확한 설치 진입 파일 기준으로 Node 모듈 해석기가 고른 플랫폼 패키지 실행 파일 하나를 기존 목록에 추가한다. 플랫폼 패키지 미발견 때만 자체 vendor를 확인한다. Node 진입 링크는 실경로를 확인한다(D-276). |
| 권한 오류를 인증 실패로 표시 | `bootstrap.py:643`·`:672`는 login-shell 경로를 로그인 요구로 검색 | `bootstrap.py:643`, `:676`, `linux_kit_reinstall_check.py:253`, `:262` | 실행 장애·실행 권한 안내를 표시하고 `model_signed_in`을 보존한다. 일반 경로와 실제 로그인 요구를 구분한다(D-277). |
| Codex 토큰 갱신 실패 누락 | `bootstrap.py:643`은 공식 문구에 일치하지 않아 자격 파일의 존재값 True를 유지 | `bootstrap.py:646`, `:678`, `linux_kit_reinstall_check.py:273` | 공식 갱신 실패를 인증 실패로 분류해 False·로그인 필요·Codex 로그인 명령을 일치시킨다(D-278). |

정책·신원·계약 승인·감사 기록·토큰 전달은 변경하지 않았다. npm 해석은 래퍼를 실행하지 않는 Node 표준 API 호출이다. `NODE_OPTIONS`·`NODE_PATH`는 제거하며 파일 누락·Node 부재·실행 오류·5초 시간 초과에는 새 제외 경로를 추가하지 않는다. 다른 위치의 동명 파일·패키지 하위 서버 전체를 제외하지 않는다.

## 공식 근거

OpenAI Codex `rust-v0.160.0`, commit `a956835d020762cb2b570053af06f643a11c0ecc`, Apache-2.0. 2026-10-28 공식 릴리스·본문·라이선스를 확인했다. 현재 유지보수 상태 전체를 평가한 조사나 새로운 라이브러리 도입은 아니다.

- [codex.js](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-cli/bin/codex.js#L73): `findCodexExecutable`의 플랫폼 매핑·require.resolve·vendor 대안·자식 실행. 적용 범위는 설치 때의 경로 해석뿐이다.
- [manager.rs](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/login/src/auth/manager.rs#L193): `REFRESH_TOKEN_*_MESSAGE`와 `classify_refresh_token_failure`. 만료·재사용·철회·기타 영구 갱신 실패·계정 불일치 원문 5종을 단위 입력으로 쓴다.
- [라이선스](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/LICENSE)·[릴리스](https://github.com/openai/codex/releases/tag/rust-v0.160.0). 외부 스킬·설치 스크립트를 실행하거나 의존성을 추가하지 않았다.

## 검증

Windows Python 3.10·설치된 Node에서 `python -B -X utf8`로 실행했다. 합성 파일·프로세스·모델 응답과 OS/API 대역을 사용하는 단위 시험이다. 실제 설치/점검 함수·파일 입출력·JSON·Node 해석·수집기 분류를 거치되 native 파일은 실행하지 않는다. 실제 OSS MCP·기기·모델 호출 증거가 아니다. HOME·CODEX_HOME은 임시 폴더다.

| 확인 | 명령·범위 | 결과 |
| --- | --- | --- |
| 수정 전후 반례 | `compare_baseline.py`가 `git show 5d7b1937` 소스를 메모리에 적용 | 기준 3시험에서 7실패(native 1·실행 오류 1·갱신 문구 5), 현재 모두 통과. 진입 링크도 별도 시험에서 기준 실패·현재 통과. 비교 도구 초안은 Windows grp 대역 누락으로 중단했으며 수정 후 결과만 집계했다. |
| 관련 Python 7스위트 | `endpoint_collector_check` 16, `kit_simple_mode_check` 13, `linux_kit_reinstall_check` 37, `windows_kit_reinstall_check` 10, `kit_screen_check` 19, `kit_continuity_check` 25, `macos_kit_check` 11 | 총 131건 중 **129통과·POSIX 2생략**. 중첩 filesystem 서버·동명 Python 및 initialize 응답 우선 판정 유지. |
| Node 회귀 | `node --test full_stack_lab/tests/kit-download-console.test.mjs` | 4통과 |
| 정적 검사 | 변경 Python 6파일 `compile`, `deploy/check.py`, `git diff --check` | 통과 |
| 결정·추적 | `split_decisions.py index`, `split_decisions.py check`, `check_trace.py` | 색인 갱신·분할 검사 통과, 추적 오류 0·경고 5 |
| 위키 전체 검사 | `check_wiki.py` | 실패 58: 원문 누락 29·매핑 해시 불일치 29. 이전 fix3 보고와 같은 수이며 일괄 재생성 금지 지시를 유지한다. |
| 분석 전체 검사 | `check_enterprise_analysis.py` | 코드/연동 해시 불일치 54로 실패. 이전 보고와 같은 수이며 통과로 세지 않는다. |
| 정밀 린트·자체 시험 | `pyflakes`, `agent.py --self-check`, `bootstrap.py --self-check` | 각각 pyflakes 미설치·TOML 파서 미설치·Windows grp 부재로 실행 불가/중단. 기기 이미지에서 확인 필요. |
| 실제 모델·MCP·배포 | 미실행 | 로컬 스택을 기동하지 않았다. |

`check_freshness.py`는 9점검 중 4건의 낡음 경고(백로그·START_HERE 기준일, 시트 사본, 보고서 색인)를 냈다. 새 보고서의 색인은 일괄 생성물 갱신 금지 지시에 따라 재생성하지 않았다. 결정 색인과 현황의 D-278 참조는 최신으로 확인했다.

로그·비교 도구는 Git 제외 `research/collaboration-console/runtime/fix4-checks/`에 있다. `baseline-regressions.log`·`fixed-regressions.log`·`baseline-symlink.log`·`fixed-symlink.log`, Python 스위트와 전체 위키 검사 로그를 보존했다. Node·정적 검사·결정 검사는 이번 명령 출력으로 확인했다.

## 실패·미완료·한계

- 명시한 코드·시험 파일만 `git add`했으나 `.git/worktrees/r1-fix/index.lock` 생성이 `Permission denied`로 실패했다. 인덱스는 비어 있고 새 커밋 해시는 없다. 권한·ACL·잠금 파일을 바꾸거나 다른 Git 경로로 우회하지 않았다.
- 실제 설치 반영에는 키트 재설치가 필요하다. 확인된 경로의 파일 교체·동일 사용자 공격·명령줄 위조를 막는 무결성 증명이 아니다. 미지원 래퍼·해석 불가 경로는 추정으로 제외하지 않으므로 오탐 가능성이 남는다.
- 실행 장애 때 보존한 로그인 값은 인증 성공을 새로 확인한 값이 아니다. 권한 복구 후 모델 점검이 필요하다. 오류 분류는 기존 마지막 줄 160자와 확인한 공식 문구에 한정된다.
- 실제 Node 경로 해석은 Windows에서 실행했다. Linux/macOS 실설치·OS 관찰·실제 플랫폼 패키지·시험 PC 모델 재로그인은 별도 검증이 필요하다.

## 다음 작업

S4 후속: Git 쓰기 권한이 정상인 환경에서 이번 변경만 커밋하고 지원 기기 이미지의 생략·중단 검사를 수행한다. 배포 후 지정 시험 PC에서 npm Codex의 프롬프트·로그인 소켓 오탐 0, 별도 실제 OSS MCP 탐지 유지, 실행 권한 장애 시 인증 값 보존, 실제 인증 실패와 재로그인 후 정상 응답을 확인한다.

## 사용자에게 필요한 입력

코드·단위 검증을 위한 추가 입력은 없다. 미완료 커밋에는 공통 Git 저장소의 정상 쓰기 권한이 필요하다. 실기기 검증에는 지정 시험 PC와 지원 이미지가 필요하며 자격증명 값은 기록하지 않는다.
