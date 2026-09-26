# 설계 결정 기록 (v2·v3)

> 형식: 결정 · 이유 · 대안과 버린 이유 · 되돌릴 조건. 번호는 다른 문서에서 `D-07`처럼 인용한다.
> 새 결정을 내리면 맨 아래에 추가하고, 뒤집으면 원래 항목에 "→ D-xx로 대체"를 적는다(지우지 않는다).

## D-01 웹에서 MCP를 호출하지 않는다
- **결정**: Console은 관제·승인·계약 검토·종료 판정만 한다. 도구 호출은 사내망 직원 워크스테이션
  컨테이너의 AI 에이전트가 Gateway `/mcp/`로만 한다.
- **이유**: v1은 Console에서 "도구 실행" 버튼을 눌러 호출했는데, 실제 조직에서 MCP를 부르는 것은
  사람이 아니라 직원 PC의 에이전트다. 웹 호출은 통제 지점(Gateway)의 의미를 흐린다.
- **되돌릴 조건**: 없음(요구사항).

## D-02 실제 MCP 서버 10종, 버전 고정
- **결정**: mock/time 서버를 버리고 많이 쓰는 실제 서버 10종(filesystem, git, fetch, memory,
  desktop-commander, postgres-mcp, redis-mcp-server, mcp-email-server, gitea-mcp, @playwright/mcp)을
  이미지 빌드 시 버전 고정으로 설치한다.
- **이유**: 정책·분류·종료 판정이 실제 도구 설명·스키마·부작용에서 검증돼야 한다. 선택 기준은
  (1) 사용량 (2) r/w/x 위험의 다양성 (3) 서버 보유 자격(email, gitea) 유무 — 논문 E3에 필요.
- **되돌릴 조건**: 서버 교체는 `catalog.toml` + `mcp/run-server.sh` + 잠금 갱신으로 한다(→ MCP_SERVERS.md).

## D-03 stdio 서버는 mcp-proxy `--stateless`, 서버 venv의 SDK는 1.x로 고정
- **결정**: stdio 전용 서버는 `mcp-proxy 0.12.0 --stateless`로 Streamable HTTP로 감싼다. 서버별
  venv에 `mcp>=1.17,<2`를 함께 설치한다.
- **이유**: mcp-proxy·postgres-mcp가 MCP SDK 2.x에서 import 단계에 깨졌다. stateless로 두면 Gateway
  연결마다 세션이 새로 생기고 서버 재시작에도 세션 복구 문제가 없다.
- **부작용**: mcp-proxy가 자기 SDK 버전(1.30.0)을 serverInfo.version으로 보고한다. 그래서 잠금의
  `server_version`은 패키지 버전이 아니다. 패키지 버전은 `package` 필드(`pkg@ver`)로 본다.

## D-04 Gateway는 SDK 2.2.0 저수준 Server, 도구 이름은 `<server>__<tool>`
- **결정**: `/mcp/`는 `Server(on_list_tools=…, on_call_tool=…)`. 도구 목록은 DB에서 역할별로
  만든다. 협력사 직원에게는 `r` 도구만 보인다.
- **이유**: 고수준 FastMCP는 도구를 코드로 등록해야 한다. 등록 서버·도구가 데이터(카탈로그)인 이상
  저수준 API가 맞다. 목록에서 w/x를 숨기는 것은 통제가 아니라 소음 제거다(통제는 정책이 한다).

## D-05 레지스트리는 데이터, 계약은 커밋된 잠금 파일 (TOFU 금지)
- **결정**: `registry/catalog.toml`에 승인 서버·도구(r/w/x)·분류 규칙·이용 관계를 두고, 도구
  설명·스키마 해시는 `registry/contracts.lock.json`에 커밋한다. `registry.sync()`는 잠금 파일의
  다이제스트가 바뀌었을 때만 승인 해시를 DB에 반영한다. 광고됐지만 카탈로그에 없는 도구는
  `enabled=false`·행위 x.
- **이유**: 첫 관찰값을 자동 승인(TOFU)하면 처음부터 오염된 서버가 승인본이 된다. 잠금 갱신은
  사람이 diff를 보고 커밋하는 행위여야 한다(`./console.sh contracts --update`).

## D-06 정책은 도구가 아니라 자원을 본다, 모르는 자원은 important
- **결정**: `classify.py`가 인자에서 자원·목적지·DLP 라벨을 뽑고 실효 행위를 승격한다(DDL→x,
  외부 메일→x, 외부 목적지→x). 규칙에 없는 자원은 important.
- **이유**: 같은 `read_text_file`이 공개 공지와 급여표를 모두 읽는다. 도구 단위 정책은 둘 중 하나를
  틀리게 한다. fail-safe 기본값은 분류 누락이 허용으로 새지 않게 한다.

## D-07 LiteLLM → Ollama는 `openai/` 경로
- **결정**: `llm/litellm.yaml`의 모델은 `openai/bob-assistant`, `api_base: http://ollama:11434/v1`.
- **이유**: `ollama_chat/` 경로가 응답의 `tool_calls`를 버렸다(도구 호출이 텍스트로만 옴).
- **되돌릴 조건**: LiteLLM이 ollama_chat의 tool_calls를 보존하는 버전이 확인되면.

## D-08 파생 모델 `bob-assistant` (qwen2.5:1.5b, num_thread 6)
- **결정**: `console.sh up`이 Modelfile로 `bob-assistant`를 만든다. 스레드 수는 `LOCAL_LLM_THREADS`(기본 6).
- **이유**: Intel Ultra 7 255H(하이브리드 P/E 코어)에서 16스레드는 0.5 tok/s, 6스레드는 32 tok/s였다.
  E코어·LP-E코어가 끼면 동기화 비용이 이긴다.

