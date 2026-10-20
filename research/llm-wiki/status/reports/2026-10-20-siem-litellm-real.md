# 2026-10-20 SIEM·LiteLLM 실환경 연동 시험 (T1)

- 작업자: Claude Code (Sonnet 5.5)
- 코드 기준: 브랜치 `10/20-siem-litellm-real`, 시작 `origin/main 5b5a134`. 기기 제품 스택은 시험 중 조정자가 `10/20-dev73-impl 217da74`로 다시 배포했다(아래 6절).
- 시작 근거: 소유자 지시 "litellm같은 llmgw랑 os siem연동하라고 한게 코드만 남아있고 연결을 제대로 안해서 문제가 생긴 거 같은데 / 솔루션 기기 WSL에 두 개 깔아서 테스트". `AGENTS.md`(LiteLLM의 LLM 경로와 MCP 경로를 각각 확인, 신원·자격 경계 완화 금지).
- 해결할 문제와 완료 조건: ① 실제 OSS SIEM을 별도 컨테이너로 세우고 `siem-worker`를 운영자 방식으로 연결해 decisions·approval_events·ops_alerts 도착, UID 중복 제거, 워커 재시작·SIEM 중단 뒤 무손실·무중복을 행 수로 증명. ② LiteLLM을 별도 컨테이너로 세우고 실제 하네스 모델 호출·로그·키별 지출·정책 확인, MCP 경로를 LLM 경로와 따로 확인. ③ 제품 비방해, 정확한 런북.

## 결과 요약

| 항목 | 상태 |
| --- | --- |
| SIEM 설치(OpenSearch+Dashboards+Vector, 별도 프로젝트 `mint-siem`) | 구성·기동·검증 완료, 기기에서 계속 실행 중 |
| `siem-worker` 현장 활성화(`.env`+`up --no-deps siem-worker`) | 활성화·검증 완료, 계속 실행 중 |
| 백로그 전달·검색 | 147/147(기동 직후), 시험 종료 시점 238/238 일치 |
| 실제 하네스(PJ1 Claude Code) 판정 → SIEM | 확인(Block·PAC-01, 생성 2초 뒤 검색 가능) |
| ops_alerts | 현장 DB에는 실제(비합성) 경보가 0건이라 현장 경로는 **미실행**. 일회용 DB에서 제품 코드 경로로 만든 경보 1건을 같은 실제 SIEM에 전달·검색 확인 |
| 중복 제거(UID→`_id`), 워커 kill·재시작, SIEM 수신 중단, OpenSearch 중단 | 모두 손실 0·중복 0 |
| LiteLLM 1.105.0(별도 프로젝트 `mint-llm`) + Ollama + qwen3:0.6b | 기동, 계속 실행 중(LLM 경로만) |
| 하네스→LiteLLM | Claude Code 2.1.288·Codex 0.160.0(PJ1과 같은 판본) 컨테이너로 확인. 키별 지출·예산·모델 허용목록·분당 한도 적용 |
| PJ1 관리형 하네스→LiteLLM | 맞지 않음(근거 4절). 설정 변경·강제 시도 없음 |
| LiteLLM MCP 경로 | 공개 Microsoft Learn MCP로 별도 확인. 우리 Gateway를 우회하는 경로임을 실증 |

## 1. 환경과 판본

솔루션 기기 `user@100.83.175.111`(WSL2, 12코어, RAM 11.4GB 중 시작 시 가용 약 8.5GB, 디스크 908GB 여유). 시험 시작 시 제품 컨테이너 13개 + 별개의 옛 시험 스택 `mcpgw-interop-20261013`(건드리지 않음).

