# 운영 대응

설계 결정 D-120~D-123·D-127·D-128, DEV-50·52·60·61·62·63. 코드 구현과 로컬 단위 검증 단계이며 배포·실기기 검증은 별도다.

## 이미지 재검사

`runtime-worker`는 활성 실행의 불변 이미지 ID를 Trivy 0.74.0의 Docker 이미지 소스로 검사한다. 도입 검사의 JSON 파서와 DB 시각 파서를 `supply_chain/trivy_scan.py`로 공유한다. 이미지 ID 불일치, 검사기 오류, 잘못된 JSON, 취약점 DB 시각 누락·미래·7일 초과는 검사 실패다. 실패는 즉시 실행 중지 대상이다.

`runtime_image_scans`에 이미지 ID·검사 시각·DB 시각·버전·결과 해시·발견 항목·최초 발견 시각을 추가한다. CRITICAL의 CVE·대상·패키지·설치 버전 조합별 최초 발견 시각에서 조치 기한을 계산한다. 검사 실패는 이전 시각을 지우지 않는다. 정상 재검사에서 사라진 항목은 해소로 본다. 기한이 지난 항목이 남으면 서버를 비활성화하고 기존 `STOPPING` 정리 경로로 실행 컨테이너·망을 제거한다. 잔존 자원이 있으면 `STOPPING`에서 재시도한다. 검사는 `approval_events`에도 추가한다.

| 설정 | 기본값 | 의미 |
| --- | ---: | --- |
| `RUNTIME_SCAN_INTERVAL_SECONDS` | 86400 | 재검사 간격 |
| `RUNTIME_CRITICAL_DEADLINE_DAYS` | 7 | 최초 발견 후 조치 기한 |
| `RUNTIME_SCAN_TIMEOUT_SECONDS` | 600 | 이미지 검사 시간 제한 |

초기 활성 실행도 검사한다. 검사는 실행기의 기존 직렬 루프에서 수행하므로 빌드·다른 검사 중에는 지연될 수 있다. `runtime_trivy_cache`와 외부 다운로드가 가능한 `scanner` 망을 사용한다. 검사 결과 원본의 해시는 남기지만 임시 원본 JSON 파일은 보존하지 않는다. KEV·EPSS 피드를 자동 수집하거나 점수로 기한을 바꾸지는 않는다. 이 작업의 격리 기준은 요청한 CRITICAL·기한이다.

## 경보 자체 시험

게이트웨이의 운영 감시 루프가 실제 로드된 OPA 규칙·데이터·capability 해시를 확인한다. 같은 해시의 성공 기록이 없으면 정상군 1건과 새 도구·미승인 연결·미승인 리스너·중요정보 호출 급증·반복 거부 합성군 5건을 평가한다. `decision`과 `policy_id`를 모두 비교하고 실제 경보 기록 함수의 저장 결과까지 확인한다. 도구를 실행하거나 실제 `decisions`에 합성 호출을 넣지 않는다.

실제 경보와 합성 경보는 `ops_alerts.synthetic`로 구분한다. 실제 새 도구는 계약 스냅샷의 추가 도구에서, 연결·이상 호출은 기존 정책 판정에서 경보로 기록한다. `alert_self_tests`에는 해시·합성 표식·케이스별 판정·경보 ID·성공 여부를 추가한다. OPA 장애, 정책 해시 불일치, 예상과 다른 정책 ID, 시험 도중 해시 변경은 실패로 남기고 합성 `policy-self-test-failed` 경보를 기록해 다음 감시에서 재시도한다. DB 저장 실패는 감시 루프에 오류를 남기며 다음 주기에 다시 시도한다. 자체 시험은 정책 평가·경보 기록 경로에 대한 시험이고 외부 알림/SIEM 전달 증거는 아니다.

## 자동 중지와 복귀

활성 도구의 미승인 계약 변경은 영향이 확정된 도구만 제한한다(D-127). 영향 미확정 변경은 서버 전체를 중지한다. `P-ANOMALY-*`·`P-VOLUME-*` 반복은 원장의 최종 판정·관찰 모드 판정·충돌 후보를 모아 센다. 동일 판정을 중복 집계하지 않으며, 합성 이벤트와 직전 복귀 이전 판정은 제외한다.

