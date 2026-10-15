# 2026-10-14 엔드포인트 로그 경로 수정·PJ1 Linux 검증

- 작업자: Codex 검수/배포, Luna 수신기 회귀·Console·Windows 수집기 분업.
- 코드 기준: `10/14-endpoint-telemetry-fix`, 시작 HEAD `ab6936c64f3578de8360b840f1928681714fa7bb`. 기존 미커밋 변경은 보존했다. 제품 소스 변경분을 새 커밋/PR로 게시하지 않았다.
- 시작 근거: [6개 로그 공백](2026-10-14-endpoint-log-wbs.md), DEV-18/33/34, D-82, 원본 PAC07/22/23/24.
- 완료 범위: 사용자의 “PJ1 Linux 검증을 먼저 완료”에 따라 관리 UID1001의 수집·전송·저장·화면과 선별 실패/복구를 검증했다.

## 결과와 문제 해결

| 문제 | 변경 | 이번 확인 |
| --- | --- | --- |
| NETSCAN=0이면 stdio/process도 자동 수집 중단 | `ENDPOINT_PROCESS_SCAN`을 네트워크 탐색과 분리, 보호된 설정의 UID/SID만 수집 | PJ1 UID1001 합성 marker 자동 수신, UID1000 대조 프로세스 제외. 실제 Ghidra/MCP 호출 증거는 아님 |
| exit0/service active가 채널별 성공으로 오해됨 | 설정·프로세스·네트워크·OS의 success/partial/failed/disabled/unauthorized/unsupported/unknown, 서버 수신 시각/마지막 성공 저장 | OS journal 오류는 failed, 마지막 성공 보존. process/inventory success 및 broker 유효 유지. 정상 복구 후 OS success |
| 500건 잘림/정보원 실패가 기존 행 삭제 가능 | `complete=False` 기본값. 전체 성공에만 명시적 true. listener source 범위 검증/제한, upsert·삭제·metadata 동일 transaction | sender501개→500개 partial 단위 검사, 실제 PostgreSQL incomplete/unmarked-empty 보존·scoped 삭제·trigger rollback |
| 전용 미등록·잔존 상세에서 listener 누락 | 프로세스/리스너 표·차트·수집 상태 추가, MCP 추정과 확인·OS 차단을 구분, 최근 최대200건 명시 | 배포된 제품 Console에서 실제 수신 marker·채널 상태·OS 차단 표 표시 확인 |
| 오래된 관측이 정상0 또는 현재 탐지로 섞임 | listener에 fresh/stale/unknown 표시, 마지막 성공 유지. 과거 shadow count는 보수적으로 유지 | stale/partial/malformed/future 경계 회귀와 실제 PG 대조. 전체 누적집계/페이지 이동 추가는 아님 |
| Windows producer 공백 | 보호된 Python/PowerShell collector와 supervisor/kit 연결, event-time SID 정확 대조, bookmark는 전달 성공 후 저장 | 합성 단위7 및 실제 Windows PowerShell 구문 검사. **Windows 기기 이벤트 생성/전달은 미검증** |

서버 `/api/endpoint/observation-status`는 장치 key·inventory 권한을 요구한다. 다른 endpoint 보고는403이며, positive process/network는 netscan, positive OS는 enforcement 권한이 추가로 필요하다. negative 진단은 본인 endpoint에 한정한다. Gateway 이름만 주장하는 stdio 및 승인 서버의 직접 로컬 경로를 registered로 취급하지 않도록 listener 분류도 보강했다. 정책·계약 승인을 추가하지 않았다.

## 배포와 DB 보존

솔루션에서 기존 source SHA를 먼저 검증하고 task 백업을 보존한 뒤 `./console.sh field up`으로 배포했다. 실제 Gateway/Agent-Service 파일10개의 SHA와 readiness/build 일치를 확인했다. 제품 DB `mcp_governance`의 시작시각·principals·devices·grants 및 MCP registry 상태는 배포 전후 동일했다. 기존 무효9-tool 등록3건의 DISABLED도 유지했다.

원격 Console/main에는 로컬과 다른 기존 기능이 있어, Console의 coverage/import와 backend report 모델·수신 경로만 반영한 prepared source를 사용했다. 전체 로컬 working tree가 배포됐다는 뜻은 아니다. Windows collector의 unused import 제거는 기존 read-only kit mount에서 최종 SHA를 별도로 확인했다. PJ1 설치3파일 hash, AppArmor/nft·설정 보호·일반 계정 점검은 정상이고, 코드 갱신을 위한 서비스 restart1회 뒤 실제 시험에서는 서비스 restart나 수동 telemetry POST를 하지 않았다.

