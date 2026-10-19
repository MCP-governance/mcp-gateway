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
- **현재 상태**: D-46의 Tailscale 전용 HTTP 배치로 대체했다. 아래는 이전 배치의 결정 기록이다.
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

## D-45 도입 신청 자동 검증·종료조건 조사·신청별 보고서
- **결정**: 접수 INSERT에서 `VALIDATION_QUEUED`를 설정한다. 실행과 승인 권한은 분리하며, 실제 Registry 활성화와 원격 종료조건의 관리자 확인은 기존 승인 게이트를 유지한다.
- **자동 조사**: 격리 체크아웃의 문서를 제한된 범위에서 읽어 C1~C4 후보 근거를 수집한다. 근거에는 전체 commit SHA·파일·줄·고정 URL을 남긴다. 키워드 발견은 실제 회수·제공자 계약의 검증이 아니므로 `exit_terms.verified_by`나 T 등급을 자동 작성하지 않는다.
- **증적**: Syft 구성요소 목록, Trivy 설치·수정 버전, Semgrep 발견과 종료조건 조사를 신청별 관리자 보고서로 제공한다. 성공한 검사 결과는 다른 검사 실패 시에도 보존하고, 실패한 검증은 승인 대상이 되지 않는다.
- **파일 접근**: Console에 보고서 볼륨을 읽기 전용으로 마운트한다. 관리자 인증·UUID·보고서 종류 allowlist·신청 증적 귀속으로 다운로드를 제한한다. symlink와 임의 경로를 거부한다.
- **중단 복구**: 도입 검증에도 lease를 둔다. 워커 중단 시 기한 뒤 재예약하며 자동 시도는 3회로 제한한다. 실패·기존 HOLD는 관리자가 재검증할 수 있다.
- **되돌릴 조건**: 검증 예약을 별도 승인 단계로 요구하는 조직에서는 명시적 구성 정책을 도입해야 한다. 검증 예약을 도입 승인으로 간주하지 않는다.

## D-46 실기기 간편 배치는 Tailscale IP에만 게시
- **결정**: `field up`이 `tailscale ip -4`를 읽어 Caddy의 호스트 게시를 그 IP의 443 포트로 제한한다. Caddy는 내부 8080에서 HTTP를 제공하고 Gateway·IdP의 공개 주소는 `http://<Tailscale IP>:443`이다. CI의 `127.0.0.1` 예외만 별도로 허용한다. 일반 LAN IP나 전체 인터페이스로 HTTP를 게시하지 않는다.
- **이유**: 현재 tailnet에서 `tailscale cert`가 인증서 발급을 거절한다. 사설 CA·hosts 배포 없이 같은 tailnet의 관리자·직원이 ID/PW로 접속하도록, Tailscale 터널 암호화와 앱 토큰·역할 판정을 사용한다. 브라우저에는 HTTP로 표시되므로 이 배치는 tailnet 전용이며 일반 LAN/인터넷에는 조직이 신뢰하는 HTTPS 종료 지점을 둔다.
- **신청 표시**: 신청 목록이 비어 있을 때도 폴링한다. 공개 `IDP_ISSUER`와 요청의 실제 origin을 함께 검사하여 Caddy 컨테이너 IP 변경이 로그인·신청 POST를 막지 않게 한다. 다른 origin의 쓰기 요청은 계속 거부한다.
- **운영 단순화**: 새 `.env`에는 DB와 초기 IdP 비밀번호를 임의 생성한다. 기존 `.env`·DB는 건드리지 않는다. 컨테이너 직원 PC를 띄우지 않는 field 기본 배치에서는 가상 PC 등록을 생략한다.

## D-47 A.I.G 코드 감사는 field 기본으로 초경량 로컬 모델 — `qwen3.5:0.8b`
- **결정**: `./console.sh field up`이 [2/5] 단계에서 Ollama를 띄우고 `qwen3.5:0.8b`(Q8, 약 1GB)를 처음 한 번 받아,
  컨텍스트 16K로 고정한 파생 모델 `aig-scanner`를 만든다. `.env`의 `MCP_SCAN_BASE_URL`·`MODEL`·`API_KEY`·`CONTEXT_WINDOW`가 비어
  있을 때만 로컬 값으로 채운다 — 조직이 다른 검사 endpoint를 적어 두었으면 건드리지 않는다. 끄려면 `AIG_LOCAL_MODEL=none`,
  바꾸려면 `AIG_LOCAL_MODEL=<ollama 태그>`. 이제 검증 완료·이상행위(`P-ANOMALY-001`)·정기 재감사가 별도 설정 없이 돈다.
- **고른 과정(솔루션 기기 Ryzen 5 7530U, CPU만)**: 스캐너 저장소의 취약 예제(`mcp-scan/testcase/case1`)로 비교했다.
  | 모델 | 결과 |
  | --- | --- |
  | `qwen3.5:0.8b` | 4분에 완료, 발견 0 |
  | `qwen2.5-coder:1.5b` | 도구 호출 형식을 못 지켜 반복 한도(80회)까지 11분, 발견 0 |
  | `qwen3:1.7b` | 첫 요청이 60초를 넘겨 끊김 |
  `mcp-scan`은 텍스트로 쓴 도구 호출 형식을 모델이 따라야 하고, OpenAI 클라이언트 제한이 요청당 60초다(`utils/llm.py`). CPU에서
  이 둘을 지키며 끝까지 도는 것은 0.8B뿐이었다. 도입 신청(MicrosoftDocs/mcp) 자동 감사는 약 6분, 이상행위로 걸린 재감사도 약 6분이었다.
- **한계(중요)**: 0.8B는 심어 둔 취약점을 찾지 못했다. 파이프라인은 실제로 돌지만 **로컬 소형 모델의 "발견 0"은 안전의 증거가
  아니다**. 화면은 이 경우 "발견 0 · 로컬 소형 모델"로 따로 표시한다. 실제 판단이 필요하면 더 큰 모델(GPU 기기)이나 조직이
  승인한 외부 endpoint를 `.env`에 적는다 — 코드가 그 endpoint로 나간다는 점은 README "운영으로 옮기기 전에"의 경고 그대로다.
- **함께 고친 것**: 워커가 `mcp-scan`에 `DEFAULT_MODEL_CONTEXT_WINDOW`(=`MCP_SCAN_CONTEXT_WINDOW`)를 넘긴다. 없으면 128K로 가정해
  압축하지 않고, Ollama가 넘친 앞부분(시스템 프롬프트)을 조용히 자른다. 또 `mcp-scan`이 기본으로 만드는 thinking·coding·fast 보조
  클라이언트가 OpenRouter를 가리켜서, 같은 로컬 endpoint·모델로 고정했다. 고정 커밋은 이 클라이언트를 부르지 않지만(해당 호출이
  주석 처리돼 있음) 버전을 올리면 저장소 코드가 외부로 나갈 수 있는 경로였다.

## D-48 내부 Gitea의 신원은 솔루션 계정 — Caddy `forward_auth` + Gitea 역방향 프록시 인증
- **결정**: field 배치에서 `/git/*`는 Caddy가 agent-service의 `/auth/gitea`에 먼저 묻는다(`forward_auth`). Console 로그인 때
  같은 토큰을 `/git` 경로 전용 HttpOnly 쿠키(`mcpgw_git`)로도 주고, git 명령은 같은 솔루션 ID/PW를 Basic으로 보낸다.
  통과하면 Gitea 사용자 이름을 `X-WEBAUTH-USER`로 싣고, Gitea는 그 헤더를 Caddy의 고정 IP(`${MCP_NET_PREFIX}.1.250`)에서
  온 것만 믿는다(`REVERSE_PROXY_TRUSTED_PROXIES`). 로그인하지 않은 브라우저는 `/login?next=/git/…`로, git은 401 Basic 요청으로 돌아간다.
- **권한(인가)**: 승인한 저장소는 `mcp` 조직(visibility `limited`, 로그인한 사용자만)으로 가져오고 이슈를 켠다. 직원은 읽기·클론·
  이슈·개인 저장소, 관리자 역할은 Gitea 관리자다(`ensure_gitea_user`가 역할에 맞춰 둔다). 풀 리퀘스트는 끈다 — 저장소는 검증한
  커밋의 사본이고, 고친 코드는 도입 신청을 다시 거친다. 같은 저장소를 다시 승인하면 예전 사본을 덮지 않고 신청 id를 붙인 새 사본을 둔다.
- **순서가 통제다**: Caddy `route` 안에서 ① 클라이언트가 보낸 `X-WEBAUTH-USER` 삭제 ② 인증 ③ `Authorization` 삭제(Gitea가 그 값으로
  따로 로그인하지 않게) ④ 접두어 제거 ⑤ Gitea. Caddy 문서는 인증 응답에 헤더가 없을 때 같은 이름의 클라이언트 헤더를 지우는지
  밝히지 않아 ①을 명시했다(`tests/field_kit_check.py`가 순서를 고정).
- **Gitea 설정**: `REQUIRE_SIGNIN_VIEW`, 자동 가입 끔(agent-service가 만든 사용자만), 비밀번호 로그인 화면·가입 버튼·OpenID·SSH 끔.
  Gitea가 예약한 이름(`user` 등)은 `-mcpgw`를 붙여 매핑하고, 그런 아이디로 가입 신청은 받지 않는다. 가입 아이디는 Gitea 규칙
  (영문·숫자 사이의 기호 하나)을 따른다.
- **이유**: 사용자 요구는 "내부 저장소를 직원이 잘 쓰게"였고, 이전 판은 저장소를 tailnet 전체에 무인증 공개로만 열어 직원이 로그인·
  이슈·클론 인증을 할 수 없었다. OIDC 인가 코드 흐름을 IdP에 새로 짜는 대신 Caddy·Gitea에 이미 있는 기능을 썼다. 계정을 중지하면
  다음 요청부터 Gitea도 막힌다(쿠키 토큰을 매번 관리대장에서 확인).
- **한계**: 쿠키는 Console 토큰과 같은 30분이다. 만료되면 로그인 화면으로 돌아간다. Gitea API의 역방향 프록시 인증은 켜지 않았다(웹과 git만).

## D-49 승인한 서버를 Console에서 Gateway에 등록 — 계약 고정과 사용 기한
- **결정**: 도입 신청이 APPROVED면 관리자가 **Gateway 등록**을 한다: 엔드포인트 → 도구 불러오기(`POST /api/registry/discover`,
  아무것도 기록하지 않음) → 도구별 읽기·쓰기·실행/미승인, 데이터 등급, 사용 기한(30~365일) → 등록(`POST /api/registry/servers`).
  등록은 `REGISTRY_RUNTIME_DIR/servers.json`(named volume)에 카탈로그와 같은 모양으로 남고, `registry.catalog()`는 검토된
  `catalog.toml`과의 합집합이다(이름이 겹치면 파일이 이긴다 — 등록 자체를 거부). `pc-command`·서버별 경로·`tools/list`가 그대로 따라온다.
- **LiteLLM에서 가져온 것 / 가져오지 않은 것**(BENCHMARK_LITELLM.md 4절 1번, 2절 1·22번): 설정 서버와 런타임 서버를 합치는 모양,
  제출→승인 흐름. 가져오지 않은 것은 "승인 뒤 무재검증 신뢰" — 등록 요청은 관리자가 검토한 `catalog_hash`를 싣고, 서버가 지금 말하는
  계약이 그와 다르면 409다(검토와 등록 사이의 변경 차단). 고정한 해시는 이후 매 호출의 계약 재검증에 그대로 쓰인다.
- **BeyondTrust에서 가져온 것**: 기한 있는 접근(요청 → 승인 → 사용 → 만료 → 감사). 기한은 그 서버 도구의 `approval_valid_until`이고,
  지나면 기존 `P-APPROVAL-EXPIRY-001`이 호출을 막는다. 연장은 오늘부터 새 기한이며, 등록·연장·해제 이력은 `servers.json`의
  `history`에 남는다. 해제하면 서버는 DISABLED로 남아 감사 행과 종료 케이스가 그대로 참조된다.
- **신청의 근거를 등록에 싣는다**: GitHub 저장소·검증 커밋(`version` = 커밋, `source_ref` = `github.com/owner/repo@커밋`)·목적·
  종료 조건 확인·신청자 부서. 그래서 이상행위(`P-ANOMALY-001`)나 정기 재감사로 도는 A.I.G 정적 감사가 도입 때 검증한 바로 그
  커밋을 다시 받는다(워커가 `source_ref`의 40자리 커밋을 쓴다). 이용 관계 `UR-<ID>`도 함께 만들어 종료·폐기 절차에 바로 오른다.
- **데이터 등급**: 전용 인자 추출기가 없는 서버는 전에는 모든 호출이 "중요"였다. 등록한 등급을 자원(`service`)으로 싣고, 인자는
  DLP 패턴으로 본다. 모르는 서버는 여전히 중요다.
- **egress**: 정책 데이터의 허용 목록에는 랩 서버만 있어 원격 서버가 전부 `MCP-EGRESS-001`로 막혔다. 관리자가 등록 절차에서 승인한
  **그 엔드포인트 URL**만 허용으로 본다(`core.egress_allowed`). 호스트 전체를 열지 않는다. 사내가 아니면 HTTPS만 등록된다.
- **검증**: `acceptance.console_registration_expires` — 랩 fetch 서버를 다른 id로 등록해 외부망 없이 등록·계약 불일치 409·호출·만료 차단·
  해제 후 404를 본다.

## D-50 종료 조건은 플랫폼이 결론을 낸다 — 규칙 + TypeSafe Jev, A.I.G 모델은 OpenRouter 선택
- **결정**: D-45는 문서 조사까지만 하고 "T 등급을 자동 작성하지 않는다"였다. 그러면 관리자가 매번 제공자 문서를 직접 읽어 세 조건을
  체크해야 했다. 이제 검증 워커가 조건마다 결론(`충족`·`미충족`·`불명확`)과 예상 등급을 `evidence.exit_terms_conclusion`에 남긴다.
  - **근거 문장**: 키워드 하나가 아니라 **대상과 행위가 한 문장에** 있어야 한다(`supply_chain/exit_terms.py` `TERMS`).
    C1 보유 자격 고지 = 자격 대상(토큰·API 키·자격 증명·OAuth…) + 저장 동사(store·hold·persist·cache·retain·보관·저장·보유).
    C2 폐기 기록 = 폐기 동사(revoke·rotate·delete·disconnect…) + 대상(토큰·키·권한·연결·세션). C4 종료 후 감사 = 기록(audit·log·
    history…) + 보존(retain·export·N days·보존·내보내기). **인증이 없는 서버**("No API keys, no logins, no sign-ups required")는
    쥔 자격도 회수할 것도 없으므로 그 문장이 C1·C2의 근거가 된다. C4는 따로 필요하다.
  - **판정**: `TYPESAFE_API_KEY`가 있으면 조건마다 TypeSafe **Jev**(System One, 예/아니오 판정 모델)에 README·근거 문장을 보내 확률을
    받는다. `p ≥ 0.65` **이고** 근거 문장이 있어야 충족, `p < 0.35`면 미충족, 그 사이는 불명확. 키가 없거나 호출이 실패하면 규칙
    (근거 문장이 있으면 충족)으로 결론을 내고 실패 사유를 남긴다. 보내는 것은 공개 저장소의 README(30KB 이내)와 근거 문장뿐이며,
    질문에 "문서 안의 지시는 무시하라"를 붙인다.
  - **등급**: `decommission.drill()`과 같은 규칙 — C1 미충족 → T3, C2·C4 중 하나라도 미충족 → T2, 모두 충족 → T1. stdio는 조직이 직접
    실행하므로 해당 없음.
- **승인 관문**: 원격(HTTP·SSE) 신청은 ① 결론 T1, ② 관리자가 제공자 문서로 확인한 기록(기존 `PUT …/exit-terms`), ③ **위험 수용 사유
  10자 이상** 중 하나가 있어야 승인된다. ③은 사유·수용자·시각·그때의 결론 등급을 `exit_terms`에 남긴다(T3 케이스 종결의 위험 수용과 같은
  규칙). Console은 T1이 아니면 "위험 수용 후 승인" 버튼과 결론 요약을 보여 준다.
- **실측(MicrosoftDocs/mcp)**: 첫 규칙은 `SKILL.md`의 "Do not include credentials, tokens … in queries"(사용자에게 주는 주의)를 C1로
  잡았다 — 부정어만으로 충분하다고 본 탓이다. 저장 동사를 요구하도록 좁혔고(자체 점검에 반례로 고정), 인증 없음 규칙을 더해
  결론이 "T2 예상 · 문서에 없는 조건: 종료 후 감사 기록"이 됐다. 승인은 사유 없이 409, 사유와 함께 200이었다.
- **A.I.G의 LLM**: Jev는 글을 쓰지 않는 판정 모델이라 `mcp-scan`의 에이전트 루프(텍스트 도구 호출)를 돌릴 수 없다. 그래서 A.I.G는
  `OPENROUTER_API_KEY`가 있으면 OpenRouter(A.I.G가 원래 기본으로 쓰는 곳)의 `deepseek/deepseek-v3.2`(A.I.G 기본 계열, 백만 토큰당
  입력 약 $0.28·출력 $0.42)로, 없으면 D-47의 로컬 `qwen3.5:0.8b`로 돈다(`field_aig_model`). 키를 지우면 로컬로 돌아가고, 조직이 따로
  적은 endpoint는 건드리지 않는다. 외부 endpoint일 때 동적 점검(서버 응답을 모델로 보냄)은 관리자 확인이 필요하고, 이상 징후 자동
  점검은 로컬 모델에서만 돈다 — 정적 감사는 공개 저장소 코드만 보낸다.
- **되돌릴 조건**: Jev의 판정이 제공자 문서와 어긋나는 사례가 쌓이면, 관리자 증거 기록(②)이 결론보다 우선하므로 그 경로로 바로잡고
  규칙·질문을 고친다.

## D-51 하네스가 기본으로 붙이는 커넥터는 섀도가 아니라 승인 대상 — 키트 보고 · 관리자 결정 · 하네스 스스로 끄기
- **대체된 부분**: 기본 허용·사용 유예·승인 후 전체 계정 커넥터 허용과 집행 추론은 D-53으로 대체했다. 아래는 이전 결정의 기록이다.
- **문제**: 실제 직원 PC의 `claude mcp list`에는 Gateway 서버 말고도 `claude.ai Notion`·`claude.ai Google Drive` 같은 **계정 커넥터**와
  `plugin:engineering:slack` 같은 플러그인 서버가 나온다. Codex에는 ChatGPT 앱(Slack·Notion·Google Drive…)과 웹 검색·브라우저·
  컴퓨터 조작 같은 기본 기능이 켜져 있다. 모두 Gateway를 거치지 않는다. 엔드포인트 평면은 registered·shadow·retired-residue뿐이라
  이것들을 섀도로 뭉갤 수밖에 없었고, field 직원 PC는 애초에 보고할 길이 없었다(Caddy가 `/api/endpoint/*`를 게시하지 않음).
- **탐지(키트)**: `mcpgw_pc.py report` — setup·doctor 끝에, 그리고 하네스가 연결할 때마다 부르는 `header` 헬퍼가 **6시간에 한 번**
  떼어 내어 돈다(예약 작업을 설치하지 않는다). 읽는 것: `claude mcp list`(JSON 출력이 없어 줄을 읽음, 2.1.283 실측 형식),
  `codex mcp list --json`, `codex app-server`의 `app/installed`(설치된 ChatGPT 앱만 — `app/list`는 앱 디렉터리 전체다),
  `codex features list`, `config.toml`의 `web_search`(기본 `cached`). 직원 토큰으로 `POST /api/pc/inventory`에 보낸다.
  URL은 `scheme://host[:port]`만 보낸다 — 경로에 키를 넣는 MCP URL이 있다. stdio는 명령을 보내지 않는다.