| 구성 | 판본·이미지 digest | 라이선스 |
| --- | --- | --- |
| OpenSearch | `opensearchproject/opensearch:3.8.0` `sha256:fafe3fc3…5236a40`(build e5a3c56) | Apache-2.0 |
| OpenSearch Dashboards | `3.8.0` `sha256:7fb7ec1b…852bbd` | Apache-2.0 |
| Vector(수신 앞단) | `timberio/vector:0.59.0-alpine` `sha256:0e36bc2a…15172b7a2`(0.59.0, a3231c7) | MPL-2.0 |
| LiteLLM | `ghcr.io/berriai/litellm-database:v1.105.0` `sha256:f99e4cc5…27e88`, 패키지 litellm 1.105.0, mcp 2.2.0 | MIT(enterprise 디렉터리 별도 라이선스, 사용 안 함) |
| Ollama | `ollama/ollama:0.40.3` `sha256:adca95a1…eff99` | MIT |
| 모델 | `qwen3:0.6b`(manifest `7df6b6e09427`, 522MB) | Apache-2.0(`ollama show --license`로 확인) |
| PostgreSQL | `postgres:18-alpine` `sha256:77f58511…a1873` | PostgreSQL License |
| 하네스 시험 이미지 | `mint-llm-harness:t1`(node:22-bookworm-slim + `@anthropic-ai/claude-code@2.1.288` + `@openai/codex@0.160.0`) | Claude Code는 Anthropic 상용 약관, Codex는 Apache-2.0(패키지 표기 기준, 약관 원문은 미독) |

digest 전체 값은 기기에서 `docker image inspect <태그> --format '{{index .RepoDigests 0}}'`로 다시 얻는다. 서명·attestation 검증은 미실행.

**SIEM 선택 근거.** `siem.py`의 송신 계약은 "이벤트 1건=HTTPS POST, Bearer 토큰, Idempotency-Key"다. OpenSearch 단독은 Bearer 불투명 토큰을 검증하지 못하고 POST로는 문서 `_id`를 지정할 수 없어 UID 중복 제거가 안 된다. Vector `http_server`는 TLS·사용자 지정 인증(VRL)·싱크 확인 뒤 응답(end-to-end acknowledgements)을 제공하고 `elasticsearch` 싱크의 `id_key`로 `_id`를 지정한다. Fluent Bit은 Bearer 검증이 없고 Logstash는 JVM이 하나 더 필요했으며 Wazuh·Graylog는 이 계약과 직접 맞는 입력이 없어 제외했다(문서·이미지 비교는 하지 않았고 위 계약 대조만으로 판단. 한계).

**자원.** 시험 중 실측 메모리: OpenSearch 969MiB, Dashboards 223MiB, Vector 40MiB, LiteLLM 798MiB, Ollama 2.5GiB(16k 컨텍스트 로드 시, 유휴 10분 뒤 해제), 워커 26MiB. 시험 끝 가용 RAM 약 4.2GB.

## 2. SIEM 구성 (저장소 `full_stack_lab/siem/`)

- `compose.yaml`: 프로젝트 `mint-siem`, 자체 네트워크, 게시는 Tailscale IP의 `:8688`(수신)·`:5601`(Dashboards)만. OpenSearch는 게시하지 않는다. 메모리·CPU 제한, `no-new-privileges`, digest 고정.
- `vector.yaml`: `POST /ingest`만 받는다(`strict_path`). TLS 종단(자체 CA가 서명한 SAN=Tailscale IP 인증서). 인증은 VRL로 `Authorization == "Bearer " + 토큰`이고 토큰은 `SECRET[]`(파일)로 읽어 설정 파일에 값이 없다. 헤더 `Idempotency-Key`와 본문 `metadata.uid`가 다르거나 시각이 없으면 버리지 않고 `mint-ocsf-rejected` 색인으로 보낸다. 문서 `_id`=`metadata.uid`, 색인 이름은 이벤트 시각의 연월(`mint-ocsf-2026.10`)이라 재전송이 달을 넘어도 같은 문서가 된다. 싱크 확인 뒤에만 2xx.
- `setup.sh`: 난수 토큰·OpenSearch 관리자 비밀번호·사설 CA와 서버 인증서를 만들고(값 비출력), 인덱스 템플릿(`time` 날짜, 복제본 0)과 Dashboards 인덱스 패턴 `mint-ocsf-*`(시간 필드 `time`)을 만든 뒤 제품 `siem-secrets/`에 `ca.pem`·`token`을 둔다.
- `verify.sh`, `ops_alert_probe.py`: 대조·일회용 DB 경보 전달 확인 도구.

실행한 것: 기기 `~/mint-siem-t1/`에 이 파일들을 올려 `SIEM_BIND=100.83.175.111 ./setup.sh /home/user/mcp-gateway/full_stack_lab/siem-secrets`.