## D-09 작은 모델을 위한 도구 표현
- **결정**: (1) 도구 설명 160자 요약 (2) 의도 힌트로 상위 8개 도구만 제시 (3) 결과는 도구 출력이
  앞, Gateway 메모가 뒤 (4) `<tool_call>` 텍스트 형식도 파싱.
- **이유**: qwen2.5:1.5b는 14개 전체 설명을 주면 호출을 안 했고, 결과 맨 앞의 "[허용·경보 …]"를
  거절로 읽어 "차단됐다"고 답했다.

## D-10 IdP는 agent-service 안의 OAuth 2.0, Gateway는 RFC 9728 + 401 챌린지
- **결정**: password/refresh grant, RFC 8414 메타데이터, RFC 7009 폐기(항상 200), RFC 7662 조사.
  Gateway `/mcp/`는 토큰이 없거나 틀리면 HTTP 401과 `WWW-Authenticate: Bearer resource_metadata=…`.
- **이유**: 논문 E1이 "폐기 응답은 처리만 증명한다"를 실제 표준 엔드포인트로 재현해야 한다.
  401 챌린지가 없으면 표준 MCP 클라이언트가 인가 서버를 찾지 못하고, `initialize`가 성공한 뒤에야
  JSON-RPC 오류로 거절된다(2026-09-24 acceptance가 발견).

## D-11 종료 판정의 분석 단위는 이용 관계, 차단이 먼저
- **결정**: 케이스는 이용 관계(`usage_relationships`)에 연다. 여는 순간 서버 lifecycle이
  TERMINATING이 되고 모든 호출이 `MCP-DECOMM-001`. 회수 대상마다 C1~C4와 등급, 케이스 등급은 최저.
  C4는 "상태를 특정하는 증거"(회수됨이든 아직 있음이든) — 그래서 T2가 가능하다.
- **이유**: 논문 모델 그대로. 회수 후 차단하면 그 사이가 C3의 공백이 된다.
- 자세한 규칙: [TERMINATION_MODEL.md](TERMINATION_MODEL.md).

## D-12 종료 확인 프로브는 "이용"이 아니다
- **결정**: `client.agent = 'termination-probe'`인 판정은 이용 주체 모집단·관계 통계·개요 숫자에서 뺀다
  (`decommission.REAL_CALL`).
- **이유**: 프로브는 그 주체의 이름으로 Gateway를 시험한다. 세면 관리자가 모든 서버의 이용자가 되고,
  케이스를 열 때마다 모집단이 불어난다(2026-09-24 발견).

## D-13 MCP 서비스마다 hostname 고정
- **결정**: compose의 `x-mcp` 앵커에서 `hostname: mcp-<id>`.
- **이유**: desktop-commander가 `start_process` 설명에 `Container: <id>`를 넣는다. 재생성마다
  컨테이너 id가 바뀌어 계약이 DRIFT가 됐다.

## D-14 호스트 포트는 설정값, 기본은 loopback
- **결정**: `CONSOLE_PORT`, `GATEWAY_PORT`, `JAEGER_PORT`, `GITEA_PORT`(.env). 모두 127.0.0.1 바인딩.
- **이유**: 같은 WSL에서 다른 작업 트리의 랩(v1)이 8000/8080을 잡자 v2 컨테이너가 내려갔다.
  서로 멈추게 하는 대신 포트를 나눈다. 이 노트북의 v2는 18000/18080/26686/13000을 쓴다.

## D-15 Console은 빌드 없는 바닐라 ES 모듈
- **결정**: `console.html` + `console.js`(단일 모듈) + `console.css`. 해시 라우팅, `html```
  템플릿이 모든 보간을 이스케이프, 이벤트는 `data-act` 위임, CSP same-origin.
- **이유**: 폐쇄망 배포와 감사가 쉬워야 한다. 번들러·npm 의존이 없고, 감사 행에 공격자가 쓴 문자열
  (프롬프트 주입된 인자)이 들어오므로 기본 이스케이프가 필수다.

## D-16 Gateway 읽기 API도 토큰 필요
- **결정**: `/api/state`·`registry`·`policy/*`·`monitor/summary`·`supply-chain/coverage`·
  `enforcement`·`risk-catalog`는 인증(일부 관리자). 무인증은 `/api/health`와 로그인뿐.
- **이유**: 직원 워크스테이션이 `/mcp/` 때문에 Gateway와 같은 `office` 망에 있다. 프롬프트 주입된
  에이전트가 `curl gateway:8080/api/state`로 전체 감사 기록을 읽을 수 있었다(2026-09-24 수정).
  `tests/open_endpoints.py`가 무인증 목록과 README 문장을 대조한다.

## D-17 승인형 예외는 부여된 승인으로 충족된다
- **결정**: 예외의 effect가 `Approval`이고 `input.approval.granted`면 판정은 Allow(`exception_effect`).
- **이유**: 없으면 승인된 요청을 재판정할 때 예외가 다시 Approval을 내서 **승인해도 영원히 실행되지
  않았다**(EXC-002, 2026-09-24 acceptance가 발견). Rego 테스트 3건 추가.

## D-18 실습 복원은 하위 자격을 되살리지 않는다
- **결정**: `/api/lab/restore/<server>`는 lifecycle·이용 관계만 되돌린다. 종료 케이스가 폐기한
  Gitea 토큰은 `./console.sh restore-token gitea`로 재발급한다(복원 응답의 `follow_up`이 알려 준다).
