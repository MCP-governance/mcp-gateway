# 엔드포인트 로그 전달 진단·목표 기능 WBS — 2026-10-14

- 작업자: Codex; Luna는 정적 경로·WBS 초안·한국어 카피를 분담했고 최종 판단·현장 읽기·산정은 Codex가 수행했다.
- 코드 기준: `10/14-endpoint-log-wbs`, 시작 HEAD `ab6936c64f3578de8360b840f1928681714fa7bb`. 시작 전 미커밋 변경을 보존했다. 이번 제품 코드·수집 설정·승인·DB 상태 변경은 없다.
- 시작 근거: [목표 G01–G10](2026-10-13-development-goals.md), [원본 정책](../../threats/policies-24.md), DEV-18·29–33, 사용자 로그 전달 의심과 웹 WBS 요청.

## 결과

목표 10개를 40개 원자 작업으로 나눴다. **검증 단계 가중 진척 21.8%**이며, 새 완료조건 5단계 전체를 충족한 작업은 **0/40**이다. 구현 단계는 완전 근거 16개(이번 개발 현황판 2개 포함), 부분 후보 23개, 미구현 1개다. 작동하는 기능이 0이라는 뜻이 아니다. 코드·과거 판본·선택 계정 표본과 전체 완료 검수를 구분한 보수적 새 WBS 기준이다. 웹 게시 직전의 근거 스냅샷이며, 새 사이트의 이후 게시 성공을 제품 기능 검증 점수로 자동 가산하지 않는다.

각 작업의 구현·회귀·배포·실제환경·검수에 20%씩 주고 `0=미확인, 0.5=부분/과거/선택 표본, 1=해당 단계 범위 충족`으로 계산한다. 작업들은 동일 가중이다. 공수·일정 추정·전체 도구 개수·제품 인증 완료율이 아니다. [산정표](../../analysis/development-wbs/README.md)와 [JSON 정본](../../analysis/development-wbs/snapshot.json)에 완료조건·원본 PAC·코드·시험 후보·근거 SHA·남은 공백을 연결했다. 원본 PAC01–24와 런타임 PAC-01–15는 내용으로 매핑하며 숫자로 합치지 않는다.

별도 웹 현황판을 [개발 사이트 소스](../../../development-status-site/README.md)에 만들었다. 목표별 막대, 로그 전달 단계, 6개 문제, 검색/목표/상태 필터, 작업별 근거 상세, 정본 JSON 다운로드를 제공한다. 제품 운영 콘솔과 별도이며 **시각이 있는 검수 스냅샷**이다. 제품 API 실시간 연동·자동 WBS 갱신은 구현하지 않았다.

