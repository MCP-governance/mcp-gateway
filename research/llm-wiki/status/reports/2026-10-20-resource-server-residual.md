# 2026-10-20 DEV-08 자원 서버 잔존 재접근

- 작업자: Codex sol
- 코드 기준: `10/20-resource-server-residual`, 시작 commit `bac155a8b78222fc878ff642ea1aa177ddb82fba`, 시작 작업 트리 clean, 결과 미커밋. 원격 HEAD 재조회는 github.com:443 연결 실패. 커밋·푸시 없음.
- 변경 파일: `full_stack_lab/gateway/app/idp.py`·`decommission.py`, 새 `tests/resource_residual_check.py`·`resource_residual_pg_check.py`, 기존 `tests/termination_flow.py` 설명만, `docs/ai/TERMINATION_MODEL.md`·`DECISIONS.md`, DEV-08 상태 칸, [분석 정본](../../analysis/resource-residual/README.md)·JSON/검사 기록, 재생성 `catalogs/threats.json`.
- 시작 근거: DEV-08·G07.03, CISC-W'26 종료 모델 C1~C4·T1~T3, D-146·D-123·D-154. 새 논문 방법론이나 자체 MCP 구현을 도입하지 않았다.
- 완료 조건: 발급자 introspection·캐시·서버 보유 하위 자격·풀·실행기의 재접근 경계를 연결하고 확인된 공백만 보완한다. 실제 기기 검수와 로컬 구현을 구분한다.

## 결과

1. 갱신 토큰 introspection에서 현재 계정이 없거나 중지됐거나 관리형 인증으로 전환됐거나 로컬 발급이 OIDC로 대체됐으면 inactive를 반환한다. 기존 발급·갱신·철회 순서는 유지했다.
2. `client-token`·`refresh-token`에도 기존 `resource-rejection`을 상태 증거로 연결했다. 자원 서버가 기존 토큰을 수락하면 inactive introspection이 있어도 C3 미충족/T2다. 수정 전 새 시험에서 수락 무시 T1 두 건·직접 거부 무시 T3 한 건을 재현했고 수정 후 통과했다.
3. 발급자 응답 캐시는 없음(TTL 0), 기존 `no-store` 유지. 기존 업스트림 풀 폐기·세션 종료·실행기 STOPPING/제거 재시도를 재사용한다. 외부 자원 서버의 자체 인가 캐시를 강제 갱신하는 구현을 추가하지 않았다.
4. 새 PostgreSQL 시험은 전용 DB 이름 검사·`isolated_disposal()`·일회용 키·전용 Gitea PAT와 `finally` 정리를 사용한다. 기존 Gitea MCP 컨테이너의 토큰은 폐기하지 않는다. 실제 PostgreSQL·Gitea API 절차는 작성만 했다.

구현·문서·로컬 검사만 완료했다. 활성화·솔루션 배포·PJ1 하네스·실제 SDK/외부 JWT 자원 서버·실행기 제거 시험은 미실행이다.
신규 정책 ID·DB 변경·의존성·API 라우트·제품 화면 변경은 없다. `status/current.md`는 지시대로 수정하지 않았다.

## 검증