- **이유**: Gateway가 Docker를 조작하면 안 된다. 실제 조직에서 끊은 관계를 되살리는 것은 새 도입이다.

## D-19 관찰(monitor) 모드
- **결정**: monitor에서는 Allow가 아닌 판정을 `P-MONITOR-001` Allow로 바꿔 실행하고 원래 판정을
  `would_decision`에 남긴다. 단 `core.ALWAYS_ENFORCED` 접두사(`MCP-`, `P-CONTROL-`, `P-INPUT-`,
  `P-RATE-`, `P-CHAIN-` — 레지스트리·계약·SSRF·민감정보 반출·종료·실패 안전·입력·호출량·연쇄 반출)는
  관찰 모드에서도 그대로 집행.
- **이유**: 도입 초기에 "켜면 무엇이 막히는가"를 숫자로 보여 줘야 집행을 켤 수 있다.

## D-20 ~~Presidio는 OPA와 같은 `policy` 망~~ — D-24로 대체
- **대체(2026-09-25)**: 망마다 명시 서브넷을 주면서(D-24) 주소 풀 소진 문제가 사라져, Presidio는 전용 `privacy`
  망으로 돌아갔다. 아래는 당시 기록.
- **결정**: presidio-analyzer·anonymizer는 새 망 없이 `policy`(internal, Gateway·OPA만)에 붙는다.
- **이유**: PDF 통합(cc086e5)은 전용 `privacy` 망을 만들었지만, 이 랩은 이미 망이 11개라 같은 호스트에 랩을
  여러 개 띄우면 Docker 기본 주소 풀이 소진돼 네트워크를 만들 수 없었다(2026-09-25 병합 중 실제 발생).
  `policy` 망의 구성원은 모두 Gateway의 판정 보조(자격 없음, 상태 없음)라 격리 수준이 같다.
- **되돌릴 조건**: 판정 보조 사이의 분리가 필요해지면 전용 망 + 명시 서브넷.

## D-21 PDF 통합 필드는 감사 체인 v6
- **결정**: 정책 입력·위험 점수·개인정보 유형·연쇄 표지를 v2의 v5 뒤에 **v6**로 기록한다.
- **이유**: v1 main이 같은 필드를 자기 "v5"로 추가했고 v2의 v5는 다른 열(서버·자원·목적지·클라이언트·요약)이다.
  두 정의를 모두 허용해 검증하면 한쪽에만 있는 열을 변조한 행이 통과한다. v1 DB는 이관하지 않는다(`reset`).

## D-22 열람→반출 연쇄는 검증된 주체 단위
- **결정**: `P-CHAIN-001` 입력(`sensitive_read_then_send`)은 같은 **사용자 토큰 주체**가 최근
  `CHAIN_WINDOW_MINUTES`(10분) 안에 중요정보 읽기를 실행했고 이번 호출에 외부 목적지가 있을 때 켜진다.
- **이유**: v1은 서명된 Agent 세션 id로 묶었다. v2 워크스테이션의 작업 id(`X-Agent-Task-Id`)는 클라이언트가
  보고하는 값이라 작업을 새로 열면 끊긴다. 주체 단위는 우회할 수 없고, 같은 사람의 정상 업무 몇 건이
  함께 막히는 비용은 "외부 전송" 한정이라 작다. `P-CHAIN-`은 관찰 모드에서도 집행한다.

## D-23 Presidio 엔터티 허용 목록과 이메일 예외
- **결정**: 검사 엔터티를 `EMAIL_ADDRESS`, `KR_RRN`, `KR_PHONE`, `CREDENTIAL`, `CREDIT_CARD`, `IBAN_CODE`,
  `US_SSN`으로 제한하고, 호출의 수신자 주소와 사내 도메인 주소는 세지도 가리지도 않는다.
- **이유**: v2는 실제 도구 출력 전체를 마스킹한다. Presidio 기본 인식기(날짜·인명·장소·URL·IP)를 켜 두면
  git 로그의 날짜와 작성자, 웹 페이지의 링크까지 가려 업무가 불가능하다. 수신자 주소는 반출 내용이 아니라
  목적지이고(그것까지 세면 모든 외부 메일이 차단된다), 동료의 사내 주소는 조직이 스스로에게 숨길 개인정보가 아니다.
- **실패 안전**: 입력 검사 불능 → `P-DATA-INSPECTION-001`(실행 전 차단), 출력 검사 불능 → `MCP-OUTPUT-001`(실행됨·출력 보류).

## D-24 망마다 명시 서브넷, Presidio는 전용 `privacy` 망 (origin/main a14fe13 통합)
- **결정**: 12개 망 전부 `${MCP_NET_PREFIX}.N.0/24`를 명시한다(edge 1 · office 2 · policy 3 · privacy 4 · tools 5 ·
  data 6 · telemetry 7 · model 8 · scanner 9 · corp 10 · ops 11 · internet 12). `MCP_NET_PREFIX`는 처음 실행 때
  `scripts/network_prefix.py`가 다른 Docker 망·호스트 라우트와 겹치지 않는 `10.200`~`10.249`에서 골라 `.env`에
  고정한다(체크아웃 경로 해시가 시작점이라 복제본마다 다르다). presidio-analyzer·anonymizer는 `privacy`(internal)에만
  붙고 그 망에는 gateway·gateway-sse만 들어온다.
- **이유**: 한 호스트에 랩을 여러 벌 띄우면 Docker 기본 풀(/16·/20 단위)이 바닥난다. 명시 /24는 기본 풀을 쓰지
  않으므로 망 수를 줄이려고 격리를 합칠 필요가 없어진다. 정책 엔진과 개인정보 검사기를 한 망에 둘 이유가 없다.
