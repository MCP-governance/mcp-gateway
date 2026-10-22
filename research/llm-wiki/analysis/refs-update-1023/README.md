# 2026-08~10 MCP·AI 에이전트 보안 최신 레퍼런스 갱신

작성: 2026-10-23 · 근거: arXiv API·공식 명세 페이지·GitHub 릴리스/권고 API·공급자 공식 글 · MINT 쪽은 `origin/main 8edcb95`의 문서(`docs/ai`)를 읽은 범위. 코드를 새로 실행하거나 시험하지 않았다.
[출처 manifest](refs-update-1023.sources.json)에 URL·확보 시각·SHA-256·열람 범위가 있다. 원본은 ignored `local-sources/refs-update-1023/`에 있다. 아래 「적용」은 **방향 제안**이며 구현·승인·일정이 아니다.

> **확인 범위**: 학술 자료는 arXiv API의 초록·서지만 읽었다(본문·실험 조건 미정독). 공식 명세는 변경 목록 전문을 읽었다. OSS는 릴리스 노트와 보안 권고를 읽었고 코드는 읽지 않았다. 마케팅·저자 수치는 「저자 보고」로 표시했다.

## 1. 이전 초안에서 바로잡은 내용

같은 경로에 있던 미커밋 초안(작업 ID `RES-REFS`, Gemini)을 검증하며 대체했다. 초안의 항목 중 다음은 사실과 달랐거나 확인되지 않았다.

| 초안 항목 | 확인 결과 | 처리 |
| --- | --- | --- |
| arXiv:2510.16558(MCP 생태계 첫 분석)·2508.12538(MCPXKIT)이 카탈로그에 없다 | 이미 `LIB-G04`·`LIB-B14`로 등록돼 있다. 2603.22489(`LIB-B10`)·2608.20481(`LIB-D04`)·2608.00150(`LIB-G06`)·2609.19100(`LIB-G08`)·2607.14754(`LIB-G09`)·2609.15906(`P58`)도 마찬가지다 | 신규에서 제외. 「DSN 2026」 채택 표기는 확인하지 못해 쓰지 않음 |
| CoSAI MCP 보안을 v1.0에서 v2.0으로 갱신해야 한다 | `T15`가 이미 v2.0이다(2026-10-13 등록) | 갱신 불필요 |
| 「ToolHive v0.55.2 이후, CVE-2026-58197 송신 프록시 차단」 | v0.55.2는 권고 `GHSA-2x65-h9w3-h7hc`(루트리스 Podman 호스트 접근 엔드포인트가 송신 프록시 격리를 우회, 2026-10-19)의 수정 판본이다. CVE-2026-58197은 별개 결함으로 2차 자료가 설명한다(컨테이너에서 호스트 서비스 도달, 0.30.1에서 수정) | 두 결함을 분리해 기록 |
| 「OpenCode RCE via MCP OAuth (Pillar, 2026-10-20)」 | 공식 출처를 찾지 못했다. 가장 가까운 확인 사실은 MCP Inspector 권고 묶음(악성 OAuth 콜백이 stdio로 전환해 로컬 명령 실행 `GHSA-4fc4-wcmh-4g86` CVSS 9.6 등, 2026-10-21 공개)이다 | 「미확인」으로 제외, Inspector 권고를 §4에 수록 |
| 「OWASP MCP Top 10 v2026, Phase 5 개정 2026-10」 | 공식 프로젝트 페이지(2026-10-23 확보)는 「Phase 3 Beta, 현재 단계」이며 항목 번호는 `MCP01:2025`~`MCP10:2025` 그대로다 | 개정 게시는 「미확인」 |
| 「NSA+CISA+NIST 합동 초지능 사고 대응 10개 권고(2026-10)」 | 1차 원문을 찾지 못했다. Cloud Security Alliance 연구 노트(AI 보조 작성 안내 포함)가 2026-10-16 게시로 설명한다. 주 대상은 최전선 모델 개발자이며 MCP 게이트웨이와의 직접 관련은 작다 | 「미확인(2차만)」으로 §3에만 기록 |
| 「MCP 명세의 sampling 경계는 이미 문서화됨」 | 2026-07-28 명세는 Roots·Sampling·Logging을 **폐기 예정**으로 돌렸다(변경 목록 원문). `LIB-N24`의 sampling 지적은 신규 배포 기준 영향이 줄었다 | 정정 메모 |
| 「`LIB-M03`와 N-G02는 같은 문서일 수 있다」 | 이번에도 확인하지 못했다. `LIB-M03`는 호주 사이버보안센터(cyber.gov.au) 페이지로 등록돼 있다 | 미확인 유지 |

