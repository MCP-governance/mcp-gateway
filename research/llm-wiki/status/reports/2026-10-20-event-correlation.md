# 2026-10-20 이벤트 상관 조회 보강
- 작업자: Codex luna
- 코드 기준: `60afcb1ec8519e3eca4c4e5abae26592efc197df`, 브랜치 `10/20-event-correlation`, 시작 작업 트리 clean
- 근거: G06.01 / DEV-34, [2026-10-15 엔드포인트 증거](2026-10-15-endpoint-evidence.md), [2026-10-13 PJ1 원장 증거](2026-10-13-pj1-evidence.json), [WBS-1015 실험 결과](../../analysis/wbs-1015/lab-results.jsonl), [배포 기록](../../analysis/wbs-1015/deploy.json)
- 완료 조건: 요청/trace ID·판정·전송 의도·동일 장치/주체/시간 창의 엔드포인트 이벤트를 관리자 조회와 감사 상세에서 연결하고, 정확/보조 근거를 드러낸다.

## 결과
`event_correlation.py`에 DB 의존성 없는 상관 투영 함수를 추가했다. `/api/endpoint/correlation`은 decision의 `request_id`·`trace_id`와 같은 요청의 `dispatch_intents`를 포함한다. 엔드포인트 이벤트는 endpoint_agents에 등록된 동일 장치의 소유 주체가 판정 주체와 같고 시간 창 안일 때만 결과에 넣는다. 연결 근거와 정확/보조 수준을 반환하고, 과거 trace ID가 없는 행은 그 상태 그대로 반환한다. 이벤트 원장과 판정 원장은 수정하지 않는다.

감사 상세 탭을 「연관 이벤트」로 바꾸고 판정·전송 의도·OS 이벤트와 근거를 한국어 라벨로 표시한다. 관리자 API의 `Depends(admin_caller)`는 기존 경로를 유지했다. 신규 DB 열과 정책 ID, 의존성은 없다.

문서에는 D-145와 데이터 모델 상관관계를 추가했고, DEV-34 백로그 마지막 상태 칸을 구현/현장 검증 대기로 갱신했다. `status/current.md`는 변경하지 않았다.

## 검증
| 확인 종류 | 명령·환경 | 결과 | 근거 |
| --- | --- | --- | --- |
| 순수 함수 회귀 | `python -m unittest full_stack_lab/tests/event_correlation_check.py` (Windows Python 3.10) | 5건 통과 | `full_stack_lab/tests/event_correlation_check.py` |
| Python 구문 | `python -m py_compile full_stack_lab/gateway/app/endpoint_plane.py full_stack_lab/gateway/app/event_correlation.py full_stack_lab/tests/event_correlation_check.py` | 통과 | 로컬 |
| JavaScript 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 로컬 |
| PostgreSQL/관리자 API 통합 | 미실행 | 미실행 | 게이트웨이 이미지 필요 |
| 콘솔 브라우저 렌더링 | 미실행 | 미실행 | 브라우저/솔루션 기기 검증 필요 |
| 솔루션 배포·PJ1 실기기 | 미실행 | 미실행 | 소유자 규칙에 따라 담당자가 수행 |

## 실패·미완료·한계
OS 이벤트 스키마에는 trace/request ID가 없어 해당 연결은 같은 장치·같은 주체·시간 창의 보조 근거이며 인과 증명이 아니다. 시간만 겹치는 다른 장치 또는 다른 주체의 이벤트는 제외한다. 과거 trace ID 부재는 보완 추정하지 않는다. 기존 역방향 엔드포인트 기록 조회의 PostgreSQL 회귀는 이번 범위에서 실행하지 않았다.

## 다음 작업
게이트웨이 이미지에서 `python -m unittest tests/event_correlation_check.py`와 기존 `tests/endpoint_evidence_pg_check.py`를 실행하고, 솔루션 기기 배포 후 PJ1 하네스 호출로 관리자 API와 실제 OS 이벤트 결속을 확인한다. 콘솔의 실제 브라우저 렌더링도 확인한다.

## 사용자 입력
없음.