**구성 중 발견한 함정(수정 반영됨).**
1. Vector `SECRET[]`는 파일 내용을 그대로 설정 텍스트에 넣는다. 토큰 파일 끝 개행이 YAML 블록 스칼라를 끊어 `could not find expected ':'`로 기동이 실패했다. 개행 없이 쓰도록 `setup.sh`를 고침.
2. 사용자 지정 인증의 `.headers` 키는 소문자(`authorization`)다. 대문자로 쓰면 올바른 토큰도 401.
3. `decoding: json`+`framing: bytes`를 지정하지 않으면 본문이 `message` 문자열로 들어간다.
4. 싱크 `index` 템플릿은 정적 접두사가 있어야 한다(`mint-ocsf-{{ _suffix }}`).
5. VRL에서 실패 가능한 호출을 처리하지 않으면 변환 오류로 이벤트가 버려지는데 소스는 이미 200을 돌려줄 수 있다. 모든 호출을 `?? 기본값`으로 막아 두었다.
6. 싱크 기본 배치 대기 1초 때문에 송신이 건당 1초에 한 건이었다. `batch.timeout_secs: 0.1`로 줄임(이후 시험에 적용; 백로그 147건은 1건/초로 약 3분에 소진).

기본 수신 거동 확인(기기에서 curl): 토큰 없음 401, 틀린 토큰 401, 올바른 토큰 200(같은 UID 2번 → 문서 1개), 다른 경로 405, 평문 HTTP는 연결 거부. OpenSearch를 멈추고 보낸 요청은 응답을 보류하다가 복구 뒤 색인됨(송신 쪽 5초 타임아웃과 맞물려 재전송 → 같은 `_id`).

## 3. 현장 활성화 방법과 실제 절차

`siem-worker`는 `compose.yaml`에 `profiles: [siem]`로 있고 `SIEM_URL` 등은 `.env`에서 읽는다. 기본 `field up`은 이 서비스를 목록에 넣지 않으므로 켜지 않는다. 이전에는 `.env` 키와 켜는 방법이 어디에도 없었고, `field up --with-siem`은 값이 없으면 워커가 즉시 죽어 재시작만 반복하며(그 명령은 gateway·opa도 강제 재생성한다).

실제 순서(실행함):
1. SIEM 설치(2절). 제품 `siem-secrets/ca.pem`(0644), `token`(0600, `sudo chown 10001:10001` — 워커 UID, `cap_drop ALL`이라 다른 소유자는 못 읽는다).
2. `.env`에 `SIEM_URL=https://100.83.175.111:8688/ingest`, `SIEM_TOKEN_FILE=/run/siem/token`, `SIEM_CA_FILE=/run/siem/ca.pem` 추가(기존 `.env`는 `/tmp/t1_env_backup_*`에 0600 백업).
3. 제품 컨테이너를 건드리지 않는 기동: field 환경 변수를 `field_dispatch`와 같게 내보낸 뒤 `docker compose -f compose.yaml -f compose.field.yaml up -d --no-deps siem-worker`(이미지 `mcpgw-55e075465e-siem-worker`는 게이트웨이와 같은 Dockerfile이라 빌드 캐시 적중).
4. 컨테이너→Tailscale IP:8688 연결은 별도 네트워크 연결 없이 `edge` 망에서 된다(워커 로그 `status=200`).

**코드 변경(최소, 커밋됨).** `full_stack_lab/console.sh`: `field siem up|status|down`(워커만 `--no-deps`로 생성·정지, 상태는 outbox 대기열 집계)과 `siem_require_config`(`.env` 세 키와 `siem-secrets/` 파일이 없으면 시작 전에 거절, `--with-siem`에도 적용). `docs/ai/FIELD.md`에 "SIEM 연동" 절. 이 변경을 기기에 반영하지 않고(배포는 조정자 몫) 복사본 `console.t1.sh`로 기기에서 실제 실행해 확인한 뒤 삭제했다: 빈 `.env`에서 `up`은 `.env에 SIEM_URL 가 없습니다`로 종료 코드 1, `status` 출력, `down`→`up`으로 워커만 정지·재생성(다른 컨테이너 StartedAt 불변). `bash -n` 통과. 변경한 Python 파일은 새 `siem/ops_alert_probe.py`뿐이며 pyflakes 통과. `gateway/app/siem.py`는 수정 없음.