- **검증**: CI `static`이 모든 망의 명시 대역, Presidio의 망 = {privacy}, privacy 망 구성원(Gateway·Presidio만)을 확인.
- **주의**: 이 방식 이전에 만든 스택은 `./console.sh down` 뒤 `up`해야 망이 새 대역으로 다시 만들어진다(볼륨 유지).

## D-25 권한 허용은 배포 데이터 번들, 배포 정책의 식별은 네 파일 묶음 (origin/main a14fe13 통합)
- **결정**: 역할×등급×행위 허용 조합을 Rego 소스(`permissions` 표)에서 `opa/data.json`의 `authorization.grants`로
  옮기고 정책 id를 `P-333-*` → `P-AUTHZ-DENY-001`/`P-AUTHZ-ALLOW-001`로 바꿨다(정책 집합 2.2.0). 번들이 비면 전부
  차단. v2는 `/api/policy/matrix`를 **유지**한다 — 코드에 고정된 표가 아니라 지금 배포된 번들로 OPA에 27칸을 묻는
  결과이기 때문이다(main은 이 API를 지웠다). `/api/policy/ledger`에 `authorization`(번들)을 더했다.
  Gateway가 기동 때 기록하는 배포 정책 버전(`policy_versions`)은 `policy.rego`만이 아니라 `policy.rego`·`data.json`·
  `exceptions.json`·`policy_ledger.json` 묶음의 sha256(`bundle-<12자>`)이다.
- **이유**: 권한이 데이터로 옮겨 가면 Rego 해시만으로는 "무엇이 집행 중인가"를 식별할 수 없다. 번들만 바뀐
  배포가 같은 버전으로 보이면 사후 조사에서 판정 차이를 설명할 수 없다(docs/architecture 제안 D단계의 첫걸음).
- **남은 일**: 이 digest를 감사 행과 재생 결과에 연결하는 것(감사 체인 버전 변경이 필요) — ROADMAP.

## D-26 원격 MCP의 종료 조건은 신청자가 아니라 플랫폼이 증거로 검증 (origin/main a14fe13 통합)
- **결정**: 도입 신청은 저장소·목적만 받는다(종료 조건 필드를 보내면 `StrictModel`이 422). 관리자가
  `PUT /api/mcp-requests/{id}/exit-terms`로 세 조항(제공자 보유 자격 고지·폐기 기록 제출·종료 후 감사 접근)의
  확인 결과와 HTTPS 근거 문서·확인 내용을 기록하고, 원격(HTTP·SSE) 서버는 세 조항이 모두 확인돼야 승인된다.
  `INTAKE_EXIT_TERMS_REQUIRED` 스위치는 없앴다(항상 요구).
- **이유**: 신청자의 체크박스는 "합의했다"는 자기 신고라 종료 시점의 C1(모집단)을 뒷받침하지 못한다. 논문 5.2의
  소급 불가 증거를 도입 때 확보하는 유일한 자리이므로 증거 문서와 검증 주체가 남아야 한다.
- **Console**: 신청 양식의 체크박스를 없애고, 관리자에게 "종료 조건 검증" 대화상자(체크 3개·근거 URL·확인 내용)를
  두었다. 승인 버튼은 서버와 같은 규칙(`termsVerified`)을 만족할 때만 보인다. 보안 회귀가 422·403·409·200을 확인한다.

## D-27 승인된 호출의 최종 상태는 실행 사실을 그대로 (docs/architecture/proposals 반영)
- **결정**: 승인 뒤 재판정·실행 결과로 `approvals.status`를 `EXECUTED`(실행됨) / `NOT_EXECUTED`(전송 전에 멈춤) /
  `UNCONFIRMED`(전송했지만 결과 미확인)로 닫는다. `REJECTED`는 사람의 거부와 무결성 실패에만 쓴다.
  기존 DB는 `v2_tables.sql`이 CHECK 제약을 넓힌다.
- **이유**: 전과 같이 실행되지 않은 모든 경우를 REJECTED로 닫으면 "정책이 막았다"와 "외부 효과가 있었을 수
  있다"가 같은 말이 된다. 후자는 종료 판정의 C3가 세는 미확인 호출과 같은 종류다.

## D-28 활동 로그 상태는 DOM 없는 모듈로 (정원재 0c1736d 통합)
- **결정**: `agent_static/console-state.mjs`(병합·검색·상태 문장)를 `node --test`로 검사한다. 폴링이 페이지 재구성과
  겹쳐도 같은 호출이 두 번 보이지 않고(id로 병합, 세대 번호로 늦은 응답 폐기), 일시정지해도 폴링은 계속해
  "새 판정 N건"을 세며, 실패한 폴링은 조용히 넘기지 않고 "마지막 성공 시각"과 함께 알린다.
  접근성: 본문 건너뛰기 링크, 화면 이동 시 제목으로 초점, 닫힌 드로어는 `inert`, 드로어는 연 요소로 초점 복귀,
  IME 조합 중 Enter 무시, 터치 기기 44px, `prefers-reduced-motion`, `forced-colors`.
- **이유**: main의 콘솔 개편은 v1 화면 구조(웹 도구 실행 포함) 위의 것이라 그대로 가져올 수 없다. 사용자가
  얻는 성질(정확성·접근성)만 v2 화면에 옮겼다.

## D-29 단말 에이전트는 저장소 루트 `endpoint-agent/` 하나 (origin/main ae7ec85 통합)
- **결정**: 실제 PC용 설치 패키지(Linux·Windows 설치기, 장치 키, 1회 보고, 제거)와 랩의 직원 PC가 같은
  `endpoint-agent/agent.py`를 쓴다. 워크스테이션 이미지는 compose `additional_contexts`(`endpoint: ../endpoint-agent`)로
  빌드 때 복사한다.
