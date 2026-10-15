# OSS 심층 코드 분석 (DEV-47, 2026-10-15)

[OSS 감사·보완 계획](../oss-audit/README.md)의 2~5단계를 실행한 결과다. 분석은 서브에이전트(Codex gpt-6.1-sol, Claude Sonnet·Haiku)가 고정 commit의 로컬 클론을 **읽기만** 하고 [공통 지시](_brief.md)대로 썼다. 메인(Claude Opus)이 핵심 주장마다 원본을 다시 열어 대조했고, 틀린 부분은 각 문서 앞의 "메인 검토" 절에 고쳤다. 실행 재현(L4)은 하지 않았다.

## 분석 목록

| 문서 | 대상·고정 commit | 작성 | 깊이 | 한 줄 결론 |
| --- | --- | --- | --- | --- |
| [toolhive-runtime](toolhive-runtime.md) | stacklok/toolhive `v0.54.0` = `1ce13bbb` | sol | 수명·이미지·격리·브리지 L3 | DEV-38 첫 구현은 **자체 최소 실행기**. ToolHive는 기본 허용 gate·경고 후 진행 검증·하네스 직접 등록이라 승인 경계로 쓸 수 없고, 재조정·오류 분류 패턴만 참고 |
| [litellm-mcp-path](litellm-mcp-path.md) | BerriAI/litellm `f8e456d`(1.102.0) | sol | MCP 입구→권한→호출→사후 가드레일 L3 | upstream은 호출마다 세션 생성(재사용 근거 아님). 목록 완결성·원본 Tool 보존을 계약 전제로. 기존 BENCHMARK의 "5단 교집합·사후 검사 없음·재시도 없음"은 현 판본에서 틀림 |
| [ms-mcp-gateway-session](ms-mcp-gateway-session.md) | microsoft/mcp-gateway `3594c4e` | Sonnet | 세션·제어평면·수명·장애 L3 | 세션 키 `사용자:어댑터:세션ID`와 교차 재생 시험(`SEC-0003`)은 DEV-29 2단계 결속의 독립 근거. 어댑터 경로는 도구 단위 권한이 없고, 삭제가 세션 저장소를 정리하지 않음 |
| [contextforge-hooks](contextforge-hooks.md) | IBM ContextForge `5735c9d`, cpex-plugins `ae26938` | Sonnet(+메인 정정) | 훅 배선 L3, 엔진 L2 | 훅 엔진(`cpex.framework`)은 별도 패키지. 플러그인 오류 처리는 플러그인별 `mode`·`on_error`로 운영자가 고름(문서 근거). PDP 캐시 `invalidate()` 호출자 없음 |
| [mcpx-cisco-scanner](mcpx-cisco-scanner.md) | Lunar MCPX `fb93c38`, Cisco mcp-scanner `v4.8.6` | Sonnet | 신원·ACL·세션 L3, 스캐너 L3 | MCPX 신원은 서명 없는 `x-lunar-consumer-tag` 헤더, upstream 연결은 서버당 하나를 모든 소비자가 공유(반례). `proxy/`는 MIT 아님. 스캐너 오류가 빈 findings로 보일 수 있음 |
| [deps-sdk-authlib-opa](deps-sdk-authlib-opa.md) | MCP Python SDK `v2.2.0`, Authlib `v1.6.12`, OPA `v1.20.2` | Sonnet(Luna가 한도로 중단) | 사용 API→호출자→실패 결정 L3 | **`tools/list` 첫 페이지만 읽던 결함**, **ID 토큰 `aud` 값 미검증**을 찾음(둘 다 고침). OPA undefined·JWKS 회전은 이미 차단으로 닫힘 |
| [deps-presidio-gitleaks](deps-presidio-gitleaks.md) | Presidio `2.2.364`, Gitleaks `v8.30.1` | Haiku(+메인 정정) | L2~L3 | 검사기 장애는 차단으로 닫힘. 분할·다층 인코딩 입력과 언어 고정(`en`)이 미탐 위험. 오프셋 위험은 낮음 |
| [legacy-cards](legacy-cards.md) | Azure AI-Gateway·remote-mcp-apim·agent-framework·PyRIT·AGT | Haiku(+메인 확인) | L1~L2 정리 | 카탈로그 밖 5개 클론의 카드. **remote-mcp-apim 정책 10개 중 9개가 AI-Gateway 랩과 바이트 동일** → 독립 게이트웨이로 세지 않음 |

