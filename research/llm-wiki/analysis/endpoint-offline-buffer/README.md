# DEV-80 엔드포인트 오프라인 관측 버퍼

기준 commit: `d3238dccd6a6fb7266a7b9201f5b133e2a025aea` (작업 트리 clean). 작업 브랜치 생성은 읽기 전용 Git 메타데이터에서 거부됨. 코드·시험·보고 근거는 워크스페이스에 작성했다.

## 결정 범위

관리형 Linux/Windows OS 차단 관측만 디스크에 임시 보관한다. 설정 인벤토리, 리스너 스냅샷, heartbeat, 인증 토큰은 오프라인 큐에 넣지 않는다. 토큰은 기존 자격 경계를 따라 온라인 전송 시에만 사용한다. 버퍼는 서버 정책 판정이나 오프라인 허용을 만들지 않는다.

| 원자 요구사항 | 근거 | 구현 위치 | 로컬 확인 / 한계 |
| --- | --- | --- | --- |
| OBUF-01 정상 전송 후 큐 행을 제거한다 | 기존 `POST /api/endpoint/os-events`; `endpoint_os_events` | `offline_buffer.flush`, Linux/Windows 관측기 | 콜백 수신기 단위 시험. 실제 Gateway/DB ACK 미실행 |
| OBUF-02 연결 실패 중 이벤트를 내구 저장하고, 재연결 뒤 누락·중복 없이 전달한다 | DEV-80 원문; 기존 서버 `raw_sha256` 7일 replay 제거와 `(endpoint_id,event_id)` UNIQUE | `EventBuffer.enqueue`, `flush`; Linux `os-observer.main`; Windows `collect` | 로컬 수신기 집합 대조 7/7, 중복 0. 별도 프로세스 두 개 경합, 실제 서버 응답·디스크 오류는 미실행 |
| OBUF-03 버퍼가 8 MiB·10,000건 상한을 넘으면 수집을 멈추고 미적재 건수를 남긴다 | direction-1020 §3 DEV-80의 상한 필요; 저장소 fail-closed/조용한 유실 금지 원칙 | `MAX_BYTES`, `MAX_EVENTS`, `BufferFull`; Gateway `endpoint_buffer_events` | 2건 한도에서 1건 미적재·커서 유지 확인. 실제 PostgreSQL append-only 행 미확인 |
| OBUF-04 7일 지난 행 폐기를 기록한다 | DATA_MODEL §5: `raw_sha256` 7일 재전송 중복 | `EventBuffer.pending`, `drop_report`; status API의 UID 보고 | 8일 경과 시 미적재·만료 건수 1 확인. 장치/Gateway 시각 합의는 보장하지 않음 |
| OBUF-05 잘린 마지막 JSONL 행은 복구하고, 완전한 손상 행은 실패한다 | 프로세스 kill/부분 기록 요구 | `EventBuffer._read`, `_atomic_write` | 끝부분 부분행 제거 후 이전 행 보존 확인. 중간 손상은 조용히 건너뛰지 않음 |
| OBUF-06 재부팅·프로세스 재시작 뒤 버퍼와 수집 커서를 이어간다 | OS journal cursor / Windows event record ID 구조 | `.journal-buffer-cursor`, `.os-buffer-cursor.json`, 버퍼 파일 | 새 `EventBuffer` 인스턴스에서 재로딩 확인. 실기기 프로세스 강제 종료 미실행 |
| OBUF-07 시계 역행 때 보존 기한을 앞당기지 않는다 | 시간 역행 완료 조건 | `clock_high_water` 논리 UTC | 30일 역행 가상 시각 후 행 보존 확인. 실제 OS 시각 변경 미실행 |
| OBUF-08 비밀·원문 로그/XML을 디스크에 쓰지 않는다 | 기존 `seal_os_event`는 원문 대신 SHA-256만 외부 전송; D-86~88 provenance | `seal_os_event`; buffer secret-key 검사; Linux mode 0600·Windows 설치 폴더 ACL 상속 | 토큰/원문 키 거부 단위 시험. 장치 ACL·디스크 암호화 검증은 미실행 |
| OBUF-09 오프라인 heartbeat 격리를 유지한다 | D-172, D-159 | 변경한 managed observer 호출은 별도 서비스 경로; heartbeat 코드·만료 설정 변경 없음 | 정적 호출 경로 검토. 실제 180초 정책 전이는 미실행 |

