# MCP 게이트웨이·AI 에이전트 보안 업계 동향 (2026-01~10)

작성: 2026-10-23 · 근거: 재단·표준기구·공급자의 공식 발표와 기술 블로그, 보도 · MINT 쪽은 `origin/main 8edcb95`의 문서(`docs/ai`)를 읽은 범위. 코드를 새로 실행하거나 시험하지 않았다.
[출처 manifest](industry-trends-1023.sources.json)에 URL·확보 시각·SHA-256·열람 범위가 있고 원본은 ignored `local-sources/trends-1023/`(일부는 `cases-1023/`, `refs-update-1023/`)에 있다. 「시사점」과 「포지셔닝 갭」은 **방향 제안**이며 구현·승인·일정이 아니다.

> **읽는 법**: 「확인」 열은 1차(공급자·재단 공식 페이지), 2차(매체 보도), 제목만(목록 페이지에서 제목·날짜만 봄)으로 나눈다. 가격·수치는 공급자 표기를 옮긴 것이며 계약 조건·실거래가가 아니다. 기사에서 얻은 인수 금액은 쓰지 않았다.

## 1. 시간순 표

| 날짜 | 구분 | 사건 | 핵심(요약) | 확인 |
| --- | --- | --- | --- | --- |
| 2025-12-09 | 재단 | Linux Foundation이 Agentic AI Foundation(AAIF) 설립 발표 | MCP(Anthropic)·goose(Block)·AGENTS.md(OpenAI) 3개 프로젝트로 출범. 백금 회원은 AWS·Anthropic·Block·Bloomberg·Cloudflare·Google·Microsoft·OpenAI | 1차 |
| 2026-01-08 | 인수 | CrowdStrike, SGNL(지속 신원) 인수 계약 | 사람·비인간·AI 에이전트 접근을 실시간 위험에 따라 지속 부여·회수하는 동적 인가를 Falcon에 확장. 발표가 IDC의 신원 보안 시장 전망(2025년 약 290억 달러에서 2029년 560억 달러)을 인용 | 1차 |
| 2026-02-24 | 재단 | AAIF 신규 회원 97곳 | 회원 확대 발표 | 제목만 |
| 2026-03-03 | 클라우드 | Amazon Bedrock AgentCore Policy 정식 출시 | 정책을 자연어로 쓰면 Cedar로 변환되어 정책 엔진에 저장, AgentCore Gateway가 에이전트-도구 요청마다 평가 후 허용·거부. 13개 리전 | 1차 |
| 2026-03-24 | 사건 | LiteLLM PyPI 악성 판본(1.82.7·1.82.8) | 자격 탈취 코드 포함, 이후 제거. 사건과 같은 시기 다른 오픈소스 보안 도구에 대한 연쇄 공격으로 보도됨 | 2차 |
| 2026-04-14 | 공급자 | Cloudflare, 사내 MCP 운영 참조 아키텍처 공개 | MCP 서버 포털에 코드 모드 추가, 게이트웨이로 섀도 MCP 탐지 | 1차 |
| 2026-05-01 | 상용 | Microsoft Agent 365 정식 출시 | 에이전트 레지스트리·Entra Agent ID·도구·MCP 서버 접근 통제와 수명주기 규칙(비활성·소유자 없음·위험 에이전트 차단). 공식 페이지는 사용자당 월 $15(연 약정), Microsoft 365 E7 $99 표기 | 1차(가격)·2차(출시일, 메시지 센터 미러) |
| 2026-05-12 | 상용 | Docker AI Governance 발표 | 에이전트가 쓰는 네트워크·파일시스템·자격·MCP 도구 네 표면을 중앙 정책으로 통제, 개발자 노트북이 새 운영 환경이라는 논지. 가격은 확인하지 못함 | 1차 |
| 2026-05-18 | 재단 | AAIF 신규 43곳 | 골드: F5·GoDaddy·Stripe·TRON, 금융·인프라·보안·공공 포함 | 1차 |
| 2026-05-20 | 정부 | NSA AI 보안센터, MCP 보안 설계 고려사항 CSI | 인증·인가·입력 검증만으로 부족, 에이전트 환경 전체를 연속체로 | 1차(보도자료) |
| 2026-05-27 | 인수 | Snowflake, Natoma(MCP 플랫폼) 인수 계약 | 데이터 거버넌스 경계를 AI 행동으로 확장: 에이전트·MCP 도구 접근의 신원·정책·감사. 종결·가격 미확인 | 1차 |
| 2026-07-09 | 상용 | Citrix NetScaler에 MCP Gateway 기능 | 에이전트-MCP 서버 트래픽을 라우팅·통제·관측하는 단일 진입점. 발표 인용문은 사이버 보험이 MCP 게이트웨이를 요구하게 될 것이라고 예측(제조사 전망) | 2차(매체 게재 보도자료) |
| 2026-07-28 | 표준 | MCP 명세 2026-07-28 | 무상태 핵심, 다회전 요청, 헤더 라우팅, 인가 하드닝, 확장 프레임워크(tasks·MCP Apps·Enterprise Managed Authorization), 폐기 정책 | 1차 |
| 2026-07-28 | 상용 | Snowflake Cortex AI Gateway(Black Hat) | Natoma를 통합해 도구 호출 수준에서 신원·정책·감사를 집행한다고 설명 | 1차 |
| 2026-08-03 | OSS | agentgateway v1.4가 새 명세 명시 지원 | 블로그 배너는 agentgateway가 AAIF에 합류했다고 표시(합류일 미확인) | 1차 |
| 2026-08-13 | 재단 | AAIF 신규 57곳(총 247), MCP Dev Summit Seoul(08-13~14) | 골드: Alibaba·Visa·Wells Fargo. 한국 회원으로 NHN KCP·쿠콘·갤럭시아머니트리·ETRI를 지목 | 1차 |
| 2026-09 | 상용 | Nightfall 월간 제품 업데이트에 MCP Gateway 포함 | 블로그 목록의 9월 업데이트 제목에 포함. 상세 미확인 | 제목만 |
| 2026-09-14 | 재단 | AAIF, MCPA 자격 인증 출시 | AAIF 첫 공식 인증. 시험 5개 영역에 「보안·거버넌스」 포함. 같은 글이 MCP Tier 1 SDK 월 다운로드를 약 5억, ChatGPT 사용자의 MCP 도구 호출이 1월 대비 8월 98배라고 밝힘(재단 자체 수치). 게이츠 재단 가입은 제목만 확인 | 1차(인증)·제목만(가입) |
| 2026-09-17~18 | 행사 | AGNTCon+MCPCon 유럽(암스테르담) | 기조에서 「무상태 MCP를 운영에서」, 「AI 제어 평면」, 「에이전트 게이트웨이 패턴」 등이 의제. 사례 발표 다수(제목만) | 1차(일정표) |
| 2026-10-07 | OSS | Envoy AI Gateway가 Agent Router로 개명(AAIF 프로젝트) | 같은 코드·유지관리자·Apache 2.0, API 그룹·CRD는 유지. MCP 인증 강화 | 1차(릴리스 노트) |
| 2026-10-21 | 인수 | Cohere, AISLE(자율 취약점 탐지·수정) 인수 추진 | 에이전틱 AI에서 사이버보안이 핵심 과제라는 취지. 거래 조건 미확인 | 2차 |
| 2026-10-22 | 재단 | AAIF 회원 305곳, 프로젝트 10개로 확대 | 신규 4개: Agent Skills(Anthropic), Open Responses(OpenAI), OpenEnv(Hugging Face), OpenSandbox(Alibaba). 골드에 Ant Group·게이츠 재단·MongoDB·Nutanix·Royal Bank of Canada·Vercel·Vultr. AGNTCon+MCPCon 북미(산호세)에서 발표 | 1차 |