[게시된 현황판](https://mcpgw-status-20261014.sleek-stoat-4347.chatgpt.site)은 소유자만 접근한다. native 배포 결과 `succeeded`와 URL·판본을 확인했다([배포 기록](../../analysis/development-wbs/site-publication.json)). Windows helper가 패키징 shell 경로를 제대로 전달하지 못해 첫 packaging은 실패했고, 동일 checkout/사이트/credential을 사용한 WSL Node helper로 commit·push·package를 완료했다. 기존 제품 Git checkout은 출판 대상으로 사용하지 않았고 사이트를 중복 생성하지 않았다.

## 로그가 안 보이는 지점

| 항목 | 확인한 사실 | 검증 수준·남은 조건 |
| --- | --- | --- |
| 자동 프로세스·stdio 관측 | PJ1 root observer 설정 `NETSCAN=0`, 설치 collector 3파일은 현재 소스 LF 정규화 SHA와 일치. 자동 listener report가 생기지 않는 경로 | 현재 설정/소스 확인. 네트워크 스캔과 분리한 관측 scope/UID/보존 계약은 미구현 |
| 수집 상태 표현 | 비활성/401·403/정책 꺼짐도 `agent.py`는 exit0, supervisor는 `observer=ok`. 설정 보고 성공이 프로세스 관측 성공으로 읽힐 수 있음 | 정적 확인. 채널별 disabled/unauthorized/partial/failed/success·last-success 계약 필요 |
| 전용 화면 누락 | 실제 서비스가 제공하는 Console JS의 coverage에는 `inv.listeners` 참조가 없음. API 및 넓은 통합 목록은 listener 행을 처리함 | 현재 제공 JS 확인. 화면 전체가 비가시라는 주장은 하지 않음 |
| 부분 snapshot 삭제 | agent 500건 cap, receiver는 제출되지 않은 기존 행을 DELETE. 완전성 계약 부재 | 정적 위험. 실제 데이터 손실은 이번에 재현하지 않음. 격리 DB의 501건·정보원 실패·재시도 대조 필요 |
| 과거 발견의 신선도 | shadow 정책 집계에 관측 시각 조건이 없음. 수집 중단 뒤 과거 행이 남을 수 있음 | 정적 확인. stale을 삭제해 정상 0으로 만드는 방식은 부적절; coverage unknown과 역사 기록을 함께 유지해야 함 |
| Windows 경로 | Windows managed supervisor에는 Linux journald OS observer와 동등한 차단 이벤트 collector가 없음 | 소스 범위 확인. 실제 Windows 생산원·권한·수신 시험 미실행 |

[정적 감사](../../analysis/endpoint-log-audit/static-review.md), [상세 함수·행·SHA·수정 선택·시험 조건](../../analysis/endpoint-log-audit/static-review.json), [현재 기기/API 읽기](../../analysis/endpoint-log-audit/live-readonly.json)를 남겼다.

## 정상 전달 표본과 무결성 범위

PJ1 서비스는 `active`, API 기기 `last_seen_at`은 19:41:05 KST, listener `last_scan_at`은 19:02:59 KST다. 마지막 수신과 마지막 스캔은 다른 상태다. cursor 수정이 오래됐다는 이유만으로 실패로 판정하지 않았다. 새 관련 이벤트가 없으면 cursor가 진행되지 않을 수 있다.

기존 자동 OS 이벤트 **1387**은 현재 API에 남아 있다. 원본 발생 19:04:15.120155 KST → 수신 19:04:47.543552 KST, 기록 간 지연 **32.42초**다. 이전 시험에서 조회로 확인하기까지 걸린 시간은 **35.84초**이며 이 둘을 구분한다. 수동 POST나 서비스 재시작 없이 기존 주기 수집기로 전달된 실제 Python 실행 거부 표본이다. Ghidra 프로세스 탐지·자동 stdio 전송·Gateway 도구 호출의 증거가 아니다.

이번 읽기에서는 기기에 보존된 당시 원본과 현재 수신본의 `event_id·종류·UTC 정규화 시각·안전한 details`를 동일 직렬화 규칙으로 비교했다. 두 projection SHA는 `824d448193c94651cac5b780b2d22cc75616f915f0d65bc04a9e8524edb71b63`으로 일치했다. 원본 파일 SHA와 projection SHA를 별도로 보존했다. 이는 표본 1건의 정규화 내용 일치이며 raw HTTP 바이트 무결성·전체 이벤트 무손실의 증거가 아니다.

API의 최근 200행에 이 기기 행이 200개 있는 것을 관찰했다. 전체 누적 건수로 표현하지 않는다. integration/device summary의 **24시간 전체 거부 집계는 이미 존재**하므로 그 기능의 부재로 기록하지 않는다. 남은 공백은 관측 채널 신선도/실패 표시와 전용 listener 상세, 200건 조회 상한의 범위 표시/페이지 이동이다.

## 검증

| 확인 종류 | 환경·결과 | 원본 |
| --- | --- | --- |
| 설치/현재 수신 읽기 | PJ1 root 보호 설정·service·기존 API를 읽음. 보고 POST/정책/승인/DB 변경 없음 | [현재 읽기](../../analysis/endpoint-log-audit/live-readonly.json) |
| 현재 관리형 검사기 회귀 | WSL Python, 기존 정상/음성 **9개 PASS**. Windows 규칙 검사 단위 케이스는 실제 Windows 집행 증거가 아님 | [검사 기록](../../analysis/wbs-review/current-checks.json) |
| 표시 로직 회귀 | Node, 실제 0·미측정·오래된 값·실패/타입/범위 등 **4개 PASS** | 같은 검사 기록 |
| backend 보안·지표 회귀 | Windows task venv에 fastapi/jsonschema 부재. WSL system에도 psycopg_pool/OpenTelemetry가 없어 import 실패. **이번 소스의 해당 회귀 미검증** | [첫 환경 실패](../../analysis/wbs-review/environment-failure-checks.json); WBS 회귀 점수에서 제외 |
| WBS 정본 | 40개 고유 ID, 목표별4개, 산식, 근거 경로, 감사 source SHA, 표본 projection 일치 검증 | [빌더](../../../development-status-site/build_snapshot.py) |
| 웹 UI | 실제 내장 브라우저: 40개 목록, G06 필터4개, 검색1개, 상세의 조건/코드/근거, 최종 완료 필터0·빈 상태, 브라우저 console error0. 기본 좁은 폭 및 1280×900 배치 확인 | [UI 검사](../../analysis/development-wbs/web-qa.json), [미리보기](../../../development-status-site/preview-desktop.png) |

현재 PJ1 collector 3파일과 receiver `endpoint_plane.py`의 정규화 SHA는 현재 소스와 일치했다. `system_metrics.py`, `agent_service.py`, `contract.py`도 image와 정규화 SHA가 일치했다. **core.py와 Console JS 전체는 현재 working tree와 다르다.** 따라서 과거 배포 증거를 현재 working tree 전체의 배포 완료로 세지 않았다. 실제 제공 JS에도 listener 누락이 있음을 독립 확인했다.

## 미완료·다음 작업

제품의 위 6개 결함/범위 공백은 이번 확인·현황판 작업에서 수정하지 않았다. **DEV-34**로 기존 목록에 연결했다. 순서는 채널별 상태/전용 표시 → incomplete snapshot 삭제 방지 → 자동 process-only 수집 scope 및 freshness → 실제 하네스 helper/세션/잡음 → Windows/종료·외부 자격 철회 검증이다. 각 수정은 현재 DB를 초기화하지 않고 검증하고, 초기화가 필요한 반례는 지정 격리 DB에만 적용한다.

D-79 자가 승인 9개 도구 시험은 무효로 유지했고 원장744–800을 긍정 검증에서 제외했다. E13 변형은 부분 증거며 공식 실험 카드의 미실행 상태는 그대로다. 사용자 승인·MCP 등록을 에이전트가 대신 수행하지 않았다.

필요한 사용자 입력은 이번 보고/현황판 제공에는 없다. 자동 관측 범위를 확대하는 제품 작업에서는 UID/PC·네트워크 범위·보존 정책을 운영 요구조건으로 정해야 한다.
