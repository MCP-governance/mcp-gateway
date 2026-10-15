# PJ1 Ghidra 로그 확인 인덱스

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