실행 시각·명령·종료 코드·stdout/stderr는 [checks.json](../../analysis/resource-residual/checks.json)에 남겼다. 로컬 Python은 3.10.5이며 기존 인접 가상환경의 pyflakes 4.0.3만 읽기 전용으로 재사용했다. 패키지를 설치하거나 다른 작업 트리를 수정하지 않았다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 신규 순수/대역 | `python -B -X utf8 full_stack_lab/tests/resource_residual_check.py -v`, 10-20 | 13/13 통과. 인증/DB 응답·실행기 엔진은 대역 | checks.json `resource_residual_unit` |
| 기존 세션 시험 | `python -B -X utf8 full_stack_lab/tests/session_termination_check.py`, 10-20 | 실행 실패: Python 3.10의 `datetime.UTC` import 불가, 시험 본문 미실행 | checks.json `existing_session_termination` |
| Python 구문 | `python -m py_compile` 제품 2개·신규 시험 2개·기존 종료 시험, 10-20 | 통과 | checks.json `py_compile` |
| CI 범위 pyflakes 원형 | full_stack_lab에서 gateway/app·tests·supply_chain·endpoint-agent·field/pc 대상 전개 후 `python -m pyflakes`, 10-20 | Python 3.10에서 기존 미변경 파일 5곳의 3.11 내장 이름 경고. 새 경고 0 | checks.json `pyflakes_ci_raw_py310` |
| CI 범위 pyflakes 내장 이름 보정 | 같은 범위, `PYFLAKES_BUILTINS=BaseExceptionGroup,ExceptionGroup`, 10-20 | 경고 0. 3.11+ 실행 검증은 아님 | checks.json `pyflakes_ci_py311_builtin_names` |
| 화면 구문·기존 회귀 | `node --check full_stack_lab/gateway/app/agent_static/console.js`, `node --test full_stack_lab/tests/console-state.test.mjs`, 10-20 | 구문 통과·15/15 통과 | checks.json `console_syntax`·`console_state` |
| 라우트 인증 | `python full_stack_lab/tests/open_endpoints.py`, 10-20 | 무인증 1개 문서 일치, 인증 필요 84개 검사 통과 | checks.json `open_endpoints` |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py`, 10-20 | 24개 매핑 재생성 | checks.json `map_threats` |
| 기존 종료 시험 보존 | HEAD/현재 실행 AST 대조, 10-20 | 모듈 설명 외 동일, 기존 assert/기대값 변경 없음 | checks.json `existing_termination_flow_executable_ast_unchanged` |
| 위키·형식 | `check_wiki.py --ci-ignored-local-sources`, `git diff --check`, UTF-8/BOM/LF 검사, 10-20 | 오류 0, ignored 원본 누락 경고 119개. 공백·UTF-8/BOM/LF 검사 통과 | [final-checks.json](../../analysis/resource-residual/final-checks.json) |
| PostgreSQL·Gitea 보호 자원 | `tests/termination_dispatch_lab.sh run resource_residual_pg_check.py` | 미실행 | 기기 실행 필요 |
| 실제 모델·하네스 | PJ1 관리형 하네스 | 미실행 | 없음 |
| upstream 효과·배포 | 실제 MCP·실행기/외부 자원 서버·`field up` | 미실행/미확인 | 없음 |

위협 매핑의 `reservation_effect_check.py` raw hash 두 곳은 기존 CRLF의 관찰값 재생성이며 정규화 hash·실행 코드는 바뀌지 않았다.

## 기존 시험 변경 필요

기대값 변경 필요 없음. `termination_flow.py`는 D-156 보완 시험 위치를 모듈 설명에만 추가했고 실행 AST 전체를 HEAD와 대조했다.
기존 `session_termination_check.py`의 로컬 import 실패는 Python 3.11+ 환경에서 재실행할 사항이며 시험 소스는 수정하지 않았다.

## 실패·미완료·한계

- 로컬 표준 Python에는 게이트웨이 의존성 및 `datetime.UTC`가 없어 게이트웨이 전체 import/실제 PG 시험을 실행하지 않았다. 원형 pyflakes의 기존 5개 경고도 이 Python 판본 차이다.
- 서명 검증만 하는 자원 서버의 비교는 기존 E1 함수의 로컬 실행 예정이다. 실제 외부 자원 서버 실험으로 승격하지 않는다. 새 PAT는 실제 Gitea 보호 자원에 제시할 합성 고지 fixture이며 MCP 서버에 주입하지 않는다.
- 외부 인가 캐시 TTL·미고지/복제 자격·업스트림 진행 중 I/O·다중 프로세스 풀 제거·실제 컨테이너 제거 시각은 미확인이다. 기존 기본 주기(풀 2초, 실행기 5초)는 제거 완료 보장이 아니다.
- 발급자 대상의 T1은 전체 이용 관계/외부 자원 서버의 T1을 뜻하지 않는다. C3의 기존 상태 비저장 만료 공백과 케이스 최저 등급 집계는 유지한다. D-154 회전 후 서명 기록 장애/과거 복원 공백은 남는다.

## 다음 작업

DEV-08은 기기 검수 대기다. 메인이 소유한 별도 일회용 실험실에서만 아래 명령을 실행한다. 기존 다른 랩이 있으면 `up`/`down`으로 덮어쓰지 않는다.

```bash
cd full_stack_lab
tests/termination_dispatch_lab.sh up
trap 'tests/termination_dispatch_lab.sh down' EXIT
tests/termination_dispatch_lab.sh run resource_residual_pg_check.py
```

게이트웨이 이미지(Python 3.11+·기존 의존성)에서는 전체 `full_stack_lab`을 `/src:ro`로 마운트하고 작업 위치 `/src`에서
`python tests/resource_residual_check.py`와 `python tests/session_termination_check.py`를 재실행한다.
두 순수 시험은 저장소의 상대 디렉터리를 읽으며 새 시험은 `runtime/worker.py`도 읽으므로, PG 드라이버의 `/tests` 단독 마운트로 실행하지 않는다.
기존 `tests/termination_flow.py` 전체 회귀는 별도 일회용 전체 랩에서 `TERMINATION_DISPOSABLE_LAB=1 python tests/termination_flow.py`로 실행한다.
새 시험이 실제 PG·보호 자원 응답·서명 폐기·대상 등급과 정리를 모두 통과한 뒤, 솔루션 기기의 `./console.sh field up`과 PJ1 실제 하네스 재접근/독립 효과 검증을 별도 수행한다.

## 사용자에게 필요한 입력

없음. 기기 실행과 배포는 이번 레인의 로컬 구현 결과에 대한 메인의 후속 검수로 남긴다.
