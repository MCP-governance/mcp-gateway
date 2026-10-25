# 외부 AI 게이트웨이 애드온 (D-191)

기업이 LiteLLM·Kong·Portkey 같은 AI 게이트웨이로 MCP를 중앙 연결하면 직원 PC의 하네스는 MINT를 거치지 않는다.
MINT는 이런 게이트웨이에 붙는 세 가지 방법을 제공한다. 코드와 설치는 [addons/litellm](../../addons/litellm/README.md).

도입 승인·철회를 관리 API로 전파하는 선택 기능은 [LiteLLM 동기화](LITELLM_SYNC.md)(D-208·D-249)를 본다. 기본 꺼짐이며 호출 판정 API와 별도다. 동기화가 등록하는 주소와 인증은 `MINT_LITELLM_ROUTE` 하나가 정한다: `mint`이면 A(아래 표), `direct`이면 B. 운영 배포는 `./mint.sh litellm enable`로 켠다.

키트 없이 중앙 AI 게이트웨이로만 MCP를 쓰는 직원은 `./mint.sh add-account <아이디> --role 직원 --ai-gateway`로 만든다(D-250). 이 직원은 관리형 PC 없이 자기 MINT 토큰을 받고, 판정·원장 귀속은 다른 직원과 같다.

| 방식 | 구성 | MINT가 보장하는 것 | 필요한 것 |
| --- | --- | --- | --- |
| A 업스트림 | AI 게이트웨이의 MCP 서버가 MINT `/mcp/<서버>/`를 가리킨다 | MINT의 모든 통제(전송 직전 재검사, 승인, 출력 통제, 기록) | 게이트웨이가 직원 토큰을 서버별로 MINT에 전달 |
| B 플러그인 | MCP 서버는 AI 게이트웨이에 직접 등록. 호출 직전에 MINT 판정을 부른다 | 호출 직전 판정과 사후 기록 | 호출 직전 훅, 직원 토큰 접근 |
| C 범용 | B와 같은 판정 API를 다른 게이트웨이가 부른다 | B와 같다 | 아래 계약을 지키는 훅 |

## 판정 API 계약 (B·C)

모든 요청에 `Authorization: Bearer <직원 MCP 토큰>`이 필요하다(직원 PC 키트가 발급하는 `mcp` scope 토큰, 콘솔 토큰은 403).
**신원은 이 토큰에서만 정한다.** 본문의 `asserted`는 기록만 하며 판정에 쓰지 않는다.

### `POST /api/addon/v1/mcp-decision` — 호출 직전

```json
{ "server_id": "context7", "tool": "resolve-library-id", "arguments": {"libraryName": "react", "query": "hooks"},
  "gateway": "litellm", "asserted": {"user_id": "u-123", "team_id": "t-9"}, "call_ref": "게이트웨이의 호출 ID" }
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `server_id` | 예 | MINT에 등록된 서버 ID. 게이트웨이의 서버 별칭과 같아야 한다 |
| `tool` | 예 | 서버가 아는 원래 도구 이름(게이트웨이가 붙인 접두어 제외) |
| `arguments` | 아니오 | 도구 인자 객체. 기본 `{}` |
| `gateway` | 아니오 | 게이트웨이 종류(40자). 기록용 |
| `asserted` | 아니오 | 게이트웨이가 주장하는 사용자·키·팀. 최대 10개, 기록용 |
| `call_ref` | 아니오 | 게이트웨이 쪽 호출 ID(80자). 기록용 |

본문에 정의되지 않은 필드가 있으면 422다.

```json
{ "decision": "Allow", "allow": true, "policy_id": "P-AUTHZ-ALLOW-001", "reason": "…", "decision_id": 4021,
  "effective_arguments": null, "upstream_executed": false, "delivery": "caller" }
