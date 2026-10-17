# 논문·프로토콜·보안 문서

다음 구현에 필요한 자료는 [작업별 읽기 지도](development-reading-guide.md)에서 찾는다. 정책50 구현 공백을 메우는 자료 36건은 [정책50 공백 지도](policy50-gap-references.md)에서 공백·POL 번호별로 찾는다. [2026-10-15 공식 근거](../analysis/review-2026-10-15/references.json)는 명세 판본·빌드 provenance·하네스 훅·행 잠금·관측·배포 절차를 최근 검토와 연결한다. 별도 19개 링크를 기존 167개 연구 문헌 수에 합산하지 않는다.

2026-10-13 [정식 저널3건·기존 학회/preprint 재검토](../analysis/reference-updates.json)와 [방법론](../methodology/evidence-methodology.md)을 추가했다. 저널의 서지·선별 내용 확인과 전문 정독을 구분하며 새3건의 전문은 확보하지 못했다.

- [TOSEM MCP landscape](REF-J01.md)
- [IEEE TSE Beyond the Protocol](REF-J02.md)
- [Information Sciences 비교 취약점 연구](REF-J03.md)

개발에 직접 필요한 공개 자료를 선별했다. 각 페이지는 원본·전체 추출 MD·이전 위키 provenance·SHA-256 경로로 이어진다. 재배포가 확인되지 않은 원본·전체 MD는 로컬 캐시에만 보존하며 공개 Git과 웹 본문에서 제외한다.

보존 자료는 재현용 스냅숏이다. 요약의 적용 제안은 아직 검증되지 않은 개발 후보이며 현재 배포의 통제 증거를 대신하지 않는다.

## 먼저 읽을 순서

1. T01·T02·T21: 인가, 도구 계약, 프록시 보안 경계.
2. P54·P57·P51: 실행 권한, 데이터 계보, 통제 배치.
3. P60·P43·P39·P38: 도구 오염, 공격 표면, 정상 업무와 공격 실험.
4. T15·T19·T20·T22: 서버·자격·진행 중 작업 종료 증거.

| ID | 자료 | 개발 연결 | 원본 / MD | 배포 |
|---|---|---|---|---|
| P38 | [InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents](P38.md) | fetch·email·파일 읽기 결과를 통해 외부 전송이 유도되는 사례를 만든다. | [원본](../sources/policy/P38/originals/P38.pdf) · [MD](../sources/policy/P38/extracts/P38.md) | public-under-license |
| P39 | [AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents](P39.md) | 동일한 데이터 스냅숏에서 무방어·Gateway·추가 통제의 비교군을 만든다. | [원본](../local-sources/policy/P39/originals/P39.pdf) · [MD](../local-sources/policy/P39/extracts/P39.md) | local-only |
| P43 | [MCPSecBench: A Systematic Security Benchmark and Playground for Testing Model Context Protocols](P43.md) | 위협 XLSM에 공격 표면·실행 위치·검증 수단을 추가한다. | [원본](../local-sources/policy/P43/originals/P43.pdf) · [MD](../local-sources/policy/P43/extracts/P43.md) | local-only |
| P46 | [Systematization of Knowledge: Security and Safety in the Model Context Protocol Ecosystem](P46.md) | 도구 목록·리소스·프롬프트 응답의 관측 범위를 명시한다. | [원본](../local-sources/policy/P46/originals/P46.pdf) · [MD](../local-sources/policy/P46/extracts/P46.md) | local-only |
| P47 | [Real Faults in MCP Software: A Comprehensive Taxonomy](P47.md) | 잘못된 스키마·빈 결과·이상 응답·전송 종료·설정 누락을 회귀 사례로 만든다. | [원본](../local-sources/policy/P47/originals/P47.pdf) · [MD](../local-sources/policy/P47/extracts/P47.md) | local-only |
| P51 | [MCP-DPT: A Defense-Placement Taxonomy and Coverage Analysis for Model Context Protocol Security](P51.md) | 각 정책에 Gateway·엔드포인트·하네스·MCP 서버의 책임을 표시한다. | [원본](../sources/policy/P51/originals/P51.pdf) · [MD](../sources/policy/P51/extracts/P51.md) | public-under-license |
| P54 | [Progent: Securing AI Agents with Privilege Control](P54.md) | OPA 정책과 승인 레코드의 자원·동작·목적지·만료 결합을 비교한다. | [원본](../local-sources/policy/P54/originals/P54.pdf) · [MD](../local-sources/policy/P54/extracts/P54.md) | local-only |
| P55 | [Design Patterns for Securing LLM Agents against Prompt Injections](P55.md) | 고위험 쓰기 도구는 제한된 인자·사전 계획·승인 계약으로 묶는 후보를 검토한다. | [원본](../sources/policy/P55/originals/P55.pdf) · [MD](../sources/policy/P55/extracts/P55.md) | public-under-license |
| P57 | [Securing AI Agents with Information-Flow Control](P57.md) | 읽은 민감 데이터와 외부 전송 호출을 trace·resource로 연결하는 후보를 검토한다. | [원본](../sources/policy/P57/originals/P57.pdf) · [MD](../sources/policy/P57/extracts/P57.md) | public-under-license |
| P58 | [Authorization Architectures for Tool-Using AI Agents](P58.md) | transport 신원과 자기 신고 하네스 정보를 섞지 않는다. | [원본](../local-sources/policy/P58/originals/P58.pdf) · [MD](../local-sources/policy/P58/extracts/P58.md) | local-only |
| P60 | [MCPTox: A Benchmark for Tool Poisoning on Real-World MCP Servers](P60.md) | tools/list 설명 변경·schema 변경·다른 도구 유출의 연쇄 사례를 만든다. | [원본](../local-sources/policy/P60/originals/P60.pdf) · [MD](../local-sources/policy/P60/extracts/P60.md) | local-only |
| P63 | [How Agents Ask for Permission: User Permissions for AI Agents, from Interfaces to Enforcement](P63.md) | 승인 UI에 동작·자원·목적지·범위·유효기간을 결합한다. | [원본](../local-sources/policy/P63/originals/P63.pdf) · [MD](../local-sources/policy/P63/extracts/P63.md) | local-only |
| P64 | [SafeHarness: Lifecycle-Integrated Security Architecture for LLM-based Agent Deployment](P64.md) | 지원 하네스에 직접 훅이 필요한 통제와 MCP 프록시로 가능한 통제를 분리한다. | [원본](../sources/policy/P64/originals/P64.pdf) · [MD](../sources/policy/P64/extracts/P64.md) | public-under-license |
| T01 | [MCP Authorization specification 2026-07-28](T01.md) | Gateway 토큰의 aud·issuer·scope·만료 검증을 실패 차단 테스트로 묶는다. | [원본](../local-sources/policy/T01/originals/T01_mcp_auth.html) · [MD](../local-sources/policy/T01/extracts/T01_mcp_auth.md) | local-only |
| T02 | [MCP Tools specification 2026-07-28](T02.md) | 설명·스키마·annotation을 정규화한 계약 해시의 변화 테스트를 만든다. | [원본](../local-sources/policy/T02/originals/T02_mcp_tools.html) · [MD](../local-sources/policy/T02/extracts/T02_mcp_tools.md) | local-only |
| T04 | [Enterprise-Managed Authorization extension](T04.md) | Keycloak과 서버별 자격 브로커 연결의 지원 범위를 비교한다. | [원본](../local-sources/policy/T04/originals/T04.html) · [MD](../local-sources/policy/T04/extracts/T04_web.md) | local-only |
| T08 | [OWASP MCP Top 10 project](T08.md) | 위협 XLSM 항목별로 코드·정책·테스트·원장 증거의 연결을 추가한다. | [원본](../local-sources/policy/T08/originals/T08_owasp_mcp.html) · [MD](../local-sources/policy/T08/extracts/T08_owasp_mcp.md) | local-only |
| T10 | [RFC 9700 / BCP 240: Best Current Practice for OAuth 2.0 Security](T10.md) | refresh helper의 잠금·회전·재사용 시 계열 회수 동작을 점검한다. | [원본](../sources/live/T10/rfc9700.txt) · [MD](../sources/live/T10/rfc9700.md) | public-under-license |
| T11 | [RFC 8693: OAuth 2.0 Token Exchange](T11.md) | 직원 토큰을 upstream에 전달하지 않는 교환 경로를 설계할 때 참조한다. | [원본](../sources/live/T11/rfc8693.txt) · [MD](../sources/live/T11/rfc8693.md) | public-under-license |
| T12 | [RFC 9396: OAuth 2.0 Rich Authorization Requests](T12.md) | 승인 계약의 자원·동작·목적지·데이터 범위 필드를 비교한다. | [원본](../sources/live/T12/rfc9396.txt) · [MD](../sources/live/T12/rfc9396.md) | public-under-license |
| T15 | [CoSAI Model Context Protocol Security v2.0](T15.md) | TERMINATION_MODEL의 자격 회수·신규 호출 차단·진행 중 호출 정지 증거를 대조한다. | [원본](../sources/policy/T15/originals/T15_original.md) · [MD](../sources/policy/T15/extracts/T15.md) | public-under-license |
| T19 | [RFC 7009: OAuth 2.0 Token Revocation](T19.md) | 회수 응답·재사용 차단·자원 서버 효과를 각각 원장에 남긴다. | [원본](../sources/policy/T19/originals/T19_supplement.txt) · [MD](../sources/policy/T19/extracts/T19_supplement.md) | public-under-license |
| T20 | [RFC 7662: OAuth 2.0 Token Introspection](T20.md) | 회수 직후·캐시 만료 직후·IdP 불능의 판정 시나리오를 분리한다. | [원본](../sources/policy/T20/originals/T20_supplement.txt) · [MD](../sources/policy/T20/extracts/T20_supplement.md) | public-under-license |
| T21 | [MCP Security Best Practices](T21.md) | OAuth discovery SSRF와 승인된 내부 MCP 자산 조회를 구분한다. | [원본](../local-sources/policy/T21/originals/T21_mcp_best.html) · [MD](../local-sources/policy/T21/extracts/T21_mcp_best.md) | local-only |
| T22 | [MCP Tasks extension](T22.md) | 종료 케이스에 task id와 신규 호출 차단·실행 중 작업 상태를 연결한다. | [원본](../local-sources/policy/T22/originals/T22_supplement.html) · [MD](../local-sources/policy/T22/extracts/T22_supplement.md) | local-only |

