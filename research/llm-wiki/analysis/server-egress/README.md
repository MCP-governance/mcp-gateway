# DEV-20 서버 외부 통신과 호출 상관

2026-10-20 · Codex sol · `10/20-server-egress` · 시작 `89aad130cefc290c2705aff4954086d58d270381`.
설계 결정 [D-155](../../../../docs/ai/DECISIONS.md), [작업 보고](../../status/reports/2026-10-20-server-egress.md).
아래 구현은 소스/대역 시험 범위다. 과거 실기기 증거를 이번 코드 통과로 재사용하지 않는다.

## 시작 시 코드 목록

| 경로·심볼 | 기존 통제·기록 | 호출 연결과 공백 |
| --- | --- | --- |
| `full_stack_lab/runtime/worker.py`의 `start`, `mcp_run_args` | 서버별 `--internal` 망, 게이트웨이와 실행기만 직접 연결. 서버 cap-drop·비특권 UID·읽기 전용·HTTP(S)_PROXY | 서버 컨테이너 자체에 nftables를 설치하지 않는다. 프록시를 무시한 직접 소켓은 내부 망 격리에 의존 |
| 같은 파일 `egress_filter`, `egress_run_args`, `sync_egress`, `destinations` | tinyproxy exact-host ERE, 빈 목록 `^$`, 프록시만 edge 망 연결, 심사한 모든 도구 목적지 합집합의 해시가 바뀌면 프록시 재생성 | 이전에는 연결/거부 사건을 DB로 수집하지 않음. 도구 하나의 목적지보다 서버 합집합이 넓을 수 있음 |
| `full_stack_lab/model-proxy/tinyproxy.conf` | `LogLevel Connect`, `ConnectPort 443`, `FilterDefaultDeny Yes`, `FilterURLs Off` | Caddy는 이 서버→API 경로의 출구가 아님. 일반 HTTP의 포트 전체 제한·DNS/IP 고정은 별도 문제 |
| `full_stack_lab/runtime/worker.py`의 `event` | 빌드·활성·실패·중지를 `approval_events`에 추가 | 실행 수명 기록이며 외부 API의 성공·실패·자격 사용 증거 아님 |
| `full_stack_lab/supply_chain/intake_worker.py:215`의 `validate` | 고정 소스 확보, Syft·Trivy·Semgrep·Gitleaks 및 종료 조건 검사 | 후보 MCP 코드를 실행하지 않는 소스 검사. 실행 서버 egress 사건의 수집기가 아님 |
| `full_stack_lab/gateway/app/destination.py` (D-116), `pac.py:165`의 `transfer_binding` (D-132) | 게이트웨이 발신 DNS/IP 검사와 최종 전송 목적 결속 | 서버의 자체 HTTP 클라이언트에 같은 transport를 자동 주입하지 않음 |
| `endpoint_plane.py`의 `correlate`, `event_correlation.py` (D-145) | 원장↔전송 의도는 요청 ID, 엔드포인트는 장치·주체·시간 보조 근거 | 기존 조회에 실행기 출구 사건은 없었음 |

D-114의 과거 프로브 5종(허용 200, 미심사 403, 메타데이터 403, 직접 우회 실패 2종)은
[10-15 보고](../../status/reports/2026-10-15-dev38-runtime.md)와 [당시 증거](../wbs-1015/dev38-runtime.json)에 있다.
이것은 신규 `tools/call` 상관이나 실제 API 업무 효과를 입증하지 않는다.

## 선택한 보강과 증거 계약

| 원자 요구사항 | 현재 코드 접점 | 검증 조건·시험 이름 | 실제 효과 |
| --- | --- | --- | --- |
| SE-01 목적지·결과 분리 | `server_egress.py:26` `parse_log` | `test_connected_denied_failed_are_distinct_and_not_business_effects` | connected는 TCP 접속, blocked는 필터 거부. 업무 성공 미확인 |
| SE-02 원문 최소화 | 같은 함수 | `test_no_urls_credentials_header_or_forged_multiline_survive`, 잘못된 시각/포트 음성 | 요청 URL/쿼리/헤더를 새 사건으로 저장하지 않음. 기존 Docker 원본 로그의 비밀 제거를 주장하지 않음 |
| SE-03 실행 위치 결속·재수집 | `runtime/worker.py:366` `collect_egress`, 기존 `event` | 다른 runtime 표식 거부, 중복/새 컨테이너/오래된 수집기/커밋 응답 유실/복구 | runtime·세대·컨테이너·이미지 ID 기록, 정확히 한 번 보장은 실제 DB 경합 검증 대기 |
| SE-04 실패를 통과로 세지 않음 | `collect_egress`, `sync_egress`, `reconcile` | 엔진 오류·행 상한은 예외/커서 미진행, 변경된 옛 프록시 제거 | 관측 오류가 있으면 완전한 차단·무통신을 주장할 수 없음 |
| SE-05 호출 후보 상관 | `server_egress.py:60` `correlate`, `:86` `for_decision`, `endpoint_plane.py` | 같은 서버/실행 구간 양성, 다른 서버/전송 전/전송 후/intent 없음 음성, 경계·경쟁 | 기존 요청·추적 ID는 후보로만 붙임. 서로 다른 동시 호출에 같은 사건이 나타나도 정확 연결로 승격하지 않음 |
| SE-06 자격·재시도·독립 효과 | 사건과 조회의 고정 미확인 필드 | 경쟁 시험에서도 `retry_count=null`, `credential_use=unobserved`, `external_effect=unverified` | TLS 자격 사용·요청 재시도와 업무 효과는 추가 독립 증거 필요 |
| SE-07 제품 조회·표기 | 기존 관리자 상관 API와 `console.js`의 `relatedBody` | 기존 라우트 인증 검사, JS 구문, 기존 콘솔 상태 시험 | 서버 외부 통신/연결 확인/프록시에서 차단/연결 실패/보조 근거. 브라우저 렌더링 미실행 |