AAIF 프로젝트 10개: MCP, goose, AGENTS.md, A2A, Agent Router, agentgateway, Agent Skills, Open Responses, OpenEnv, OpenSandbox. AAIF 회비는 공식 회원 페이지에 백금 $350,000(신규 불가), 골드 $200,000로 표기돼 있다. 은/준회원 금액은 이번에 확인하지 못했다.

## 2. 시장 구조 — 누가 어디에서 MCP를 통제하는가

| 층 | 대표(이번에 확인한 것) | 통제 위치 | 배포 |
| --- | --- | --- | --- |
| 클라우드 제어 평면 | AWS AgentCore Policy·Gateway, Cloudflare MCP 서버 포털 | 클라우드 게이트웨이 앞단 | 클라우드(Cloudflare는 사내 적용도 자사 플랫폼) |
| 신원·SaaS 플랫폼 | Microsoft Agent 365(Entra Agent ID), CrowdStrike+SGNL, Snowflake Cortex AI Gateway(Natoma) | 신원·데이터 플랫폼 | 클라우드 중심 |
| 개발자 환경 | Docker AI Governance·MCP 게이트웨이 | 개발자 노트북·샌드박스 | 로컬+중앙 정책 |
| 네트워크 어플라이언스 | Citrix NetScaler MCP Gateway | 애플리케이션 전달 장비 | 온프레미스·클라우드 |
| 오픈소스 데이터 평면 | agentgateway·Agent Router(AAIF), IBM ContextForge, ToolHive | 프록시·쿠버네티스 | 자체 호스팅 |
| 스캐너·공급망 | Snyk Agent Scan, Cisco MCP Scanner | 도입 전 점검 | 개발·CI |

