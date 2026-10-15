# 2026-10-15 엔드포인트 증거·완전성·망 품질 (작업 A)

- 작업자: Claude Code(Sonnet 5.5) 서브에이전트. 메인 에이전트가 조율하고 병합한다.
- 코드 기준: 브랜치 `10/15-wbs-endpoint-evidence`, 시작 `8cf3d08`, 작업 후 `9c91d50`(보고서 커밋 별도). 푸시·병합·다른 워크트리 변경 없음.
- 시작 근거: WBS G05.03·G05.04·G06.01·G06.03·G06.04·G01.04, 백로그 DEV-18·DEV-22·DEV-30, [10-14 로그 경로 수정](2026-10-14-endpoint-telemetry-fix.md), 결정 D-85–D-89.
- 해결할 문제와 완료 조건: 최근 200건만 보이던 목록의 전체 건수·페이지 이동, 저장 레코드의 원본→projection→저장 해시 사슬, 수집 출처 라벨과 재전송 중복, 호출과 엔드포인트 기록의 연관, 엔드포인트→게이트웨이 지연 표기, 정상 기동 거부 잡음 분류, 통제 밖 계정 라벨.

## 결과

구현 위치와 계약만 적는다. 실기기 동작은 아래 검증 표의 층을 따른다.

| 항목 | 상태 | 구현 |
| --- | --- | --- |
| G06.03 / DEV-18 완전성 | 구현·격리 DB 확인 | `endpoint_plane.inventory_page/listeners_page/os_events_page/observations_page`: `rows`·`total`·`limit`·`next_cursor`, `id DESC` 키셋, 최대 200건. 요약 API는 기존 키 유지 + `pages`. 신규 `GET /api/endpoint/inventory/{entries,listeners,os-events}`, `/observations`. Console: "전체 N건", `일부 표시 M건` 표식, 이전/다음. 24시간 차단 집계는 유지하되 OS 채널이 최근 성공일 때만 숫자, 아니면 `수집 중단`(`kernel_denials_state`) |
| G06.04 + G01.04 출처 | 구현·격리 DB 확인 | 에이전트가 `raw_sha256`·`projection_sha256`·`transformations`·`collector` 전송, 서버가 저장한 필드만의 정규 JSON으로 재계산해 `match`/`mismatch`/`unreported` 기록. `GET /api/endpoint/records/{config,listener,os-event}/{id}`. Console 상세 "출처" 탭에 짧은 해시와 일치/불일치. 하트비트의 `install_receipt`에 `provider_artifact_sha256`(Gateway가 렌더링)와 `installed_sha256`(장치 보고)를 분리 보관 |
| G05.03 출처 라벨 | 구현·격리 DB 확인 | `origin` automatic/manual/os_event. 서비스(`observer.json`·연속 실행)=automatic, `--once` 손수 실행=manual, OS 이벤트=os_event. 라벨 없는 옛 보고는 manual. 7일 안 같은 원본 해시는 새 행이 아님(`duplicates` 응답). Console 라벨 자동 수집/수동 보고/운영체제 이벤트 |
| G06.01 연관 | 구현·격리 DB 확인 | `GET /api/endpoint/correlation?decision_id=` 또는 `?kind=&record_id=`, `window_seconds` 10–3600(기본 300). 기록은 합치지 않고 각자 `source`·`at`. 장치(`decisions.client.device_id`)와 사용자(`user_token`=`owner_token`) 둘 다 일치할 때만 연결. `traceparent`는 형식 검증 후 `decisions.client`에 기록만. Console 호출 상세·엔드포인트 기록 상세에 "연관 기록" 탭 |
| DEV-22 망 품질 | 구현·격리 DB 확인(루프백 프로브) | `agent.measure_gateway`: TCP 연결 5회 + `GET /api/health` 1회(설정된 Gateway 주소만). p50/p95(최근접 순위), 지터(연속 표본 차 평균), 실패율. 하트비트의 `network_quality`를 서버가 검증(NaN·음수·6만 ms 초과·분위수 역전·±10분 밖 시각 거부, 하트비트는 유지하고 응답에 `rejected`). `endpoint_network_samples` PK `(endpoint_id, measured_at)`, 적재 시 7일 지난 행 삭제. `GET /api/endpoint/network-quality`는 지정된 형태 그대로, `stale`=180초 초과. Console 엔드포인트 표 `지연`·`실패율`(fresh 아니면 `—`) |
| DEV-30 잡음 | 구현·합성 입력 확인 | `os-observer.py`가 `comm`(시도한 프로세스)·프로파일·파일명을 보내고 `harness_startup`/`blocked_attempt`/`unknown` 분류. 시도가 `claude`/`codex`이고 대상이 시스템 경로의 `git`·`claude`·`codex`일 때만 기동. 프로파일·nft 변경 없음. Console 하네스 기동/차단된 시도/확인 불가 |
| G05.04 | 구현·자체 점검 | `integrations.device_state`가 `unmanaged_accounts[{name,uid,privileged_groups,scope:"out_of_scope"}]`를 돌려주고 우회 경로 문구가 `… 통제 범위 밖`. Console 엔드포인트 표에 그대로 표시 |

