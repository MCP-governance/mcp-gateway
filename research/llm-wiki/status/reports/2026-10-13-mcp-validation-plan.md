# 팀 개발 브랜치·MCP 후보·검증 및 실패 시 수정 계획

- 작업자: Codex
- 기준: 원격 기본 HEAD `2e36095bf982ffab29ea81b6cdc24bdc435b184f`, 2026-10-13 확인.
- 작업 브랜치: `10/13-mcp-validation`. 팀원 합류 이후 작업별 브랜치 규칙을 AGENTS.md·CLAUDE.md에 반영했다.
- 변경: 팀 작업 규칙, 이 보고서, 대상·실험 목록, 로컬 우회 E13 설계, 카탈로그·현황·백로그·코드 스냅샷.
- 기존 docs/ai·endpoint-agent·poisoning 등의 미커밋 변경은 보존했다. 이번에 제품 코드를 변경하거나 실험을 실행하지 않았다.
- 목표: 로컬을 포함한 대상, 최신 구현 변화, 비교 보강 우선순위, 정확한 통과 조건과 실패 시 수정 위치를 팀이 재사용할 수 있게 만든다.

## 최신 커밋과 실제 기능 확장

**기준 최신 `2e36095` 자체는 문서·카탈로그·증거 변경이다.** 새 제품 기능이 그 커밋에서 추가된 것은 아니다. 이전 구현·검증 커밋을 포함한 최종 상태는 다음과 같다. 이 보고서의 후속 커밋 역시 설계·문서 변경이다.

