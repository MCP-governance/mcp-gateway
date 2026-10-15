# PJ1 9개 도구 시험: 기존 원격 MCP 등록 경로 검토

기준: 2026-10-14, branch `10/14-pj1-nine-tools`, HEAD `ab6936c64f3578de8360b840f1928681714fa7bb`. 범위는 기존 Gateway 도입 신청·원격 계약 검토·등록·tools/list/호출 인가의 정적 코드 경로다. 구현과 설정을 읽었고 요청을 보내거나 DB를 변경하지 않았다. 로그인 token, secret, 사용자 인증값은 읽거나 출력하지 않았다.

## 권고

기존 원격 endpoint 도입 흐름을 사용한다. 공개 OSS 세 서버는 한 서버에 합치지 말고 **endpoint마다 별도 remote-endpoint 신청·review·approval·등록**으로 처리한다. 각 검토 본문은 실제 MCP `tools/list`에서 받은 전체 catalog hash를 대상으로 삼고, 선택 도구 map에는 해당 서버에서 선택한 도구만 넣는다. 세 등록을 합쳐 선택된 도구가 정확히 9개인지, 각 도구의 canonical ID 및 input schema가 [selection.md](selection.md)와 PJ1의 실제 Gateway `tools/list` 양쪽에서 일치하는지 확인한다. 기존 선택표는 시험 계획일 뿐 현재 등록·승인·PJ1 광고 스키마 증거가 아니다.

현재 선택 기준은 `git:git_status`, `git:git_log`, `git:git_add`, `git:git_commit`; `sqlite:search_objects`, `sqlite:execute_sql`; `playwright:browser_navigate`, `playwright:browser_snapshot`, `playwright:browser_evaluate`다. DBHub 구현을 사용하더라도 현재 canonical server ID는 `sqlite`다. PJ1에서 재조회한 값이 다르면 임의 이름변경·스키마 대체 대신 해당 차이를 보류하고 기존 등록 검토 절차를 다시 거친다.

## 신청·검토·승인·등록 호출 순서

모든 예시는 payload 구조만 보인다. `<...>` 값은 해당 task의 실제 비밀 아닌 endpoint, UUID, public metadata, 또는 `user_id`로 채우고 access token 값은 본문·로그·보고서에 넣지 않는다. 호출은 기존 Console 세션의 인증 경로를 사용한다.

1. 신청자는 `POST /api/mcp-requests`에 서버별로 `display_name`, `intake_kind: "remote-endpoint"`, `endpoint_url`, `requested_transport: "streamable-http"`, `purpose`를 제출한다. `repository_url`은 필요 없다. 요청 데이터 모델은 `agent_service.py:221-228`, handler는 `910-945`행이다. endpoint가 URL로 정규화/검증되지 않거나 remote 요청 transport가 Streamable HTTP가 아니면 신청이 거부된다. 중복 진행 신청은 409이다.

```json
{
  "display_name": "<server label>",
  "intake_kind": "remote-endpoint",
  "endpoint_url": "https://<public-host>/<mcp-path>",
  "requested_transport": "streamable-http",
  "purpose": "<task-only purpose>"
}
```

2. 관리자는 `POST /api/mcp-requests/{request_id}/review-contract`로 실제 계약을 조회·고정한다. 서버의 실제 이름, 버전, protocol version, 전체 catalog hash, 도구 이름/설명/schema 및 warning을 fresh `/api/registry/discover`로 가져온 뒤 확인한다. `tools` map에는 그 endpoint의 실제 도구 이름 중 선택한 것만 넣고 `r/w/x` action을 지정한다. `allowed_principals`에는 시험 사용자의 **활성 `user_id`**를 넣을 수 있으며 backend가 해당 활성 principal을 찾아 internal principal token으로 정규화한다 (`agent_service.py:1154-1213`). 사용할 endpoint는 신청에 기록된 URL과 정확히 같아야 한다. 각 selected tool마다 `parameter_constraints`가 정확히 하나 있어야 하며 모두 top-level JSON Schema `type: object`, `additionalProperties: false` 조건을 통과해야 한다.

```json
{
  "server_id": "<unique-server-id>",
  "endpoint": "https://<same-public-host>/<mcp-path>",
  "catalog_hash": "<fresh-discovery-sha256>",
  "tools": {"<exact-advertised-name>": "r"},
  "data_class": "<public|nonimportant|important>",
  "valid_days": 1,
  "poisoning_ack": false,
  "allowed_principals": ["<active-PJ1-user-id>"],
  "review_note": "<what was reviewed and the task-only scope>",
  "parameter_constraints": {
    "<exact-advertised-name>": {
      "type": "object",
      "properties": {},
      "required": [],
      "additionalProperties": false
    }
  }
}
```

이 예시는 구조 설명용이다. 실제 도구마다 실제 schema와 의미에 맞는 argument constraints가 필요하며, `properties: {}`를 그대로 적용하라는 뜻이 아니다. 도구 설명에 poisoning warning이 있으면 내용 검토 후 `poisoning_ack`를 true로 하는 별도 관리자 판단이 필요하다.

3. 별도의 관리자 승인 요청 `POST /api/mcp-requests/{request_id}/approve`는 신청자가 본인이면 거부된다. 원격 요청은 `REMOTE_REVIEWED` 상태, 저장된 remote contract, 동일한 fresh catalog hash·version·advertised server name·protocol version을 다시 요구한다. 검토자와 승인자는 동일해야 하며 신청자와 달라야 한다 (`agent_service.py:1069-1113`, `core.py:475-500`). Provider 종료/철회·감사 조건이 관리자가 확인한 형태로 충족되지 않으면 위험 수용 사유를 명시하는 경로가 있으나, 이는 확인 증거를 대체하는 risk acceptance일 뿐이다.