API 계약은 [docs/API.md](../../../../docs/API.md), 열·표는 [DATA_MODEL](../../../../docs/ai/DATA_MODEL.md), 결정은 D-85–D-89, 수집기 계약은 [endpoint-agent/README.md](../../../../endpoint-agent/README.md).

## 검증

환경: Windows 11 호스트(Python 3.12 venv, Node), 솔루션 기기의 **일회성 PostgreSQL 18 컨테이너**와 기기에 이미 있는 gateway 이미지. 운영 DB·`~/mcp-gateway`·기존 컨테이너·PJ1은 건드리지 않았다.

| 확인 종류 | 명령·환경 | 결과 | 층 |
| --- | --- | --- | --- |
| 정적 검사 | `pyflakes gateway/app/*.py tests/*.py ../endpoint-agent/*.py` | 오류 0 | 로컬 |
| JS | `node --check console.js`, `node --test tests/console-state.test.mjs` | 13/13 통과(신규 3) | 로컬 단위 |
| 열린 API | `python tests/open_endpoints.py` | 통과(무인증 1개, 인증 필요 64개) | 로컬 정적 |
| 증거 단위 | `python tests/endpoint_evidence_check.py` | 24/24 통과 | 단위. 기록 수신은 SQL 기록용 대역, 프로브는 루프백 stdlib HTTP 대역(Gateway 아님) |
| 기존 엔드포인트 | `endpoint_inventory_check` 6, `endpoint_collector_check` 8, `endpoint_snapshot_check` 21, `windows_os_observer_check` 7(대역에 `seal_os_event` 위임 추가) | 전부 통과 | 단위 |
| 자체 점검 | `python -m app.integrations`, `python -m app.endpoint_plane`, `agent.py --self-check`, `os-observer.py --self-check` | 통과 | 단위 |
| 변이 확인 | 서버 projection에서 `denial_class`를 빼고 단위 검사 실행 | 1건 실패로 검출(원복 확인) | 단위 |
| **격리 PostgreSQL** | `tests/endpoint_evidence_pg_check.py`, 일회성 `postgres:18-alpine` + gateway 이미지(코드는 읽기 전용 마운트), 새 DB에 스키마 4개 적용 + `v2_tables.sql` 2회 재적용 | 17개 확인 통과, 종료 코드 0 | 실제 PostgreSQL + 실제 수신 코드 + 실제 수집기 코드. 실제 Gateway·MCP·단말은 아님 |
| Console 렌더링 | 실제 정적 Console을 임시 스텁 서버(합성 JSON)로 띄워 통제 범위 화면에서 페이지 이동·상세 서랍·지연 열 확인 | 오류 로그 없음, 의도한 문구 | 렌더링 대역. 제품 Console 배포 증거 아님 |

