# 클라우드 감사·AI 통제 제품 요약 (AWS·Azure·Google·Cloudflare)

확인일: 2026-10-23 · 확인 수준: 공급자 공식 문서 선택 열람 · 실제 서비스 시험·계약·가격 미확인. 문서 날짜와 확보 시각·SHA-256은 [출처 manifest](../analysis/cloud-control-benchmark-1023/cloud-control-benchmark-1023.sources.json)에 있다. 기능별 비교와 MINT 대응은 [벤치마크](../analysis/cloud-control-benchmark-1023/README.md)를 읽는다. 관리형 서비스는 판본 번호가 없어 문서 날짜를 기준으로 하며 공개 문서 전체 복제본은 보관하지 않는다.

## AWS — CloudTrail과 Bedrock·AgentCore

- **CloudTrail**: 이벤트 이력은 관리 이벤트 90일 보기, trail은 S3로 전달, CloudTrail Lake는 SQL 조회형 불변 저장소다. Lake는 2026-05-31부터 신규 고객을 받지 않는다고 문서에 표시된다(이유는 문서에 없다). 관리 이벤트(제어 평면)는 기본 기록, 데이터 이벤트는 기본 꺼짐이며 고급 이벤트 선택기로 대상을 고른다. 데이터 이벤트 리소스 유형에 Bedrock 가드레일·모델, AgentCore Gateway, MCP 도구 항목이 있다. Insights는 호출률·오류율 기준선 이탈을 별도 이벤트로 낸다. 조직 trail과 위임 관리자(최대 3개)로 조직 단위 기록을 중앙화한다.
- **로그 무결성 검증**: 로그 파일 해시와 매시간 digest 파일을 만들어 SHA256withRSA로 서명하고, 각 digest는 이전 digest의 서명을 포함한다. digest는 로그와 다른 위치에 보관한다.
- **Bedrock Guardrails**: 콘텐츠·주제·단어·민감정보·근거성·자동 추론 검사. 작업 초안을 버전으로 고정해 ID와 판본으로 호출한다. 모델 호출 없이 쓰는 `ApplyGuardrail` API가 있다. 조직 정책으로 가드레일을 강제하며 `DescribeEffectivePolicy`로 계정별 실제 적용을 확인한다. 자동 추론 정책은 강제 대상에서 지원되지 않는다고 문서에 표시된다.
- **모델 호출 로깅**: 기본 꺼짐. 켜면 입력·출력 전문을 같은 계정·리전의 S3 또는 CloudWatch Logs에 남긴다.
- **AgentCore**: Gateway는 MCP·A2A·모델 호출을 한 진입점으로 모으고 인바운드 OAuth와 아웃바운드 자격 주입을 맡는다. Identity는 워크로드 신원·자격 공급자·동의 포털. Policy는 Cedar(및 세션 인지용 Dogwood)로 도구 호출을 게이트웨이에서 평가하며 정책 단위 `ACTIVE`/`LOG_ONLY`와 엔진 단위 `ENFORCE`/`LOG_ONLY`를 제공한다. 모드 변경 권한이 `UpdateGateway` 하나라는 점을 문서가 주의로 적는다.
- **미확인**: IAM 정책 시뮬레이터, Cedar 진단 형식, 가격, 각 기능의 실제 시험.

## Azure — Monitor·Entra·Foundry·API Management

- **Monitor 활동 로그**: 제어 평면 작업을 기본 수집하며 변경·삭제할 수 없고 90일 보존한다. 읽기 작업은 대체로 기록하지 않는다. 데이터 평면은 리소스 로그이며 진단 설정이 필요하다. 진단 설정으로 최대 12년까지 보관할 수 있다.
- **Entra 감사 로그**: 사용자·그룹·앱·라이선스 변경을 기록한다. 보존 기간은 읽은 범위에서 미확인이다.
- **Prompt Shields(Content Safety)**: 사용자 프롬프트 공격과 문서 공격을 탐지한다. Foundry에서는 프롬프트 공격 탐지가 기본 켜짐, 문서 공격은 기본 꺼짐이며, 에이전트의 도구 응답 스캔은 미리보기다. 한 요청의 결과는 `detected`·`filtered` 값으로 반환한다.
- **API Management의 MCP 지원**: REST API를 MCP 서버로 노출하거나 기존 MCP 서버를 프록시한다. 호출 제한·JWT 검증·IP 필터·캐시를 정책으로 적용하며, 현재 정책은 서버가 노출한 모든 도구에 일괄 적용되는 것으로 읽힌다. Azure Monitor로 관측한다.
- **AI 게이트웨이 기능**: 토큰 한도·시맨틱 캐시·로드 밸런서·서킷 브레이커·콘텐츠 안전 검사·프롬프트와 완성문 로깅. Foundry의 AI 게이트웨이(미리보기)는 Azure·타 클라우드·온프레미스에서 도는 에이전트와 MCP 도구를 Foundry 제어 평면에 등록하는 구조다. API Center에 MCP 서버를 등록·검색한다.
- **미확인**: 정책 단위 도구 차등, 프롬프트 로깅의 개인정보 처리, 가격, 실제 시험.

