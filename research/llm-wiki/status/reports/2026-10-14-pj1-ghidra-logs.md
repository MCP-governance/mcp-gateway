# 2026-10-14 PJ1 Ghidra·GhidraMCP 설치와 로그 전달 확인

- 작업자: Codex(설치 검수·수신/원장·관리거부·자동전송 대조), Luna(공식 설치·SDK 읽기 호출)
- 기준: `10/14-pj1-ghidra-logs`, HEAD `ab6936c` + 다른 작업의 dirty 보존. 제품 코드·정책·관리 설정·기기 자격·MCP 등록/승인은 변경하지 않았다.
- 시작 근거: 사용자 PJ1 설치/로그 확인 요청, LOCAL-RISK-01/02/08/10, DEV-32.
- 완료 조건: 실제 공개 GhidraMCP 호출, PID/UID/profile과 실제 수신 대조, 자동/수동 전송 구분, 원복·읽을 수 있는 로그 확보.

## 결과

PJ1에서 Ghidra12.1.4·GhidraMCP2.0.0·Temurin21.0.12.1+1·private Python3.12 venv를 구성했다. 디스크 여유가 약502MB라 Ghidra/JDK는 task-owned `/dev/shm` 약1.24GiB에 임시 설치했다. Python venv·extension jar·원본/로그 약38.9MB는 `/home/pj1/mcpgw-ghidra-20261014`에 남겼다. 재부팅 이후 유지되는 Ghidra 설치라고 주장하지 않는다.

실제 `pj1` UID1000/unconfined에서 공개 OSS GhidraMCP stdio의 `initialize→tools/list(28개)→get_program_info`가 성공했다. 합성ELF126바이트/함수1·hash를 대조했고, ELF를 실행하지 않았다. 변경 도구8개는 광고만 확인하고 호출하지 않았다. 내부 bridge는 loopback35673, 프로세스29514였으며 종료코드0·프로세스/리스너 부재를 확인했다. SDK가 광고한 serverInfo version1.30.0과 패키지GhidraMCP2.0.0은 다른 값으로 기록했다.

## 어디까지 로그가 넘어갔는가

| 경로 | 실제 결과 | 의미 |
| --- | --- | --- |
| GhidraMCP 자체 SDK·앱 로그 | 원본 요청/응답·stderr·프로세스·bridge 보존 | 로컬 호출은 실제 성공; 자연어 모델 호출 증거는 아님 |
| 기본 stdio 프로세스 관측 전송 | 자동0, installed observer `ENDPOINT_NETSCAN=0` | 탐지 regex가 있어도 현재 서비스는 해당 보고를 실행하지 않음 |
| 명시적 일회성 관측 | 실제프로세스1건 검출→netscan 장치자격 POST→수신1→Console shadow/suspected1 | 관측 로그 전송 성공. MCP 계약 승인·confirmed 프로토콜 판정으로 승격하지 않음 |
| 관리UID1001 실행 시도 | general Python exec exit126, 실제 AppArmor denial | GhidraMCP 로딩 전에 interpreter를 거부; Ghidra 전용 signature 차단 증거는 아님 |
| OS거부 자동 전송 | 별도 실행시도 후 기존 주기 서비스만 대기, 약35.84초 뒤 Console1387 | 수동POST/서비스재시작 없이 자동 경로 수신 확인 |
| SDK시험창 Gateway 도구 원장 | 0건, 조회시 최대803 | 로컬 stdio는 Gateway `tools/call` 경로를 우회. telemetry POST는 도구 판정 원장이 아님 |

## 검증

설치 공식 archive SHA·pinned commit/license·private dependency 판본·SDK28 schemas·읽기 응답·합성ELF hash는 [상세 보고](../../analysis/pj1-ghidra/report.json)에 있다. 실제 실행·수신·독립 효과와 원본 hash는 [검수 JSON](2026-10-14-pj1-ghidra-logs.json), 사람이 읽는 순서는 [로그 인덱스](../../analysis/pj1-ghidra/README.md)에 있다.

수동 관측 전 장치의 기존 listener snapshot이0건임을 확인한 뒤 실제 installed `stdio_processes()` 결과만 전송했다. 종료 후 task digest만 남았는지 검사해 실제 프로세스0 상태의 빈 snapshot으로 해당1건을 원복했다. 다른 관측자가 추가했으면 원복을 중단하는 guard가 있다. 관리 서비스는 active이며 NETSCAN 설정·정책은 그대로다. OS이벤트1385(수동 수신)·1387(자동 수신)은 감사 이력으로 남고, 수동 shadow 종료 전 원본은 로컬/PJ1 로그에 보존했다.

## 문제·한계·해결 방향

- **stdio 관측은 현재 자동 전송되지 않는다.** `managed-linux.py::serve`가 observer config의 NETSCAN을0으로 쓴다. 이름 기반 process scan과 네트워크 probe가 같은 보고 스위치에 묶여 있다. 자동 stdio 관측을 켜려면 process-only 보고와 네트워크 스캔 범위, 다른UID의 수집·장치/사용자 귀속, 주기·보존 방식을 별도 설계해야 한다(DEV-32·DEV-33). 이번에는 이를 활성화하거나 제품을 바꾸지 않았다.
- **Gateway 원장으로 전체 로컬 호출 상세를 볼 수 없다.** 원장이0이라고 로컬 호출이 없었다는 뜻이 아니다. 일반 pj1 계정은 기존 관리UID1001의 집행 범위 밖이며, root/다른 계정 전체를 차단했다고 주장하지 않는다.
- **RAM 설치는 휘발성이다.** 영구 설치에는 디스크 확보가 필요하다. 기존 사용자 파일·snap·로그는 삭제하지 않았다. GUI, 프로젝트 변경, 실제 고객 바이너리, 자연어 Ghidra 하네스, Windows는 미실행이다.
- 이전 `pj1-nine-*` 자가승인 시험의 무효/철회(D-79)와 E13 후속 보고를 보존했다. 해당 서버를 복구·재승인하지 않았다.

## 다음 작업·필요 입력

DEV-33: 영구 디스크 용량과 process-only 자동 관측의 허용 범위를 정한 뒤 설치 지속성/보고 모델을 개선한다. 이번 로그 전달 확인에 추가 사용자 입력은 없음. 영구설치와 자동관측 변경은 이번 결과와 분리한다.