## 2. 학회·preprint (신규 27건)

선정 기준: arXiv API로 「Model Context Protocol」·게이트웨이·도구 호출 인가 관련 제출물을 2026-07-14~10-20 제출순으로 훑어 MINT 구조(게이트웨이 판정·승인·감사·공급망)에 직접 닿는 것을 골랐다. 2026-08 이전 제출은 MINT에 직접 관련된 6건만 포함했다(표의 제출일로 구분). 모두 `catalogs/papers.json`에 `LIB-N01`~`LIB-N27`로 추가했고 각 페이지는 [papers/](../../papers/)에 있다. 정식 학회지 게재가 확인된 것은 없다(채택 표기는 arXiv 주석 기준이며 판본 미확인).

| ID | 자료(arXiv) | 종류 | 제출일 | 핵심 | MINT 적용 |
| --- | --- | --- | --- | --- | --- |
| [LIB-N01](../../papers/LIB-N01.md) | GatewayBench: Unified Capability and Security Evaluation Platform for MCP Gat... (2610.23449) | preprint | 2026-10-16 | 게이트웨이 7종을 평면형·계층형으로 나눠 작업 완료·효율·공격 저항을 함께 측정한 첫 벤치마크(작업 524, 도구 11,118) | 참고: 우리 시험에 「도구 수가 늘어도 판정 유지」 축 추가 |
| [LIB-N02](../../papers/LIB-N02.md) | Zero-Trust Authorization and Discovery for Enterprise MCP (2609.22573) | preprint | 2026-09-18 | 목록 숨김과 호출 시 집행을 같은 선언으로 묶으면 금지 도구 노출 21.1%에서 0, 목록만 거르면 우회됨 | 이미 있음(주체별 목록 필터, D-74). 점검: 같은 규칙에서 나오는지 |
| [LIB-N03](../../papers/LIB-N03.md) | A Gateway Architecture for Enterprise MCP Authentication: Unifying Heterogene... (2608.10760) | preprint | 2026-08-11 | 팀별 제각각 인증을 중앙 게이트웨이로 모은 운영 보고. 사용자·자동 주체 2축, 토큰 교환(RFC 8693) 위임 | 갭: 사용자별 업스트림 위임 미구현(ARCHITECTURE) |
| [LIB-N04](../../papers/LIB-N04.md) | Hybrid Semantic Tool Discovery for Enterprise MCP Gateway: Architecture and I... (2608.23992) | preprint | 2026-08-25 | 도구 2,000개 이상 앞에서 검색·실행 메타 도구 2개로 노출. PayPal 운영 토큰 140.2k에서 1.3k(저자 보고) | 갭: 점진 노출 없음. 검색 도구도 정책 판정 대상이어야 함 |
| [LIB-N05](../../papers/LIB-N05.md) | My Credentials, Please: Detecting Filesystem Capability Laundering in MCP Ser... (2610.22301) | preprint | 2026-10-15 | 로컬 MCP 서버 승인이 호스트 파일 권한까지 열어 주는 「능력 세탁」. 선별 서버 4,806개 중 16.4%가 비파일 분류인데 파일 능력 | 참고: 로컬 MCP 원클릭 승인(D-192) 계약에 접근 경로 기재 |
| [LIB-N06](../../papers/LIB-N06.md) | Runtime Authorization Consistency Checking for MCP-based Agentic Workflows (2609.23498) | preprint | 2026-09-20 | 호출별로는 허용돼도 이어 붙이면 경계를 넘는 「인가 표류」를 계보 비교로 차단. 놓침 0/1,008 | 부분: 호출 순서 정책 있음. 점검: 「직전 수락보다 넓은 권한」 시험 |
| [LIB-N07](../../papers/LIB-N07.md) | ACLE-MCP: Attested Capability Leases for Execution-Time Trust in Remote LLM T... (2609.02690) | preprint | 2026-09-02 | OAuth 승인 뒤 실제 실행 워크로드가 바뀌는 간극. 호출 단위 임대와 서버 실행 관문(p95 +25.7%) | 참고: 외부 원격 MCP를 업스트림으로 쓸 때의 한계 문서화 |
| [LIB-N08](../../papers/LIB-N08.md) | TrustShiftProbe: Characterizing, Benchmarking, and Defending Staged Trust Att... (2608.23763) | preprint | 2026-08-24 | 처음엔 정상이다 나중에 악성으로 전환하는 서버(TrustShift)와 행동 기준선 방어 SHIELD | 부분: 계약 해시 재승인만 있음. 응답 기준선 이탈은 갭 후보 |
| [LIB-N09](../../papers/LIB-N09.md) | Local Allow, Global Deny: Why Per-Action Authorization Does Not Compose in LL... (2610.27620) | preprint (채택 표기: IEEE TPS 채택본의 확장판) | 2026-10-20 | 호출별 인가는 합성되지 않음. 목적 위반은 호출별 감시기로 원리상 못 잡는다는 불가능 결과 | 참고: 호출별 판정 한계의 이론 근거. 교차 실행 감시는 후속 |
| [LIB-N10](../../papers/LIB-N10.md) | Approve What, Exactly? Effect Binding and Trusted Rendering for Agent Step-Up... (2610.21063) | preprint | 2026-10-15 | 승인 경로 공격 12종. 승인 카드를 게이트웨이가 정규화해 서명하면 포착률 0.30에서 0.98 | 갭 후보: 승인 후 인자 변경 방지·승인 홍수 대응 점검 |
| [LIB-N11](../../papers/LIB-N11.md) | Agent Approval Laundering: Transitive Effects Beyond the Approved Invocation (2609.28586) | preprint | 2026-09-23 | 승인 기록이 진입 호출만 적고 전이 효과를 빠뜨리는 「승인 세탁」. 효과 단위 기록으로 잔여 40에서 13 | 갭 후보: 원장에 예상 효과 필드 |
| [LIB-N12](../../papers/LIB-N12.md) | Runtime Authorization for Resources Acquired by AI Agents (2609.14744) | preprint | 2026-09-13 | 획득한 자격·계정 등이 곧바로 권한이 되는 간극. 격리, 증거 해석, 활성화 트랜잭션 | 참고: 도구 응답 속 자격 재사용 차단 규칙의 근거 |
| [LIB-N13](../../papers/LIB-N13.md) | Kairos: Transactional Security Enforcement at the System Boundary for LLM Agents (2610.18457) | preprint | 2026-10-13 | 에이전트 격리 경계의 참조 모니터. 신뢰 출처 정책과 보류 후 증거로 해제. AgentDojo 47.0%에서 2.7% | 참고: 허용·차단 외 「보류」 상태 검토(관찰 모드와 구분) |
| [LIB-N14](../../papers/LIB-N14.md) | CreepScope: Measuring Post-Use Authorization Exposure in Tool-Using Agents (2610.15988) | preprint | 2026-10-11 | 앞서 준 권한이 단계 뒤에도 남는 「권한 잔존」을 CSE·RPD로 측정 | 참고: 동의·목적 결속 유효 기간 점검 지표 |
| [LIB-N15](../../papers/LIB-N15.md) | Persistent Billable State: Denial-of-Wallet Attacks and Defenses in Tool-Call... (2609.28585) | preprint | 2026-09-23 | 도구 응답 보존이 재과금되는 지갑 서비스 거부. 세션 누적 입력이 첫 호출의 14,293배 | 이미 있음(응답 크기 상한). 점검: 후속 문맥 증식 |
| [LIB-N16](../../papers/LIB-N16.md) | Mandato: Protocol-Level Enforcement of Digitally Signed Mandates on AI Agent ... (2608.14074) | preprint | 2026-08-14 | 서명된 위임장으로 도구·인자·기간을 제한하는 MCP 투명 프록시. 해시 체인 감사 로그, EU 규제 대응 매핑 | 참고: 감사 원장 증거 가치 비교. 구현·평가는 계획 단계 |
| [LIB-N17](../../papers/LIB-N17.md) | KedgeFlow: A Programmable Control Plane for Enterprise AI Agents (2610.14810) | preprint | 2026-10-10 | 승인·실행이 계약을 공유하지 않아 생기는 변조·동시 재사용·재시도를 1회 소비 허용량으로 해결 | 참고: 승인 호출 1회 소비·경쟁 시험 |
| [LIB-N18](../../papers/LIB-N18.md) | Registry Descriptions Go Stale Unevenly: An 89-Day Measurement of Model Conte... (2608.00997) | preprint | 2026-08-02 | 공식 레지스트리 89일 관측. 설명 변경 서버 8.6%, 변경 절반은 신규 등록. 해시 변경 즉시 재검증과 주기 전수 점검 | 이미 있음(계약·설명 해시 재승인). 외부 근거로 인용 |
| [LIB-N19](../../papers/LIB-N19.md) | What a Random Draw from the MCP Registry Contains, and What Tool-Use Benchmar... (2609.10962) | preprint | 2026-09-10 | 레지스트리 무작위 400개 중 초기화 성공 48.8%, 도구 안전 주석 누락 58.8% | 참고: 기동 실패·주석 누락 서버를 심사에서 다루는 방식 확인 |
| [LIB-N20](../../papers/LIB-N20.md) | Understanding the Hierarchical Structure and Functional Landscape of the Mode... (2610.05319) | preprint | 2026-10-04 | 서버 124,267개·도구 1,328,233개 지도. 98.5%가 대체 도구 보유, 복잡도 2.5배 이상 차이 41% | 참고: 도입 심사에서 대체 도구 비교 화면 |
| [LIB-N21](../../papers/LIB-N21.md) | A Formal Security Framework for MCP-Based AI Agents: Threat Taxonomy, Verific... (2604.05969) | preprint | 2026-04-07 | 위협 7범주·벡터 23개 분류, 기존 방어 12종 비교(단일 방어는 34%를 넘지 못한다는 주장) | 참고: 위협표 대조 점검표. 91%는 저자 주장 |
| [LIB-N22](../../papers/LIB-N22.md) | SMCP: Secure Model Context Protocol (2602.01129) | preprint | 2026-02-01 | 통합 신원·상호 인증·정책·감사를 더한 프로토콜 확장 제안(설계 논문) | 참고: 직접 채택 대상 아님 |
| [LIB-N23](../../papers/LIB-N23.md) | Invisible Threats from Model Context Protocol: Generating Stealthy Injection ... (2603.24203) | preprint | 2026-03-25 | 트리 기반 적응 탐색의 간접 주입 TIP. 방어 없을 때 95% 이상, 대표 방어 4종 앞에서 50% 이상 | 참고: 적응형 공격 가정 시험. 결정적 정책이 받침이라는 점 명시 |
| [LIB-N24](../../papers/LIB-N24.md) | Breaking the Protocol: Security Analysis of the Model Context Protocol Specif... (2601.17549) | preprint | 2026-01-24 | 명세 구조 취약점 3가지(능력 증명 부재·sampling·다중 서버 신뢰). 확장 MCPSec 52.8%에서 12.4% | 정정 메모: 새 명세가 sampling을 폐기 예정으로 돌림 |
| [LIB-N25](../../papers/LIB-N25.md) | MCP Security Bench (MSB): Benchmarking Attacks Against Model Context Protocol... (2510.15994) | preprint (채택 표기: ICLR 2026 채택) | 2025-10-14 | 공격 12종을 실제 도구로 실행하는 MSB(공격 2,000개, 9모델). 성능 높은 모델이 더 취약 | 참고: 기존 MCPSecBench(P43)와 보완 |
| [LIB-N26](../../papers/LIB-N26.md) | AI Agents May Always Fall for Prompt Injections (2605.17634) | preprint | 2026-05-17 | 데이터-지시 분리 방어의 한계와 문맥적 무결성 관점. 방어자 딜레마 제시 | 참고: 「완전 방어 아님」 제품 주장 근거 |
| [LIB-N27](../../papers/LIB-N27.md) | ClawMMU: Protection-Coherent Virtual Memory for Stateful LLM Agents (2610.28093) | preprint (채택 표기: NeurIPS 2026 AgenticOS 워크숍) | 2026-10-20 | 기억 조각마다 소유자·범위·출처·권한 라벨을 붙여 검사(워크숍 채택, 비아카이브) | 참고: 응답에서 후속 호출로 라벨 전파 가능성(채택 여부는 소유자) |

