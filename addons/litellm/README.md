# LiteLLM 애드온

LiteLLM(1.105.0)이 MCP를 중앙에서 연결하는 기업도 MINT의 통제를 받게 한다. 승인·철회는 MINT가 LiteLLM 관리 API로 자동 반영하고(동기화),
호출 경로는 아래 두 가지 중 하나를 `MINT_LITELLM_ROUTE`로 고른다. 설계·한계는 [AI 게이트웨이 애드온](../../docs/ai/AI_GATEWAY_ADDON.md),
동기화 동작은 [LiteLLM 동기화](../../docs/ai/LITELLM_SYNC.md).

| | A. MINT 경유 (`mint`, 권장) | B. 직접 + 가드레일 (`direct`) |
| --- | --- | --- |
| 실제 호출 | LiteLLM → MINT `/mcp/<서버>/` → MCP 서버 | LiteLLM → MCP 서버 |
| LiteLLM에 등록되는 서버 | MINT 주소, `auth_type: oauth_delegate`(동기화가 등록) | 원래 주소, `auth_type: none`(동기화가 등록) |
| MINT가 보장하는 것 | 판정, 전송 직전 재검사, 사람 승인, 출력 통제, 기록 전부 | 호출 직전 판정과 사후 기록 |
| 직원이 보내는 헤더 | `x-litellm-api-key`, `x-mcp-<서버>-authorization: Bearer <본인 MINT 토큰>` | `x-litellm-api-key`, `Authorization: Bearer <본인 MINT 토큰>` |
| LiteLLM 설정 견본 | [config/litellm-mint.yaml](config/litellm-mint.yaml) | [config/litellm-plugin.yaml](config/litellm-plugin.yaml) + `mint_guardrail.py` |

공통 전제: **LiteLLM에 공유 직원 토큰을 넣지 않는다.** 직원마다 자기 MINT 토큰을 보내고, MINT는 그 토큰으로만 신원을 정한다.
LiteLLM이 주장하는 사용자·팀은 기록만 한다. A의 `oauth_delegate`는 받은 토큰을 그대로 넘기고 보관하지 않는다. B는 직원 토큰을 upstream으로 보내지 않는다.

## 설치

1. **LiteLLM 띄우기** — 위 견본을 LiteLLM `config.yaml`로 쓴다. 두 견본 모두 `require_key_mcp_access_defined: true`(키에 MCP 권한이 명시돼야 MCP를 씀)와
   프롬프트·응답 저장 끔이 들어 있다. A는 LiteLLM이 MINT의 사설 루트(`deploy/ca/root.crt`)를 신뢰해야 한다(`SSL_CERT_FILE`에 공인 CA와 합친 묶음).
   B는 `mint_guardrail.py`를 설정 파일과 같은 폴더에 두고 `MINT_GATEWAY_URL=https://<MINT 주소>`, `MINT_CA_FILE=<MINT 루트 PEM>`을 준다.
   망을 닫아 두려면 A 전용 묶음 [`full_stack_lab/llm/standalone`](../../full_stack_lab/llm/standalone/compose.yaml)(출구가 MINT뿐)을 쓴다.
2. **매핑 쓰기** — [sync-bindings.example.json](sync-bindings.example.json) 형식. `mint_user_id`는 MINT 아이디, `litellm_user_id`는 LiteLLM 사용자,
   `key_hashes`는 그 사용자 가상 키의 SHA-256, `workers`는 각 LiteLLM 워커에 직접 닿는 origin 전체다. 비밀 값은 넣지 않는다.
3. **켜기** — LiteLLM 관리자 키(proxy admin)를 파일로 준비해 MINT 서버에서:
   ```bash
   cd deploy
   ./mint.sh litellm enable --url https://<LiteLLM> --bindings 매핑.json --route mint < 관리-키-파일
   ./mint.sh litellm status
   ```
   점검(매핑·키·명시적 키 접근 설정·워커)이 통과해야 적용된다. 키 회전은 `./mint.sh litellm rotate-key < 새-키-파일`(재기동 없음).
4. **직원 계정** — PC 키트 없이 LiteLLM으로만 쓰는 직원은 `./mint.sh add-account <아이디> --role 직원 --ai-gateway`.
   직원은 MINT IdP(`/oauth/token`)로 자기 MCP 토큰을 받아 위 헤더로 보낸다. 승인 화면의 사용 대상에 들어 있어야 도구가 보인다.

정적 YAML 생성(`gen_mcp_servers.py`)은 동기화를 쓰지 않는 설치용으로 남겨 둔다. 동기화를 켜면 쓰지 않는다.

## 동작

- MINT에서 승인·등록하면 LiteLLM에 서버가 생기고 매핑된 키·팀에 승인 도구만 부여된다. 철회·중지·기한 만료면 서버와 권한·저장 자격·세션을 지운다.
- 완료 뒤에도 기본 300초마다 LiteLLM 상태를 다시 읽어, LiteLLM 쪽에서 바뀐 서버·도구·키 권한·팀 구성원을 되돌린다.
- 키·팀 하나의 매핑이 틀리면 그 대상만 권한을 받지 못하고 다른 직원은 계속 쓴다.
- B의 가드레일은 허용·경보·제한이고 원장에 기록된 판정일 때만 진행한다(제한이면 MINT가 준 인자로 바꿔 보냄). 그 밖은 모두 차단.
  호출 뒤 결과의 SHA-256·크기·오류 여부를 MINT에 남기고, MINT가 기록을 거절(`recorded:false`)하면 LiteLLM 로그에 경고를 남긴다.

### 한계

- B: 판정과 실제 전송 사이는 LiteLLM이 한다. 사람 승인이 필요한 판정은 차단으로만 끝난다. 결과 본문은 MINT를 거치지 않아 출력 검사·마스킹이 없다.
  LiteLLM 관리자가 등록 서버를 바꾸면 계약 확인이 적용되지 않는다(재조회가 동기화 대상 서버는 되돌린다).
- 동기화는 관리 상태 관측이다. 호출별 통제나 종료 판정(T1)의 증거가 아니다.
- 직원 하네스의 헤더 자동 구성(토큰 복사 없이 연결·만료 후 재연결)은 아직 없다. 직원이 토큰을 받아 헤더에 넣는다.

## 확인한 것

CI `litellm` 작업(새 실행기, 대역 없음): `deploy/`로 설치한 MINT + LiteLLM 1.105.0(digest 고정) + Microsoft Learn MCP.
결과와 실행 링크는 [보고](../../research/llm-wiki/status/reports/2026-10-25-litellm-addon.md).