## 4. SIEM 검증 결과 (숫자는 기기 실측)

기준: `siem_outbox`의 `(source:source_id)` 집합과 OpenSearch 문서의 `unmapped.source:source_id` 집합 대조(`verify.sh`), 문서 `_id`==`metadata.uid`, `_id` 중복 없음. 시각은 기기 로컬(KST)과 UTC가 섞여 있으면 병기.

| # | 시험 | 방법 | 결과 |
| --- | --- | --- | --- |
| A | 백로그 소진·검색 | 활성화 시점 대기 147건(decisions 65, approval_events 82) | 05:44:29Z 시작 → 약 3분 뒤 대기 0. outbox 147, 전달 147, OS 문서 147, 양방향 차집합 0, `_id` 중복 0. 원본 위반 없음 |
| B | 실제 하네스 결정 | PJ1 Claude Code로 markitdown 변환 요청 → 게이트웨이가 `PAC-01` Block | 결정 93: 생성 05:47:38, 전달 05:47:40(2초). SIEM에서 `decision=Block, policy_id=PAC-01, severity_id=3` 검색됨 |
| C | SIEM 수신 앞단 중단 | 수신(Vector) 정지 → 실제 하네스 3건 + 자연 발생 이벤트 → 워커 재시작 2회 포함 3분 | 중단 중 문서 증가 0, 대기 3→(자연 발생 포함 최대 3), 모두 `ConnectionRefusedError`, 시도 횟수 증가. 복구 후 약 2.5분 뒤(백오프) 마지막 행(시도 7회) 전달. 최종 outbox 156 = OS 156, 차집합 0 |
| D | 중복 재전송 | 이미 전달된 30행의 `delivered_at`을 NULL로 되돌려 재전송 | 30건 POST·200, OS 문서 156 유지, `_version>1` 문서 0 |
| E | 워커 kill | 90행 재전송 도중 `docker kill`(전달 25건 시점), 6초 뒤 시작 | 남은 대기 65 → 모두 전달. POST 91건, 200 90건, 서로 다른 UID 90개, **동일 UID 2번 전송 1건**(kill 순간 진행 중이던 `decisions:69`), OS 문서 156 유지 |
| F | OpenSearch 중단(수신 앞단은 가동) | 57행 재전송 도중 OpenSearch 정지 40초 | 대기 44, `TimeoutError`(수신 앞단이 색인 확인 전 응답 보류), 복구 후 모두 전달. POST 71, 재시도 14건, 동일 UID 2번 이상 14개, OS 문서 156 = outbox 156 |
| G | 제품 재배포 중 | 조정자의 `field up`(게이트웨이 재생성) | 워커는 목록 밖이라 재생성되지 않음(StartedAt 불변). 재배포 후 outbox 172 = OS 172 |
| H | 워커만 정지·재기동(`field siem down/up`) | 정지 중 결정 1건 대기 → `up` 후 소진 | 142/142, 차집합 0 |
| I | ops_alerts | 현장 DB에 비합성 경보 0건 → 일회용 PostgreSQL에서 제품 코드(`review.record_event`·`ops_response.emit_alert`)로 승인 이벤트 1·실제 경보 1·합성 경보 1 생성, 제품 `siem.py` 루프로 실제 SIEM에 전송 | 합성 경보는 큐에서 제외, 나머지 2건 전달, `unmapped.source=ops_alerts, kind=unapproved-connection, severity_id=3, synthetic=false` 검색됨. 시험 문서 2건은 삭제(현장 대조 오염 방지) |

마지막 대조(시험 말미, `verify.sh`): outbox 238 / 전달 238 / OS 238 / 구별되는 쌍 238 / 차집합 0·0 / `_id`==`metadata.uid` 참. decisions 156, approval_events 82, 최대 시도 2.