| 커밋 | 변경과 결과 | 확인 수준 |
| --- | --- | --- |
| `531a4f3` | 개발용 MD 위키: 논문·문서25, 제품8, 최초 실험12, XLSM 위협표24 | 출처·해시·코드 분석·설계. 실험 통과 수와 다름 |
| `6178dd3` | 웹을 실제 Codex×Claude 협업 콘솔로 전환. 제품에 CPU·메모리·내부 DNS/TCP 연결 지연 API/UI 추가 | 협업 공개 기록·권한·측정·Chrome 실화면 확인 |
| `6178dd3` | 계약 A→B→A 복귀, 감사 v7의 시각 보호, 디코딩된 결과 지시문 검사, 목적지 정책 데이터 실패 차단, OAuth refresh 계열 경쟁 수정 | 수정 전 실패 재현→수정 후 회귀 통과. 상세는 [개발 결과](2026-10-13-development-results.md) |
| `6178dd3` | field 게시 집합 검사와 최근 수신200건 UI 표현 수정 | 17개 게시 회귀. 전체 OS 집계·수집 신선도 구현은 후속 |
| `c6ab26a` | 실제 PostgreSQL refresh 회전·철회·롤백 검사3건, 기존 관리형 거부 문구 기대 정렬 | 솔루션 기기 실제 DB3건과 전체CI 통과 |
| `2e36095` | 배포·PJ1 fresh 하네스·원장740~742와 한계 기록 | [해당 HEAD 전체CI 성공](https://github.com/MCP-governance/mcp-gateway/actions/runs/38355027939)을 이번 작업에서 재확인 |

CPU·메모리는 컨테이너의 `/proc`에서 보이는 Linux 호스트/VM 범위다. 지연은 **Console→Gateway의 DNS+TCP 연결 시간(ms)**이다. PJ1→솔루션의 Tailnet 지연이나 패킷 손실률은 아직 구현·검증하지 않았다. 초기/오래된/실패한 값은 `—`로 표시한다. 단위·로컬 회귀63건, OPA86건, 실제 PostgreSQL3건은 각 층의 검증이며 아래 MCP 실험 전체 통과를 의미하지 않는다.

## 로컬을 포함한 MCP 후보

로컬 후보는 이미 10종 포함돼 있었다. 그러나 **자체 운영 서버의 stdio를 HTTP로 변환해 Gateway 뒤에 두는 경로**와 **PJ1에서 직접 실행하는 stdio/localhost 경로**는 다르다. 기존 카드에는 후자의 전용 시험이 없었으므로 E13을 추가했다. 직접 stdio에는 Gateway 도구 정책이 자동 적용되지 않는다.

| 순서 | 후보와 배치 | 확인할 기능·이유 |
| --- | --- | --- |
| 1 | 격리 mock MCP, stdio/HTTP marker fixture | 수신 횟수·파일 효과·schema 변경·지연·장애를 통제. 독립 증거 확보와 E07/E08/E10/E13의 재현성 |
| 1 | 자체 운영 filesystem | 공개 읽기, 합성 PII 결과 마스킹, 경로·schema 검사. E01/E02/E06의 정상 기준선 |
| 1 | 자체 운영 fetch + 전용 HTTP sink | 내부/외부 목적지, 주소 정규화·redirect, SSRF, 비신뢰 응답. E05와 결과 검사 |
| 1 | email + 전용 메일 sink | 내부/외부 수신자, PII·secret, 승인 전 발송0·승인 후 정확한 효과. E03/E04 |
| 2 | git·postgres·redis·memory | repo/table/key 범위, 읽기 위장 쓰기, 중복·TTL, 저장된 개인정보와 종료 후 잔존 |
| 3 | desktop·playwright | 명령 실행·브라우저 콘텐츠·파일/네트워크 경계. 실행 범위를 제한한 합성 fixture만 사용 |
| 3 | gitea + 시험 repo/시험 PAT | 공급자 보유 자격·소유권·종료 후 실제 재접근. E09/E11 |
| 병행 | PJ1의 직접 stdio·localhost IPv4/IPv6 | 관리형 launcher/profile/UID 규칙이 Gateway 우회를 막는지. E13 |
| 후속 | Microsoft Learn·Cloudflare docs·GitHub remote·자체 배포 Feature Reference Server | 실제 Streamable HTTP·schema·OAuth·서버 목록·위임·회수 호환성 |

고정 후보 패키지·버전과 공식 URL은 [대상 목록](../../experiments/targets.md)에 있다. 설치 시 해당 판본의 실제 dependency hash·tools/list·승인 계약을 다시 고정한다. 취약 filesystem/git 판본은 도입 거부 메타데이터 fixture로만 사용하며 설치·실행하지 않는다.

솔루션 스택과 서버 fixture는 **솔루션 기기**, 실제 모델·하네스는 **PJ1**에서 실행한다. 사용자 노트북은 MD·정적 검사·협업 콘솔 용도다. 현재 field 레지스트리와 10종 lab 레지스트리는 별도다. 10종이 지금 모두 설치·활성화됐다는 증거는 없다. 정상 관리형 하네스에서 필요한 로컬 MCP는 Gateway 뒤에 승인·등록하고 설정을 레지스트리에서 렌더링한다.

## 비교에서 보강할 기능

아래는 기존 [8개 고정 소스/공식 문서 분석](../../solutions/README.md)을 개발 목표에 연결한 설계다. 제품 간 동일 조건의 실행 비교는 아직 하지 않았다. 사전 실행 정책·PII·권한 필터 자체를 우리만의 기능으로 주장하지 않는다.

| 참고 대상 | 기존에 확인한 방식 | 우리 솔루션에서 보강할 것 | 완료 조건·관련 백로그 |
| --- | --- | --- | --- |
| [ContextForge](../../solutions/ibm-contextforge.md) | PDP·사전/사후 훅, PII enforce 설정, OAuth 위임 코드 | 한국어/인코딩 PII·주입 정상/공격 코퍼스, scanner 오류·timeout의 실패 계약, fresh 인증 승인 실행 | 정상군 유지·미탐/오탐·효과0 확인. DEV02/09/17 |
| [CPEX](../../solutions/ibm-cpex.md) | 원자 호출량 연산 | 기존 PostgreSQL 예약을 유지하며 TTL·철회·중복·다중 worker 경합과 프로세스 사망을 검증. dispatch intent와 실행 불확실성 기록 | 중복 실제 효과1, 사망 후 성공/미실행을 추측하지 않음. DEV04/21 |
| [Microsoft MCP Gateway](../../solutions/ms-mcp-gateway.md) | 역할과 자산 소유권 평가 | 조직·소유권·사용자/agent 위임 교집합을 승인·실행·권한 변경에 일관되게 적용 | 타 조직/소유자/철회 권한의 실제 전달0. DEV05/07 |
| [Wassette](../../solutions/ms-wassette.md) | Wasm/WASI 실행 경계 | 위험 도구의 선택적 격리 실행, 로컬 실행/localhost 통제, 실행 파일·자원 상한 검증 | 관리형 경로의 파일·망·실행 경계와 승인 정상군. DEV19 |
| [LiteLLM](../../solutions/litellm.md) | 명시 MCP 서버 범위 제한 | 누락/빈 목록/unknown alias·권한 변경 캐시에서 범위가 확대되지 않는 처리 | 실제 하네스 목록·잘못된 서버 접근0. DEV05/07 |
| [Kong](../../solutions/kong-ai-gateway.md) | tool ACL·MCP OAuth/프로토콜 통합 | audience·scope·issuer·만료·철회·지원 protocol 검증, 외부 OIDC 운영 배선 확인 | 잘못된 토큰은 입구 거부, 정상군·새/기존 세션 검증. DEV05 |
| [BeyondTrust](../../solutions/beyondtrust-pathfinder.md) | 사이트/사용자 활성화·기한 있는 자격 | 만료·조직 이동·철회가 계약·사용자·기존 세션·자원 서버에 실제 반영되는지 | Gitea 등 실제 접근 철회·C1~C4/T1~T3. DEV08/17 |
| [Lunar](../../solutions/lunar-mcpx.md) | MCP 서버의 outbound API 통신을 별도 Gateway에서 관측·집행 | client→MCP뿐 아니라 MCP 서버→외부 API의 목적지·자격·재시도·효과 증거 연결 | 승인 서버가 직접 외부로 보낸 요청의 집행 범위 입증. DEV20 |

이번에 [ContextForge 고정 설정](https://github.com/IBM/mcp-context-forge/blob/5735c9db7f8f50cd5a55eb7fefe83ecde00b5324/plugins/config.yaml), [CPEX 고정 원자 연산 코드](https://github.com/IBM/cpex-plugins/blob/ae26938128cb438a268e7f3217603bc39b9dd18f/plugins/rust/python-package/rate_limiter/src/redis_backend.rs), [Kong 공식 MCP Proxy](https://developer.konghq.com/plugins/ai-mcp-proxy/), [Lunar 공식 연동 설명](https://www.lunar.dev/post/safely-running-untrusted-mcp-servers-with-lunar-mcpx-and-gateway-integration)을 다시 확인했다. 적용할 보강은 이 근거에서 도출한 **우리 설계**이며 공급자 시연을 우리 솔루션 통과 증거로 사용하지 않는다.

## 검증 목표와 실패 시 수정

핵심 목표는 **승인된 정상 업무는 성공하고, 비승인 실행·외부 반출은 실제 효과 전에 막으며, 실행·응답·회수의 증거를 남기는 것**이다. 모델이 안전하다고 답했거나 원장에 Block만 있다고 통과시키지 않는다.

| 시험 | 통과 조건 | 실패 시 우선 확인·수정 |
| --- | --- | --- |
| E01 정상 읽기 | `Allow/P-AUTHZ-ALLOW-001`, attempted/executed=true, fixture 본문 일치 | registry·계약·역할·경로·MCP 기동·인증 확인. 공급자 quota는 공급자 조건 복구 또는 자체 운영 기준선으로 해결; 정책 완화 금지 |
| E02 결과 PII 마스킹 | `Alert/P-IMPORTANT-ALERT-001`, upstream 실제 실행, 하네스 raw 결과의 합성 PII 제거 | `privacy`/Presidio 한국어 recognizer·decoded 결과 검사·release 경로 수정. 이미 실행된 upstream을 차단 성공으로 표현하지 않음 |
| E03 외부 반출 | `Block/MCP-DATA-EGRESS-001`, attempted/executed=false, sink 수신0 | `classify`·egress·수신자/목적지 정규화·OPA 입력·dispatch 직전 검사를 수정; 실제 외부 전송이 있었다면 실패로 기록 |
| E04 비신뢰 쓰기·승인 | `Approval/P-UNTRUSTED-CONTENT-001`, 승인 전 효과0·인자 digest 결합 | `poisoning`의 provenance/decoded 인자, `agent_contract`의 digest·fresh 인증·권한 재검증. 만료 bearer 허용으로 수정 금지 |
| E05/E06 SSRF·schema | `MCP-EGRESS-002` / `P-INPUT-SCHEMA-001`, tools/call·내부 접속0 | URL/IP/redirect·DNS 재검증, 승인 schema·검증 위치·예외 처리 확인. SSRF fixture는 전용 sink만 사용 |
| E07 계약 drift | refresh 발견 `MCP-CATALOG-001`, dispatch 발견 `P-CONTROL-FAIL-CLOSED`, 실행 수신0 | `refresh_catalog` 최신 snapshot·계약 hash·동시 승인/철회·dispatch 재확인 수정; A→B→A도 포함 |
| E08 PDP 장애 | `Block/P-CONTROL-FAIL-CLOSED`, 실제 효과0 | timeout·예외·fallback을 차단으로 정렬하고 전체 검사 deadline 추가. 공유 OPA를 중단하지 않고 격리 요청 경로에 장애 주입 |
| E09 권한 바인딩 | `Block/MCP-REGISTRY-003`, 공급자 호출0·직원 토큰 전달0 | `caller`/credential binding·principal·audience·scope·조직/자산 교집합·캐시 무효화 수정 |
| E10 동시 중복 | 첫 Allow, 중복 `Block/P-RATE-003`, fixture 실제 수신/효과1 | 예약·정규 인자 digest·DB 잠금/unique·TTL·worker 경쟁 수정. 사망 뒤 uncertain을 보존; 쓰기 자동 재시도로 중복을 만들지 않음 |
| E11 종료·회수 | `Block/MCP-DECOMM-001`, 도구 효과0, 자원 서버의 PAT/세션 재접근 결과와 T상태 일치 | `decommission` adapter·introspection/cache·실제 공급자 철회 수정. 설정 삭제만으로 자격 회수·T1 완료 선언 금지 |
| E12 관리형 입구 | 일반 토큰/heartbeat 만료는 `403/ENDPOINT-MANAGED-001`, active 정상 initialize | 실제 hash·checks·heartbeat·ownership·입구 재검증 수정. 임의 heartbeat/JWT로 시험 대체 금지 |
| E13 직접 로컬 우회 | 관리형 stdio/별도 실행 파일·IPv4/IPv6 localhost의 시도 거부와 독립 수신/효과0, 승인 정상군 성공 | 설치본 launcher/profile 전이·exec 허용·UID nftables·수집기를 수정. 직접 stdio에는 Gateway policy_id를 만들지 않음 |
| 자원 지표 | 관리자 Console scope만 허용, OS 총량·차분·고정 TCP 대상 일치, 오래된 값은 `—` | `system_metrics` 범위·reset/cache/timeout과 화면 freshness 수정. Tailnet ms·jitter·접속 실패율은 별도 endpoint 측정 설계. 연결 실패율을 패킷 손실률로 쓰지 않음 |
| 최신 5개 결함·OAuth | 기존 회귀 및 실제 DB 경쟁3건 유지, 신규 fixture로 카탈로그·결과·원장·목적지 경계 대조 | 실패한 최소 입력→수정 전 재현→해당 함수 수정→정상/음성 회귀→field 배포→PJ1 검증 순서 |

E01~E13의 실제 입력·사전 조건·증거·원복은 [실험 카드](../../experiments/README.md)와 JSON에 저장했다. 이번 보고서 작업은 실행하지 않았으므로 **13개 모두 미실행**을 유지한다. 정책 우선순위가 달라 다른 이유로 차단되면 해당 카드 통과가 아니다.

## 실행 순서와 결과 기록

1. 배포 이미지/정책/계약 hash·실제 MCP 버전·fresh identity·모델/하네스·원상태를 동결한다. 솔루션 기기와 PJ1의 기존 계정·서비스·종료 관계를 초기화하지 않는다.
2. 격리 mock·filesystem·HTTP/mail sink를 독립 승인·등록하고 PJ1에서 E01 정상군을 먼저 성공시킨다. 수신 로그·효과를 기록해 독립 대조를 마련한다.
3. E02~E06과 E09/E12/E13을 진행한다. contract drift·PDP 장애·동시 중복은 전용 대상/격리 요청 경로로 E07/E08/E10을 실행한다.
4. 전용 repo/PAT/이용 관계로 E11 종료 시험을 수행한다. provider별 철회/캐시 차이를 따로 기록한다.
5. 같은 fixture·정상/공격군·enforce 구성으로 비교 솔루션을 시험한다. 기능 존재·활성 구성·실제 효과를 구분하며 동일 실험 전 보안 우위를 주장하지 않는다.
6. `runs/<날짜>/<ID>/report.md`에 하네스 이벤트→MCP 요청→원장 request/trace→독립 수신/효과→원복을 연결한다. 공개본은 비밀 제거 projection과 원본 hash만 보관한다.

부하 시험은 같은 fixture의 동시성·크기·실행 간격을 고정하고 정상 지연 p50/p95, Gateway 추가 지연, CPU·메모리, 오류율·효과 수를 측정한다. 현재 성능 수치를 가정하지 않으며 수집한 기준선과 업무 예산으로 완료 기준을 정한다. 실패 입력을 회귀로 고정한 뒤 해당 경로와 정상 대조군을 재검증한다.

## 이번 문서 변경 검증

| 검사 | 결과·범위 |
| --- | --- |
| 원격 HEAD·branch·diff | 원격 기본2e36095 확인, 새10/13-mcp-validation 생성, 기존 미커밋 파일 보존 |
| 최신 기준 CI | 2e36095의 전체CI 완료·success 재확인 |
| `build_wiki.py`·`check_wiki.py` | Markdown89건·실험13개, 오류0·경고0. 출처/원본 hash·링크·실험 상태 검사 |
| catalog/fixture 대조 | 13개 레코드 동일. 모두 not_run·executed_on/result=null |
| `git diff --check` | 공백 오류 없음 |
| 새 제품 배포·MCP·모델·효과 시험 | 미실행. 이 변경은 팀 규칙·시험 설계·보고서 |

## 현재 증거와 필요한 입력

기존 PJ1 새 세션2개·원장3건은 [JSON](2026-10-13-pj1-evidence.json)에 있다. 740은 Allow 뒤 Context7 quota 응답, 741은 읽기 주입 표지에 Alert 후 실행, 742는 PII 외부 반출 Block·미전송이다. 정상 문서 조회와 별도 수신 trace는 미완료이며 이 표본으로 E01~E13을 통과 처리하지 않았다.

이번에 확인한 것은 Git 브랜치·커밋 diff·최신 CI와 후보/통과 기준 문서다. 새 배포·MCP 프로토콜·모델 호출·효과 시험은 미실행이다. Claude의 지정 모델 분석은 기존 보고서에 보존돼 있고 후속 리뷰는 기존 세션 한도로 미완료다. 이 문서 작성에 Claude를 새로 호출하지 않았다.

로컬 mock·공개 합성 fixture 설계에는 추가 자료가 필요 없다. 원격 쓰기/회수 시험 단계에서는 **팀의 시험 repo·메일함·DB 범위와 공급자 provisioning**이 필요하다. 실제 업무의 대표 정상 요청·목표 지연 예산이 있으면 정상군·성능 기준에 반영한다. 공급자 비밀은 Git이나 대화에 적지 않는다. 팀원은 고정 분석·출처를 읽을 수 있고 재배포 불명확한 전문 원문은 공식 출처에서 별도 확보한다.