수집은 Docker `logs --timestamps --since ... --until ... --tail 10001`을 사용한다. 정상 수집은 최대 10,000행이고,
수집 커서는 기존 `mcp_runtimes.evidence.egress_log_cursor`이며 감사 원장을 수정하지 않는다.
사건은 `approval_events.kind=runtime-egress`, outcome는 `recorded`, 실제 통신 결과는 `scope.outcome`에 둔다.
프록시 필터 거부는 운영자 자기 승인 거부와 다르므로 승인 기록 표에서는 제외하고 호출 연관 표에 표시한다.
사건 ID는 원 로그 전체를 저장하지 않고 컨테이너 ID와 해당 행의 SHA-256으로 만든다.
같은 컨테이너·동일 Docker 나노초 시각·동일 행은 같은 사건이다.

수집 시각은 사건 시각이 아니다. 호출 구간과 사건 시각이 정확히 겹칠 때만 상관되며 수집 지연 후 재조회할 수 있다.
`server_egress.observation_status`는 `no_dispatch`/`unobserved`/`observed`이고 `truncated`는 200건 조회 상한 표시다.
`observed`는 일부 사건 존재만 뜻한다. 로그 완전성·원인·부재 증명이 아니다.
새 정책 판정을 만들지 않아 OPA·정책 원장은 바꾸지 않는다. 기존 신원/권한·D-132 허가 범위도 넓히지 않는다.

## 외부 근거와 재사용 범위

| 자료 | 판본·라이선스·확인 범위 | 채택·한계 |
| --- | --- | --- |
| [tinyproxy 1.11.2](https://github.com/tinyproxy/tinyproxy/commit/dd49e975a04a66c2a32e6d2fc7cd7ddf0cb9fe33) | `dd49e975a04a66c2a32e6d2fc7cd7ddf0cb9fe33`, 소스 헤더 GPL-2.0-or-later. 공식 유지보수 저장소의 릴리스/수정 이력 확인 | 기존 패키지 사용. 새 판본 설치·소스 복제 없음. 기기의 Alpine 패키지 판본은 미확인 |
| [reqs.c](https://github.com/tinyproxy/tinyproxy/blob/dd49e975a04a66c2a32e6d2fc7cd7ddf0cb9fe33/src/reqs.c#L438-L458), [연결 확인](https://github.com/tinyproxy/tinyproxy/blob/dd49e975a04a66c2a32e6d2fc7cd7ddf0cb9fe33/src/reqs.c#L1610-L1616) | 도메인 필터 거부와 TCP 연결 뒤 메시지 본문 선별 확인 | 허가 요청 전체나 API 응답 성공으로 해석하지 않음 |
| [sock.c](https://github.com/tinyproxy/tinyproxy/blob/dd49e975a04a66c2a32e6d2fc7cd7ddf0cb9fe33/src/sock.c#L184-L193), [log.c](https://github.com/tinyproxy/tinyproxy/blob/dd49e975a04a66c2a32e6d2fc7cd7ddf0cb9fe33/src/log.c#L164-L188) | 접속 실패 메시지, 프로세스 ID 포함 로그 형식 확인 | PID는 MCP 요청 ID가 아님. DNS 실패와 포트 거부 등 다른 로그는 이번 파서 대상 밖 |
| [Lunar 기존 분석](../../solutions/lunar-mcpx.md) | MCPX 코드 `7193eab5535ec0be2c973007b9ab5cccab15fd70`, MIT. outbound 연동은 공식 공급자 설명 수준 | 집계와 서버 API 경계 구분만 참고. Lunar 코드는 가져오지 않음 |
| [ToolHive 기존 검토](../../solutions/toolhive-runtime.md), [실행기 비교](../oss-deep/toolhive-runtime.md) | 저장소의 고정 판본·라이선스·범위 기록 재사용 | 기존 실행기 교체 없음 |
| 공개 스킬 검색 | GitHub 관련 `skills tinyproxy egress logging` 검색 | 이번 연동에 채택할 검증 근거 미확보. 외부 SKILL/스크립트 실행 없음 |

## 남은 공백

제3자 GitHub·Context7의 서버→API 통신은 관측하지 않는다. 이 경로에는 수집 없음이 정상이며 무통신 증거가 아니다.
자격을 서버 컨테이너에 새로 주입하거나 직원 토큰을 전달하지 않는다. TLS 복호화도 하지 않는다.
연결 횟수로 API 재시도를 세면 풀 재사용·다중 HTTP 요청·동시 호출에서 틀린다.
출구 프록시는 edge 망에도 있으므로 같은 프록시를 쓰는 다른 프로세스의 사건이 섞일 수 있다.
서버와 프록시 간 인과를 확정하려면 연결별 peer/도구 요청 결속 등 추가 증거가 필요하다.
Docker 로그 회전·종료/재생성 직전의 마지막 기록·worker 빌드 중 장시간 지연·상한 초과·로그 형식 변경은
기록 누락 가능성이 있다. 이 구현을 사전 집행·전체 감사·외부 효과 확인으로 표현하지 않는다.
