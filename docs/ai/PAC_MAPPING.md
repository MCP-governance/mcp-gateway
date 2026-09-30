# PAC-01~15와 이 Gateway의 통제 대응

> 팀원이 제안한 실행 전 정책 15개(`PAC-01`~`PAC-15`, 별도 Rego 초안 `mcp.pac15`)를 이 저장소의 통제와 맞춰 본 표다.
> 이 문서는 **어느 PAC이 이미 집행되고 있고, 어느 것이 구조상 집행될 수 없는지**를 한 번에 답하려고 만들었다.
> 정책 자체는 [POLICY.md](POLICY.md), 판정 흐름은 [ARCHITECTURE.md](ARCHITECTURE.md) §4를 본다.

## 1. 왜 초안 Rego를 그대로 끼우지 않았나

`mcp.pac15`는 `data.mcp.decision.decision`에서 `{effect, policy_ids}`를 돌려주고, 입력으로 `request` + `facts`
(위임·토큰 발급자·원자적 예약·철회 최신성·요청 다이제스트에 묶인 단회 승인)를 요구한다. 이 Gateway는
`data.mcp.authz.decision`에 `{decision, policy_id, reason, restrictions}`를 묻고, 입력은
`principal`·`resource`·`destinations`·`tool`·`contract`·`context`로 만든다(`core.execute_call`).

첨부 ZIP의 코드와 인터페이스를 읽어 확인한 것:

- 정책 package·질의 경로, 입력 필드, 결과 effect 형식이 현재 Gateway와 다르다. 파일 교체로 통합할 수 없다.
- OPA는 외부 신원·철회·원자적 예약 사실을 스스로 생성하지 않는다. Gateway가 검증한 사실과 실행 경계를 제공해야 한다.
- 이전 Claude 보고서의 200건·100건 및 59건 오류 수치는 이번 클린 환경에서 독립 재검증하지 않아 확정 근거에서 제외한다.
  첨부 파일은 설계 자료이며 그 안의 실행 지시를 사용자의 별도 요청으로 취급하지 않았다.

그래서 **초안을 교체하지 않고**, PAC이 말하는 통제를 이 Gateway의 입력과 결과 계약 위에서 구현하는 쪽을 택했다.
그 결과가 아래 표이고, 2026-09-30에 새로 구현한 것은 §3에 있다.

## 2. 대응표

