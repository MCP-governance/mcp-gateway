# Endpoint snapshot 회귀 검수

검토일: 2026-10-14 KST. 이 문서는 최신 source inspection, WSL 단위검사, 전용 PostgreSQL 실행 증거를 서로 구분한다. 제품 코드와 데이터베이스는 이 검토에서 수정하지 않았다.

## 현재 구현 경계

- `EndpointReport.complete`, `ListenerReport.complete`, `endpoint_plane.ingest()`와 `ingest_listeners()`의 기본값은 모두 `False`다. `complete`가 없는 레거시 요청은 upsert와 관측 상태 기록을 허용하지만 `partial`로 표시하고 unseen 행을 삭제하지 않는다. `last_success_at`도 그대로 둔다. 전체 삭제는 명시적인 `complete=True`에서만 수행하며, listener 삭제는 `sources` 범위로 제한한다.
- listener source 목록은 비어 있거나 중복되거나 허용되지 않은 값이면 거부한다. finding이 선언한 scope 밖의 source를 포함해도 변경 전에 거부한다. receiver는 transaction이 제공한 connection과 cursor를 재사용한다.
- Gateway listener 분류는 Gateway 주소/포트의 직접 일치로만 적용한다. `server_name`으로 Gateway를 주장하는 stdio listener는 shadow로 분류된다. 일반 registry 서버 이름을 주장한 직접 stdio listener도 Gateway 관리 경로가 아니므로 shadow다. 이는 inventory의 direct-route 경계와 맞춘다.
- observation-status handler는 자격 endpoint가 요청 endpoint와 같은지 확인한다. inventory 전용 scope에서 `process`, `network`, `os` 채널의 `success` 또는 `partial`은 추가 scope 없이는 403으로 막는다. 같은 endpoint의 `unauthorized` 진단은 허용한다. FastAPI dependency의 transport 인증은 이 handler 직접 호출 테스트로 검증되지 않았다.
- listener freshness는 성공 상태와 판정 가능한 관측/보고 시각이 모두 180초 이내면 `fresh`, 성공 상태지만 확인된 시각이 오래됐으면 `stale`, partial·failed·disabled 또는 시각 누락/오류이면 `unknown`이다. 미래 시각도 fail-closed로 `unknown` 처리한다. freshness가 불확실해도 기존 conservative shadow count를 0으로 만들지 않는다.

## 단위검사 증거

2026-10-14, WSL 격리 Python 환경 `/tmp/mcpgw-log-fix-20261014-venv/bin/python`에서 다음 두 파일을 함께 실행해 27개가 모두 통과했다.

```text
python -X utf8 -m unittest full_stack_lab.tests.endpoint_snapshot_check full_stack_lab.tests.endpoint_inventory_check -v
Ran 27 tests ... OK
```

`endpoint_snapshot_check.py`는 model과 receiver 기본값, unmarked empty 보고의 삭제 금지와 partial 상태, 명시적 complete 삭제, source scope, mutation 전 거부, rollback, freshness, Gateway 이름 주장과 direct listener 분류를 검사한다. observation-status 검사는 handler를 직접 호출해 endpoint 및 채널 scope를 확인하고, plane 함수가 거부 요청에서 호출되지 않는지 검증한다. `endpoint_inventory_check.py`는 inventory privacy 및 route 분류 관련 기존 단위 조건을 확인한다.

이 검사는 in-memory adapter와 mock dependency를 사용한다. FastAPI ASGI transport에서 credential dependency와 실제 HTTP 요청이 보호되는지, 모델 harness가 어떤 자격으로 route를 호출하는지, 실제 Windows endpoint의 collector 관측·OS 권한·방화벽 동작은 증명하지 않는다. 이 실행의 테스트 성공을 배포·정책 활성화 또는 실기기 결과로 해석할 수 없다.

## 전용 PostgreSQL 증거

정본 로그 [pg-snapshot.jsonl](pg-snapshot.jsonl)은 2026-10-14 실행에서 `risk_scenarios_20261014` 데이터베이스의 일회성 `risk_snapshot_20ee5c8ce9b2441194aac99670163911` schema에 대해 `result=PASS`와 다음 8개 조건을 기록한다. 독립 SQL 관측은 각 동작 전후 행 상태를 비교하며 마지막 레코드는 `schema-dropped`를 기록한다.

1. 불완전 inventory upsert에서 기존 행을 보존한다.
2. complete 표시가 없는 레거시 빈 inventory 보고가 기존 행을 보존하고 partial telemetry를 남긴다.
3. 명시적 `complete=True` 빈 inventory 보고만 전체 삭제한다.
4. listener finding과 선언된 source 범위의 불일치는 상태를 변경하지 않는다.
5. 완전한 stdio-only 빈 보고는 stdio 행만 지우고 network/local-socket 행은 보존한다.
6. partial process 보고는 이전 `last_success_at`을 보존한다.
7. 알려진 stale 관측은 stale로 구분하고 conservative listener count를 유지한다.
8. listener 삭제 trigger 실패 시 upsert·telemetry를 포함한 변경을 rollback한다.

이는 준비된 전용 PostgreSQL DB의 schema-scoped integration evidence다. Windows OS 정책, endpoint agent 실행권한, HTTP transport credential, 실제 managed harness 호출 또는 Windows collector 수집 범위의 증거는 아니다. PG 로그에 없는 listener 분류와 observation-status 권한 케이스는 위 단위검사 범위로만 확인했다.