- **이유**: 랩에서 검증한 에이전트와 배포하는 에이전트가 다르면 랩의 결과가 배포물에 대해 아무것도 말해 주지 않는다.

## D-30 직원 PC는 실제 하네스, 관리형 설정은 레지스트리에서, Gateway는 서버별 엔드포인트 (v3)
- **결정**: 손으로 짠 `office_agent.py`를 지우고 직원 PC 이미지에 Claude Code·Codex CLI·Gemini CLI·OpenCode를 공식 npm
  패키지·고정 버전으로 설치한다. 회사가 더하는 것은 IT 부서가 더하는 것뿐이다 — 관리형 설정(`/etc/claude-code`,
  `/etc/codex`, `/etc/gemini-cli`, `/etc/opencode`), SSO 자격 도우미(`bob-sso`), 단말 에이전트. 관리형 설정은
  `registry/catalog.toml`에서 빌드 때 생성(`workstation/managed/render.py`)하고, 서버마다 Gateway의 `/mcp/<server>/`를
  가리킨다. Gateway는 그 경로를 같은 MCP 앱·같은 판정 경로에 서버 범위로 태운다(`main.ServerPath`).
- **이유**: 통제하려는 것은 "직원이 평소 쓰는 하네스가 MCP 서버를 부르는 통신"이다. 자체 에이전트로는 하네스의 MCP
  클라이언트(세션·전송·도구 이름 규칙·재시도)가 게이트웨이와 맞물리는지 알 수 없다. 서버별 URL이면 직원에게는 서버가
  원래 이름·원래 도구 이름으로 보이고(`mcp__filesystem__read_text_file`), 하네스의 서버 켜고 끄기도 그대로 동작한다.
  설정 네 벌을 손으로 쓰면 서버 하나가 빠지는 일이 생기므로 레지스트리에서 만들고 CI가 대조한다.
- **대안**: 집계 `/mcp/` 하나만 배포 — 도구 166개가 한 서버로 보여 소형 모델이 도구를 부르지 못했고(1.5B, 90초), 직원이
  서버를 골라 켤 수 없다(집계는 호환용으로 남김). TLS 가로채기로 원격 MCP를 투명 프록시 — 사내 CA 배포와 하네스별
  인증서 신뢰 설정이 필요하고, 관리형 설정이 있는 한 얻는 것이 없다.
- **되돌릴 조건**: 하네스가 관리형 MCP 설정을 지원하지 않게 되면 그 하네스는 망 차단 + 단말 인벤토리로만 다룬다.
- D-04의 집계 이름 규칙(`<server>__<tool>`)은 `/mcp/`에만 해당한다.

## D-31 LLM 게이트웨이가 하네스별 API를 번역, 스크립트 모드는 MCP Inspector CLI (v3)
- **결정**: 하네스는 각자 자기 형식으로 LiteLLM에 요청한다(Claude `/v1/messages`, Codex `/v1/responses`, Gemini
  `generateContent`, OpenCode `/v1/chat/completions`). LiteLLM이 전부 `bob-assistant` → Ollama `/v1`로 번역하고
  `reasoning_effort: none`을 붙인다. 모델 없는 결정적 실행(CI·`--no-llm`)은 공식 MCP Inspector CLI가 시나리오의 호출을
  같은 URL·같은 SSO 토큰으로 보낸다. 판정 대조는 하네스 출력이 아니라 직원 토큰으로 읽은 Gateway 활동 기록으로 한다.
  하네스 연결 확인은 각 하네스의 `mcp list`(Codex는 app-server `mcpServerStatus/list`)로 모델 없이 한다.
- **이유**: 형식 번역·가상 키·사용량 귀속은 LLM 게이트웨이의 본업이고 이미 랩에 있다(손코드 대신 오픈소스). 스크립트
  클라이언트를 직접 짜면 그것이 또 하나의 가짜 하네스가 된다. 판정을 Gateway에서 읽으면 네 하네스의 출력 형식 차이가
  시험에 들어오지 않는다.
- **실측**(2026-09-26): Claude Code(4B) filesystem 두 번 호출 후 올바른 요약 146초, Codex(2B) postgres 조회 43초, Gemini
  CLI(2B) fetch 54초, OpenCode(2B) read_text_file → `MCP-SHADOW-001` 65초. qwen3.5 생각 모드를 끄지 않으면 한 턴에 70초가
  더 걸렸다.
- **대안**: 하네스를 Ollama에 직접 연결(Ollama도 Anthropic·Responses API를 낸다) — 직원별 키와 사용량 귀속이 사라지고
  LLM 통제 지점이 없어진다.

## D-32 메모리 예산: Presidio 소형 spaCy, 모델 하나, 기본 2B (v3)
- **결정**: Presidio analyzer는 원본 이미지에 spaCy `en_core_web_sm`만 더한 파생 이미지(`full_stack_lab/privacy/`)를 쓴다.
  Ollama는 모델 하나·요청 하나만 올리고(KV 캐시 q8), 기본 모델은 `qwen3.5:2b-q4_K_M`(12K)이다.
