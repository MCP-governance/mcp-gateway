# 2026-10-20 사고 증빙 패키지 적대 검토 수정

- 작업자: Codex sol
- 코드 기준: `10/20-incident-pack`, 시작 `a29320c560028281ce741c9d29e3a2517ce3e803`; 사람이 준비한 병합 상대 `48436fa2344bfdc95ca070199c19855414aef6bc`. 시작부터 병합 중·미커밋 상태이며 다른 작업자의 staged 변경을 보존했다.
- 시작 근거: DEV-66, D-144, [c5 적대 검토 1~10](../../analysis/review-1020/c5-incident-pack.md), [분석 정본](../../analysis/incident-pack/README.md).
- 해결할 문제와 완료 조건: 서버 미지정 조회·탐지 이후 영향·누락 보고 단계·경보 실패·대응/승인/무효/정책 증빙·팩 판본을 수정하고 기존 시험 기대값을 유지한다. 배포/실기기 검수와 구별한다.

## 결과

| 검토 | 처리 |
| --- | --- |
| 1 | 무형식 NULL 매개변수 비교 제거, 서버 참조 배열은 `::text[]` 명시. 실제 PostgreSQL EXPLAIN 사례 추가. |
| 2 | 탐지와 영향 기간 분리, 탐지 후 영향 허용. 관리자 보강 API가 초기 범위를 유지하며 추가 이력으로 확대한다. |
| 3 | NIS2 중간/최종/진행/처리 종료 후 최종 단계 추가. 실제 제출·처리 종료 기산, 달력 1개월, 미확정은 수동 확인. |
| 4 | CRA 적극 악용 취약점/중대한 사고 단계 구분. 유형별 최종 보고와 기산점 연결, 유형 미정은 수동 확인. |
| 5 | 경보 기록 성공 후 heartbeat, 별도 실패 시각과 복구. 한 사고 실패에도 다른 사고와 기존 운영 대응은 계속 실행. |
| 6 | 영향 호출 기간과 증빙 기준 시각 분리. 이전 승인·지속 중지·탐지 후 대응을 관련 이력으로 수집. |
| 7 | 영향 호출의 실제 `approval_id`/서버와 도입 관계의 승인/철회 이력 연결, 자유서술 원문 제외. |
| 8 | 호출과 같은 스냅샷에서 기존 무효 주석 의미를 투영. 전체/무효/유효 건수 및 관리자·사유 해시 참조. |
| 9 | 사고에 선택 팩 판본 저장. 시행일/지원 기간 이전 및 고정 팩 없는 기존 사고는 수동 확인. |
| 10 | 판정 당시 정책 판본·사유 코드(선택 정책 ID)·사유 해시 참조 투영, 원문 제외. |

`DECISIONS.md`·`main.py`·`v2_tables.sql`의 충돌 텍스트를 양쪽 기능을 보존하여 합쳤다. 결정은 번호순이며 도입 위험 등급·중대 영향·이벤트 상관 기능을 보존한다. `.git`은 쓰기 범위 밖이므로 인덱스의 세 파일 `UU` 표시는 남는다. 커밋/푸시하지 않았다. 사람이 세 파일을 `git add`하여 병합 해결을 표시해야 한다.

추가·수정 범위는 `gateway/app/{incidents,incident_pack,main,ops_response}.py`, `gateway/app/v2_tables.sql`, `gateway/app/agent_static/console.js`, `registry/field/incident_jurisdictions.json`, `tests/incident_pack_check.py`, D-144, 분석 정본과 본 보고, 백로그 DEV-66 상태 칸이다. 기존 staged 병합 변경과 구별한다. `status/current.md`는 수정하지 않았다.

## 검증

다음은 이 PC에서 실제 실행한 검사다. 최종 실행 시각·종료 코드·출력은 [local-checks.json](../../analysis/incident-pack/local-checks.json), 코드 행·SHA-256은 [source-snapshot.json](../../analysis/incident-pack/source-snapshot.json)에 기록한다.