## 메인 검토에서 확인·정정한 것

| 주장 | 판정 | 근거 |
| --- | --- | --- |
| ToolHive 기본 gate는 모든 생성을 허용, 이미지 검증 `warn`은 provenance 없으면 경고 후 통과 | 확인 | `toolhive/pkg/runner/policy_gate.go:31-38`, `pkg/runner/retriever/retriever.go:344-357` |
| 기존 ToolHive 카드의 검토 commit `14c6066…` | 정정: v0.54.0 태그 = `1ce13bbb…` | `git rev-parse v0.54.0^{commit}` |
| MS Gateway 세션 키 결속, 삭제 시 세션 저장소 미참조 | 확인 | `AdapterSessionRoutingHandler.cs:113-126`, `AdapterManagementService.cs`에 `SessionStore` 0회 |
| ContextForge "플러그인 장애는 fail-open, MINT와 정반대 기본값" | **과장, 정정** | `tool_service.py:7531-7540`은 `raise`로 다시 올림. 실제 동작은 `docs/docs/using/plugins/index.md:1128-1135`의 플러그인 모드별 규칙 |
| MCPX 신원은 자기 신고 헤더 | 확인 | `mcpx/packages/mcpx-server/src/server/metadata.ts:54` |
| SDK `Client.list_tools`는 한 페이지만 반환 | 확인 | `mcp/client/client.py:924-944`(cursor는 호출자 책임) |
| Authlib은 `aud` 값을 옵션 없이는 비교하지 않음(azp만 확인) | 확인 | `authlib/jose/rfc7519/claims.py:143-152`, `oidc/core/claims.py:138-152` |
| Haiku 문서의 Presidio·Gitleaks commit | 정정 | 태그 commit `779dbd28…`, `83d9cd68…` |
| remote-mcp-apim이 AI-Gateway 정책의 사본 | 확인(새로 판정) | 정책 XML 10개 바이트 대조, 1개는 변수명 1개 차이 |

## 이번에 제품에 반영한 것

| 변경 | 출처 분석 | commit·결정 |
| --- | --- | --- |
| `tools/list`의 모든 페이지를 읽음(발견·카탈로그 점검·실행 직전 재확인) | deps-sdk-authlib-opa | `8906f24` |
| OIDC 콜백이 `aud`에 이 클라이언트가 있는지 확인 | deps-sdk-authlib-opa | `8906f24` |
| 승인 계약의 프로토콜 판으로 연결(신형은 탐색 왕복 없음) | DEV-29 설계 + SDK `client.py:456-462` | D-110, `f7563c8` |
| 목적지 없으면 주소 인자 불허, 중첩·배열·`$defs` 처리 | 검토 RV-01·04, litellm(원본 계약 보존) | D-111, `50347ee` |
| 관리 Claude는 관리 설정 훅만 실행 | 검토 RV-02 | D-112, `0a68a39`, PJ1 음성 시험 |

## 남은 L4 재현 후보

각 문서 9절에 시나리오가 있다. 우선순위는 [목표 기능 재검토](redesign-2026-10-15.md)의 순서를 따른다. 외부 저장소의 스크립트는 실행하지 않고, 필요한 OSS는 솔루션 기기의 격리 환경에서 고정 판본으로 띄운다.

## 서브에이전트 운용 기록

- Codex sol 2건·Luna 1건이 ChatGPT 사용량 한도로 중단됐다. sol 2건은 같은 세션을 재개해 완료했고, Luna 작업은 Sonnet이 새로 했다.
- Haiku는 지시와 달리 `status/reports/`에 보고서를 추가로 만들었다(2회). 메인이 지우고 분석 문서만 남겼다. 고정 commit 표기도 틀려 고쳤다. Haiku는 요약·정리에는 쓸 만하지만 사실 근거가 필요한 판정은 메인 대조가 필수다.
