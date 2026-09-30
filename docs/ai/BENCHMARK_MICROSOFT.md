# Microsoft MCP 관련 공개 소스 분석 — 2026-09-30 정정본

## 범위와 결론

[microsoft/mcp-gateway](https://github.com/microsoft/mcp-gateway/tree/3594c4eee36308ac131aad1c946ea14140b4353d)의
`3594c4eee36308ac131aad1c946ea14140b4353d`와
[microsoft/wassette](https://github.com/microsoft/wassette/tree/742ebb7236273dad2d88c415eabe872d3b95dff9)의
`742ebb7236273dad2d88c415eabe872d3b95dff9`를 다운로드한 소스로 검토했다.
이 문서는 해당 커밋의 정적 관찰이다. Azure API Management·Entra·Foundry·Purview·Defender 전체의
기능을 이 작은 저장소의 검색 결과로 부정하지 않는다. Microsoft 스택을 배포한 비교 실험도 아니다.

MCP Gateway는 라우팅·세션·서버 수명주기·Entra 연동에, Wassette는 Wasm 실행과 자원 권한에
각각 초점이 있다. “아무 통제가 없는 기준선”이라는 기존 표현은 부정확하여 철회한다.
우리 Gateway와 통제 위치를 맞춰 비교해야 한다.

## MCP Gateway의 실제 코드 경로

### 입구 인증과 관리 권한

[`Microsoft.McpGateway.Service/src/Program.cs`](https://github.com/microsoft/mcp-gateway/blob/3594c4eee36308ac131aad1c946ea14140b4353d/dotnet/Microsoft.McpGateway.Service/src/Program.cs)는
production에서 Microsoft Identity Web JWT 인증과 MCP resource metadata를 구성한다. Development 또는
`Authentication:BypassEntra` 설정은 `X-Dev-*` 개발 인증 경로를 켠다. 후자를 인터넷 노출 운영 설정으로
복사하면 안 되며, 개발 모드의 성공을 production 신원 검증 증거로 사용하지 않는다.

관리·데이터 경로의 역할을 분리해서 봐야 한다. 같은 파일은 `BuiltinToolAuthorizer`와
`WorkloadIdentityAuthorizer`를 등록한다. 관리 프로젝트의 `Authorization/` 두 구현은 명시적 설정이
없으면 `mcp.admin`만 허용한다. 전자는 bash/read_file/write_file 같은 내장 도구, 후자는 공유 workload
identity 사용을 제한한다. 이것은 실제 서버 측 권한 검사이며 단순 포털 표시가 아니다.

우리 쪽도 역할만 비교하면 부족했다. 직원 PC의 `mcp` 토큰이 관리자 역할을 갖더라도 Console 계정 관리,
등록·승인·예외·스캔 같은 control plane은 `console` scope를 요구하도록 공통 인증 경계에서 보강했다.
scope 없는 구형 토큰을 암묵적으로 관리 토큰으로 취급하지 않는다. 다시 로그인하여 올바른 토큰을 발급한다.

### 라우팅, 저장소와 수명주기

Service의 `Routing/`, `Session/`는 MCP session affinity와 node 라우팅을 처리한다. Management의
adapter/tool 서비스는 등록·배포·갱신·삭제를 Kubernetes 및 자원 저장소에 연결한다.
development의 Redis 부재 시 메모리 저장소 fallback과 production Cosmos 구성은 역할이 다르다.
개발의 재시작 후 상태 소실을 운영 제품의 고정 특성으로 일반화하지 않는다.

서버 등록·삭제는 “그 서버가 가진 외부 SaaS refresh token까지 폐기됐음”과 같은 진술이 아니다.
우리 종료 판정 C1~C4도 Gateway 경로 차단, endpoint 항목 삭제, provider 자격 폐기 증거를 구분한다.
원격 DELETE 성공이나 GatewayLog 한 줄만으로 모든 잔존 권한이 사라졌다고 판정하면 안 된다.

### 도구 정의와 내용 정책

도구 resource에는 definition metadata와 input schema가 있다. 이는 우리 `contracts.lock.json`의
검토한 설명·스키마·버전 고정과 호출 직전 같은 upstream session에서의 재대조와 동일한 보장이라고
단정할 수 없다. 반대로 해당 저장소에서 요청별 DLP/OPA 코드가 보이지 않는다는 사실은 Microsoft가
외부 정책 엔진이나 API Management로 이를 구성할 수 없다는 뜻도 아니다.

비교표의 상태는 다음처럼 표현한다.

| 주제 | 검토 커밋에서 확인한 것 | 추가 확인 필요 |
| --- | --- | --- |
| 신원 | Entra JWT와 개발 인증 분기 | 실제 tenant·audience·권한 오류 시험 |
| 관리 권한 | privileged built-in/shared identity authorizer | 조직 role 설정과 배포된 control plane 경계 |
| MCP 라우팅 | session routing·adapter/tool resource | multi-node 장애·세션 재개 |
| 데이터 내용 | 이 검토만으로 자산등급×외부목적지 정책의 동등성 입증 못 함 | APIM·외부 PDP·DLP 구성 |
| 계약 변경 | metadata/schema가 있음 | 승인된 hash baseline과 호출 전 재대조 여부 |
| 전체 확장 설치 통제 | Gateway 경유 resource 통제 | endpoint/OS·egress·직접 앱 경로 통제 |
| 공급자 자격 회수 | resource 수명주기 관리 | provider token introspection·revocation state |

## Wassette와 실행 경계

Wassette는 Wasmtime/WASI로 Wasm component를 MCP 도구로 실행하고 network·filesystem 자원 권한을
관리한다. 이는 임의 npm/stdio 프로그램이 로컬 사용자 권한으로 실행되는 경우와 다른 경계다.
우리 Gateway가 `tools/call`을 거부해도 이미 설치된 플러그인의 임의 프로세스 권한은 줄지 않는다.

기존 보고서에 있던 특정 deny 필드의 무효 주장이나 우회 가능성은 컴파일한 runtime 재현 증거가
동반되지 않아 이 정정본의 확정 결론에서 제외했다. 실제 적용 경로, host 함수 권한, 기본 deny,
DNS/redirect 동작은 동일 커밋을 실행하여 확인해야 한다. 존재하는 설정 필드만 보고 강제력을 주장하지 않는다.

즉시 Wasm 실행기로 모든 MCP를 변환하지 않는다. GitHub·Notion·Figma 등 원격 OAuth MCP는 Wasm
프로세스 샌드박스만으로 보호되지 않는다. 현 배치에서는 native policy, 별도 SaaS 자격,
Gateway의 결정론적 정책, 테스트 환경의 OS/네트워크 경계를 먼저 검증한다.

## Kong·LiteLLM과 함께 볼 점

[Kong AI MCP Proxy](https://developer.konghq.com/plugins/ai-mcp-proxy/)는 MCP 요청 라우팅·인증·정책
플러그인을 배치하는 경계를 제공한다. [LiteLLM MCP Permission Management](https://docs.litellm.ai/docs/mcp_control)는
MCP 서버·도구별 접근 권한을 key/team/user와 연결한다. 둘 다 조직 endpoint의 모든 셸·브라우저·별도
커넥터를 Gateway 하나만으로 강제 통제한다는 근거가 되지는 않는다. 제품·버전·설정 범위를 고정해 비교한다.

## 적용 결정과 다음 시험

승인 화면은 gateway resource 등록과 외부 앱 허용 요청을 구분하되, 승인된 레코드를 자동으로 모든
실행 환경에 적용하지 않는다. 실제 적용 여부는 장치의 managed config와 코드·정책 revision,
독립적인 upstream effect 및 packet evidence로 확인한다. 이번 `배포 확인` 화면은 Gateway/Console
코드 hash와 OPA 로드된 정책 일치를 보여준다. 단말 관리·egress 완전성을 의미하는 화면은 아니다.

추가 비교를 할 때는 공통 공격군, 실제 SaaS의 정상 연결 대조군, disabled 정책·인증 우회 개발 모드,
timeout·재시작·출력 유실, 공급자 권한 회수를 각각 검사한다. 우리 클린 환경 실행 결과는
[OVERHAUL_VALIDATION_2026-09-30.md](OVERHAUL_VALIDATION_2026-09-30.md)에 별도로 남긴다.
