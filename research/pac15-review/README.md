# 팀원 PAC-15 Rego 초안 검토 (2026-09-30 ~ 10-01)

팀원이 준 `pac15-mvp 2.zip`(PAC-01~15를 `package mcp.pac15`·`mcp.decision`으로 구현한 초안)을
Gateway에 넣기 전에 따로 시험한 기록이다. **다시 돌릴 수 있게** 원본·수정본·시험을 같이 둔다.

```bash
./run.sh      # 원본과 수정본을 OPA 1.20.2(Gateway와 같은 이미지)로 따로 띄우고 같은 300건을 보낸다
```

| 경로 | 내용 |
| --- | --- |
| `original/policy/` | 받은 그대로의 `pac15.rego`·`decision.rego` |
| `fixed/policy/` | 아래 결함을 고친 사본. 바꾼 곳마다 `REVIEW: B<n>` 주석 |
| `examples/allow.json` | 받은 허용 예시(모든 시험 입력의 바탕) |
| `pac15_suite.py` | 정상 동작 200건 + 결함 탐색 100건 |

## 결과

| | 정상 200건 | 결함 탐색 100건 중 fail-closed가 아닌 동작 |
| --- | --- | --- |
| 원본 | 200/200 (ALLOW 83 · APPROVAL 20 · DENY 97) | **59건** |
| 수정본 | 200/200 (같은 분포) | **0건** |

정상 200건은 두 버전에 같은 입력을 보낸다. 입력에는 수정본이 요구하는 사실(로컬 커넥터의 신원·기한·scope,
승인자 id)도 들어 있다 — 원본은 읽지 않는 필드를 무시하므로 두 버전에게 같은 뜻이다.

## 결함과 수정

| 번호 | 건수 | 원본의 동작 | 원인 | 수정 |
| --- | --- | --- | --- | --- |
| B1 | 26 | `total_calls: null`, `retry_count: true`, 한도 `max_calls: "1"`에 999999회, 음수 카운터 → **ALLOW** | Rego는 타입이 다른 값도 순서를 매긴다(null < boolean < number < string). `null <= 10`, `5 <= "1"`이 참 | `within_limit`: 둘 다 숫자이고 값 ≥ 0일 때만 한도 비교. 예약 만료 시각도 숫자 검사 |
| B2 | 7 | 바인딩된 `opts.path` 옆의 `opts.cmd`·`opts.url` 등 → **ALLOW** | 최상위 키만 바인딩과 대조 | 스칼라 **잎 경로**가 전부 바인딩돼 있어야 함(배열 안은 늘 거부 — 기능별 추출기가 필요하다는 초안 설계서의 원칙 그대로) |
| B3 | 6 | 선택 인자를 뺀 정상 호출 → **DENY**(과차단) | 모든 바인딩이 존재해야 함 | 바인딩에 `optional: true`를 둘 수 있고, 있으면 없는 것을 허용·있으면 똑같이 검사 |
| B4 | 9 | 수동 호출에 받은 단회 승인을 자동 실행·대리 실행·다른 환경에서 사용 → **ALLOW** | 승인 다이제스트에 environment·automated·on_behalf_of가 없음 | `approval_binding`에 네 필드(+high_risk) 추가 |
| B5 | 6 | `auth.mode: "local"`이면 폐기·만료·scope·커넥터 신원을 전혀 보지 않음 → **ALLOW** | 로컬 분기가 `verified`만 봄 | 로컬도 `connector_id ∈ approval.local_connectors`, `not_revoked`, 유효기간, action ∈ scopes |
| B6 | 4 | 요청자가 자기 고위험 호출을 승인 → **ALLOW** | 승인자 신원 검사 없음 | `approver_id`가 비어 있지 않고 요청자와 달라야 함 |
| B7 | 1 | 요청 ID `" "` → **ALLOW** | `!= ""`만 검사 | `trim_space` 후 비교 |

탐색 100건 중 나머지 41건(잘못된 형식의 입력 28건 + 타입·대소문자 변형 13건)은 원본도 DENY로 올바르게 처리했다.

**시험 쪽 정정 한 가지.** 첫 실행(2026-09-30)의 B5에는 로컬 모드에서 `audience`·`issuer`를 바꾼 2건이 있었다.
로컬 연결에는 발급자도 대상도 없으므로 그건 시험의 잘못이었다. 커넥터 신원(`connector_id`)과 시작 시각을 바꾸는
2건으로 교체했고, 원본은 이 2건도 허용하므로 총계는 여전히 59건이다.

## 수정본이 바꾸는 입력 계약

팀원 초안의 자체 시험(`tests/run.py`, 39건)은 원본에서 39/39, 수정본에서 37/39다. 달라지는 2건은 의도한 변경이다.

| 시험 | 수정본에서 필요한 것 |
| --- | --- |
| `PAC-13 valid individual approval` | 승인 레코드에 `approver_id`(요청자가 아닌 사람) |
| `verified local connector` | `facts.auth`에 `connector_id`·`not_revoked`·`valid_from_ns`·`valid_until_ns`·`scopes`, `facts.approval.local_connectors` |

## Gateway에 그대로 넣지 않은 이유

초안은 `data.mcp.decision.decision`에서 `{effect, policy_ids}`를 돌려주고 `request`+`facts` 입력을 요구한다.
Gateway는 `data.mcp.authz.decision`에 `{decision, policy_id, reason, restrictions}`를 묻는다. 그대로 교체하면
결과가 비어 `P-CONTROL-FAIL-CLOSED`로 모든 호출이 차단된다(실측). 그래서 PAC 각각이 말하는 통제를 Gateway의 입력과
결과 계약 위에서 구현했고, 그 대응은 [../../docs/ai/PAC_MAPPING.md](../../docs/ai/PAC_MAPPING.md)에 있다.
수정본은 초안을 계속 발전시킬 때의 출발점으로 둔다.