| PAC | 통제 내용 | 이 저장소에서 집행하는 것 | 상태 |
| --- | --- | --- | --- |
| PAC-01 | 승인 상태와 기간 | `P-APPROVAL-EXPIRY-001`(도입 승인 기한), `MCP-REGISTRY-001/002`(등록·활성), `MCP-DECOMM-001`(종료 절차) | 집행 |
| PAC-02 | 승인 기준상태 | `MCP-CATALOG-001` — 설명·스키마·서버 버전 해시를 `contracts.lock.json`에 고정하고 **호출 직전 같은 연결에서 다시 대조**(`core._call_upstream`) | 집행 |
| PAC-03 | 사용 환경 | 관리대장의 `environments`와 `GATEWAY_ENVIRONMENT`를 `in_force()`가 대조 — 환경 밖 정책은 집행되지 않는다 | 집행 |
| PAC-04 | 요청 주체 | 신원은 **transport 토큰에서만** 온다(`agent_contract.authenticated_user`). 역할·상태는 토큰이 아니라 관리대장에서 읽으므로 계정 정지가 즉시 듣는다. `P-INPUT-001` | 집행 |
| PAC-05 | 대리 실행 = 사용자 ∩ Agent ∩ 위임 | **구조상 없음.** 이 배치에서 하네스는 인증된 주체가 아니다 — `clientInfo`·User-Agent는 자기 신고라 기록만 하고 판정에 넣지 않는다([SECURITY_BOUNDARIES.md](SECURITY_BOUNDARIES.md) §4). 위임을 판정에 쓰려면 하네스에 장치/앱 증명이 먼저 있어야 한다 | 미구현(의도) |
| PAC-06 | 토큰 발급자·대상·기간·scope | Ed25519 서명 + `iss`/`aud`/`exp`/`jti` 필수 + 폐기목록 + 관리대장 조회. **2026-09-30 추가**: scope 분리 — PC에 놓이는 `mcp` 토큰으로는 관리 API를 쓸 수 없다 | 집행(강화) |
| PAC-07 | 서버·Endpoint·최종 접속 대상 조합 | endpoint는 레지스트리가 고정하고 `MCP-EGRESS-001`이 허용 목록과 대조, `MCP-TRANSPORT-001`이 평문 차단. 최종 대상은 `upstream.session`이 **리디렉션을 따르지 않아서**(`follow_redirects=False`) 등록된 곳 외로 가지 않는다 | 집행 |
| PAC-08 | 기능(서버+유형+ID+정의 해시) 허용목록 | 카탈로그에 없는 도구는 목록에 나오지 않고 호출하면 `MCP-REGISTRY-002`. 정의 해시는 PAC-02와 같은 경로 | 집행 |
| PAC-09 | 행위 정규화·권한 | `classify`가 인자에서 실효 행위(r/w/x)를 정하고 — 도구 이름이 아니라 **인자의 의미**로 — 권한 번들이 (역할×등급×행위)를 판정(`P-AUTHZ-DENY-001`/`ALLOW-001`) | 집행 |
| PAC-10 | 인자 경로에서 파일·명령·수신자 추출과 범위 | `P-INPUT-SCHEMA-001`(승인 스키마, 정책 전·집행 직전 2회), `classify`의 서버별 추출기, `P-SCOPE-001`(이용 관계가 허용한 자원 밖). **2026-09-30 강화**: SQL은 PostgreSQL 파서로 판정 | 집행(강화) |
| PAC-11 | 데이터 자산·등급 | `registry/catalog.toml`의 분류 규칙(최장 접두사, 미분류는 important), `P-CLASSIFICATION-001` | 집행 |
| PAC-12 | 외부 전송 목적지·등급 조합 | `MCP-DATA-EGRESS-001`(중요·개인정보의 외부 전송, 역할 무관·예외 불가), `P-DLP-001`, `MCP-EGRESS-002`(인자 목적지 SSRF), `P-X-RESTRICT-001`. **2026-09-30 강화**: 주소 정규화 | 집행(강화) |
| PAC-13 | 고위험 건별 단회 승인, 요청에 결합 | `P-X-APPROVAL-001`·`P-UNTRUSTED-CONTENT-001` → `approvals` 행에 `request_fingerprint`(정규 해시)를 묶고 승인 시 대조, 10분 만료, 실행 직전 승인 상태 재확인. **2026-09-30 추가**: 자기 요청 자기 승인 금지 | 집행(강화) |
| PAC-14 | 철회·중지 | 토큰 폐기목록(즉시), `principals.status`, refresh 재사용 시 가족 전체 폐기, `MCP-DECOMM-001`, 종료 케이스 C1~C4 | 집행 |
| PAC-15 | 반복·동시·연쇄 실행 제한(원자적 예약) | **2026-09-30 추가**: `call_reservations` 테이블 + 주체별 advisory lock으로 판정 전에 자리를 예약 → `P-RATE-001`(호출량), `P-RATE-002`(동시 실행), `P-RATE-003`(중복 호출). 연쇄는 `P-CHAIN-001`·`P-VOLUME-001`·`P-ANOMALY-001` | 집행(신규) |

## 3. 2026-09-30에 바꾼 것과 그 근거

바꾸기 전에 실제로 재현해 본 것만 적는다. 재현 스크립트는 `tests/adversarial_check.py`다.

### 3.1 목적지 주소 정규화 (PAC-07·PAC-12, `MCP-EGRESS-002`)

분류기가 호스트 문자열을 그대로 비교해서, 같은 내부 주소의 다른 표기가 **external**로 분류됐다.
실측(구현 전, 운영 중이던 컨테이너에서):

| 입력 | 이전 판정 | 실제 도달 대상 |
| --- | --- | --- |
| `http://0x7f.0.0.1/` | external | 127.0.0.1 |
| `http://0177.0.0.1/` | external | 127.0.0.1 |
| `http://169.254.169.254.nip.io/` | external | 169.254.169.254 (클라우드 메타데이터) |
| `http://corp-db.bob.local/` | external | 사내 DB |
| `http://intranet.bob.local./` | external | 사내 위키 |