정부 가이드 [`LIB-N28`](../../papers/LIB-N28.md)(NSA CSI)는 §3에 있다. 아래는 이미 등록된 관련 자료이며 이번에 중복 추가하지 않았다: `LIB-G04`(2510.16558), `LIB-B14`(MCPXKIT), `LIB-B10`(2603.22489 위협 모델링·도구 오염, 클라이언트 7종 비교), `LIB-D04`(AEGIS), `LIB-G06`(인터넷 노출 서버 동적 평가), `LIB-G08`(원격 MCP 중앙화·관측), `LIB-G09`(FlowGuard), `P58`(인가 아키텍처 서베이).

## 3. 공식 명세·표준·정부 가이드

| 자료 | 종류 | 날짜 | 핵심(요약) | MINT 적용 |
| --- | --- | --- | --- | --- |
| [MCP 명세 2026-07-28 변경 목록](https://modelcontextprotocol.io/specification/2026-07-28/changelog) (manifest `S1`) | 공식 명세 | 2026-07-28 | 프로토콜 세션·`Mcp-Session-Id`·`initialize` 제거(요청마다 `_meta`), `server/discover`, 서버가 클라이언트에 묻는 요청을 다회전 요청(MRTR, `input_required`)으로 대체, `Mcp-Method`·`Mcp-Name` 헤더 필수, 목록 응답 `ttlMs`·`cacheScope`, 인가 서버의 `iss` 응답(RFC 9207)을 클라이언트가 검증, DCR 폐기 예정과 Client ID Metadata Documents 전환, 자격은 발급 인가 서버에 결속, Roots·Sampling·Logging·HTTP+SSE 폐기 예정(최소 12개월), tasks를 공식 확장으로 이동 | 이미 있음: 두 세대 협상·`cacheScope` 확인(D-74). 갭: ① `Mcp-Method`·`Mcp-Name`와 본문의 일치 검증(CoSAI `T15` 권고, D-74는 `x-mcp-header` 미시험) ② 공급자가 `input_required`를 돌려주면 현재 실패 처리(D-74③) ③ 인가 변경은 IdP에 해당 엔드포인트가 없어 해당 없음(D-74) |
| [MCP 공식 블로그 글](https://blog.modelcontextprotocol.io/posts/2026-07-28/) (`C17`) | 공식 블로그 | 2026-07-28 | 위 변경의 배경. 게이트웨이·WAF가 본문 해석 없이 헤더로 라우팅·계량할 수 있다고 설명. Tier 1 SDK 월 다운로드 약 5억(프로젝트 자체 수치) | 참고. 다운로드 수치는 공식 주장으로만 취급 |
| [NSA AISC, MCP 보안 설계 고려사항 CSI](../../papers/LIB-N28.md) | 정부 가이드 | 2026-05-20 | 보도자료만 읽음: MCP 직렬화 위험·신뢰 경계·에이전트 오용, 인증·인가·입력 검증만으로 부족해 에이전트 환경 전체를 연속체로 다뤄야 함, 고보증 환경에서 신중 도입 | 참고: 본문 권고는 PDF 확보 후 대응표. PDF는 서버가 자동 요청을 403으로 막아 본문을 읽지 못함 |
| [OWASP MCP Top 10](https://owasp.org/www-project-mcp-top-10/) (`OW1`) | 업계 표준(베타) | 2026-10-23 확보 | 10항목: 토큰·비밀 노출, 범위 확대 권한 상승, 도구 오염, 공급망, 명령 주입, 문맥 페이로드 주입, 인증·인가 부족, 감사·텔레메트리 부족, 섀도 MCP 서버, 문맥 과다 공유. 현재 Phase 3(베타) | 이미 있음: 기존 `T08`. 번호 체계가 2025 그대로이므로 개정 시 재대조 |
| CoSAI MCP 보안 v2.0 | 업계 표준 | 2026-08 | 기존 `T15`(2026-10-13 등록)와 동일. 이번에 다시 읽지 않음 | 이미 있음 |
| [CSA 연구 노트: MCP 도구 오염과 IDE 자동 실행](https://labs.cloudsecurityalliance.org/research/csa-research-note-mcp-tool-poisoning-auto-execution-20260701/) (`CSA1`) | 보조(연구 노트) | 2026-07-01 | 프로젝트가 정의한 MCP 서버를 IDE가 자동 실행하는 위험을 다룸. 참고문헌에 2026-05~06 사건(Adversa, Wiz의 Amazon Q 사례)을 인용하나 원 사건은 이번에 확인하지 않음 | 참고. CSA 연구 노트는 공식 승인 문서가 아님 |
| [CSA 연구 노트: 합동 「10 practices」](https://labs.cloudsecurityalliance.org/research/csa-research-note-caissi-nsa-cisa-si-incident-readiness-2026/) (`CSA2`) | 2차 자료 | 2026-10-16 게시로 서술 | NIST·NSA·CISA가 최전선 모델 훈련·평가 중 「통제 사고」 대비 10개 실천을 냈다고 설명. 증거 보존에 거부된 도구 호출도 포함 | **1차 원문 미확인.** MINT는 차단 호출을 원장에 남기므로 참고만 |

## 4. 주요 OSS 게이트웨이·스캐너 릴리스와 공시

자세한 표와 한계는 [solutions/oss-gateway-scanner-releases-1023.md](../../solutions/oss-gateway-scanner-releases-1023.md). 코드는 읽지 않았다.

| 자료 | 종류 | 날짜 | 핵심 | MINT 적용 |
| --- | --- | --- | --- | --- |
| agentgateway v1.6.0 (Apache-2.0, AAIF 프로젝트) | OSS 릴리스 | 2026-10-02 | MCP 호환 공백 보완, OIDC·JWT 개선, 키별 로컬 요율 제한. v1.4가 2026-07-28 명세 지원(공식 블로그 08-03). 권고 `GHSA-h7hp-2f8r-9g9c`(MCP를 OpenAPI로 변환할 때 인자 정제 미흡, v1.6.0 수정) | 참고: 호환 대상. 변환형 게이트웨이는 인자 정제가 공격 면 |
| Agent Router v1.2.0 (구 Envoy AI Gateway, Apache-2.0, AAIF 프로젝트) | OSS 릴리스 | 2026-10-07 | 개명 후 첫 릴리스. MCP 인증·교차 네임스페이스 참조 강화, MCPRoute에 호출자 제공 자격·정책 병합. 보안 수정으로 동작이 바뀜(노트 경고) | 참고: 이전 이름으로 된 자료와의 연속성 주의 |
| IBM ContextForge v1.1.0 (Apache-2.0) | OSS 릴리스 | 2026-10-20 | 현대 MCP 협상 기본 `auto`, Origin/Host 보안 강제, 설정 가져오기 소유권 강제, 호출 시점 URL 스킴 허용 목록, 연합 도구 이름 충돌 탐지. 2026-08~09 공시 15건(기본 JWT 키 「changeme」 CVSS 8.9, Compose 기본 JWT 비밀 9.8, SSRF 9.1 등) | 참고: 기존 카드는 고정 커밋 기준. **기본 비밀·SSRF 시험을 MINT에도 적용** |
| Docker MCP Gateway v0.44.2 (MIT) | OSS 릴리스 | 2026-10-21 | 권고 2건: 대소문자만 다른 도구 이름이 예약 이름 충돌 검사 우회(10-13), 잘못된 URI로 충돌(10-08) | 참고: 도구 이름 정규화·충돌 시험 |
| ToolHive v0.56.0 (Apache-2.0) | OSS 릴리스 | 2026-10-22 | 권고 다수: 필터가 본문을 못 읽으면 도구 허용 목록 건너뜀(0.51.3 이하), 범위 밖 숫자로 인가가 빈 도구 이름 평가(0.54.0 미만), 같은 JSON-RPC id 동시 요청 시 응답 뒤바뀜(0.55.0 미만), 새 규격 요청이 DNS 리바인딩 Host 검사 건너뜀(0.56.0 미만) | 참고: **파싱 실패·id 충돌 시 fail-open 여부를 MINT 시험에 추가** |
| Microsoft MCP Gateway (MIT) | 보안 권고 | 2026-10-16 | 쿠버네티스 이름 충돌로 내장 도구 게이트웨이 탈취·타 사용자 워크로드 접근(1.0.0 미만, 수정 1.0.0). 저장소에 GitHub 릴리스는 조회되지 않음 | 참고: 이름·소유 결속 시험 |
| MCP Inspector 권고 묶음 | 보안 권고 | 2026-10-21 | 악성 OAuth 콜백이 stdio로 전환해 로컬 명령 실행(CVSS 9.6, 수정 1.0.3), 원격 MCP 앱이 프록시 토큰 탈취 후 로컬 명령 실행(9.6), 원격 서버가 OAuth 인가 경로로 사용자 PC에서 코드 실행(8.8, 수정 2.12.0) 등 9건 | 참고: 도입 심사에 쓰는 Inspector는 최신 판본 고정·격리 실행 |
| MCP TypeScript·Python SDK 권고 | 보안 권고 | 2026-09-28~10-15 | OAuth 클라이언트가 서버가 고른 인가 서버로 자격을 보냄(TS `CVE-2026-104850`, Python 같은 제목), 다른 서버용 토큰 수락, 교차 출처 리다이렉트에 헤더 재전송, 요청 크기 무제한, 공유 전송에서 클라이언트 간 메시지 전달(TS `CVE-2026-111770`, 2026-10-15) | 이미 있음: `LIB-A05`가 한 건을 등록. 나머지는 SBOM 영향 조회로 판본 확인 대상 |
| Snyk Agent Scan v0.6.9 (Apache-2.0) | OSS 스캐너 | 2026-10-20 | MCP-Scan의 후속 이름. 점검 항목 수·토큰 요구는 2차 자료(미확인) | 참고: 도입 심사 스캐너 후보 비교 |
| Cisco MCP Scanner 4.8.7 (Apache-2.0) | OSS 스캐너 | 2026-10-20 | MCP SDK 2.0 협상 지원 추가 | 참고: 판본 갱신 |
| LiteLLM PyPI 악성 판본 1.82.7·1.82.8 | 사건(2차 보도) | 2026-03-24 | 계정 탈취로 탈취 코드를 담은 판본 게시 후 제거. 2026-08~10에 권고 5건 | 이미 있음: SBOM 영향 조회·판본 고정. 점검: LiteLLM 애드온(D-191)이 침해 판본을 쓰지 않았음을 확인하는 절차 |

## 5. MINT에 주는 것 (이미 있음 · 갭 · 제안)

**이미 있음(문서 기준)**: 새 명세 두 세대 협상과 주체별 목록 캐시 격리(D-74), 호출 전 OPA 판정과 실패 시 차단, 계약 해시 재승인, 호출 순서 정책, 응답 크기 상한·멱등성, SBOM 영향 조회, 오프라인 버퍼·SIEM 전달. 코드 존재와 기기 통과는 구분해 읽는다(위키 규칙).

| 번호 | 갭(문서 기준 후보) | 근거 | 확인할 일 |
| --- | --- | --- | --- |
| RU-1 | 사용자별 업스트림 위임(토큰 교환) 미구현 | `LIB-N03`, ARCHITECTURE의 「RFC 8693 위임은 아직 아니다」 | 어떤 업스트림에 위임이 필요한지부터 목록화 |
| RU-2 | 공급자 `input_required`(다회전) 응답을 실패로 처리 | 명세 변경 목록, D-74③ | 사람 확인이 필요한 호출을 새 규격에서 어떻게 받을지 설계 결정 필요 |
| RU-3 | `Mcp-Method`·`Mcp-Name`와 본문 불일치 검증 | 명세, CoSAI `T15`(헤더·본문 불일치는 보안 실패) | 판정이 본문을 기준으로 하는지 코드 확인과 음성 시험 |
| RU-4 | 게이트웨이 자체의 fail-open·기본 비밀·이름 충돌 | ContextForge·ToolHive·Docker·Microsoft 권고(§4) | 같은 유형 시험 목록을 MINT 시험에 추가 |
| RU-5 | 도구 카탈로그 점진 노출과 응답 투영 | `LIB-N04`, [기업 사례](../mcp-enterprise-cases-1023/README.md)(Uber·Cloudflare·PayPal·Booking.com) | 보안 속성을 유지한 채 도입할지 소유자 결정 |

RU 번호는 이 문서 안에서만 쓰는 임시 표기이며 백로그 번호가 아니다. 구현·우선순위는 소유자가 정한다.

## 6. 이 문서가 확인하지 않은 것

- 논문 27건의 본문·실험 조건·재현. 초록의 수치는 저자 보고다.
- NSA CSI PDF 본문(자동 요청 403, 브라우저에서는 다운로드 처리). 보도자료와 PDF 바이트 해시만 확보했다.
- 정식 학회·저널 게재 여부: `LIB-N09`(IEEE TPS)·`LIB-N25`(ICLR 2026)·`LIB-N27`(NeurIPS 워크숍)은 arXiv 주석의 채택 표기이며 학회 논문집은 확인하지 않았다.
- OSS 제품의 코드·기본 설정·호출 단위 인가 여부. 릴리스 노트와 권고만 읽었다.
- OWASP MCP Top 10 개정 게시, 합동 「10 practices」 1차 원문, `LIB-M03`와 합동 CSI의 동일성.
- 2026-08 이전 제출 6건은 MINT 직접 관련성으로 골랐다. 전수 조사가 아니다.
