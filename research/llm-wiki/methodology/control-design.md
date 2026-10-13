# MCP 통제 설계와 증거 계약

## 통제 위치

| 경로 | 확인할 것 | 결과 증거 |
| --- | --- | --- |
| 도입·승인 | 공급자·버전·라이선스·검사 결과·도구 계약·승인자 분리 | 신청 ID, 고정 commit/hash, 계약 diff, 승인 이력 |
| 게이트웨이 실행 전 | 토큰 신원, 권한, 계약, 인자·데이터·목적지, 승인 nonce | decision, policy_id, upstream_attempted=false |
| 게이트웨이 실행 | 예약·동시 호출·중복·실제 upstream·timeout | 요청/trace ID, upstream_attempted, 독립 서비스 효과 |
| 응답 통제 | 개인정보·Secret·주입·크기·검사기 장애 | response disposition, masked types, upstream 실행 여부 |
| 엔드포인트 | 관리형 설정, 프로세스·OS 경계, 직접 연결 우회 | 활성화 상태, 장치 결합, kernel/OS 이벤트 |
| 철회·종료 | 토큰·세션·자원 서버·제공자 조건 C1~C4 | 재접근 시도, 독립 효과, T1~T3 판정과 남은 공백 |

## 실험 기록의 최소 필드

```json
{
  "run_id": "실험 고유 ID",
  "code_revision": "확인한 코드 커밋",
  "policy_digest": "실제로 로드된 정책 해시",
  "managed_state": "확인한 장치 상태",
  "harness": "관찰된 실제 하네스와 버전",
  "model_involved": false,
  "decision_id": null,
  "decision": "미실행",
  "policy_id": null,
  "upstream_attempted": null,
  "upstream_executed": null,
  "independent_effect": "미확인",
  "evidence_paths": [],
  "cleanup": "미실행"
}
```

`null`은 미확인이며 `false`와 다릅니다. 공급자 timeout 뒤 효과는 없었다고 추정하지 않습니다. 하네스 설정 목록 조회는 실제 모델이 도구를 선택한 증거가 아닙니다.

## 검사 실패와 경계

계약 조회·정책 평가·PII/Secret 검사·목적지 확인에 실패하면 허용으로 넘어가지 않는지 시험합니다. 정상군을 반드시 두어 전부 차단하는 구현을 성공으로 세지 않습니다. 한 번 승인한 요청의 인자·도구·주체·기한을 바꿔 승인 재사용을 확인합니다.

직접 연결이 네트워크 분리 때문에 실패했으면 네트워크 차단 증거입니다. 엔드포인트 제품의 차단 증거는 실제 OS 이벤트와 장치 보고까지 있어야 합니다. 문서·소스상 구현과 실제 설치 기기의 활성화·집행은 따로 보고합니다.

## 이 저장소의 정본

[SECURITY_BOUNDARIES](../../../docs/ai/SECURITY_BOUNDARIES.md), [POLICY](../../../docs/ai/POLICY.md), [PAC_RUNTIME](../../../docs/ai/PAC_RUNTIME_2026-10-01.md), [TERMINATION_MODEL](../../../docs/ai/TERMINATION_MODEL.md), [TESTING](../../../docs/ai/TESTING.md)를 우선합니다. 오래된 ROADMAP의 미완료 표시는 최신 코드·현황과 대조하고 그대로 복사하지 않습니다.