`classify.host_category()`가 이제 (1) 후행 점·대문자 정규화, (2) `socket.inet_aton`으로 10진·8진·16진·축약
IPv4 해석, (3) IPv4-mapped IPv6, (4) 이름 안에 박힌 주소(`nip.io`·`sslip.io` 형태, 점·하이픈 표기 모두),
(5) 인프라 호스트의 FQDN 형태, (6) `internal_domains` 아래의 이름을 모두 infrastructure로 판정한다.
DNS는 조회하지 않는다 — 조회하면 판정과 실제 연결 사이에 시간 차가 생기고(TOCTOU), 조회 자체가 유출 신호가 된다.

### 3.2 SQL 판정을 PostgreSQL 파서로 (PAC-09·PAC-10)

정규식으로 문장 유형을 보던 것을 `pglast`(libpg_query, PostgreSQL 서버와 같은 파서)로 바꿨다. 이전 판정 실측:

| 입력 | 이전 | 지금 | 왜 |
| --- | --- | --- | --- |
| `select * into public.stolen from hr.salaries` | r | x | 테이블을 만들고 중요정보를 복사한다 |
| `select pg_terminate_backend(...)` | r | x | 다른 세션을 끊는다 |
| `select set_config('role','postgres',false)` | r | x | 세션 권한을 바꾼다 |
| `select nextval('...')` | r | w | 시퀀스 상태가 남는다 |
| `select pg_sleep(600)` | r | x | 자원을 붙잡는다 |
| `select $$; drop table x;$$` | x + 없는 테이블 `public.x` | r | 문자열 리터럴이다(오탐이었다) |
| `with d as (delete ...) select * from d` | w, 테이블 `public.d` | w, 테이블 `sales.orders` | CTE 이름을 회사 테이블로 세던 것 |

파싱되지 않는 입력은 `x`(가장 엄격)로 둔다 — 서버가 받아들이지 않을 문장을 "읽기"로 보는 쪽이 위험하다.

### 3.3 주입 탐지 규칙을 한 곳으로 (PAC-10)

같은 성격의 검사가 두 벌이었다: 등록 시점은 `poisoning.py`(6규칙+보이지 않는 문자), 인자·결과는 `core.py`의
짧은 정규식 8개. **가장 신뢰할 수 없는 내용(인자·결과)에 가장 약한 검사가 돌고 있었다.**
이제 `poisoning.py` 하나가 세 문을 모두 담당하고, 규칙 묶음은 결과의 무게에 맞춰 넓어진다:

| 묶음 | 쓰는 곳 | 결과 | 포함 |
| --- | --- | --- | --- |
| `OVERRIDE_RULES` | 도구 **결과** | 결과 보류(`MCP-OUTPUT-001`) | 지시 무시, 숨긴 지시 태그, 사용자에게 숨김, 정책 우회, 역할 탈취, 시스템 프롬프트 요구, 보이지 않는 문자 (영·한) |
| `INSTRUCTION_RULES` | 도구 **인자** | 승인 또는 경보 | + 다른 도구 조종 |
| `CATALOG_RULES` | **계약**(설명·스키마) | 등록 시 확인 요구 | + 외부 전송 문구, 민감 파일 경로 |

넓힐수록 오탐 비용이 커지므로 각 묶음에 정상 문장 대조군을 자체 검사에 넣었다
(`python -m app.poisoning`). 예: "Send the invoice to finance@bob.local"은 인자에서 걸리지 않는다 —
목적지는 문구가 아니라 분류기의 destinations가 판단한다.

