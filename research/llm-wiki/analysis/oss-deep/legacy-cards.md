# 누락된 5개 카드 — OSS-A01 분석 정리

확인일: 2026-10-15 · 대상: solutions 카탈로그에 없는 5개 clone 요약 · 범위: 로컬 clone 메타데이터와 README 정독, 기존 분석 대조

> **메인 검토 확인(2026-10-15).** remote-mcp-apim의 APIM 정책 XML 10개를 AI-Gateway 클론과 바이트 대조했다. `mcp-api.policy.xml`·`authorize`·`consent`·`oauthmetadata-get`·`oauthmetadata-options`·`register-options`·`register`·`token` 9개는 AI-Gateway의 `labs/mcp-client-authorization/src/apim-oauth/`(mcp-api는 `labs/mcp-a2a-agents/src/mcp_sk_servers/apim-mcp/`)와 **완전히 같다**. `oauth-callback.policy.xml`은 127행의 변수 이름 하나(`EntraIDFicClientId`↔`EntraIDClientId`)만 다르다. 따라서 remote-mcp-apim은 AI-Gateway 랩 정책의 재배포본이며 **독립 게이트웨이 구현 1종으로 세지 않는다**. 두 저장소 모두 MIT(`LICENSE`/`LICENSE.md` 첫 줄 확인). 아래 카드들은 README·기존 문서 중심의 L1~L2 정리이며 새 경로 추적이 아니다.

---

### Azure AI-Gateway

- 저장소: `Azure-Samples/AI-Gateway`, commit `1679e3137d2fe7592d2a668d77ff71550d35b69e`, 라이선스: MIT (`LICENSE.md`)
- **역할**: Azure API Management 기반의 엔터프라이즈급 AI 게이트웨이 랩 모음. OAuth 2.0, 콘텐츠 안전 필터, 로드 밸런싱, 토큰 속도 제한, 라우팅 정책을 APIM 정책 XML로 구현(README.md:29-35)
- **기존 분석**: docs/ai/BENCHMARK_MICROSOFT.md:33-58에서 APIM 정책 XML, DCR+PKCE, RFC 9728 PRM, llm-content-safety, validate-azure-ad-token을 다룬 관찰. **이번 재확인**: README는 30개 이상 랩을 제시하며 MCP 프로토콜 지원을 명시하지만(README.md:35), 기존 분석은 MCP 관련 정책 코드 위치를 명시하지 않았다. clone 내 MCP 정책 범위는 미독
- **분석 깊이**: L2 부분 · 이유: APIM 정책 XML과 인증 흐름 선별, 정책 오류/철회 경로는 미확인
- **MINT와의 관계**: 참고만 · OAuth DCR/PKCE 구현은 우리 bob-sso 시나리오(제3자 클라이언트 자체 등록)와 다른 계층(문서:35참고). APIM 정책 레이아웃은 정책 강제 방식 비교에 유용하지만 직접 채택 대상 아님
- **정정**: 기존 문서(BENCHMARK_MICROSOFT.md:33)는 "복제된 저장소"로 표시했으나, AI-Gateway가 공식 Azure 샘플(`Azure-Samples` 조직)이고 remote-mcp-apim이 community 샘플인지 확인 필요
- **미독 범위**: 30개 랩 전체, MCP 관련 정책 코드, 실제 배포 policy 파일들, 정책 실패 시 응답 경로

---

### Azure remote-mcp-apim

- 저장소: `Azure-Samples/remote-mcp-apim-functions-python`, commit `130c553e12bca6d5287e3cd7df5585846b1da55a`, 라이선스: MIT (`LICENSE.md`)
- **역할**: Azure API Management를 MCP 서버의 AI 게이트웨이로 사용하는 예제. RFC 7591 동적 클라이언트 등록, MCP Authorization specification을 APIM 정책으로 구현(README.md:23-24). Azure Functions 위에 MCP 서버 배포
- **기존 분석**: docs/ai/BENCHMARK_MICROSOFT.md:79-95에서 OAuth 프록시 XML 분석, register.policy.xml의 CosmosDB 저장, token.policy.xml의 PKCE 계산(S256/plain), redirect_uris 검증, 캐시 조회 후 Entra 토큰 전달 확인. **이번 재확인**: clone 내 README는 "AI Gateway"를 명시적으로 참고하며 아래 제목 "Secure Remote MCP Servers"를 붙임(README.md:17). 정책 파일 구조는 로컬에서 확인 가능(infra/app/apim-oauth/ 폴더)하지만 정책 본문 비교는 미수행
- **분석 깊이**: L2 · 이유: 정책 XML 메타데이터와 README, Azure Functions 런타임 경계는 확인, 실제 배포·실행·장애 경로 미확인
- **MINT와의 관계**: 참고만 · 우리 Gateway와 달리 APIM이 정책 판정 지점이므로 직접 이식 불가능. 토큰 회수/철회 경로는 APIM 특화 메커니즘(cache eviction)
- **정정**: docs/ai/BENCHMARK_MICROSOFT.md:38에서 "remote-mcp-apim이 AI-Gateway를 복제"라는 표현. 확인: 두 저장소 모두 Azure-Samples 조직에 속하며 공식 샘플 계열로 보임. 정책 파일 복제 여부는 로컬 정책 XML 내용 diff를 수행하지 않아 미확인(문서에서 "완전히 동일"이라 표현했으나 근거가 source code grep만)
- **미독 범위**: 정책 파일 전문 diff(문서 claim "완전히 동일" 검증), Azure Functions 수명 관리, 실제 배포 bicep 템플릿 상세, 콘솔 로그 구조