| 설정 | 기본값 | 의미 |
| --- | --- | --- |
| `OPS_RESPONSE_INTERVAL_SECONDS` | 5 | 운영 감시 주기 |
| `OPS_AUTO_STOP_SOURCES` | `drift,anomaly,volume` | 중지 원인. 빈 값은 대상 없음 |
| `OPS_AUTO_STOP_SERVERS` | `*` | 서버 ID 목록. 빈 값은 대상 없음 |
| `OPS_AUTO_STOP_REPEAT` | 3 | 시간 창 안에서 필요한 반복 판정 수 |
| `OPS_AUTO_STOP_WINDOW_SECONDS` | 300 | 반복 판정 시간 창 |

서버 전체 중지 시 `ops_suspensions`에 사유·근거를 기록하고 서버를 `DISABLED`, 관리형 실행을 `STOPPING`으로 바꾼다. 도구별 제한은 실행 프로세스를 중지하지 않고 도구 목록·계약 판정·최종 dispatch에서 막는다. 호출 직전 dispatch에도 비활성·중지·폐기 상태를 검사한다. 이미 dispatch 의도를 기록하고 전송한 호출을 취소했다고 주장하지 않는다. 원격 제공자 프로세스는 게이트웨이가 종료할 수 없으며 조직 경로만 중지한다.

## 선택적 계약 제한과 보안 관제 전달

도구 `a`만 변경되면 `catalog_snapshots.restricted_tools=['a']`이며 `a` 호출은 `MCP-CATALOG-001`로 차단하고 승인본과 같은 `b`는 계속 심사·실행한다. `DRIFT` 서버도 관리형 서버 목록에 유지하며 제한된 도구는 MCP 목록에 내리지 않는다. 영향이 `NULL`인 과거/미확정 스냅샷은 전체 차단이다. 승인본으로 원복한 사실도 새 스냅샷에 남기고, 변경된 계약의 새 채택은 기존 사람 승인 절차를 쓴다. 이미 중지·폐기된 서버는 자동 복귀하지 않는다.

보안 관제 전달은 `siem-worker` 프로파일로 분리한다. 운영자가 솔루션 기기의 `.env`에 `SIEM_URL=https://수신기/경로`, 필요하면 `SIEM_TOKEN_FILE=/run/siem/token`, `SIEM_CA_FILE=/run/siem/ca.pem`을 설정하고 실제 파일은 `full_stack_lab/siem-secrets/`에 배치한다. 비밀 파일은 Git에서 제외된다. 활성화 명령은 솔루션 기기의 `./console.sh field up --with-siem`이며 이 작업에서는 실행하지 않았다. 워커에는 호스트 게시 포트·MCP 망·업스트림 자격 볼륨을 추가하지 않는다. HTTPS 목적지의 라우팅·수신 계약은 배포 검수 대상이다.

`GET /api/audit/siem`과 감사 화면은 대기·재시도·최초 대기·최근 2xx 수신 시각을 보여 준다. 원장에 대한 관리자 권한이 필요하고 수신 주소·토큰·응답 본문은 공개하지 않는다. 기본 워커 미기동 중에도 설치 후 이벤트 참조는 큐에 남는다. 큐의 보존·정리·상한 자동 삭제는 구현하지 않아 디스크 관리가 필요하다. 과거 원장 일괄 소급 수집은 하지 않는다.

전송 형식은 OCSF 1.4.0 Base Event(`class_uid=0`, `activity_id=99`, `type_uid=99`)이며 MINT 전용 판정·상관 필드는 `unmapped`에 둔다. 요청/응답 본문·클라이언트 보고는 제외하고 식별자를 SHA-256 참조로 보내므로 실제 이름 확인은 내부 원장에서 한다. 2xx 수신 뒤 로컬 커밋 전 중단은 재전송될 수 있어 수신기는 `metadata.uid`로 중복을 제거해야 한다. 재시도는 5초부터 최대 1시간 간격이며 4xx도 폐기하지 않는다. 특정 SIEM 제품의 정규화·내구 수신·검색 성공은 아직 확인하지 않았다.