4. 승인 뒤 `POST /api/mcp-requests/{request_id}/register`에서 검토한 registration object 그대로 보낸다. request는 `server_id`, exact `endpoint`, `catalog_hash`, selected `tools`, `data_class`, `valid_days`, `poisoning_ack`다. handler가 이전 review의 `registration` object와 완전 일치를 확인하고 `intake_id`, `source_url`, supplier, purpose, owner department를 채워 `/api/registry/servers`로 전달한다 (`agent_service.py:1143-1157`, `1216-1246`; Gateway model/route는 `main.py:492-530`). 승인 후 scope·도구·등급·기한을 바꾸지 않는다. 새 선택은 새 신청/검토 흐름으로 진행한다.

5. 서버가 즉시 호출가능하다고 가정하지 않는다. `core.register_server()`는 RemoteContractReview의 exact endpoint/tools/data class/expiry/poisoning acknowledgment를 재확인하고, 현재 remote approval의 review digest·actor·expiry·endpoint를 검사하며, endpoint를 다시 discover해 version/name/protocol/full catalog hash를 확인한다. catalog drift, 승인되지 않은 tool, 만료, 기존 id 충돌을 거부한다 (`core.py:471-520`). runtime registration과 contract hashes는 승인된 상태로 저장되고, 선택된 도구만 `enabled=true`가 된다. fresh `refresh_catalog()` 결과가 정확히 맞으면 `READY`, 다르면 `DRIFT`로 기록한다 (`core.py:543-597`, `158-296`). Console 등록 서버는 별도 `/api/registry/{id}/approve-contract` route로 임의 재승인할 수 없고 새 intake를 거쳐야 한다 (`core.py:315-323`).

## scope와 tools/list/호출 guard

- `registry.allowed_principals()`는 remote Console 등록의 `allowed_principals`를 반환하며, intake가 없는 과거 등록은 빈 목록으로 닫힌다 (`registry.py:105-115`).
- Gateway MCP `tools/list`는 enabled tool, server 상태/lifecycle, principal allowlist 및 PAC scope를 통과한 도구만 노출한다. 원격 등록의 PAC scope는 정확 principal, 선택 tool, 승인 action, 비어있지 않은 parameter constraint 및 실제 arguments 유효성을 확인한다 (`mcp_facade.py:94-117`, `172-180`; `pac.py:41-54`).
- `tools/call`도 transport에서 검증한 principal을 사용하고 `execute_call()`로 전달한다. 호출 직전 allowlist 검사가 다시 있으며 tool enablement, catalog schema, policy/approval guards도 계속 적용된다 (`mcp_facade.py:182-195`; `core.py:1475-1489` 및 이후 dispatch checks). requester/admin이 선택 목록을 늘렸다는 것만으로 실행할 수 없다.
- 요청된 “92개 중 9개”는 task authorization이며 API 자체가 `len(tools)==9`를 고정한 것은 아니다. Remote review model은 1–300개를 허용한다 (`agent_service.py:1143-1157`). 따라서 세 review의 선택 도구 수 합계가 9인지, PJ1 실제 `tools/list`에서 허용된 user로 노출되는 합계가 9인지 시험자가 직접 확인해야 한다.
- 9개가 tools/list에서 보이는 것은 실행 승인과 같지 않다. 자연어로 요청한 각 쓰기·브라우저 호출은 별도 runtime approval guard, OPA decision, Gateway decision/policy, actual upstream dispatch/effect 확인을 거친다. `git_add`/`git_commit`, `sqlite:execute_sql`, `playwright:browser_evaluate`는 프롬프트에 적힌 제한이 실제 tool 권한 제한을 대신하지 않는다. 오직 disposable 합성 Git repo/DB/page를 사용한다.
- `/api/registry/discover`는 등록 전 계약 조회이고 등록/승인 상태를 만들지 않는다 (`main.py:488-518`). `POST /api/registry/servers`는 admin-only registry mutation이다 (`main.py:521-530`). `registry/discover`가 성공하거나 contract hash가 생긴 것만으로 업무 수행 승인·모델 tool call로 기록하지 않는다.

## 코드상 주의사항과 한계

`core.registration_endpoint()`는 scheme/hostname/userinfo/password/fragment와 remote HTTPS 요구를 확인하지만 URL query를 거부하지 않는다 (`core.py:447-454`). registry에 저장되는 endpoint 전체 URL에 query token/credential을 넣지 말고, 이 경로에서 자격정보 제공을 지원한다고 가정하지 않는다. URL userinfo와 fragment는 거부되어도 query parameter는 별도 위험이다.

Remote intake는 code scan을 수행하지 않는다고 계약 evidence가 명시한다 (`agent_service.py:1203-1205`, approve evidence 1102-1105). 따라서 공개 OSS라는 사실이나 version label만으로 source/audit 확인을 주장하지 않는다. 등록이 엔드포인트를 runtime egress endpoint로 허용하는 효과도 있으므로 세 URL과 DNS/서비스 소유자를 먼저 사람이 확인해야 한다 (`registry.py:90-95`, `core.py:812-838`).

기존 도구 선택안은 [selection.md](selection.md)와 [selection.json](selection.json)이다. 이 파일들은 schema/prompt 계획이며 실제 PJ1 server endpoint의 현재 advertised schema, intake 승인 또는 natural-language call 성공 증거가 아니다. 특히 선택안의 예전 후보/로컬 tool-capabilities 버전이 현재 PJ1 공급자 endpoint 버전과 다르면 실제 discovery 응답을 기준으로 새로 비교한다. 코드 검토를 위해 `Authorization` header 형태 외 자격·세션 저장소를 확인하지 않았으며, 어떠한 토큰 값도 이 보고서에 넣지 않았다.