```

- `decision`: `Allow` · `Alert` · `Restrict` · `Approval` · `Block`.
- `allow`: **`true`일 때만 진행한다.** `Allow`·`Alert`·`Restrict`이고 판정이 원장에 기록되었을 때만 `true`다.
- `effective_arguments`: `Restrict`로 바뀐 인자. 있으면 호출자는 이 인자로 보내야 한다. 바뀐 것이 없으면 `null`.
- `Approval`: 이 경로는 승인 대기 건을 만들지 않는다. 호출자는 차단으로 취급하고 `reason`을 사용자에게 보여 준다.
- `decision_id`: 원장 행. 사후 기록에 쓴다.

### `POST /api/addon/v1/mcp-result` — 호출 후(선택)

```json
{ "decision_id": 4021, "outcome": "executed", "is_error": false, "result_sha256": "<64자 hex>", "result_bytes": 163 }
```

같은 직원의 애드온 판정에만 붙는다. 응답은 `{"recorded": true, "event_id": …}` 또는 `{"recorded": false, "reason": …}`.
원장의 판정 행은 고치지 않고 별도 사건(`addon-result`)으로 덧붙는다. 결과 본문은 보내지 않는다.

### 호출자가 지킬 규칙 (fail-closed)

다음은 모두 **차단**이다: `allow`가 `true`가 아님, 200이 아닌 응답(401·403·422·5xx), 시간 초과·연결 실패, JSON이 아닌 응답,
직원 토큰 없음. 사후 기록 실패와 `recorded:false` 응답은 이미 나간 호출을 되돌릴 수 없으므로 호출자 로그에 경고로 남긴다.

```bash
curl -sS https://<게이트웨이>/api/addon/v1/mcp-decision -H "Authorization: Bearer $MINT_TOKEN" \
  -H 'Content-Type: application/json' -d '{"server_id":"context7","tool":"resolve-library-id","arguments":{"libraryName":"react","query":"hooks"}}'
```

## 게이트웨이에 붙이는 방법

| 게이트웨이 | 훅 | 상태 |
| --- | --- | --- |
| LiteLLM | A: `oauth_delegate` 서버(동기화가 등록) · B: 커스텀 가드레일 `pre_mcp_call` | 1.105.0, CI `litellm` 작업에서 실제 MINT와 함께 검수 ([addons/litellm](../../addons/litellm/README.md)) |
| Kong, Portkey, Envoy `ext_authz` 등 | 요청 본문(서버·도구·인자)을 읽을 수 있는 호출 직전 훅 | **계약만 제공, 미확인**. 응답 형식이 다른 훅(예: 허용 여부만 보는 훅)은 `allow`를 그 형식으로 바꾸는 얇은 어댑터가 필요하다 |

붙이려면 ① 도구 호출 직전에 서버·도구·인자를 읽을 수 있고, ② 직원 MINT 토큰을 받을 수 있고(예: `Authorization`),
③ 판정이 허용이 아니면 호출을 막을 수 있어야 한다. 하나라도 안 되면 A 방식을 쓴다.

## 한계 (B·C)

- **판정과 전송 사이의 경쟁**: 전송은 호출자가 한다. MINT는 전송 직전 검사를 하지 못하고, 판정 뒤 승인이 철회되거나 서버 상태가 바뀌어도 이미 진행한 호출은 막지 못한다. 최종 전송 검사가 필요하면 A 방식이다.
- **신원**: 호출자가 직원 토큰을 가져와야 한다. 게이트웨이가 주장하는 사용자 ID만으로는 판정하지 않는다.
- **출력**: 결과 본문은 MINT를 거치지 않으므로 출력 검사·마스킹·도구 설명/스키마 계약 확인이 적용되지 않는다.
- **승인**: 사람 승인이 필요한 판정은 차단으로만 끝난다.
- **네트워크**: 게이트웨이가 MINT의 `/api/addon/v1/*`에 닿아야 한다. 제품 앞단(`field/Caddyfile`)에 경로를 추가했으며 적용하려면 재기동이 필요하다.