## 3단계 검증

| 층 | 환경·결과 | 정본 증거 |
| --- | --- | --- |
| 정적·회귀 | pyflakes, source JS 문법, auth route inventory 통과. WSL endpoint42개 중41 PASS/Windows native PS1 skip, Windows parser7 PASS(중복6개+PS 구문1); Node14 PASS, managed-health9 PASS | [검사 JSON](../../analysis/endpoint-log-fix/checks.json) |
| DB 보존 실제 동작 | PJ1 자동 process 발견·다른UID 제외·종료 후 다음 완전 snapshot 자동 제거, 실제 AppArmor Python 실행 exit126→OS 표본1388 자동 수신. journal 오류·마지막 성공/cursor 보존·broker 유지·원복 후 주기 복구 | [기기 원본 검사 로그](../../analysis/endpoint-log-fix/pj1-live/automatic-check.jsonl), [안전한 수신 표본](../../analysis/endpoint-log-fix/pj1-live/delivered.json), [결과](../../analysis/endpoint-log-fix/pj1-live/result.json) |
| 초기화 후 선별 DB | 제품 DB가 아닌 전용 `risk_scenarios_20261014`의 새 UUID schema를 초기화해8조건 PASS 후 schema 삭제. 배포 image에서도 bind 없이 같은8조건 PASS | [배포 전](../../analysis/endpoint-log-fix/pg-snapshot-predeploy.jsonl), [배포 image](../../analysis/endpoint-log-fix/pg-snapshot-deployed.jsonl), [검사 코드](../../experiments/endpoint-log-fix/pg_snapshot_check.py) |
| 배포/실기기 | 솔루션10 path hash·DB/registry 보존·ready, PJ13 path hash 및 scope 확인 | [배포](../../analysis/endpoint-log-fix/deployment.json), [PJ1 갱신](../../analysis/endpoint-log-fix/pj1-update.json), [원본/준비/실행 SHA](../../analysis/endpoint-log-fix/deploy-manifest.json) |
| 제품 화면 | 미등록·잔존의 listener/채널 상태/OS 차단이 실제 배포 화면에서 표시 | [화면 관측](../../analysis/endpoint-log-fix/console-delivery.json), [프로세스 표 화면](../../analysis/endpoint-log-fix/console-process-status.png) |

표본1388은 발생 `12:08:45.615202Z`, 수신 `12:08:55.047985Z`, 지연9.43초다. 독립 journal의 event_id/UTC시각/kind/details와 솔루션 보관 projection이 일치한다. process 명령은 digest만 저장하고 원문 인자는 전송하지 않았다. 일회성 marker는 관리자가 생성한 합성 `sleep` 프로세스이며 실제 Ghidra/MCP 프로토콜·자연어 하네스 호출과 구분한다.

추가로 cursor를 같은 이벤트 직전으로 되돌려 기존 주기 수집기가 실제 재전송하게 했다. OS 채널의 새 수신 시각과 처리1건을 확인했고, DB의 표본1388은 같은 id/최초 received_at/행1개를 유지했다. [자동 재전송·중복 검사](../../analysis/endpoint-log-fix/pj1-live/replay-result.json), [진행 로그](../../analysis/endpoint-log-fix/pj1-live/replay.jsonl). 정상 cursor 진행은 수집기에 맡겼으며 service restart/수동 POST는 없었다.

검사 실행 환경 실수도 보존했다. OAuth Form route에 JSON을 보낸 최초 probe는422라 실제 Console 로그인 경로로 정정했다(제품 결함 아님). Linux 모듈을 Windows에서 가져온 managed-health 실행은 grp import 실패라 [원본 실패](../../analysis/endpoint-log-fix/checks-windows-linux-import-error.json)를 남기고 Linux에서9개 재검증했다. PG 초기 fixture의 partial 후 행 수 예상 오류는 [첫 실행](../../analysis/endpoint-log-fix/pg-snapshot-first-failure.jsonl)에 보존하고 실제 보존 행을4개로 정정했다. 실패한 실행을 PASS로 세지 않는다.

## 타 수집 솔루션 대조와 선택

