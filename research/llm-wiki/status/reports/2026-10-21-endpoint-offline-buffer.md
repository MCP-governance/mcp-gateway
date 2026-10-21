# 2026-10-21 엔드포인트 오프라인 관측 버퍼

- 작업자: Codex luna B
- 코드 기준: `d3238dccd6a6fb7266a7b9201f5b133e2a025aea`; 시작 작업 트리 clean. `.git` 쓰기 차단으로 전용 브랜치를 만들지 못함. 원격 HEAD 조회는 GitHub 네트워크 차단으로 실패했고 로컬 `origin/HEAD`는 `origin/main`.
- 시작 근거: DEV-80 / D-182 예약, direction-1020 §3, GB/T 45654—2025 6.7 b), D-128·D-157 SIEM UID, D-159 토큰 캐시, D-172 일시 격리.
- 해결할 문제와 완료 조건: 관리형 Linux/Windows OS 이벤트를 안전한 제한 버퍼에 보관하고 재연결 때 재전송하여 로컬 검증에서 누락·중복 0을 확인한다. 용량 초과·부분 행·재시작·시계 역행을 다룬다.

## 결과

`endpoint-agent/offline_buffer.py`에 표준 라이브러리 기반 내구 JSONL 큐를 추가했다. 크기 8 MiB, 10,000 이벤트, 7일 보존 한도를 둔다. 상한 초과 시 이벤트를 덮어쓰지 않고 수집 커서를 유지해 관측 수집을 멈춘다. 버퍼에 넣지 못한 건수와 보존 만료로 지운 건수를 합친 미적재·만료 건수는 재연결 뒤 stable UID·건수·사유로 새 append-only `endpoint_buffer_events`에 기록한다. 용량 초과 시 원천 커서가 유지되므로 미적재 이벤트가 곧 영구 유실을 뜻하지 않는다. 큐에는 정제 이벤트, 원본 SHA-256, 수집 시각만 저장한다.

Linux는 journal cursor를 수집용/ACK용으로 분리했다. Windows도 event record ID cursor를 분리한다. 먼저 기존 큐를 전송하고, 수신 ACK가 확인되고 큐가 비워진 뒤에만 ACK cursor를 갱신한다. 기존 서버의 7일 `raw_sha256` replay 제거와 `(endpoint_id,event_id)` unique 키를 재사용한다. SIEM UID는 아직 Gateway 행이 없는 엔드포인트 이벤트에 적용할 수 없어 새 UID 체계를 추가하지 않았다.

게이트웨이 미적재·만료 건수 표가 추가된 이유는 기존 `endpoint_agents.detail.observation`이 마지막 상태를 덮어써서 건수 이력을 남기지 않기 때문이다. OS 이벤트 표와 감사 원장에는 가짜 OS 차단이나 MCP 판정을 만들지 않는다. 버퍼는 heartbeat/정책 판단을 대체하지 않으며, 연결 공백의 기존 180초 일시 격리는 그대로 둔다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| Python 구문 | `python -X utf8 -m py_compile endpoint-agent/agent.py endpoint-agent/offline_buffer.py endpoint-agent/os-observer.py endpoint-agent/os-observer-windows.py endpoint-agent/managed-linux.py endpoint-agent/managed-windows.py endpoint-agent/runtime-check.py endpoint-agent/tests-windows/test_windows_kit.py full_stack_lab/gateway/app/agent_service.py full_stack_lab/gateway/app/main.py full_stack_lab/gateway/app/endpoint_plane.py full_stack_lab/tests/endpoint_offline_buffer_check.py` (Python 3.10.0) | 통과 | 명령 종료 코드 0, 출력 없음 |
| DEV-80 단위 회귀 | `python -X utf8 full_stack_lab/tests/endpoint_offline_buffer_check.py` | 통과, 10건 | `Ran 10 tests ... OK` |
| Windows OS observer 회귀 | `python -X utf8 full_stack_lab/tests/windows_os_observer_check.py` | 통과, 7건 | `Ran 7 tests ... OK` |
| Windows 설치 키트 회귀 | `python -X utf8 endpoint-agent/tests-windows/test_windows_kit.py` | 미완료, 16건 실행 | 10건 통과, 5건 실패·1건 오류. PowerShell 스크립트 실행 정책이 dot-source를 차단하고 ACL 검사가 실패해 환경 차단으로 분류. 제품 회귀 판정 아님 |
| Windows observer parser self-check | `python -X utf8 endpoint-agent/os-observer-windows.py --config C:/nonexistent/observer.json --self-check` | 통과 | `Windows OS observer parser check OK` |
| endpoint evidence 회귀 | `python -X utf8 full_stack_lab/tests/endpoint_evidence_check.py` | 실행 불가 | Python 3.10에 `datetime.UTC`가 없어 import 실패. 이 코드는 3.11+ 필요 |
| Gateway 보고 모델 | 새 report payload 모델 구성 검사 | 실행 불가 | 동일한 Python 3.10 `datetime.UTC` import 차단 |
| pyflakes | `python -m pyflakes --version` | 미완료 | 모듈이 설치되어 있지 않음 |
| DB/장치/하네스 | 솔루션 기기·PJ1 실행 금지 범위 | 미실행 | 요청에 따라 배포·실기기·PJ1 시험 없음 |

단위 수신기는 메모리 콜백이며 실제 Gateway/PostgreSQL dedup·재부팅·전원 손실 증거가 아니다. 실제 장치 ACL, OS 수집기의 프로세스 kill, 여러 collector 경합, 미적재·만료 건수 행의 DB append-only 동작도 미검증이다.

## 실패·미완료·한계

- 저장장치 전체 손실, 시계 역행 중 보존 연장, 게이트웨이 연결이 계속 끊긴 상태에서 7일/용량 한도에 닿았을 때는 보존 만료 건 또는 버퍼 미적재 건을 기록하고 후속 수집을 중지한다. 용량 초과 시 수집 커서를 고정해 원천 이벤트를 재시도한다.
- 나중에 적재된 건이 이 수치에서 빠지지 않는다. 미적재·만료 건수는 같은 보고 uid 안에서만 단조 증가하며, 보고가 성공하면 새 uid로 다시 센다.
- `endpoint_buffer_events`의 애플리케이션 경로는 insert-only지만 DB 관리자 직접 UPDATE/DELETE를 막는 권한·트리거 검증은 하지 않았다.
- Linux managed installer와 Windows 허용 파일 목록에 새 모듈을 포함했다. 설치 번들 재생성·승인 해시·실기기 활성화는 미실행이다.
- 신규 작업 브랜치 생성은 `.git` 읽기 전용으로 거부됐다. 시작 HEAD 변경 없이 파일을 수정했다. 커밋·push 하지 않았다.

## 다음 작업

메인이 솔루션 기기에서 승인된 설치 키트 재생성·파일 해시 반영 후 Linux/Windows 실제 오프라인·재시작·재연결과 Gateway/PostgreSQL 중복/미적재·만료 건수 행 기록을 확인한다. PJ1에서 OS 관측 호출과 180초 일시 격리 유지도 별도 확인한다.

## 사용자에게 필요한 입력

없음. 기기 시험은 사용자가 지시한 대로 메인이 담당한다.
