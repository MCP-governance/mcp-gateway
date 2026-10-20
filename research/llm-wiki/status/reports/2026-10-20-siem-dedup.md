# 2026-10-20 SIEM UID·실제 DB 큐 재시작 시험

- 작업자: Codex sol
- 코드 기준: `10/20-siem-dedup`, 시작 `a7aa43a1970333a28aaf9050ebaa476d8673c098`, 시작 clean. 커밋·푸시 없음.
- 시작 근거: DEV-61 / WBS G06.06 / POL-38·42 / [D-128 보고](2026-10-17-selective-restriction-siem.md) / [기존 분석](../../analysis/selective-restriction-siem/README.md).
- 해결할 문제와 완료 조건: 수신 확인 뒤 큐 커밋 실패/프로세스 종료로 재전송되는 사건의 UID를 안정화하고 시도 기록과 연결한다. 실제 PostgreSQL 트리거·TLS·워커 중단/재시작·수신 중복 제거 시험을 작성한다. 실제 기기 실행은 메인이 수행한다.
- 변경 범위: `gateway/app/siem.py`, 새 시험 `siem_uid_check.py`·`siem_queue_pg_check.py`·공통 시험 수신기 `siem_tls_receiver.py`, D-157·운영/데이터 문서, [분석 정본](../../analysis/siem-dedup/README.md), DEV-61 상태, 필수 위협 매핑 재생성.

## 결과

판정 UID를 원장 행 ID·사슬 해시에 결속했다. 사슬이 없는 과거 판정·승인 감사·경보는 UTC로 정규화한 기록 시각의 해시를 사용한다.
유효하지 않은 사슬 해시는 전송 실패로 남긴다. `metadata.uid`와 기존 `Idempotency-Key`의 값은 같다.
워커의 표준 오류 INFO 로그에 UID별 시도·응답·큐 커밋을 구별해 기록한다. DB 큐의 `attempts`가 롤백되어도 프로세스의 전송 시도 로그는 남으며,
로그 행 수를 UID별로 집계할 수 있다. 로그에는 소스 본문·사유·토큰·주소·원격 응답 본문을 넣지 않는다.

새 PG 시험은 기존 격리 드라이버의 전용 DB/`isolated_disposal`을 사용하고, 생산 `_record_decision`·`siem_enqueue`·`python -m app.siem`을 호출한다.
시험용 AFTER UPDATE 트리거·advisory lock으로 수신 200 뒤 큐 커밋 직전을 멈춘 사실을 관측하고 SIGKILL한 뒤 실제 새 워커를 실행한다.
503, 트리거 롤백, 합성 경보 제외, 다중 워커 `SKIP LOCKED`, TLS CA/호스트명 거부, SQLite UID 유일 키의 독립 저장을 검사하도록 작성했다.
3개 합성 사건·5회 요청·4회 큐 결과 커밋·사건별 저장 1건·누락 0은 **실제 PG 시험의 예상값**이며 아직 관측 결과가 아니다.
이 수신기는 표준 라이브러리 HTTPS 시험 서버이며 MCP 서버가 아니다.

새 의존성·DB 변경·정책 ID·라우트·콘솔 변경은 없다. 원장 UPDATE/DELETE도 없다.
`status/current.md`는 요청대로 변경하지 않았고, 백로그는 DEV-61 행의 마지막 칸만 변경했다.
기존 D-128 분석·실험실·시험 기대값은 보존했다. 필수 위협 매핑의 다른 파일 변경은 시작 커밋을 기준으로 낡은 committed hash/dirty 표시를 재계산한 결과다.

## 검증