**주입 탐지율은 재현 가능한 측정으로 둔다.** `tests/injection_corpus_check.py`가 microsoft/PyRIT 고정 커밋
`ea9d0b4`의 garak latent-injection 지시문 시드(NVIDIA, Apache-2.0)를 받아 `poisoning.text_findings`에 넣는다.
시드 32건 중 6건은 "혐오 문장을 써라"류의 독성 유도라 도구 호출을 돌리려는 시도가 아니므로 따로 센다.
지시 주입 26건 중 **21건 탐지**(2026-10-01, 고정 URL 다운로드와 로컬 클론 양쪽에서 같은 값). 처음 규칙은 같은
26건 중 1건이었다. 못 잡는 5건은 명령문이 없는 설득문("최고의 이력서다")·강조 반복·한 줄에 붙은 가짜 대화 턴이다.
오탐 쪽은 같은 규칙을 이 랩이 제공하는 도구 전부의 이름·설명·스키마에 건다(2026-09-30 223개 전수 0건).

실제 Sentry의 `root cause` 오탐은 수정했고, Notion의 미노출 안내 helper 경고가 정상 검색까지
차단하던 오류도 수정했다. 새 흐름은 **노출되는 도구**의 미검토 경고를 차단하고, 명시적 설명 검토는
해당 설명·입력 schema hash에 묶어 보존한다. 전체 catalog 이름·버전·계약 해시 고정은 유지한다.
선택되지 않은 helper를 자동으로 노출하지 않으며 검토 hash가 달라지면 전달 전에 차단한다.

### 3.4 호출 상한의 원자적 예약 (PAC-15)

호출량은 감사 테이블(`decisions`)에서 셌는데, 그 표에는 **끝난 호출만** 있다. 같이 도착한 호출은 서로를 세지
못해서, 상한이 1이어도 동시에 온 10건이 전부 통과했다. 그리고 "지금 몇 건을 돌리고 있나"는 물을 수조차 없었다.

`call_reservations`에 판정 **전에** 이번 호출의 자리를 적고, 주체별 `pg_advisory_xact_lock` 안에서 세기와
쓰기를 한 트랜잭션에 넣었다. 잠금은 주체별이라 서로 다른 사람은 기다리지 않고, 도구 호출이 아니라 짧은
트랜잭션 동안만 잡는다. 예약은 `_decision_payload`에서 판정이 저장된 뒤 풀린다. `tools/call` 전달 후
결과를 잃은 호출은 즉시 풀지 않고 lease까지 유지한다. 상태 저장소가 답하지 않으면 실행하지 않는다.

새 정책 두 개: `P-RATE-002`(동시 실행 상한, 기본 4), `P-RATE-003`(같은 인자의 같은 호출이 아직 실행 중).
전달 후 시간초과의 같은 요청 재시도는 lease 동안 `P-RATE-003`으로 막는다. 전달 전 연결 실패는
미실행으로 기록하고 재시도를 허용한다. lease 이후 원격 작업이 계속되는 경우의 exactly-once는 보장하지 않는다.
호출량과 중요정보 호출량은 완료 기록만이 아니라 먼저 도착한 예약도 함께 센다.

### 3.5 토큰 scope 분리와 자기 승인 금지 (PAC-06·PAC-13)

실측: 직원 PC의 하네스가 쓰는 MCP 토큰(`scope=mcp`, `bob-sso`가 `~/.cache/bob-sso/token.json`에 둔다)으로
관리 API가 그대로 열렸다 — `/api/state` 200, `/api/registry` 200, 승인 API는 역할 검사를 통과해 409(그 승인
건이 없다)까지 갔다. 관리자 계정이면 **PC의 파일을 읽을 수 있는 아무 프로세스나** 그 사람 이름으로 고위험
호출을 승인할 수 있었다는 뜻이다.

이제 관리 API(`admin_caller`)는 대화형 로그인으로 받은 `console` scope를 요구한다. 비대칭은 의도한 것이다:
`console` 토큰은 30분짜리이고 키트가 디스크에 쓰지 않는다. 그리고 `approve_request`가 요청자와 승인자가 같으면
거부한다 — 예외 관리대장이 이미 지키던 규칙(§8.6 자가 승인 금지)을 건별 승인에도 적용한다.

## 4. 아직 아닌 것

- **PAC-05(대리 실행)**: 하네스가 인증된 주체가 아니므로 "사용자 권한 ∩ Agent 권한"을 판정할 근거가 없다.
  헤더로 자기소개한 하네스를 인가 근거로 쓰지 않는다는 기존 결정([BENCHMARK_GATEWAYS.md](BENCHMARK_GATEWAYS.md) §7)을 유지한다.
