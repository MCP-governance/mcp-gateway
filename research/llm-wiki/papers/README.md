# 논문·프로토콜·보안 문서

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

## 업데이트

선별·개발 요약은 `sources/selection.json`, 공식 추가 입수 이력은 `sources/live/`에 보존한다.
기존 위키를 다시 가져오려면 `python tools/import_policy_sources.py --source-root <기존-위키-경로>`를 실행한다.
동일 경로의 원본 해시가 달라지면 덮어쓰지 않고 중단하므로 새 판본은 새 경로로 기록해야 한다.