[OpenTelemetry resiliency](https://opentelemetry.io/docs/collector/resiliency/)는 전송 queue/retry와 crash 후 디스크 지속성을 구분하며, 한도·timeout·디스크 장애가 손실 원인이 될 수 있다고 설명한다. 현재는 기존 journal/bookmark와 서버 idempotency를 활용했다. 별도 spool/WAL·용량/보존 운영은 도입하지 않았으며 장기 오프라인 무손실을 주장하지 않는다.

[OpenTelemetry internal telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/)의 수신 실패·queue·전송 흐름을 따로 보는 방식에서 수집 채널별 상태/마지막 성공을 분리하는 설계 기준을 가져왔다. 제품에 OpenTelemetry Collector나 새 외부 backend를 설치한 것은 아니다.

[Fluent Bit 4.2 backpressure](https://docs.fluentbit.io/manual/4.2/administration/backpressure)의 memory/filesystem 제한·pause/resume 구분을 참고해, 잘림/부분 보고를 완전 snapshot으로 해석하지 않았다. source-scoped 완전성 계약은 이 제품의 구현 판단이며 Fluent Bit의 MCP 보장 기능으로 설명하지 않는다. [읽기 범위/적용/한계](../../analysis/endpoint-log-fix/references.json).

## 로그 확인과 WBS

- 제품 Console: 통제 범위 → 미등록·잔존 → 엔드포인트 수신기/관측 수집 상태/엔드포인트 차단. 프로세스 종료 후 발견 행은 다음 complete report에서 사라지고, OS 이벤트는 보존된다.
- PJ1 사용자 계정으로 읽을 수 있는 파일: `/home/pj1/mcpgw-telemetry-fix-20261014/logs/ea472c80fae8/automatic-check.jsonl`, `delivered.json`, `result.json`. device key/JWT·원문 명령·raw journal은 저장하지 않았다.
- [로그 안내](../../analysis/endpoint-log-fix/README.md), [WBS 정본](../../analysis/development-wbs/README.md), [웹 현황판](https://mcpgw-status-20261014.sleek-stoat-4347.chatgpt.site).
- 검수 진척은21.8→24.8%, 최종 완료0/40. G05.03 10→60, G06.03 10→50, G06.04 20→50만 점수를 바꿨다. 다른 작업 점수와 [수정 전 스냅샷](../../analysis/development-wbs/snapshot-before-log-fix.json)은 보존했다. 이번 Linux 성공으로 전체 OS/92개 도구/완료 검수를 올리지 않는다.

## 실패·미완료·한계

Windows는 WFP5152/5157에 event-time 사용자 SID가 없으면 PID의 현재 주체로 추론하지 않고 partial/sid_unavailable로 제외한다. AppLocker는 실제 event의 TargetUser가 관리SID와 정확히 일치해야 수집한다. audit 정책·AppLocker를 자동 활성화하지 않았다. Windows 실기기 전달/집행은 사용자의 Linux 우선 선택에 따라 남겼다.

수집은 관리UID/SID·이름 패턴에 따른 관측이고 root attestation이 아니다. 실제 사용자 Ghidra는 UID1000 통제 밖이라 이번 자동 수집 범위에 넣지 않았다. journal/bookmark 유실·오래된 로그 rotation·디스크 full·장기 네트워크 단절·고부하 전 이벤트 무손실은 별도 검증이다. 이번 잘못된 journal cursor는 관리자가 원복했으며 손상 cursor를 자동 재설정하는 기능을 만든 것은 아니다. 최근200건 표는 전체 누적집계/페이지 이동이 아니다. status server 수신시각은 실제 기기의 event 발생시각과 다르다.

DEV-29 업스트림 세션·DEV-30 정상 거부 잡음·DEV-31 Bash의 helper 접근·DEV-32 통제 밖 계정/PC·DEV-33 Ghidra 영구 설치·Windows 실제 시험은 이 로그 수정으로 해결했다고 표시하지 않는다. E01–E13 전체 카드는 미실행 상태를 유지하며 자가 승인9-tool 기록은 계속 제외한다.

## 다음 작업과 사용자 입력

DEV-18/34의 전체 누적집계·페이지 이동·장기 오프라인/복구, DEV-33 실제 MCP 앱의 관리 범위 시험/영구 설치, DEV-25 Windows 실기기 검증은 남았다. 이번 Linux 완료 범위에 필요한 추가 입력은 없다. Windows 후속에는 별도 Windows 시험기기와 관리 계정이 필요하며 자격값은 위키에 남기지 않는다.

위키 출처·경로·매핑 hash 검사:141문서/위험13개/PAC24개, 오류0·경고0. 웹은 2026-10-14T12:36:51.536206+00:00에 기존 owner-private Site로 게시 succeeded; source 3e1529ac89e0218c114b487852ab164c14faf8cd. [게시 확인](../../analysis/development-wbs/site-publication.json).