**알게 된 동작(결함 후보).**
- 백오프는 `5·2^시도`초(상한 1시간)라 장시간 중단 뒤에는 복구 후에도 수 분에서 최대 1시간까지 지연될 수 있다(C에서 2.5분). 무손실이지만 실시간성은 아니다.
- 송신 쪽 5초 타임아웃 < 수신 쪽 확인 대기(색인 지연)이면 같은 UID를 여러 번 보낸다. 받는 쪽이 `Idempotency-Key`로 합쳐야 한다(Vector `_id` 방식이 이를 충족).
- 워커는 한 번에 1건·건마다 새 TLS 연결이다. 수신 앞단 배치 지연 1초가 처리량을 건당 1초로 묶었다. 지속 부하(초당 수십 건)에서의 처리량은 미시험.
- `uid`는 `approval_events`·`ops_alerts`에서 `created_at`의 해시이므로 같은 트랜잭션에서 만들어진 행 간 해시가 같다(id가 달라 UID는 구별됨).

**행 조작 고지.** D·E·F에서 `siem_outbox`의 `delivered_at/attempts/last_error`를 되돌려 재전송을 일으켰다(각 30·90·57행, 합계 177행 되돌림). `siem_outbox`는 전달 큐이며 감사 원장(`decisions`·`approval_events`·`ops_alerts`)이 아니다. 원장 테이블에는 쓰지 않았다. 일회용 DB 시험은 별개 컨테이너로 시험 직후 삭제.

## 5. LiteLLM 구성과 LLM 경로 결과 (`full_stack_lab/llm/standalone/`)

구성: 프로젝트 `mint-llm`, PostgreSQL(내부 망)·Ollama(내부 망, 게시 없음)·LiteLLM(`127.0.0.1:4010`만 게시, 하네스 컨테이너는 같은 `edge` 망). 설정은 제품 랩 `llm/litellm.yaml`과 같은 모양(`bob-assistant` 한 이름). 로컬 모델은 비용이 0이라 예산이 안 걸리므로 시험용 단가(입력 1e-5, 출력 2e-5/토큰)를 `model_info`에 두었다. 두 번째 모델 `bob-reserved`는 허용목록 시험용. 마스터 키·salt·DB 비밀번호는 `secrets/`(0700)에 난수로 생성. `require_key_mcp_access_defined: true`.

| 시험 | 결과 |
| --- | --- |
| 직접 API(`/v1/chat/completions`) 정상 | 200, 5.5초(첫 호출, 모델 적재), 이후 0.2~0.5초 |
| 모델 허용목록 | 키가 허용하지 않은 `bob-reserved` → 403 `key_model_access_denied` |
| 잘못된 키 | 401 |
| 분당 한도(rpm 2) | 3번째부터 429 |
| 키 예산 | max_budget 0.002 키가 7회 성공(지출 0.0018) 후 8번째 422 `Budget has been exceeded`(현재 0.00212). 지출 갱신은 일괄 기록이라 연속 호출은 몇 건 더 통과할 수 있다(예산 0.004 키는 5회 호출 뒤에도 지출 0.0012로 보임) |
| 지출·로그 | `/spend/logs`에 사용자별 행(`user, model, spend, total_tokens, call_type, status`). 실패 호출(429·예산)도 `failure` 행. `/key/info`에 키별 누적 지출 |
| `/v1/messages`(Claude Code 와이어)·`/v1/responses`(Codex 와이어) | 모두 200, 변환되어 Ollama에서 응답 |
| **Claude Code 2.1.288 컨테이너** | `ANTHROPIC_BASE_URL=http://litellm:4000`+가상 키 → 응답, `anthropic_messages` 지출 행 기록. 경고: 모델 카탈로그 미등록, 자동 모드 분류기 요금 안내(LiteLLM이 그 갱신과 비호환) |
| **Codex 0.160.0 컨테이너** | `model_provider`(wire_api=responses)로 응답 `pong`, `aresponses` 지출 행(7461토큰) |
| 정책이 하네스에도 적용됨 | 예산 초과 키: Codex·Claude Code 모두 422 오류 메시지를 그대로 보고. 허용 밖 모델: Claude Code `403 not available for this API key` |