| 확인 종류 | 명령·환경 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수/DB·HTTP 대역 | `python -B -X utf8 tests/incident_pack_check.py -v`, Python 3.10.5, `full_stack_lab/` | 24개 중 21개 통과·3개 건너뜀; 기존 import 기반 2개는 psycopg 부재, 실 DB 계획 1개는 기기 전용 | `local-checks.json` |
| 구문 | `python -m py_compile gateway/app/incidents.py gateway/app/incident_pack.py gateway/app/main.py gateway/app/ops_response.py tests/incident_pack_check.py` | 통과 | `local-checks.json` |
| 구문 | `node --check gateway/app/agent_static/console.js` | 통과 | `local-checks.json` |
| 콘솔 상태 회귀 | `node --test tests/console-state.test.mjs` | 15개 통과 | `local-checks.json` |
| 인증 경계 | `python -B -X utf8 tests/open_endpoints.py` | 통과: 문서와 무인증 1개 일치·인증 필요 84개 | `local-checks.json` |
| 변경·병합 텍스트 | `git diff --check`, 작업 트리의 추적/비추적 텍스트 충돌 표시 탐색 | 통과, 충돌 마커 없음; 인덱스 `UU` 3개는 별도 | `local-checks.json` |
| 보존 검사 | 시작 commit과 기존 시험 클래스 AST 대조·양쪽 병합 심볼·결정 번호순·DEV-66 상태 칸 외 백로그 보존 | 통과 | `local-checks.json` |

## 기존 시험 변경 필요

없음. 기존 세 시험 클래스와 기대값은 그대로다. 추가 사례만 같은 시험 파일에 넣었다. AST 격리 시험은 실제 함수 본문과 DB/HTTP 대역을 실행하며, 게이트웨이 모듈 import·SQL 성공·실제 MCP 실행 증거로 세지 않는다. 기존 두 import 기반 사례는 게이트웨이 이미지에서 다시 실행해야 한다.

## 실패·미완료·한계

- 실 DB EXPLAIN·원장/주석/승인 데이터 대조, 병렬 범위 확대, 보고/경보 경합·재시작, 브라우저 표시·솔루션 배포·PJ1 실제 하네스는 미실행이다. 새 MCP/mock 서버는 만들지 않았다.
- 월 계산은 UTC 달력 기준이며 관할 현지 달력·휴일·법정 기간 계산 특례는 수동 확인이다. 한국 정보통신망법은 한국 시각 시행 경계, CRA는 위키의 적용일을 사용하며 현지 경계는 수동 심사 대상이다.
- 과거 원장에 더 세분된 사유 코드나 정책 판본이 없으면 복원하지 않는다. 유효 건수는 무효 주석이 없는 행 수다. 대응 이력 전체와 호출 목록은 단일 원자 스냅샷이 아니며, 해시는 전자서명이 아니다.
- 원격 HEAD 확인은 GitHub:443 연결 실패. 법령 공식 페이지 재열람은 자동화 확인 화면으로 실패하여 기존 위키 본문 확인 기록에 한정했다. 외부 스킬/OSS 검색의 commit·라이선스/유지보수 미확인 항목은 채택하지 않았다.

## 다음 작업

DEV-66: 사람이 병합 해결을 인덱스에 표시하고, 솔루션 기기에 `./console.sh field up`으로 배포한 뒤 게이트웨이 의존성 환경에서 다음을 실행한다. 이 PC에서 스택은 띄우지 않았다.

```bash
cd full_stack_lab
MINT_INCIDENT_PG_CHECK=1 python -B -X utf8 tests/incident_pack_check.py -v
python -B -X utf8 tests/open_endpoints.py
node --check gateway/app/agent_static/console.js
node --test tests/console-state.test.mjs
```

첫 명령은 게이트웨이 이미지의 의존성·DB 연결·갱신된 스키마와 레지스트리를 사용할 수 있는 환경에서 실행한다. PostgreSQL 사례는 `EXPLAIN`만 실행하고 쓰기나 `ANALYZE`는 하지 않는다. 실제 데이터의 정확성·효과·경합 검증은 별도로 남는다.

## 사용자에게 필요한 입력

추가 입력 없음. 기기 검증·병합 인덱스 반영은 사람이 수행하는 인계 범위다. 자격증명은 기록하지 않는다.