## 코드 심볼과 판본

기준은 위 기준 commit의 checkout에 적용한 작업 변경이다. 새 모듈·스키마는 이번 브랜치 변경이며 아직 통합 commit/배포 판본은 없다.

| 위치 | 핵심 심볼·행 | 역할 |
| --- | --- | --- |
| [`offline_buffer.py`](../../../../endpoint-agent/offline_buffer.py#L12) | `MAX_BYTES`, `MAX_EVENTS`, `MAX_AGE` L12–14; `EventBuffer` L71; `pending` L138; `enqueue` L156; `flush` L204 | 상한·logical clock·손상 마지막 행 복구·fsync/atomic replace·멱등 UID |
| [`os-observer.py`](../../../../endpoint-agent/os-observer.py#L94) | `main` L94; buffer cursor L131; durable enqueue L154; status report L184 | Linux journal 수집 커서와 ACK 커서 분리 |
| [`os-observer-windows.py`](../../../../endpoint-agent/os-observer-windows.py#L216) | `collect` L216; buffer cursor L224; enqueue L311; ACK cursor L350 | Windows EventRecordID 수집 커서와 ACK 커서 분리 |
| [`main.py`](../../../../full_stack_lab/gateway/app/main.py#L1304) | `ObservationReport` L1304; `/api/endpoint/observation-status` L1585 | 미적재·만료 건수·사유·stable UID 형식 검증 및 전달 |
| [`endpoint_plane.py`](../../../../full_stack_lab/gateway/app/endpoint_plane.py#L261) | `observation_status` L261; `endpoint_buffer_events` INSERT L273 | 상태 보고 트랜잭션과 append-only 미적재·만료 건수 기록 |
| [`v2_tables.sql`](../../../../full_stack_lab/gateway/app/v2_tables.sql#L147) | `endpoint_buffer_events` L147–157 | 보고 UID unique constraint와 미적재·만료 건수·사유 제약 |
| [`agent_service.py`](../../../../full_stack_lab/gateway/app/agent_service.py#L364) | `KIT_FILES` L364–367 | 장치 설치 키트에 새 표준 라이브러리 모듈 포함 |
| [`managed-linux.py`](../../../../endpoint-agent/managed-linux.py#L207), [`managed-windows.py`](../../../../endpoint-agent/managed-windows.py#L562) | 설치 복사 목록 | 보호 설치 경로에 관측 버퍼 코드 배치 |

## 출처와 버전

1. [개발 방향 10-20, §3 DEV-80](../direction-1020/README.md#3-새-기술-목표): “OS 차단·관측 기록을 보호 위치에 쌓았다가 재연결 때 원본 해시와 함께 전송”; 완료 조건은 누락 없음·중복 0, 원본 해시 7일 중복 규칙. D-182가 예약됨.
2. GB/T 45654—2025 6.7 b), [LIB-M32 분석](../../papers/LIB-M32.md#조항별-요구와-mint-연결): 단말 배포 모델의 안전 로그 수집·보존 및 네트워크 연결 시 업로드 또는 로컬 내보내기. 표준은 권장성이고, 이 조항은 단말 모델을 대상으로 해 OS 차단 관측 버퍼 전체의 적합성 근거로 확대하지 않는다. 원문 PDF는 저장소의 `local-sources/` 로컬 전용 자료여서 복제하지 않았다.
3. [데이터 모델 §5](../../../../docs/ai/DATA_MODEL.md#5-엔드포인트-평면): OS 이벤트 원본 해시 7일 dedup, 관측 원장과 `decisions` 분리.
4. [D-128/D-157 및 SIEM 중복 분석](../siem-dedup/README.md): SIEM UID는 게이트웨이 DB 원장 행 ID+chain hash 기반이라 아직 DB 행이 없는 엔드포인트 오프라인 이벤트에 직접 적용할 수 없다. 해당 UID 설계를 복제하지 않고 기존 endpoint OS 이벤트 원본 해시 UID와 DB 유일 키를 재사용한다.
5. [D-159](../../../../docs/ai/DECISIONS.md#d-159-관리형-linux-토큰-헬퍼-캐시를-정상-heartbeat-주기-안에-유지한다-2026-10-20)·[D-172](../../../../docs/ai/DECISIONS.md#d-172-오래된-보고-장치는-영구-격리하지-않는다-2026-10-20): 토큰 캐시와 heartbeat 공백 처리, 180초 일시 격리. 오프라인 버퍼는 둘의 통제 의미를 변경하지 않는다.
6. 기존 코드: `endpoint-agent/agent.py::seal_os_event`; `endpoint-agent/os-observer.py::event/main`; `endpoint-agent/os-observer-windows.py::parse_event/collect`; `full_stack_lab/gateway/app/endpoint_plane.py::ingest_os_events`; `full_stack_lab/gateway/app/main.py::EndpointOSEvent/endpoint_os_report`; `full_stack_lab/gateway/app/v2_tables.sql::endpoint_os_events`.

## 구현 선택과 한계

- 새 런타임 의존성은 없다. JSONL 파일과 표준 라이브러리 `fsync`/atomic replace를 쓴다. 큐 행에는 정제된 `event`와 `provenance.raw_sha256`만 저장한다. TLS 자격·장치 키·토큰·수집 원문은 큐 페이로드에 포함되지 않는다.
- 수집 커서와 게이트웨이 ACK 커서를 분리했다. 버퍼 쓰기 뒤 수집 커서는 진행할 수 있지만, ACK 커서는 모든 적재 행이 비워진 뒤에만 따라간다. 재시작 직후 기존 큐를 먼저 재전송한다.
- 논리 큐 상한은 8 MiB, 10,000건, 7일이다. atomic replace 중에는 기존 큐와 임시 파일이 함께 있어 순간 사용량이 최대 약 16 MiB와 작은 메타 파일 크기까지 늘 수 있다. 재시작 시 같은 버퍼 이름의 남은 임시 파일을 지운다. 용량 초과 이벤트는 버퍼에 넣지 않고 원천 커서를 고정해 후속 수집을 멈추며, 같은 이벤트 묶음의 재시도는 미적재·만료 건수에 중복 더하지 않는다. 버퍼에 미적재된 건수와 보존 만료 건을 기록한다. 시간 역행은 기록된 UTC high-water 아래로 보존 시각이 내려가지 않게 처리한다.
- 손상된 완전 행은 수집을 실패시켜 수동 조사 대상이 된다. 마지막 불완전 행은 원천 커서가 아직 그 행을 넘지 않았으므로 잘라낸 뒤 재수집할 수 있다.
- 미적재·만료 건수 보고를 위한 `endpoint_buffer_events`는 새 테이블이다. 기존 `endpoint_agents.detail.observation`은 최근 상태만 덮어쓰고, `decisions`는 도구 판정 원장이라 기기 관측을 위조해 넣을 수 없다. 표는 `(endpoint_id,event_uid)` 유일 키와 INSERT-only 경로로 재시도 중복을 막는다. 실제 DB 권한을 통한 직접 UPDATE/DELETE 방지는 별도 운영 DB 권한에 의존한다.
- 나중에 적재된 건이 이 수치에서 빠지지 않는다. 값은 같은 보고 uid 안에서만 단조 증가하고, 보고가 성공하면 새 uid로 다시 센다. 용량 초과 건수와 보존 만료 건수가 한 값에 섞이면 사유는 mixed다.
- 추가 한계: 파일시스템/저장장치의 실제 내구성, 디스크 전체 손실, 장치 키 회전 중 재전송, 여러 collector 프로세스 동시 실행 잠금, queue 폭발/수신 지속 장애, 실제 Windows ACL과 Linux 소유권, OS 이벤트 로그 자체의 회전/유실, server raw-hash dedup 경합은 로컬 테스트로 증명되지 않았다. 보존 기한은 클럭이 뒤로 간 동안 연장될 수 있다.
- 이 구현의 상태는 코드·로컬 검사 완료로 한정한다. 기기 배포, PJ1, 실제 PostgreSQL, SIEM, 독립 효과 검증은 모두 미실행이다.