한계: 모델은 0.6B 로컬이라 도구 선택·품질 시험이 아니다. LiteLLM 로그는 컨테이너 표준 출력과 DB(`/spend/logs`)이며 프롬프트 본문 저장은 켜지 않았다. LiteLLM→SIEM 연동은 하지 않았다(미실행).

## 6. PJ1 관리형 하네스와 LiteLLM — 맞지 않는 이유 (읽기 전용 증거)

PJ1 `ssh pj1@100.110.81.60` 읽기 전용 조회(설정 파일·버전만, 자격 파일 미접촉):
- `/etc/claude-code/managed-settings.json`의 `env`는 `HTTPS_PROXY`/`HTTP_PROXY=http://100.83.175.111:3128`(모델 프록시)과 `NO_PROXY=100.83.175.111`뿐이다. `ANTHROPIC_BASE_URL`·`apiKeyHelper`가 없고 모델 인증은 직원의 구독 로그인이다. 허용 MCP는 게이트웨이 3개 URL만(`allowManagedMcpServersOnly`).
- 모델 프록시 허용 도메인(`full_stack_lab/model-proxy/model-domains.txt`)은 `openai.com`·`chatgpt.com`·`anthropic.com`·`claude.ai`·`claude.com`뿐이고 TLS 터널은 443만이다(FIELD.md D-67). 엔드포인트 방화벽은 관리 계정의 바깥 통신을 게이트웨이 포트와 모델 프록시 포트로만 묶는다. LiteLLM 포트(4010 등)와 호스트는 허용 목록에 없다.
- 구독 로그인 토큰은 제공자 엔드포인트용이며 LiteLLM 가상 키가 아니다. LiteLLM을 쓰려면 하네스를 API 키/기본 URL 방식으로 바꿔야 하고, 그러면 구독 로그인·관리형 설정·방화벽 허용 목록을 모두 바꿔야 한다. 이는 "PJ1 관리형 설정을 바꾸지 않는다" 조건에 걸리므로 시도하지 않았다.
- 참고: 랩의 컨테이너 직원 PC(`full_stack_lab/workstation/managed/`)는 이미 `ANTHROPIC_BASE_URL=http://llm-gateway:4000`과 Codex `model_providers.bob`(LiteLLM)로 구성돼 있다. 즉 LiteLLM 경로는 랩 워크스테이션용 설계이고 현장 `compose.field.yaml`에는 없다(`llm-gateway`가 정의돼 있지 않다). 현장 PJ1 구독 경로와는 별개다.
- 부수 관찰: PJ1 Codex는 ChatGPT 구독 사용량 한도에 걸려(`usage limit`) 이번 시험의 PJ1 Codex 결정 생성은 실패했다. Claude Code만 사용.

대체 증명: 같은 판본의 Claude Code·Codex를 격리 컨테이너로 실행해 LiteLLM 가상 키로 호출(5절). 이것은 PJ1 관리형 경로 증거가 아니다.

## 7. LiteLLM의 MCP 경로 (LLM 경로와 별개로 확인)

- 제품 랩 구성(`mcp_servers` 없음): `GET /v1/mcp/server` → `[]`, `/mcp` `tools/list` → 빈 목록, 키 도구 조회 → "The key is not allowed to access any MCP servers". 즉 LLM 프록시로만 동작한다.
- 확인용 별도 덮어쓰기(`compose.mcp.yaml`+`litellm-mcp.yaml`): 공개 Microsoft Learn MCP(`https://learn.microsoft.com/api/mcp`, 인증 없음, 읽기 전용) 하나를 `mcp_servers`에 등록. 공식 MCP SDK 클라이언트(mcp 2.2.0)로 `/mcp`에 접속: ① MCP 권한(`object_permission.mcp_servers`)을 가진 가상 키 → 도구 3개 목록, `microsoft_docs_search` 실제 호출 성공(Azure Functions 문서 결과). ② MCP 권한 없는 키 → 오류(거절). ③ 마스터 키는 목록 가능. 지출 로그에 `list_mcp_tools`·`call_mcp_tool` 행이 남는다.
- **우리 Gateway와의 관계.** 이 호출 전후 제품 `decisions`에서 `microsoft*` 도구 행은 0건 그대로였다. LiteLLM MCP 경로는 MINT 판정·원장을 거치지 않는다(우회 경로). 이를 막는 것은 엔드포인트 방화벽(관리 계정이 LiteLLM 호스트로 못 나감)과 하네스의 허용 MCP 제한이다. LiteLLM 안에서 우리 Gateway를 upstream으로 등록하는 것은 시도하지 않았다: Gateway는 직원 개별 토큰(transport)으로 신원을 정하므로 LiteLLM에 공유 토큰을 쥐여야 하고, 그것은 신원·직원 토큰 전달 금지 불변식과 충돌한다. 토큰 없이 LiteLLM 컨테이너에서 Gateway를 부르면 401(`로그인이 필요합니다`)이다. 이 경로의 재현·수용 조건은 별도 설계 사안이다.
- 확인 후 LiteLLM은 MCP 설정 없는 LLM 전용 구성으로 되돌려 실행 중이다(MCP 덮어쓰기 파일은 필요할 때만 `-f compose.mcp.yaml`로 적용).