실제 명령·시각·종료 코드·출력은 [checks.json](../../analysis/siem-dedup/checks.json), 파일 SHA-256·심볼/행은 [anchors.json](../../analysis/siem-dedup/anchors.json)에 있다.
로컬 추가 실행 환경은 Windows Python 3.12.14, cryptography **50.0.2**, OpenSSL 3.5.8이다. 게이트웨이 고정 의존성 cryptography **50.0.1**과 구별하며 고정 이미지 검증은 대기다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| UID·로그·TLS | Python 3.12.14 `-B -X utf8 -m unittest discover -s full_stack_lab/tests -p siem_uid_check.py -v`, 2026-10-20 | 새 7건 통과. 실제 로컬 CA 검증/호스트명 거부·SQLite 중복 제거 포함, PG 아님 | `checks.json`: `new_uid_tls` |
| 기존 회귀 | 같은 환경 `-m unittest discover -s full_stack_lab/tests -p selective_restriction_siem_check.py -v` | 기존 14건 통과, 파일/기대값 미변경 | `checks.json`: `existing_siem` |
| Python 구문 | `python -m py_compile` 변경 모듈·새 시험 4파일 | 통과 | `checks.json`: `compile` |
| JS 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js`, Node 24.21.0 | 통과 | `checks.json`: `node_check` |
| 인증·스키마 정적 | `python full_stack_lab/tests/open_endpoints.py`, `python full_stack_lab/tests/schema_check.py` | 통과 | `checks.json`: `authenticated_routes`, `schema_static` |
| CI와 같은 pyflakes 범위 | `cd full_stack_lab && python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py`(Windows에서 파일 패턴 전개) | 도구 없음, 종료 1. 경고 0으로 간주하지 않음 | `checks.json`: `ci_pyflakes` |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py` | 통과, 24개 정적 후보 매핑 재생성 | `checks.json`: `threat_map` |
| 위키 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 오류 0. Git 제외 로컬 원본 누락은 경고 | `checks.json`: `wiki` |
| 변경 범위·형식 | `git diff --check`, UTF-8 BOM/CRLF 검사·기존 시험 해시 대조 | 통과 | `checks.json`: `diff_whitespace`, `file_integrity` |

## 실패·미완료·한계

- 기본 Python 3.10.5에는 cryptography·psycopg·pglast·pyflakes가 없다. 제공 런타임의 Python 3.12.14로 로컬 TLS 시험을 실행했다. pyflakes는 그 런타임에도 없어 임시 설치를 시도했지만 패키지를 확보하지 못했다. CI lint 통과 여부는 미검증이다.
- 최초 TLS 수신기 시험에서 SQLite 연결 context가 연결을 닫지 않아 Windows 임시 파일 정리가 실패했다. 새 공통 시험 수신기와 두 소비 시험에 명시적 연결 닫기를 넣고 재실행해 통과했다. 기존 시험은 수정하지 않았다.
- 원격 기본 HEAD는 GitHub 연결 실패로 확인하지 못했다. 브랜치/커밋은 로컬에서 확인했다.
- 실제 PostgreSQL 큐·트리거/동시 워커·SIGKILL/재시작 시험, 솔루션 배포, PJ1, 실제 SIEM 저장/검색, 구 UID 전환은 **미실행**이다. 로컬 TLS 통과를 DB 통합·제품 검수로 올리지 않는다.
- D-128과 판정/비-UTC 사건의 UID가 달라질 수 있다. 구 워커 정지 후 수신 측 기존 사건과 새 UID 별칭을 연결한 뒤 신 워커를 가동해야 한다. 별칭 전환은 자동 구현하지 않았고 혼재 버전 중복 제거를 보장하지 않는다.
- 로그의 시도 수는 전송 직전 행 수이며 실제 수신 건수나 DB 영속 시도 원장이 아니다. 로그 유실/회전·정확히 한 번 전송·DB/수신기 저장소 유실·전체 HTTP 시간 제한은 남는다.

## 기존 시험 변경 필요

없음. 기존 시험/드라이버의 실행 코드·기대값은 변경하지 않았고 기존 14건도 통과했다.

## 다음 작업

메인이 DEV-61의 전용 실험실을 확인한 뒤 다음을 실행한다. 다른 작업자의 실험실은 생성/정리하지 않는다.

```bash
cd full_stack_lab
# 아래 run은 기존 WSL 드라이버에서 솔루션 기기의 격리 게이트웨이 이미지로 실행한다.
tests/termination_dispatch_lab.sh run siem_uid_check.py
tests/termination_dispatch_lab.sh run siem_queue_pg_check.py
python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py
```

빈 전용 실험실이 필요할 때만 기존 드라이버 `up`/자신의 실험실 `down` 절차를 쓴다([안전한 실행 범위](../../analysis/siem-dedup/README.md#격리-postgresql-시험-설계와-실행)).
고정 게이트웨이 이미지의 의존성/판본과 PG 시험의 모든 JSON 체크 통과를 확인하고 출력 증거를 보관한다.
그 뒤 수신 제품의 UID 유일 키·저장 후 수신 확인 계약과 구 UID 별칭을 검수하고 기존 `./console.sh field up --with-siem` 경로로 배포한다. 이번에는 배포하지 않았다.

## 사용자에게 필요한 입력

없음. 이번 레인은 미커밋 변경과 기기 시험 명령을 메인에 넘긴다.
