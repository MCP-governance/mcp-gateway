# 실험 사전 조건 및 증거 규칙

## 실행 장소

저장소 [AGENTS.md](../../../AGENTS.md)의 소유자 규칙에 따라 솔루션 배포는 솔루션 기기의 `./console.sh field up`, 실제 하네스 시험은 PJ1에서 한다. 이 노트북에는 compose 스택을 띄우지 않는다. 이 문서는 실행 명령을 자동화하지 않는다.

일반 컨테이너 랩의 테스트와 현재 field 배치의 테스트는 경로·서버·사용자·데이터가 다르다. lab 파일 경로를 PJ1에 그대로 넣어 성공할 것으로 가정하지 않는다. 데이터 fixture가 없으면 전용 fixture를 승인·등록한 뒤 경로와 계약 해시를 기록한다.

## 실행 전 동결할 값

1. 대상 솔루션의 실제 배포 commit 또는 release 식별자, 정책 bundle digest, 정책 관리대장 상태, registry·계약 잠금 hash를 기록한다. 이 카드의 판정 기준은 `enforcement=enforce`다. monitor 모드의 `would_decision`을 실제 집행 판정으로 세지 않는다. 로컬 checkout SHA만으로 배포 버전을 증명하지 않는다.
2. 실제 서버 버전·광고한 tools/list·승인된 schema·하네스 버전·모델·MCP endpoint를 기록한다. `mcp list`는 구성·연결 증거이고 모델의 tool call 증거는 아니다.
3. 현재 계정·등록 주체·관리형 identity·`managed_state=active`·fresh heartbeat를 확인한다. 설치만 되었거나 pending인 PC를 관리형 활성 시험으로 세지 않는다.
4. fresh한 전용 시험 주체를 사용하고, 최근 중요정보 열람·호출량·동시 실행·차단 누적이 사전 조건을 바꾸지 않는지 확인한다. 임의 JWT·heartbeat·PDP 결과를 만들어 실제 집행 증거로 쓰지 않는다.
5. 메일·파일·DB·공급자 자격의 원상태를 기록한다. 모든 값은 합성 fixture로 준비하고 실사용 조직 데이터로 공격 입력을 보내지 않는다. 활성 종료 케이스가 다른 실험·사용자의 케이스인지 확인한다.

## 실행 증거

| 증거 | 기록할 값 | 증명하는 것 |
| --- | --- | --- |
| 하네스 이벤트 | 실행 ID, 시각, 하네스·모델·도구·원본 이벤트 파일 hash | 모델이 실제로 선택한 MCP 도구와 호출 |
| MCP 프로토콜 | initialize·tools/list·tools/call, 요청 ID, 대상 endpoint, 결과 meta | 프로토콜의 실제 경로 |
| Gateway 원장 | decision ID, trace/request ID, decision, policy_id, principal, attempted/executed | 어떤 정책이 어느 요청에 적용됐는지 |
| upstream 및 대상 상태 | mock 수신 횟수·수신 메일·DB 변경·파일 변경·자격 접근 확인 | 시도와 완료, 실제 부수효과 |
| 복구 증거 | 변경 전후 hash·복구 결과·남은 fixture | 공유 환경이 정상화됐는지 |

원본 증거에 토큰·비밀번호가 있으면 원문을 위키에 커밋하지 않는다. 보고서에는 접근권한이 제한된 원본 위치와 hash, 비밀을 제거한 projection을 연결한다. 위키 Markdown 안에 공급자 token이나 실제 JWT를 넣지 않는다.

## 판정 기준

- 허용: 카드의 policy_id와 실행 허용 판정, attempted=true·executed=true, 실제 결과가 모두 일치해야 한다.
- 실행 전 차단: 카드의 policy_id, attempted=false·executed=false, upstream 요청·부수효과 0을 함께 확인한다.
- 승인 대기: approval ID와 인자 digest가 생성되되 승인 전 실행은 0이어야 한다. 승인이 아닌 다른 차단은 통과로 세지 않는다.
- 입구 인가: HTTP 상태·정책 식별자·MCP 세션 미생성·upstream 없음으로 판정한다. 도구 실행 원장이 아직 생기지 않은 것을 누락으로 오판하지 않는다.
- 도구 실패: upstream 시도 후 실패와 정책의 실행 예방을 구분한다. 검사기가 죽거나 증거가 없으면 실패 또는 미확인으로 남긴다.

## 원복

복구는 만든 시험 계정·fixture·서버·이용 관계만 대상으로 `finally` 또는 `trap`에 넣는다. 기존 `termination_flow.py` 같은 lab 전체 복구 코드를 공유 field 환경에서 그대로 실행하지 않는다. append-only 원장을 삭제하거나 수정해 상태를 깨끗하게 만들지 않는다.