- **이유**: 참조 노트북의 WSL VM은 7.6GB다. 스택 ~3.6GB + qwen3.5:4b@16K(+3.46GB) + Codex 실행에서 VM이 두 번 응답을
  멈췄다(`Wsl/Service/0x8007274c`, `wsl --shutdown`으로만 복구). Gateway가 Presidio에 요청하는 엔터티는 전부 패턴
  인식기라 NER 대형 모델(785MB)이 쓸모없었다 — 소형으로 182MB. 벤치(실제 도구 스키마·한국어 지시 4건): 4B 4/4·첫 턴
  39~148초, 2B 2/4·12~44초(나머지 2건도 탐색 도구·별칭 도구로 합리적 선택), qwen3 4B·granite4·ministral-3 2/4.
- **되돌릴 조건**: 메모리가 넉넉한 호스트에서는 `LOCAL_LLM_MODEL=qwen3.5:4b`, `LOCAL_LLM_CONTEXT=16384`. 사람 이름·주소 같은
  NER 엔터티를 정책에 넣으면 대형 모델로 되돌린다.

## D-33 Console v3: 페이지 내 탭, 차트 우선, 설명 없는 화면 (v3)
- **결정**: 각 화면을 머리·KPI 스트립·페이지 내 탭·차트가 앞선 패널로 나누고, 상세는 탭이 있는 드로어로 연다. 차트는
  Apache ECharts 6.1.0을 내장(`vendor/echarts.min.js`, npm 무결성 대조)하고 `charts.mjs`로 감싼다. 툴팁은
  `renderMode: "richText"`(캔버스). 글꼴은 두 단계 키우고(본문 16px, KPI 36px), 사용법·의의 설명 문단은 UI에서 뺀다.
- **이유**: 한 화면에 표·카드·설명이 모두 있어 읽히지 않았다(사용자 피드백). 레퍼런스(Datadog Cloud SIEM Signals Explorer,
  Elastic Security Alerts·Overview, Tines Cases, Portkey·Langfuse)는 공통으로 KPI → 시계열 → 분포/Top-N, 목록 위 히스토그램,
  측면 패널 안의 탭을 쓴다. 디자인 스킬(anthropics `frontend-design`, vercel `web-design-guidelines`, `ui-ux-pro-max`
  밀도 8·모션 2)의 규칙을 따랐다: 판정 5색만 채도, 숫자 tabular-nums, 색만으로 의미를 싣지 않기(칩에 점+단어), 카드마다
  같은 그림자 금지. 설명은 팀원이 가이드라인 문서로 쓴다.
- **보안**: 감사 로그의 문자열(하네스가 스스로 대는 이름 포함)이 HTML 툴팁의 innerHTML로 들어가지 않게 캔버스 툴팁을 쓴다.
  HTML 툴팁은 인라인 스타일 속성이 필요해 CSP(`style-src 'self'`)에도 걸린다.
- **대안**: 관리자 템플릿(Tabler 등)을 통째로 도입 — 기존 안전 HTML 템플릿·드로어·키보드 동선을 다시 짜야 하고 화면
  어휘가 제품과 무관해진다. 차트만 오픈소스(ECharts)로 가져왔다.

## D-34 하네스 안의 도구 승인은 IT의 사전 승인, 판정은 Gateway (v3)
- **결정**: Claude `permissions.allow: mcp__<server>`, Codex `default_tools_approval_mode = "approve"`, Gemini `trust: true`,
  OpenCode 기본 허용. 소형 CPU 모델에서는 컴팩트 모드(`BOB_HARNESS_COMPACT=1`)로 하네스의 시스템 프롬프트를 짧게 바꾸고
  내장 도구(셸·편집·웹·이미지·서브에이전트)를 하네스 고유 스위치로 끈다.
- **이유**: 하네스와 Gateway가 둘 다 막으면 어디서 막혔는지 기록이 둘로 갈라지고, 헤드리스 실행은 사람 확인을 기다리다
  실패한다(Codex: "MCP tool call requires approval, but approval policy is never"). 셸이 있으면 소형 모델은 MCP 도구 대신
  `psql`을 시도했고, 컨테이너의 bwrap 샌드박스에서 실패하며 40턴을 돌았다. 컴팩트 모드는 모델이 읽는 것을 줄일 뿐 MCP
  경로(하네스의 MCP 클라이언트 → Gateway)는 바꾸지 않는다.
- **되돌릴 조건**: 클라우드 모델을 LiteLLM 뒤에 붙이면 `BOB_HARNESS_COMPACT=0`으로 하네스 본래 동작.

## D-35 협력사에게 숨긴 도구는 시나리오가 아니라 acceptance가 확인 (v3)
- **결정**: 협력사 목록에는 w/x 도구가 없으므로 ws-nkk의 `push-change`(Gitea 파일 수정) 기대 판정을 `[]`로 바꾼다.
  숨긴 도구를 목록 없이 직접 호출해도 판정된다는 것은 acceptance `tool-hidden-from-partner-still-decided`가 확인한다.
- **이유**: 실제 하네스(와 Inspector CLI)는 목록에 없는 도구를 부르지 않는다("tool not found"). 기대값을 Block으로 두면
  하네스가 할 수 없는 행동을 시나리오가 요구하게 된다. 통제가 목록 숨김에 기대지 않는다는 보장은 직접 호출 시험이 맡는다.

> D-36~D-38은 `Proxy` 브랜치(투명 MCP 리버스 프록시)의 결정이라 이 파일에 없다. 번호가 겹치지 않게 비워 둔다.