## 2026-10-14 추가 레퍼런스

주제별 조사(조사 에이전트 10개)와 직접 확인으로 139건을 추가했다. 모든 항목의 제목(arXiv는 저자·최초 게시 연도 포함)을 공식 페이지와 대조했다. 요약 검토 수준은 전문 선별 절 6건, 초록 문장 대조 81건, 출처 페이지 대조 49건, 페이지 메타데이터만 3건이다. 원문은 보관하지 않고 서지와 자체 요약만 둔다. [대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json)

### A. MCP 명세·SEP·SDK 보안 권고 (16건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-A01 | [SEP-2468: Recommend Issuer (iss) Parameter in MCP Auth Responses](LIB-A01.md) | 명세·제안 2026 | 게이트웨이 OAuth 콜백 핸들러에서 iss를 추출하고, 인가 요청 전에 기록해 둔 기대 발급자와 정확 문자열로 비교한다. 불일치하면 코드 교환을 중단하고 감사 원장에 기록한다. |
| LIB-A02 | [RFC 8707: Resource Indicators for OAuth 2.0](LIB-A02.md) | RFC 2020 | 게이트웨이가 업스트림 MCP 서버용 토큰을 받을 때 resource에 해당 서버 식별자를 명시하고, 받은 토큰의 audience가 그 서버와 일치하는지 확인한다. 이렇게 하면 토큰 passthrough와 다른 서버 토큰 재사용을 막을 수 있다. |
| LIB-A03 | [RFC 9728: OAuth 2.0 Protected Resource Metadata](LIB-A03.md) | RFC 2025 | 게이트웨이를 보호 리소스로 보고 /.well-known/oauth-protected-resource에 authorization_servers, scopes_supported 등을 게시해 클라이언트가 인가 서버를 자동으로 찾게 한다. |
| LIB-A04 | [SEP-985: Align OAuth 2.0 Protected Resource Metadata with RFC 9728](LIB-A04.md) | 명세·제안 2025 | 게이트웨이 클라이언트 측 401 처리에서 헤더의 resource_metadata를 우선 쓰고, 없으면 well-known 경로로 폴백한다. 두 경로가 모두 실패하면 명확한 오류로 끝낸다. |
| LIB-A05 | [GHSA-6qxp-vccf-f47h (CVE-2026-104850): MCP TypeScript SDK: OAuth client could send credentials to an authorization server chosen by the MCP server](LIB-A05.md) | 보고서·권고 2026 | 게이트웨이가 SDK의 OAuth 클라이언트를 쓰면 sdk 1.31.0 이상 또는 client 2.2.0 이상으로 올린다. 자체 OAuth 구현이라면 refresh token과 client secret을 발급 issuer에 바인딩해 다른 인가 서버로 보내지 않게 한다. |
| LIB-A06 | [SEP-2260: Require Server requests to be associated with a Client request.](LIB-A06.md) | 명세·제안 2026 | 게이트웨이 라우팅에서 서버 발신 요청을 진행 중인 tools/call, resources/read, prompts/get과 연결하고, 연결되지 않은 요청은 차단한 뒤 감사 원장에 기록한다. |
| LIB-A07 | [SEP-1036: URL Mode Elicitation for secure out-of-band interactions](LIB-A07.md) | 명세·제안 2025 | 자격증명·결제·3자 OAuth가 필요한 도구는 폼 모드 대신 URL 모드로 우회시키는 정책 규칙을 둔다. 폼 모드 응답에 URL이 들어오면 차단한다. |
| LIB-A08 | [SEP-1024: MCP Client Security Requirements for Local Server Installation](LIB-A08.md) | 명세·제안 2025 | 게이트웨이의 MCP 서버 등록 흐름에서 stdio 명령과 인자 전체를 잘라내지 않고 보여준 뒤 명시적 승인을 받은 경우에만 실행한다. 승인 기록에는 명령의 해시를 함께 남긴다. |
| LIB-A09 | [GHSA-6xpm-ggf7-wc3p (CVE-2025-6514): mcp-remote exposed to OS command injection via untrusted MCP server connections](LIB-A09.md) | 보고서·권고 2025 | 게이트웨이가 업스트림 MCP 서버의 OAuth 메타데이터를 받을 때, OS 호출 전에 URL 스킴과 형식을 검증하고 셸을 거치는 실행을 금지한다(설계 제안). |
| LIB-A10 | [GHSA-7f8r-222p-6f5g (CVE-2025-49596): MCP Inspector proxy server lacks authentication between the Inspector client and proxy](LIB-A10.md) | 보고서·권고 2025 | 게이트웨이의 로컬 제어 채널이나 관리 포트는 인증 없이 열지 않는 것을 설계 원칙으로 두고, 인증 없는 요청이 거부되는지를 회귀 테스트에 넣는다. |
| LIB-A11 | [SEP-2322: Multi Round-Trip Requests](LIB-A11.md) | 명세·제안 2026 | 게이트웨이가 서버 발신 요청을 중계할 때 공유 저장소 없이 재시도 사이의 상태를 운반하는 구조가 MRTR의 전제이므로, 게이트웨이의 다중 인스턴스 설계를 이 방식 기준으로 검토한다. |
| LIB-A12 | [SEP-991: Enable URL-based Client Registration using OAuth Client ID Metadata Documents](LIB-A12.md) | 명세·제안 2025 | URL형 client_id를 처리할 때, 메타데이터를 가져오기 전에 스킴(https)과 호스트·IP를 검증하고 응답 크기, 타임아웃, 캐시 상한을 둔다. SSRF를 막기 위한 체크리스트로 쓴다. |
| LIB-A13 | [RFC 9207: OAuth 2.0 Authorization Server Issuer Identification](LIB-A13.md) | RFC 2022 | 게이트웨이가 OAuth 클라이언트로 동작할 때 인가 응답의 iss를 검증하고, 불일치하면 코드 교환을 중단한다. SEP-2468 구현의 근거가 된다. |
| LIB-A14 | [GHSA-345p-7cg4-v4c7 (CVE-2026-25536): @modelcontextprotocol/sdk has cross-client data leak via shared server/transport instance reuse](LIB-A14.md) | 보고서·권고 2026 | 게이트웨이는 클라이언트나 세션마다 server와 transport 인스턴스를 분리해 만들고, 인스턴스 공유를 금지하는 것을 아키텍처 원칙으로 둔다. |
| LIB-A15 | [Model Context Protocol (MCP): Landscape, Security Threats, and Future Research Directions](LIB-A15.md) | preprint 2025 | 게이트웨이 위협 모델을 수명주기 단계(생성, 배포, 운영, 유지보수)별로 나누어, 각 단계에서 어떤 정책과 통제를 걸지 매핑하는 틀로 쓴다. |
| LIB-A16 | [GHSA-8r9q-7v3j-jr4g (CVE-2026-0621): Anthropic's MCP TypeScript SDK has a ReDoS vulnerability](LIB-A16.md) | 보고서·권고 2026 | 게이트웨이가 리소스 URI를 정책 평가하기 전에 길이 제한, 패턴 검사, 정규식 실행 타임아웃을 적용한다. |

### B. 도구 오염·악성 서버 공격 (16건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-B01 | [MCP Security Notification: Tool Poisoning Attacks](LIB-B01.md) | 도구 문서 2025 | tools/list 응답의 이름·설명·스키마를 해시로 고정하고, 승인 시점과 달라지면 차단하거나 재승인을 요구하도록 게이트웨이의 계약 변경 탐지에 넣는다. 글이 권장하는 버전·해시 고정과 같은 방향이다. |
| LIB-B02 | [ETDI: Mitigating Tool Squatting and Rug Pull Attacks in Model Context Protocol (MCP) by using OAuth-Enhanced Tool Definitions and Policy-Based Access Control](LIB-B02.md) | preprint 2025 | 게이트웨이가 도구 정의(이름·설명·스키마·버전)를 정규화해 해시나 서명과 함께 기록하고, 값이 바뀌면 계약 변경 탐지와 같은 흐름에서 승인 재요청을 띄운다. |
| LIB-B03 | [Prompt Injection Attack to Tool Selection in LLM Agents](LIB-B03.md) | 논문 2025 | 게이트웨이 도구 카탈로그에 등록되는 설명 문서를 검색과 선택 전에 정적으로 점검해, 지시형 문구나 '항상 이 도구를 쓰라'류 문장을 차단하거나 표시한다. |
| LIB-B04 | [MPMA: Preference Manipulation Attack Against Model Context Protocol](LIB-B04.md) | 논문 2025 | 게이트웨이의 도구 추천과 정렬에 설명 문구 점수를 쓰지 않고, 관리자가 승인한 서버와 도구만 노출하는 허용 목록을 기본값으로 둔다. |
| LIB-B05 | [From Component Manipulation to System Compromise: Understanding and Detecting Malicious MCP Servers](LIB-B05.md) | preprint 2026 | 게이트웨이에서 도구의 선언된 의도(설명과 스키마)와 실제 호출 인자·응답 패턴을 비교하는 이탈 탐지 로직을 설계한다. 실행 전 단계는 셸 명령 같은 위험 인자의 정적 검사로 시작한다. |
| LIB-B06 | [Attractive Metadata Attack: Inducing LLM Agents to Invoke Malicious Tools](LIB-B06.md) | 논문 2025 | 도구 등록 시 이름·설명·스키마를 모두 점검 대상으로 삼고, 외부 서버가 보낸 메타데이터 변경을 계약 변경 탐지 이벤트로 기록한다. |
| LIB-B07 | [MindGuard: Intrinsic Decision Inspection for Securing LLM Agents Against Metadata Poisoning](LIB-B07.md) | preprint 2025 | 게이트웨이는 모델 내부 어텐션에 접근할 수 없어 MindGuard를 그대로 쓸 수 없다. 설명 문구가 호출 인자에 그대로 나타나는지 같은 외부 근사 신호로 줄일 수 있는지 검증 과제로 둔다. |
| LIB-B08 | [Same Name, Different Server: A Security Census of Silent Drift in the Model Context Protocol Ecosystem](LIB-B08.md) | preprint 2026 | 계약 변경 탐지에서 광고 내용이 바뀌었는데 공지가 없는 조합을 높은 위험 신호로 두고, 자동 차단 대신 승인 재요청을 띄운다. |
| LIB-B09 | [MCP-Guard: A Multi-Stage Defense-in-Depth Framework for Securing Model Context Protocol in Agentic AI](LIB-B09.md) | preprint 2025 | 정책 엔진 앞단에 정적 규칙과 분류기 기반 탐지 단계를 두는 구성을 참고한다. 최종 차단 기준은 OPA 명시 정책으로 두고, 탐지 결과는 근거와 함께 감사 원장에 남긴다. |
| LIB-B10 | [Model Context Protocol Threat Modeling and Analyzing Vulnerabilities to Prompt Injection with Tool Poisoning](LIB-B10.md) | preprint 2026 | 클라이언트별 검증 격차를 게이트웨이 보안 요구사항 체크리스트로 쓰고, 클라이언트가 약한 정적 메타데이터 분석을 게이트웨이가 대신 맡는 항목을 정한다. |
| LIB-B11 | [MCP-ITP: An Automated Framework for Implicit Tool Poisoning in MCP](LIB-B11.md) | preprint 2026 | 도구 목록 점검에서 설명 안에 다른 고권한 도구 이름이나 기능을 지시하는 문구를 탐지 규칙으로 추가한다. |
| LIB-B12 | [TRUSTDESC: Preventing Tool Poisoning in LLM Applications via Trusted Description Generation](LIB-B12.md) | preprint 2026 | 게이트웨이가 도구 설명과 실제 호출 결과 샘플을 비교해, 설명에 없는 부작용(외부 전송, 파일 쓰기 등)이 보이면 설명 불일치 플래그를 남긴다. |
| LIB-B13 | [Machine Learning-Based Detection of MCP Attacks](LIB-B13.md) | preprint 2026 | 게이트웨이 도구 등록 파이프라인에 설명 분류기를 경고용 단계로 넣고, 규칙 기반 점검 결과와 나란히 기록해 비교한다. |
| LIB-B14 | [MCPXKIT: The Unified Toolkit for Analyzing Model Context Protocol Security](LIB-B14.md) | preprint 2025 | 31개 공격 구현을 게이트웨이 보안 회귀 테스트 스위트의 공격 목록 출발점으로 쓴다. 코드 라이선스와 사용 조건은 저장소에서 따로 확인해야 한다. |
| LIB-B15 | [Securing GenAI Multi-Agent Systems Against Tool Squatting: A Zero Trust Registry-Based Approach](LIB-B15.md) | preprint 2025 | 게이트웨이에 관리자 승인 기반 도구 레지스트리를 두고, 등록되지 않은 서버의 도구는 호출 경로에 올라오지 못하게 한다. |
| LIB-B16 | [MCP Safety Audit: LLMs with the Model Context Protocol Allow Major Security Exploits](LIB-B16.md) | preprint 2025 | MCPSafetyScanner 방식의 서버 등록 전 점검을 게이트웨이 승인 절차의 한 단계로 넣고, 점검 결과를 승인 근거로 감사 원장에 기록한다. |

### C. 간접 프롬프트 주입 공격·방어 (16건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-C01 | [Indirect Prompt Injections: Are Firewalls All You Need, or Stronger Benchmarks?](LIB-C01.md) | preprint 2025 | 게이트웨이의 tools/call 요청 직전(입력 최소화)과 응답 직후(출력 정화)에 두 단계 필터를 두는 구조를 그대로 매핑할 수 있다. 출력 정화를 OPA 정책 판정 이전 단계에 배치하는 설계 근거가 된다. |
| LIB-C02 | [Defeating Prompt Injections by Design](LIB-C02.md) | preprint 2025 | 게이트웨이에서 출처 태깅을 도입한다. 각 도구 응답에 출처와 신뢰 등급을 붙이고, OPA 정책이 그 태그를 보고 후속 도구 호출을 허용하거나 차단하게 한다. |
| LIB-C03 | [Defending Against Indirect Prompt Injection Attacks With Spotlighting](LIB-C03.md) | preprint 2024 | 게이트웨이가 도구 응답을 모델에 넘기기 전에 출처 표시 변환을 적용하는 전처리 단계로 구현할 수 있다. 모델 재학습 없이 쓸 수 있는 1차 완화책이다. |
| LIB-C04 | [Adaptive Attacks Break Defenses Against Indirect Prompt Injection Attacks on LLM Agents](LIB-C04.md) | preprint 2025 | 게이트웨이 방어(출력 필터, 탐지기, 프롬프트 기반 가드)를 도입하기 전에, 방어를 아는 공격자 시나리오인 적응형 공격을 평가 하네스에 넣는 기준으로 쓴다. |
| LIB-C05 | [The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Against Llm Jailbreaks and Prompt Injections](LIB-C05.md) | preprint 2025 | 게이트웨이 방어의 릴리스 기준으로, 탐지와 필터 계층을 최적화 기반 공격 도구로 재시험하는 단계를 CI 게이트에 넣는다. |
| LIB-C06 | [RTBAS: Defending LLM Agents Against Prompt Injection and Privacy Leakage](LIB-C06.md) | preprint 2025 | 게이트웨이의 승인 흐름을 모든 호출 승인에서 정책 판정 결과에 따른 자동 통과 또는 승인 대기로 나누는 설계 근거로 쓴다. |
| LIB-C07 | [MELON: Provable Defense Against Indirect Prompt Injection Attacks in AI Agents](LIB-C07.md) | preprint 2025 | 게이트웨이에서 사용자 입력 제거 재실행 비교를 고위험 도구 호출에만 적용하는 탐지기로 구현한다. 원래 세션의 도구 호출 시퀀스와 재실행 결과의 유사도를 계산해 플래그를 남기며, 재실행 비용이 크므로 적용 범위를 제한한다. |
| LIB-C08 | [PromptArmor: Simple yet Effective Prompt Injection Defenses](LIB-C08.md) | preprint 2025 | 도구 응답 정화 단계에 가드레일 LLM 호출을 선택 기능으로 넣고, 지연과 비용 때문에 고위험 응답 유형에만 적용하도록 OPA 정책으로 설정한다. |
| LIB-C09 | [DataSentinel: A Game-Theoretic Detection of Prompt Injection Attacks](LIB-C09.md) | preprint 2025 | 도구 응답 탐지기의 후보로 평가한다. 게이트웨이의 응답 필터 자리에 탐지 모델을 연결하고, 차단 임계값을 OPA 정책 파라미터로 노출한다. |
| LIB-C10 | [Bypassing LLM Guardrails: An Empirical Analysis of Evasion Attacks against Prompt Injection and Jailbreak Detection Systems](LIB-C10.md) | preprint 2025 | 탐지 모델 도입 시 문자 변형 같은 회피 공격으로 재시험하는 항목을 평가 체크리스트에 넣고, 탐지기 단독 차단에 의존하지 않도록 정책을 설계한다. |
| LIB-C11 | [Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents](LIB-C11.md) | preprint 2024 | 게이트웨이 회귀 테스트 세트로 ASB의 시나리오 형식(도구 정의, 공격 주입 위치, 성공 판정 기준)을 차용하고, 우리 MCP 도구 목록에 맞춘 시나리오를 만든다. |
| LIB-C12 | [Your Agent is More Brittle Than You Think: Uncovering Indirect Injection Vulnerabilities in Agentic LLMs](LIB-C12.md) | preprint 2026 | 게이트웨이의 도구 호출 직전 훅에서 승인되지 않은 행동을 막는 서킷 브레이커 개념을 참고하되, 은닉 상태 접근은 게이트웨이가 모델 내부에 닿을 수 없으므로 적용할 수 없다. 대신 호출 인자와 출력에 기반한 신호로 대체한다. |
| LIB-C13 | [Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](LIB-C13.md) | preprint 2023 | 게이트웨이 위협 모델의 출발점으로 쓴다. 웹, 파일, 이슈 등 외부 데이터가 도구 응답으로 들어오는 모든 경로를 신뢰되지 않은 입력으로 분류한다. |
| LIB-C14 | [StruQ: Defending Against Prompt Injection with Structured Queries](LIB-C14.md) | preprint 2024 | 게이트웨이가 직접 학습할 수는 없으므로, 백엔드 모델 선정 시 명령과 데이터를 분리하도록 학습됐는지를 모델 점검 항목으로 쓴다. |
| LIB-C15 | [SecAlign: Defending Against Prompt Injection with Preference Optimization](LIB-C15.md) | preprint 2024 | StruQ와 함께 모델 측 방어의 평가 기준으로 쓴다. 다만 게이트웨이에서는 모델 방어를 1차 방어로 간주하지 않고, 모델 방어가 있어도 정책 차단을 완화하지 않는 원칙을 둔다. |
| LIB-C16 | [Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models](LIB-C16.md) | preprint 2023 | BIPIA의 공격 유형 분류(외부 콘텐츠에 지시를 심는 여러 형태)를 게이트웨이 시나리오 목록의 기준으로 쓴다. |

### D. 에이전트 권한·정보흐름·정책 집행 (14건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-D01 | [AgentBound: Securing Execution Boundaries of AI Agents](LIB-D01.md) | 논문 2025 | 게이트웨이 권한 정책을 Android식 자원 단위 권한 선언(파일, 네트워크, 프로세스 등)으로 설계할 때 스키마를 참고한다. 정책을 서버 소스에서 추출하는 방식은 MCP 서버 등록 단계의 계약 검사와 연결할 수 있다. |
| LIB-D02 | [AgentSpec: Customizable Runtime Enforcement for Safe and Reliable LLM Agents](LIB-D02.md) | 논문 2025 | 게이트웨이 정책을 '이벤트, 조건, 집행 동작' 3요소 규칙으로 적는 방식을 OPA(Rego) 정책 설계의 용어 기준으로 삼는다. |
| LIB-D03 | [Formal Policy Enforcement for Agentic Systems](LIB-D03.md) | preprint 2026 | Datalog 기반 출처 정책을 OPA 정책과 비교해, "이 외부 전송이 신뢰 불가 문서와 민감 파일 둘 다에 의존하는가"를 규칙으로 쓸 수 있는지 검토한다(설계 제안). |
| LIB-D04 | [AEGIS: Preventing Cross-Domain Resource Abuse in MCP](LIB-D04.md) | preprint 2026 | 우리 게이트웨이도 OPA 기반이므로, AEGIS의 '도구 온톨로지 캐시, 파라미터 정규화, 임계값 정책' 흐름을 자원 남용 방지 플러그인 설계의 직접 참고로 쓴다. |
| LIB-D05 | [Causality Laundering: Denial-Feedback Leakage in Tool-Calling LLM Agents](LIB-D05.md) | preprint 2026 | 게이트웨이 감사 원장에 거부된 호출도 기록하고 이후 호출의 출처 판단에 반영하면, 거부 응답이 정보 유출 경로가 되는 것을 막을 수 있다. |
| LIB-D06 | [APPA: Recoverable Information-Flow Control for Real-World LLM Agents](LIB-D06.md) | preprint 2026 | 게이트웨이 정책 결과를 허용과 거부 두 가지에서 확장해, 차단 시 승인 요청이나 마스킹 후 재시도 같은 허용 가능한 대안 경로를 제시하는 응답 설계를 검토한다. |
| LIB-D07 | [MiniScope: Authorizing Agents with Least-Privilege Permissions](LIB-D07.md) | preprint 2025 | 커넥터 권한을 도구 단위가 아니라 과제 단위 권한 계층으로 묶는 정책 모델을 OAuth 스코프 매핑 설계에 참고하고, 현재 스코프가 과도하게 넓은지 점검한다. |
| LIB-D08 | [ACE: A Security Architecture for LLM-Integrated App Systems](LIB-D08.md) | 논문 2025 | 게이트웨이에서 사전 계획(허용 도구 시퀀스)과 실행 중 일치 검사 구조를 적용해, 에이전트가 계획에 없는 도구를 호출하면 차단하는 정책 항목으로 쓴다. |
| LIB-D09 | [AgentArmor: Enforcing Program Analysis on Agent Runtime Trace to Defend Against Prompt Injection](LIB-D09.md) | preprint 2025 | 도구 호출 궤적을 데이터 흐름 그래프로 저장하는 감사 원장 스키마를 설계할 때 참고한다. 민감 출처에서 외부 전송으로 가는 경로를 사후에 질의할 수 있다. |
| LIB-D10 | [Towards Verifiably Safe Tool Use for LLM Agents](LIB-D10.md) | 논문 2026 | 게이트웨이 정책을 만들기 전에 위험 분석 단계를 둔다. 도구별로 유출과 오작동이라는 손실 상황을 먼저 적고, 이를 정책 규칙으로 번역하는 절차를 정책 작성 가이드에 넣는다. |
| LIB-D11 | [ShieldAgent: Shielding Agents via Verifiable Safety Policy Reasoning](LIB-D11.md) | preprint 2025 | 게이트웨이 정책 검사 단위를 단일 호출에서 호출 시퀀스로 넓힐 때 설계를 참고한다. 행동 유형별로 규칙을 묶는 방식이 정책 그룹화 기준이 된다. |
| LIB-D12 | [GuardAgent: Safeguard LLM Agents by a Guard Agent via Knowledge-Enabled Reasoning](LIB-D12.md) | 논문 2024 | 자연어 접근 규칙을 검사 코드로 번역하는 파이프라인을 정책 작성 보조(자연어, Rego 초안, 사람 검토)에 참고한다. 생성 코드는 반드시 검토 후 적용한다. |
| LIB-D13 | [IsolateGPT: An Execution Isolation Architecture for LLM-Based Agentic Systems](LIB-D13.md) | 논문 2024 | MCP 서버를 각각 격리된 실행 경계로 두고 게이트웨이를 유일한 교환 지점으로 삼는 구조의 선행 설계로 인용한다. |
| LIB-D14 | [Contextual Agent Security: A Policy for Every Purpose](LIB-D14.md) | preprint 2025 | 과제별로 허용 도구와 인자 범위를 자동 생성해 OPA 입력 데이터로 넣는 과제 단위 정책 번들 구조를 참고한다. 생성된 정책은 사람이 검토한 뒤 활성화한다. |

### E. OAuth·인증·에이전트 신원 (14건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-E01 | [RFC 9068: JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](LIB-E01.md) | RFC 2021 | 게이트웨이 토큰 검증기는 typ=at+jwt 헤더와 필수 클레임 존재 여부를 먼저 확인하고, ID 토큰을 액세스 토큰으로 받지 않도록 거부한다. |
| LIB-E02 | [RFC 9449: OAuth 2.0 Demonstrating Proof of Possession (DPoP)](LIB-E02.md) | RFC 2023 | 하네스에서 빼낸 액세스 토큰을 다른 호스트에서 재사용하는 공격을 막기 위해, 게이트웨이가 모든 호출에서 DPoP 증명의 htm, htu, ath를 검증하고 jti 재사용 캐시로 리플레이를 차단한다. |
| LIB-E03 | [The OAuth 2.1 Authorization Framework](LIB-E03.md) | 명세·제안 2026 | 게이트웨이 설계 문서에서 OAuth 기준 인용을 RFC 6749 대신 이 초안으로 잡되 WIP 표기를 붙이고, RFC 발행 시 갱신한다. |
| LIB-E04 | [Identity Assertion JWT Authorization Grant](LIB-E04.md) | 명세·제안 2026 | 하네스가 사내 SaaS MCP 서버에 접근할 때 사용자별 동의 대신 IdP가 발급한 ID-JAG 존재를 게이트웨이 정책의 필수 조건으로 두면, 관리자가 앱 간 접근을 중앙에서 통제할 수 있다. |
| LIB-E05 | [Transaction Tokens](LIB-E05.md) | 명세·제안 2026 | 게이트웨이가 MCP 도구 호출마다 트랜잭션 토큰을 발급해 하류 MCP 서버에 전달하면, 하네스의 원 액세스 토큰을 노출하지 않고도 원 요청 맥락을 넘길 수 있다. |
| LIB-E06 | [Identity Management for Agentic AI: The new frontier of authorization, authentication, and security for an AI agent world](LIB-E06.md) | preprint 2025 | 논문이 꼽은 공백(에이전트 중심 신원, 위임 권한, 확장 가능한 접근 제어, AI 워크로드 구분)을 게이트웨이 로드맵 항목과 대응시켜 근거 문서로 인용한다. |
| LIB-E07 | [OAuth Client ID Metadata Document](LIB-E07.md) | 명세·제안 2026 | 하네스 클라이언트가 동적 등록 없이 접속하는 경로를 열 경우, 게이트웨이의 메타데이터 가져오기는 내부망 주소와 리다이렉트를 차단하는 SSRF 안전 페처로 구현하고 허용 도메인 목록을 둔다. |
| LIB-E08 | [RFC 7591: Dynamic Client Registration Protocol (OAuth 2.0)](LIB-E08.md) | RFC 2015 | 게이트웨이가 하네스의 동적 등록을 받을 경우 software statement를 요구하고 그 발급자를 신뢰 목록으로 제한해, 아무 클라이언트나 등록되지 않게 한다. |
| LIB-E09 | [RFC 7523: JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](LIB-E09.md) | RFC 2015 | 게이트웨이가 상위 인가 서버에 자기 자신을 증명할 때 클라이언트 비밀 대신 짧은 수명의 서명 JWT 어설션을 쓰고, 이 규격의 검증 규칙을 게이트웨이 어설션 검증기의 체크리스트로 삼는다. |
| LIB-E10 | [OAuth SPIFFE Client Authentication](LIB-E10.md) | 명세·제안 2026 | 하네스 워크로드가 SPIFFE ID를 가지면 게이트웨이 등록 클라이언트를 SPIFFE ID에 매핑해 공유 클라이언트 비밀을 없애고, OPA 정책 입력에 워크로드 신원을 넣는다. |
| LIB-E11 | [OAuth 2.0 Attestation-Based Client Authentication](LIB-E11.md) | 명세·제안 2026 | 고위험 도구 호출에는 하네스 인스턴스 증명을 요구하는 정책을 두고, 증명 유효성과 키 보유 검증 결과를 OPA 입력 신호로 넣는다. |
| LIB-E12 | [AI Identity Management System](LIB-E12.md) | 명세·제안 2026 | 이 개념 스택을 게이트웨이 기능 맵의 체크리스트로 쓴다. 인가는 OPA, 모니터링은 감사 원장, 교정은 승인 워크플로가 맡는지 계층별 대응표를 만든다. |
| LIB-E13 | [AIP: Agent Identity Protocol for Verifiable Delegation Across MCP and A2A](LIB-E13.md) | preprint 2026 | 게이트웨이 단일 홉 검증은 서명 JWT 방식을, 다단계 위임 체인은 추가 전용 체인 구조를 참고해 감사 원장의 해시 체인 설계와 비교 검토한다. |
| LIB-E14 | [Authenticated Delegation and Authorized AI Agents](LIB-E14.md) | preprint 2025 | 사용자, 하네스 클라이언트, 에이전트로 이어지는 위임 메타데이터(위임자, 범위 제한)를 게이트웨이 감사 원장 스키마에 넣어 책임 추적 항목을 설계한다. |

### F. 가드레일·런타임 모니터링 (10건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-F01 | [LlamaFirewall: An open source guardrail system for building secure AI agents](LIB-F01.md) | preprint 2025 | 게이트웨이의 도구 결과 검사 단계에 탈옥·간접 인젝션 탐지기를 붙이고, 탐지 결과를 OPA 입력 신호로 넘긴 뒤 차단 사유를 감사 원장에 함께 기록한다. |
| LIB-F02 | [Enforcing Temporal Constraints for LLM Agents](LIB-F02.md) | preprint 2025 | 게이트웨이 정책 중 순서 규칙(예: 승인 전 쓰기 금지, 인증 후 개인정보 조회)을 세션 상태 기반 검사로 구현할 때 요구사항 목록으로 쓴다. 단일 호출을 판정하는 OPA만으로는 잡기 어려운 규칙이다. |
| LIB-F03 | [NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails](LIB-F03.md) | 논문 2023 | 애플리케이션과 모델 사이에서 프록시처럼 끼어 규칙을 집행하는 구조가 게이트웨이의 위치와 같으므로, 게이트웨이 내부 규칙 실행 계층의 설계 참고로 쓴다. |
| LIB-F04 | [Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations](LIB-F04.md) | preprint 2023 | 게이트웨이의 입력(도구 인자)과 출력(도구 결과)을 각각 다른 지시문으로 분류하는 구조를 그대로 가져온다. 역할에 따라 분류 프롬프트를 나누는 설계다. |
| LIB-F05 | [AgentSight: System-Level Observability for AI Agents Using eBPF](LIB-F05.md) | preprint 2025 | 게이트웨이 감사 원장에 ‘LLM 의도(요청 요약)’와 ‘실제 실행 효과(파일·네트워크 변화)’를 연결하는 설계 목표로 참고한다. 게이트웨이가 보는 것은 MCP 호출이므로 호스트 효과 관측은 보완 계층으로 둔다. |
| LIB-F06 | [TrajAD: Trajectory Anomaly Detection for Trustworthy LLM Agents](LIB-F06.md) | preprint 2026 | 세션 단위 호출 궤적을 저장해 두고, 이상 단계를 지목하면 해당 호출 직전으로 되돌려 재시도하거나 승인 요구로 넘기는 흐름의 설계 근거로 쓴다. |
| LIB-F07 | [Trajectory Guard -- A Lightweight, Sequence-Aware Model for Real-Time Anomaly Detection in Agentic AI](LIB-F07.md) | preprint 2026 | LLM 판정기 호출 없이 밀리초 단위로 돌아가는 1차 필터로 쓴다. 계획과 다른 도구 호출 순서를 상시 감시하고, 의심 세션만 LLM 판정이나 사람 검토로 넘긴다. |
| LIB-F08 | [WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs](LIB-F08.md) | 논문 2024 | 도구 호출 인자의 의도 판정과 도구 결과의 위험 판정을 같은 모델로 처리하되, 결과는 OPA 입력 신호로만 쓰고 최종 결정은 정책 엔진에 둔다. |
| LIB-F09 | [Granite Guardian](LIB-F09.md) | preprint 2024 | RAG 기반 사내 지식 도구를 게이트웨이 뒤에 둘 때, 도구가 가져온 문서에 대한 근거성 판정을 출력 검사 단계에 넣어 환각 의심 응답을 감사 원장에 남긴다. |
| LIB-F10 | [SentinelAgent: Graph-based Anomaly Detection in Multi-Agent Systems](LIB-F10.md) | preprint 2025 | 여러 에이전트나 세션이 MCP 도구를 공유할 때 호출 관계를 그래프로 쌓아, 여러 단계에 걸친 위험 연쇄 경로를 찾는 감사 뷰의 설계 참고로 쓴다. |

### G. MCP 생태계 측정·취약점 (14건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-G01 | [Rethinking MCP Security: A Large-Scale Study of Runtime MCP Servers and Security Scanner Reliability](LIB-G01.md) | preprint 2026 | 게이트웨이가 외부 스캐너 결과를 곧바로 자동 차단 규칙으로 쓰지 않도록 설계하고, 스캐너 판정은 의심 등급으로만 받아 승인 단계의 사람 검토 입력으로 연결한다. |
| LIB-G02 | [Unicode TAG-Block Concealment of Tool-Metadata Payloads in the Model Context Protocol: An Approval-View Fidelity Gap Across Three Independent Server Implementations](LIB-G02.md) | preprint 2026 | 게이트웨이 승인 화면은 도구 설명을 보여주기 전에 유니코드 TAG 블록(U+E0000 to U+E007F)과 제어 문자를 제거하거나 가시화하고, 모델에 전달될 원문을 함께 표시한다. |
| LIB-G03 | [An Empirical Study of Model Context Protocol Applications](LIB-G03.md) | preprint 2026 | 게이트웨이 정책의 승인 강제(require_approval)를 호스트 설정에 맡기지 않고 게이트웨이에서 직접 집행한다. 측정상 차단형 승인을 두는 앱이 약 37%에 그쳐 호스트 측 통제에 기대기 어렵다. |
| LIB-G04 | [A First Look at the Security Issues in the Model Context Protocol Ecosystem](LIB-G04.md) | preprint 2025 | 서버 등록 시점 검사 게이트를 둔다. 레지스트리에서 가져온 서버의 도구 설명(지시문 패턴)과 코드 취약점을 연결 전에 검사하고, 실패하면 등록을 거부한다. |
| LIB-G05 | [Model Context Protocol (MCP) at First Glance: Studying the Security and Maintainability of MCP Servers](LIB-G05.md) | preprint 2025 | 서버 허용 목록 심사 항목을 나눈다. 일반 취약점과 MCP 특유의 도구 포이즈닝 패턴을 따로 체크한다. |
| LIB-G06 | [Exposed by Design: A Dynamic Security Assessment of Internet-Facing MCP Servers at Scale](LIB-G06.md) | preprint 2026 | 게이트웨이를 거치지 않고 외부에 노출된 MCP 엔드포인트를 주기적으로 찾아 게이트웨이 경유 강제 정책과 대조하는 인벤토리 점검을 둔다. |
| LIB-G07 | [A First Measurement Study on Authentication Security in Real-World Remote MCP Servers](LIB-G07.md) | preprint 2026 | 논문의 9종 결함 taxonomy를 게이트웨이의 OAuth 토큰 검증과 클라이언트 등록 회귀 테스트 케이스로 옮긴다. |
| LIB-G08 | [Characterizing Network Centralization and Observability in the Remote MCP Ecosystem](LIB-G08.md) | preprint 2026 | 게이트웨이는 외부 점검이 막힌 서버의 도구 호출과 응답을 볼 수 있는 유일한 관측 지점이므로, 도구 호출·응답 로그를 확보하는 위치로 배치하는 근거로 쓴다. |
| LIB-G09 | [FlowGuard: From Signals to Evidence for MCP Security Detection](LIB-G09.md) | preprint 2026 | 게이트웨이 서버 심사를 두 단계로 나눈다. 정적 의미 경고는 의심으로만 기록하고, 샌드박스에서 실행 증거가 확인된 경우에만 차단한다. |
| LIB-G10 | [VIPER-MCP: Detecting and Exploiting Taint-Style Vulnerabilities in Model Context Protocol Servers](LIB-G10.md) | preprint 2026 | 서버 등록 심사 파이프라인에서 등록, 핸들러, 파라미터, 싱크로 이어지는 호출 경로를 정적 점검 규칙으로 옮겨 외부 서버 코드 심사에 활용한다. |
| LIB-G11 | [Unsafe by Flow: Uncovering Bidirectional Data-Flow Risks in MCP Ecosystem](LIB-G11.md) | preprint 2026 | 게이트웨이 PII 마스킹과 정책 검사의 적용 위치를 입력 방향뿐 아니라 도구 응답이 LLM 컨텍스트로 나가는 출력 방향까지 포함하도록 설계하는 근거로 쓴다. |
| LIB-G12 | [When MCP Servers Attack: Taxonomy, Feasibility, and Mitigation](LIB-G12.md) | preprint 2025 | 12개 공격 범주를 게이트웨이 정책과 탐지 회귀 테스트 케이스로 옮기고, 범주마다 차단 규칙이 있는지 검증하는 매트릭스를 만든다. |
| LIB-G13 | [A Measurement Study of Model Context Protocol Ecosystem](LIB-G13.md) | preprint 2025 | 서버 허용 목록 심사에 유지보수 상태, 포크 여부, 방치 여부를 반영해 레지스트리 항목의 신뢰도를 점수화한다. |
| LIB-G14 | [A Large-Scale Evolvable Dataset for Model Context Protocol Ecosystem and Security Analysis](LIB-G14.md) | 데이터셋 2025 | 게이트웨이의 계약(스키마) 변경 탐지와 회귀 테스트에 실제 도구 정의 샘플을 공급한다. |

### H. PII·비밀정보·개인정보 (8건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-H01 | [Microsoft Presidio (GitHub: microsoft/presidio)](LIB-H01.md) | 도구 문서 2018 | 게이트웨이의 도구 호출 인자와 응답 경로에서 Analyzer로 PII 엔티티를 찾고 Anonymizer로 마스킹하는 1차 필터로 쓴다. 감사 원장에는 원문 대신 엔티티 유형과 위치만 남긴다. |
| LIB-H02 | [GLiNER: Generalist Model for Named Entity Recognition using Bidirectional Transformer](LIB-H02.md) | 논문 2023 | 게이트웨이의 2단계 PII 탐지기로 쓴다. 정규식과 Presidio가 놓치는 이름, 주소, 소속 같은 문맥 의존 엔티티를 레이블 문자열만 바꿔 제로샷으로 추가하고, 엔티티 목록은 정책 파일에서 관리한다. |
| LIB-H03 | [Gitleaks (secret detection tool)](LIB-H03.md) | 도구 문서 2026 | 게이트웨이가 쓰는 파일과 MCP 도구 출력에 gitleaks를 pre-commit 또는 CI 단계로 붙여 비밀정보 유출을 막는 정적 검사 레이어로 쓴다. |
| LIB-H04 | [OWASP Top 10 for LLM Applications 2025: LLM02:2025 Sensitive Information Disclosure](LIB-H04.md) | 표준·규제 2025 | 게이트웨이의 출력 측 PII 검사 요구사항을 정리하는 체크리스트로 쓴다. 입력 정제, 출력 마스킹, 로그 필드 필터링을 각각 정책 항목에 대응시킨다. |
| LIB-H05 | [Secret Breach Detection in Source Code with Large Language Models](LIB-H05.md) | 논문 2025 | 게이트웨이 비밀정보 탐지를 2단계로 구성한다. 1단계 정규식 후보 추출은 게이트웨이 안에서 빠르게 수행하고, 후보만 사내에서 돌리는 소형 LLM에 넘겨 오탐을 줄인다. 원문을 외부로 보내지 않는다는 조건을 함께 건다. |
| LIB-H06 | [Are Large Pre-Trained Language Models Leaking Your Personal Information?](LIB-H06.md) | 논문 2022 | 도구 응답이나 모델 출력에 섞이는 이메일·연락처 유출을 게이트웨이 출력 검사 대상으로 두는 근거로 쓴다. 2022년 PLM 대상 연구라 현재 대형 모델에 그대로 적용하지 않는다. |
| LIB-H07 | [가명정보 처리 가이드라인(2026.3. 개정)](LIB-H07.md) | 보고서·권고 2026 | 한국어 PII 마스킹·가명 처리 설계(DEV-09)에서 가명 처리 기준과 서식을 확인할 1차 출처로 쓴다. 본문을 읽기 전에는 구체 기준을 설계에 인용하지 않는다. |
| LIB-H08 | [개인정보의 안전성 확보조치 기준](LIB-H08.md) | 표준·규제 2026 | 감사 원장 보존·접근 통제·암호화 같은 게이트웨이 기능을 한국 개인정보 안전조치 요구와 대응시킬 때의 1차 출처로 쓴다. 조문을 읽고 확인하기 전에는 구체 조항을 인용하지 않는다. |

### I. 표준·프레임워크·규제 (16건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-I01 | [OWASP Top 10 for Agentic Applications 2026](LIB-I01.md) | 보고서·권고 2025 | 게이트웨이 위협 모델링의 기본 목록으로 쓰고, 항목별로 게이트웨이의 통제 지점(도구 호출 정책, 승인, 감사 원장, 계약 변경 탐지)을 대응시킨다. 항목명은 PDF 확인 후 매핑한다. |
| LIB-I02 | [Technical Blog: Strengthening AI Agent Hijacking Evaluations](LIB-I02.md) | 보고서·권고 2025 | 게이트웨이 회귀 테스트에서 같은 주입 시나리오를 한 번이 아니라 여러 번 반복 실행해 성공률을 기록한다(블로그는 25회 반복 사례를 제시). |
| LIB-I03 | [Security Challenges in AI Agent Deployment: Insights from a Large Scale Public Competition](LIB-I03.md) | preprint 2025 | 정책 위반 유형(무단 데이터 접근, 불법 금융 행위, 규제 위반)을 OPA 정책 카테고리로 나누고, 감사 원장 이벤트를 같은 분류 체계로 기록한다. |
| LIB-I04 | [OWASP Top 10 for LLM Applications 2025](LIB-I04.md) | 보고서·권고 2025 | LLM01(프롬프트 인젝션)과 LLM06(과도한 권한)을 게이트웨이 정책 설계의 기준 항목으로 쓴다. 도구 호출 전 OPA 정책으로 권한 범위를 좁히고, 도구 응답 안의 지시문이 호출 인자를 바꾸지 못하게 한다. |
| LIB-I05 | [[Concept Paper] Accelerating the Adoption of Software and AI Agent Identity and Authorization](LIB-I05.md) | 보고서·권고 2026 | 에이전트마다 고유 신원을 부여하고, 게이트웨이의 OAuth 토큰 검증 단계에서 에이전트 신원과 사용자 위임 주체를 구분해 기록한다. |
| LIB-I06 | [SP 800-53 Control Overlays for Securing AI Systems (COSAiS)](LIB-I06.md) | 표준·규제 2025 | 에이전트 오버레이가 공개되면 게이트웨이의 접근 제어, 승인, 감사 로그 기능을 SP 800-53 통제 ID에 매핑해 인증·감사 대응 자료로 만든다. |
| LIB-I07 | [Regulation (EU) 2024/1689 (AI Act), Article 12: Record-keeping](LIB-I07.md) | 표준·규제 2024 | 감사 원장 스키마를 자동 기록 방식으로 만든다. 호출 시각, 에이전트 신원, 도구, 인자 해시, 정책 판정과 근거를 호출 경로에서 자동으로 남기고, 사후 수기 작성은 두지 않는다. |
| LIB-I08 | [Regulation (EU) 2024/1689 (AI Act), Article 14: Human oversight](LIB-I08.md) | 표준·규제 2024 | 승인 흐름을 감독 요건에 맞춘다. 승인자가 호출 인자와 정책 판정 근거를 보고 거부하거나 중단할 수 있어야 하며, 전체 에이전트 호출을 멈추는 긴급 정지 스위치를 둔다. |
| LIB-I09 | [Regulation (EU) 2024/1689 (AI Act), Article 15: Accuracy, robustness and cybersecurity](LIB-I09.md) | 표준·규제 2024 | 도구 설명과 스키마 변경 탐지를 제5항 대응 통제로 문서화하고, 무단 변경이 감지되면 해당 도구 호출을 막는 정책을 둔다. |
| LIB-I10 | [Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations (NIST AI 100-2e2025)](LIB-I10.md) | 보고서·권고 2025 | 게이트웨이 설계 문서와 위협 모델의 용어를 이 분류 체계에 맞춘다. 예를 들어 회피, 포이즈닝, 프롬프트 인젝션을 같은 이름으로 쓴다. |
| LIB-I11 | [Artificial Intelligence Risk Management Framework (AI RMF 1.0)](LIB-I11.md) | 표준·규제 2023 | GOVERN 기능: 게이트웨이의 정책(OPA) 변경 절차와 승인 권한을 조직의 위험 책임 체계에 연결하는 문서 근거로 쓴다. |
| LIB-I12 | [Principles for Secure-by-Design Agentic Systems](LIB-I12.md) | 보고서·권고 2025 | 두 번째 원칙(영향 범위 최소화)을 에이전트별 도구 허용 목록과 권한 범위 설계 요구로 옮기고, 한 에이전트의 침해가 다른 에이전트 자격증명으로 번지지 않게 격리한다. |
| LIB-I13 | [Securing Agentic AI: A Comprehensive Threat Model and Mitigation Framework for Generative AI Agents](LIB-I13.md) | preprint 2025 | 5개 영역을 게이트웨이 통제 지도의 열로 쓴다. '신뢰 경계 위반'은 도구 출력 검증 지점, '거버넌스 우회'는 정책 우회 탐지 지점에 대응시킨다. |
| LIB-I14 | [Agentic AI Threat Modeling Framework: MAESTRO](LIB-I14.md) | 보고서·권고 2025 | 게이트웨이 위협 모델을 계층별로 나눈다. 에이전트 생태계(MCP 서버, 외부 도구)와 에이전트 프레임워크(클라이언트 측 호출)의 신뢰 경계를 따로 그린다. |
| LIB-I15 | [MITRE ATLAS (Adversarial Threat Landscape for AI Systems)](LIB-I15.md) | 도구 문서 2026 | 감사 원장의 이벤트 분류에 ATLAS 기법 ID를 태그로 붙여, 실제 사고 분석과 레드팀 결과를 같은 축에서 비교한다. ID는 공식 페이지 확인 후 붙인다. |
| LIB-I16 | [인공지능 발전과 신뢰 기반 조성 등에 관한 기본법](LIB-I16.md) | 표준·규제 2025 | 생성형 AI를 쓰는 제품의 고지·표시 의무 같은 조항이 게이트웨이 기록·표시 기능과 관련되는지 법무와 함께 조문을 읽고 판단하는 출발점으로 쓴다(설계 제안). |

### J. 감사·무결성·공급망·관측성 (15건)

| ID | 자료 | 유형 | 개발 연결 |
|---|---|---|---|
| LIB-J01 | [RFC 9943: An Architecture for Trustworthy and Transparent Digital Supply Chains](LIB-J01.md) | RFC 2026 | 게이트웨이가 MCP 서버 매니페스트와 승인된 도구 계약(스키마)에 대한 승인 기록을 COSE 서명 statement로 만들어 투명성 서비스에 등록하고, 받은 receipt를 감사 원장과 함께 보관하면 현재 계약이 승인된 계약과 같은지를 제3자가 검증할 수 있다. |
| LIB-J02 | [RFC 9162: Certificate Transparency Version 2.0](LIB-J02.md) | RFC 2021 | 게이트웨이 감사 원장을 Merkle 트리로 구성해 특정 기록이 원장에 들어 있음을 보이는 포함 증명과, 원장이 과거 기록을 바꾸지 않고 이어졌음을 보이는 일관성 증명을 제공하도록 설계하는 기준으로 쓴다. |
| LIB-J03 | [Notarized Agents: Receiver-Attested Confidential Receipts for AI Agent Actions](LIB-J03.md) | preprint 2026 | 게이트웨이가 바로 호출을 받는 서비스이므로, 도구 호출의 승인과 거부 결과를 게이트웨이 키로 서명한 receipt로 만들고 에이전트 쪽 로그와 대조하는 구조를 설계할 수 있다. |
| LIB-J04 | [LLM Agents Can Easily Tamper With Their Own Traces](LIB-J04.md) | preprint 2026 | 감사 원장은 에이전트 프로세스가 쓰기나 삭제를 할 수 없는 별도 권한과 경로에 두는 것을 요구사항으로 명시하는 근거로 쓴다. |
| LIB-J05 | [Agent Flight Recorder: Tamper-Evident Audit Trails with On-Chain Anchoring for Long-Horizon Tool-Using Agents](LIB-J05.md) | preprint 2026 | 게이트웨이 원장에 에포크 단위 Merkle 루트를 만들어 WORM 저장소나 공개 로그에 주기적으로 게시하는 방식을 설계할 수 있다. 블록체인 앵커는 필수가 아니고 외부 고정 저장소로 대체할 수 있다. |
| LIB-J06 | [aiAuthZ: Off-Host, Identity-Bound Authorization for AI Agents](LIB-J06.md) | preprint 2026 | 우리 게이트웨이와 같은 위치(외부 정책 판단과 도구 호출 전 검사)에 놓인 설계이므로, 인가 결정 기록 스키마와 헤드 해시 고정 방식을 비교 기준으로 쓴다. |
| LIB-J07 | [Behavioral Governance for Autonomous AI Agents: The AgentBound Framework](LIB-J07.md) | preprint 2026 | OPA 정책 결정 로그를 어떤 정책 버전과 어떤 위임 토큰에 따른 결정인지까지 묶은 영수증으로 확장하면, 정책을 바꾼 뒤에도 과거 결정을 재현하고 검증할 수 있다. |
| LIB-J08 | [open-telemetry/semantic-conventions-genai (OpenTelemetry generative AI semantic conventions repository)](LIB-J08.md) | 도구 문서 2026 | 게이트웨이의 도구 호출 스팬과 메트릭 속성 이름을 이 저장소의 MCP 항목에 맞춰 두면 외부 관측 도구와 바로 연결된다. |
| LIB-J09 | [A Taxonomy of Runtime Faults in Model Context Protocol Servers](LIB-J09.md) | preprint 2026 | 게이트웨이의 결함 주입 시험 계획에 이 분류의 범주를 가져와 세션 수명, 전송 계층, 스키마 호환성, 취소 처리 같은 시나리오를 만든다. 범주명은 본문을 확인한 뒤 확정한다. |
| LIB-J10 | [in-toto Attestation Framework Specification](LIB-J10.md) | 명세·제안 2025 | MCP 서버 릴리스마다 빌드 출처와 승인된 스키마 해시를 Predicate로 담은 Statement를 만들고, 게이트웨이가 로드 시점에 이를 정책 입력으로 검증하도록 설계한다. |
| LIB-J11 | [in-toto: Providing farm-to-table guarantees for bits and bytes](LIB-J11.md) | 논문 2019 | MCP 서버 배포 파이프라인을 레이아웃(허용된 단계와 서명 키)과 단계별 링크 증명으로 나눠, 한 단계가 뚫려도 게이트웨이의 최종 검증이 실패하도록 설계한다. |
| LIB-J12 | [SLSA specification (v1.0)](LIB-J12.md) | 명세·제안 2023 | MCP 서버 배포 파이프라인을 SLSA 수준으로 단계화하고, 게이트웨이 정책에 '최소 수준 이상의 provenance가 있어야 설치 허용'을 규칙으로 넣는다. |
| LIB-J13 | [Taxonomy of Attacks on Open-Source Software Supply Chains](LIB-J13.md) | 논문 2022 | MCP 서버 공급망 위협 모델의 공격 벡터 목록을 이 트리에서 가져와, 설치 단계(출처, 의존성 고정, 서명 검증)별 방어 체크리스트를 만든다. |
| LIB-J14 | [SoK: Agentic Skills -- Beyond Tool Use in LLM Agents](LIB-J14.md) | preprint 2026 | MCP 서버와 스킬의 설치 경로에 신뢰 등급별 실행을 두어, 출처가 검증된 도구에는 높은 권한을, 미검증 도구에는 샌드박스 권한만 주는 정책 모델을 설계한다. |
| LIB-J15 | [Building an Open AIBOM Standard in the Wild](LIB-J15.md) | preprint 2025 | MCP 서버 매니페스트에 AIBOM 필드를 얹을 때 SPDX 확장 구조의 데이터셋과 학습 산출물 항목을 참고해 필드 이름을 맞추면 외부 감사 도구와 호환하기 쉽다. |

## 2026-10-17 정책50 구현 공백 보강 (K, 36건)

정책50(POL-01~50) 중 부분 구현으로 남은 공백(목적지 DNS·서버 outbound, 전송 TLS, 에이전트 신원, 데이터 등급, 대량 조회, 중복 실행, 공급자 측 자격 회수, 경보 검증·자동 대응, 복원 후 재활성화)과 정책 번호 체계 표류를 메울 근거 문헌을 공식 원문에서 확인해 추가했다. 공백별 사용처와 등록하지 못한 목록은 [정책50 공백 지도](policy50-gap-references.md), 확인 기록과 해시는 [검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json)에 있다. 자료 수는 기존 167건에 36건이 더해진 203건이며, 자료를 등록했다는 사실이 정책의 구현·검수 완료를 뜻하지 않는다.

| ID | 자료 | 유형 | 정책 | 공백 |
| --- | --- | --- | --- | --- |
| LIB-K01 | [OSCAL v1.2.3 통제 매핑 모델](LIB-K01.md) | 명세 2026 | POL-01~POL-50 | 정책 번호 체계 표류 |
| LIB-K02 | [OPA Policy Testing](LIB-K02.md) | 공식 문서 2026 | POL-22, POL-37, POL-44, POL-01~POL-50 | 정책 변경 시험·동치 분석 · 정책 번호 체계 표류 |
| LIB-K03 | [OPA Decision Logs](LIB-K03.md) | 공식 문서 2026 | POL-38, POL-42, POL-01~POL-50 | 경보 검증·자동 대응 · 정책 번호 체계 표류 |
| LIB-K04 | [OPA Agent Tool Calling](LIB-K04.md) | 공식 문서 2026 | POL-16, POL-28, POL-35, POL-22 | 전송 TLS · 대량 조회·호출량 · 정책 변경 시험·동치 분석 |
| LIB-K05 | [Regal v0.43.0](LIB-K05.md) | 도구·OSS 2026 | POL-01~POL-50, POL-37 | 정책 번호 체계 표류 · 정책 변경 시험·동치 분석 |
| LIB-K06 | [Cedar (OOPSLA 2024)](LIB-K06.md) | 논문 2024 | POL-37, POL-22, POL-23 | 정책 변경 시험·동치 분석 |
| LIB-K07 | [Zelkova (FMCAD 2018)](LIB-K07.md) | 논문 2018 | POL-37, POL-25 | 정책 변경 시험·동치 분석 · 데이터 등급 |
| LIB-K08 | [NIST SP 800-162 (ABAC)](LIB-K08.md) | 표준·RFC·권고 2014 | POL-25, POL-19, POL-20, POL-22 | 데이터 등급 · 에이전트 신원·위임 |
| LIB-K09 | [OWASP SSRF Prevention Cheat Sheet](LIB-K09.md) | 지침 2026 | POL-10, POL-26, POL-40, POL-24 | 목적지 DNS·서버 outbound |
| LIB-K10 | [Stripe Smokescreen v0.1.0](LIB-K10.md) | 도구·OSS 2026 | POL-10, POL-26, POL-40 | 목적지 DNS·서버 outbound |
| LIB-K11 | [RFC 9325 / BCP 195 (TLS 권고)](LIB-K11.md) | 표준·RFC·권고 2022 | POL-16 | 전송 TLS |
| LIB-K12 | [NIST SP 800-52 Rev. 2 (TLS)](LIB-K12.md) | 표준·RFC·권고 2019 | POL-16 | 전송 TLS |
| LIB-K13 | [RFC 9334 (RATS 아키텍처)](LIB-K13.md) | 표준·RFC·권고 2023 | POL-19, POL-20 | 에이전트 신원·위임 |
| LIB-K14 | [SPIFFE ID·X509-SVID·JWT-SVID](LIB-K14.md) | 명세 2026 | POL-19, POL-20, POL-21, POL-15 | 에이전트 신원·위임 |
| LIB-K15 | [SPIRE v1.15.4](LIB-K15.md) | 도구·OSS 2026 | POL-19, POL-20 | 에이전트 신원·위임 |
| LIB-K16 | [Sigstore (CCS 2022)](LIB-K16.md) | 논문 2022 | POL-01, POL-39 | 공급망 출처·취약점 대응 |
| LIB-K17 | [OpenSSF Scorecard v5.6.0 점검 항목](LIB-K17.md) | 도구·OSS 2026 | POL-01, POL-03, POL-39 | 공급망 출처·취약점 대응 |
| LIB-K18 | [OSV 스키마 1.9.2](LIB-K18.md) | 명세 2026 | POL-39, POL-03 | 공급망 출처·취약점 대응 |
| LIB-K19 | [CISA KEV 카탈로그](LIB-K19.md) | 데이터 서비스 2026 | POL-39 | 공급망 출처·취약점 대응 |
| LIB-K20 | [CISA BOD 26-04 (BOD 22-01 대체)](LIB-K20.md) | 정책 문서 2026 | POL-39, POL-43 | 공급망 출처·취약점 대응 · 경보 검증·자동 대응 |
| LIB-K21 | [FIRST EPSS 모델 v5](LIB-K21.md) | 데이터 서비스 2026 | POL-39 | 공급망 출처·취약점 대응 |
| LIB-K22 | [CSAF 2.0 (OASIS Standard)](LIB-K22.md) | 표준·RFC·권고 2022 | POL-03, POL-39 | 공급망 출처·취약점 대응 |
| LIB-K23 | [OpenVEX v0.2.0](LIB-K23.md) | 명세 2026 | POL-39 | 공급망 출처·취약점 대응 |
| LIB-K24 | [CISA VEX 최소 요건](LIB-K24.md) | 지침 2023 | POL-39 | 공급망 출처·취약점 대응 |
| LIB-K25 | [OWASP Secrets Management Cheat Sheet](LIB-K25.md) | 지침 2026 | POL-41, POL-45, POL-47, POL-49, POL-14 | 공급자 측 자격 회수 |
| LIB-K26 | [Idempotency-Key 초안 -07 (만료)](LIB-K26.md) | 명세 2025 | POL-36 | 중복 실행 |
| LIB-K27 | [OWASP API Security Top 10 2023](LIB-K27.md) | 지침 2023 | POL-35, POL-28, POL-10, POL-25 | 대량 조회·호출량 · 목적지 DNS·서버 outbound · 데이터 등급 |
| LIB-K28 | [OpenID Shared Signals Framework 1.0](LIB-K28.md) | 명세 2025 | POL-41, POL-45, POL-44 | 공급자 측 자격 회수 |
| LIB-K29 | [OpenID CAEP 1.0](LIB-K29.md) | 명세 2025 | POL-44, POL-45, POL-22, POL-20 | 공급자 측 자격 회수 · 에이전트 신원·위임 |
| LIB-K30 | [RFC 8417 (SET)](LIB-K30.md) | 표준·RFC·권고 2018 | POL-44, POL-38 | 공급자 측 자격 회수 · 경보 검증·자동 대응 |
| LIB-K31 | [NIST SP 800-61 Rev. 3](LIB-K31.md) | 표준·RFC·권고 2025 | POL-42, POL-43, POL-50 | 경보 검증·자동 대응 · 복원 후 재활성화 |
| LIB-K32 | [NIST SP 800-34 Rev. 1](LIB-K32.md) | 표준·RFC·권고 2010 | POL-50, POL-46 | 복원 후 재활성화 |
| LIB-K33 | [ISO/IEC TS 27560:2023 (동의 기록)](LIB-K33.md) | 표준·RFC·권고 2023 | POL-08, POL-26 | 법령·표준 근거 확인 |
| LIB-K34 | [ISO/IEC 42001:2023](LIB-K34.md) | 표준·RFC·권고 2023 | POL-02, POL-03, POL-05, POL-07, POL-32, POL-37, POL-38, POL-39 | 법령·표준 근거 확인 |
| LIB-K35 | [ISMS-P 인증기준 안내서 2023.11.](LIB-K35.md) | 지침 2023 | POL-38, POL-43, POL-44, POL-45, POL-50, POL-46, POL-16, POL-10 | 법령·표준 근거 확인 · 경보 검증·자동 대응 · 공급자 측 자격 회수 · 복원 후 재활성화 |
| LIB-K36 | [개인정보 보호법 (시행 2026.9.11.)](LIB-K36.md) | 법령 2026 | POL-02, POL-31, POL-26, POL-48, POL-49, POL-09, POL-38, POL-43, POL-07, POL-30 | 법령·표준 근거 확인 · 경보 검증·자동 대응 |


## 업데이트

선별·개발 요약은 `sources/selection.json`, 공식 추가 입수 이력은 `sources/live/`에 보존한다.
기존 위키를 다시 가져오려면 `python tools/import_policy_sources.py --source-root <기존-위키-경로>`를 실행한다.
동일 경로의 원본 해시가 달라지면 덮어쓰지 않고 중단하므로 새 판본은 새 경로로 기록해야 한다.