설문: Stacklok의 금융 기술 리더 100명 조사에서 MCP 서버를 주로 온프레미스·프라이빗 클라우드에 둔다는 응답이 33%(전 산업 평균 20%)였고 운영 사용은 3%였다(공급자 보고서 소개 페이지, 표본 100). 이 수치는 공급자 마케팅 자료의 일부이며 일반화하지 않는다.

## 3. 가격 모델 (확인된 범위만)

| 모델 | 사례 | 표기 | 비고 |
| --- | --- | --- | --- |
| 사용자당 월 구독 | Microsoft Agent 365 | $15/사용자/월(연 약정), M365 E7 $99 | 공식 페이지. 소비 요금이 별도인지는 확인하지 못함 |
| 소비(작업 단위) | AWS AgentCore Gateway | 작업(도구 목록·호출·상태 확인)·검색 질의·색인 대상 단위 과금, 최소 약정 없음 | 공식 가격 페이지. 단가는 이 조사에서 읽지 않음 |
| 요청 수 구독 | Portkey(LLM 게이트웨이) | Production $49/월, 월 10만 로그 포함, 초과 10만당 $9 | MCP가 아니라 LLM 게이트웨이 요금 |
| 오픈코어·영업 문의 | LiteLLM Enterprise | 가격 비공개(30일 체험 키), 거버넌스·SOC 2·ISO 27001·SSO·감사 로그를 엔터프라이즈 가치로 표기 | 공식 페이지 |
| 순수 OSS+자체 운영 | IBM ContextForge, agentgateway, Agent Router, ToolHive | 라이선스 비용 없음(Apache-2.0) | 에이블리는 핵심 기능이 유료 플랜에 묶이지 않은 점을 선정 이유로 밝힘(사례 10) |
| 재단 회비 | AAIF | 백금 $350,000, 골드 $200,000 | 공식 회원 페이지 |
| 인수 편입 | CrowdStrike+SGNL, Snowflake+Natoma | 가격 미확인 | 플랫폼 번들로 판매될 가능성이 높으나 확인되지 않음 |

Kong·Cloudflare·Docker·Okta의 MCP 가격은 공식 페이지에서 확인하지 못했다. 제3자 가격 비교 글은 서로 충돌해 사용하지 않았다.

## 4. 시사점