## D-39 이용 관계의 허용 자원을 평상시 호출에도 적용 — `P-SCOPE-001` 경보 (v3.1)
- **결정**: 서버의 ACTIVE 이용 관계가 허용한 자원(`[[usage_relationships]] allowed_resources`)을 모든 `tools/call`의
  정책 입력 `relationship`(`defined`·`ids`·`in_scope`·`outside`)에 싣는다. 경로·저장소·테이블·메일함 자원이 그 합집합
  밖이면 `P-SCOPE-001`(경고, priority 136)이 성립한다. 경로는 세그먼트 단위 접두어, 이름은 정확히 일치하거나 `sales.*`·
  `bob/*`로 묶는다(`classify.outside_scope`). 메시지·명령·URL처럼 관계가 부여하지 않는 종류와 DB 카탈로그 뷰는 보지 않는다.
- **이유**: LiteLLM MCP 게이트웨이 벤치마킹(BENCHMARK_LITELLM.md)에서 LiteLLM은 키·팀의 허용 서버·도구를 **호출마다**
  평가하는데, 이 저장소의 이용 관계는 종료 케이스를 열 때만 읽혔다(`decommission.py`). 논문의 분석 단위가 평상시 호출에는
  서류로만 있었다.
- **왜 차단이 아니라 경보인가**: `allowed_resources`는 회수 범위를 적으려고 만든 목록이라 소유 부서가 인가 목록으로 검토한
  적이 없다. 곧바로 차단하면 검토되지 않은 목록이 업무를 끊는다. 증적을 먼저 쌓고, 차단 승격은 관리대장의 결정이다(ROADMAP 0번).
  경보는 권한·계약을 충족한 호출에만 붙고 더 강한 판정(차단·승인·제한)을 약하게 만들지 않는다(`test_scope_does_not_weaken_a_block`).
- **호환**: 값이 없는 입력(구버전 Gateway, 정책 재생의 합성 사례)은 판단하지 않는다. 정책 묶음 2.3.0.

## D-40 연결 확인을 계약 재검증과 분리 — `POST /api/registry/{server}/check` (v3.1)
- **결정**: MCP 세션만 협상하고 닫는 확인을 둔다(`upstream.handshake`, 제한 5초 `SERVER_CHECK_TIMEOUT_SECONDS`).
  결과는 `healthy`·`unhealthy`·`retired`와 지연·서버가 밝힌 이름·버전·프로토콜. `tools/list`를 읽지 않고, 계약 상태·
  `mcp_servers.status`·감사 원장을 바꾸지 않는다. 폐기된 서버는 연결하지 않는다. Console 서버 화면의 "연결 확인" 버튼.
- **이유**: LiteLLM은 `health_check_server()`를 도구 조회와 분리해 둔다. 여기서는 "살아 있나"를 알려면 `refresh_catalog`로
  도구 목록 전체를 읽고 계약 상태까지 다시 써야 했다 — 장애 대응 중에 계약 드리프트 판정을 건드리는 것은 부작용이다.
- **대안**: 종료 판정의 `liveness-probe`(HTTP HEAD) 재사용 — 그것은 케이스의 **증거**로 남고 MCP를 말하는지는 보지 않는다.

## D-41 순수 계약 모듈 `contract.py` (v3.1)
- **결정**: `canonical_hash`, OPA 결과 스키마 `POLICY_RESULT`, 감사 체인 열 집합·`audit_fingerprint`를 환경 변수·연결·
  tracing이 없는 `gateway/app/contract.py`로 옮긴다. `core`는 같은 이름을 다시 내보낸다.
- **이유**: `replay`는 해시와 결과 스키마만 필요한데 `core`를 import하면서 tracing을 초기화했고, `registry`는 순환 import를
  피하려고 함수 안에서 `core`를 불렀다(ROADMAP 6절 "순수 계약 모듈"). 감사 체인의 열 집합은 버전별로 고정해야 하는 데이터라
  정책 판정 코드와 같은 파일에 있을 이유가 없다.

## D-42 실기기 배치는 오버레이 하나와 직원 PC 키트로 (v3.1)
- **결정**: 사내망 노출은 `full_stack_lab/compose.field.yaml` + `field/Caddyfile`로만 켠다(`./console.sh field …`,
  내부적으로 `docker compose -f compose.yaml -f compose.field.yaml`). 기본 `compose.yaml`과 `./console.sh up`은 그대로이고,
  CI는 `verify` 끝에서 이 오버레이를 얹어 README의 실기기 절차를 그대로 돌린다. 컨테이너 직원 PC 4대는 오버레이에서만
  `profiles: [lab-workstations]`를 받아 기본으로 꺼진다. 직원 PC에는 `field/pc/mcpgw_pc.py`(표준 라이브러리 한 파일)를 준다.
- **키트의 모양**: 랩의 `bob-sso`와 같은 일(합성 IdP에 password grant로 한 번 로그인, 리프레시 토큰으로 10분 토큰 갱신)을
  Windows에서도 한다 — bob-sso의 `fcntl` 대신 `msvcrt`/`fcntl` 잠금. IdP는 리프레시 토큰을 쓰면 바꾸고 옛 토큰의 재사용을
  계열 폐기로 처리하므로(idp.py), 하네스가 서버 10개에 동시에 헬퍼를 부를 때 갱신이 겹치면 로그인이 풀린다. 잠금 안에서만
  갱신한다. 두 하네스 모두 연결마다 같은 헬퍼 명령을 실행한다(Claude Code `headersHelper`, Codex CLI 0.148+
  `http_headers_helper`, 401이면 다시 부름). 랩의 Codex 설정이 쓰는 `bearer_token_env_var`는 실행 시 한 번 읽어 10분 뒤
  긴 세션이 끊기므로 실기기에서는 쓰지 않았다. Codex는 헬퍼를 환경 변수를 비운 채(`env_clear()`) 실행하므로 토큰 폴더를
  `--home`으로 명령에 싣는다. 이 Windows PC에서 실제 Claude Code 2.1.179·Codex CLI 0.157.1로 확인했다(가짜 IdP·Gateway,
  서버 10개, 만료 뒤 동시 헬퍼 10개에서 갱신 1번·재사용 0번).