격리 DB 확인 내용: 450건 설정·260건 리스너·230건 OS 이벤트를 200건 창으로 읽을 때 총계가 따로 나오고 커서로 겹침·누락 없이 끝까지 걷기, 페이지 사이에 행이 들어와도 둘째 쪽 불변, 에이전트 해시=서버 재계산 해시(저장 열만으로 재계산) 일치와 변조 시 불일치·옛 보고 미보고, `origin` CHECK, 같은 원본 해시 재전송 중복(7일 창 안/밖), 같은 장치·같은 사용자·시간 창 연관(창 밖·다른 사용자·장치 미바인딩 제외, 반대 방향 조회), 감사 원장 UPDATE 거부 유지, 표본 적재·7일 삭제·동일 시각 재전송 무시, `network-quality` 키 정확성·fresh/stale/unknown·24시간 요약 값, 설치 영수증 두 역할. 컨테이너·네트워크·`/tmp/wbs-a-*`는 종료 때 모두 제거했다(확인함).

## 실패·미완료·한계

- **실기기 미검증.** PJ1 Linux 단말·Windows 단말에서 새 수집기를 돌리지 않았다(메인 에이전트의 병합 후 검증 몫). `managed-windows.py`·`os-observer-windows.py` 변경은 구문·단위 대역만 확인했다. `managed_enrollment_check.py`는 실제 스택(agent-service)이 필요해 실행하지 못했다.
- **분류 규칙은 합성 저널 줄로만 확인.** AppArmor `comm`이 스레드 이름이나 16자 잘림일 수 있고, Claude Code·Codex의 실제 기동 거부 줄이 이 규칙과 같은지는 PJ1의 실제 이벤트로 확인해야 한다. 사용자 쓰기 경로의 같은 이름 바이너리는 `blocked_attempt`로 본다.
- **망 품질 측정은 루프백에서만.** 실제 Tailscale/HTTPS 경로, 일반 계정의 nft 경로와의 차이는 확인하지 않았다. 지연은 TCP 연결 시간이고 HTTP 시간은 실패 판정에만 쓴다. 실패율은 패킷 손실이 아니다.
- **해시의 의미.** 서버는 원본 해시를 검증할 수 없고, 설정 항목의 원본 해시는 `env`·`headers`를 제외한다. 침해된 root에는 증명이 아니다. 출처 라벨(자동/수동)은 장치 키 소유자의 자기 신고다.
- 옛 행(`origin`·`provenance` NULL)은 화면에서 `—`이다. 이전 데이터를 채우지 않았다.
- 사용자·엔드포인트 화면(`people`)의 엔드포인트 표에는 지연 열을 넣지 않았고 통제 범위의 엔드포인트 표에만 넣었다. 개요 요약은 메인 에이전트가 `GET /api/endpoint/network-quality`로 추가한다.
- 위키 점검 `check_wiki.py`는 이 변경으로 `endpoint-agent/agent.py`·`managed-linux.py`·`managed-windows.py`·`endpoint_plane.py`의 위협 매핑 해시가 달라졌다고 보고한다(`map_threats.py` 재실행·검토 필요, 공유 위키 파일을 바꾸므로 실행하지 않았다). `analysis/local-tools/*`의 오류는 이 작업과 무관하다.
- 위키 `status/current.md`·`backlog.md`·`repository-snapshot.*`·`analysis/development-wbs/*`는 지시대로 건드리지 않았다. DEV-18·22·30과 WBS 점수 갱신은 메인 에이전트가 결정한다. 이 보고서가 완료를 뜻하지 않는다(5단계 중 구현·회귀만 해당).
- 병합 시 주의: `v2_tables.sql`(메인의 `decisions.timings`와 같은 파일, 서로 다른 구간), `console.js`(개요 패널과 다른 구간), `agent_service.py`는 건드리지 않았다. 변경 파일의 줄바꿈을 LF로 바꿨고 Git이 정규화하므로 diff에는 보이지 않는다.

## 다음 작업

1. 병합 후 솔루션 기기에 배포하고 PJ1에서 새 수집기로 자동 수집·`harness_startup` 분류·지연 열·해시 일치를 확인한다(DEV-18·DEV-30·DEV-22).
2. Windows 기기에서 `network_quality`와 이벤트 해시 일치를 확인한다.
3. 필요하면 `people` 표에 지연 열을 추가하고 개요 요약에 `network-quality`를 연결한다.

## 사용자에게 필요한 입력

없음. 실기기 검증에는 PJ1 접근과 Windows 시험 기기가 필요하다(자격 값은 이 문서에 쓰지 않는다).
