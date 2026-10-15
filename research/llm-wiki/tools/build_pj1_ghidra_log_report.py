"""Link actual PJ1 SDK, collector, receiver, automatic OS event and ledger evidence."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'analysis/pj1-ghidra'
REPORT=ROOT/'status/reports'


def read(name):
    return json.loads((DIR/name).read_text(encoding='utf-8'))


def main():
    sdk=read('mcp-probe.json');live=read('live-observation.json')
    finish=read('finish-and-managed-denial.json');automatic=read('automatic-os-event.json')
    ledger=read('gateway-window.json');install=read('report.json')
    assert install['tools'][0]['installation']['reboot_persistent_runtime'] is False
    assert sdk['process_exit_code']==0 and sdk['hold_completed'] and 'error' not in sdk
    assert len(sdk['tools_list']['result']['tools'])==28 and sdk['read_call']['result']['isError'] is False
    info=json.loads(sdk['read_call']['result']['content'][0]['text'])
    assert info['sha256']==sdk['binary_sha256'] and info['memory_size']==126 and info['function_count']==1
    assert live['processes'][0]['uid']==1000 and live['processes'][0]['profile']=='unconfined'
    assert live['automatic_scan_enabled'] is False and live['automatic_listener_rows']==0
    assert live['receiver_result']['accepted']==1 and len(live['console_listener_rows'])==1
    assert live['console_listener_rows'][0]['classification']=='shadow'
    assert live['console_listener_rows'][0]['mcp_evidence']=='suspected'
    assert live['registry_approval_performed'] is False
    assert finish['ghidra_process_exited'] and finish['listener_snapshot_cleanup']['removed']==1
    assert finish['managed_launch']['exit']==126 and finish['managed_service_active']
    assert automatic['ok'] and automatic['manual_report_sent'] is False
    assert automatic['periodic_service_not_restarted'] and automatic['console_os_events']
    assert ledger['window']['calls_in_probe_window']==0
    files=[p for p in sorted(DIR.iterdir()) if p.suffix in ('.json','.txt')]
    files += sorted((ROOT/'experiments/pj1-ghidra').glob('*.py'))
    files += sorted((ROOT/'experiments/pj1-ghidra').glob('*.sh'))
    hashes=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
    ids=[r['id'] for r in automatic['console_os_events']]
    result=dict(verified_at=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
        branch='10/14-pj1-ghidra-logs',basis_head='ab6936c64f3578de8360b840f1928681714fa7bb',
        product_code_changed=False,tool_registration_approval_performed=False,
        runtime_installation='PJ1 user space; Ghidra/JDK in volatile /dev/shm; venv/jar/logs persistent',
        actual_sdk=dict(protocol=sdk['initialize']['result']['protocolVersion'],advertised_server=sdk['initialize']['result']['serverInfo'],
            package_version='GhidraMCP 2.0.0',tool_schemas=28,tool_called='get_program_info',read_success=True,
            uid=1000,profile='unconfined',target_executed=False,natural_language_harness=False),
        automated_stdio_forwarding=False,manual_stdio_forwarding=dict(accepted=1,classification='shadow',evidence='suspected',snapshot_removed_after_exit=True),
        managed_python_launch_denied=True,automatic_kernel_event_forwarding=dict(console_ids=ids,
            elapsed_seconds=round(automatic['finished_at']-automatic['started_at'],2),manual_report_sent=False),
        gateway_tools_call_decisions_in_sdk_window=0,ledger_max_at_read=ledger['tail']['ledger_max'],
        observation_test_complete=True,reboot_persistent_ghidra_runtime=False,evidence=hashes)
    (REPORT/'2026-10-14-pj1-ghidra-logs.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    overview='''# PJ1 Ghidra 로그 확인 인덱스

[검수 보고서](../../status/reports/2026-10-14-pj1-ghidra-logs.md) · [설치·프로토콜 상세](report.md)

| 확인할 내용 | 원본 | 핵심 값 |
| --- | --- | --- |
| 실제 GhidraMCP 요청·응답·stderr·PID·bridge | [mcp-probe.json](mcp-probe.json) | initialize, schema28, get_program_info 성공, 합성ELF126B/함수1, UID1000/unconfined |
| 자동 stdio 수집 비활성 및 일회성 전송·Console 수신 | [live-observation.json](live-observation.json) | 자동0, 수동accepted1, shadow/suspected1 |
| 종료·수동표식 원복·관리Python실행거부·수동OS수신 | [finish-and-managed-denial.json](finish-and-managed-denial.json) | PID종료, listener1건제거, exit126, Console1385 |
| 기존 주기 수집기의 OS거부 자동 수신 | [automatic-os-event.json](automatic-os-event.json) | 수동전송없음, 약35.84초 후 Console1387 |
| SDK시험창 Gateway MCP 원장 | [gateway-window.json](gateway-window.json) | decisions0, 원장최대803 |
| 판본·라이선스·hash·설치 위치·28개 schema | [report.json](report.json) | Ghidra12.1.4/GhidraMCP2.0.0, Ghidra/JDK RAM1.24GiB |

PJ1에서 직접 읽을 수 있는 로그는 `/home/pj1/mcpgw-ghidra-20261014/logs/`에 있다. 비밀번호·장치키·JWT를 기록하지 않았다.

```bash
ssh pj1@100.110.81.60 'cat /home/pj1/mcpgw-ghidra-20261014/logs/automatic-os-event.json'
ssh pj1@100.110.81.60 'cat /home/pj1/mcpgw-ghidra-20261014/logs/mcp-probe.json'
```

[솔루션 Console](http://100.83.175.111:443/)에서 관리자 권한으로 엔드포인트의 실행 차단을 확인한다. **1387번**은 수동 전송 없이 들어온 실제 OS거부 이벤트다. Ghidra 로컬 SDK 호출은 Gateway를 통과하지 않아 도구 호출 원장에는 없다. 수동 shadow 표식은 실행 종료 후 원복했고, 종료 전 수신본은 위 원본에 보존했다.

Ghidra/JDK의 `/dev/shm` 설치는 재부팅 시 사라진다. GUI·프로젝트 변경8개·자연어 하네스는 이번 Ghidra 시험에서 실행하지 않았다.
'''
    (DIR/'README.md').write_text(overview,encoding='utf8')
    report='''# 2026-10-14 PJ1 Ghidra·GhidraMCP 설치와 로그 전달 확인

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
'''
    (REPORT/'2026-10-14-pj1-ghidra-logs.md').write_text(report,encoding='utf8')
    print(json.dumps(dict(verified=True,schemas=28,manual_observation_rows=1,automatic_os_event_ids=ids,gateway_calls=0,evidence_files=len(hashes))))


if __name__=='__main__':
    main()
