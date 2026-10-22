# LiteLLM이 이미 MCP를 통제할 때 MINT가 끼어드는 지점 — 솔루션·애드인 적용 설계 (2026-10-23)

P1 후속 구현(D-208): [승인·철회 동기화 근거](sync-implementation.md), [원자 요구사항](sync-requirements.json), [보고](../../status/reports/2026-10-23-litellm-sync.md). `10/23-litellm-sync`의 미커밋 구현과 로컬 대역 검증이며, 아래 설계 당시의 1.102 근거와 과거 기기 시험은 이력으로 유지한다. LiteLLM 1.105·PostgreSQL·PJ1 실기기 검증은 남는다.

- 작업자: Claude(Opus, 리더). 기준 main `7b7ad6d`. 제품 코드 변경 없음(설계).
- 이어받은 근거: [LiteLLM 중앙 MCP 기회 분석](../litellm-mint-opportunities-20261022.md)(중복 기능 표·가능성 1~3), [애드온 연동 문서](../../../../docs/ai/AI_GATEWAY_ADDON.md)·D-191(구현), [LiteLLM 심층 코드 분석](../oss-deep/litellm-mcp-path.md).
- LiteLLM 고정 소스: `f8e456d105`(1.102.0). 이번에 직접 확인한 행은 아래 표에 적었다. 그 밖의 동작은 위 분석의 범위를 이어받는다.
- 소유자 지시(10-22·23): 평가자 피드백 "LiteLLM 쪽에서 MCP를 연동하는 경우는 커버가 안 되나", "AddOn만 가능하다면 방어할 수 있다, 더 쉬운 쪽으로" → LiteLLM의 통제를 대체하지 않고 **끼어들 지점**을 솔루션·애드인 두 형태로 정리한다.

## 1. 전제 — LiteLLM이 이미 하는 것과 MINT가 다시 하지 않을 것