## 8. 제품 비방해 확인

- 시험 중 내가 만든 변경: 제품 컨테이너 중 `siem-worker` 하나(생성·kill·재시작·정지·재생성)와 `.env` 키 3개, `siem-secrets/` 파일 2개, `siem_outbox` 재전송 조작(4절). 활성화 전후 제품 컨테이너 13개의 StartedAt·RestartCount 비교는 동일(`diff` 출력 없음). 조정자의 재배포 이후에는 해당 시각이 조정자 작업으로 바뀜.
- 기기 시험 파일: `~/mint-siem-t1/`, `~/mint-llm-t1/`, `/tmp/t1_*`. 일회용 `t1-pg` 컨테이너·`t1-pgnet`은 삭제 완료. 옛 시험 스택 `mcpgw-interop-20261013`은 건드리지 않음.
- 새 MCP 서버를 만들거나 우리 Gateway에 등록·승인하지 않았다. LiteLLM 시험 인스턴스에만 공개 Microsoft Learn MCP를 등록했다.
- 비밀: 토큰·비밀번호·가상 키를 보고서에 쓰지 않았다. 다만 Vector 디버그 중 도구 출력에 시험 토큰 1개가 한 번 노출돼 즉시 새 토큰으로 교체(재생성 후 Vector 재시작, 제품 `siem-secrets/token` 교체)했다. 현재 사용 중인 토큰은 출력된 적이 없다.

## 9. 런북

**상태 확인**
- SIEM: 기기 `cd ~/mint-siem-t1 && bash verify.sh`(대조), `docker ps --filter name=mint-siem`. 화면 `http://100.83.175.111:5601`(관리자 `admin`, 비밀번호는 `secrets/vector/opensearch_password`를 운영자가 읽음. 로그인 입력은 사람이 한다).
- 워커: `cd ~/mcp-gateway/full_stack_lab && ./console.sh field siem status`(반영 뒤). 반영 전에는 `docker logs mcpgw-55e075465e-siem-worker-1`과 `SELECT source,count(*),count(delivered_at) FROM siem_outbox GROUP BY 1`.

**끄기**
- 워커만: `./console.sh field siem down`(또는 `docker compose -f compose.yaml -f compose.field.yaml stop siem-worker`). 대기열은 DB에 남고 다시 켜면 이어서 전달한다. 영구 해제는 `.env`의 `SIEM_*` 3줄 삭제(백업 `/tmp/t1_env_backup_*`).
- SIEM: `cd ~/mint-siem-t1 && docker compose down`(데이터 유지; 볼륨 삭제는 `-v`). 끄면 워커는 재시도만 쌓는다(백오프 상한 1시간).
- LiteLLM: `cd ~/mint-llm-t1 && docker compose down`(DB·모델 볼륨 유지). MCP 확인: `docker compose -f compose.yaml -f compose.mcp.yaml up -d litellm`, 끝나면 `docker compose up -d litellm`.