- **render.py는 그대로 둔다**: 관리형 설정 네 형식의 원천(D-30)은 이미지 빌드용이고, 키트는 사용자 범위(Claude
  `claude mcp add-json --scope user`, Codex `config.toml` 끝의 표식 블록)에 헬퍼만 쓴다. 서버 목록은 여전히 레지스트리가
  원천이다 — `./console.sh field pc-command`가 `registry/catalog.toml`에서 읽어 직원용 명령을 만든다.
- **한계**: 키트가 보내는 `client_id`(`--workstation`)는 허용 목록으로 검증되지 않는다 — 리프레시 토큰 계열을 나누는
  이름표일 뿐이다. PC 단위 통제는 단말 관측 에이전트의 장치 자격(`field register-pc`, 기존 `POST /api/endpoint/devices`)과
  조직 IdP의 몫이다(ROADMAP 10번). 합성 계정은 첫 기동 때 모두 같은 `MOCK_SSO_PASSWORD`로 심어지므로 사내망에 열 때는
  `field set-password`로 계정마다 바꾼다.

## D-43 사내망 TLS 앞단은 Caddy `tls internal` 하나만 게시 (v3.1)
- **결정**: `field/Caddyfile`의 Caddy(`caddy:2.11.4-alpine`)만 `${APPLIANCE_BIND}:443`에 게시하고, 경로로 Gateway의
  `/mcp/<server>/`·`/api/health`·`/.well-known/oauth-protected-resource`, IdP의 `/oauth/*`, Console을 나눈다. 나머지 서비스는
  여전히 loopback 게시이거나 게시 자체가 없다. `APPLIANCE_BIND`에 기본값을 두지 않아 실수로 모든 인터페이스가 열리지
  않는다. 인증서는 Caddy 자체 사설 CA가 내고, 루트 인증서와 SHA-256 지문만(`./console.sh field ca`) PC에 배포한다.
- **이유**: ROADMAP 9번("사내망 TLS")이 남겨 둔 일이다. 평문 HTTP로 사내망에 여는 모드는 만들지 않았다 — 하네스의 MCP
  베어러 토큰이 그대로 흐른다. Caddy 하나만 게시하면 "무엇이 노출되는가"가 오버레이 한 파일로 답이 되고(D-14와 같은 이유),
  TLS 종료 지점이 하나면 인증서 갱신·CA 배포도 한 곳이다.
- **공개 주소와 내부 주소**: 오버레이는 Gateway·IdP가 PC에 알리는 절대 URL(`IDP_ISSUER`, `GATEWAY_PUBLIC_MCP_URL`)을
  `https://${APPLIANCE_HOST}`로 바꾼다. 그 이름은 컨테이너 안에서 풀리지 않으므로 Gateway가 IdP를 직접 부르는 논문 실험은
  `IDP_INTERNAL_URL`(내부 주소)을 먼저 본다. 토큰의 `iss`는 URL이 아니라 상수라 판정은 바뀌지 않는다.
  MCP 파사드의 DNS 리바인딩 방어(SDK `TransportSecuritySettings`)는 `gateway`·`localhost`만 허용해 Caddy가 넘긴
  `Host: mcp-gw.internal`을 421로 거부했다(CI에서 발견). 허용 목록에 `GATEWAY_PUBLIC_MCP_URL`의 호스트 하나만 더한다 —
  랩 기본값(`gateway:8080`)에서는 목록이 그대로다.
- **대안**: 서비스마다 사내 CA 인증서 — 수명 관리가 서비스 수만큼 생기고 "게시된 것은 하나뿐"이 깨진다. mTLS는 넣지 않았다
  — 자격은 여전히 IdP가 발급하는 OAuth 토큰이 진다.
- **되돌릴 조건**: 조직에 이미 사내망 리버스 프록시·TLS 종료 지점이 있으면 이 Caddy는 그 뒤로 옮기고 Caddyfile은 예시로 남긴다.

## D-44 실기기 기본은 하네스 벤더 로그인, 회사 LLM 게이트웨이는 열지 않음 (v3.1)
- **결정**: 키트의 `setup`은 MCP 서버 등록만 한다 — 랩의 `managed-settings.json`처럼 `ANTHROPIC_BASE_URL`을 강제하거나
  Codex의 `model_provider`를 바꾸지 않는다. 하네스는 각자의 벤더 계정으로 로그인한 그대로 쓰고, 이 배치가 통제하는 것은
  MCP 경로뿐이다. 오버레이는 LiteLLM을 사내망에 게시하지 않고, `field up`은 로컬 LLM도 띄우지 않는다.
- **이유**: 실제 노트북은 이미 그 사람의 Claude 구독이나 회사가 발급한 키로 하네스가 돌고 있을 가능성이 높다. 기본값이
  그것을 덮어쓰면 첫 설치부터 "AI 코딩 도구가 갑자기 다른 모델을 쓴다"는 사고가 생긴다. 거버넌스 대상은 도구 호출이지
  모델 선택이 아니다. 로컬 CPU 모델(D-32)은 실기기 여러 대의 하네스를 받기에 느리기도 하다.
- **되돌릴 조건**: 조직이 사내 LLM 통제(사용량 귀속·키 회수)도 이 배치에서 하기로 정하면, LiteLLM을 같은 Caddy 뒤에
  경로로 붙이고 직원별 가상 키 발급을 키트에 더한다 — 지금은 코드에 없다.