LiteLLM은 서버 제출·승인, 서버·도구 단위 키/팀 권한(`mcp_tool_permissions`, `mcp_access_groups`), 인자 규칙, 사용자별 자격 저장(BYOK·OAuth), 호출 전후 가드레일, 설명 검사, 도구 목록 고정(pin), 세션 종료·자격 철회(1.103), 공통 로그를 이미 제공한다([중복 표](../litellm-mint-opportunities-20261022.md#중복되는-기능과-정정)). MINT는 이 기능을 **복제하지 않는다.** 차별점으로 내세우지도 않는다.

MINT가 더하는 것은 LiteLLM이 구조적으로 보지 못하거나 맡지 않는 다섯 가지다.

| # | LiteLLM의 빈 곳 | MINT가 가진 것 (코드) |
| --- | --- | --- |
| G1 | **LiteLLM을 거치지 않는 MCP** — 직원 PC의 로컬 stdio MCP, 하네스가 원격 MCP에 직접 붙는 경로 | 엔드포인트 키트: 관리 계정·방화벽·하네스 관리형 설정으로 MCP 경로를 게이트웨이로 강제, 비인가 로컬 MCP 관측·차단(E13), 승인된 로컬 MCP 격리 실행(D-175·D-192) |
| G2 | **호출 단위 사람 승인** — 1.104 OWASP 매핑 기준 서버 측 호출 승인 단계 없음(agent 측 HITL 권고) | 고위험 호출 승인·인자 지문 결속·만료/철회(`dispatch.py`, `high_impact.py`, `core.py` 전송 직전 재확인) |
| G3 | **연결한 제3자 MCP의 공급망 검증과 실행 세대 대응** | 도입 심사 워커(Syft·Trivy·Semgrep·Gitleaks), 실행 세대·SBOM 영향 조회·중지(`sbom_impact.py`) |
| G4 | **실행 직전 live 계약 대조** — pin은 고정본 노출·알림, 출력 스키마는 pin 밖 | 설명·입력·승인 출력 스키마 해시 대조 후 `MCP-CATALOG-001` 차단(`core.py`), 출력 계약 검사 |
| G5 | **종료·폐기 증거와 실행불명 구분** | 차단·권한·전파·대상 상태 증거 분리(`decommission.py`), 전송 의도·응답 없는 쓰기 구분(`dispatch.py`) |

한계: G2는 판본 한정 관찰이다(새 판본에서 줄 수 있다). G3은 원격 SaaS MCP 내부를 검증하지 못한다. G4는 upstream pin 확장으로 격차가 줄 수 있다. 어느 하나도 영구 차별점으로 단정하지 않는다.

## 2. LiteLLM 안의 끼어들 지점 (고정 소스로 확인)

| 접점 | LiteLLM 위치 (`f8e456d105`) | 무엇을 할 수 있나 |
| --- | --- | --- |
| P1 관리 평면 | `proxy/management_endpoints/mcp_management_endpoints.py` 라우터 `/v1/mcp`: `/server/register`(1274)·`/server/{id}/approve`(1378)·`/reject`(1422)·`/server`(1569)·`/server/import`(1662)·`DELETE /server/{id}`(2131)·사용자 자격 저장/삭제(2197~2313). 키·팀 권한 필드 `_types.py:1116-1117` | 서버 등록·승인·삭제, 키/팀의 허용 서버·도구를 바꿀 수 있다 |
| P2 탐색 | 도구 목록 노출 단계(설명 검사·pin, 기회 분석 가능성 3) | 모델에 보이는 도구를 줄이거나 경고를 붙인다 |
| P3 호출 직전 | `mcp_server_manager.py:5335-5445` `pre_call_tool_check` → 가드레일 이벤트 `pre_mcp_call`(`types/guardrails.py:1153`, `proxy/utils.py:1492`) | 허용/거부, 인자 교체(`modified_arguments`) |
| P4 호출 중 | `during_mcp_call`(`types/guardrails.py:1154`). 같은 확장점을 Cisco AI Defense(`guardrail_hooks/cisco_ai_defense/cisco_ai_defense.py:72,362`)·Bedrock(`bedrock_guardrails.py:337`)이 쓴다 | 병렬 검사 — **외부 보안 제품이 LiteLLM에 붙는 공식 방식의 선례** |
| P5 호출 후 | `post_mcp_call`(`types/guardrails.py:1155`), 로그 훅 `custom_logger.py:567` `async_post_mcp_tool_call_hook`(응답 객체 변경은 in-place) | 출력 마스킹·거부, 결과 기록 |
| P6 전송 대상 | `mcp_servers`의 서버 URL·사용자별 인증 헤더 전달(`mcp_server/utils.py:159-215`, `mcp_server_manager.py:975-1040`) | 실제 전송 상대를 MINT 게이트웨이 `/mcp/<서버>`로 둔다 |

## 3. 두 가지 적용 형태

### 3.1 솔루션 형태 — "MINT를 LiteLLM의 MCP 업스트림 겸 통제 평면으로"

배치: LiteLLM(모델·키·예산·MCP 집계) → **MINT 게이트웨이**(판정·전송·원장) → 실제 MCP 서버. 직원 PC는 엔드포인트 키트로 MCP 경로를 LiteLLM/MINT로만 강제한다.

| 접점 | 적용 | 보장 수준 | 상태 |
| --- | --- | --- | --- |
| P6 | LiteLLM `mcp_servers`가 MINT `/mcp/<서버>`를 가리키고 직원 MINT 토큰을 사용자별 헤더로 전달(`addons/litellm/gen_mcp_servers.py`) | **최종 전송을 MINT가 쥔다** — G2·G4·G5가 그대로 동작, 판정~전송 경쟁 없음 | 구현(D-191 A). 기기 LiteLLM 1.105로 토큰별 전달·변조 거절 확인, 호출 판정 행은 승인된 시험 주체 대기 |
| P1 | **승인 동기화**: MINT 도입 심사·승인 결과로 LiteLLM 서버를 `/v1/mcp/server`로 만들고 키/팀 `mcp_tool_permissions`를 승인 도구로 맞춘다. 철회·SBOM 중지·폐기는 LiteLLM 서버 삭제·사용자 자격 삭제·세션 종료로 전파 | LiteLLM 화면과 MINT 원장이 같은 승인 상태. 전파 결과는 G5 증거로 기록(성공 응답만으로 완료 인정 안 함) | **선택 애드온 구현·로컬 대역 검증, 실기기 미실행**([근거·지원 범위](sync-implementation.md), D-208) |
| G1 | 엔드포인트 키트가 MCP 출구를 게이트웨이(=LiteLLM 경유 포함)로만 허용 | LiteLLM을 우회한 직접 연결·로컬 MCP까지 통제 범위 | 구현(D-62·D-71·D-192). LiteLLM 주소를 허용 출구로 넣는 설정은 미구현 |
| G3 | LiteLLM에 등록하려는 자체 배포 MCP는 MINT 도입 심사를 통과해야 P1 동기화 대상 | 공급망 검사·실행 세대 대응 | 심사는 구현, LiteLLM 연결은 P1과 함께 |

장점: 보장이 가장 강하다. 단점: LiteLLM 운영자가 MCP 서버 주소를 MINT로 바꿔야 한다(배치 변경).

### 3.2 애드인 형태 — "LiteLLM은 그대로, MINT는 플러그인으로"

배치 변경 없이 LiteLLM 설정 파일에 플러그인만 넣는다. 외부 보안 제품(Cisco AI Defense 등)이 쓰는 것과 같은 가드레일·콜백 확장점이다.

| 접점 | 플러그인 | 보장 수준 | 상태 |
| --- | --- | --- | --- |
| P3 | `mint_guardrail.py`(`pre_mcp_call`) → MINT `POST /api/addon/v1/mcp-decision` — 정책·동의·고위험 승인 필요 여부·계약 상태로 허용/거부/인자 교체. MINT 무응답이면 거부 | **사전 판정까지.** 판정 후 LiteLLM이 직접 전송하므로 전송 직전 재확인(G4 live 대조)·전송 의도 기록은 못 한다 | 구현(D-191 B). 실제 MINT 판정 API와의 기기 E2E는 승인된 시험 주체 대기 |
| P5 | 같은 플러그인의 사후 훅 → `POST /api/addon/v1/mcp-result`(결과 해시·크기·오류)로 원장 연결 | 실행 결과 증거(G5 일부) | 구현(D-191). `post_mcp_call`로 MINT 출력 계약 검사(마스킹·거부)를 붙이는 것은 미구현 |
| P2 | 탐색 훅에서 MINT 승인 목록·설명 경고·계약 불일치 도구를 숨기거나 표시 | 모델이 미승인·변경 도구를 보지 않음 | **미구현 — 2순위**(LiteLLM 판본별 탐색 훅 확인 필요) |
| P1 | 선택 동기화 워커: MINT 승인/철회 이벤트를 LiteLLM 관리 API에 반영 | 3.1의 P1과 공용. 관리 상태 전파이며 호출 신원 전달과 별개 | 선택 애드온 구현·로컬 대역 검증, 실기기 미실행(D-208). 직원 토큰을 새 동기화 경로로 전달하지 않음 |
| P4 | 필요 시 `during_mcp_call`로 병렬 검사(지연 없이 감사 기록) | 차단보다 관측 | 보류 |

장점: 고객 배치를 거의 바꾸지 않는다(설정 몇 줄). 단점: 사전 판정과 실제 전송 사이 경쟁이 남고(D-191 한계), LiteLLM이 주장한 사용자 신원은 기록만 한다(불변식) — 직원 MINT 토큰을 같이 넘길 때만 그 토큰으로 판정한다.

### 3.3 둘의 관계

- 같은 MINT 서버가 두 형태를 다 받는다. 고객은 MCP별로 고른다: **고위험·사내 자체 배포 MCP는 솔루션 형태(P6), 나머지는 애드인 형태(P3·P5)**.
- 엔드포인트 키트(G1)는 두 형태 모두의 바닥이다. LiteLLM이 중앙에서 통제해도 직원 PC가 LiteLLM을 우회하면 그 통제는 닿지 않는다. 키트가 출구를 LiteLLM/MINT로 묶어야 "중앙 통제"가 성립한다.
- 범용 AI 게이트웨이(Kong·Portkey·Envoy ext_authz)는 애드인 형태의 판정 API 계약을 그대로 쓴다([연동 문서](../../../../docs/ai/AI_GATEWAY_ADDON.md) C절, 미시험).

## 4. 발표 방어 문장 (사실 범위 안에서)

1. "LiteLLM이 중앙에서 MCP를 통제하는 고객에게 MINT는 대체재가 아니라 애드온이다. LiteLLM의 공식 가드레일 확장점(Cisco AI Defense가 쓰는 것과 같은 `pre/during/post_mcp_call`)에 MINT 판정을 꽂거나, LiteLLM의 MCP 업스트림을 MINT로 둔다."
2. "LiteLLM 통제는 LiteLLM을 지나는 호출에만 닿는다. 직원 PC의 로컬 MCP와 직접 연결은 MINT 엔드포인트 키트가 LiteLLM/MINT 경로로 강제한다."
3. "MINT가 더하는 것은 호출 단위 사람 승인, 연결 MCP의 공급망 검사와 중지, 실행 직전 계약 대조, 종료 증거다. LiteLLM에 이미 있는 ACL·자격 저장·설명 검사는 다시 만들지 않았다."
- 쓰지 말 것: "LiteLLM에는 승인·pin·세션 종료가 없다"(판본에 따라 틀림), "애드인만으로 MINT와 같은 보장"(판정~전송 경쟁 있음).

## 5. 다음 구현 (우선순위, 정상 기능 우선)

| 순위 | 작업 | 완료 조건 | 연결 |
| --- | --- | --- | --- |
| 1 | **승인·철회 동기화(P1)** — MINT 승인 → LiteLLM 서버·키/팀 도구 권한, 철회·중지·폐기 → LiteLLM 서버 삭제·자격 삭제 | LiteLLM 1.105 기기 시험에서 MINT 승인/철회가 LiteLLM 관리 화면·실제 호출 가능 여부에 반영되고 전파 결과가 원장에 남음 | AIG-01, G3·G5 |
| 2 | 애드인 플러그인의 실제 MINT 판정 E2E | 승인된 시험 주체로 허용·거부·인자 교체·MINT 무응답 차단을 원장 행으로 확인 | D-191 미실행 항목 |
| 3 | 탐색 단계 필터(P2) | 미승인·계약 불일치 도구가 모델 도구 목록에 안 나옴 | G4 |
| 4 | 키트 출구에 LiteLLM 주소 추가 설정 | 관리 계정이 LiteLLM 경유로만 MCP 사용, 직접 연결 차단 | G1 |
| 5 | `post_mcp_call`에 MINT 출력 계약·마스킹 | 출력 계약 위반 응답이 모델로 가지 않음 | G4 |

기기 시험은 저장소 규칙대로 솔루션 기기에서 별도 compose 프로젝트의 LiteLLM으로 하고, 콘솔 인증이 필요한 확인은 CI localhost 스택이나 사람이 로그인한 세션으로 한다(10-22 결정).