**다시 올리기**
- SIEM: `cd ~/mint-siem-t1 && SIEM_BIND=100.83.175.111 ./setup.sh /home/user/mcp-gateway/full_stack_lab/siem-secrets` (비밀 보존, 이미지 digest 해석, 템플릿·인덱스 패턴 재적용).
- 워커: 위 3절 순서 또는 반영 뒤 `./console.sh field siem up`.
- LiteLLM: `cd ~/mint-llm-t1 && ./setup.sh`(모델을 한 번 내려받음, 일회용 컨테이너만 인터넷 접속). 하네스 이미지: `docker build -t mint-llm-harness:t1 harness/`. 시험 키는 `/key/generate`로 새로 만든다(이번 시험 키 별칭 `t1-*`는 LiteLLM DB에 남아 있고 삭제 가능).

**비밀 회전**
- 토큰: `secrets/vector/siem_token`을 새 값으로(개행 없이) 쓰고 `docker restart mint-siem-ingest-1`, 제품 `siem-secrets/token` 교체(UID 10001, 0600). 워커는 매 전송마다 파일을 읽으므로 재시작 불필요.

## 10. 실패·미완료·한계

- **Vector→OpenSearch 인증서 검증 끔**(`verify_certificate: false`). OpenSearch 보안 플러그인의 기본 시연 인증서·시연 설정을 그대로 쓰고, 내부 전용 네트워크라는 점에만 기댄다. Dashboards는 `admin`으로 접속하고 평문 HTTP(Tailscale 구간 암호화에 의존)다. 운영용은 자체 인증서·전용 서비스 계정·Dashboards TLS가 필요하다.
- 색인 수명주기(ISM)·보존·샤드 설정, 경보 규칙(Security Analytics/Detector)은 구성하지 않았다. 문서 검색·집계만 확인했다.
- ops_alerts 현장 경로(실제 `MCP-REGISTRY-001` 등 결정 → 경보 → SIEM)는 현장 DB에서 **미실행**(자연 발생 0건, 가짜 incident 등 원장 오염 우려로 만들지 않음). 일회용 DB 증거와 구분한다.
- 지속 부하·대용량 백로그 처리량, SIEM 장기 중단(1시간 백오프 상한 도달), TLS 인증서 만료·회전, 토큰 회전 중 실패는 미시험.
- 이 시험의 SIEM 판본 선택은 계약 대조 기준이며 Wazuh·Graylog 실제 설치 비교는 하지 않았다.
- LiteLLM은 로컬 0.6B 모델이라 하네스 업무 품질·도구 호출 시험이 아니다. LiteLLM 공식 Admin UI·SSO·비밀 저장소·감사 로그 내보내기는 미구성. 이미지 서명 검증 미실행.
- 코드 변경은 `console.sh`와 문서뿐이고 기기 `~/mcp-gateway`에는 반영하지 않았다. 반영하면 `field siem` 명령을 쓸 수 있다.
- Codex(PJ1)는 구독 한도로 이번 시험에서 판정을 만들지 못했다.

## 11. 검증 표

| 확인 종류 | 명령·환경 | 결과 |
| --- | --- | --- |
| 정적 검사 | `bash -n console.sh siem/setup.sh`, `pyflakes siem/ops_alert_probe.py` | 통과 |
| 프로토콜(TLS·Bearer·Idempotency) | 기기에서 curl(401/401/200/405) | 통과 |
| 실제 DB 큐·트리거 | 현장 DB, 워커 활성화 | 백로그 147 + 이후 신규 포함 238/238 |
| 장애·복구 | 수신 중단, 워커 kill/재시작, OpenSearch 중단, 제품 재배포 | 손실 0, 중복 0(문서 기준) |
| 실제 모델·하네스 | PJ1 Claude Code→게이트웨이 결정→SIEM / 컨테이너 Claude Code·Codex→LiteLLM→Ollama | 통과 |
| upstream 효과 | MCP 실제 호출(Microsoft Learn via LiteLLM) | 도구 결과 수신, 제품 원장 0건 |
| 배포 | 기기 `siem-worker` 계속 실행, SIEM·LiteLLM 계속 실행 | 확인 |

## 사용자에게 필요한 입력

- `console.sh`의 `field siem` 변경을 기기에 반영할지(조정자 배포 시 함께). 승인 후 `field siem up`으로 워커를 코드 판본과 맞춰 재생성.
- 운영 SIEM에 쓸 인증서·서비스 계정 정책(10절 첫 항목).
