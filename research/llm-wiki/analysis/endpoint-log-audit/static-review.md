# 엔드포인트 관측 로그 전달 정적 검토

- 검토일: 2026-10-14; 브랜치 `10/14-endpoint-log-wbs`; 기준 HEAD `ab6936c64f3578de8360b840f1928681714fa7bb`
- 범위: endpoint collector, Linux/Windows managed supervisor, Linux OS event cursor, Gateway receiver/persistence, integration projection, Console 렌더링.
- 구분: 소스 경로·조건에 대한 정적 결함/설계 공백이다. 이 검토에서 PJ1 설정·서비스·자격증명을 읽거나 코드를 바꾸거나 런타임 시험하지 않았다. 상세 행·함수·SHA-256·수정 선택·정상/음성 기준은 같은 폴더의 JSON이다.

## 확인 결과

**1. `NETSCAN=0` 또는 netscan 401/403이 정상 종료와 `observer=ok`에 섞인다.** `agent.py::report_listeners`는 스캔 설정이 꺼졌거나 권한/정책이 없으면 `None`을 반환하고, `once()`는 오류 없이 끝난다. Linux/Windows 관리 서비스는 observer 프로세스 exit 0을 전체 `agent.py=ok`로 기록한다. 다만 그 실행은 MCP 설정 inventory를 올렸을 수 있으므로 “프로세스 전체 실패”가 아니라 **리스너·stdio 관측은 미실행**이라고 별도로 보여야 한다. Ghidra PJ1 결과에서도 자동 listener scan/report는 0이었고, 사용자 지시의 일회성 process report만 수신됐다.

**2. snapshot 삭제에는 완전성 보장이 없고 500개에서 조용히 자른다.** 수집기는 설정 파일 오류나 프로세스/소켓 정보원 실패를 빈 결과/부분 결과로 축약할 수 있다. listener 결과는 `findings[:500]`으로 잘리며 API 역시 최대 500개만 받는다. Gateway의 `ingest`와 `ingest_listeners`는 제출된 항목을 upsert한 뒤 제출 목록에 없는 기존 행을 삭제한다. 따라서 수집 실패·부분 가시성·501개 이상 결과가 완전한 전체 스냅샷처럼 취급되면 이전 설정/리스너 행이 사라지고 섀도 집계가 낮아질 수 있다. 각 source의 상태/완전성을 전파하고 **완료된 스냅샷만** 삭제 대조에 사용해야 한다. 대량 결과는 pagination/finalize 또는 incomplete 보존으로 처리한다.

**3. 스캔을 중지해도 지난 리스너가 현재 정책 수치로 남는다.** 스캔 비활성은 아무 listener 보고도 보내지 않아 기존 DB 행이 보존된다. 그 자체는 incomplete scan에서 전부 삭제하는 것보다 안전하지만 `shadow_listener_count_for`는 관측 시각/`last_scan_at` fresh 여부 없이 confirmed/suspected shadow 행을 모두 세며, 지난 scan freshness를 소비하지 않는다. audit row는 보존하되 stale 상태를 분리하고, 정해진 신선도 조건 밖의 행은 현재 정책 신호로 사용하지 않는 방안을 권한다.

**4. 집중된 `미등록·잔존` 화면은 endpoint listener 결과를 계산하지 않는다.** `/api/endpoint/inventory`는 `listeners`를 반환하고 `/api/integrations`의 넓은 MCP·커넥터 목록도 listener row를 포함한다. 그러나 Console의 `ROUTES.coverage` shadow tab은 `inv.entries`만으로 count/chart를 만들고 설정 표도 config entries만 렌더링한다. 따라서 Ghidra 같은 `stdio-process` finding은 넓은 목록에 나타날 수 있지만 listener 전용/미등록 상세 count와 chart에는 나타나지 않는다. 이 탭에 listener panel을 별도로 추가하거나 현재 패널을 설정 inventory 전용으로 명확히 해야 한다.

**5. OS 거부 telemetry producer는 이 코드상 Linux 전용이다.** Linux 서비스는 `os-observer.py`를 주기 실행하고 이 스크립트가 journald의 AppArmor/nft event를 읽는다. Windows managed loop는 `agent.py --once`만 실행하고 Windows 방화벽/실행 거부 event collector가 없다. 따라서 PJ1 Console OS event 1387은 해당 Linux 경로의 증거이지, Windows denial logging의 증거나 플랫폼 전체 성공이 아니다.

## 정상 경로와 캡 경계

`os-observer.py`는 최대 100건씩 보고하고 모든 batch가 성공한 뒤에만 journal cursor를 진행한다. 일부 batch가 먼저 수신된 뒤 후속 요청이 실패하면 다음 시도에서 다시 보낼 수 있지만 Gateway가 `(endpoint_id, event_id)` 충돌을 무시하므로 중복 안전 구조다. 수집기 정상 종료와 이 retry/idempotency 형태는 유지할 가치가 있다.

OS event 화면은 최근 수신 200행으로 제한하고 차트도 이를 명시한다. 반면 integration/device summary의 24시간 거부 수는 `endpoint_os_events` 전체에서 별도로 count한다. 이는 의도된 상세 목록 cap과 전체 기간 집계를 구분하는 구현으로 봤고, 현재 발견사항에는 넣지 않았다. 엔드포인트 설정/리스너 조회도 API 기본 200건 limit이 있으나 잘림 표시와 페이지 토큰이 없다. 특히 전용 shadow 상세 표에서 결과 범위가 200건에 닿으면 누락을 알리기 어렵다. 이는 위 4번 UI 집계/가시성 변경 때 pagination/truncated 표기를 함께 검증할 조건이다.

## PJ1 Ghidra 로그 증거의 범위

기존 PJ1 검수는 UID1000 GhidraMCP 프로세스 1개를 명시적 일회성 관측으로 POST해 endpoint accepted 1·Console shadow/suspected 1을 확인했고 프로세스 종료 뒤 snapshot row를 제거해 기존 빈 상태를 복구했다. 기본 managed `ENDPOINT_NETSCAN=0` 자동 stdio report가 아님을 구분했다. 별도 Linux AppArmor `execution-denied` 이벤트는 `/usr/bin/python3.12` 시도 1건이며, 수동 POST/서비스 재시작 없이 기존 주기 observer를 통해 약35.84초 뒤 Console id1387로 수신됐다. 원본 근거는 JSON `evidence_boundaries`의 `live-observation.json`, `finish-and-managed-denial.json`, `automatic-os-event.json` 경로와 SHA-256이다. 이는 **해당 interpreter denial event** 경로를 입증하나 Ghidra process scan, 자동 stdio forwarding, Gateway MCP 호출 또는 모든 event 전달을 입증하지 않는다.

2차 WBS와 기기 재검증 예상 조건은 JSON `wbs`와 각 finding의 `verification`에 정리했다. 이 subtask에서는 소스만 검토했고 별도 단위/실기기 검사는 실행하지 않았다.
