# 2026-10-23 공식 MCP 격리 실행 기본값 제안

- 작업자: Claude Code (Sonnet 5.5, 서브에이전트)
- 코드 기준: `origin/main` `e30be96`, 브랜치 `10/23-local-run-presets`. 변경 파일은 아래 「결과」.
- 시작 근거: 10-23 실사용 시험 보고(`2026-10-23-real-usage-local-mcp.md`)의 「다음 작업」 첫 항목, D-206. 소유자 원칙 "솔루션이 채우고 사람은 승인만"
- 해결할 문제와 완료 조건: stdio 공식 MCP 승인 때 관리자가 이미지·실행 인자·폴더·환경 변수를 손으로 넣지 않게 한다. 기본값은 제안일 뿐 서버 검증과 승인 범위는 그대로다.

## 결과

- `intake_proposal.LOCAL_RUN_PRESETS`와 `local_run_preset(row)`: 공식 저장소(`modelcontextprotocol/servers`)의 `src/filesystem`·`memory`·`sequentialthinking`·`git`·`time`만 제안. 다른 저장소·모르는 경로는 빈 제안.
- `approval-preview` 응답에 `local_run_preset` 추가. `askLocalRun`은 저장된 실행 지정이 없을 때만 이 값으로 입력란을 미리 채운다.
- 승인 창에 「환경 변수 (이름=값, 쉼표 구분)」 입력란을 추가했다. 이전에는 `env: {}`가 코드에 고정돼 화면만으로는 memory의 `MEMORY_FILE_PATH`를 넣을 수 없었다. 저장된 값도 이 칸에 보인다.
- 값은 라벨과 입력란에 그대로 보인다(memory의 `mcp-memory:rw` 포함). 설명 문단은 넣지 않았다.
- 서버 검증(`LocalRunSpec`, `manifest_errors`, 허용 이미지 저장소, digest 고정, 서명)은 바꾸지 않았다.
- 근거: [analysis/local-run-presets-1023](../../analysis/local-run-presets-1023/README.md) — README 5개의 upstream commit `51b6382a…`, 해시, 행 번호, 우리 쪽 차이.
- 변경 파일: `full_stack_lab/gateway/app/intake_proposal.py`, `agent_service.py`, `agent_static/console.js`, `full_stack_lab/tests/local_run_presets_check.py`(신규), `docs/ai/DECISIONS.md`(D-206), 위키 분석·보고서, 코드 해시 갱신 산출물.
- 구현·시험 단계다. 배포·기기 활성화·PJ1 실측은 하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `node --check console.js` | 통과 | 콘솔 출력 |
| 새 시험 | `python full_stack_lab/tests/local_run_presets_check.py` (6건: 선택·빈 제안·복사본·표 전체가 `LocalRunSpec`+`manifest_errors` 통과·변형 입력 거부·배선) | 통과 | 콘솔 출력 |
| 기존 시험 | `node --test full_stack_lab/tests/console-state.test.mjs` 15건, `local_runner_usability_check.py` 28건, `intake_one_click_ast_check.py` 12건 | 통과 | 콘솔 출력 |
| 위키 CI | 위 4단계와 `check_wiki`·`check_trace`·`check_enterprise_analysis`·`test_enterprise_code_refresh`·`test_console` | 아래 「위키 검사」 | 콘솔 출력 |
| 프로토콜·실제 모델·하네스 | — | 미실행 | |
| upstream 효과 | — | 미확인 | |
| 배포·정책 해시 | — | 미확인 | |

## 위키 검사

`map_threats.py`와 `build_enterprise_analysis.py --refresh-code-only`로 재생성한 뒤(코드 해시만 갱신) 2026-10-23 로컬 Windows·Python 3.12에서 실행:
`check_wiki.py --ci-ignored-local-sources` 오류 0(무시된 로컬 원본 부재 경고만), `check_trace.py --self-test` 통과, `check_trace.py` 오류 0·경고 6,
`check_enterprise_analysis.py` 오류 0·경고 0, `test_enterprise_code_refresh.py` 3건 통과, `PYTHONUTF8=1 test_console.py` 32건 통과.

## 실패·미완료·한계

- 폴더 이름(`mcp-docs`·`mcp-repo`·`mcp-memory`)은 PC 홈의 관례 이름이다. 실제 폴더와 다르면 관리자가 고친다. 폴더가 없을 때의 실패 문구는 확인하지 못했다.
- memory 파일은 README의 `.jsonl` 예시와 달리 PJ1에서 통과한 `memory.json`을 쓴다. 확장자 영향은 문서로 확인하지 못했다.
- git은 읽기 전용 마운트라 쓰기 도구는 실패한다. 읽기 전용에서의 `git status`·소유자/`safe.directory` 동작은 미확인이다.
- `mcp/*` 이미지의 실제 digest 고정과 `initialize`·`tools/list` 통과는 이번 작업에서 확인하지 않았다(Docker Hub·기기 접속 없음).
- 환경 변수 값에 쉼표가 있으면 입력란에서 나뉜다(허용 이름·값 범위 안에서는 해당 없음).
- `pac_boundary_check`·`adversarial_check`처럼 이미지·운영 DB가 필요한 시험은 돌리지 않았다.

## 다음 작업

- 기기 배포 후 PJ1에서 승인 창이 5종에 대해 미리 채워지는지, 그대로 승인했을 때 도구 목록이 나오는지 확인한다(리더).
- git 읽기 전용 동작이 문제면 표를 한 줄 고친다.

## 사용자에게 필요한 입력

없음