- **PAC-13의 승인 다이제스트에 환경·자동 실행·대리 실행을 묶는 것**: 팀원 초안도 이 세 가지를 다이제스트에
  넣지 않아 승인 재사용이 가능하다(시험에서 9건 확인). 우리 `request_fingerprint`는 server·tool·arguments·
  user_token을 묶는다. 환경은 배치당 하나라 지금은 같은 값이지만, 다환경 배치를 하면 함께 묶어야 한다.
- **원격 MCP의 자격 연동**: 별도 자격 파일의 exact HTTPS resource·등록 주체·만료 검사는 추가했다.
  자동 OAuth refresh, RFC 8693 위임, 공급자 측 폐기 검증은 아직 아니다. 운영 절차는 [RUNBOOK.md](RUNBOOK.md)를 본다.

## 5. 후속 검토에서 보강한 경계

- scope 요구를 Gateway 관리 API뿐 아니라 Console 계정·도입·커넥터 관리의 공통 인증 경계에도 적용했다.
- SQL의 미검토 함수와 비표준 schema 함수는 `x`로 올린다. AST가 DB view·operator·함수의 순수성을 증명하지는 않는다.
  **2026-10-01 정정**: "검토한 함수"를 손으로 쓴 40개 목록으로 정했더니 평범한 분석 쿼리 40개 중 25개
  (`extract`, `row_number() over`, `split_part`, `percentile_cont` …)가 `x`가 되어 직원에게 차단됐다. 이제
  기준은 서버의 카탈로그다 — PostgreSQL 18.6 `pg_proc`의 내장 함수 2,787개와 변동성(`pg_builtin_functions.json`).
  불변·안정 함수는 PostgreSQL이 데이터베이스를 바꾸지 못하게 하므로 읽기, 휘발성 248개는 읽기 전용으로 확인한
  26개(random·크기 조회 등) 외에는 `x`, 내장이 아닌 함수와 사용자 스키마 함수는 그대로 `x`. 같은 40개가 0개로 줄었다.
- **자격 증명 유출(PAC-12)**: 발급자 접두어가 있는 토큰(GitHub·GitLab·Slack·Google·Stripe·OpenAI/LiteLLM `sk-`·
  Anthropic·JWT·AWS 비밀 키·`client_secret=` 할당)을 DLP 라벨과 Presidio `SECRET_TOKEN`으로 본다. 이전에는 9종 모두
  라벨이 없어 GitHub 토큰을 외부 메일로 보내도 통과했다. 규칙은 IBM CPEX `secrets_detection`(Apache-2.0)에서
  접두어형만 가져왔고, 같은 플러그인의 "32자 이상 hex·24자 이상 base64" 규칙은 커밋 해시·SHA-256을 매번 잡아
  외부 전송 차단의 근거로 쓸 수 없어 제외했다. 도구 **결과**에 섞인 토큰은 모델에 가기 전에 가린다.
- 배포 확인의 정책 일치가 `policy.rego`만 비교해서, 권한 번들(`data.json`)·관리대장·예외가 바뀌고 OPA가 다시
  읽지 않은 상태도 "일치"로 보였다. 이제 네 파일을 모두 대조한다(규칙 일치·데이터 일치를 따로 표시).
- 팀원 초안의 검토는 재현 가능한 형태로 [research/pac15-review](../../research/pac15-review/README.md)에 있다 —
  원본 200/200·결함 59건, 결함 7종을 고친 수정본 200/200·결함 0건.
- malformed URL/port는 fail-closed로 분류한다. 인자 주소 정규화는 upstream MCP 자체의 DNS 재바인딩 방어를 대신하지 않는다.
- code revision/hash와 OPA의 실제 로드 정책 hash를 Console의 `배포 확인`에서 비교한다.
- 종료 대상에는 비활성 과거 이용자도 남긴다. 서버 종료 차단과 확인된 비활성 계정 차단을 서로 다른 근거로 기록한다.
- 실측 결과와 시험 범위는 [OVERHAUL_VALIDATION_2026-09-30.md](OVERHAUL_VALIDATION_2026-09-30.md)에 기록한다.
