# DEV-61 SIEM UID·전송 로그·실제 DB 큐 재시작 시험

담당 Codex sol, 브랜치 `10/20-siem-dedup`, 시작 `a7aa43a1970333a28aaf9050ebaa476d8673c098`(clean).
[D-157](../../../../docs/ai/DECISIONS.md), [운영 계약](../../../../docs/ai/OPS_RESPONSE.md#사건-식별자와-전송-시도-기록-d-157),
[작업 보고](../../status/reports/2026-10-20-siem-dedup.md), [로컬 명령·실제 출력](checks.json), [코드 지문·심볼](anchors.json).
WBS G06.06 / POL-38·42 / DEV-61을 연결한다. 검수 완료 점수·배포 상태는 변경하지 않는다.
원격 HEAD 조회는 GitHub 연결 실패로 확인하지 못했고 지정된 기존 브랜치에서만 작업했다.

## 원자 요구사항과 확인 범위

| ID | 조건과 결과 | 코드/시험 | 이번 증거 |
| --- | --- | --- | --- |
| SIEM-UID-01 | 정상 판정 UID에 원장 행 ID·사슬 해시 사용. 재전송·시도 횟수·DB 시각 오프셋 변경에도 같음 | `siem.event`, `UidChecks.test_chain_and_row_identity_ignore_session_timezone_and_attempt_state` | 순수 함수 통과 |
| SIEM-UID-02 | 다른 행·다른 사슬은 다른 사건. 손상/빈 사슬을 시각 UID로 조용히 대체하지 않음 | `test_row_id_and_chain_changes_are_distinct_events`, `test_invalid_chain_is_not_silently_reidentified` | 양성/음성·경계 통과 |
| SIEM-UID-03 | 사슬 없는 과거 판정·승인·경보는 소스·행 ID·UTC 기록 시각 해시. 토큰·본문은 UID에 넣지 않음 | `test_unchained_sources_use_utc_and_keep_the_legacy_utc_uid`, `test_uid_does_not_include_private_fields` | 3개 소스·비-UTC 경계 통과 |
| SIEM-LOG-01 | 전송 직전·응답·큐 커밋에 동일 UID 기록. 수신 후 커밋 실패 시 2회 시도/2회 응답/1회 커밋 로그 | `siem.deliver_one`, `AttemptLogChecks` | AsyncMock DB 대역 통과. DB/프로세스 장애 증거 아님 |
| SIEM-TLS-01 | 시험 CA를 명시적으로 신뢰하고 호스트명 검증. 미신뢰 CA/호스트명 불일치는 HTTP 전달 전 거부 | `siem.send`, `TlsChecks`, `siem_tls_receiver.receiver` | 실제 로컬 TLS 소켓 통과. 검증 끄기 없음 |
| SIEM-DB-01 | 생산 `_record_decision`→원장·큐 동일 커밋. 승인 트랜잭션 롤백은 큐도 롤백. 합성 경보 제외 | `siem_enqueue` 트리거, `triggers_and_restart` | 실제 PostgreSQL 시험 작성, **미실행** |
| SIEM-DB-02 | HTTPS 503이면 참조·오류·재시도 시각 유지. 수신 200 뒤 큐 UPDATE 커밋을 DB 잠금으로 정지하고 SIGKILL | `triggers_and_restart`, 실제 `python -m app.siem` 하위 프로세스 | **미실행** |
| SIEM-DB-03 | 한 워커가 행을 잡고 있어도 다른 워커가 승인/경보를 `SKIP LOCKED`로 처리 | 같은 PG 시험, 별도 2개 생산 워커 | 경쟁 조건 **미실행** |
| SIEM-DB-04 | 워커 재시작 후 원장/승인/경보 각 1건 누락 0. 중단 사건만 같은 UID/본문 재전송, 수신 측 UID 유일 키 후 정확히 1건 | SQLite 별도 저장소와 큐 집계, UID별 요청·시도·응답 로그 수 대조 | 로컬 TLS 수신기 중복 제거 통과, **실제 DB 복구 경로 미실행** |
| SIEM-DB-05 | 배송 전후 원장 전체 행 동일. 큐 커밋 횟수와 로그 시도 수 차이 검증 | PG 시험: 3개 사건/5회 시도/4회 큐 커밋 기대 | **미실행**, 이 숫자는 예상값 |

## 격리 PostgreSQL 시험 설계와 실행

[siem_queue_pg_check.py](../../../../full_stack_lab/tests/siem_queue_pg_check.py)는 기존
[termination_dispatch_lab.sh](../../../../full_stack_lab/tests/termination_dispatch_lab.sh) 경로를 사용한다.
DB 호스트 `wbs-c-pg`와 DB 이름 `t_siem_queue_pg_check_py_*`를 검사한 뒤 스키마를 적용한다.
`isolated_disposal`의 임시 키/디렉터리만 쓰며 생산 폐기 볼륨·컨테이너는 접근하지 않는다.
기존 시험 파일/실험실 드라이버와 기대값은 변경하지 않았다.

1. 원장 함수로 판정 1건을 기록하고 큐 참조와 사슬 UID를 읽는다. 감사 트랜잭션 롤백·합성 경보 제외를 확인한다.
2. 표준 라이브러리 HTTPS 수신기는 임시 CA의 서버 인증서를 사용하고, 성공 요청만 SQLite `PRIMARY KEY(uid)`로 저장/커밋한 뒤 200을 응답한다. 503 요청도 UID·본문·응답 코드로 따로 계수한다.
3. 별도 워커가 503 재시도 후 200을 받고 큐를 갱신할 때, 시험 DB에만 설치한 AFTER UPDATE 트리거가 부모의 advisory lock을 기다린다. `pg_stat_activity.wait_event='advisory'`와 수신 기록 양쪽을 확인한 뒤 프로세스를 SIGKILL한다. 시간 지연만으로 장애 지점을 추정하지 않는다.
4. 중단 전에 두 번째 워커가 잠긴 행을 건너뛰고 새 감사·경보를 전달하는지 확인한다. 잠금 해제 후 죽은 연결 종료/롤백을 기다리고 새 프로세스를 시작한다.
5. 수신 SQLite·전송 요청·생산 로그·큐·원장을 대조한다. 모든 subprocess는 finally에서 kill/wait, 트리거/함수·CA/키·수신기·SQLite는 전용 DB/임시 디렉터리 범위에서 정리한다. 도구/import/워커 종료·대기 시간 초과는 실패다.

다음은 메인이 솔루션 기기에서 수행할 명령이다. 새 로컬 스택을 띄우지 않는다.

```bash
# 전용 실험실이 이미 떠 있거나 다른 작업자가 사용 중이면 up/down을 실행하지 않는다.
cd full_stack_lab
# 새 전용 실험실이 필요한 경우에만, WSL에서 기존 드라이버로 솔루션 기기에 생성:
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run siem_uid_check.py
tests/termination_dispatch_lab.sh run siem_queue_pg_check.py
# 자신이 생성했고 다른 작업자가 사용하지 않는 전용 실험실만 제거:
tests/termination_dispatch_lab.sh down
```

기존 드라이버의 고정 이미지에 현재 gateway requirements가 있는지 메인이 확인해야 한다.
이 시험은 자체 MCP를 만들거나 기존 MCP에 호출하지 않는다. 표준 HTTPS 시험 수신기와 SQLite는 합성 데이터의 독립 저장 효과이며 실제 SIEM 제품과 구별한다.
시험 로그/키는 임시 폴더에 두고 삭제하므로 실행 시 상위 드라이버의 stdout JSON 검사 결과를 별도로 보관한다.

## 선행 공개 스킬·OSS 검토 (2026-10-20)

외부 지시·스크립트·서버는 실행하지 않았고 제3자 코드를 복제하지 않았다. 새 라이브러리/서비스 의존성은 없다.

| 자료 | 판본·commit·라이선스·유지보수 관찰 | 사용 범위와 한계 |
| --- | --- | --- |
| [OCSF Metadata](https://raw.githubusercontent.com/ocsf/ocsf-schema/1.4.0/objects/metadata.json), [릴리스](https://github.com/ocsf/ocsf-schema/releases/tag/1.4.0) | 1.4.0, `6109cc5e834c1adfee67dda6c9bcfa5e37f79012`. 기존 D-128 분석은 Apache-2.0으로 기록했으나 이번 태그 LICENSE URL 재열람은 실패. 릴리스/필드 본문만 확인, 최신 전체 유지보수 감사 아님 | 사건 UID 의미만 적용. 이전 분석의 `v1.4.0` 태그 표기는 공식 `1.4.0` 태그와 구별해 정정. 이전 분석은 이력으로 보존. OCSF 전체 검증 아님 |
| [anthropics/skills webapp-testing](https://github.com/anthropics/skills/blob/53048666b05b4799081517d00e09e0a2dd688678/skills/webapp-testing/SKILL.md), [라이선스](https://raw.githubusercontent.com/anthropics/skills/53048666b05b4799081517d00e09e0a2dd688678/skills/webapp-testing/LICENSE.txt) | `53048666b05b4799081517d00e09e0a2dd688678`, Apache-2.0. 지정 commit의 SKILL/라이선스 본문 검토. 최신 브랜치 유지보수는 미확인 | Playwright 웹 화면 시험 중심이라 DB 큐/워커 장애 과제에 채택하지 않음. 외부 스킬 실행 없음 |
| [Psycopg 트랜잭션](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [고정판 라이선스](https://raw.githubusercontent.com/psycopg/psycopg/3.3.5/LICENSE.txt) | 기존 고정 의존성 psycopg 3.3.5, pool 3.3.1, LGPL-3.0 라이선스 본문. 열린 문서는 3.3.7.dev1로 소스 commit/고정판 전수 대조는 미수행 | 이미 쓰는 `db.transaction`과 실제 PostgreSQL 연결/잠금 사용. 커밋 전 연결 종료 시 재전송 경계의 근거로만 사용 |
| [Python TLS](https://docs.python.org/3/library/ssl.html#ssl.create_default_context) | 표준 라이브러리, PSF. 공식 `create_default_context` 문서. 제품 이미지는 Python 3.12, 로컬 추가 검증 3.12.14 | 인증서/호스트명 검증을 기본으로 유지. 시험 CA 발급만 기존 cryptography 50.0.1 사용(라이선스 Apache-2.0/BSD, 설치 추가 없음). 이번 문서 열람은 최신 Python 문서로 3.12 전체 코드 감사 아님 |

## 남은 경계

재전송은 최소 한 번 전달 방식이다. 중복 제거는 수신기의 UID 유일 키·내구 저장 계약에 의존한다.
구 UID 별칭 전환, 컨테이너 로그 손실/회전, DB/수신 저장소 백업 유실, 다중 배치의 이름 공간, 전송 전체 기한·보존/용량 관리는 이번 범위 밖이다.
PG 시험을 실행하기 전에는 트리거·잠금·실제 프로세스 재시작·합성 큐 누락 0을 확인했다고 말하지 않는다.