- **표준화는 재단으로 모이는 중**: MCP뿐 아니라 A2A·게이트웨이 데이터 평면 2개(agentgateway, Agent Router)와 샌드박스·스킬·응답 형식이 AAIF 아래에 있다(2026-10-22 기준 10개). 오픈 데이터 평면이 사실상 표준이 되면 자체 게이트웨이 데이터 평면의 유지 부담과 호환 설명 부담이 커진다.
- **새 명세가 게이트웨이 책임을 늘림**: 헤더 라우팅(`Mcp-Method`·`Mcp-Name`), 무상태 요청, 다회전 사람 확인, 인가 서버 검증. 헤더와 본문이 어긋날 때의 처리(분리된 판단)가 새 공격 면이라고 CoSAI가 지적한다.
- **통제 위치가 다양화**: 클라우드 앞단(AWS·Cloudflare), 신원(Microsoft·CrowdStrike), 데이터 플랫폼(Snowflake), 개발자 노트북(Docker), 어플라이언스(Citrix)로 나뉜다. 온프레미스 직원 PC·게이트웨이 한 세트로 도입 심사부터 종료까지 묶은 제품은 이번 조사 범위에서 확인하지 못했다(없다는 단정이 아님).
- **인수는 신원·접근 통제로 향함**: SGNL(신원), Natoma(MCP 접근)처럼 에이전트 접근 인가를 기존 플랫폼에 흡수하는 방향이다.
- **게이트웨이도 공격 대상**: 2026-08~10에만 ContextForge 15건·ToolHive 다수·Docker 2건·Microsoft 1건·MCP Inspector 9건의 권고가 있었다([최신 레퍼런스](../refs-update-1023/README.md) §4). 공급망 사건(LiteLLM)도 있었다.
- **금융 도입은 느리다**: 운영 사용 3%(설문), 국내는 강연 수준의 요구(신원 전파·읽기/쓰기 분리·승인 레지스트리)와 토스 같은 선도 사례만 확인된다([사례](../mcp-enterprise-cases-1023/README.md)). AAIF에는 Visa·Wells Fargo·Royal Bank of Canada와 국내 결제·정보통신 기관이 가입했다.

## 5. MINT 포지셔닝 갭 (후보)

| 번호 | 갭 | 근거 | 제안(구현 아님) |
| --- | --- | --- | --- |
| PG-1 | 새 명세 호환의 외부 설명 근거 | 명세 2026-07-28, 경쟁 OSS의 호환 발표(agentgateway v1.4) | 두 세대 협상 시험(D-74) 결과를 헤더 검증·다회전 요청 시험을 포함한 호환 표로 확장해 판매 자료의 근거로 둘지 결정 |
| PG-2 | 오픈 데이터 평면과의 관계 정리 | AAIF의 게이트웨이 프로젝트 2개, ContextForge 채택 사례 | MINT 게이트웨이의 고유 가치(도입 심사·종료 수명주기·감사 증거)와 대체 가능한 부분(프록시·라우팅)을 구분해 문서화 |
| PG-3 | 개발자 노트북·로컬 통제의 경쟁 | Docker AI Governance(네트워크·파일시스템·자격·MCP 도구), CrowdStrike(엔드포인트) | MINT 직원 PC 키트가 하는 것·하지 않는 것을 같은 4개 표면으로 대조(셸·SDK 범위 밖은 이미 문서화됨) |
| PG-4 | 가격·판매 단위의 근거 | 사용자당(Microsoft)·소비(AWS)·OSS+지원(LiteLLM·ContextForge) | 온프레미스 라이선스 단위(직원 수·서버 수·호출 수)에 대한 시장 비교표 필요 여부 결정 |
| PG-5 | 에이전트 신원 체계 연계 | Entra Agent ID, SGNL의 지속 신원 | MINT의 OIDC 선택 경로(D-65)가 에이전트 신원과 어떻게 만나는지 점검(미확인) |
| PG-6 | 금융권 요구와의 대응 | 토스·KB데이타시스템의 요구, 운영 사용 3% 설문 | 사례 문서의 CU-1·CU-5를 금융 도입 체크리스트로 묶을지 결정 |

PG 번호는 이 문서 안의 임시 표기이며 백로그 번호가 아니다.

## 6. 이 문서가 확인하지 않은 것

- 발표 사건의 거래 금액·종결 여부(Snowflake–Natoma, Cohere–AISLE)와 제품의 실제 호출 단위 차단 능력.
- Kong·Cloudflare·Docker·Okta의 MCP 가격, AWS AgentCore Gateway의 단가.
- Palo Alto Networks·Cisco·Zscaler·Okta 등의 MCP 관련 신제품. 검색에서 1차 출처를 얻지 못해 표에 넣지 않았다.
- agentgateway의 AAIF 합류일, Nightfall MCP Gateway의 출시 상세, Kong 2.0(2026-09 GA 보도)의 내용.
- 이전 초안이 언급한 Nightfall 「2026-09-09 Early Access」 날짜는 확인하지 못했다(블로그 제목만 확인).
- AAIF의 한국 회원 전체 목록과 MCPA 인증의 응시 조건.
- 1월 이전 사건(2025년 인수 등)은 포함하지 않았다.