- **분류(서버)**: 결정 단위는 Claude는 **목적지 호스트**(같은 Notion이 계정 커넥터로 오든 플러그인으로 오든 "그 호스트로 보내도
  되는가"), Codex는 앱 id·기능 이름이다. 벤더 자신의 것(`api.anthropic.com` 커넥터, Codex `connector_openai_*` 앱, 기본 기능)은
  **기본 허용**, 제3자 커넥터·앱·플러그인은 **검토 대기**로 시작하고 `CONNECTOR_REVIEW_DAYS`(기본 14일) 안에 결정하지 않으면 거부로
  본다 — BeyondTrust PRA의 "응답 없는 요청은 자동 거부"와 같은 이유(대기가 무기한이면 검토 안 된 외부 전송이 무기한 열린다).
  직접 추가한 서버는 "직접 추가"(섀도)로 표시하고, 정식 경로는 도입 신청이다.
- **결정·강제**: Console 직원·단말 → **하네스 커넥터** 탭에서 승인·거부(사유 필수)·되돌리기. 거부는 하네스가 스스로 끄게 한다.
  - 사용자 범위(키트가 다음 보고 때): Claude Code `~/.claude/settings.json`의 `deniedMcpServers`에 `{"serverUrl": "*://호스트/*"}`와
    벤더가 붙인 이름(`claude.ai …`·`plugin:…`)의 `{"serverName": …}`. 직원이 붙인 이름은 넣지 않는다(같은 이름의 Gateway 서버까지
    막힐 수 있다). Gateway 자신의 호스트는 어떤 경우에도 넣지 않는다. Codex는 키트 블록에 `[apps.<id>] enabled = false`와
    `[features] <기능> = false`. 웹 검색은 루트 키라 파일 끝 블록에 둘 수 없어 관리형으로만 끈다. 키트는 자기가 넣은 항목만 기억해
    바꾸고, uninstall이 지운다.
  - 관리형(IT 배포): Console의 **정책 파일**(`GET /api/connectors/policy`) → `mcpgw_pc.py managed … --connectors connector-policy.json`이
    `managed-settings.json`(`deniedMcpServers`, 승인한 계정 커넥터가 있으면 `allowAllClaudeAiMcps: true` — `managed-mcp.json`은 계정
    커넥터를 모두 끄기 때문)과 `requirements.toml`(`allowed_web_search_modes = ["disabled"]`, `allow_browser_and_computer_use = false`,
    `[features]`, `[apps.<id>] enabled = false`, 기존 `[mcp_servers.*.identity]`)을 만든다. 키는 Claude Code 문서(`managed-mcp`,
    `managed-settings`)와 Codex 소스(`config/src/config_requirements.rs` — 어느 계층이든 `enabled = false`면 최종 false)로 확인했다.
- **우회 탐지**: 거부됐는데 보고에서 여전히 켜져 있으면 "거부 후에도 켜짐"으로 따로 센다(사용자 범위 설정은 직원이 지울 수 있다).
- **한계**: 보고는 키트가 돌 때만 있다(설치·점검·연결 시 6시간 주기). claude.ai 커넥터·ChatGPT 앱의 **호출 내용**은 여전히 Gateway가
  보지 못한다 — 사용량이 필요하면 Claude Code의 OpenTelemetry(`OTEL_LOG_TOOL_DETAILS=1`)가 MCP 서버·도구 이름을 남긴다(미연동).
  Codex `app/installed`는 ChatGPT 로그인이 있어야 답한다.

## D-52 도구 설명의 숨은 지시(tool poisoning)는 등록 때 한 번 더 본다
- **결정**: `POST /api/registry/discover`가 도구마다 `warnings`를 싣는다(`gateway/app/poisoning.py`): 지시 무시("ignore previous
  instructions"), 숨긴 지시 태그(`<IMPORTANT>`·`<SYSTEM>`), 사용자에게 숨김("do not tell the user"), 민감 파일 경로(`~/.ssh`·`id_rsa`·
  `mcp.json`·`.aws/credentials`…), 다른 도구 조종("when … tool … must/always/bcc"), 외부 전송 지시("send … to https://…"), 보이지 않는
  문자(zero-width·bidi·Unicode tag). 이름·설명·입력 스키마(속성 설명 포함)를 본다. 경고가 있는 도구를 고르면 등록 요청에
  `poisoning_ack: true`가 있어야 한다(없으면 409). Console은 경고 칩과 설명 전문, 확인 체크박스를 보여 준다.
- **이유**: 계약 해시(`MCP-CATALOG-001`)는 승인 **뒤** 바뀐 설명을 잡지만, 승인한 설명이 처음부터 깨끗했는지는 말하지 않는다. LiteLLM
  1.104의 `tool_catalog_guard.py`가 같은 문제를 tools/list 시점에 가드레일로 본다(BENCHMARK_GATEWAYS.md). 우리는 승인 절차가 있으니
  승인 시점에 규칙으로 본다 — 모델 없이, 의존성 없이.
- **오탐**: 실험실 서버 도구 222개 설명에서 0건. 공개된 공격 예시(Invariant Labs의 `add` 도구, 메일 조종 도구)와 숨김 문자는 잡는다
  (`python3 gateway/app/poisoning.py`).
- **다음**: 계약 변경(DRIFT) 재승인 화면에도 같은 경고를 보여 준다 — 승인 뒤 설명을 바꾸는 rug pull이 거기서 승인될 수 있다.

## D-53 Gateway 통제 범위를 한정하고 native 정책·집행 증거를 분리
- **문제**: vendor prefix·기본 기능을 자동 신뢰하고 pending을 사용 유예로 취급했다. 커넥터 하나 승인 시 `allowAllClaudeAiMcps`를 켜면 전체 계정 연결이 다시 열린다. 사용자 보고에서 사라졌다는 것만으로 차단 적용을 추론할 수 없고, 현장 PC는 Docker office 망의 egress 격리를 받지 않는다.
- **결정**: 벤더 출처와 무관하게 pending부터 거부 정책 대상. 14일은 검토 기한. 승인은 업무 예외 기록이며 Gateway 전용 프로필을 자동 확장하지 않는다. API와 Console은 `enforcement: unverified`·미관측을 표시한다.
- **native 제약**: PC 키트가 인벤토리 파일 유무와 무관하게 세 파일을 생성한다. Claude는 고정 Gateway MCP, 관리형 allowlist, 계정 커넥터/마켓플레이스 제한. Codex는 name+URL identity의 `requirements.toml`과 Apps·plugins·web/browser 제한. 랩 이미지에도 requirements를 복사한다. 시스템 파일 보호와 지원 버전은 조직 IT 책임이다.
- **시험**: 모형 MCP를 새로 만들지 않고 GitHub·Supabase·Sentry·Notion·Figma·Zapier·Context7의 실제 공식 원격 서버로 opt-in 검사한다. 별도 native 프로필, OAuth, secret-free 결과, 독립 패킷/목적지 관측을 사용한다. 회귀 검사와 실제 서비스/현장 증거를 구분한다.
- **한계와 순서**: [SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md). Desktop/웹·임의 셸/SDK·root/admin·LLM 전송·원격 upstream OAuth는 이 변경의 집행 범위 밖이다. 기존 Gateway·Control Plane·PC 키트와 조직 관리 제품을 연결하며 새 범용 통제 서비스를 만들지 않는다.

## D-54 우회 표기를 판정의 근거로 삼지 않는다 — 주소·SQL·지시문·상한
- **문제**: 통제는 전부 있었지만 넷 다 **입력의 겉모습**을 봤다. 실측(2026-09-30, 운영 중이던 랩 컨테이너):
  `http://0177.0.0.1/`·`http://0x7f.0.0.1/`·`http://169.254.169.254.nip.io/`·`http://corp-db.bob.local/`이 모두
  **external**로 분류돼 `MCP-EGRESS-002`(SSRF)를 지났다. `select * into public.stolen from hr.salaries`와
  `select pg_terminate_backend(…)`·`set_config(…)`는 **r**(읽기)로 분류됐고, 반대로 `select $$; drop table x;$$`는
  문자열 안의 단어 때문에 **x**로 올라가며 없는 테이블 `public.x`를 만들어 냈다. 인자·결과의 주입 검사는
  `core.py`의 짧은 정규식 8개였고 등록 시점의 `poisoning.py`(6규칙+숨김 문자)보다 약했다 — **가장 신뢰할 수 없는
  내용에 가장 약한 검사**가 돌았다. 호출량은 감사표에서 셌는데 그 표에는 끝난 호출만 있어, 같이 도착한 6건이
  서로를 세지 못하고 전부 통과했다(동시 실행 수는 물어볼 수조차 없었다).
- **결정**: 네 가지 모두 "그 입력이 실제로 무엇이 되는가"로 판정한다.
  - **주소**: `classify.host_category()`가 후행 점·대문자, `socket.inet_aton`이 받는 10진·8진·16진·축약 IPv4,
    IPv4-mapped IPv6, 이름 안에 박힌 주소(`nip.io`·`sslip.io`의 점·하이픈 표기), 인프라 호스트의 FQDN,
    `internal_domains` 아래 이름을 모두 infrastructure로 본다. **DNS는 조회하지 않는다** — 조회하면 판정과 실제
    연결 사이에 TOCTOU가 생기고, 조회 자체가 유출 신호가 된다.
  - **SQL**: `pglast`(libpg_query — PostgreSQL 서버와 같은 파서)의 구문 트리로 판정한다. 문장 종류, `SELECT INTO`,
    `COPY … TO PROGRAM`/파일, `EXPLAIN ANALYZE`의 내부 문장, WITH 안의 DML, 바깥에 닿는 함수(파일·대형 객체·
    dblink·설정·세션 종료·sleep)를 본다. 파싱되지 않으면 `x` — 서버가 받지 않을 문장을 "읽기"로 보는 쪽이 위험하다.
  - **지시문**: `poisoning.py` 하나가 계약·인자·결과를 모두 본다. 규칙 묶음은 **결과의 무게에 맞춰** 넓어진다:
    `OVERRIDE_RULES`(결과 보류) ⊂ `INSTRUCTION_RULES`(인자 → 승인/경보) ⊂ `CATALOG_RULES`(계약 → 확인 요구).
    오탐 비용이 다르기 때문이다 — 결과를 막으면 업무가 끊기고, 계약은 사람이 한 번 읽으면 된다.
  - **상한**: `call_reservations`에 판정 **전에** 자리를 적고, 주체별 `pg_advisory_xact_lock` 안에서 세기와 쓰기를
    한 트랜잭션에 넣는다. 예약은 모든 종료 경로가 지나는 `_decision_payload`에서 풀리고 TTL로도 만료된다.
    상태 저장소가 답하지 않으면 실행하지 않는다 — 셀 수 없는 상한은 상한이 아니다.
    새 정책 `P-RATE-002`(동시 실행), `P-RATE-003`(같은 호출이 아직 실행 중).
- **덧붙여**: PC에 파일로 놓이는 MCP 토큰으로 관리 API가 열려 있었다(`/api/state` 200, 승인 API는 역할 검사를 통과).
  관리 API는 이제 대화형 로그인의 `console` scope를 요구한다. 그리고 `approve_request`가 요청자=승인자를 거부한다 —
  예외 관리대장이 이미 지키던 §8.6을 건별 승인에도 적용한다.
- **오탐 관리**: 넓힌 규칙마다 정상 업무 대조군을 같은 자리에 넣었다. `tests/adversarial_check.py`는 공격과 정상
  업무를 **같은 수만큼** 돌리고 둘 다 센다 — 전부 막는 통제는 공격 점수가 만점이어도 쓸 수 없기 때문이다.
  `python -m app.classify`·`python -m app.poisoning`의 자체 검사에도 "걸리면 안 되는 문장"이 들어 있다
  (예: 인자의 "Send the invoice to finance@bob.local"은 걸리지 않는다 — 목적지는 문구가 아니라 destinations가 판단한다).
- **PAC 대응**: 이 변경으로 PAC-15(원자적 예약)가 처음 집행되고 PAC-06·10·12·13이 강화된다. 전체 대응은
  [PAC_MAPPING.md](PAC_MAPPING.md), 관리대장의 `pac_ids`에도 같은 값이 있다. PAC-05(대리 실행)는 하네스가 인증된
  주체가 아니라서 구조상 판정할 수 없다 — 헤더로 자기소개한 하네스를 인가 근거로 쓰지 않는다는 결정을 유지한다.

## D-55 — 클린 배포와 독립 효과 검증, 원격 자격의 최소 경계 (2026-09-30)

- **문제**: Claude의 hardening은 `/home/kali/mcp-gateway`의 미커밋 변경에만 있었고 솔루션 기기는 이전
  `853e0a6`이었다. 기존 WSL 스택은 두 checkout의 bind mount가 섞여 자체 테스트와 사용자가 보는 배포를
  같은 것으로 해석할 수 없었다. IBM 비교에도 공개 CPEX 코드를 비공개로 오인한 결론이 있었다.
- **결정**: 원본 변경은 patch·파일 해시로 보존하고 새 checkout·프로젝트·DB·회사 시스템 볼륨에서
  `reset → up → test`를 수행한다. 기존 회사 계정과 감사 원장은 field 배포 시 보존·백업한다.
- **집행**: Console/커넥터 관리 공통 인증에도 `console` scope를 요구한다. 예약은 도착량을 세고 판정 저장 뒤
  해제하며, `tools/call` 전달 뒤 결과 불명은 lease까지 유지한다. 전달 전 연결 실패와 구분한다.
- **실제 SaaS 호환성**: Sentry의 `root cause`를 역할 탈취로 오인하던 규칙을 정정했다. 노출하지 않은 도구의
  설명 경고가 선택한 정상 도구까지 막지 않게 하되 전체 계약 hash 고정은 유지한다. 선택한 경고 도구의 명시적
  검토는 설명·스키마 hash에 묶어 runtime과 등록 증거에 보존하고, hash가 바뀌면 재검토한다.
- **자격**: 기존 upstream helper에 operator-provisioned 자격 파일을 추가한다. exact HTTPS resource,
  등록 주체, 초 단위 만료, 파일 권한을 검증한다. 사용자 SSO는 전달하지 않는다. 자동 OAuth 수명주기나
  표준 위임을 구현했다고 주장하지 않는다.
- **증거**: 실제 DB 잠금을 유지한 동시·중복 쓰기는 별도 DB 변화로 대조한다. 실제 일곱 벤더 MCP를
  native 하네스와 SDK로 시험하고, VM 호스트 SYN 관측 및 독립 internal network 시험을 분리 기록한다.
  managed 연결 목록에서 사라진 결과를 전체 egress 차단으로 바꾸어 쓰지 않는다.
- **배포**: health/readiness와 Console `정책 → 배포 확인`에 code revision/hash·OPA의 로드 정책 일치를 표시한다.
  이 일치는 해당 서비스의 배포 증거이며 단말 전체의 강제성·공급자 권한 폐기를 뜻하지 않는다.
- **문서**: [검증 보고서](OVERHAUL_VALIDATION_2026-09-30.md), [IBM 정정본](BENCHMARK_IBM_CONTEXTFORGE.md),
  [Microsoft 정정본](BENCHMARK_MICROSOFT.md). 이전 수치 중 재검증하지 않은 것은 확정 근거에서 제외한다.

## D-56 판정의 기준을 손으로 쓴 목록이 아니라 원천에서 가져온다 (2026-10-01)

- **문제**(D-54·D-55 뒤의 실측): (1) SQL의 "검토한 함수" 40개 허용목록은 평범한 분석 쿼리 40개 중 25개를 `x`로
  올렸다 — `extract`, `row_number() over`, `lag`, `split_part`, `percentile_cont`, `generate_series` …. 직원에게 `x`는
  차단이므로 규칙이 업무를 막고 있었다. (2) 발급자 접두어가 있는 토큰 9종(GitHub·Slack·Google·OpenAI·Anthropic·
  Stripe·GitLab·JWT·AWS 비밀 키)이 DLP 라벨을 받지 못해 GitHub 토큰을 외부 메일로 보내도 통과했다. Presidio의
  주민번호 인식기는 하이픈을 요구해, 하이픈 없는 번호는 분류기가 라벨을 붙이고도 결과 마스킹을 지나쳤다.
  (3) 배포 확인의 정책 일치는 `policy.rego`만 비교해 권한 번들·관리대장·예외가 OPA에 반영되지 않은 상태를
  "일치"로 보였다.
- **결정**:
  - SQL 함수는 **서버의 카탈로그**로 판정한다. PostgreSQL 18.6 `pg_proc`의 `pg_catalog` 함수 2,787개와 변동성을
    `gateway/app/pg_builtin_functions.json`으로 두고(생성 쿼리는 `classify.PG_FUNCTIONS_QUERY`), 불변·안정은 읽기,
    휘발성은 읽기 전용으로 확인한 26개 외 `x`, 내장이 아니거나 사용자 스키마의 함수는 `x`. D-55의 안전 성질(사용자
    정의 함수 → `x`)은 그대로이고 같은 40개 쿼리의 오판은 25 → 0이다.
  - 자격 증명은 **발급자가 문서화한 접두어**로 본다(`classify.SECRET_PATTERNS`, IBM CPEX `secrets_detection`의
    접두어형 규칙 + OpenAI/LiteLLM `sk-`·Anthropic·GitLab). 같은 문자열을 DLP 라벨(`P-DLP-001`)과 Presidio
    `SECRET_TOKEN`(결과 마스킹·`MCP-DATA-EGRESS-001`)이 함께 쓴다. CPEX의 일반 hex·base64 규칙은 커밋 해시와
    SHA-256을 매번 잡으므로 차단 근거로 쓰지 않는다. 주민번호는 두 곳이 같은 모양(생년월일 검증, 하이픈 선택)을 쓴다.
  - 정책 일치는 **OPA가 실제로 쓰는 네 파일 모두**를 본다: 규칙 해시와 `data.json`·`exceptions.json`·
    `policy_ledger.json`의 최상위 문서를 OPA가 서빙하는 값과 정규 JSON으로 대조한다. 데이터만 바꾸고 OPA를 다시
    읽히지 않으면 `not_ready`가 된다(실측: 한도 값 하나를 바꾸자 즉시 불일치, 되돌리자 일치).
- **재현 가능성**: D-55가 확정 근거에서 뺀 두 수치를 다시 잴 수 있게 했다. 주입 탐지율은
  `tests/injection_corpus_check.py`가 PyRIT 고정 커밋의 garak 시드를 받아 잰다(지시 주입 26건 중 21건).
  팀원 PAC-15 초안의 검토는 [research/pac15-review](../../research/pac15-review/README.md)의 `run.sh` 한 번으로
  원본(정상 200/200·결함 59)과 결함 7종을 고친 수정본(200/200·0)을 나란히 낸다.
- **시험**: 적대적 회귀에 자격 증명 유출 4건(메일·URL, GitHub·Slack·`sk-`·JWT)과 정상 대조 2건(커밋 해시·SHA-256이
  든 사내 메일, `extract`+창 함수 쿼리)을 더해 공격 42/42·정상 16/16. `python -m app.classify`에 카탈로그 판정과
  자격 증명 11종·정상 문자열 6종의 대조를 넣었다.
- **실제 LLM 하네스**: Codex CLI 0.158(`gpt-6-luna`)과 Claude Code 2.1.283(`claude-sonnet-5-5`), effort medium으로
  솔루션 기기의 게이트웨이를 거쳐 업무 5건씩 — 10회 모두 게이트웨이 경유, 4건 허용·권한 밖 수정 2건 실행 전 차단,
  DB 값 불변을 독립 확인. 내장 셸이 켜진 Codex는 MCP 대신 셸로 `git`을 시도했다 — 관리형 설정이 셸을 끄는 근거.
  기록은 [FOLLOWUP_VALIDATION_2026-10-01.md](FOLLOWUP_VALIDATION_2026-10-01.md).

## D-57 원격 도입도 실제 신청과 독립 승인에 묶는다 (2026-10-01)

- 미등록 MCP 초기화는 HTTP 404로 막혔지만 `tools/call` 원장을 거치지 않았다. 인증된 실제 연결 거부를
  `event_kind=mcp-connection`, `action=connect`, `MCP-REGISTRY-001`로 append-only 원장에 기록한다.
  이를 도구 실행으로 세지 않는다. 무인증은 기존 401 경계를 유지한다.
- 호스팅 서비스의 구현 소스가 공개되지 않은 경우 GitHub 문서 저장소 검사로 서비스를 검증했다고 하지 않는다.
  `remote-endpoint` 신청은 실제 Gateway 브로커로 조회한 endpoint·광고 계약·선택한 도구·주체·기한을 검토한다.
  Console이 MCP에 직접 연결하지 않는다. 현재 지원 전송은 Streamable HTTP이며 SSE를 검증한 것처럼 승인하지 않는다.
- 신청자와 승인자는 달라야 한다. 승인한 검토 digest·endpoint·도구·등급·기한은 등록 시 공통 경계에서 다시 검증한다.
  주체 범위를 관리자도 우회하지 않는다. 계약 갱신·기한 연장은 새로운 도입 검토·승인을 요구한다.
  동시 검토와 승인은 원래 evidence와의 CAS로 오래된 검토를 승인하지 못하게 한다.
- 단말 설정이 `/mcp/<아무 이름>/`을 가리킨다는 사실만으로 등록 사용이 되지 않는다.
  실제 운영 중 READY 서버 ID와 일치해야 한다. 알 수 없거나 비활성 경로는 승인 사용으로 세지 않는다.
- 시험: 별도 WSL2 checkout·신규 Compose 네트워크·빈 볼륨에서 전체 필수 검증 통과(phase2).
  기존 실기기의 임시 등록 7개와 과거 200건은 보존·비활성화하고, 소급 승인 기록을 만들지 않는다.

## D-58 운영 UI는 판정과 실행을 구분하고 가입은 1회용 조직 초대로 줄인다 (2026-10-01)

- MS·IBM·LiteLLM 고정 소스 분석은 [UI·가입 비교](BENCHMARK_UI_ONBOARDING_2026-10-01.md)에 보존한다.
  상단 검색·접는 메뉴, 서비스별 검토 범위, 일반 사용자 초대를 채택한다. UI 프레임워크 전체 이식은 하지 않는다.
- 개요·로그는 도구 호출과 연결 거부를 구분하고 upstream 실행·미전송·미확인을 따로 표시한다.
  허용 판정 수를 실제 공급자 실행 수로 쓰지 않는다.
- 초대는 관리자 Console 자격으로 발급·회수하며 아이디·부서·48시간·1회로 제한한다. 비밀은 해시만 저장한다.
  초대 수락과 계정 생성은 하나의 DB 트랜잭션이고 역할은 서버가 employee로 고정한다.
  링크는 발급 때만 보여주며 이메일 발송은 수행하지 않는다. 외부 IdP SSO가 구현된 것으로 표시하지 않는다.

## D-59 fa70b95 검수: 연결 거부는 호출이 아니고, 신청 없는 등록은 실행되지 않는다 (2026-10-01)

독립 검토 2건(서버 경계, 문서 대 코드·실기기)과 실기기 DB 실측으로 확인한 결함을 공통 경계에서 고쳤다.

- **연결 거부가 호출 한도를 소모**: 연결 거부 행이 `data_class=important`·예약 없이 기록되어 `_reserve_call`의
  호출 수·중요정보 폭주·차단 연속에 합산됐다. 실기기에서 04:43에 호출 몇 건 만에 `P-VOLUME-001` 승인 요구가 난
  원인이다. 이제 `action='connect'` 행은 세 집계에서 빠지고 등급은 `public`이다. 같은 주체·경로는 1분에 1행,
  주체당 1분 20행을 넘으면 기록 없이 404만 준다(행마다 `audit_chain` 잠금을 잡으므로 상한이 없으면 한 토큰이 모든
  판정 기록을 늦춘다). 깊게 중첩된 본문도 500 대신 거부 기록이 남는다.
- **신청 없는 등록이 열려 있음**: D-57의 방어는 `intake_id`·`allowed_principals`가 있을 때만 걸려, 그 전의 직접
  등록(실기기 `context7`·`figma`·`supabase`·`notion`·`zapier`, 신청 0건)은 전원에게 열려 있었고 관리자 혼자 기한을
  늘릴 수 있었다. `registry.allowed_principals()` 한 곳에서 신청 없는 Console 등록을 `[]`(아무도 못 씀)로 판단해
  `MCP-REGISTRY-003`으로 막고 목록에서 숨긴다. 제자리 기한 연장 API·버튼은 없앴고(새 신청), `approve_contract`도
  Console 등록에는 쓰지 않는다. catalog.toml의 검토 서버는 그대로 정책 범위다.
- **저장소 도입이 신청자 1인용으로 바뀜**: 원격 서비스만 계약 검토의 주체 목록을 쓴다. 소스를 검증한 저장소 도입은
  D-57 이전처럼 정책 범위다. 계약 검토는 로그인 아이디와 주체 토큰을 모두 받아 토큰으로 저장한다(화면 문구와 일치).
- **등록**: 승인 1건은 등록 1개이고, 다른 신청이 운영 중인 서버 id를 덮어쓰지 않는다.
- **그 밖**: 종료 판정의 이용 주체 집계(`TOOL_CALL`)에서 연결 거부를 뺐다. 계약 불일치·오류·대기 상태의 등록 서버를
  가리키는 Gateway 경로는 섀도가 아니다(해제된 서버·알 수 없는 id는 여전히 미등록 설정). `REMOTE_REVIEWED`에서도
  종료 조건 증거를 기록한다. 초대 수락 성공은 가입 시도 한도에서 뺀다. 개요 KPI 링크는 필터 전체를 바꾸고, 상단
  검색은 "최근 활동 200건"이라고 쓴다. 대시보드의 "오늘"은 KST 자정부터다(전에는 UTC라 09:00에 0이 됐다).
- **배포**: OPA는 시작할 때만 `./opa`를 읽고 Gateway는 부팅 때 관리대장을 캐시한다. `field up`·`up`이 opa·gateway·
  gateway-sse를 다시 만든다. fa70b95 실기기 배포는 gateway·agent-service만 다시 빌드해 `MCP-REGISTRY-003`이 OPA
  관리대장에 없었다.
- **시험**: 공허하게 통과하던 인수 검사를 바꿨다 — 직접 등록 409는 "도입 신청" 사유를 확인하고, 초대 재사용은
  아이디를 비운 뒤 1회 소비 자체와 48시간을 확인한다. 자기 승인 403, 연결 거부 1분 1건, 연결 거부가 한도에 들어가지
  않음을 더했다. 깨진 opt-in 실서비스 시험 2개는 `tests/intake_register.py`(신청 → 검토 → 다른 사람의 승인 →
  활성화)를 쓴다. Codex OAuth 설정 키(`mcp_oauth_credentials_store`)를 시험 프로필 생성기에도 반영했다.
- **PC 키트**(pj1 실측): Codex 서버 항목에 `default_tools_approval_mode = "approve"`가 없어, 실제 PC의 Codex는 MCP
  호출마다 승인을 묻고 `codex exec`에서는 게이트웨이에 닿기 전에 스스로 거절했다(원장 0건, 답변 "승인 정책에 의해
  차단"). 랩 관리형 설정(`render.py`)과 같게 판정을 게이트웨이에 맡긴다. `claude`가 PATH에 없으면(공식 설치 위치
  `~/.local/bin`, SSH·스크립트 같은 비로그인 셸) Claude 등록을 건너뛰던 것을 그 위치까지 찾게 했다.
- **실기기 실측**([PJ1_SIGNALS_2026-10-01.md](PJ1_SIGNALS_2026-10-01.md)): 직렬화 64KB를 넘는 인자는 보내기 전에
  `P-INPUT-SCHEMA-001`(200KB가 외부 공급자까지 갔다). Presidio 요청은 게이트웨이에서 2건씩 줄 세우고 제한 20초
  (동시 6건에서 8초를 넘겨 공개 결과가 fail-closed로 버려졌다).
- **남은 것**: Codex 테스트보드(`mcpgw-remaster-20261001`)의 미커밋 PAC 통합·단말 집행 작업(49개 파일, 업무 시나리오
  3건 실패)은 검토·통합 전이다. 커밋된 fa70b95만 이 결정의 대상이다.

## D-60 팀원 공격 수정 PAC15를 실행 인가로 통합 (2026-10-01)

- D-54 하드닝과 D-59 등록 경계를 보존하면서 팀원 수정본 PAC15를 실제 OPA 후보에 연결한다.
  `INPUT_CONTRACT`·`POLICY_BUNDLE`도 실행을 막는다. 원본과 공격 검토 사본은 변경하지 않는다.
- D-25 역할×등급×행위 권한과 EXC-001·002 완화를 종료한다. 명시적 capability 또는 독립 승인된
  원격 신청의 주체·도구별 인자 스키마·기한이 권한 근거다. 관리자 역할도 범위를 우회하지 않는다.
- 실제 검증 claims·현재 DB·검토 registry로 사실을 만든다. clientInfo는 앱 신원 증명이 아니다.
  승인 다이제스트에 검토된 전체 scope 해시를 포함하고, 재실행 nonce·내용·승인자·폐기를 재검사한다.
- 계약과 PAC를 같은 upstream 세션에서 다시 검사하고 조건 변화는 call_tool 전에 차단한다.
  과거 승인에 없는 인자 범위를 자동 생성하지 않는다. PAC·계약 실패는 예외/monitor로 실행하지 않는다.
- 신규 빈 볼륨 테스트보드에서 제품 PAC 모듈 정상 200/200·탐색 100/100, Rego 99건,
  인수 23건, 동시·중복 예약의 독립 DB 효과, 네 하네스·네 사용자 연결과 업무 시나리오를 확인했다.
  전체 시험 종료 및 실제 배포 증거는 런타임 통합 문서에 별도로 기록한다.
- 로컬 공급자 MCP 세 종류의 직접 실행 증거와 Gateway 통제 증거는 별개다.
  엔드포인트 커널 통제는 비관리자 Linux 범위이며 Windows·관리자 우회까지 증명하지 않는다.

D-60 검증 완료: 클린 보드 전체 시험 exit 0(Rego 99·인수 23·보안 회귀 55·공격 42/정상 16·E1~E3).
실기기 PAC15 적재와 PJ1 실제 GitHub 커밋 반환 2건·PAC-01 미전송 2건은
[PAC 런타임 통합](PAC_RUNTIME_2026-10-01.md)의 384~387 원장 근거를 따른다.
정책 화면의 원격 승인 범위 수와 운영 bundle 이름 표시도 실제 배포 파일 기준으로 정정한다.

## D-61 가입을 관리형 단말 연결의 시작점으로 (2026-10-01)

- **문제**: 사용자 범위 설정 파일과 password/refresh grant만으로는 단말 집행을 확인할 수 없다.
  D-42·D-51의 비관리 키트는 관측·랩용으로 남기고, field 일반 계정의 실행 인증은 새 경로로 전환한다.
- **등록**: 가입 승인·초대 수락 계정은 `managed_required=true`. 인증된 Console ZIP에는 가입자에 결합한
  30분·1회용 grant를 넣는다. DB에는 해시만 저장하고 소비와 장치 생성을 같은 트랜잭션으로 처리한다.
  OS 관리자가 검증한 설치기는 키를 생성하고 장치를 pending으로 등록한다. 서버가 UID를 스스로 확인한 것처럼 표현하지 않는다.
- **집행**: 기존 장치-key 평면과 Linux AppArmor/nft 집행기를 재사용한다. root 소유 고정 하네스·헬퍼,
  레지스트리 렌더링 시스템 설정 4개, UID의 Gateway 전용 IP 경로, root 정책 서비스와 UID 검사 Unix 소켓을 설치한다.
  장기 키는 root 600, 직원에게는 5분 MCP JWT만 전달한다. 하네스·MCP 제공자 소스는 수정하지 않는다.
- **활성화**: 정상 보고가 있어도 자동 활성화하지 않는다. 독립 Console 관리자가 실제 호스트 집행을 확인하고
  최근 180초 보고·정확한 정책 해시를 비교해 활성화한다. 자체 보고는 root/하드웨어 원격 attestation이 아니다.
- **회수**: 미등록·pending·격리·폐기·180초 보고 만료·정책 변경은 인증과 upstream 직전에서 차단한다.
  이미 발급된 JWT도 현재 DB 상태를 확인한다. password/refresh·Console scope·장치 key 재발급으로 이 조건을 우회하지 못한다.
  60초 정책 주기로 실제 커널 규칙과 보호 파일 해시를 확인한다. 정상 보고만으로 격리를 해제하지 않는다.
- **감사**: `ENDPOINT-MANAGED-001`. 가입 키트·장치 활성화·인증 거부 이력과 실제 kernel deny를 도구 판정 원장과 구분한다.
  Claude의 헬퍼 socketpair 통신과 Codex의 sh→dash 실행만 OS 프로필에 제한적으로 허용했다.
  field의 401 discovery URL이 내부 `gateway:8080`을 노출하던 설정도 공개 주소로 바로잡았다.
- **증거**: 가입/동시 1회 소비/만료/pending/자기 승인/폐기는 실제 IdP·DB 검사로,
  커널 차단·heartbeat 만료·설정 격리·미만료 JWT 폐기는 PJ1 일반 UID의 실측으로 검증한다.
  공식 native Codex 0.158.0·Claude 2.1.282가 관리 설정으로 공식 원격 GitHub `list_commits`를 호출했다(389·390).
  이는 모델 턴 없는 native 도구 호출이다. 합성 공급자나 변조 MCP를 실측 증거로 세지 않는다.
- **한계**: Linux SSH 일반 계정 + UID IP egress. Windows/다른 로그인 경로/root·커널 침해는 미검증.
  LLM 전송은 승인된 사내 모델 프록시 경로가 필요하다. 공급자 OAuth와 종료 C1~C4/T1~T3는 기존 모델을 그대로 따른다.

## D-62 강제한 주체와 관찰한 주체를 나누고, 응답 보류를 실행 여부와 같이 기록한다 (2026-10-01)

- **문제**: 통제 상태가 `enforcement: unverified` 하나뿐이라 Gateway·Endpoint·Vendor 중 누가 강제했는지,
  관찰만 했는지, 우회 가능한지를 화면·API가 구분하지 못했다. 관리형 단말의 다른 관리자 계정(PJ1 `pj1`,
  sudo·docker)도 표시되지 않았다. 응답은 text 밖의 형식(image·resource·embedded)이 JSON 문자열로 잘려 하네스에
  전달됐고, 처리 결과(반환·마스킹·보류)는 사유 문장에만 있었으며, 감사 `result_preview.head`에 응답 원문 200자가
  남았다. 공급자 호스팅 MCP의 읽기 인자는 PII 검사를 건너뛰었다. 예외·관찰 모드는 *선택된* 정책 ID만 보고
  완화해, conflicts에 남은 PAC 거부·승인을 지울 수 있었다(현재 적용 중인 예외는 없어 잠재 결함).
- **통제면 모델**(`integrations.py`, `GET /api/integrations`): Registry·키트 보고·단말 설정·리스너를
  `gateway_mcp`·`gateway_backend_connector`·`vendor_native_connector`·`local_plugin_or_stdio`·`shadow_or_unknown`으로
  나누고, 항목마다 발견 위치·시각, 소유자·단말·하네스, 출처, 관리 주체, 실제 강제 여부, 승인·만료, 우회 경로,
  마지막 확인 시각을 계산한다. 상태는 `gateway_enforced`·`endpoint_enforced`·`vendor_enforced`·`observed_only`·
  `unknown_not_enrolled`·`bypass_possible`. 저장된 판단이 아니라 현재 원장·장치 보고에서 매번 계산한다.
- **Endpoint 강제의 조건**: Linux 관리형 장치, 180초 안의 heartbeat, AppArmor·UID nft·보호 설정 네 검사가 모두 참.
  같은 단말의 다른 로그인 계정(관리자 그룹 포함), 다른 계정을 보고하지 않은 구버전 에이전트, Windows·WSL은
  `bypass_possible`로 표시하고 관리 계정의 커널 강제 사실은 `account_state`로 따로 남긴다. 에이전트는 heartbeat에
  `host`(커널·WSL 여부·다른 계정과 특권 그룹)를 보고한다. 이 보고는 준수 판정(격리)에 쓰지 않는다.
- **Vendor 통제**: 벤더 관리 콘솔 상태는 이 저장소가 가져오지 못한다. 관리자가 본 콘솔 상태·허용 action·OAuth
  scope·역할 접근을 `PUT /api/integrations/vendor-control`로 기록하면 `vendor_enforced(수기 확인)`로만 표시한다.
  Gateway 차단으로 표시하지 않는다.
- **응답 통제**: 결과 content는 `text`만 반환한다. 다른 형식, MCP 구조가 아닌 결과, 크기 초과, 지시문 표지,
  마스킹 실패는 실행 후 보류(`MCP-OUTPUT-001`, `upstream_executed=true`)다. 감사에는 응답 대신
  `{disposition, sha256, bytes, content_types, structured, masked_types}`만 남긴다(`result_preview` 열을 재사용).
  하네스 `_meta.gateway`와 활동 API에 `response_disposition`·`response_withheld`를 싣고, 보류 응답 문구와 화면에
  "이미 실행된 쓰기·전송은 되돌리지 않는다"를 표시한다.
- **공급자 호스팅 인자**: registry endpoint가 외부 host면 읽기 인자도 Presidio 검사를 거치고, 탐지 PII는
  `MCP-DATA-EGRESS-001`로 실행 전에 막는다. 서버의 데이터 등급은 돌아오는 데이터의 등급이라 이 조건에 쓰지 않는다.
- **PAC 보존**: PAC 결과가 하나라도 있으면 예외를 적용하지 않는다. 관찰 모드도 conflicts에 항상 집행 정책
  (PAC·MCP·INPUT_CONTRACT 등)이 있으면 완화하지 않는다. 활동 상세에 PAC 실패 목록과 conflicts를 함께 보인다.
- **판정 근거 원칙**: 차단 근거는 transport 신원·등록·계약 해시·승인 범위·예약 상태·커널 규칙 같은 재현 가능한
  사실이다. 지시문 표지는 실행 판정에서 승인 요청·경보로만 쓰고(P-UNTRUSTED-CONTENT-001/002), 응답에서는
  반환 보류로만 쓴다. 호출의 허용·차단에 LLM 판단을 쓰지 않는다(A.I.G·Jev는 도입 검토 보조 자료다).
- **한계**: 응답 보류는 이미 일어난 공급자 쪽 효과를 되돌리지 못한다. 공급자 계정의 다른 단말·웹 접근은
  SaaS 조직 정책 소관이다(`residual`). Windows·WSL·root·Docker 권한 계정은 강제 범위 밖이다.

## D-63 통제 상태를 증거와 짝으로 표시하고 호출의 다섯 단계를 나눈다 (2026-10-01)

- **문제**: 커넥터 승인이나 Gateway 경유 기록만으로 사용자 PC 전체가 통제되는 것처럼 보이면 운영자가
  우회 경로를 놓친다. 실행 전 거부와 실행 뒤 응답 보류도 같은 차단 색만으로는 구별되지 않는다.
- **화면**: MS·IBM·LiteLLM 고정 소스의 검색·심사 이력·역할별 메뉴를 참고하고, `통제 범위`를 독립 페이지로
  둔다. 항목·단말/계정·섀도/잔류·벤더 탭에서 D-62의 다섯 분류와 여섯 상태를 사용한다.
  기존 `people`의 통제 탭 링크는 새 경로로 정규화한다. 승인 여부와 집행 여부를 합치지 않는다.
- **증거**: 상태 옆에 커널 heartbeat·Gateway 원장·벤더 콘솔 수기 기록·자체 보고·없음을 표시한다.
  Endpoint heartbeat 180초, 수기 기록 14일, 자체 보고 6시간이 지나면 증거 만료를 표시한다.
  강제 상태라도 원장/커널 근거가 없거나 만료되면 녹색으로 그리지 않는다. 커널 heartbeat는 root 에이전트의
  측정 보고이며 하드웨어 원격 attestation이 아니다. 원장 행은 그 시점의 경유 증거다.
- **호출**: 목록은 시각·판정/정책·사람/단말/하네스·도구/대상·경로·전송/실행/응답의 여섯 열이다.
  상세는 출처 → Gateway → Endpoint → upstream → 응답의 다섯 단계다. clientInfo는 자기 신고,
  device_id는 서명 토큰 결합으로 구분하고 호출 당시 결합과 조회 시점의 단말 상태를 섞지 않는다.
  응답 보류에는 이미 실행된 효과가 유지됨을 표시한다.
- **개요**: 경유 호출·관리 계정의 Endpoint 강제·upstream 실행·응답 보류·우회 항목·종료 T2/T3의
  여섯 운영 질문에 KPI를 연결한다. 호출 수에 단말 설치/차단 이벤트를 합쳐 MCP 사용량으로 제시하지 않는다.
- **설치**: 권한상 첫 화면이 `activity`인 가입자는 hashchange를 예약하지 않고 동기적으로 경로를 바꾼다.
  그래야 첫 로그인에서 연 관리형 키트 안내가 뒤늦은 라우팅으로 닫히지 않는다. 실기기 가입/로그인으로 확인했다.
- **시험 보강**: 동시 3건은 원장 3행뿐 아니라 실행 1건·`P-RATE-003` 미전송 차단 2건까지 검사한다.
  실행/반환 사례는 같은 원장 ID의 native 응답이 비오류·비어 있지 않은 text인지도 확인한다.
  SSH는 저장된 호스트 키만 신뢰한다. 계약 변경과 등록 해제 순서 시험은 실패해도 `finally`에서 계약과
  독립 승인된 등록을 원복해야 한다. 등록 원복은 시작 전에 확보한 기존 승인 신청의 register API를 사용한다.
  원복 가능한 독립 승인 근거가 없으면 시험을 시작하지 않는다.
- **검증/한계**: 실제 PJ1·공식 공급자·배포 UI·원장 대조는
  [CONTROL_PLANES_2026-10-01.md](CONTROL_PLANES_2026-10-01.md)에 기록한다. 관리자 `pj1`의 다른 경로,
  Windows/WSL, SaaS의 다른 단말 접근은 강제 완료로 표시하지 않는다. D-60 PAC15와 D-61 단말 인증 경계를 유지한다.

## D-64 Console 전체를 목록 중심으로 재구성하고 상세는 native modal로 표시한다 (2026-10-01)

- **문제**: D-63의 640px 상세 안에 5개 카드를 나란히 놓아 단말 ID·정책·응답 유형과 배지가 잘렸다.
  관리 페이지에서도 차트·필터 버튼이 목록과 주요 작업을 밀어냈다.
- **결정**: Microsoft의 제목·명령·서버 목록, IBM의 관리 그룹, LiteLLM의 로그 필터·상세 분리를 고정 커밋 소스로 참고한다.
  탐색·공통 색상/글꼴·표/폼·로그인·9개 화면을 함께 바꾼다. 목록은 먼저, 분석은 별도 탭/펼침으로 배치한다.
  상세는 900px native dialog와 세로 5단 경로로 표시한다. 상태와 증거의 결합, 서명/자기 신고, 당시/현재, 판정/실행/응답은 유지한다.
- **키보드 결함**: Enter에서 행의 click을 수동 호출한 뒤 기본 동작도 허용하면 새로 초점이 간 닫기 버튼이 바로 실행된다.
  Enter·Space의 기본 동작을 취소한다. native modal의 초점 이동·배경 접근 차단·Escape 복귀를 실제 브라우저에서 확인했다.
- **검증**: 필수 전체 시험 종료 0, Rego 103/103·공격 42/42·정상 16/16·E1~E3.
  9개 페이지·29개 탭 렌더링, 검색·펼침, 브라우저 error/warn 0. 대비와 검증 범위는
  [CONSOLE_UI.md](CONSOLE_UI.md)에 기록한다. UI 검수를 위해 공급자 MCP를 수정하거나 실행 로그를 생성하지 않는다.
- **범위**: 기존 PAC15 권한·단말 집행·독립 승인과 실제 감사 원장을 유지한다. 새 프런트엔드 의존성을 추가하지 않는다.

## D-65 조직 로그인과 Secret 검사를 오픈소스에 맡기고 감사 API를 화면에 연결한다 (2026-10-03)

- **대체**: 조직 로그인은 Keycloak 26.8.0 + Authlib 1.6.12의 OIDC Code/PKCE 검증을 사용한다.
  Gitleaks 8.30.1의 기본 규칙으로 도입 저장소와 Gateway 전송 인자·마스킹 후 응답을 검사한다. 자체 프로토콜·Secret 규칙 목록의
  유지 부담을 줄이고, 기존 보수적 마스킹 규칙·Presidio·OPA·단말 관리·합성 IdP 실험은 해당 책임에 맞춰 유지한다.
- **신원**: 관리자만 `(issuer,sub)`를 기존 관리대장 주체에 연결한다. 이메일·공급자 role로 자동 활성화하지 않는다.
  SSO 모드는 로컬 비밀번호·refresh·기존 비장치 토큰을 차단한다. 요청마다 introspection을 확인하며 장애도 차단한다.
  외부 토큰은 서버에서 암호화하고 callback code/state를 로그에서 제거한다. 단말 키는 별도 회수 절차다.
- **Secret**: 제출 저장소의 설정·ignore·allow 주석은 적용하지 않는다. snapshot을 검사하며 전체 Git 이력을 검사했다고
  주장하지 않는다. 검사 실패는 도입 FAILED/실행 전 Block이다. 산출물의 Secret/Match와 Gateway 결과의 값은 제거한다.
- **감사**: 관리자 전용 필터·cursor·상세·내보내기를 추가한다. 원장/head를 read-only REPEATABLE READ로 검증하고
  export payload의 SHA-256을 제공한다. 실행 시도 후 응답을 잃은 기록은 미확인이다. 본문 제외 파일은 원문 체인의
  독립 재검증이나 서명된 외부 증거가 아니다. 공식 감사 원장을 OpenSearch로 대체하지 않는다.
- **UI**: SSO 로그인, 정책의 구성요소/신원 연결, 도입 Secret 보고서, 감사 증거 메뉴를 기존 안전 HTML/CSP/modal로 만든다.
  실제 배포 상태와 단말 강제 범위를 과장하지 않는다. 설정과 검증은 [OSS_ADOPTION_2026-10-03.md](OSS_ADOPTION_2026-10-03.md).

## D-66 Console을 판매 가능한 제품 화면으로 정리하고 쓰지 않는 기능을 걷어낸다 (2026-10-03)

- **문제**: 소유자 검수에서 이중 로고·이중 사용자 표시, 페이지마다 설명 문단, 주석 같은 칩, 정책 표의 `순위`(간격이 큰
  우선순위 값)·`상태`·`담당`, 만들 방법이 없는 `예외` 탭과 333 시절 잔재, LLM 없이는 돌지 않는 A.I.G 검사, `커널`·GW/EP/VD
  같은 표기, 종료·폐기 화면의 제각각 카드와 미번역 값·시험 데이터 문구, `실습 복원` 버튼이 지적됐다.
- **결정**: [CONSOLE_UI.md](CONSOLE_UI.md)의 화면 원칙을 정본으로 한다. 용어는 게이트웨이·엔드포인트로 통일한다.
  정책 목록은 번호·정책·결과만 보이고, 이용 관계는 표와 상세로 바꾼다. 구성요소·배포 확인 탭과 `/api/components`를 지운다.
- **333 잔재**: `exceptions.json`(EXC-001·002), 예외 판정 코드, `P-AUTHZ-DENY-001`, `P-DEPT-001`과 부서 범위 스위치를 지운다.
  과거 감사 기록의 id는 append-only 원장에 그대로 남는다.
- **A.I.G**: mcp-scan은 LLM이 필수라 기기의 소형 로컬 모델로는 의미 있는 결과를 내지 못했다. 화면·API·워커 작업·이상행위 자동
  예약·기기 로컬 모델 준비를 지운다. 과거 mcp-scan 보고는 공급망 차단 계산에서 제외하고 표는 남긴다(파괴적 이전 없음).
- **검증**: OPA 86/86(예외·부서 시험 17건은 기능과 함께 삭제), node·pyflakes 정적 검사. 기능 확인은 솔루션 기기 배포 뒤 PJ1.

## D-67 관리형 계정의 모델 API는 솔루션 기기의 승인 프록시로만 연다 (2026-10-03)

- **문제**: 관리형 계정의 UID 방화벽은 게이트웨이 IP·포트만 열어 PJ1의 Codex가 `wss://api.openai.com`에서 Permission denied로
  멈췄다. MCP 단계까지 가지 못해 관리형 설치로는 하네스를 쓸 수 없었다.
- **결정**: 기기에 tinyproxy(`full_stack_lab/model-proxy`, alpine 패키지)를 Caddy처럼 Tailscale IP에만 게시한다(기본 3128).
  `model-domains.txt`(정규식)의 도메인만, TLS 터널은 443만 허용한다. 처음 붙인 Squid 6.12는 PJ1 시험 중 연결 도중
  끊긴 터널에서 `check failed: waiting()` 단언 실패로 죽었다. tinyproxy는 같은 상황(중도 종료 200건)에서 재시작 없이 동작했다. 관리형 정책은 `proxy_port`와
  `HTTPS_PROXY`·`HTTP_PROXY`·`NO_PROXY`(게이트웨이 주소)를 내려 준다. Linux는 nft가 두 포트만 열고 실행기 래퍼가 환경 변수를
  고정한다. Claude Code는 `managed-settings.json`의 `env`로도 받는다. Codex의 모델 웹소켓이 `HTTPS_PROXY`를 따르는 것을
  확인했다(Windows 0.153.4, 존재하지 않는 프록시로 연결 거부).
- **호환**: 정책 해시는 gateway·gateway-sse·agent-service가 각자 계산하므로 `MODEL_PROXY_PORT`를 세 서비스에 같은 값으로 둔다.
  프록시 이전 설치(설정에 `proxy_port` 없음)는 재설치 요구 없이 동작하되 모델에 닿지 않는다.
- **불변식 변경**: 실기기 게시는 Caddy와 모델 프록시 두 개다. 둘 다 Tailscale IP에만 바인딩한다.
- **함께 고친 것**: 관측 보고(`agent.py --once`·`os-observer.py`)가 실패하면 토큰 캐시를 비워 MCP 인증이 끊기던 순서를
  바꿨다(토큰 먼저, 관측 실패는 기록만). `os-observer.py`의 `datetime.UTC`(3.11+)를 3.10 호환으로.
  Codex 0.158은 모든 도구 호출을 실행 파일 옆의 `codex-code-mode-host`로 처리한다. 승인 경로에 이 파일이 없고 AppArmor가
  실행을 막아 관리형 계정에서는 MCP 도구를 부를 수 없었다(모델 경로가 열리자 드러남). 설치기는 같은 릴리스의 짝 실행기를
  요구하고, Codex 프로필 안에서 같은 제한을 물려받아(`ix`) 실행하게 한다. `managed-linux.py rollback`으로 제거가 완전해졌다.
- **PJ1 검증(2026-10-04)**: 옛 설치에서 OS 이벤트 수집기를 실패시키자 `connection-stopped`·헤더 거부(재현), 새 설치에서는
  `observers: {"os-observer.py": "CalledProcessError"}`로 기록만 하고 `active`·토큰 유지. `rollback` 뒤 서비스·유닛·nft·장치 비밀·
  AppArmor·관리형 파일이 모두 사라지고 같은 키트로 재설치됨. 관리 계정 UID: 인터넷 직접 접속 차단, 프록시 경유 OpenAI 401(도달),
  example.com 403, 게이트웨이 200. 관리 계정 로그인 셸의 Codex 0.158이 프록시로 모델에 닿고 `context7/resolve-library-id`를 호출해
  원장에 `Allow P-AUTHZ-ALLOW-001`·upstream 실행·관리형 장치 ID로 남음. 같은 시간 AppArmor가 `bwrap`·`lsb_release`·`mawk` 실행을 차단.
  Python 3.10 컨테이너에서 옛 `os-observer.py`는 `ImportError`, 새 파일은 통과.

## D-68 Windows 관리형 설치기 (2026-10-03)

- **문제**: field는 관리자가 아닌 계정을 모두 관리형 필수로 두는데 관리형 키트는 Linux뿐이라 Windows 직원은 연결할 방법이 없었다.
- **결정**: `endpoint-agent/managed-windows.py`. 관리자 권한으로 한 계정을 등록하고(`platform=windows`, 계정 SID, 헤더 명령),
  SYSTEM 예약 작업이 단말 키를 보유한다. Linux의 AppArmor+UID nft 대신 계정 SID(`LocalUser`) 범위의 방화벽 차단 규칙
  3개로 게이트웨이 호스트의 게이트웨이·프록시 포트 밖 통신을 막는다(차단 규칙은 허용 규칙보다 우선, 프로그램 경로 무관).
  헤더는 그 SID에만 읽기를 허용하는 명명 파이프로 전달한다. 점검은 `firewall_enforcing`·`protected_configs`·`ordinary_account`.
- **Codex**: Windows Codex는 `managed_config.toml`을 지원하지 않는다(바이너리 문구로 확인). `requirements.toml`이 서버 신원을
  강제하고, 서버 정의는 계정 `config.toml`의 표식 블록(정책 파일 `codex-config.toml`)에 두어 해시로 점검한다.
- **판별**: 관리형 플랫폼은 등록 때 저장한 SID로 정한다. `platform` 열은 관측 에이전트의 enroll 보고가 덮어쓴다.
- **검증**: 이 노트북에서 관리자 권한 없이 가능한 범위 — 파이프 전달·거부, 계정·ACL·방화벽 조회, Claude Code·Codex가
  공백 있는 따옴표 경로의 헬퍼를 인자 그대로 실행함. 방화벽·예약 작업·관리형 파일 설치는 Windows 시험 PC에서 확인한다.
- **한계**: loopback은 Windows 방화벽 대상이 아니다. 도메인 그룹을 거친 관리자 구성원은 점검하지 않는다. WFP 차단 이벤트는 미수집.

## D-69 계약 차단은 클라이언트가 닿는 도구로 판정한다 (2026-10-04)

- **문제**: figma·github가 승인한 도구는 그대로인데 DRIFT로 서버 전체가 막혔다. github는 서버 버전이 배포 빌드 ID
  (`github-mcp-server/remote-<sha>`)라 GitHub가 배포할 때마다 모든 도구가 버전 불일치가 됐다. figma는 43개 중 허용한 1개
  (`whoami`)가 아니라 허용하지 않은 `report_mcp_app_failure`의 설명이 바뀐 것이었다. 관리형 정책은 READY 서버만 하네스에
  넣으므로 직원 PC에서는 두 서버가 사라졌다.
- **결정**: DRIFT(→ `known_tools_only=false`, `MCP-CATALOG-001`)는 허용한 도구의 설명·스키마 변경, 허용한 도구의 소멸,
  위험한 설명일 때만이다. 허용하지 않은 도구의 추가·변경·삭제는 스냅샷 findings로만 남긴다 — 게이트웨이는 허용한 도구만
  나열하고 등록되지 않은 도구 호출은 `registered=false`로 막는다. 허용한 도구의 설명·스키마가 승인본과 같고 서버 버전만
  바뀌면 승인 버전을 따라 올리고 `version-carried`(이전·새 버전)를 남긴다. 설명·스키마 변경은 여전히 새 도입 신청이 필요하다.
- **실행 직전 재확인**: GitHub 원격 MCP는 같은 시각에도 요청마다 다른 빌드 ID(`718d…`·`8928…`·`aa40…`)로 답한다(서버 여러 대).
  `_call_upstream`의 같은 연결 재확인과 PAC-02 기준선도 위 규칙(허용 도구의 설명·스키마)으로 맞추고 버전 문자열은 비교하지 않는다.

## D-70 승인 근거가 그대로면 사용 기한을 자동 연장한다 (2026-10-04)

- **문제**: figma·github의 사용 승인(30일)이 끝나면 계약이 그대로여도 `P-APPROVAL-EXPIRY-001`로 모든 호출이 막히고,
  콘솔 등록 서버는 제자리 연장이 없어 매번 신청자·승인자를 거친 새 도입 신청이 필요했다(D-57·D-59).
- **결정**: `catalog_watch`가 카탈로그를 다시 읽은 직후 `renew_approvals`를 돈다. 만료 7일 전(`APPROVAL_RENEW_WINDOW_DAYS`)부터,
  허용한 모든 도구의 계약 입력(등록·허용·설명/스키마 일치·허용 도구만·위험 설명 없음·공급망 승인·안전한 전송·허용 목적지)이 참이고
  치명 취약점이 없고 서버가 READY·운영 중이면 원래 기간(`approval_days`)만큼 늘린다. 레지스트리 이력에 `approval-renewed`
  (이전·새 기한, 도구)를 남긴다. 이미 만료된 승인은 되살리지 않는다. 계약이 바뀐 서버는 D-69대로 DRIFT라 연장되지 않는다.
- **위험**: 정기 재검토가 사람 검토에서 근거 재확인으로 바뀐다. 사용자·목적의 변화는 자동으로 잡지 못하므로 종료·폐기 절차로 다룬다.

## D-71 엔드포인트 연결은 설치 파일 하나와 권한 확인 한 번으로 끝낸다 (2026-10-04)

- **문제**: 직원이 압축 해제, `sudo python3 … install`, 하네스 바이너리 수동 배치, 관리 계정 전환, `codex login`까지 했다.
  레퍼런스 조사([ENDPOINT_ONBOARDING_2026-10-04.md](ENDPOINT_ONBOARDING_2026-10-04.md))에서 LiteLLM은 `lite login`·`lite configure`로
  설정 기록을 도구가 대신하고, Windows ODR는 동의를 호스트 단위 1회로 모은다. 둘 다 OS 강제가 없어 그 부분은 우리가 유지한다.
- **결정**: `endpoint-agent/bootstrap.py`와 진입점 `install.sh`·`install.cmd`. 직원은 콘솔 → **내 PC 연결** → OS별 설치 파일 →
  실행 → sudo/UAC 1회. 설치기가 승격 한 번 안에서 필수 패키지 설치, 승인 하네스 배치(Codex는 같은 릴리스 `codex-code-mode-host`
  동반 필수, 복사본 SHA-256 기록), 관리 계정 결정, 관리형 설정·프록시·헤더 헬퍼 구성, 모델 로그인 안내·실행을 한다. 이미 설치돼
  있으면 자동 rollback 후 재설치하고, 중간 실패도 rollback 뒤 원인 한 줄만 보여 준다.
- **관리자 계정인 직원**: 자기가 지울 수 있는 규칙으로는 자기를 통제할 수 없다. Linux는 `managed-<계정>`을 자동 생성하고 직원 계정의
  `codex`·`claude`를 그 계정의 **로그인 셸을 거쳐** 실행하는 shim(`/usr/local/bin`)을 둔다 — AppArmor·UID 방화벽이 로그인 때와 같이
  붙는다. sudoers 규칙은 그 로그인 셸 하나만 NOPASSWD로 허용하며, 이미 sudo가 있는 계정이라 권한이 늘지 않는다. Windows는 비밀번호
  없는 교차 계정 실행이 없어 표준 계정을 만들고 그 계정 로그인을 안내한다(생성 시 무비밀번호 → Windows 기본 정책이 콘솔 로그인으로
  제한, 첫 로그인에서 직원이 설정).
- **활성화**: 관리자 콘솔 클릭을 유지한다(소유자 결정). 자기 장치를 스스로 활성화할 수 없다는 통제가 단순화보다 우선이다.
- **한계**: 하네스 바이너리는 복사본 무결성만 고정하고 공급자 서명은 검증하지 않는다. 관리 계정은 홈이 달라 직원 계정의 파일을
  읽지 못한다. 설치기는 네트워크에서 하네스를 받아오지 않는다 — 공식 설치가 없으면 한 줄로 거부한다.

## D-72 관리자 계정의 터미널에서 친 명령도 관리 계정으로 간다 (2026-10-05)

- **문제**: D-71의 shim은 `/usr/local/bin`에만 있다. 직원 PATH는 `~/.local/bin`이 앞서므로 평소 터미널에서 `claude`·`codex`를 치면
  직원 소유의 진짜 하네스가 먼저 실행돼 관리형 MCP·판정 로그를 모두 비껴갔다(`Needs authentication`, `headers helper exited with
  status 1`, 솔루션에 기록 없음). 시험이 SSH 한 줄 명령(비대화형이라 PATH에 `~/.local/bin`이 없다)이어서 가려졌다.
- **결정**: ① `/etc/profile.d/mcpgw-managed.sh`에 `codex`·`claude` 셸 함수(PATH 조회보다 앞선다)를 두고 `/etc/bash.bashrc`·
  `/etc/zsh/zshrc`에 표식 블록으로 불러온다(비로그인 터미널까지). **직원 계정에서만 정의한다** — 관리 계정의 로그인 셸도 profile.d를
  읽는데, 거기서 shim을 부르면 AppArmor가 실행을 거부해 `bad interpreter: Permission denied`로 죽는다. shim이 없으면 원래 명령으로 폴백.
  제거 시 함수·블록 모두 원복. ② 하네스 탐색에 공식 설치기 위치(`~/.codex/packages/standalone/current/bin`,
  `~/.local/share/claude/versions`·`~/.local/bin/claude`)를 추가. ③ Codex 0.159+ 대화형 CLI는 공유 백그라운드 서버를 Unix 소켓으로
  쓰려 하므로(승인 복사본은 패키지 구조가 없고 프로필은 Unix IPC 금지) 래퍼가 `--no-daemon`을 앞에 붙인다(플래그를 모르는 빌드엔 안 붙임).
  ④ 설치 끝의 모델 로그인을 Codex·Claude 각각 안내(Ctrl+C로 건너뜀, 첫 실행 때 하네스가 다시 묻는다). ⑤ 활성화 전에는 점검 주기를
  10초로 줄여 활성화 직후 토큰이 몇 초 안에 열린다(관측기는 60초 주기 유지).
- **시험(PJ1)**: 설치 → 활성화 → 새 PTY 터미널에서 `claude mcp list` 3개 연결, 옵션 없이 친 `codex` TUI에서 `context7.resolve-library-id`
  호출 → 관리형 장치 ID·codex-mcp-client 0.160.0으로 판정 로그 기록. 시험은 비대화형 SSH가 아니라 **대화형 PTY**로 한다.
- **한계**: 전체 경로나 `command claude`로 진짜 하네스를 실행하면 우회다(관리자 계정의 원래 권한, 통제 범위 화면의 `우회 가능`).
  함수는 bash·zsh 대화형 셸에만 걸리고 GUI 실행기·IDE 확장은 shim PATH에 의존한다. 같은 PC의 다른 사용자가 친 명령은 shim으로 가
  sudo 규칙이 없어 실패한다(직원 1인 1PC 전제).

## D-73 도구 계약의 숨김 기법과 정보 전달용 인자도 등록 때 본다 (2026-10-05)

- **문제**: D-52의 계약 규칙은 지시 문구만 봤다. 관리자 눈에 띄지 않게 둔 문장(마크다운 주석, 빈 줄 아래 꼬리, base64)과 모델이
  빼낸 정보를 담아 보낼 인자 이름(공개 사례 `sidenote`)은 보지 않았다. `sidenote`는 자체 시험 예시의 스키마에 이미 있었는데도
  인자 이름은 판정에 쓰이지 않았다. Microsoft agent-governance-toolkit(MIT)의 스캐너를 읽고 우리 규칙과 대조해 찾은 빈 곳이다.
- **결정**: `poisoning.findings()`(계약)에만 라벨 4개를 더한다. 인자·결과 규칙에는 넣지 않는다 — 웹 페이지·출력에는 HTML 주석,
  빈 줄, base64가 흔하다. ① `숨긴 주석`(`<!--` 같은 여는 표식, `[//]: #`) ② `공백 아래 숨은 문장`(빈 줄 5개 이상 뒤의 글, CRLF·스키마 안의 `\n`
  포함) ③ `인코딩된 문장`(40자 이상 base64 중 읽을 수 있는 문장으로 디코딩되는 것, 해시·id는 제외) ④ `정보 전달용 인자`(최상위 인자
  이름이 `sidenote`·`system_prompt`·`chat_history`·`conversation(_history)`·`callback_url`·`webhook(_url)`·`target_url`과 정확히 일치).
- **하지 않은 것**: 같은 이름·비슷한 이름의 도구 사칭 검사. 이 Gateway는 서버마다 엔드포인트가 따로라(`/mcp/<서버>/`) 호출은 하네스가
  연결한 서버로만 가고, Claude Code는 `mcp__<서버>__<도구>`로 서버 이름을 붙이며 통합 엔드포인트는 `<서버>__<도구>`다. 실제 카탈로그에도
  정확히 같은 이름이 정상으로 있다(`list_branches`: github·supabase, `search_issues`: github·sentry — 이 검사는 둘 다 오탐).
  비슷한 이름(편집거리 2 이하) 쌍은 0건이었다. 이름을 합치는 다른 하네스(Gemini CLI 등)에서 모델이 헷갈릴 수 있는지는 확인하지 않았다.
  인자 이름의 부분 문자열 규칙(`command`·`eval`·`exec` 등)도 쓰지 않는다 — Notion의 수정 도구 2개가 enum 인자 `command`를 쓰고
  `retrieval`에도 `eval`이 들어 있다.
- **시험**: 기기 DB의 도구 316행(중복 제외 165개, 서버 8개, 비활성 도구 포함)에 새 규칙을 걸어 **새 적중 0건**(기존 1건은 비활성
  notion 도구). `python -m app.poisoning`에 검출 7건·무음 6건을 더했고, 공개 사례 `sidenote` 예시는 이제 라벨 하나가 늘어난다.
  garak 주입 코퍼스는 변경 전과 같은 21/26(인자·결과 규칙은 건드리지 않음).
- **한계**: 새 규칙이 이미 등록된 활성 도구에 적중하면 `poisoning_review`가 없는 한 카탈로그 갱신 때 `unsafe-description`으로 서버가 막힌다.
  그래서 위 실측을 먼저 했고, 랩 서버(filesystem·git 등)의 도구 원문으로는 재지 못했다. 중첩 객체 속 인자 이름은 보지 않는다(그 설명·기본값은
  본다). 규칙은 숨김 기법의 흔한 형태만 본다.

## D-74 새 MCP 규격(2026-07-28)과는 코드 변경 없이 맞는다 — 두 세대를 시험으로 고정한다 (2026-10-05)

- **문제**: 2026-07-28 규격은 프로토콜 세션과 `Mcp-Session-Id`를 없애고(`initialize` 제거, 요청마다 `_meta`에 버전·능력·클라이언트 정보),
  `server/discover`·`ttlMs`/`cacheScope`·`resultType`·다회전 요청(공급자가 사용자 입력을 되묻는 `InputRequiredResult`)을 더했다.
  Gateway가 두 세대를 다 받는지, principal별로 걸러지는 도구 목록이 공유 캐시에 남지 않는지, 공급자가 되물으면 어떻게 되는지 몰랐다.
- **확인**(기기에서 실행 중인 gateway 이미지, `mcp==2.2.0`의 최신 규격 2026-07-28·기본 협상 2025-03-26, loopback, DB·정책은 대체):
  ① 옛 클라이언트(`initialize` 2025-11-25 + 세션 ID)는 그대로 동작하고 하네스 이름이 기록된다. ② 새 클라이언트는 `server/discover`로
  2026-07-28을 협상하고 `tools/list`·`tools/call`이 동작한다. 목록 결과는 `cacheScope: private`·`ttlMs: 0`이라 공유 캐시가 쥐지 않고,
  하네스 이름은 `initialize` 없이도 `_meta`의 clientInfo로 남는다. ③ 공급자가 도구 호출에 `InputRequiredResult`("API 키를 붙여 달라")를
  돌려주면 upstream 클라이언트가 `MCPError: Elicitation not supported`로 실패하고 답하지 않는다. 이 Gateway는 sampling·elicitation·roots
  능력을 선언하지 않으므로 공급자가 합법적으로 물을 수도 없다.
- **결정**: 코드는 바꾸지 않는다. 위 세 가지를 `tests/protocol_versions_check.py`로 고정한다(SDK를 올리거나 `build_mcp`를 바꿀 때 돌린다).
  같은 파일의 기대값을 `(0, "public")`으로 뒤집으면 exit 1로 실패함을 확인했다.
- **적용되지 않는 변경**: 인가 쪽(Client ID Metadata Document, `iss` 검증, DCR의 `application_type`)은 IdP에 `authorization_endpoint`·DCR가 없고
  password·refresh·장치 토큰만 있어(`idp.py` 라우트) 해당 없다. Gateway는 상태 핸들을 만들지 않는다(핸들 탈취 방어는 공급자 몫). 세션 ID는
  판정에 쓰지 않는다 — 요청마다 Bearer 토큰으로 신원을 정한다.
- **한계·후속**: ① 하네스가 실제로 어느 세대로 붙는지는 확인하지 못했다(결정 원장에 협상 버전이 없다). ② SSE 진입점(`gateway-sse`, 2024-11-05
  전송)은 이번 규격에서 Deprecated로 분류됐다. 제거는 12개월 이후라 당장 영향은 없으나, 이 진입점을 쓰는 하네스가 있는지 확인해 둘 것.
  ③ 공급자가 tasks 확장의 작업 핸들을 먼저 돌려주는 경우, stdio 진입점, 도구 인자를 HTTP 헤더로 복사하는 `x-mcp-header`는 시험하지 않았다.

## D-75 도구 텍스트 검사는 길이에 선형이어야 한다 — 정규식 서비스 거부 3곳을 고쳤다 (2026-10-05)

- **문제**: D-73 시험에 아주 긴 입력을 넣다가 `poisoning.py`의 기존 규칙이 입력 길이의 제곱으로 느려지는 것을 찾았다. 줄바꿈이 있는 평범한
  로그 100 KB를 `result_findings`에 넣으면 16.9초, 50 KB는 4.2초가 걸렸다. 결과 상한 `MAX_RESULT_BYTES`(256 KB)에서는 약 2분(제곱으로 늘려 추정)이고, 인자 상한
  64 KB에서도 수 초다. 이 검사는 Gateway의 이벤트 루프 안에서 동기로 돌기 때문에 그동안 모든 사용자의 요청이 멈춘다. 정상적으로 큰 결과
  하나, 또는 악의적인 공급자의 결과 하나로 Gateway 전체가 멈출 수 있다.
- **원인**(`OVERRIDE_RULES`, 결과·인자·계약 세 곳에 모두 쓰인다): ① 위조 대화 규칙 `(?=.*^…user:)(?=.*^…assistant:)`는 선행 탐색 두 개를 모든
  위치에서 다시 시작해 전체를 훑는다. ② `숨긴 지시 태그`의 `<\s*/?\s*`는 공백이 두 곳에 겹쳐 맞는다. ③ `^\s*###`는 줄 머리마다 뒤의 공백 전체를 다시 읽는다.
- **결정**: ① 두 패턴을 각각 한 번씩 찾는 `_Both`로 바꾼다(뜻은 같다). ② `<\s*(/\s*)?`로 바꾼다(받아들이는 문자열이 같다). ③ `^[ \t]*###\s*`로 바꾼다
  (줄 머리 뒤의 공백이 줄바꿈을 건너 시작해도 마지막 줄 머리에서 시작한 것과 같다). 무작위 입력 6만 건으로 옛 패턴과 새 패턴의 판정이 같음을 확인했다(불일치 0).
  평범한 100 KB 출력은 39 ms, 256 KB는 43 ms가 됐다.
- **시험**: `python -m app.poisoning`이 길이 20만 안팎의 병적 입력 6종(여는 표식 반복, 줄바꿈·CRLF·이스케이프된 줄바꿈 연속, 한 글자 반복, 공백 연속)을
  각 5초 안에 읽는지 본다. 규칙이 다시 제곱으로 느려지면 실패한다. garak 주입 코퍼스는 변경 전과 같은 21/26.
- **한계**: 병적 입력으로 잰 것은 이 파일의 규칙뿐이다. 다른 모듈의 정규식 16곳(`classify.py`의 DLP·비밀 패턴 포함)은 구조를 읽고 중첩 반복과 겹치는
  공백 반복이 없음만 확인했다. 파이썬 표준 `re`에는 시간 제한이 없으므로, 앞으로 이 파일에 규칙을 더할 때는 위 병적 입력 검사를 통과해야 한다.

## D-76 개발 협업 기록과 제품 자원 지표를 분리하고 재현된 경계 결함을 수정한다 (2026-10-13)

- 사용자 정정: 연구 위키는 Markdown 정본이다. 웹은 실제 Codex·Claude 공개 요청/응답·작업·검사를 보는 별도 localhost 협업 콘솔이며 원본 대화·CLI 설정·비밀은 Git에서 제외한다. 제품 Console에 개발 기록을 넣지 않는다.
- 자원 상태: 관리자 Console scope로만 `/api/system/metrics`를 읽는다. Linux `/proc` 누적 CPU 차분과 `MemTotal-MemAvailable`, 고정 Console→Gateway DNS·TCP 연결 시간을 사용한다. 최초/30초 초과 CPU 간격·실패/오래된 화면 값은 미측정이며 0으로 만들지 않는다. 추가 수집 서비스·Docker 소켓·셸 실행을 넣지 않는다.
- 계약 복귀: 임의 과거 catalog hash 존재 여부 대신 마지막 서버별 snapshot을 비교하여 A→B→A의 관측값과 재승인이 B에 남지 않게 한다.
- 감사: 새 체인 v7은 INSERT에 명시한 동일 UTC `created_at`을 지문에 넣는다. v1~6은 기존 지문으로 검증하고 원장을 다시 쓰지 않는다. 기존 체인의 시각 무결성을 소급해 보장하지 않는다.
- 결과·목적지: JSON 직렬화와 함께 디코딩된 모든 문자열을 검사하여 줄바꿈 기반 지시 규칙을 유지한다. OPA egress 데이터 실패/결측/타입 오류는 거부하고 명시적 빈 목록과 구분한다.
- 배치 검사: Tailnet Caddy와 모델 프록시의 서비스·주소·게시/대상 포트·프로토콜 정확 집합만 허용한다. 임의 서비스/전체 인터페이스/추가 포트의 음성 시험을 유지한다.
- 근거·검증·잔여 작업: `research/llm-wiki/status/reports/2026-10-13-feature-design.md`와 현황/작업 보고. 실제 Claude Sonnet5.5 분석은 수신했으나 수정 후 CLI는 계정 세션 한도로 미완료다. 자동 모델 대체 없이 Codex 검증을 계속한다.

## D-77 로컬 앱의 MCP·bridge·OS 권한과 점검 증거를 분리한다 (2026-10-14)

- 실제 공개 GhidraMCP·Git MCP·DBHub·Blender MCP·Playwright MCP를 설치·호출하고 스키마92개, 경로/readonly/bridge 반례와 위험10건을 기존 정책24개에 연결했다. 운영 registry 자동 등록이나 계약 TOFU는 하지 않는다.
- Linux heartbeat는 정확한 프로필 행을, Windows는 실제3개 프로필과 규칙3개의 이름·활성 상태·방향/Action/Profile/SID·baseline을 대조한다. 불완전한 관찰/설치 snapshot을 정상으로 받아들이지 않는다.
- 인벤토리 Gateway 경유는 실제 URL로 판단하고 클라이언트 이름만으로 승인하지 않는다. URL userinfo/query/fragment와 legacy stdio 원문은 SHA-256 참조로 수집/저장하며 raw JSON도 원문 자격을 보존하지 않는다. 기존 과거 저장분과 URL path에 든 비밀을 정화했다는 뜻은 아니다.
- MCP annotation·Git base dir·SQL readonly·Blender safe mode·브라우저 isolated/allowed origins는 OS sandbox를 대신하지 않는다. 직접 앱 bridge의 인증·계정·파일·최종 egress를 독립 통제/검증한다.
- D-68의 Windows loopback 일반론은 현재 키트에서 Win32/WFP IPv4/IPv6 loopback 효과가 미측정된 한계로 정정한다. App Control/AppLocker와 실행/스크립트 권한은 현재 키트에 미설치다.
- Linux root service의 privilege 분리/strict unit을 적용할 때는 policy/state 쓰기·journal·nft AF_NETLINK·socket의 필요 권한부터 설계한다. UID peer credential은 공유 계정 경계이며 per-process identity나 remote root attestation이 아니다.
- 회귀15개·기존 Linux 키트17개, 솔루션 field up/source46개·정책/build hash, PJ1 설치 hash·active/compliant·fresh enforce label·승인 하네스·비승인 Node/loopback 거부를 확인했다. 새 자연어 model→MCP turn이나92개 모두의 managed 집행은 미실행이다.
- 근거·변경·실패·복구: [2026-10-14 검수 보고](../../research/llm-wiki/status/reports/2026-10-14-local-mcp-endpoint.md). Burp Community desktop MCP와 유료 DAST MCP는 구분한다. DBeaver 사용자 캐시 생성 정황은 보존했고 Windows 제거 경합은 후속으로 남겼다.

## D-78 상태 전이와 감사기록은 함께 commit하며 시험 DB 초기화는 제품 DB와 분리한다 (2026-10-14)

- 위험매핑의 정적 예상 → 실제 PJ1 DB 보존 시험 → task-owned 전용 PostgreSQL DB 실제 초기화 후 선별시험으로 진행한다. static/unit/DB fixture/protocol/kernel/model/upstream 증거를 섞지 않는다.
- 관리 장치 활성화·철회의 UPDATE와 감사 INSERT를 같은 connection·transaction에 묶는다. PostgreSQL trigger 실패 주입으로 수정 전 부분commit과 수정 후 전체rollback을 독립조회로 검증했다.
- 감사기록 오류로 철회가 rollback되면 완료되지 않은 요청이다. 오류를 유지하고 재시도가 필요하다고 보고한다. 독립 긴급deny/remote attestation을 추가한 것으로 해석하지 않는다.
- 운영 DB·이전 interoperability lab은 초기화하지 않는다. 정확한 전용DB명·컨테이너task label·제품mount/공개port부재를 guard하고 reset marker 소멸을 확인한다.
- [실험·수정·배포·한계](../../research/llm-wiki/status/reports/2026-10-14-risk-scenarios.md), LOCAL-RISK-11, DEV-27로 추적한다.

## D-79 시험 대상 MCP를 에이전트가 승인하지 않는다 — 자가 승인 시험은 무효이며, 호출별 세션은 유지한다 (2026-10-14, 세션 부분은 D-115로 개정)

- 위험 매핑이 묻는 것은 비인가 로컬 MCP가 엔드포인트에서 막히는가다. 시험 대상 MCP를 에이전트가 신청·검토·승인해 Gateway에 등록하고 인자를 `const`로 고정해 통과시킨 시험은 거버넌스 증거가 아니다. 그런 1차 시험(원장 744~800)은 무효이며 서버 3건은 `deregister_server`로 철회했다(행은 `DISABLED`로 남음). 계약 승인은 사람이 한다는 불변식은 시험에도 적용한다.
- 콘솔에 로그가 없던 원인은 Gateway가 아니라 Codex 하네스의 모델 턴이 사용량 한도로 시작 즉시 실패해 `tools/call`이 0건이었던 것이다. `initialize`·`tools/list`는 판정 대상이 아니라 원장에 남지 않는다. 한 하네스가 막히면 다른 실제 하네스(Claude Code)를 쓰되, 시험 대상과 승인 상태는 바꾸지 않는다.
- Gateway는 `tools/call`마다 업스트림 MCP 세션을 열고 닫는다(`upstream.session`). Playwright MCP는 마지막 세션이 닫히면 탭을 닫아 호출 사이 상태가 사라진다. 호출자 사이 세션 공유는 상태 유출 위험이라 채택하지 않는다(IBM ContextForge는 풀을 폐기하고 세션별 레지스트리로 대체). 세션 바인딩은 별도 결정 사항이다(DEV-29).
- 2026-10-17 개정: 위 호출별 세션 수명만 D-115의 주체·대화별 구형 MCP 세션 재사용으로 대체한다. 시험 대상 자가 승인 금지와 호출자 사이 공유 금지는 유지한다.
- 근거·한계: [정정된 보고](../../research/llm-wiki/status/reports/2026-10-14-pj1-nine-tools.md), DEV-28·DEV-29.

## D-80 비인가 로컬 MCP는 겹친 계층이 막지만, 통제 밖 계정은 비가시이고 정상 사용 거부가 잡음이며 헬퍼 토큰이 Bash에 닿는다 (2026-10-14)

- PJ1 관리 계정의 실제 Claude Code에게 등록하지 않은 실제 OSS 로컬 MCP(Git·DBHub·Playwright)를 자연어로 쓰게 했다. 하네스 정책(`allowManagedMcpServersOnly`)·AppArmor exec·nft uid 규칙·모델 프록시가 겹쳐 관리 계정의 사용은 성공 0·수신 서버 요청 0이었다. 시험 대상 서버를 Gateway에 등록·승인하지 않는다(D-79).
- 같은 PC의 비관리 계정은 같은 요청이 전부 성공했고(9개 도구, `git_commit` 효과 확인) Gateway 원장·엔드포인트 이벤트에 0건이었다. 통제 범위는 관리 계정으로 한정된다고 명시하고, 통제 밖 사용을 막는다고 쓰지 않는다.
- 관리 프로파일은 `header-helper` 실행(`px`)을 허용하는데 Bash 자식이 같은 프로파일이라 기기 Gateway 토큰을 얻을 수 있다. 모델이 실제로 토큰으로 Gateway에 직접 요청했다(원장 803, 비인가 서버 `Block/MCP-REGISTRY-001`). 헬퍼는 하네스 본체만 실행하도록 분리해야 한다(DEV-31). 이번에는 모델이 토큰을 출력에서 가려 대화에는 남지 않았다.
- Claude Code가 시작마다 부르는 `git`·`claude` 재실행이 프로파일에 거부돼 정상 사용에서도 "실행 차단" 이벤트가 매번 생긴다(시험 창 62%). 프로파일을 완화해 해결하지 않는다. 이벤트 분류·상세 보강을 별도 결정한다(DEV-30).
- 모델이 스스로 멈춘 케이스는 통제 증거가 아니다. 명시적으로 허용한 케이스에서 OS 계층이 막은 것만 집행 증거로 센다.
- 근거·한계·미실행(Codex·Windows·E13 전체 조건): [작업 보고](../../research/llm-wiki/status/reports/2026-10-14-e13-local-mcp-natural-language.md), DEV-28·30·31·32.

## D-81 PJ1 Ghidra의 로컬 SDK·수동 관측·OS 자동 전송·Gateway 원장을 구분한다 (2026-10-14)

- 사용자 설치/로그 확인 요청으로 PJ1의 Ghidra12.1.4/GhidraMCP2.0.0 실제stdio28 schema·합성ELF 읽기를 검증했다. UID1000/unconfined의 로컬 호출은 Gateway 원장0이었다. 이를 관리UID1001의 허용이나 자연어 모델 호출 증거로 세지 않는다.
- 기본 observer의 NETSCAN0은stdio관측도 끈다. 실제 process scanner1건을 명시적 일회성으로보고했을 때 Console shadow/suspected1 수신했고, 종료후task표식1건만 원복했다. observed process를 confirmed MCP계약·운영승인으로 올리지 않는다.
- 관리UID1001의 Python실행은 AppArmor가 로딩전 exit126으로거부했다. 별도실제거부는 수동POST/서비스재시작없이 주기수집기만 기다려 약35.84초 후 Console1387에수신했다. 일반interpreter거부와Ghidra전용정책은 구분한다.
- 디스크여유502MB 때문에 Ghidra/JDK는 RAM1.24GiB task설치로분리하고privatevenv/로그는디스크에보존했다. 영구설치/자동stdio관측은DEV-33 후속이다. 사용자파일·정책·기기자격·무효화된9개시험등록을 변경하지 않았다.
- [검수·원본·로그](../../research/llm-wiki/status/reports/2026-10-14-pj1-ghidra-logs.md).

## D-82 로그 채널별 전달·수집 상태와 검수 WBS를 분리한다 (2026-10-14)

- 설정 inventory·프로세스/stdio 발견·OS 거부 이벤트·Gateway tools/call 원장은 다른 채널이다. 서비스 active, subprocess exit0, MCP SDK 성공, raw/projection hash 일치를 채널 전체 성공으로 합치지 않는다.
- PJ1 NETSCAN0과 제공 Console 전용 listener 누락을 확인했다. 부분 snapshot DELETE·stale 집계·Windows producer 공백은 DEV-34 후속이며 실제 손실/Windows 전달 성공은 이번에 재현하지 않았다. 자동 수집 확대나 승인 상태 변경 없이 읽기 전용으로 검수했다.
- 목표 G01–G10/원본 PAC01–24를 40개 작업에 의미 매핑한다. 구현·회귀·배포·실제환경·검수20%씩, 부분/과거 표본0.5, 해당 단계 충족1. 단계 가중 진척과 5단계 모두 충족한 최종 완료 수를 따로 표시한다. 공수·인증·전체 효과 완료율로 쓰지 않는다.
- Markdown/JSON을 정본으로 유지하고 웹은 제품 Console과 분리한 owner-private 검수 스냅샷으로 제공한다. 제품 key/token·내부 주소·비밀 raw payload를 사이트에 싣지 않는다. 실시간 API 연동과 자동 점수 갱신은 후속이다.
- [이번 보고](../../research/llm-wiki/status/reports/2026-10-14-endpoint-log-wbs.md), [정본 산정표](../../research/llm-wiki/analysis/development-wbs/README.md).

## D-83 완전성·관측 source·수집 상태는 별도 계약이며 Linux 주기 전달을 검증한다 (2026-10-14)

- D-82의 로그 공백 후속으로 process-only 자동 수집을 network scan과 분리하고 root 보호 UID/SID 범위만 본다. 실제 Ghidra UID1000은 통제 밖으로 유지한다. name marker는 MCP suspected이며 운영 승인이 아니다.
- unmarked/partial 보고의 기본 complete는 False다. 명시적 complete에서만 unseen 행 삭제, listener source 범위만 reconciliation, upsert/삭제/observation은 동일 connection transaction. server-managed observation은 enroll detail에서 받아 덮어쓰지 않는다.
- 채널별 수신 시각·last-success·상태와 fresh/stale/unknown을 보존한다. 미수집/오류를 건강한0으로 바꾸지 않으며 과거 shadow count는 보수적으로 남긴다. 별도 status route도 기존 device scope와 본인 endpoint 경계 안이다.
- OS batch가 성공해야 cursor/bookmark를 진행하고 중복 event_id는 새 행을 만들지 않는다. collector 실패는 healthy managed credential을 지우지 않는다. 이는 집행 점검 실패를 무시하는 변경이 아니다.
- Windows는 event-time 관리SID를 요구하며 WFP의 현재 PID 주체를 과거 SID로 추론하지 않는다. audit 정책을 자동 활성화하지 않고 실제 Windows 시험은 Linux 우선 사용자 결정에 따라 남긴다.
- Linux 자동 marker/다른UID 음성·실제 AppArmor 이벤트·정보원 오류/last-success/cursor/복구, 전용 PG8조건과 배포 image PASS, Console 표시·source SHA/제품DB 보존 확인. 합성 process, 실제 OS, protocol/model 증거를 구분한다.
- 40개 WBS는3개 작업만 검수 점수 갱신(21.8→24.8%, 최종0/40). 제품 Console은 제품 로그만, 별도 owner-private WBS는 검수 스냅샷만 제공한다. 기존 자가 승인 시험은 복원하지 않는다.
- [검증·배포·보존·한계](../../research/llm-wiki/status/reports/2026-10-14-endpoint-telemetry-fix.md), DEV-18/33/34, LOCAL-RISK-12/13.

## D-84 검사 엔진을 프로세스 안의 네이티브 코드로 옮기되 판정은 원래 엔진과 같아야 한다 (2026-10-15)

- 결정: Secret 검사는 gitleaks 바이너리를 매번 실행하지 않고 같은 판본(v8.30.1)의 Go 라이브러리를 C ABI 공유 객체(`gateway/native/gitleaks`)로 빌드해 ctypes로 부른다. 도구 텍스트 규칙(`poisoning.py`)은 PCRE2-32 JIT를 쓰는 CPython 확장(`gateway/native/textscan`)에서 GIL을 놓고 실행한다. OPA·Presidio·콘솔 중계는 이벤트 루프별 공유 클라이언트(`app/connections.py`)를, 업스트림 MCP 전송은 (엔드포인트, 주체, 자격) 단위 연결 풀을 쓴다.
- 이유: 쓰기·외부 전송 호출마다 gitleaks 실행이 두 번(인자·결과) 일어나 각 65 ms였고(기기 측정), 200 KB 결과의 규칙 검사는 파이썬 `re`가 GIL을 쥔 채 27~70 ms 이벤트 루프를 막았다. OPA는 호출당 두 번, Presidio는 최대 네 번 새 TCP 연결을 열었고 업스트림은 호출마다 TCP·TLS를 새로 맺었다.
- 동등성: gitleaks 라이브러리는 CLI `stdin`과 같은 설정(기본 카탈로그·디코드 깊이 5·아카이브 미탐색·표준 regexp·호출마다 새 탐지기·로거 끔)이고, `tests/secret_engine_parity_check.py`가 132개 합성 시료에서 규칙 ID 집합을 대조한다(차이 0). 텍스트 규칙은 PCRE2의 유니코드·대소문자 처리를 쓰지 않는다. 입력을 CPython이 `_sre`에서 쓰는 함수(`Py_UNICODE_TOLOWER`·`ISALNUM`·`ISSPACE`·`ISDECIMAL`)와 `re._casefix`로 작은 정규 알파벳에 사상하고, 각 규칙의 파싱 트리를 그 알파벳 위 PCRE2로 번역하면서 원소마다 `re`에 직접 물어 허용 기호를 정한다. `tests/textscan_parity_check.py`가 원소 422개를 전 코드포인트 0x110000개에서, 규칙 21개를 무작위 6만 건에서 대조한다(차이 0). 번역하지 못하는 구문·확장 부재·PCRE2 오류는 해당 규칙을 `re`로 판정한다.
- 연결 재사용 경계: MCP 세션은 호출마다 열고 닫는다(D-79). 연결 풀 항목은 주체마다 따로이고 쿠키를 저장하지 않으며, 사용 중인 연결은 축출하지 않는다.
- 한계: 측정값은 기기(Ryzen 5 7530U)·WSL의 격리 컨테이너 기준이다. 실제 호출 경로의 전후 지연은 `decisions.timings`(D-95)로 따로 확인한다. 이미지 빌드에 Go 모듈·Debian 패키지 내려받기가 필요하다.

## D-85 엔드포인트 목록은 반환 창과 전체 건수를 분리하고 커서로 넘긴다 (2026-10-15)

- 결정: 설정·리스너·OS 이벤트·관측 상태 API는 `rows`/`total`/`limit`/`next_cursor`를 돌려준다. 정렬은 `id DESC`, 커서는 마지막 `id`(키셋)라 페이지 사이에 새 행이 들어와도 겹치거나 빠지지 않는다. 한 번에 최대 200건. 요약 API(`/api/endpoint/inventory`)는 기존 키를 유지하고 `pages`를 더한다.
- 이유: 최근 200건만 보이는 목록은 전체가 200건이라는 뜻으로 읽힌다. 수집 중단도 0건과 구별돼야 하므로 24시간 차단 집계는 OS 채널이 최근 성공일 때만 숫자로 보이고, 아니면 `수집 중단`으로 보인다.
- 한계: 커서는 불투명한 id라 중간으로 건너뛰는 임의 쪽 이동은 없다. 요약의 분류 필터는 쉼표로 여러 개를 받는다.

## D-86 저장 레코드는 에이전트 해시와 서버 재계산 해시, 변환 이름, 수집기를 함께 남긴다 (2026-10-15)

- 결정: 각 레코드에 원본 해시·projection 해시·변환 이름·수집기를 에이전트가 보내고, 서버는 저장한 필드만의 정규 JSON으로 projection 해시를 다시 계산해 `match`/`mismatch`/`unreported`를 기록한다. 하트비트에는 Gateway가 렌더링한 파일 해시와 장치가 보고한 설치 해시를 따로 둔 설치 영수증을 기록한다. 수집하지 않은 값은 만들지 않는다.
- 이유: 전달 중 또는 저장 중에 형태가 바뀌었는지 사람이 확인할 수 있어야 한다(원본→projection→저장 사슬).
- 한계: 해시는 단말 root 침해에 대한 증명이 아니다. 원본 해시는 서버가 검증하지 못하고, 설정 항목의 원본 해시는 `env`·`headers`를 제외한다(비밀 값을 해시로도 남기지 않음).

## D-87 수집 출처를 라벨로 남기고 재전송을 줄이며 연관 기록은 합치지 않는다 (2026-10-15)

- 결정: 출처는 `automatic`(수집 서비스)·`manual`(운영자·헬퍼 업로드)·`os_event`다. 라벨이 없는 옛 보고는 `manual`로 받는다. 7일 안의 같은 원본 해시 OS 이벤트는 새 행이 아니다. 연관 API는 같은 장치·같은 사용자의 기록을 시간 창(기본 ±5분, 최대 ±60분) 안에서 각자의 출처·시각으로 따로 나열하고 하나의 사건으로 합치지 않는다. 하네스가 보낸 `traceparent`는 형식이 맞을 때만 `decisions.client`에 기록하며 연결의 근거나 인가에 쓰지 않는다.
- 이유: 시각이 겹친다는 것은 같은 행위라는 증거가 아니다.
- 한계: 출처 라벨은 장치 키를 가진 쪽의 자기 신고다. 호출에 장치 바인딩(`device_id`)이 없으면 엔드포인트 기록을 연결하지 않는다.

## D-88 엔드포인트→게이트웨이 망 품질은 설정된 Gateway 주소에 대한 프로브 요약이다 (2026-10-15)

- 결정: 하트비트마다 TCP 연결 5회와 `/api/health` 1회를 측정해 p50·p95(최근접 순위)·지터·실패율을 `network_quality`로 보낸다. 서버는 NaN·음수·상한 초과·분위수 역전·허용 밖 시각을 거부하고(하트비트는 유지, 응답에 `rejected`) 정상 값을 `endpoint_network_samples`에 적재하며 7일 지난 행을 지운다. `GET /api/endpoint/network-quality`는 장치별 최신 값과 24시간 요약을 돌려주고 하트비트 3회분(180초)보다 오래된 값은 `stale`이다.
- 이유: 설정된 Gateway 주소와의 연결 상태를 가입자 단말에서 관측해야 지연이 보인다.
- 한계: 지연은 TCP 연결 시간이고 HTTP 호출 시간은 실패 판정에만 쓴다. 실패율은 패킷 손실이 아니다. 측정 주체는 root 서비스라 일반 계정의 경로와 같다고 단정하지 않는다.

## D-89 OS 거부는 프로세스 정보와 분류를 갖고, 통제 밖 계정은 그렇게 표시한다 (2026-10-15)

- 결정: AppArmor 거부에 실행 시도 프로세스·프로파일·파일명을 담고, 시도한 프로세스가 `claude`/`codex`이고 대상이 시스템 경로의 `git`·`claude`·`codex`일 때만 `harness_startup`으로 분류한다. 그 밖의 exec 거부는 `blocked_attempt`, 프로세스·작업을 모르거나 네트워크 거부는 `unknown`이다. 프로파일과 nft 규칙은 바꾸지 않는다. 같은 단말의 다른 계정은 `통제 범위 밖`으로 API(`unmanaged_accounts`)와 Console에 표시한다.
- 이유: 정상 기동 거부가 대부분을 차지하면 우회 시도가 묻힌다. 분류는 보이는 것을 접을 뿐 숨기지 않으며 우회 시도는 그대로 노출된다.
- 한계: `comm`은 스레드 이름이 될 수 있고 사용자 쓰기 경로의 같은 이름 바이너리는 `blocked_attempt`로 본다. Windows 이벤트는 분류하지 않는다(`unknown`).

## D-90 도입 승인마다 출처·고정 버전·라이선스·배포 파일 해시를 남기고, 검사가 비었거나 낡았으면 보류한다 (2026-10-15)

- 격리 워커는 복제한 소스 트리의 파일 해시 목록(`경로별 sha256`을 정렬해 다시 sha256)과 Trivy 라이선스 분류 결과, 그리고 그 검사가 쓴 취약점 DB의 갱신 시각(`trivy version --format json`)을 남긴다. 승인 때 Gateway 쪽이 내부 Git(Gitea) 사본의 보관본을 받아 같은 방식으로 해시를 다시 계산하고, 직원에게 보이기 전에 기록과 대조한다. 두 구현은 빌드 문맥이 달라 파일이 둘이며 `tests/provenance_check.py`가 같은 값을 내는지 본다.
- 출처 기록이 없거나(공급 주소·40자리 커밋·라이선스·해시), 사본 해시가 다르거나, 검사기가 실패·누락됐거나, 취약점 DB가 7일(`provenance.VULN_DB_MAX_AGE`)보다 오래됐거나 시각이 없으면 승인하지 않고 요청을 보류(`HOLD`)한다. 보류도 승인 기록(`approval_events`)에 남는다. 제공자가 운영하는 원격 서비스는 해시를 만들지 않고 "해당 없음"과 엔드포인트·광고 버전·계약 해시를 기록한다. 검사기가 읽지 못한 라이선스는 승인자가 직접 적을 수 있고 그 사실이 기록된다.
- 치명적 발견은 자동 거부하지 않고 보류한다. 다른 관리자가 사유·기한(1~30일)으로 `accepted_risks`에 수용을 남기면 승인할 수 있다. 수용은 검증한 커밋과 발견 id에 묶이고, 기한이 지나면 요청이 보류로 돌아가며 Gateway는 원래의 치명 건수를 다시 본다(`MCP-SUPPLY-001`). 등록할 때 검사 보고서를 서버의 `source_ref`에 연결해 이 차단이 실제 호출에 닿는다.
- 한계: 라이선스는 저장소 루트의 라이선스 파일만 읽는다(Trivy `--license-full`). `.gitattributes`의 `export-ignore`·`export-subst`가 있는 저장소는 보관본과 체크아웃이 달라 보류될 수 있다(fail-closed). 갱신은 재검사를 하지 않는다. 실기기의 현재 취약점 DB는 2026-10-06분(9일)이라 이 기준이면 지금은 승인이 막힌다.

## D-91 Console 등록은 도구마다 사람이 승인한 범위가 있어야 하고, 없는 도구는 목록에서도 호출에서도 빠진다 (2026-10-15)

- 등록할 때 승인한 도구마다 목적·자산·외부 목적지를 사람이 적는다(행위는 승인한 r/w/x를 따른다). 범위가 없는 도구는 `mcp_tools.enabled=false`라 `tools/list`에 나오지 않고 호출하면 `MCP-REGISTRY-002`다. 이미 등록된 서버는 `POST /api/registry/servers/{id}/tool-reviews`(신청자가 아닌 관리자)나 `tests/tool_scope_review.py`로 범위를 채운다. 그 전까지 그 도구들은 꺼져 있다 — 의도한 fail-closed다.
- 한계: 외부 목적지는 기록·표시만 한다. 외부로 나가는 호출은 지금도 PAC 전송 검사가 모두 막으므로 목적지 허용 목록으로 풀어 주는 집행은 아직 없다. 인자 범위(JSON Schema)와 사용자 범위는 기존 원격 검토 그대로다.

## D-92 신청자는 자기 신청을 승인할 수 없고, 모든 승인은 되돌릴 수 없는 기록으로 남으며, 무효 행은 주석으로 표시한다 (2026-10-15)

- 신청자≠승인자를 서버가 강제하는 곳: 도입 승인, 원격 계약 검토, 위험 수용, 도구 범위 심사, 건별 호출 승인. 막힌 시도도 `refused`로 남는다. Console은 신청자에게 승인 버튼을 내지 않지만 규칙은 서버에 있다.
- `approval_events`(append-only 트리거)에 승인자·신청자·사유·범위를 남긴다. 신청 때 신청자가 남기는 `user-consent`는 운영자 승인과 별도 기록이다.
- `audit_annotations`(append-only)로 `decisions.id` 범위를 "무효 처리"한다(관리자 API, 사유 10자 이상). 판정 행과 해시 체인은 건드리지 않으며 활동·감사 화면이 표시를 단다. D-79의 원장 744~800은 배포 뒤 이 API로 주석을 단다(이번 작업에서 제품 DB에는 쓰지 않았다).

## D-93 만료·철회·계약 변경은 모두 재승인이고, 하네스 설정은 사람이 볼 수 있는 서버만 담는다 (2026-10-15)

- 만료 → `P-APPROVAL-EXPIRY-001`, 철회(등록 해제) → `MCP-REGISTRY-001`·목록에서 제외, 계약 변경 → `MCP-CATALOG-001`. 자동 연장은 계약 일치·서버 정상에 더해 도입 신청이 `APPROVED`로 남아 있고 승인한 모든 도구의 범위 심사가 있을 때만 하며, 이미 만료된 승인은 되살리지 않는다.
- 관리형 하네스 설정(Claude·Codex)과 `tools/list`가 같은 판단(`pac.visible`)을 쓴다. 사용자에게 허용된 서버가 아니거나 철회·미심사인 서버는 설정에 들어가지 않는다. 정책 해시가 바뀌므로 엔드포인트는 다음 점검에서 새 설정을 받는다.
- 한계: 이미지 빌드용 `workstation/managed/render.py`는 `catalog.toml` 전체를 그리는 시험용이라 이 규칙 밖이다.

## D-94 PAC-05 위임 실행은 "지원 안 함"을 명시하고, 위임을 주장하는 호출은 전용 정책으로 거부한다 (2026-10-15)

- `act`·`may_act`·`on_behalf_of` 같은 토큰 클레임이나 위임 헤더로 "누군가를 대신한다"고 주장하는 호출은 전송 계층에서 검증한 에이전트 신원이 없으므로 `PAC-05-DELEGATION-UNSUPPORTED`로 거부한다(관찰 모드에서도 풀리지 않는다). 주장이 없는 호출은 영향이 없다. `clientInfo`·User-Agent는 "검증 안 된 출처"로 기록만 하고 판정에 쓰지 않는다. 위임을 허용하려면 검증된 에이전트 주체(`facts.delegation.actor_verified`)가 먼저 있어야 하며 그 뒤에도 사용자·에이전트·위임의 교집합 규칙이 적용된다. Console 정책 화면은 이 항목을 "지원 안 함"으로 표시한다.

## D-95 도구 호출의 구간별 처리 시간을 판정과 함께 남기고 콘솔에 보인다 (2026-10-15)

- 결정: `core._Laps`가 신원 확인·호출 예약·입력 형식·입력 검사·정책 입력·정책 판정·전송 준비·서버 연결·계약 재확인·실행 전 재판정·도구 실행·세션 종료·출력 검사와 전체 시간을 ms로 재고, 판정 행 `decisions.timings`(jsonb)에 함께 쓴다. `GET /api/latency`(관리자)는 창 안의 게이트웨이 처리(전체−업스트림 구간)·MCP 서버 응답·구간별·서버별·시간대별 중앙값과 95% 값을 돌려준다. 콘솔은 대시보드 요약 카드, `지연` 탭, 호출 상세의 `처리 시간` 탭에 보인다. 엔드포인트 왕복은 D-88의 측정을 쓴다.
- 이유: 지연을 줄이려면 어디서 시간이 드는지가 먼저 보여야 한다. 기존 표시는 콘솔→게이트웨이 TCP 연결 시간 하나였다.
- 감사 경계: `timings`는 판정 지문 밖의 운영 정보다(무엇을 판정했는지가 아니라 얼마나 걸렸는지). 원장은 여전히 추가만 하며 기록 뒤에 수정하지 않는다. 기록 자체에 드는 시간은 그 행에 들어가지 않는다.
- 한계: 구간 합과 전체가 다를 수 있다(승인 요청 저장 등 구간 밖 처리). 이 기능 이전의 판정 행에는 값이 없다.

## D-96 보내기 직전의 전송 의도를 같은 DB에 먼저 적고, 답이 없는 호출은 자동 재시도하지 않는다 (2026-10-15)

- 결정: `dispatch_intents`(판정 원장과 별개 표)에 `tools/call`을 보내기 직전 한 문장으로 의도를 쓴다. 같은 문장이 예약(열림·미만료)·주체(active)·서버(OPERATING)를 확인하고 서버 행을 공유 잠금으로 잡는다. 판정을 기록한 뒤 예약 해제와 같은 문장에서 닫는다: 답이 확정되면 `resolved`, 시간 초과처럼 답이 없으면 `uncertain`(자리는 풀지 않음). 프로세스가 죽으면 `pending`으로 남고 예약이 사라지면 `uncertain`과 같이 취급한다. 미확인 쓰기(`w`/`x`)가 있으면 같은 호출은 `P-RATE-003`으로 막는다(읽기는 막지 않는다). `GET /api/dispatch-intents`, `POST …/resolve`로 관리자가 하위 시스템을 확인한 결과(실행됨/실행 안 됨)를 적으면 풀린다. 승인된 호출은 같은 트랜잭션에서 승인이 승인한 서버·도구·인자·주체와 보내려는 호출이 같은지 확인하고 승인을 소비(`APPROVED`→`UNCONFIRMED`)해, 승인 id를 두 번 쓰거나 다른 요청에 쓰면 전송이 경계에서 멈춘다(변형 요청이 기존 승인 id로 `execute_call`을 직접 부르면 쓰기 호출이 실행되던 것을 격리 랩에서 재현해 고쳤다. PAC-13 다이제스트는 고위험 `x`에만 걸리고, 외부에서 닿는 경로 `approve_request`는 저장 payload의 지문을 따로 확인하므로 방어를 한 층 더한 것이다). Console 승인 대기 화면에 "실행 확인" 탭.
- 이유: 판정 원장은 답이 온 뒤에 쓰이므로 전송 후 프로세스가 죽으면 흔적이 없고, 예약이 만료되면 같은 쓰기가 다시 나갔다. 실제 Gitea MCP 서버에서 프로세스를 SIGKILL한 격리 랩으로 확인했다(보낸 호출은 효과 1, 보내기 전 사망은 효과 0, 둘 다 `pending`으로 남고 45초 예약 만료 뒤에도 같은 호출 거부, 자동 재시도 없음).
- 비용·한계: 전송 직전 DB 왕복 한 번(실행 기록 단계, 격리 랩 p50 4.4ms·p95 7.1ms, 총 처리 p50 231ms 중). 동기 커밋을 끄지 않았다 — 의도가 PostgreSQL 장애에서도 남아야 하기 때문이다. 읽기 도구의 미확인은 차단하지 않고 목록에만 보인다. 같은 호출이라도 앞의 호출이 끝난 뒤 다시 보낸 것은 별개 요청이다(중복 방지는 진행 중·미확인에 한정). `pac.py`의 미확정 변경 조회는 관리자 확인이 끝난 호출을 제외한다.

## D-97 차단 시각은 DB가 정하고, 전송 경계가 그 시각을 넘는 호출을 막으며, 따뜻한 연결을 닫는다 (2026-10-15)

- 결정: 종료 개시 트랜잭션이 서버 행을 `FOR UPDATE`로 잡은 뒤 `clock_timestamp()`를 `cutover_at`으로 쓴다. 전송 의도는 같은 행을 `FOR SHARE`로 잡으므로 호출은 cutover 전에 기록되거나 이후에 `MCP-DECOMM-001`로 거부된다(240건 경쟁에서 35건 기록·205건 거부, cutover 뒤 기록 0). 종료 개시와 계정 중지·삭제는 `upstream_pool_events`에 행을 남기고 이 프로세스의 풀을 즉시 비운다. 다른 게이트웨이 프로세스는 다음 풀 사용 시(2초 간격 이내) 읽어 닫는다. 쓰는 중인 연결은 호출이 끝나는 대로 닫는다. 자격이 바뀌거나 빠져 풀 키가 달라지면 같은 (엔드포인트, 주체)의 이전 클라이언트를 닫는다.
- 이유: 최종 재판정과 전송 사이의 틈에서 개시된 종료가 진행 중인 호출을 막지 못했고, 풀의 클라이언트는 만든 때의 자격 헤더를 계속 쥐고 있었다.
- 한계: 쓰는 중인 호출의 연결을 끊지 않는다(끊으면 새 미확인이 생긴다). cutover 전에 보내 뒤에 답한 호출은 C3에서 실행된 호출로 그대로 세고 `straddled`로 따로 보인다. 아무 호출도 없는 다른 프로세스는 풀 소켓이 유휴 만료(60초)될 때까지 연결을 가질 수 있으나 그 연결로 새 전송은 불가능하다. 보낸 뒤 원장에 남지 못한 호출은 판정에서 실행 여부 미확인으로 센다(케이스 T3, `TERMINATION_MODEL.md`).

## D-98 제공자 측 폐기는 보호 자원이 이전 토큰을 거부하는지로 본다 (2026-10-15)

- 결정: 증거 종류 `resource-rejection`을 더한다. 조직이 제공자에게 준 토큰의 사본 파일(`GITEA_PROBE_TOKEN_FILE` 또는 자격별 `probe_token_file`)이 있으면 폐기 전에 한 번, 폐기 뒤에 한 번 보호 자원(`GET /api/v1/user`)에 제시한다. 401/403이면 거부, 2xx면 수락(잔존 접근, C3 미충족·`provider_side=accepted`), 물을 수 없으면(설정 없음·읽을 수 없음·자원 불능) 증거를 만들지 않고 `provider_side=unverified`와 만료 시각만 남긴다. 자원의 응답이 관리 API 목록의 부재보다 우선한다. 제품 스택에는 사본이 없어 기본값은 `unverified`이며 기존 등급 계산은 바뀌지 않는다.
- 이유: 발급자가 목록에서 지웠다는 사실만으로 자원 서버가 거부한다고 볼 수 없다(`TERMINATION_MODEL.md` §1).
- 한계: 같은 값을 아는 조직이 가진 자격에만 적용되고, 다른 자원 서버·복제된 자격은 증명하지 못한다. 값은 어떤 행에도 쓰지 않는다(상태 코드만). 격리 랩의 일회용 Gitea 1.27.3에서 폐기 전 200, 폐기 뒤 401, 운영자가 폐기로 적었지만 지우지 않은 토큰은 200(→T2)을 확인했다.

## D-99 토큰 폐기의 범위와 자격 제거의 범위를 정한다 (2026-10-15)

- 결정: 리프레시 토큰 폐기·재사용 탐지·계정 중지·장치 폐기는 해당 계열/주체/장치의 모든 액세스 토큰을 다음 요청부터 거부한다(API와 MCP ingress 모두 `authenticated_user`). 액세스 토큰 하나의 폐기(RFC 7009)는 그 토큰만 폐기한다 — 논문 E1이 재현하는 성질이라 바꾸지 않는다. 발급과 폐기를 경쟁시켜도 계열에 살아 있는 토큰이 남지 않고, 발급 실패는 회전과 접근 토큰 기록을 함께 되돌린다(실제 서명 토큰·PostgreSQL 12회 경쟁). 폐기된 장치의 키는 어느 범위도 인증하지 못하고 heartbeat로 되살릴 수 없으며 이미 발급된 장치 토큰도 즉시 거부된다.
- 이유: WBS G07.01/G07.04. 기존 PG 검사는 토큰 서명을 대체한 고정 스키마였다.
- 한계: 직원 PC의 작업 백업·캐시·내보낸 파일은 게이트웨이가 통제하지 않아 검증하지 않았다(엔드포인트 에이전트 영역). 게이트웨이가 쓰는 증거·원장·판정서·고지 요청서에는 토큰 값과 끝 8자리가 없음을 격리 랩에서 확인했다.
## D-100 텍스트 검사 규칙은 공개 코퍼스로 재고, 정상 결과를 막는 오탐을 먼저 없앤다 (2026-10-15)

- 결정: `tests/inspection_corpus_eval.py`가 고정 커밋·SHA-256으로 검증한 공개 자료 189개 파일에서 표본 9,463건(공격·정상, 표본 자신의 해시로 dev 5,679·held-out 3,784)을 만들고, 결과(`core._guarded_result`)·인자(`core.untrusted_markers`)·계약(`poisoning.findings`)을 **실제 함수로** 판정한다. 규칙은 dev에서만 고치고 held-out은 개수로만 확인했다. 자료는 저장소에 두지 않는다(MCPTox는 라이선스 파일이 없어 읽기만 한다). 새 시험 `tests/korean_pii_eval.py`와 같은 원칙이다.
- 출처: garak(PyRIT ea9d0b4 경유, Apache-2.0)·yanismiraoui 다국어 주입(Apache-2.0)·jackhhao 탈옥(Apache-2.0)·InjecAgent(MIT)·MCPTox(공격 485·정상 342 설명)·CPython·Express 코드·loghub 로그·PokeAPI JSON·Kubernetes 영·한 문서·OWASP/garak/PyRIT 보안 문서, 합성 한국어 120문장(`tests/data/synthetic_ko_inspection.json`, 공개 코퍼스가 아님). 한국어 공개 프롬프트 주입 코퍼스는 찾지 못했다.
- 결과 경로: 정상 1,978건 중 오탐 **91 → 0**(dev 53→0, held-out 38→0). 원인은 보이지 않는 문자 규칙(BOM 40건·ZWJ 이모지 40건 전부 보류)과 지시 무시 규칙의 넓은 목적어(urllib `# ignore POSTed data`, logging HOWTO `ignore DEBUG messages`, 알림 메일 `ignore this message`)와 정책 우회 규칙(Pod Security Standards `disable most security mechanisms`)이었다. 탐지율(범위 안 공격 3,501건)은 0.494 → 0.495(dev 0.492→0.496, held-out 0.498→0.494). 인자 경로 오탐 89 → 0, 탐지율 0.521 → 0.530. 계약 경로는 MCPTox 공격 485건 중 132 → 254(0.272 → 0.524, held-out 0.244 → 0.518), 정상 342건 오탐 0 유지(새 규칙 `선행 호출 강요`: "Before X you MUST FIRST call Y").
- 줄어든 것: 탈옥 서술의 "system message/prompt"·"ignore ... rules/messages"에 기대던 탐지(탈옥 195 → 172/666, 시스템 프롬프트 요구 질문 8 → 5/28). 이 규칙은 정상 문서(OWASP 페이지, syslog 설명)에서도 걸리던 것이라 좁혔다.
- 측정만 하고 고치지 않은 것(결과 규칙은 좁게 둔다): 명령형만 있고 무시 표현이 없는 도구 응답(InjecAgent base 1,054건 0% — 위험 도구 호출은 정책·승인이 막는다), 설득문, 다국어 의역(yanismiraoui 0.6%, 의미 분류기가 할 일), rot13·역순·leetspeak·글자 사이 공백(디코드 단계를 모델이 직접 따라야 해서 도구 출력이 실어 오지 않는다), 같은 말을 정직하게 쓰는 보안 문서(OWASP 3/6 보류).
- 입력 게이트(G04.01): 64 KiB 초과·형식 불일치(정수·배열·null·추가 속성·`__proto__`·필수 누락)는 `P-INPUT-SCHEMA-001`로 차단, 표지(비신뢰 지시)는 쓰기·실행 `P-UNTRUSTED-CONTENT-001`(승인)·읽기 `-002`(경보)이며 OPA 시험 91/91. PayloadsAllTheThings 경로 조작 1,468줄은 전부 important로 분류, 정상 경로 11건 기대 등급과 일치. **미해결**: 인자나 결과 문자열의 `\u0000`은 MCP SDK 파서가 받고 감사 저장소(jsonb)가 거부한다(`UntranslatableCharacter`, 일회성 Postgres 18에서 재현) — 판정 행을 쓰지 못한다. `core.execute_call`·`_audit_payload`의 몫이며 이 변경에서는 고치지 않았다.
- 한계: 합성 한국어 표본은 규칙을 읽은 같은 작성자가 썼다(독립 검증 아님). dev·held-out은 같은 출처에서 갈랐으므로 새 출처에는 일반화되지 않는다. 지연: 파이썬 대체 경로의 규칙 검사는 약 2.5배(규칙 수 증가), 네이티브 엔진은 200 KB 6.5 ms(`textscan_parity_check` 31/31 규칙 네이티브, 원자·퍼즈 차이 0).

## D-101 결과·인자에서는 보이지 않는 문자를 가려 읽고, 인코딩은 풀어서 한 번 더 읽는다 (2026-10-15)

- 결정: 계약은 모든 서식 문자를 표시하지만(관리자가 볼 수 없는 글자), 결과·인자는 유니코드 태그 문자, 방향 덮어쓰기(U+202D·202E), ASCII 글자 사이의 폭 없는 문자만 문제로 본다. 그 밖의 U+FEFF(파일 머리의 BOM)·U+200D(이모지 결합)·U+200C·U+200F는 일상 텍스트다.
- 결정: `poisoning._variants`가 호환 문자(전각)·서식 문자·키릴/그리스 유사 글자·`%xx` 3개 이상·숫자 엔터티 3개 이상·base64/hex 덩어리를 풀어 만든 읽기를 규칙에 한 번 더 넣는다(원문과 다를 때만). 풀 수 있는 변형 7종은 결과 경로 garak 시드 1/182 → 112/182(평문이 잡는 16/26과 같은 수준). 숫자가 없는 알파벳만의 덩어리는 식별자로 보고 풀지 않는다(문장의 base64가 숫자·기호 없이 24자 이어질 확률 1% 미만).
- 이유: 인코딩은 목록의 규칙을 그대로 우회하는 가장 값싼 방법이었다. 한 번 더 읽는 비용은 원문이 비ASCII이거나 이스케이프가 있을 때만 든다. 모든 규칙은 입력 길이에 선형(퍼즈·병리 입력 10종 시험 포함)이고 네이티브 엔진으로 옮겨진다.
- 한계: 두 번 겹친 인코딩, rot13·역순·leetspeak은 읽지 않는다. 디코드 결과가 규칙에 걸릴 때만 막으므로 인코딩 문장 자체는 계약의 `인코딩된 문장`(D-73)이 따로 표시한다.

## D-102 한국어 식별자는 한국어로 쓰인 그대로 가려야 한다 — 단어 경계 대신 "라틴 문자·숫자가 아님" (2026-10-15)

- 측정(`tests/korean_pii_eval.py`, 일회성 Presidio 컨테이너 + 합성 식별자, 정상 유사 46건): 기존 인식기는 `\b`를 써서 조사가 붙은 값("010-0000-1234입니다")을 놓쳤다 — 주민번호 36/48(조사 없는 경우만), 휴대폰 24/80, 이메일 21/24, 공급자 토큰 19/30, 비밀번호 8/27. 외국인등록번호·유선전화·`+82`·사업자등록번호·계좌·여권·면허번호는 인식기가 없었다. 이후 전부 마스킹(비밀번호 라벨이 공백뿐인 "(비밀번호 값)" 형태는 정상 문장과 겹쳐 제외). 정상 유사 46건 중 마스킹 2 → 1(날짜 모양의 13자리 주문번호는 체크섬을 패턴이 확인할 수 없어 그대로 주민번호로 읽힘).
- 결정: 인식기와 외부 전송 DLP 패턴 모두 `(?<![0-9A-Za-z])…(?![0-9])`를 쓰고, 모양이 없는 번호(사업자·계좌·여권)는 라벨 뒤에서만 마스킹하며 라벨은 남긴다(날짜는 계좌가 아니다). 카드번호는 한국어에 안전한 경계의 임시 인식기가 잡고 `analyze`가 Luhn을 검사한다. 비밀번호·키는 한국어 라벨("비밀번호는 …")과 환경 변수형 이름(`DB_PASSWORD=…`)까지 읽는다. DLP에 `kr-business-number`·`kr-account`·`kr-passport`·`kr-driver-license`를 더했고, 유선전화는 외부 전송 거부 사유로 올리지 않는다(사무실 번호를 메일에 쓰는 일이 일상이라).
- 지연: 새 인식기만으로 `mask_text` 호출 중앙값 9.5 → 12.8 ms(인식기를 요청마다 임시로 컴파일). 그런데 분석기 호출 시간의 대부분은 인식기가 아니라 spaCy 파이프라인이다 — 2 KB 텍스트 한 번에 약 40 ms 중 34 ms가 신경망 NER·의존 구문 분석이고 게이트웨이는 패턴 엔티티만 쓴다. `privacy/analyzer.Dockerfile`이 NER·parser를 뺀 파이프라인을 만들고(`nlp-small.yaml`의 모델 경로) 토크나이저·태거·표제어는 남겨 문맥 단어가 그대로 작동하게 했다. 일회성 파생 이미지로 잰 값: 분석기 2 KB 42.8 → 23.6 ms, 200 B 11.4 → 7.9 ms, `mask_text` 중앙값 12.8 → 10.3 ms·p95 15.9 → 12.9 ms, 100 KB 병리 입력 최대 6.8 → 3.2 s, 한국어 시험 전 범주 마스킹·정상 유사 46건 결과 동일, 카드·IBAN·US_SSN(문맥 포함) 동일. 토크나이저만 남기면 2 KB 6.8 ms(−84%)이고 100 KB 입력도 0.4 s 안이지만 문맥 단어에 기대는 US_SSN이 탐지되지 않는다(소유자가 US_SSN을 목록에서 뺄지 정할 일). 기존 이미지를 밑으로 한 파생 이미지로만 확인했고 업스트림 이미지에서 처음부터 다시 빌드하지는 않았다.
- 한계: 모든 값은 합성이다(2097~2099년생·0000 대역). 라벨 없는 사업자번호·계좌는 가리지 않는다. 콘솔은 `privacy_types`를 원문 영어 이름으로 보인다(`agent_static/console.js`, 이 변경의 몫이 아님).

## D-103 협업 콘솔은 실행마다 요청·응답 모델과 실패 종류를 CLI 출력에서만 채운다 (2026-10-15)

- 결정: 실행마다 `runtime/runs.jsonl`에 추가만 하는 기록(마지막 레코드가 현재 상태)을 남기고 화면·`/api/runs`가 보인다. 응답 모델은 제공자 응답이 실어 온 값(`assistant.message.model`, `result.modelUsage`)만 인정하고, `system.init.model`은 CLI가 되돌려 준 요청이라 `cli_model`로만 둔다(없는 모델을 요청해도 그대로 돌아오는 것을 이 PC의 실제 인증 실패 출력에서 확인). Codex `exec --json`은 모델을 보고하지 않으므로 항상 미보고이고, Codex가 턴에 적용한 값은 세션 파일의 `turn_context`에서 읽어 별도로 `applied`에 둔다.
- 종류: 턴 오류(`assistant.error`·`result.is_error`·`turn.failed`), 사용량 한도(`rate_limit`·429·`rate_limit_event rejected`·`usage_limit_exceeded`·한도 문구), 작업 실패(제공자 오류 없이 프로세스 실패), 모델 불일치(자동 대체 없이 중단), 중단, 도구 호출 0건 표지, 게이트웨이 기록은 호출 수를 센 사람이 `gateway-records`로 넘긴 값만(`unverified`·`none`·`recorded`). 원시 출력은 `runtime/raw/`에 비공개로 보관한다.
- 이유: D-79에서 로그가 없던 원인이 게이트웨이가 아니라 한도 오류로 시작도 못 한 모델 턴이었는데 화면은 이를 구분하지 못했다. 기존 코드는 init 에코를 "모델 응답 확인"으로 세던 오류도 있었다.
- 한계: 한도 거부 출력은 이 PC에서 재현하지 못했다. 분류는 실제 레코드의 필드(`rate_limit_event`, `assistant.error`, Codex 세션의 `usage_limit_exceeded`)에 기대고, 시험은 그 필드 이름으로 만든 스트림을 쓴다. Codex 성공 스트림은 공개 문서의 항목 유형을 따르며 이 PC의 Codex가 모델 미지원 오류를 내서 성공 실행을 받지 못했다.

## D-104 관리 하네스의 bash는 헬퍼 권한이 없는 도구 프로필에서 실행한다 (2026-10-15)

- 결정: 관리 계정 하네스 프로필(`{계정}-{claude|codex}`)에서 `dash`/`sh`는 그대로 상속(ix)하고 `/usr/bin/bash`는 `{계정}-{하네스}-tool` 프로필로 전이한다. 도구 프로필은 하네스와 같은 파일·네트워크·실행 한계를 갖되 `header-helper` 실행과 자격 소켓 접근이 없다. bash가 실행하는 모든 것(안의 `sh` 포함)은 도구 프로필에 머문다.
- 이유: E13 C9에서 모델이 Bash로 `header-helper`를 실행해 장치 토큰을 얻고 게이트웨이에 직접 요청했다(DEV-31). Claude Code는 `headersHelper`를 `shell: true`(=`/bin/sh -c`, Ubuntu에선 dash)로, Codex(공개 소스 bb64b89 `rmcp-client/src/http_headers.rs`)는 `sh -c`로 실행하고, Claude의 Bash 도구는 bash를 쓴다. 그래서 dash와 bash를 나누면 하네스의 MCP 인증은 유지하고 Bash 자식의 토큰 획득만 막힌다.
- 한계: Codex의 셸 도구는 모델이 실행 인자를 직접 정하므로 `sh -c …`나 헬퍼 경로를 바로 실행하는 경로가 남는다(프로필로 구분 불가). 토큰은 수명이 짧고 장치에 묶이지만 송신자 제약(DPoP·mTLS)은 없다. 키트 재설치로 적용되며 PJ1 실기기 확인은 작업 보고에 따로 남긴다.

## D-105 재설치 때 하네스의 "로그인 필요" 표시를 지운다 (2026-10-15)

- 결정: 관리형 설치(`managed-linux.py install`)가 관리 계정의 `~/.claude/mcp-needs-auth-cache.json`을 링크를 따라가지 않고 지운다.
- 이유: 관리 계정의 홈은 재설치 뒤에도 남는다. 이전 장치 시절의 401로 Claude Code가 남긴 표시 때문에 새 장치의 github·context7이 "인증 필요"로 숨겨졌다(2026-10-15 PJ1 재현). 관리 서버는 장치 헬퍼로 인증하므로 이 표시는 쓸모가 없다.

## D-106 관리자 Console 세션은 서버에서 유휴와 절대 만료를 함께 강제한다 (2026-10-15)

- **문제**: SSO access token 만료가 관리자 Console 세션을 30분으로 제한했고, 브라우저의 유휴 타이머만으로는 서버 측 세션 만료를 보장하지 못했다.
- **결정**: 관리자는 유휴 30분 또는 로그인 후 8시간 중 먼저 도달할 때 종료한다. OIDC access token은 짧게 유지하고, 서버가 암호화 보관한 온라인 refresh token으로 만료 전에 갱신한다. 브라우저는 실제 사용자 활동에만 heartbeat를 보내며, 서버가 그 시각을 저장한다. refresh token은 회전 시 교체 저장하고 브라우저에 노출하지 않는다.
- **폐기**: 로그아웃 시 로컬 세션을 즉시 무효화하고 제공자 revocation endpoint가 있으면 access token과 refresh token 폐기도 요청한다. refresh token이 발급되지 않은 관리자 SSO 응답은 정책을 충족하지 못하므로 로그인에 사용하지 않는다.
- **한계**: OIDC 제공자 설정이 online refresh token을 발급하고 8시간 세션을 허용해야 한다. 제공자 세션이 먼저 만료되거나 갱신에 실패하면 세션은 fail-closed로 끝난다.

## D-107 직원 계정 런처는 관리 계정의 진입 래퍼를 절대 경로로 부른다 (2026-10-15)

- 문제: 관리 계정에서 Claude 로그인을 하면 Claude 설치기가 `~/.local/bin/claude`를 만들고, 관리 계정의 `.profile`이 그 경로를 PATH 앞에 둔다. 런처가 `claude`라는 이름만 넘기자 미승인 설치본이 실행됐고 AppArmor가 거부해 직원이 하네스를 아예 쓰지 못했다(PJ1).
- 결정: `/usr/local/bin/{claude,codex}` 런처는 로그인 셸 옆의 진입 래퍼(`/usr/local/lib/mcpgw-enforcement/mcpgw-<관리 계정>/<이름>`)를 절대 경로로 실행한다. 승인 바이너리로 들어가는 프로필 전환은 그 래퍼에만 있다.
- 되돌릴 조건: 관리 계정의 셸 초기화 파일을 설치기가 소유하게 될 때.

## D-108 소스 신청 등록의 사용 범위는 솔루션이 정한다 (2026-10-15)

- 문제: 현장 모드의 정책 번들은 비어 있고(검토된 등록만), 원격 신청만 계약 검토에서 허용 사용자·인자 범위를 받았다. 소스 신청으로 등록한 서버는 누구도 쓸 수 없었다. 관리자에게 JSON Schema를 쓰게 하는 것도 제품 사용자에게 맞지 않는다(사용자 지시: 주소만 넣으면 솔루션이 판단).
- 결정: 소스 신청 등록은 신청자에게 허용하고, 도구마다 고정한 계약의 입력 인자만 받도록 닫으며(`additionalProperties: false`), 주소를 뜻하는 인자(`url`·`uri`·`href`·`link`·`endpoint` 또는 `format: uri`)는 심사한 외부 목적지의 HTTPS로 제한한다. 목적지를 다시 심사하면 패턴도 따라 바뀐다. 원격 계약 검토에서 인자 범위를 비우면 같은 방식으로 만든다.
- 근거: PJ1에서 MarkItDown의 `file:///etc/passwd`·미심사 호스트 요청이 실행 전 PAC-01로 차단되고 심사한 호스트는 실행됐다.
- 한계: 주소가 아닌 이름의 인자 안에 든 주소는 PAC 전송 검사에 맡긴다. 다른 사용자에게 열려면 새 도입 신청이 필요하다.

## D-109 객체가 아닌 structuredContent는 빼고 text로 전달한다 (2026-10-15)

- 문제: GitHub 공식 MCP가 `list_commits` 등의 `structuredContent`를 배열로 보낸다(규격은 객체). 게이트웨이가 결과 전체를 보류해 목록형 도구를 쓸 수 없었다.
- 결정: 객체가 아닌 구조화 결과는 클라이언트에 넘기지 않는다. 같은 데이터가 text에 있으면 그대로, text가 비어 있으면 그 JSON을 text로 넣는다. 검사는 원래 결과 전체에 대해 하고, 원장의 응답 증거에 `structured_dropped`를 남긴다.
- 정정(10-15 검토 RV-05): "규격은 객체"는 2025-11-25 판의 설명이다. 2026-07-28 판은 outputSchema에 맞는 모든 JSON 값을 허용한다. 하네스가 게이트웨이와 협상하는 판이 섞여 있어 text로 통일하는 결정은 유지하되, 판본별 처리와 outputSchema 계약은 DEV-44에서 정한다.
- 되돌릴 조건: 하네스 쪽이 모두 2026-07-28 이상이 되어 배열 구조화 결과를 그대로 받을 수 있을 때.

## DEV-29 설계 제안 이력 — 1단계 D-110·2단계 D-115 채택, 3단계 미채택 (2026-10-15, 10-17 갱신)

제안 당시 내용은 아래에 보존한다. 2026-10-17 사용자는 2단계까지 채택했다. 현재 수명은 D-115, 호출별 `tools/list` 재확인은 그대로다. 1단계의 자동 재협상 제안은 D-110 코드에서 채택하지 않았으며 판 변경 시 실패 후 재검토한다.

- **1단계(보안 경계 변경 없음) — D-110으로 채택**: 카탈로그에 기록한 프로토콜 판으로 SDK 연결 모드를 고정한다. 구형(`2025-11-25`) 서버는 `server/discover` 탐색 왕복을 없애고, 신형(`2026-07-28`) 서버는 핸드셰이크·세션 종료 요청이 없어진다. 판이 바뀌어 연결이 실패하면 그 호출 안에서 한 번 `auto`로 다시 연결한다.
- **2단계(D-79 개정)**: 업스트림 세션을 `(주체, 다운스트림 Mcp-Session-Id, 서버, 자격 해시)`에 묶어 유휴 60초·최대 10분 재사용한다. 다운스트림 세션 ID가 없으면 재사용하지 않는다. 주체 중지·서버 종료(`release_pool`)·자격 교체·전송 오류에서 닫고, 재사용 `Client`는 SDK 응답 캐시를 끈다. 승인·주체·관리형 장치·OPA·`dispatch.record`·`tools/list` 재확인은 호출마다 그대로 한다.
- **3단계(별도 결정)**: 카탈로그가 읽기로 검토한 도구에 한해 `tools/list` 대조 결과를 min(서버 `ttlMs`, 30초) 동안 재사용하고, 변경 알림·카탈로그 감시·승인 변경·종료·자격 교체로 무효화한다. 쓰기·중요 도구는 항상 실시간 재확인한다. TOCTOU 창을 최대 30초로 여는 결정이다.
- **상태 의존 서버**: 2단계 위에서 한 대화 안의 상태(Playwright 탭)가 유지된다. 대화·주체 간 공유는 하지 않는다. 신형 규격은 상태를 명시적 핸들로 옮겼으므로 구형 서버의 과도기 기능으로 둔다.
- 근거(규격 `86f6e0c`, SDK 2.2.0, ContextForge `5735c9d`, Microsoft mcp-gateway `3594c4e`, Lunar MCPX `7193eab`)·지연 추정·불변식·시험 계획: [설계 비교](../../research/llm-wiki/analysis/upstream-session-reuse/README.md).

## 제안 (결정 대기) — 관리 계정 루프백은 소유자가 시작한 연결의 응답만 연다 (DEV-35, 2026-10-15)

2026-10-17 D-119로 채택했다. 아래는 당시 제안 이력이며 현재 구현·검증 범위는 D-119를 따른다.

- **문제**: PJ1 관리 계정의 Codex 브라우저 로그인이 실패했다. 10-15 루프백 거부 399건은 전부 데스크톱 브라우저(UID 1000) → 관리 Codex 로그인 서버(1455·1457)의 SYN-ACK 응답(392)과 Codex의 자기 `/cancel` 연결(7)이었다. Claude·하네스 내부 IPC 거부는 0건이다. 처음 "하네스 임시 포트 쌍"으로 본 것은 관측기가 `SPT`·TCP 플래그를 버려 생긴 오독이다.
- **제안**: ① Codex는 장치 코드 로그인을 기본으로 안내한다(규칙 변경 없음). ② `nft_rules`에 소유자 UID가 시작한 `lo` 연결에 ct mark `0x100` 한 비트를 OR로 켜고, 그 연결의 응답 방향만 관리 UID에 허용한다(Tailscale의 connmark `0xff0000`과 겹치지 않게). ③ 관측기가 `SPT`·플래그를 남긴다.
- **기각**: 포트(1455·1457) 허용은 다른 UID가 1455를 선점하면 관리 UID가 그 비인가 리스너와 통신한다(PJ1 커널 netns 시험에서 재현). 기간 허용도 같은 창이다. "같은 UID 소켓만"은 nft output 훅에서 목적지 소켓 소유자를 고를 수 없어 근사만 가능하고, 필요한 경우가 `/cancel` 하나라 장치 코드로 사라진다.
- **근거·시험 계획**: `research/llm-wiki/analysis/dev35-loopback/README.md`. 일회용 netns 시험에서 E13 반례 7종(IPv4·IPv6·UDP·다른 UID·자기 리스너)은 그대로 막혔다. 키트·nft 변경 적용과 PJ1 재설치는 사용자 승인 뒤에 한다.

## D-110 업스트림 연결은 승인한 계약의 프로토콜 판으로 연다 (2026-10-15)

- 결정: DEV-29 제안의 1단계를 채택한다. 호출마다 SDK가 `server/discover`를 먼저 보내던 것을, 승인 계약에 기록된 판으로 고정한다. 구형(`2025-11-25` 이하)은 `initialize`로 바로, 신형(`2026-07-28`)은 그 판을 탐색 왕복 없이 채택한다(`upstream.connect_mode`). 판이 없으면 지금처럼 탐색한다.
- 근거: MCP Python SDK 2.2.0 `client.py:456-462`(판 고정 시 `adopt`, 왕복 없음). 게이트웨이 컨테이너에서 등록 서버 대상 연결+목록: GitHub 약 2.6초→1.4초, Context7 약 1.25초→0.87초, 목록 동일. PJ1 관리 Claude 호출에서 연결 구간 660~800 ms→약 4 ms(원장 8·9).
- 당시 경계: 세션 수명·호출별 계약 재확인·실행 직전 재판정은 그대로였다(D-79). 서버가 판을 바꾸면 호출이 실패(차단)하고 카탈로그 점검에서 변경으로 드러난다. 2026-10-17 2단계는 D-115로 채택했고 3단계(목록 캐시)는 미채택이다.

## D-111 심사한 목적지가 없으면 주소 인자를 받지 않는다 (2026-10-15)

- 문제(검토 RV-01·RV-04): 자동 범위(D-108)는 목적지 목록이 비면 `^https://`를 만들어 아무 HTTPS 호스트나 통과시켰고, 최상위 인자만 보았으며 `$defs`를 버렸다.
- 결정: 목적지가 없으면 주소 인자는 어떤 값도 받지 않는다. 배열 항목·중첩 객체·`$defs`·`anyOf/oneOf/allOf` 안의 주소 인자에도 같은 패턴을 건다. `$defs`는 범위 스키마에 남겨 `$ref`가 풀리게 한다.
- 한계: 리디렉션·DNS 변경·MCP 서버 자체의 외부 통신은 인자 검사로 막지 못한다(DEV-41 남은 범위, 실행 시점 목적지 통제 필요).

## D-112 관리 하네스는 관리 설정의 훅만 실행한다 (2026-10-15)

- 문제(검토 RV-02): 사용자·프로젝트·플러그인 훅은 하네스가 시작하는 명령이라 하네스 프로필(헤더 헬퍼 실행 가능) 아래에서 돌 수 있다. Bash 도구만 `-tool` 프로필로 분리한 D-104로는 닫히지 않는 표면이다.
- 결정: 관리형 `managed-settings.json`에 `allowManagedHooksOnly: true`를 넣는다(Claude Code 관리 설정, 사용자·프로젝트·플러그인 훅을 불러오지 않음).
- 남은 것: statusLine 등 하네스가 셸로 실행하는 다른 설정 표면과 Codex 쪽 대응은 실기기 음성 시험으로 확인한다(DEV-42).

## D-113 루프백 거부는 응답과 시도를 나눠 기록하고, Codex 로그인은 장치 코드로 안내한다 (2026-10-15)

- 결정: DEV-35 제안 중 규칙을 바꾸지 않는 두 가지를 채택한다. ① 관측기가 nft 로그의 출발 포트와 TCP 플래그를 남기고, 관리 계정에서 나가는 SYN-ACK는 `listener_reply`(하네스 응답), SYN은 `blocked_attempt`로 분류한다. ② 설치기는 이 PC에서 완료될 수 없는 브라우저 로그인 안내를 빼고 Codex는 장치 코드 로그인을 고르도록 안내한다.
- 당시 결정 대기였던 ct mark 규칙은 2026-10-17 D-119로 채택했다. R1~R9의 이번 구현에 대한 실기기 검증은 남아 있다.

## D-114 승인한 소스 MCP는 솔루션의 실행기가 빌드·실행한다 (2026-10-15)

- 결정(사용자 선택: 자체 최소 실행기): `runtime-worker`가 컨테이너 엔진을 쥔 유일한 프로세스다. 관리자가 승인된 소스 신청에 "실행"을 누르면 job이 생기고, worker가 내부 미러에서 검증 커밋을 받아 검증 때 기록한 해시와 대조한 뒤, 저장소에 있는 고정 레시피(`full_stack_lab/runtime/recipes/`, 기반 이미지 digest 고정)로 빌드하고, 그 이미지 ID로만 실행한다.
- 실행 경계: 읽기 전용 루트, 권한 전부 제거, UID 65534, no-new-privileges, 게시 포트 없음, PID·메모리 제한. 실행마다 전용 internal 망을 만들고 게이트웨이만 붙인다. 바깥 통신은 같은 망의 허용목록 프록시(모델 프록시와 같은 tinyproxy 이미지)뿐이고, 허용 호스트는 등록된 도구의 심사 목적지다(등록 전에는 없음).
- 결속: 승인 상태를 빌드 전·시작 전·활성화 직전에 다시 읽는다. 승인 1건에 살아 있는 실행 1건(DB 부분 유일 색인), attempts가 fencing 토큰, 만료 lease는 재예약, 재시작한 worker는 자기 job을 즉시 정리·재예약한다. 주소는 승인 단위 별칭(`mcpgw-mcp-<신청 8자>`)이라 재실행해도 등록이 유지되고, 실행 중인 신청은 그 주소로만 등록되며 등록 기록에 이미지 ID가 남는다.
- 정지: 관리자 중지, 등록 해제, 종료 절차, 승인 무효, 승인 이미지와 다른 컨테이너. 컨테이너·망을 지우고 남은 것을 센다. 이미지는 근거로 남긴다. 계약 확인은 지금처럼 게이트웨이가 등록 때와 호출마다 한다.
- 채택하지 않음: ToolHive 런타임(기본 허용 gate·경고 후 진행 검증·하네스 직접 등록, [분석](../../research/llm-wiki/analysis/oss-deep/toolhive-runtime.md)). 레시피가 늘어 재조정 코드가 커지면 다시 본다.
- 한계: 엔진 소켓을 가진 worker는 호스트 root에 준한다. 그래서 게시 포트 없이 DB·내부 Git 망에만 두고, 레시피는 이미지에 구워 job이 다른 빌드를 지정할 수 없게 했다. 빌드 단계의 패키지 설치는 인터넷에 닿고 의존성 잠금 파일이 없으면 `pip freeze` 결과의 해시로 남긴다.

## D-115 구형 업스트림 MCP 세션은 주체·다운스트림 대화에 결속해 재사용한다 (2026-10-17)

- 결정: 사용자 채택 범위는 DEV-29의 2단계까지다. **D-79의 호출마다 MCP 세션을 닫는 부분을 개정**한다. 3단계 읽기 도구 목록 캐시는 채택하지 않는다. D-110의 프로토콜 판 고정과 판 변경 시 실패는 유지한다.
- 키: `(principal, (downstream Mcp-Session-Id, verified token jti), server_id, sha256(operator credential headers), endpoint, pinned protocol, timeout, internal)`. 주체는 전송 토큰으로 검증한 내부 주체이며 헤더·도구 인자에서 가져오지 않는다. 대화 ID는 SDK가 입장을 허용한 HTTP 요청에서만 얻어 ContextVar로 전달하고, 요청 본문·감사 client·승인 재실행 payload는 이 바인딩을 만들지 못한다. `jti`는 같은 직원의 다른 로그인을 구분한다. 엔드포인트·판·시간 제한은 서버 등록/연결 설정 변경 뒤 옛 연결을 재사용하지 않기 위한 추가 요소다. 개별 호출 승인은 키에 저장한 권한으로 보지 않고 매번 다시 검사한다.
- 수명/경합: `upstream_sessions.py`가 프로세스 안에서 유휴 60초·최대 수명 600초·전체 `UPSTREAM_POOL_SIZE`개를 관리한다. 같은 키는 **1개 세션에서 호출 전체를 직렬화**한다. 설계 비교의 키당 최대 4개 제안 대신 1개로 좁혀, 동시 Playwright 호출이 서로 다른 탭 세션으로 갈라지는 것을 막는다. 서로 다른 키는 병렬이며 상한에 닿으면 유휴 항목부터 닫고 사용 중인 항목뿐이면 기다린다. SDK transport의 AnyIO cancel scope는 전용 소유 태스크에서 열고 같은 태스크에서 닫는다.
- 규격 분기: 승인 판이 `HANDSHAKE_PROTOCOL_VERSIONS`이고 다운스트림 세션 ID와 검증한 `jti`가 모두 있을 때만 MCP 세션을 보관한다. 2026-07-28 규격은 세션이 없으므로 호출별 `Client`와 기존 HTTP 연결 풀을 쓴다. 미확인 판·stdio·세션 ID 없음·`jti` 없음·승인 payload 재실행도 MCP 세션 재사용을 하지 않는다.
- 재확인: `Client(cache=None)`과 모든 목록 페이지의 `cache_mode="bypass"`를 함께 고정한다. 계약 해시·입력 스키마·개별 승인·주체/관리형 장치·OPA·`dispatch.record`를 호출마다 원래 순서로 확인한다. 재사용은 인가가 아니다. 직원 토큰을 업스트림으로 전달하지 않는다.
- 폐기: 기존 주체 중지·서버 종료의 `release_pool`이 세션과 HTTP 풀을 함께 폐기한다. 등록 해제·등록 교체·계약 드리프트/재승인·승인 요청 거부·실행 직전 재확인 실패에도 연결했다. 다운스트림 `DELETE` 성공은 해당 주체/세션/`jti`의 세션만 닫고 해시 신호를 DB에 남긴다. 자격은 대여 때와 SDK 요청 직전 다시 읽으며, 자격이 바뀌거나 사라지면 이전 키는 전송하지 않는다. 같은 주체·서버의 옛 자격/연결 설정 세션은 새 키를 열기 전에 폐기한다.
- 유휴 시에도 돌아가는 2초 주기 감시는 다른 프로세스의 `upstream_pool_events`, 주체·서버/등록 상태·도입 승인/기한·자격 변경·최대 수명을 확인한다. 메인 리뷰 후 정정: 첫 커서는 잠금 안에서 현재 최대 이벤트 ID로 설정한다. 모든 dispatch는 세션을 열기 전에 같은 잠금을 기다리므로 초기 커서 이전에 열린 세션은 없다. 초기화 실패 시 세션을 열지 않고, 초기화 이후 이벤트만 순서대로 적용하며 폐기 실패 시 커서를 전진시키지 않는다. 로컬 폐기 표시는 즉시 적용하고 닫기 신호 전파·실제 서버 DELETE 완료 시간은 별도다. 정리는 5초 기다린 뒤 소유 태스크를 취소하며 서버 측 완전 회수를 보증하지 않는다. DB/신호 장애에서 감시의 2초는 보장하지 않지만 실행 직전 정책·전송 의도 경계는 유지한다.
- 폐기 중 대기 호출은 세대 번호로 거부해 옛 자격이나 중지 직전 상태로 다시 세션을 열지 못한다. 안전을 위해 풀 폐기와 겹친 다른 키의 대기 호출도 거부될 수 있다. 오류·취소·도구 오류 응답 뒤 세션을 버린다. 목록 단계에서만 SDK의 세션 404(`-32600`, `Session terminated`)를 한 번 새 세션으로 재시도한다. `tools/call` 뒤에는 재시도하지 않아 실행 여부 불명을 보존한다.
- 메인 리뷰 반영: `session()`의 관계 사전 거부를 제거했다. `_dispatch_allowed()`는 백그라운드 폐기에만 쓰고, 호출의 종료/주체/승인/공급망 판정과 정책 ID는 기존 core 정책 및 `dispatch.record()`가 결정한다. 종료 중 호출은 `DispatchRejected`의 `MCP-DECOMM-001`로 기존 감사 경로를 따른다. 대기 시간은 호출자의 `dispatch_budget`으로 제한한다. A의 internal 판별값도 MCP/HTTP 풀 키와 최초 transport에 결속한다.
- 관측: `decisions.timings`의 기존 구간 이름/숫자 형식을 유지한다. `close`는 풀 반환 또는 실제 종료에 든 시간이다. 재사용 여부는 시간값이 아닌 감사 `client.upstream_session_reused` 불리언으로 기록한다. 콘솔·`/api/latency`의 시간 집계를 바꿀 필요가 없다.
- 근거/검증 범위: [기존 고정 OSS·규격 비교](../../research/llm-wiki/analysis/upstream-session-reuse/README.md), [구현 요구·시험 대응](../../research/llm-wiki/analysis/upstream-session-reuse/stage2.md), [작업 보고](../../research/llm-wiki/status/reports/2026-10-17-upstream-session-reuse-stage2.md). 순수 단위 시험이며 SDK/DB/실제 MCP·배포·독립 효과 검증은 메인이 수행한다.

## D-116 연결 직전 DNS 전체 응답 검사와 숫자 IP 접속 (2026-10-17)

- 결정: `destination.PinnedBackend`를 HTTPX 0.28.1·HTTPX2 2.12.0 transport의 기존 pool network backend 앞에 둔다. 새 TCP 연결마다 제한 시간 안에서 `getaddrinfo`를 한 번 호출하고 모든 응답을 `ipaddress`로 검사한 뒤 첫 검증 숫자 IP만 기존 backend에 넘긴다. 외부 서버의 비공인·루프백·링크로컬·멀티캐스트·예약·미지정·IPv4-mapped 내부 주소, 빈 응답·해석 실패는 `MCP-EGRESS-001` 차단이다.
- 이유: URL을 IP로 바꾸면 Host·SNI·인증서 이름 검증과 풀 origin을 별도로 복원해야 한다. network backend만 바꾸면 HTTP origin·Host·TLS 검증 이름은 원래 호스트로 유지된다. proxy/redirect 비활성, 직원별 풀·자격 회전/철회는 유지한다. internal 여부도 풀 키에 넣어 분류 변경 뒤 옛 내부 예외가 재사용되지 않게 한다.
- 내부 근거(메인 검토 후 정정): `deployment`는 종료 모델의 계약 귀속이며 네트워크 위치가 아니다. 초기 초안의 `deployment=internal` 판정은 폐기한다. `registry.servers()`에 완전 일치하는 endpoint의 호스트가 숫자 IP 표기가 아닌 단일 DNS 라벨이면 내부 서비스로 본다. `email`·`gitea`는 provider 계약이지만 등록값 `mcp-email:8000`·`mcp-gitea:8000`이므로 내부다. 등록 전 실행기 역시 단일 라벨과 같은 endpoint·`ACTIVE` 레코드가 필요하다. 미등록 이름 자체는 승인이 아니며 외부 SaaS FQDN은 deployment 값과 무관하게 외부다. 내부에서도 링크로컬·멀티캐스트·예약·미지정 주소는 거부한다.
- 적용: MCP 탐색·건강 확인·호출, 종료 증거 HEAD와 E2 세션 조사. MCP upstream OAuth 자동 탐색은 구성하지 않는다. 조직 OIDC의 Authlib discovery·JWKS·토큰, 직접 refresh·introspection·revocation에도 같은 backend를 적용한다. OIDC 내부 예외는 운영자가 설정한 issuer/discovery URL 중 loopback 또는 단일 라벨 호스트의 정확한 호스트·포트다. `compose.keycloak.yaml`의 loopback issuer와 `keycloak:8080` discovery를 함께 허용하므로 같은 authority를 쓰는 동적 백채널 metadata endpoint도 정상 접속한다. metadata에 적힌 임의의 다른 사설 호스트/포트는 자동 승인하지 않는다.
- 정책 원장: `enforced_by`는 기존 값 체계의 `gateway`로 기록한다. 이 항목의 연결 직전 DNS 집행 주체를 뜻하며 같은 ID를 쓰는 기존 OPA egress 규칙을 제거하거나 바꾸지 않는다.
- 한계: [분석](../../research/llm-wiki/analysis/dest-pin-credential-redaction/README.md)·[보고](../../research/llm-wiki/status/reports/2026-10-17-dest-pin-credential-redaction.md). `_pool._network_backend`는 비공개 접점이므로 판본 변경 시 `dest_pin_transport_check.py`가 필수다. 로컬에는 HTTPX 계열이 없어 실제 풀·TLS 시험은 미실행이다. 첫 검증 IP 실패 시 다른 IP로 재시도하지 않는다. MCP 서버 자체의 outbound는 DEV-41에 남긴다.

## D-117 오류의 Secret 검사와 진단문 전체 가림 (2026-10-17)

- 결정: `secret_scan.redact_error()`에서 기존 `classify.SECRET_PATTERNS`·Gitleaks `labels()`를 재사용한다. URL decode 후 Authorization·자격 쿼리/할당 문맥은 토큰 길이와 무관하게 가린다. 탐지·검사 장애·500자 초과는 전체 `[REDACTED]`로 대체한다. Gitleaks가 span을 반환하지 않아 부분 가림을 추정하지 않으며, 자르기 전에 검사해 토큰 조각이 남는 것을 막는다.
- 경계: `_record_decision()`에서 event와 저장값을 함께 가린 뒤 해시를 계산한다. 과거 원장은 수정하지 않고 `_decision_payload()` 반환값과 원장 error를 일치시킨다. HTTPException·입력 검증·MCP 인증 거절에도 적용한다. MCP 처리의 예기치 않은 예외는 고정 문구만 반환한다. 일반 upstream 예외는 기존 형식명만 남기는 `_root_cause()`를 유지하고 카탈로그 실패 진단에도 사용한다.
- 키트: field 설정 생성·전체 CLI 인자, 서버의 Linux/Windows 관리 설정 생성과 엔드포인트의 파일 쓰기를 가짜 토큰으로 회귀 검사한다. OS 집행 코드는 변경하지 않는다. 기존 `field_kit_check.py`는 Claude add 인자의 마지막 항목만 보므로 새 회귀는 인자 전체를 본다.
- 한계: 알 수 없는 모든 비밀 형식의 탐지를 보장하지 않는다. 네이티브 Gitleaks·SDK·실제 DB 검증은 미실행이며 대역을 사용하는 함수 단위 증거로 한정한다. [보고](../../research/llm-wiki/status/reports/2026-10-17-dest-pin-credential-redaction.md).

## D-118 Windows 키트는 포함 Python·설치 마법사·트레이로 제공한다 (2026-10-17)

- 사용자 결정: Windows 기본 PowerShell 5.1·WinForms·NotifyIcon만으로 설치 마법사와 로그온 트레이를 만든다. 새 GUI 런타임·서드파티 GUI 라이브러리는 넣지 않는다. 대상은 Windows amd64다.
- Python: 공식 [3.13.16 배포](https://www.python.org/downloads/release/python-31316/)의
  `https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-amd64.zip`, SHA-256
  `97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297`를 고정한다.
  게이트웨이 Dockerfile이 빌드 중 ZIP과 원래 라이선스를 검증·보관하고 `/api/pc-kit`가 함께 압축한다. 실행 중 다운로드하지 않는다.
  이미 존재하는 게이트웨이 이미지 빌드/키트 bind mount 구조를 유지하며, 호스트별 외부 캐시 설정·실행 중 네트워크 의존성을 추가하지 않기 위해 이미지 방식을 택했다.
- 검색 경로: `python313._pth`에 표준 ZIP·런타임 폴더·키트 부모만 둔다. `import site`는 주석으로 유지하고 `-I -S`로 실행한다.
  명시적 `site` import도 훅을 활성화하지 않는지, 설치기·에이전트의 AST import 목록(ssl·ctypes·winreg·msvcrt·tomllib 등)을 포함 Python으로 설치 전에 점검한다.
  pip·사용자 site-packages·사용자 환경으로 의존성을 충족시키지 않는다. 서비스와 관측 에이전트 예약 작업은 포함 `pythonw.exe`를 쓴다.
- 권한: 시작·연결(TCP + `/api/health`)·위치/범위 확인은 일반 권한이다. 관리형 등록/제거만 별도 UAC 프로세스다.
  D-68의 대상 계정 로그아웃·일반 계정·보호된 프로그램/장치 키·파이프 신원·사람의 활성화 경계를 유지한다. 표준 사용자가 자기 로그인 세션을 유지한 채 관리형 등록하도록 완화하지 않는다.
- 트레이: 대상 SID의 Interactive/Limited 로그온 예약 작업을 쓴다. 기존 관측기가 가진 최근 실제 차단 5건과 자격정보 없는 상태 파일만 읽는다.
  150초 초과 보고는 연결 끊김, 연결된 상태의 5분 내 차단은 차단 발생으로 표시한다. 지금 점검은 게이트웨이 연결·기존 보고 시각 확인이며 정책 승인/서비스 재시작이 아니다. 새 API는 추가하지 않는다.
- 제거: 예약 작업 종료를 기다린 뒤 설치 목록의 파일만 지워 사용자 파일을 보존한다. Codex는 현재 관리 블록 밖 사용자 변경을 유지한다.
  직원 PC 키트는 report 실행·예약·제거를 같은 `report.lock`으로 직렬화하고, 자식이 잠금을 잡은 뒤 `report.log`를 연다. 제거 뒤 대기 report는 설정이 없으면 쓰지 않는다.
  잠금 inode 분리를 막기 위한 `report.lock`과 사용자가 확인할 진단 `setup.log`는 보존한다.
- 근거·원자 요구·시험·한계: [분석](../../research/llm-wiki/analysis/windows-kit-wizard-tray/README.md),
  [작업 보고](../../research/llm-wiki/status/reports/2026-10-17-windows-kit-wizard-tray.md), [pj3 절차](../../endpoint-agent/tests-windows/README.md).
  이번에는 정적/순수 단위 검사만 수행한다. 실제 ZIP 다운로드·포함 Python 실행·GUI/DPI·UAC·예약 작업/ACL·pj3 효과는 메인의 빌드/실기기 검수 대상이다.

### D-118 보안 검토 반영 (2026-10-18)

- 앞 구현의 UAC 작업자가 직원 쓰기 가능한 키트에서 common/ZIP을 읽던 경로를 폐기한다. 관리자 실행의 진입점은 조직이 별도 승인·배포한
  `%ProgramFiles%\MCPGatewayInstaller\windows-worker.ps1`뿐이다. 그 설치기 자체를 내려받은 ZIP에서 최초 승격해 배치하거나 최초 관찰 해시로 승인하지 않는다.
- 신뢰 근거는 ZIP 밖에서 IT가 관리하는 `%ProgramData%\MCPGatewayInstaller\approved-windows-kit.json`이다.
  기존 인증된 `/api/pc-kit` 응답은 전체 코드·Python ZIP의 매니페스트와 응답 헤더의 SHA-256을 제공한다. IT는 신뢰되는 인증 경로/릴리스 승인에서
  별도로 확정한 매니페스트를 승인 배포 도구로 설치한다. ZIP 옆의 매니페스트·해시를 그대로 신뢰 파일로 복사하는 자동 경로는 없다.
  승인 설치기·승인 파일이 없거나 소유자/ACL·reparse·파일 목록·해시가 맞지 않으면 승격 또는 실행을 거부한다.
- 승격 뒤에는 보호된 승인 위치의 파일만 사용한다. 사용자 폴더에서는 크기 제한된 요청/등록 JSON만 공유 쓰기·삭제를 허용하지 않는 핸들로 읽고,
  실제 열린 경로를 대조한 뒤 보호된 임시 위치로 스냅샷한다. 게이트웨이 주소·노드 ID는 승인 파일 값으로 고정한다.
  설치 목적지의 코드와 Python 전체도 실행 전에 재대조한다. 승격 프로세스의 PATH·모듈 경로·작업 디렉터리·임시 컴파일 경로는 보호된 위치로 제한한다.
- 승격 명령에서 `-ExecutionPolicy Bypass`를 제거한다. 실행 정책이나 UAC 자체를 코드 출처 인증으로 세지 않는다.
  조직의 서명/실행 정책은 승인 배포 과정에서 충족해야 하며 ZIP의 인증서나 처음 본 게시자를 자동 신뢰하지 않는다.
- 프로그램은 Users 읽기를 유지하지만 개인 트레이 설정·상태·교체용 임시 파일은 `%ProgramData%\MCPGatewayManagedTray\<SID>\`로 분리한다.
  상속을 끊고 Administrators·SYSTEM 쓰기, 해당 SID 읽기만 허용한다. 최초 서비스 실행 전에 생성하며 이후 교체 파일도 같은 ACL을 상속한다.
  승격 작업 결과도 요청자 SID 읽기·관리자/SYSTEM 쓰기 경로에만 기록한다.
- 기존 직원 키트 제거 시험은 `report.lock` 한 파일만 남는 정확한 조건으로 수정했다. 다른 잔여 파일을 허용하도록 조건을 넓히지 않았다.
- 이 신뢰 경로는 Windows 마법사의 범위다. Linux `install.sh`가 사용자 폴더의 `bootstrap.py`를 sudo로 실행하는 동일 계열 위험은
  [별도 잔여 위험](../../research/llm-wiki/analysis/windows-kit-wizard-tray/security-review.md)에 남겼으며 Linux 코드는 변경하지 않았다.

## D-119 관리 계정 루프백은 소유자 시작 연결의 응답만 허용하고 Codex는 장치 코드로 로그인한다 (2026-10-17)

- 결정(사용자 채택): Codex 로그인은 `codex login --device-auth`를 기본으로 실행한다. 관리 UID가 시작하는 루프백 연결은 계속 거부한다. 소유자 UID가 `lo`에서 시작한 `ct direction original ct state new` 연결에만 `ct mark set ct mark or 0x00000100`을 적용하고, 관리 UID의 `lo` 응답 방향 중 `ct mark and 0x00000100 == 0x00000100`만 허용한다. 포트·기간·전체 established 허용은 추가하지 않는다.
- 소유자 결속: `bootstrap.py`가 확인한 직원 계정 UID를 별도 관리 계정에만 `--owner-uid`로 전달한다. `managed-linux.py`는 등록 토큰 소비 전에 실제 계정 존재·UID 유효성을 검사하고 저장·전달한다. 소유자 미지정은 기존 전면 거부를 유지하며, 관리 계정 자신·시스템 UID·잘못된 값은 거부한다. 원시 `SUDO_UID`를 집행기에서 추측하지 않는다. 이 로컬 UID는 방화벽 범위이며 게이트웨이의 transport 신원을 대신하지 않는다.
- 근거: [DEV-35 원인·선택지·과거 netns 실험](../../research/llm-wiki/analysis/dev35-loopback/README.md). PJ1에서 관찰한 Tailscale connmark 마스크는 `0xff0000`으로 `0x100`과 겹치지 않는다. 기존 비트는 OR로 보존한다. 포트 선점·다른 UID·자기 리스너 반례 때문에 더 넓은 허용은 기각한다.
- 관측: D-113의 `SPT`·TCP 플래그·`listener_reply` 분류는 유지한다. 허용 규칙은 `MCPGW_DENY` 로그보다 앞에 있어 허용 응답은 이 거부 로그에 도달하지 않는다. 다른 UID가 시작해 차단된 SYN-ACK는 계속 `listener_reply`다. 기존 원장은 수정하지 않는다.
- 검증 범위: [작업 보고·실기기 명령](../../research/llm-wiki/status/reports/2026-10-17-loopback-owner-replies-d119.md). 로컬 순수 Python 단위 검증이며 배포·PJ1 재설치·이번 판본 netns/E13·R1~R9·실제 장치 코드 로그인은 메인이 수행한다. 과거 제안의 충돌 번호 표기는 D-119로 정정했고 런처 결정 D-107은 유지한다.

## D-120 운영 이미지 재검사와 기한 초과 격리 (2026-10-17)

- DEV-50 / POL-39 / WBS G01.06. 실행기의 기존 조정 루프에서 불변 이미지 ID를 Trivy 0.74.0으로 재검사한다. 도입 검사와 JSON·취약점 DB 시각 파서를 공유하고 7일 신선도 기준을 유지한다. 기본 검사 간격 1일, CRITICAL 조치 기한은 최초 발견부터 7일이며 환경 설정으로 바꾼다.
- 발견 항목별 최초 시각과 검사 실패를 DB·승인 이벤트에 추가한다. 기한 초과 또는 검사 실패는 비활성·실행 중지로 보낸다. 자원 잔존 시 정리 완료로 세지 않는다. 자동 재활성화하지 않는다.
- 범위: 실행기가 관리하는 이미지. KEV의 악용 확인·EPSS의 확률은 같은 지표가 아니고 이 작업의 격리 입력으로 자동 도입하지 않았다. 직렬 실행기 지연·실제 DB 다운로드·엔진 격리는 기기에서 검증해야 한다. [운영 문서](OPS_RESPONSE.md).

## D-121 정책 해시별 합성 경보 자체 시험 (2026-10-17)

- DEV-60 / POL-42 / WBS G06.05. 실제 OPA 로드 규칙·데이터·capability 해시를 기준으로 정상 1건과 주요 경보 합성 5건을 평가하고 정책 ID와 경보 저장 결과를 확인한다. 실행 전후 해시가 다르거나 검사기·저장 경로가 실패하면 실패로 남긴다.
- `alert_self_tests`는 별도 테이블, `ops_alerts`는 `synthetic`으로 구분한다. 실제 `decisions`와 호출 통계에 합성 요청을 쓰지 않는다. 새 도구는 실제 카탈로그 탐지와 같은 경보 함수를 거친다. MCP 호출과 외부 SIEM 전송은 자체 시험 범위가 아니다. 기존 정책 ID만 사용하며 OPA 관리대장은 바꾸지 않는다.

## D-122 탐지 후 서버 전체 자동 중지와 사람 승인 복귀 (2026-10-17)

- 2026-10-18 정정: 변경 영향이 도구 이름으로 확정된 계약 변경은 D-127의 선택적 제한으로 대체한다. 원인 불명 계약 변경·반복 이상 호출과 이미 저장된 서버 중지는 이 결정대로 유지한다.

- DEV-62 / POL-43 / WBS G07.05. 유효한 도구 계약의 DRIFT, 설정된 시간 창·반복 수에 도달한 P-ANOMALY/P-VOLUME 판정은 서버 전체를 비활성화한다. 원인·서버 목록·임계값을 설정할 수 있다. 합성 이벤트와 마지막 복귀 전 판정은 세지 않는다.
- 서버 중지 기록과 실행기 STOPPING을 함께 저장하고 최종 dispatch도 중지 상태를 확인한다. 계약 새로고침·승인 갱신은 비활성을 되돌리지 않는다. 관리자 API의 명시적 승인만 PENDING으로 복귀시키며 원인이 남으면 다시 중지한다. 도구별 격리는 기존 계약 경계와 겹치는 별도 작업에 남긴다.
- 원격 제공자의 프로세스와 이미 dispatch된 호출을 취소한 증거는 아니다. 실기기에서 반복 탐지·동시 dispatch·수동 복귀·물리 정지를 확인해야 한다.

## D-123 서명 폐기 목록으로 DB 복원 후 재차단 (2026-10-17)

- DEV-63 / POL-50 / WBS G07.06. DB 밖 전용 볼륨에 Ed25519 서명·연쇄 해시·서명된 head를 가진 폐기 목록을 추가 보관한다. 기존 raw 32-byte/base64url·cryptography 체계를 재사용하되 JWT 발급 키와 폐기 서명 키를 분리한다. 게이트웨이에 JWT 발급 권한을 주지 않는다.
- 토큰 철회·갱신 토큰 회전·자격 회수·종결 전에 파일을 먼저 확정한다. 시작 시와 60초마다 DB와 대조하고 누락 상태를 복원·차단하며 경보한다. 인증·계약 확인은 파일도 직접 확인한다. 서명 불일치·누락·절단·중간 쓰기 실패는 차단한다. C1~C4/T1~T3 기준은 변경하지 않는다.
- 최초 볼륨 초기화는 운영자의 명시적 `field init-disposal`이다. 이미 폐기한 식별자의 실습 복원도 거부하고 새 도입 승인을 요구한다. DB와 폐기 볼륨·키를 함께 롤백한 호스트 관리자, 외부 제공자 자격의 복구·재사용 자체는 통제하지 못한다. 내구성·이관·부하와 실제 복원 증거는 기기 검증 전이다.

## D-124 현장 하네스 연결은 배치 사설 CA의 HTTPS만 사용한다 (2026-10-18)

- 결정: Tailscale IP 바인딩은 유지하고 Caddy 	ls internal로 TLS 1.2/1.3과 ECDHE/ECDSA AEAD를 제공한다. HTTP 자동 리디렉션과 시스템 CA 등록을 끈다. IP 및 선택 공개 이름을 발급 대상으로 삼고 빈 SNI에는 IP 인증서를 선택한다. 공개 OAuth·MCP·Console·Git URL과 관리형 정책은 HTTPS다. 원격 HTTP 입력과 자격 요청 리디렉션은 거부한다. 격리 기본 랩의 명시적 HTTP 빌드 인자는 별개다.
- 신뢰: 배치 볼륨의 CA 개인 키는 내보내지 않는다. field ca는 공개 루트·DER SHA-256을 출력하며 Console ZIP에 루트·지문을 넣는다. 설치기는 단일 PEM과 지문을 설치/등록 전에 검증한다. Linux 실행기 및 직원 PC 도구의 harness 명령이 Claude의 NODE_EXTRA_CA_CERTS, Codex의 CODEX_CA_CERTIFICATE를 프로세스에 지정한다. 시스템 저장소는 변경하지 않는다. 에이전트와 Linux OS 관측기는 동일 CA로 체인·이름을 검증한다.
- 복구: CA 볼륨은 배치 수명 동안 유지한다. 새 루트는 기존 연결을 실패시키므로 별도 지문 대조·새 키트 설치로 교체한다. 키트 발행자 확인은 인증된 배포 경로와 운영자의 별도 지문 대조를 전제로 한다.
- 후속 병합 정정: D-118 키트의 `payload`와 매니페스트에 CA·지문·직원 PC 도구를 함께 넣는다. Windows도 등록 전에 CA를 검증하고 보호된 승인 키트의 루트로 고정한다. 서비스·관측기에 CA를 전달하고 하네스 `.cmd` 실행기의 `setlocal`로 프로세스에만 적용한다. PowerShell은 요청별 검증 콜백·임시 X509Chain.ExtraStore를 사용하며 시스템 저장소는 변경하지 않는다. 내부 `gateway`는 TLS 종료점이 아니므로 레지스트리 주소 기본값은 비우고 배포 시 실제 HTTPS 주소를 지정한다. [병합 후 검증](../../research/llm-wiki/status/reports/2026-10-18-field-tls-d124-merge.md)이 이전 Windows 통합 대기를 대체한다.
- 근거/한계: [DEV-64 분석](../../research/llm-wiki/analysis/field-tls-d124/README.md), [작업 보고·메인 검증 명령](../../research/llm-wiki/status/reports/2026-10-18-field-tls-d124.md). Codex 0.157.0의 고정 소스와 공식 문서로 CA 변수를 확인했다. 로컬 단위 증거이며 Caddy 자체 검사·배포·PJ1은 미실행이다. Windows 전용 설치기는 다른 작업과 공통 CA 필드/환경값을 통합해야 한다.

## D-125 단일 조회의 범위와 반환 건수·크기를 제한한다 (2026-10-18)

- DEV-54 / G03.06 / POL-35. 기본 `MAX_RESULT_ITEMS=1000`, 기존 `MAX_RESULT_BYTES=262144`를 양수로 검증한다. 반환 건수는 structured JSON의 중첩 배열 원소 합, text 블록의 JSON 배열 원소 합 또는 비어 있지 않은 줄 수, content 블록 수 중 최댓값이다. text 블록들은 합산한다. 같은 내용을 text/structured로 보낸 경우 두 표현 중 큰 값을 사용한다. 바이트는 전체 UTF-8 JSON 크기다.
- 승인 입력 스키마 확인 뒤 읽기 요청에 `P-VOLUME-002`를 적용한다. 명시된 페이지 크기는 상한 이내 양수여야 한다. 파일 시스템·Desktop의 루트/전체 경로, 무범위 재귀 조회·전체 검색, 다중 파일 수 초과·glob, Redis 전체 키 검색을 거부한다. PostgreSQL `execute_sql`의 읽기는 기존 pglast 구문 트리로 단일 SELECT의 고정 정수 LIMIT(0~상한)을 요구하며 LIMIT ALL/변수/식/WITH TIES, 다중 문장, COPY 전체 내보내기를 거부한다. 인자를 자동 변경하거나 결과를 잘라 정상 성공으로 표시하지 않는다.
- 원문과 마스킹 후 반환 표현에 상한을 각각 적용한다. 응답 초과는 `MCP-OUTPUT-001` Block, `upstream_executed=true`, `withheld`다. 실행 전 범위 차단은 upstream 미전송이다. 누적 중요정보 승인 `P-VOLUME-001`과 별개다.
- 근거: OWASP API4:2023의 반환 레코드·자원 제한, API3:2023의 필요한 속성만 노출하는 원칙. 속성별 인가·범용 레코드 스키마·서버의 쿼리 비용 제한을 이 변경으로 구현했다고 주장하지 않는다. SDK가 응답을 메모리에 읽은 다음의 통제이며 원격 서버 작업량/메모리 상한은 아니다. [분석·원자 요구](../../research/llm-wiki/analysis/response-cap-idempotency/README.md).

## D-126 완료된 변경 호출의 지문으로 재전송을 차단한다 (2026-10-18)

- DEV-55 / G03.07 / POL-36. 기존 `(transport 주체, server, tool, arguments canonical hash)`와 `dispatch_intents`를 사용한다. `w/x`의 definite outcome(`resolved`·`confirmed_executed`)은 `resolved_at`부터 `IDEMPOTENCY_TTL_SECONDS`(기본 86400초, 양수) 동안 같은 변경의 재전송을 `P-RATE-003`으로 차단한다. 응답 본문·직원 토큰을 새로 저장하거나 결과를 재생하지 않는다. 같은 의도의 인자 순서 차이는 canonical hash가 흡수한다.
- 예약 단계에서 이력을 확인하고 전송 직전에도 같은 주체별 advisory lock 안에서 이력 재확인·intent 삽입·승인 소비를 수행한다. 잠금 대기 중 기한이 지난 예약/승인은 실제 시각(`clock_timestamp()`)으로 거부한다. lease 만료가 완료 이력이나 미확인 상태를 지우지 않는다. 이력 조회용 인덱스만 추가하며 기존 표·원장을 삭제하지 않는다.
- `pending`·`uncertain` 쓰기는 시간으로 풀리지 않는다. 관리자가 downstream에서 `not_executed`를 확인해야 즉시 재시도가 가능하다. `executed` 확인은 완료 보존 기간으로 이동한다. 읽기·전송 전 거부에는 완료 변경 이력을 만들지 않는다. 기존 읽기의 동시 중복 예약 제한은 유지한다. C1~C4/T1~T3 판정 기준은 변경하지 않는다.
- IETF Idempotency-Key -07은 참고 초안이며 RFC가 아니다. MCP 공통 멱등 키·결과 재생의 구현이 아니다. 의도적으로 같은 변경을 반복하려 해도 보존 기간에는 차단되며, 인자가 달라진 동일 업무·다른 주체·게이트웨이 우회·기간 후 재시도까지 정확히 한 번 실행을 보장하지 않는다. DB 내구성과 운영자의 확인에 의존한다. [작업 보고](../../research/llm-wiki/status/reports/2026-10-17-response-cap-idempotency.md).

## D-127 계약 변경 영향은 도구별로 제한한다 (2026-10-18)

- DEV-52 / G02.06 / POL-37·43. 승인 도구의 설명·입력 스키마 변경, 소멸, 미심사 위험 설명은 해당 도구만 제한한다. 사용자별 별도 예외를 만들지 않고 그 도구의 모든 사용자에게 적용하며 기존 신원·조직·자산·사용 기한 심사를 계속 적용한다. D-69의 버전 문자열 변경·미승인 도구 변경 기록 원칙은 유지한다.
- `catalog_snapshots.restricted_tools`에 영향 도구 이름을 저장한다. `NULL`은 영향 미확정이며 서버 전체 차단이다. 과거 `exact_match=false` 행은 자동으로 좁혀 해석하지 않는다. `exact_match`·서버 `DRIFT`는 전체 변경 증거로 보존하고, 도구별 계약 판정·목록·관리형 서버 노출·같은 연결의 실행 직전 재확인을 도구 단위로 맞춘다. 실행 직전 제한은 `Block` / `MCP-CATALOG-001`이다.
- 카탈로그 스냅샷 공개와 서버 상태 저장은 같은 서버 행의 배타 잠금 안에서 한다. dispatch는 공유 잠금을 별도 문장으로 먼저 획득하고 새 문장에서 최신 도구 계약·스냅샷을 확인한다. 이미 기록한 dispatch를 취소한 것으로 간주하지 않는다. 실제 PostgreSQL 경합 시험은 미실행이다.
- 계약 잠금·승인 해시는 자동 갱신하지 않는다(동일 설명·스키마의 버전 승계만 기존 예외). 승인본으로 되돌아오면 새 스냅샷으로 제한이 해소된다. 새 계약의 채택은 기존 사람 재승인/새 도입 심사를 거친다. D-122 중지·공급망 차단·폐기 상태는 이 과정에서 복구하지 않는다.
- 근거·원자 요구사항·로컬 시험 범위는 [분석 정본](../../research/llm-wiki/analysis/selective-restriction-siem/README.md). 실제 OSS MCP·하네스·배포 검증은 남았다.

## D-128 SIEM은 감사 참조 큐에서 OCSF JSON을 전달한다 (2026-10-18)

- DEV-61 / G06.06 / POL-38·42. OCSF 1.4.0 Base Event JSON을 HTTPS POST한다. 기존 Jaeger OTLP 추적과 분리한다. RFC 8417은 전달 보장 규격이 아니며 이 구현은 SET/JWT 발행·SSF·CEF·syslog 지원을 주장하지 않는다.
- `decisions`·`approval_events`·실제 `ops_alerts`의 INSERT 트리거가 같은 트랜잭션에서 `siem_outbox`에 소스·ID만 넣는다. 원문·원장 해시·기존 판정을 수정하지 않는다. 별도 프로파일의 워커가 원장을 읽어 허용 필드만 만든다. 본문·인자·정책 입력·사유·오류·scope·클라이언트 보고·비밀은 보내지 않으며 주체/서버/도구/대상 식별자는 해시 참조다. 합성 경보는 전달하지 않는다.
- 소켓 비활동 제한 5초, 한 회차 최대 50건, 오류 재시도 간격 5초~1시간이다. DNS·전체 응답 시간의 총기한은 별도로 구현하지 않아 느린 수신기가 워커를 지연시킬 수 있다. 오류·수신 거부를 폐기하지 않으며 지연·누적 건수는 관리자 감사 화면/API에서 조회한다. 행 잠금과 `SKIP LOCKED`로 워커를 분리하고 재시작 후 미전달 행을 다시 읽는다. SIEM 네트워크 장애는 도구 호출 경로에 들어가지 않는다. 큐 자체의 DB 저장 실패는 원장 INSERT와 함께 롤백되므로 감사 저장 성공으로 취급하지 않는다.
- HTTP 2xx는 수신 확인이며 원격 저장·인덱싱 보증이 아니다. 응답 뒤 로컬 커밋 실패는 중복될 수 있어 `metadata.uid`와 `Idempotency-Key`를 고정한다. 수신자가 중복을 제거해야 한다. 순서·정확히 한 번 전달·호스트 디스크 유실 복구는 보장하지 않는다. TLS 이름/체인을 검증하고 리디렉션·프록시 환경값을 따라가지 않는다. 토큰·CA는 파일에서 매 시도 다시 읽는다.
- 기본은 전달 워커 미기동이다. 큐는 설치 이후 계속 쌓이며 소급 수집·삭제·보존 정책을 새로 만들지 않는다. 운영자는 수신 주소·CA·자격 파일과 디스크 용량을 준비한 뒤 솔루션 기기에서 `./console.sh field up --with-siem`으로 활성화한다. 배포·실제 SIEM·PostgreSQL 내구성/TLS는 검증 전이다.

## D-129 브라우저 콘솔은 Tailscale IP의 HTTP 8000번, 하네스·키트는 HTTPS 443 (2026-10-18)

- 문제: D-124 뒤 브라우저 콘솔이 사설 CA 경고를 띄웠고, 로그인이 "다른 출처의 요청은 허용하지 않습니다"로 실패했다. 브라우저는 출처를 `https://<IP>`(기본 포트 생략)로 보내는데 허용 목록은 `https://<IP>:443`과 내부 `http://<IP>`였다.
- 결정(사용자 선택: 콘솔만 HTTP, 하네스는 HTTPS): ① 출처는 기본 포트를 채워 비교한다(빈 값은 허용 목록에서 뺀다). ② Caddy가 같은 콘솔·내부 Git을 `http://<Tailscale IP>:8000`으로도 게시한다. 이 포트에서 `/mcp`·`/oauth`·`/api/endpoint`·`/.well-known`은 421로 거절해 하네스·키트·장치 보고는 계속 D-124의 HTTPS만 쓴다. 내부 Git 링크는 페이지의 스킴을 따른다. ③ `field up`은 Caddy를 다시 만든다(마운트한 Caddyfile 변경이 반영되도록, 사설 CA는 볼륨에 남음).
- 근거: 전송은 Tailscale 터널이 암호화하고(D-46의 원래 전제), 브라우저에는 키트처럼 고정할 CA 경로가 없다. 80번은 기기의 Apache가 쓰고 있어 8000번을 쓴다.
- 한계: 콘솔 포트에서는 TLS 서버 인증이 없으므로 tailnet 밖으로 게시하지 않는다(Tailscale IP 바인딩 유지). 콘솔 토큰이 HTTP로 오간다는 점은 tailnet 구성원 신뢰에 기댄다.

## D-130 협업 WBS는 게시 시트 값을 저장소 근거 위에 덮어쓴다 (2026-10-18)

- 사용자 지정 통합 시트를 개발 관리 기준으로 읽는다. 제품 게이트웨이와 별개인 협업 콘솔에서만 적용하며 runtime 설정이 없으면 기존 저장소 스냅샷을 사용한다.
- Python 표준 라이브러리 `urllib`·`csv`로 조회하고 머리글·ID로 연결한다. 점수·담당·메모·일정을 덮어쓰며 새 ID를 화면에 추가하지만 기존 코드·시험 근거는 보존한다. 점수 5개 평균과 상태·목표별 요약을 재계산하며 시트의 수식 셀은 신뢰하지 않는다.
- 같은 URL의 마지막 정상 값과 실패를 5분 캐시한다. 소켓 타임아웃 15초, 실패 시 직전 캐시→저장소 사본 순으로 대체하며 출처·오류·마지막 정상 수신 시각을 구별한다. 재시작 시 캐시는 소멸한다. CLI는 모든 입력의 manifest 열 이름 집합을 검증한 뒤 사본을 갱신하고, 명시적 `--apply-snapshot`에서만 기존 ID를 저장소 정본에 적용한다.
- 외부 SDK·공개 스킬·OSS 실행 코드는 도입하지 않았다. 실제 Google CSV는 URL 제공 후 확인하며, 로컬 격리 시험은 배포·실기기 증거가 아니다. [동작·설정](../../research/collaboration-console/README.md), [시험·한계](../../research/llm-wiki/status/reports/2026-10-18-sheet-sync.md).

## D-131 도구별 허용 입력 항목과 입력 마스킹은 도구 심사에 붙인다 (2026-10-18, POL-31·G04.06)

- 문제: 등록 시 인자 범위는 고정 계약의 전 항목(D-91 이후 추가 항목 금지)이었고, 민감정보가 든 인자는 외부·공급자 호스팅이면 차단만 했다. 필요한 항목만 넘기거나 민감정보를 지워 보내는 선택지가 없었다.
- 결정: 도구 심사(`ToolReview`)에 `inputs`(허용 입력 항목, 없으면 계약 전체)와 `mask`(입력 마스킹)를 둔다. ① `inputs`는 계약에 있는 이름만, 필수 항목은 뺄 수 없다. 파생 인자 범위(`derived_constraints`)가 그 항목만 남기고, 게이트웨이는 정책 질의 전에 `P-INPUT-FIELD-001`로 거부한다(원격 검토가 직접 쓴 스키마에도 적용). 재심사는 고정 계약(`mcp_tools.input_schema`)에서 다시 잘라 넓힐 수 있다. ② `mask`면 이미 쓰는 Presidio Anonymizer(`privacy.mask_payload`)로 인자 문자열의 탐지값을 `[REDACTED]`로 바꿔 보내고, 정책은 실제로 나가는 값(잔여 개인정보 없음)으로 판정한다. 키·숫자·키=값 맥락의 자격 증명은 가릴 수 없어 `P-DATA-INSPECTION-001`로 막는다. 원장 `classification.masked_inputs`에 가린 유형을 남긴다.
- 근거: 새 의존성 없이 기존 OSS(Presidio, jsonschema)와 심사 기록을 쓴다. Gitleaks 탐지(`dlp`)는 원래 인자 기준이라 마스킹으로 비밀 전달 판정을 피할 수 없다(POL-31 "자격 증명은 별도 전달").
- 한계: 마스킹은 Presidio 인식기가 찾는 유형까지다. 원장 `request_payload`에는 직원이 보낸 원문이 남는다(감사 목적, 기존과 같음).
- 보강(같은 날, Codex sol 적대 검증 3·10번·기기 시험): 마스킹은 문자열 단위라 가린 인자 전체를 다시 검사해 남은 유형을 정책 `pii_types`로 넘긴다. 가린 유형·송신 인자 해시는 `policy_input.request.masked_types`·`outbound_sha256`으로 원장에 남는다(원장에 classification 열이 없어 처음엔 증거가 사라졌다). 허용 입력 항목은 원격 검토 등록·재심사에서도 고정 계약과 대조한다(`review.check_inputs`). 원본 DLP 라벨은 그대로라 실행(x) 도구는 가려도 `P-DLP-001`로 계속 막힌다(의도한 보수 판정).

## D-132 외부 전송은 심사한 목적·목적지·등급 쌍에 결속한다 (2026-10-18, POL-26·G04.05)

- 문제: PAC-12는 "승인된 최종 목적지·등급 쌍"을 요구하지만 도입 등록 서버의 쌍은 늘 비어 있었고 최종 목적지 검증도 항상 거짓이어서, 승인된 전송과 승인 밖 전송을 가르지 못하고 전부 막았다.
- 결정: 도구 심사에 `grade`(외부 전송 최고 등급, 공개 기본·일반까지)를 두고, PAC 사실의 `transfer_pairs`를 그 도구의 심사 목적·목적지·등급에서 만든다(`pac.transfer_binding`). 최종 목적지는 실행기 출구 프록시가 심사 목적지만 허용하는 서버(D-114)에서만 검증된 것으로 본다. 공급자 호스팅·카탈로그 서버, 목적지 둘 이상, 심사 밖 목적지·등급은 그대로 PAC-12 차단이다. 심사 조건(목적·목적지·등급)은 승인 범위 해시에 들어가 바뀌면 개별 승인이 다시 필요하다.
- 근거: 이미 있는 OPA PAC-12 규칙과 실행기 프록시를 이어 붙였다. 중요 등급·개인정보 외부 전송은 역할과 무관하게 `MCP-DATA-EGRESS-001`이 계속 막는다.
- 한계: 호출마다 목적을 선언받지 않는다. 목적은 도구 심사 단위이고, 호출의 목적지·등급이 그 심사와 맞는지로 판정한다.
- 보강(sol 1·2번): 콘솔 등록 서버는 인자 추출기가 없어 목적지가 비어 결속이 걸리지 않았다. 주소형 이름(url·uri·href·link·endpoint, 중첩·배열 포함)의 값을 목적지로 뽑고 같은 호스트는 하나로 센다. 본문 속 링크는 읽지 않는다. 최종 목적지 검증은 실행기 출구 허용 목록(서버 전 도구 심사 목적지의 합)이 이 도구의 심사 목적지 안일 때만 참이다(다른 도구 목적지로의 redirect 차단).

## D-133 서버 간 중요정보 전달은 받는 도구가 심사받은 경우만 허용한다 (2026-10-18, POL-33·G04.07)

- 문제: P-CHAIN-001은 중요정보 열람 뒤 **외부** 전송만 봤다. 한 서버에서 읽은 중요정보를 다른 내부 서버에 쓰는 경로는 판정에 없었다.
- 결정: 같은 검증된 주체가 10분(`CHAIN_WINDOW_MINUTES`) 안에 중요 등급을 실제로 읽은 **다른** 서버 목록을 쓰기·실행 호출의 `request.flow_sources`로 넣고, 받는 도구의 심사 `accepts_from`에 없는 서버가 하나라도 있으면 OPA `P-FLOW-001`(우선순위 47, 관찰 모드에서도 집행)로 차단한다.
- 근거: OSS 조사에서 Portcullis·MCPGuard 같은 MCP 프록시가 세션 오염 표지+OPA/Rego 구조를 쓴다. 우리는 이미 OPA와 원장이 있어 같은 구조를 새 프로세스 없이 붙였다. Invariant Guardrails·CaMeL·FIDES류 정보흐름 통제는 별도 런타임·추적 형식이 필요해 도입하지 않았다.
- 한계: 주체 단위의 거친 표지라 관련 없는 쓰기도 막을 수 있다(오탐 쪽). 내용 지문 대조로 좁히는 것이 다음 단계다.
- 보강(sol 4번): 공급자 호스팅 서버는 읽기도 모든 인자를 조직 밖으로 받으므로 흐름 출처를 받고, `accepts_from`으로도 풀 수 없다(외부 반출 허가가 되지 않게). 판정과 실제 전송 사이에 새로 생긴 열람은 반영하지 않는다(sol 6번, 한계).

## D-134 데이터·기능 단위 사용자 동의는 콘솔에서 받는다 (2026-10-18, POL-08·G02.05)

- 문제: 연결 승인(관리자)은 있었지만 직원 본인이 도구·데이터 등급 단위로 동의하는 절차가 없었다.
- 결정: 도구 심사에 `consent`를 두고, 그 도구의 호출이 실행될 판정(허용·경고·제한)이면 `user_consents`에서 본인의 유효한 동의(같은 심사 조건 해시, 같거나 높은 등급, 90일)를 찾는다. 없으면 `P-CONSENT-001`로 막고 확인 요청(PENDING)을 남긴다. 직원은 콘솔에서 동의·거부·철회하고, 변경은 `approval_events`에 남는다. 거부한 등급은 다시 묻지 않는다. 심사 조건이 바뀌면 이전 동의는 덮지 않는다.
- 근거: MCP 2025-06-18의 elicitation(`elicitation/create`)이 표준 확인 경로지만 에이전트가 조종하는 같은 클라이언트를 지나고 일부 클라이언트는 자동 수락을 지원해, 본인 로그인 화면(콘솔)이 더 강한 대역 밖 확인이다. elicitation은 알림 경로로 나중에 붙일 수 있다.
- 한계: 동의는 직원 본인 기준이다. 정보주체(제3자)의 동의 관리는 범위 밖이다.
- 보강(기기 시험·sol 7·8번): 동의 결정과 `approval_events` 기록을 한 트랜잭션으로 묶고 결과값은 표의 CHECK에 맞춘다(동의=approved, 거부·철회=rejected+사유). 요청 때의 심사 조건 사본(`terms`)을 남겨 화면에 목적·외부 목적지·입력 항목을 보인다. 판정 뒤 전송 직전의 철회는 그 호출에 반영되지 않는다(sol 5번, 한계).

## D-135 통제 효과는 같은 정책 입력을 적용 전후 번들에 보내 6개 잠정 지표로 비교한다 (2026-10-18, G10.05)

- 결정: 제품 밖 `full_stack_lab/eval/before_after.py`(표준 라이브러리)가 같은 사례를 적용 전(`none` 또는 Git ref)·후 OPA 번들에 게이트웨이와 같은 경로로 보내 공격 차단율·정상 허용률·오탐률·정밀도·차단 사유 일치율·판정 지연 p50/p95를 낸다. 반복 간 흔들림·기대 불일치를 따로 적는다. 사례는 PAC 문서가 있는 `opa/replay_cases_pac15.json`에서 만든다(PAC 없는 옛 사례는 정상까지 INPUT_CONTRACT로 막혀 지표가 무의미했다).
- 근거: OPA(OSS) 고정 이미지 `openpolicyagent/opa:1.20.2-static`과 기존 재생 사례를 그대로 쓴다. 지표 6개는 위키에 정의가 없어 잠정안이며 팀 평가계획에서 확정한다.
- 한계: OPA 판정만 비교한다. 게이트웨이 앞단 판정(입력 항목·동의·마스킹)과 실제 MCP 실행 효과는 기기·PJ1 시험이 맡는다.

## D-137 도입 서버 공급자 보증을 승인에 묶고 EOL은 승인 만료로 연결한다 (2026-10-20, DEV-68)

- 문제: 도입 승인과 등록부에 공급자 법인·연락처·취약점 공개 창구·지원 종료 근거가 구조화되어 있지 않고, 지원 종료 뒤에도 기존 승인 자동 연장 경로가 실행될 수 있다.
- 결정: 승인 때 공급자 법인명, 공급자 연락처, 보안 연락처, 지원 종료일, 취약점 공개 정책 HTTPS 주소를 필수로 검사한다. 하위 처리자 여부·SBOM/VEX 제출 여부·계약 근거 참조·종료 전략 메모도 선택 보증 항목으로 함께 보존한다. 빠진 항목이나 지난 지원 종료일은 한국어 사유로 승인을 거부하고, 제출된 항목은 도입 요청 증거와 `registry/runtime/servers.json`에 보존한다. 날짜만 주어지는 지원 종료일은 다음 날 00:00 UTC부터 만료로 처리하며 자동 연장은 그 상한을 넘지 않는다. 상한이 지난 서버는 기존 `approval_valid_until` / `P-APPROVAL-EXPIRY-001` 경로에서 차단되고 사람의 재승인을 기다린다. 관리자 인증이 필요한 `/api/registry/export?format=json|csv`는 같은 런타임 대장에서 도입 등록 서버를 정렬해 내보내며 행 정본의 SHA-256을 응답 JSON 또는 `X-Registry-SHA256` 헤더에 포함한다.
- 근거: DEV-68 제안 범위와 수용 기준, RQ-04의 누락 시 보류 선택, POL-03(보안 업데이트 지원), POL-07(외부 제공자 처리 조건), POL-01(출처·무결성), POL-39(취약점 수정·격리). 서버 처리·저장 위치는 DEV-69에 남긴다. 추가 의존성이나 정책 ID는 만들지 않는다.
- 한계: 연락처와 정책 URL은 승인자가 제출한 값으로, 제공자 시스템이나 정책 문서의 진위·가용성을 자동 검증하지 않는다. 등록부 내보내기 해시는 생성 시점의 행을 식별하며 전자서명이나 별도 감사 원장 증명은 아니다. 재승인 대기는 만료 시점 이후 기존 경로에서 강제되므로 실기기/PJ1과 실제 OPA 판정은 별도 확인이 필요하다.
## D-141 원장 보존은 관할 하한을 강제하고, 만료 구간은 DB 밖 서명 봉인에서 사슬을 잇는다 — 행 삭제는 보류 (2026-10-20, DEV-67·POL-38·48·49)

- 문제: 보존 기간이 지난 원장 구간을 폐기해야 하는데(계획서 2장·7장), 원장은 해시 사슬이라 앞부분을 지우면 검증이 끊기고 백업 복원으로 지운 구간이 되살아난다. README 원칙 5는 "판정 기록을 고치거나 지우는 코드를 쓰지 않습니다"다.
- 결정: ① `GET/PUT /api/audit/retention`이 선택한 관할 팩 중 가장 긴 하한(미선택 366일) 미만을 422로 거부하고 변경을 `approval_events`(`ledger-retention`)에 남긴다. ② 만료 구간 폐기 결정은 D-123 서명 폐기 목록에 `kind="ledger"` 봉인(마지막 id·`entry_sha256`·기록 시각·보존 설정·사유·요청자≠확인자)으로 남긴다. 읽을 때 두 사람·하한·만료·단조 증가를 다시 확인하고 어기면 손상으로 본다. ③ 사슬 검증을 순수 함수 `contract.walk_chain`으로 옮기고, 최신 봉인 해시에서 시작해 봉인 이하 행이 다시 보이면 "되살아남"으로 실패시킨다. 폐기 목록을 읽지 못하면 봉인 없음으로 처리해 앞부분 누락은 기존처럼 끊김으로 보고한다. ④ `disposal.reconcile`은 `ledger` 기록을 서버 폐기로 처리하지 않는다.
- 불변식과의 구분: 봉인 구간 삭제는 남은 판정 기록의 내용·해시를 바꾸지 않고, 봉인 밖 삭제·봉인 해시 불일치·복원 되살아남을 모두 찾아내므로 "판정 기록을 고치는 코드"(AGENTS.md)가 아니다. 그러나 README 원칙 5의 "지우는 코드"에는 그대로 걸리고, `decisions_append_only` 트리거 예외는 추가형 DB 변경 규칙 밖이다. 그래서 **행 삭제 실행(요청·다른 관리자 확인·봉인 선행 기록·FK 정리·삭제·복원 후 재삭제)은 구현하지 않고** [설계](LEDGER_RETENTION.md) 2장에 남긴다. 소유자가 원칙 5에 예외를 명시하거나 RQ-03의 암호 삭제를 고를 때까지 원장 행은 지워지지 않는다.
- 근거: 새 의존성 없이 D-123의 서명·연쇄 폐기 목록과 기존 해시 사슬을 이어 썼다. 하한 값은 계획서 7장의 구속력 있는 의무 조항만, 개월·연은 가장 긴 달력 일수로 올려 잡았다.
- 한계: 키 없는 SHA-256 사슬이라 DB 쓰기 권한자가 봉인 뒤 행을 다시 계산하는 것은 막지 못한다. DB와 폐기 볼륨·키를 함께 되돌리면 탐지하지 못한다. 하한은 문서별 값이라 고객 법무가 확인한다. 삭제 의무(최대 보존)·주변 표 보존은 다루지 않았다. 지금은 봉인을 쓰는 제품 경로가 없어 봉인 검증은 시험에서만 동작한다.
## D-136 호출 결과는 연결·정책 판정·도구 업무·독립 효과로 분리한다 (2026-10-20, DEV-48)

- 문제: 기존 `decision=Block`에 정책 거부·검사기 장애·허용 후 연결 실패가 섞였고, `upstream_executed`는 MCP 응답 확인일 뿐 업무 성공이나 독립 효과의 증명이 아니었다. Context7 월 할당량 오류도 `is_error=false`면 성공과 구분되지 않았다.
- 결정: 표준 라이브러리만 쓰는 `outcomes.outcome_axes`를 두고 `core`에서 재노출한다. 새 기록은 nullable `decisions.outcome` JSONB에 네 축의 한국어 스냅샷을 저장한다. 이전 열·행은 수정하지 않는다. 신규 원장 지문은 체인 8판에 outcome을 포함하고 1~7판 정의는 유지한다. 이 값은 버린 응답의 업무 오류 정보도 포함하므로 단순 재계산 가능한 운영 통계로 보고 지문에서 제외할 수 없다.
- 판정: Allow·Alert·Restrict는 실효 허용, would 판정은 관찰값으로만 유지한다. `P-CONTROL-*`, `P-DATA-INSPECTION-001`, `MCP-CATALOG-001`, `INPUT_CONTRACT`, `POLICY_BUNDLE`의 차단은 통제 장애 차단으로 분리한다. 출력 Presidio 장애도 기존 `MCP-OUTPUT-001` 집행을 유지하며 통제 장애 차단+응답 보류로 기록한다. 허용 뒤 `MCP-UPSTREAM-001`은 정책 축 허용과 연결·업무 실패를 분리한다. 통제 동작이나 정책 ID를 추가·완화하지 않는다.
- 근거: [고정 OSS·명세·공개 스킬 대조와 요구사항 시험 연결](../../research/llm-wiki/analysis/outcome-axes-d136.md). ContextForge의 정책 오류·엔진 오류 구분만 참고하며 분석 상단 정정에 따라 전체 fail-open이라는 주장은 채택하지 않는다. 신규 의존성·코드 복사 없음. GitHub 공개 스킬의 현재 commit 고정과 원격 HEAD 재확인은 네트워크 실패로 미완료다.
- 범위: 공급자 실패는 문서로 확인한 월 할당량 응답 접두어와 실제 HTTP 예외의 401·403·429에 한정한다. 원문을 추가로 저장하지 않는다. `is_error`는 도구 오류, 출력 보류는 응답 보류다. 확정 답변이 없는 전송과 필요한 필드가 없는 과거 행은 업무 미확인으로 남긴다. 정상 응답의 업무 성공은 응답 수준의 판정이며 업무 내용 자체를 별도 검증했다는 뜻이 아니다.
- 효과·조회: 전송 전이면 실행 안 됨, 전송했거나 intent가 pending·uncertain·resolved이면 독립 효과 미확인이다. 기존 관리자의 confirmed_executed·confirmed_not_executed만 조회 시 효과에 반영한다. `outcome`은 기록 스냅샷, `outcome_axes`는 조회 투영이며 최신 효과 투영을 과거 지문이라고 부르지 않는다. 감사 조회에서 계산에 쓴 오류 원문은 응답에 포함하지 않는다. 콘솔은 네 축을 라벨·값 칩으로 표시한다.
- 한계·중단: Python 순수/대역 시험 8건(대표 사례 17개), 새 화면 함수 시험 2건, 기존 console-state 15건 통과. 기존 자격정보 경계 AST 시험의 새 `outcome_axes`·`httpx` 주입 누락으로 16건 중 2건 NameError가 발생했다. **기존 시험 변경 필요**로 시험 파일은 수정하지 않고 구현을 중단했다. 로컬 `--gateway` 시험은 psycopg 부재로 실패했고 pyflakes도 미설치다. 실제 PostgreSQL·혼합 체인·SDK·브라우저·솔루션 기기/PJ1 검증은 미실행이다. [작업 보고](../../research/llm-wiki/status/reports/2026-10-20-result-outcomes.md).
## D-138 서버 처리·저장 위치와 조직 국외 이전 규칙 팩 (2026-10-20)

- 문제: DEV-69 / POL-26·10·40. URL·목적 결속(PAC-12, D-132)만으로 처리·저장 국가나 처리 주체를 알 수 없다. 공급자 서버는 읽기 호출의 인자도 수신하며, 국가 누락을 국내로 추정하면 기본 차단을 우회한다.
- 결정: 도입 등록·원격 계약 심사 사양에 `residency`(ISO 3166-1 alpha-2 국가 목록 `processing_countries`·`storage_countries`, `processor`, `evidence_ref`, `transfer_basis`)를 더한다. 원격 승인 해시와 등록 비교에 포함하고 등록·심사·승인 이벤트에도 남긴다. 운영 중 사양의 위치 변경은 같은 도입 승인으로 덮어쓸 수 없으며 새 도입 신청/독립 승인이 필요하다. 구 승인에 필드가 없으면 원격 계약 재검토가 필요할 수 있다.
- 결정: 내부 실행기 등록은 실제 ACTIVE 실행기 확인으로만 `internal`이 되며, 국가를 호스트명/IP로 추정하지 않는다. 검토 카탈로그의 내부 서버와 실행기 서버는 `organization.machine_location`을 사용한다. 기본 KR은 조직 배치 설정값이지 실측 증거가 아니므로 배포 전에 운영자가 확인한다. 공급자 호스팅 서버는 자기 심사 속성만 사용한다. 외부 URL·메일 목적지는 `organization.destination_locations`의 정확한 호스트/도메인별 위치를 별도로 확인한다. 서버의 국내 위치로 외부 목적지의 위치를 대체하지 않는다.
- 결정: `registry/data_residency.json`이 정본이고 `registry/render_residency.py`가 `opa/residency.json`을 생성한다. `field up`은 두 파일의 일치를 먼저 검사한다. 게이트웨이는 정본/렌더링을 대조하고 OPA는 실제 로드한 팩 해시와 요청의 팩 해시를 비교한다. 누락·오류·불일치는 `P-RESIDENCY-001` 차단이다. 등급별 국가 규칙은 허용/승인 필요/금지를 표현하며 모든 처리·저장 국가와 목적지에 적용한다. 내부 이상 등급의 국가·처리 주체·위치 근거 누락도 차단한다.
- 결정: 잠정 조직 기본값은 공개 `* 허용`, 내부 `KR 허용 / * 승인 필요`, 중요 `KR 허용 / * 금지`다. 공개 외 데이터의 국외 이전 근거가 없으면 허용 국가여도 승인 필요로 남긴다. 근거 문자열 존재를 법적 유효성 자동 검증으로 해석하지 않는다. 금지는 건별 승인으로 완화하지 않는다. 차단 우선순위 48, 승인 필요 83으로 기존 계약·권한 차단(50~82)을 승인이 덮지 않는다. 기존 DLP·PAC-12·흐름 통제는 계속 적용된다.
- 결정: 위치·목적지·팩 해시를 기존 PAC baseline에 결속해 건별 승인 digest에 포함한다. 기존 PAC-13의 독립 승인·권한·기한·일회용 상태를 재사용한다. `approval.granted`만으로는 허용하지 않는다. 기존 실행 직전 `pac.build`/OPA 재판정에서 최신 위치와 팩을 다시 읽고 관찰 모드에서도 완화하지 않는다. 승인 화면에는 판정 당시 원장의 위치 값을 표시한다. 원장은 수정하지 않는다.
- 근거: [DEV-69 근거 조항 13건](../../research/llm-wiki/analysis/compliance/dev-plan/README.md), [규제 매트릭스](../../research/llm-wiki/analysis/compliance/README.md), [시행일](../../research/llm-wiki/analysis/compliance/key-dates.md), [POL 의미 매핑](../../research/llm-wiki/analysis/drive-curation/policy-id-mapping.json), 한국 개인정보 보호법 28조의8([LIB-L01](../../research/llm-wiki/papers/LIB-L01.md)), GDPR Ch.V([LIB-M06](../../research/llm-wiki/papers/LIB-M06.md)), PIPL 38·40([LIB-M29](../../research/llm-wiki/papers/LIB-M29.md)). 국가별 규정의 실제 적용 판단은 잠정이며 최신 법무 확인 대상이다. 인도 등의 시행 전 요건을 현재 국가 차단 목록으로 전환하지 않았다.
- OSS·공개 스킬 검토: GitHub에서 `SKILL.md data residency OPA` 및 `open-policy-agent/opa`를 탐색했다. 바로 적용할 공개 스킬은 확인하지 못했고 외부 스크립트를 실행하지 않았다. 기존 OPA 1.20.2-static(Apache-2.0, 위키 고정 commit `b2c26708e9d55645d7f837db495031f7e4152594`)의 JSON data/후보 규칙과 Pydantic 검증을 재사용한다. commit은 [기존 고정 분석](../../research/llm-wiki/analysis/oss-deep/deps-sdk-authlib-opa.md)의 값이며 이번 원격 ref 재조회는 실패했다. [상류 저장소](https://github.com/open-policy-agent/opa)와 [공식 외부 data 설명](https://www.openpolicyagent.org/docs/external-data)을 참고했으며 새 의존성은 없다.
- 한계: 공급자 문서/사람 심사에 기초한 선언 속성이다. 실제 클라우드 배치·보존·하위 처리자·서버 내부의 숨은 송신·리디렉션 전체를 관측하지 않는다. 인자에 표시된 외부 목적지만 분류할 수 있다. 등급은 기존 보수적 분류를 재사용한다. 최종 재판정 이후 dispatch 기록 사이의 파일 변경 경합은 원자적으로 봉쇄하지 않는다. OPA·실제 DB·실제 OSS MCP·PJ1·콘솔 화면 검증은 미실행이며 구현 완료를 현장 검수 완료로 보지 않는다. [요구사항/시험 정본](../../research/llm-wiki/analysis/dev69-data-residency/README.md).
- 보강: 이미 등록된 제공자 운영 Console 서버는 `POST /api/registry/servers/{server_id}/residency`로 재심사한다. 사내 실행 위치는 계속 조직 기기 위치 설정으로 관리한다. 신청자와 다른 관리자가 ISO 위치 필드를 검증해 `spec.residency`만 갱신하고, `residency_review`·이력·`approval_events`에 심사자·시각·이전 위치 SHA-256을 남긴다. PAC 사실은 갱신된 값을 읽으며 `remote_contract.registration`과 계약 등록 비교는 변경하지 않는다. 신청자를 확인할 수 없는 등록은 차단한다.

## D-144 사고 증빙은 동일 원장 스냅샷으로 만들고 관할 팩의 단계별 기한을 추적한다 (2026-10-20, DEV-66)

- 문제: 감사 내보내기는 원장 전체의 해시 사슬 검증과 페이지 내보내기를 제공하지만 사고 기준 시각·영향 범위·단계별 보고 기한으로 묶인 증빙은 없었다.
- 결정: 관리자 사고 API가 사고 시작·탐지·(선택)평가 시각, 원장 영향 범위(기간·서버·도구·주체), 관할 팩을 기록한다. 호출 행과 전체 원장 사슬 검증은 같은 `REPEATABLE READ, READ ONLY` 스냅샷에서 읽는다. 패키지에는 결과 네 축·정책 사유·사슬 검증·관계된 승인/철회 및 연결 중지 이력·보고 단계와 `query_count == included_count`를 담고 정렬 키 UTF-8 JSON SHA-256으로 봉인한다. 호출 원문은 투영하지 않고 주체·관리자 식별자는 해시 참조로 바꾼다. 손상된 체인은 성공으로 바꾸지 않고 검증 결과 그대로 내보낸다.
- 결정(RQ): RQ-01은 12개월 기본+관할 팩 상향, RQ-02는 값마다 근거 ID·조항을 둔 제품 내 관할 팩, RQ-03은 구간 봉인 해시 우선(행 삭제는 D-141 제약 유지), RQ-04는 공급자 보증 누락 시 도입 보류, RQ-05는 팩에 표시된 수동 확인 항목만 법무 확인 대상으로 채택한다. RQ-06은 신청자 입력+공급자 문서 근거, RQ-07은 도입 심사자의 중대 영향 라벨, RQ-08은 최고 등급 가정 후 기간제 유예를 각각 후속 기능의 권장값으로 채택한다.
- 결정: `full_stack_lab/registry/field/incident_jurisdictions.json`에 중국 핵심/일반, EU NIS2·GDPR·CRA, 한국 정보통신망법·개인정보 보호법, 인도 DPDP, 싱가포르 기한 단계를 둔다. 일반 `/registry/field`와 field 전용 `/registry-field` 마운트가 같은 원본을 읽는다. 수치가 없거나 기산 시각(평가·수정 가능 시점)을 제품이 기록하지 않은 단계는 임의 계산하지 않고 `수동 확인 필요`로 둔다. 임박 경보 기준은 팩별 운영값으로 두며 법정 기한으로 해석하지 않는다. 기존 운영 경보 테이블·전달 경로를 재사용하고 30초 heartbeat로 타이머 중단을 `확인 불가`로 표시한다. 보고 완료 이력은 추가 전용으로 남긴다.
- 근거: [DEV-66 설계·RQ 결정표·보고 기한 대조표](../../research/llm-wiki/analysis/compliance/dev-plan/README.md), [시행일 및 상태](../../research/llm-wiki/analysis/compliance/key-dates.md), [POL 의미 매핑](../../research/llm-wiki/analysis/drive-curation/policy-id-mapping.json), D-136 결과 축·D-141 원장 보존·append-only 경계. 신규 의존성이나 정책 ID는 없다.
- 한계: 관할·사고 적용성, 사고 심각도, 기한 기산 사실은 관리자 입력과 잠정 법령 매핑에 의존한다. 한국 개인정보 보호법의 구체 시한, 인도 규칙의 시행 여부, CRA 수정 가능 시점 등 표시된 항목은 법무 확인이 필요하다. 감사 패키지 해시는 서명이 아니며 관리자 API를 통한 원장 반출·패키지 대용량 제한은 없다. 운영 타이머와 실 DB·콘솔은 로컬 검증만으로 효과가 입증되지 않는다.