### 사건 식별자와 전송 시도 기록 (D-157)

`metadata.uid`와 HTTP `Idempotency-Key`는 같은 값이다. 사슬이 있는 판정은 `mint:decisions:<원장 행 ID>:<entry_sha256>`를 사용한다.
사슬이 없는 과거 판정·승인 감사·운영 경보는 `mint:<소스 테이블>:<행 ID>:<UTC created_at.isoformat()의 SHA-256>`를 사용한다.
시각은 Python `datetime.isoformat()` 기본 표현(마이크로초가 0이면 소수부 생략)이며 UTC 오프셋은 `+00:00`이다. DB 세션 시간대·시도 횟수·워커 프로세스·전송 시각은 UID에 영향을 주지 않는다.
비어 있거나 형식이 잘못된 사슬 해시는 다른 UID로 대체하지 않고 전송 실패로 남긴다. 사슬이 없는 판정의 SQL `NULL`만 과거 기록으로 취급한다.
수신기는 UID에 유일 제약을 두고 사건 저장과 중복 확인을 하나의 트랜잭션으로 끝낸 뒤 2xx를 반환해야 한다. HTTP 헤더만 보내서는 수신 측 중복 제거가 구현되지 않는다.

`python -m app.siem` 워커는 전송 직전 `SIEM attempt uid=... queue_id=... committed_attempts=...`, 응답 직후 `SIEM response uid=... status=...`,
큐 트랜잭션 커밋 뒤 `SIEM queue committed uid=...`를 표준 오류 INFO 로그로 남긴다. 실패 유형은 `SIEM retry`에 예외 클래스/HTTP 코드만 기록한다.
UID별 `SIEM attempt` 행 수가 시도 수이며 재시도 수는 첫 시도를 뺀 값이다. `siem_outbox.attempts`는 커밋된 결과 수이므로 수신 뒤 롤백된 시도는 포함하지 않는다.
시도 로그는 소켓 전송 직전에 기록되어 네트워크에 실제 도달한 건수를 뜻하지 않으며, 보존 범위는 컨테이너 로그 드라이버/회전에 따른다. 원장과 같은 내구성의 별도 DB 시도 원장은 추가하지 않았다.
원장·요청/응답 본문·주소·인증정보는 이 로그에 쓰지 않는다. UID의 사슬 해시는 사슬 검증의 대체물이 아니다.

D-128은 UTC로 정규화하지 않은 기록 시각 해시를 판정 UID에도 사용했다. 따라서 이미 수신한 판정과 비-UTC 세션에서 보낸 사건은 D-157 적용 때 UID가 달라질 수 있다.
배포 전 구 워커를 정지하고 수신 측에서 기존 `unmapped.source`·`source_id`와 내부 원장 시각/사슬 해시로 새 UID 별칭을 연결한 뒤 신 워커를 켠다.
별칭 전환·구/신 워커 혼재에서의 중복 제거는 자동화하지 않았으므로 버전을 넘는 동일 UID를 보장하지 않는다. 기존 큐·원장·수신 기록은 삭제하거나 수정하지 않는다.

격리 시험은 [siem_queue_pg_check.py](../../full_stack_lab/tests/siem_queue_pg_check.py)이며 기존 `termination_dispatch_lab.sh`의 일회용 DB와 `isolated_disposal`을 사용한다.
실제 워커 프로세스·DB 트리거·사설 시험 CA의 HTTPS 수신기·SQLite UID 유일 키를 연결하고, 수신 확인 뒤 PostgreSQL 잠금으로 큐 커밋을 멈춰 SIGKILL/재시작한다.
이 시험 수신기는 MCP 서버가 아니며 실제 SIEM 제품의 저장 검수를 대신하지 않는다. [요구사항·실행 범위](../../research/llm-wiki/analysis/siem-dedup/README.md)를 참조한다.

