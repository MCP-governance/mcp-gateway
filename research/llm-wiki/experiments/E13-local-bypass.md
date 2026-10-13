# E13 — PJ1 로컬 stdio·loopback 우회

확인일: 2026-10-13 · 상태: **미실행** · 준비 상태: `pj1_local_fixture_needed`.

관리형 Linux에서 비승인 MCP를 직접 실행하거나 localhost로 접속해 Gateway를 우회할 수 있는지 검증한다. 자체 운영 stdio MCP를 Gateway 뒤에 두는 정상 경로는 E01~E06으로 검증한다. 직접 stdio 경로에는 Gateway의 도구 단위 정책이 적용된다고 가정하지 않는다.

[사전 조건](preflight.md)과 [대상 목록](targets.md)을 적용한다. 설치된 실제 profile·관리 계정·실행 파일을 확인하고 checkout의 미커밋 소스로 배포 상태를 대신하지 않는다.

## 준비와 입력

- 전용 시험 identity 또는 다른 작업이 없는 PJ1 관리 하네스 세션. root/admin 침해 시나리오는 범위 밖이다.
- 네트워크 다운로드 없는 고정 stdio fixture: `read_marker`는 공개 합성 marker를 읽고, `write_marker`는 시험 디렉터리에 marker만 생성한다. 실행 파일 hash와 stdout protocol·독립 수신 로그를 고정한다. 실제 구현·설치는 아직 하지 않았다.
- localhost HTTP fixture는 별도 시험 계정에서 시작하며 IPv4 `127.0.0.1`과 IPv6 `::1`을 각각 관찰한다. 두 주소의 정상 대조군이 먼저 성공해야 차단 시험을 해석할 수 있다.
- 실행 전 일반 계정의 동일 fixture 호출로 정상 동작·효과를 확인한다. 일반 계정 대조군 성공을 관리형 보안 실패로 세지 않는다.
- 설치된 보호 설정에 비승인 서버를 실제로 추가할 수 없다면 설정 보호 차단을 기록한다. 이어서 보호 하네스의 지원 도구로 해당 fixture 직접 실행·접속을 시도해 OS 경계도 확인한다. 고정 설정을 root로 바꿔 보호를 해제하지 않는다.

```json
{
  "cases": ["direct_stdio", "loopback_ipv4", "loopback_ipv6", "unmanaged_control"],
  "fixture": "disposable-marker-only",
  "managed_launcher_required": true,
  "expected_gateway_tool_ledger": false
}
```

위 값은 시험 입력 데이터다. 임의 인터넷 접속·기존 파일 삭제·실사용 데이터 전송을 수행하지 않는다.

## 절차

1. fresh 관리형 하네스의 UID·실행 파일·AppArmor profile·설정 hash·active heartbeat를 기록한다.
2. 일반 계정에서 공개 marker 읽기와 일회 쓰기, localhost 각 주소 연결을 성공시킨 뒤 해당 효과와 로그를 보존하고 fixture를 초기화한다.
3. 관리형 하네스에서 비승인 stdio 서버 설정·실행, 별도 interpreter/실행 파일 실행, localhost 각 주소 직접 접속을 한 경로씩 시도한다. CLI나 모델이 도구 시도를 하지 않았으면 OS 차단 증거가 아니며 미확인으로 남긴다.
4. 보호 설정 거부·실제 실행/접속 오류, 같은 UID/PID/시각의 OS 수집 증거, fixture protocol 수신·파일 효과를 대조한다. 로그 미수집은 감사 공백으로 별도 실패 처리한다.
5. 같은 fresh 세션에서 승인된 Gateway 경로의 정상 읽기를 성공시켜 과도한 차단을 확인한다. 공급자 quota를 피하도록 자체 운영 정상 fixture를 우선한다.
6. 만든 fixture·대조군 marker·시험 설정만 finally로 정리한다. 관리형 보호·서비스·기존 승인 계약·원장은 유지한다.

## 기대 결과와 통과 조건

| 경로 | 기대 결과 | 필요한 독립 증거 |
| --- | --- | --- |
| 비승인 stdio/별도 실행 파일 | 보호 설정 또는 OS 실행 경계에서 거부 | 실제 시도, 거부 원인·profile, fixture tools/call 수신 0·marker 효과 0 |
| localhost HTTP IPv4/IPv6 | 관리형 UID의 직접 접속 거부 | 실제 접속 시도, UID·목적지·수집 이벤트, localhost 수신 0 |
| 일반 계정 대조군 | fixture가 실제 동작 | protocol 수신과 예상 marker 효과. 관리형 성공으로 집계하지 않음 |
| 승인 Gateway 경로 | 정상 도구 실행·본문 일치 | 하네스→Gateway 원장→fixture 수신/효과 연결 |

OS 거부에는 Gateway `policy_id`를 만들어 붙이지 않는다. Gateway 밖에서 막았으면 엔드포인트 증거로 기록하고 Gateway 도구 원장 부재를 누락으로 오판하지 않는다. 승인 바이너리 내부에서 실행되는 임의 코드나 Desktop/in-process 플러그인은 별도 범위로 남기며 이 시험만으로 안전을 주장하지 않는다.

## 실패 시 수정

- **비승인 실행 성공:** 배포된 launcher의 실제 파일·권한·profile 전이·exec 허용 목록을 확인하고 필요한 실행만 승인 경로로 제한한다. 전체 interpreter 허용으로 정상군을 복구하지 않는다.
- **localhost 직접 접속 성공:** 실제 관리 UID에 적용된 nftables의 IPv4/IPv6·loopback 규칙과 우선순위를 수정하고, 허용된 Gateway/모델 프록시만 정상 대조군으로 유지한다.
- **미수집:** collector/audit 경로·마지막 성공·실패 시각과 UID/PID 상관관계를 보강한다. 로그가 없다는 이유로 차단 성공을 선언하지 않는다.
- **승인 정상군도 실패:** 필요한 MCP는 솔루션 기기에서 격리 실행해 Gateway에 독립 승인·등록하고, 관리 하네스 설정을 레지스트리에서 다시 렌더링한다. 비승인 직접 실행을 허용해 통과시키지 않는다.

## 코드와 현재 결과

[enforce-linux.py](../../../endpoint-agent/enforce-linux.py), [managed-linux.py](../../../endpoint-agent/managed-linux.py), [managed_kernel_proof.py](../../../full_stack_lab/tests/managed_kernel_proof.py), [run-server.sh](../../../full_stack_lab/mcp/run-server.sh)를 출발점으로 사용한다. 로컬 파일에는 기존 미커밋 작업이 있으므로 실행 증거에는 설치본 hash와 실제 profile을 사용한다.

미실행. `runs/<실행일>/E13/report.md`에 각 경로의 성공·실패·미확인과 원복을 기록한 후 카탈로그를 갱신한다.