## Google Cloud — Cloud Audit Logs·Model Armor·Agent Platform

- **Cloud Audit Logs**: Admin Activity와 System Event는 항상 기록되며 끌 수 없다. Policy Denied는 기본 기록, 저장은 제외 필터로 줄일 수 있다. Data Access는 BigQuery를 제외하면 기본 꺼짐이다. 기록은 불변이라고 표시된다. Google Cloud MCP 서버는 `mcp.googleapis.com`을 통해 Data Access 로그를 쓰며 감사 설정으로 켠다. 로그 라우터는 프로젝트·폴더·조직 단위 싱크로 대상에 내보낸다. 폴더·조직 버킷은 보존 연장이 안 된다고 표시된다.
- **Model Armor**: 프롬프트·응답을 검사하는 서비스. 인젝션·탈옥, 유해 콘텐츠, Sensitive Data Protection 연동 PII, 악성 URL을 다룬다. 템플릿을 입력용·출력용으로 나누고, 집행 유형은 `Inspect only`(Cloud Logging에 기록만)와 `Inspect and block`이다. 프로젝트 템플릿의 최소 요건을 정하는 floor 설정이 있다. 차단은 연동 지점(Policy Enforcement Point)이 수행한다고 문서에 표시된다.
- **Gemini Enterprise Agent Platform(구 Agent Engine 문서)**: Agent Gateway로 런타임 트래픽 통제, IAM 에이전트 신원, VPC Service Controls 등이 목차에 있다. 이번에는 목차 수준만 읽었다.
- **미확인**: 로그 보존 수치, Agent Gateway의 정책 기능, 가격, 실제 시험.

## Cloudflare — AI Gateway·MCP 서버 포털

- **AI Gateway**: 분석·로깅·캐시·속도 제한·재시도·폴백. 로그는 기본 켜짐이며 요청 헤더로 로그 수집과 본문 저장을 각각 끌 수 있다. 2026-09-24 이후 처음 게이트웨이를 만든 고객은 Workers Logs 가격·보존을 따른다고 문서에 표시된다. Guardrails는 프롬프트·응답을 검사해 표시(flag) 또는 차단하며 평가 호출도 로그에 남는다.
- **MCP 서버 포털**: 여러 MCP 서버를 한 엔드포인트로 모으고 Cloudflare Access로 인증한다. 포털별로 도구·프롬프트를 고르고 별칭을 붙이며, 컨텍스트 최적화와 Code Mode(도구를 검색·코드 실행 두 개로 접음)를 제공한다. 요청은 Access가 기록하고 Gateway를 거치면 HTTP 로깅과 DLP 검사를 추가할 수 있다. 스테이트리스 MCP 2026-07-28 규격과 이전 규격을 함께 받는다고 문서에 표시된다.
- **미확인**: 로그 무결성 보장, 포털 단위 도구 호출 정책의 세부, 가격, 실제 시험.

## 관련 상용: Kong AI Gateway

[기존 요약](kong-ai-gateway.md)이 정본이다. 10-23 재확인: AI MCP Proxy 문서는 소비자·소비자 그룹 ACL을 기본·도구별로 정의하는 기능을 v3.13 이후로 표시하고 Enterprise 제품에 한정한다. Konnect의 MCP 레지스트리는 기술 미리보기로 표시된다. 로그는 별도 로깅·트레이싱 플러그인으로 더하는 구조로 읽힌다. 감사 무결성은 확인하지 못했다.

## 온프레미스 차용 후보로 확인한 OSS

| OSS | 확인 사실(2026-10-23, GitHub API) | 판단 |
| --- | --- | --- |
| Sigstore Rekor | Apache-2.0, 최신 릴리스 v1.5.5 | 외부 투명성 로그 선택 항목. 운영 부담 큼 |
| Trillian | Apache-2.0, 최신 릴리스 v1.8.0 | 위와 같음 |
| Cedar | Apache-2.0, 최신 릴리스 CLI v4.14.0 | AgentCore Policy의 정책 언어. MINT는 OPA를 쓰므로 언어 교체 불필요 |
| OPA | Apache-2.0, 최신 릴리스 v1.21.3 | MINT 사용 중(수용 시험은 1.20.2 이미지). 판본 차이 확인 필요 |
| OpenSearch Anomaly Detection | Apache-2.0, 최신 릴리스 3.6.0.0 | MINT 배포 3.8.0과 호환 미확인 |
| immudb | 라이선스 `NOASSERTION`, LICENSE는 Business Source License 계열 | 도입 전 라이선스 확인 전까지 제외 |