콘솔의 기존 서버 상태·사유로 중지를 확인할 수 있다. 운영 상세 조회는 `GET /api/ops/status`, 복귀는 `POST /api/ops/servers/{server_id}/resume`와 `{"note":"검토 사유"}`다. 두 API는 `Depends(admin_caller)`로 Console 관리자 인증을 요구한다. 복귀는 `PENDING`까지만 바꾸고 실행기를 자동 재시작하지 않는다. 원인이 남으면 다시 중지한다. 계약 변경은 검토한 잠금 파일 반영 또는 새로운 도입 승인으로 해결한 뒤 복귀한다. 폐기 목록에 있는 식별자는 복귀할 수 없다.

## 서명 폐기 보관과 DB 복원

JWT 발급 권한을 늘리지 않도록 기존 raw 32-byte/base64url Ed25519 방식과 `cryptography`를 재사용하되 `DISPOSAL_PRIVATE_KEY`·`DISPOSAL_PUBLIC_KEY`를 별도로 생성한다. JWT 개인 키는 계속 IdP만 가진다. 게이트웨이·IdP는 폐기 전용 키와 DB 외부 `/disposal` 볼륨을 공유한다.

폐기 대상은 JWT JTI·만료 시각, 갱신 토큰의 SHA-256, 서버 ID, 회수 대상 ID와 해당 서버다. 토큰 값·하위 자격 비밀은 기록하지 않는다. 로그아웃·토큰 철회·갱신 토큰 회전·자격 회수·서버 종결 전에 파일에 선행 기록한다. DB 커밋이 실패해도 이 기록은 되돌리지 않아 보수적으로 차단한다. 기존 DB의 폐기 상태도 시작 시와 주기적으로 보관한다.

`journal.jsonl`은 서명·순번·이전 항목 해시를 가진 추가 전용 파일이다. 별도의 서명된 `head.json`에 전체 바이트 수와 해시를 남겨 끝부분 절단을 탐지한다. 프로세스 간 파일 잠금, 파일 fsync, head 원자 교체, Linux 디렉터리 fsync를 사용한다. 중간 쓰기 실패는 자동 수선하지 않고 차단한다.

시작 시 전체 검증·대조에 실패하면 게이트웨이와 IdP가 준비되지 않는다. 운영 중에도 인증과 계약 확인은 서명 파일을 읽어 DB 복원 직후의 공백을 차단한다. 60초 감시가 `disposal_blocks`와 유효한 폐기 JWT 기록을 복원하고 서버·실행을 다시 중지하며 `approval_events`에 추가한다. 무결성 장애는 운영 로그·심박·원장에 기록한다. 과거 판정 원장은 수정하지 않는다. 외부 제공자의 자격을 재폐기한 증거가 아니라 조직 경로의 재차단 증거다.

최초 배포에서만 솔루션 기기에서 다음 순서로 초기화한다. 기존 보관 파일이 있으면 초기화 명령은 거부한다.

```bash
cd full_stack_lab
./console.sh field init-disposal
./console.sh field up
```

일회용 실습 모드에서는 양쪽 명령에 `--with-lab-mcp`를 붙인다. `field_disposal_journal`·`field_lab_disposal_journal`·기본 `disposal_journal`을 분리하며 DB 백업 복원 때 폐기 볼륨을 되돌리지 않는다. 키와 폐기 볼륨은 DB와 별도로 백업한다. 파일·head·키를 모두 옛 상태로 돌리거나 보관 볼륨 전체를 삭제한 호스트 관리자의 행위는 이 설계만으로 탐지할 수 없다. 별도 보관·변경 통제가 필요하다.

`tests/termination_flow.py`는 폐기 식별자의 복원을 거부하는 것을 확인한다. 폐기 보관을 되돌릴 수 없으므로 전체 회귀는 일회용 랩에서 `TERMINATION_DISPOSABLE_LAB=1 ./console.sh test`로만 실행한다. 종료 시험을 마지막에 두었으며 CI의 초기화·호출 순서도 맞췄다. 로컬에서는 이 명령을 실행하지 않았다.

파일은 매번 전체 검증하므로 장기 보관량에 따른 인증 지연과 초기 이관 비용은 아직 측정하지 않았다. Linux 파일 잠금·디렉터리 내구성, 실제 PostgreSQL 복원, 제품 `cryptography` 연동은 기기 검증 대상이다.