---

### Microsoft agent-framework

- 저장소: `microsoft/agent-framework`, commit `4b1c231b4fa42daa1a71f7e89bf3b9dc31fa2398`, 라이선스: MIT (`LICENSE`)
- **역할**: Python/C#/.NET용 다중 언어 에이전트 프레임워크. 오케스트레이션, 미들웨어, 다중 LLM 제공자 지원. MCP 도구 로딩 시 도구별 `approval_mode` 속성(always_require/never_require/목록) 지원(README.md:40-50)
- **기존 분석**: docs/ai/BENCHMARK_MICROSOFT.md:59-62에서 MCP 도구 `approval_mode`의 기본값 "never_require"(옵트인)와 에이전트 SDK 일시정지/재개 성질 확인. 정책 엔진 없음, 신원 무관 플래그라고 판정. **이번 재확인**: README에서 "에이전트 프레임워크"로 명시되며 SDK 수준에서의 기능. PAC-13(도구 승인) 같은 게이트웨이 정책과는 다른 계층(클라이언트 측 라이브러리)
- **분석 깊이**: L2 좁은 범위 · 이유: approval_mode 속성과 기본값만 확인, 실제 호출 경로·재개·취소·상태 저장소 미확인, Python 구현 전체 경로는 미독
- **MINT와의 관계**: 참고만, DEV-43 입력 · 우리 Gateway와 다른 계층(하네스 vs 원격)이지만 규칙 분류/선택 로직의 옵션 참고 값. 직접 채택은 아님. 기존 문서의 "우리 PAC-13과 다른 계층" 판정은 유지
- **정정**: 없음
- **미독 범위**: Python packages 전체 MCP 통합(python/packages/core/agent_framework/_mcp.py), 다중 도구 관리 state machine, 오케스트레이션 그래프와 tool calling 결합 방식, .NET 동등 구현

---

### Microsoft PyRIT

- 저장소: `microsoft/PyRIT`, commit `ea9d0b43d71c971f82567de499a8e2f82f1f0e15`, 라이선스: MIT (NOTICE.txt, THIRD_PARTY_NOTICES.txt 포함)
- **역할**: AI 시스템 위험 식별 레드팀 프레임워크. MCPStreamableHTTPServerConfig로 실제 MCP 서버를 PyRIT 타깃으로 지정 가능. 자동 공격 루프, latent-injection 시드 지원(README.md:1-10 및 CITATION.cff 참조)
- **기존 분석**: docs/ai/BENCHMARK_MICROSOFT.md:36에서 MCPStreamableHTTPServerConfig, 실제 MCP 서버를 타깃으로 삼은 자동 레드팀, garak 계열 시드 관찰. **이번 재확인**: README 메인 문서는 "framework"와 "security professionals"를 강조하며 웹사이트·Discord·MSRC 정책 참고. 실제 MCP 세션·target 생성 경로는 소스 정독 미수행
- **분석 깊이**: L2 좁은 범위 · 이유: MCPStreamableHTTPServerConfig 메타데이터 수준, actual MCP call 경로·scorer·converter·injection 루프·오탐 조건 미확인
- **MINT와의 관계**: 참고만, DEV-46 레드팀 코퍼스 · 우리 Gateway `/mcp/<server>/`를 PyRIT 타깃으로 삼을 수 있다는 구조적 가능성 확인. 실제 시드·시나리오·재현은 DEV-46 별도 조사 대상
- **정정**: 없음
- **미독 범위**: scorer·converter 실제 구현, garak 시드 출처와 매핑, 공격 루프의 state 관리, 결과 집계·필터링, 정상 업무와 오탐 구분 조건

---

### Microsoft agent-governance-toolkit (AGT)

- 저장소: `microsoft/agent-governance-toolkit`, commit `5233029078c6d90ed2d9e4bc6875e87e504291dd`, 라이선스: MIT (`LICENSE`, `NOTICE`)
- **역할**: AI 에이전트 거버넌스를 위한 정책 강제, 신원 관리, 샌드박싱, SRE 기능 제공. Python/TypeScript/.NET/Rust/Go 다중 SDK, 훅 플러그인(하네스 내 PreToolUse 등), 스캐너·리댁터(secret, poisoning, command 등), Merkle 감사 체인(README.md:1-50, BENCHMARK_AGT_2026-10-05.md:14-57)
- **기존 분석**: docs/ai/BENCHMARK_AGT_2026-10-05.md에서 AGT 자체 평가와 우리 MCP01~10 대응 비교. 훅 플러그인은 보조 신호, SDK 스캐너·규칙이 수확 대상. 우리 규칙과 비교 결과(문서:37-49)에서 숨은 주석·필수 인자·인코딩 3개 규칙 채택, Redactor·DID·메시지 서명은 미채택 확인. **이번 재확인**: 로컬 clone 메타데이터와 README를 읽었으나 규칙 및 구현 재검증은 BENCHMARK_AGT 문서가 이미 수행했으므로 중복 회피
- **분석 깊이**: L2 선택적 · 이유: 훅 플러그인의 위치·구조와 OWASP Agentic Top 10 매핑 선별 확인(문서:32), SDK별 스캐너 규칙 일부 대조(문서:39-49), 전체 정책 루틴·복구·상태 저장소 미확인
- **MINT와의 관계**: 부분 채택, DEV-41 · 우리와 다른 계층(훅 vs Gateway), 직원 권한이 같으면 우회 가능(문서:14). 채택한 규칙(숨은 주석·인코딩·필수 인자)은 `poisoning.py`에 구현되어 있고(DECISIONS.md D-73 참고), 서명/Merkle은 중복(우리 서명 토큰·해시 체인)
- **정정**: 문서의 "서명/HMAC/해시"를 "계약 해시" vs "메시지 서명"으로 재분류. AGT의 "HMAC 지문"은 우리 계약 해시 효과이지 메시지 서명 아님(BENCHMARK_AGT:문서의 "완전"이라 표현했으나 실제는 라이브러리 함수 수준, 우회 불가 강제 경로 아님)
- **미독 범위**: 전체 정책 엔진 호출자·실패 처리, 훅 실행 차단·복구, state를 공유하는 다중 에이전트 경우, 모든 SDK 언어별 구현 차이, 실제 하네스(Claude Code·Codex)에 플러그인 설치 효과

---

## 요약 및 누락 카드와 기존 문서 연결

| 저장소 | 카드 위치 | 기존 분석 | 직접 재확인 | 분석 깊이 | MINT 관계 |
| --- | --- | --- | --- | --- | --- |
| AI-Gateway | 이 파일 | BENCHMARK_MICROSOFT.md:33-58 | README, MIT 라이선스, MCP 범위 미명시 | L2 부분 | 참고만 |
| remote-mcp-apim | 이 파일 | BENCHMARK_MICROSOFT.md:79-95 | README, MIT 라이선스, AI-Gateway 공식 연결 | L2 | 참고만 |
| agent-framework | 이 파일 | BENCHMARK_MICROSOFT.md:59-62 | README, MIT 라이선스, 에이전트 SDK 역할 | L2 좁음 | 참고만 |
| PyRIT | 이 파일 | BENCHMARK_MICROSOFT.md:36 | README, MIT 라이선스, 레드팀 프레임워크 역할 | L2 좁음 | 참고만, DEV-46 |
| AGT | 이 파일 | BENCHMARK_AGT_2026-10-05.md 전체 | 로컬 clone 메타데이터만(규칙은 기존 대조 완료) | L2 선택 | 부분 채택, DEV-41 |

## 다음 단계

1. **AI-Gateway MCP 정책 추가 조사** (DEV-47 순서 3): 30개 이상 랩 중 MCP 관련 정책 코드 위치 확인
2. **remote-mcp-apim 정책 파일 diff** (DEV-47 순서 3): "AI-Gateway 복제" claim 검증용 정책 XML 전문 대조
3. **PyRIT 시드 및 MCP 경로** (DEV-46): 실제 시드 구성, garak 출처, MCP 타깃 구현 추적
4. **agent-governance-toolkit 하네스 호출자** (DEV-41): 실제 하네스에 훅 설치 시 강제 경로 확인

---

**기록**: OSS-A01 판정 카드 5개 완성 · 2026-10-15 · 기존 분석 정리 및 정정 대상 표시 · 실행 시험 미수행
