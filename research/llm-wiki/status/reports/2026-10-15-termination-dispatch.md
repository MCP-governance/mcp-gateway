# 2026-10-15 호출 예약 원자성·전송 의도·종료 (작업 C)

- 작업자: Claude Code(Sonnet 5.5) 서브에이전트. 메인 에이전트가 조율하고 병합한다.
- 코드 기준: 브랜치 `10/15-wbs-termination-dispatch`, 시작 `b0bfa2d`, 코드 커밋 `38a12c9`·`47feb0b`·`76008e3`·`afe9b5c`·`fc49e63`·`abbb291` 뒤 마지막 정리 커밋(보고서 포함). 푸시·병합·다른 워크트리 변경 없음.
- 시작 근거: WBS G03.04·G07.01·G07.02·G07.03·G07.04, 백로그 DEV-04·DEV-08·DEV-16·DEV-21·DEV-29, [종료 모델](../../../../docs/ai/TERMINATION_MODEL.md), 결정 D-78·D-79, 신규 D-96–D-99.
- 해결할 문제와 완료 조건: 동일 호출·승인 재사용·상한의 부수효과 수를 하위 시스템에서 센다. 보내기 전 전송 의도를 같은 DB에 적고 프로세스가 죽어도 미확인으로 남기며 자동 재시도하지 않는다. 폐기한 토큰·계열·장치가 보호 API와 MCP에서 거부된다. 종료 중 진행 호출은 cutover 뒤 새로 나가지 않고 따뜻한 연결이 닫힌다. 폐기한 자격을 보호 자원이 실제로 거부하는지 본다. 제거한 자격이 캐시·파일·증거로 돌아오지 않는다.

## 결과

| 항목 | 상태 | 구현·증거 |
| --- | --- | --- |
| G03.04 / DEV-04 예약 원자성 | 구현·격리 랩 실제 PostgreSQL·실제 Gitea MCP | 기존 예약은 경쟁에서 옳았다(동일 24개 동시 예약 중 중복 아님 1개, 동시 상한 4, 호출량 상한 정확). **결함 1건 재현·수정**: 기존 승인 id로 `execute_call`을 변형 인자로 직접 부르면 쓰기 호출이 실행됐다(PAC-13 다이제스트는 고위험 `x`에만, 외부 경로 `approve_request`는 안전). 전송 경계(`dispatch.record`)가 승인된 서버·도구·인자·주체와 보내는 호출을 대조하고 승인을 같은 트랜잭션에서 소비한다 |
| DEV-21 전송 의도 | 구현·격리 랩 | `dispatch_intents`(원장과 별개 표, `v2_tables.sql`), `app/dispatch.py`. 보내기 직전 한 문장으로 기록(예약·주체·서버 상태 확인 포함), 판정 기록 뒤 예약 해제와 같은 문장에서 `resolved`/`uncertain`. 사망한 프로세스의 `pending`은 예약이 사라지면 미확인. 같은 쓰기는 `P-RATE-003`. `GET /api/dispatch-intents`, `POST …/{request_id}/resolve`(admin_caller), Console 승인 대기의 "실행 확인" 탭, 지연 단계 "실행 기록" |
| G07.01 토큰·계열·장치 | 검증 중심(코드 변경 없음) | 실제 서명 토큰 22건: 계열 폐기 뒤 모든 액세스 토큰이 API·MCP에서 401, 재사용 탐지, 액세스 토큰 단독 폐기는 그 토큰만(E1 유지), 계정 중지 403, 발급·폐기 12회 경쟁 생존 0, 발급 실패 롤백, 장치 폐기 뒤 장치 토큰 403·모든 범위 인증 불가·heartbeat 불가·토큰 재발급 불가 |
| G07.02 세션·연결 종료 | 구현·격리 랩 | cutover를 DB가 정함(서버 행 `FOR UPDATE`+`clock_timestamp`, 전송은 같은 행 `FOR SHARE`). 240건 경쟁에서 기록 35·거부 205·cutover 뒤 기록 0. 실제 호출이 최종 검사 직후 cutover를 만나면 `MCP-DECOMM-001`, 전송·의도 없음, Gitea 효과 0. 풀 연결은 종료·계정 중지/삭제 때 닫히고 다른 프로세스는 `upstream_pool_events`를 읽어 닫는다. C3의 `unknown`에 원장에 못 남은 전송을 가산, `straddled`는 따로 표시 |
| G07.03 제공자 잔존 접근 | 구현·격리 랩 실제 Gitea 1.27.3 | 신규 증거 `resource-rejection`: 폐기 전 200, 폐기 뒤 401(`accepted_before_revocation=true`), 폐기로 적었지만 지우지 않은 토큰은 200 → C3 미충족·T2. 물을 수 없으면(설정 없음·읽을 수 없음·자원 불능) 증거를 만들지 않고 `provider_side=unverified`와 만료만. 값은 기록하지 않음 |
| G07.04 자격 제거 | 구현·격리 랩 | 자격 파일은 호출마다 재읽기(캐시 없음), 풀 클라이언트가 만든 때의 자격 헤더를 쥐던 문제를 수정(자격 변경·제거 시 같은 (엔드포인트, 주체)의 이전 클라이언트를 닫음). 증거·원장·판정서·고지 요청서·승인·예약·풀 이벤트에 토큰 값과 끝 8자리 없음. 무관한 파일 변경 없음. 폐기·종결 뒤 레지스트리 재동기화가 서버를 되살리지 않음 |

C1–C4/T1–T3 기록: 격리 랩 케이스(경로·호출자·제공자 보유 자격 2건)는 모든 대상 T1, 케이스 T1, 차단 후 실행 0·미확인 0·straddled 0. 폐기 후 자원이 수락하는 자격이 있으면 해당 대상 C3 미충족, 케이스 T2. 규칙 변경은 [TERMINATION_MODEL](../../../../docs/ai/TERMINATION_MODEL.md) §2·§4·§7과 `tests/termination_flow.py`(검사 3건 추가)에 같이 반영했다.

API 계약: `GET /api/dispatch-intents`, `POST /api/dispatch-intents/{request_id}/resolve {outcome, note}`(둘 다 `admin_caller`, [API.md](../../../../docs/API.md)). 열·표는 [DATA_MODEL](../../../../docs/ai/DATA_MODEL.md), 결정은 D-96–D-99.

## 검증

환경: Windows 11 호스트(Python 3.12 venv), 솔루션 기기의 **일회용 격리 랩**(PostgreSQL 18, OPA 1.20.2, Presidio, Gitea 1.27.3 rootless, Gitea 프로젝트의 `gitea-mcp-server:1.7.0` 이미지, 기기에 있는 gateway 이미지). 제품 컨테이너·`~/mcp-gateway`·운영 DB·운영 Gitea·PJ1은 건드리지 않았다. 랩은 `wbs-c-*`로만 만들고 끝에 `down`으로 지웠다(컨테이너·네트워크·`/tmp/wbs-c-*` 0, 시간 제한 타이머 종료 확인). 랩 구동에 쓴 `docker pull`은 사용자 docker 설정을 건드리지 않도록 임시 설정 폴더를 썼고 이미지 `gitea-mcp-server:1.7.0`(제품 스택이 고정한 것과 같은 태그)만 기기에 남았다.

| 확인 종류 | 명령·환경 | 결과 | 층 |
| --- | --- | --- | --- |
| 정적 검사 | `pyflakes gateway/app/*.py tests/*.py`, `node --check console.js`, `node --test tests/console-state.test.mjs`, `tests/open_endpoints.py`, `tests/console_copy_check.py` | 오류 0, 14건 통과, 무인증 1개 문서 일치·인증 필요 67개, 화면 문구 문제 0 | 로컬 |
| 예약·경계·cutover | `tests/termination_dispatch_lab.sh run dispatch_intent_pg_check.py` | 47건 통과, 실패 0 (동일 24 동시 예약 → 중복 아님 1, 서로 다른 12 → 상한 안 4, 해제·도착 경쟁 40회 → 둘 다 통과 0, 240건 전송 vs 종료 → 35 기록·205 거부) | 격리 랩(실제 PostgreSQL, 풀은 트래픽 없는 단위 수준) |
| 하위 시스템 효과 | `… run dispatch_effect_lab.py` | 45건 통과, 실패 0 (동일 호출 12개 → Gitea 이슈 1, 서로 다른 10개 → 4, 호출량 상한 5 → 5, 승인 6명 경쟁 → 1, 변형 요청 3종 → 0, 답 유실 → 효과 1·재시도 0, SIGKILL 2종 → 효과 1/0·원장 0·`pending`·45초 예약 만료 뒤에도 재전송 거부, 계정 중지 → 0) | 격리 랩(실제 Gitea MCP 서버·Gitea, 비밀 검사만 단위 대역) |
| 종료·잔존 접근·자격 제거 | `… reset; run termination_lab.py` | 38건 통과, 실패 0 | 격리 랩(실제 Gitea·MCP 서버) |
| 토큰·계열·장치 | `… run token_revocation_pg_check.py` | 22건 통과, 실패 0 | 격리 랩(실제 서명 토큰·PostgreSQL) |
| 기존 검사 회귀 | `… run oauth_rotation_pg_check.py`, `… run credential_binding_check.py` | 3건 통과, 통과 (Windows 호스트의 `credential_binding_check`·`intake_validation_test` 실패는 b0bfa2d에서도 같다 — POSIX 권한 가정) | 격리 랩 / 호스트 |
| 지연 | 위 `dispatch_effect_lab.py`의 `decisions.timings` | 실행 기록 단계 p50 3.8–4.4ms·p95 7.1–7.3ms, 총 p50 169–231ms (n=14–19, 동시 호출 포함) | 격리 랩 |
| 실제 하네스(PJ1) | 실행하지 않음 | 미확인 | — |
| 솔루션 기기 배포 | 하지 않음 | 미확인 | — |

랩 재현: WSL에서 `tests/termination_dispatch_lab.sh up`, `run <검사>`, 종료 검사 전 `reset`(제공자 토큰을 폐기하므로), `down`. 사용법은 [TESTING.md](../../../../docs/ai/TESTING.md).

단위 수준(대역)으로 센 것: Gitleaks 라이브러리가 이미지에 없어 비밀 검사를 "찾지 못함"으로 바꿨다. 전송 직전·전송 직후를 고정하려는 지점 후크(한 시나리오의 호출을 예약 뒤에 붙잡기, 전송 순간에 종료·계정 중지 실행, 답 가로채기)는 게이트웨이와 MCP 서버를 대체하지 않는다. 풀 닫기 단위 검사는 연결 없이 클라이언트 객체만 쓴다. 판정 함수 `_judge_target`의 세 경우(거부·수락·미확인)는 합성 증거로 부른다.

## 실패·미완료·한계

- 실제 하네스(PJ1)와 솔루션 기기 배포 검증은 하지 않았다. 병합 뒤 메인 에이전트의 실제 하네스 검증이 필요하다. 라이브 스택용 `termination_flow.py`에 넣은 3건은 실행하지 못했다(격리 랩 밖).
- 세션: Gitea MCP 서버는 세션을 발급하지 않는 상태 비저장이다. 호출별 세션 모델이라 "오래된 세션 재접근"은 구조상 없지만, 서버 쪽에 지속 세션·자원이 있는 서버(이메일·Playwright)로는 확인하지 못했다(G07.02 일부 미확인, DEV-29 열림).
- 제공자 측 폐기: 조직이 토큰 값의 사본을 갖는 자격에만 자원 서버 거부를 직접 확인할 수 있다. 제품 스택에는 사본이 없어 기본은 `unverified`이다(등급은 바뀌지 않음). 다른 자원 서버·복제된 자격은 증명하지 못한다.
- 전송 의도는 보내기 직전 DB 왕복 한 번(위 지연)을 더한다. 동기 커밋을 끄지 않았다. 읽기 도구의 미확인은 차단하지 않는다. 앞의 호출이 끝난 뒤 다시 보낸 같은 호출은 별개 요청이다.
- 풀: 쓰는 중인 연결은 끊지 않고 호출이 끝날 때 닫는다. 다른 프로세스는 다음 풀 사용 시(2초 간격)에 닫거나 유휴 60초에 소켓이 닫힌다. cutover 전에 보내 뒤에 답한 호출은 C3에서 여전히 실행된 호출로 센다.
- 액세스 토큰 단독 폐기는 계열을 폐기하지 않는다(RFC 7009 MAY, 논문 E1 재현). 계열 폐기는 리프레시 폐기·재사용 탐지·계정 중지·장치 폐기로만 일어난다.
- 직원 PC의 작업 백업·캐시·내보낸 파일은 게이트웨이 밖이라 검증하지 않았다(엔드포인트 에이전트 영역, G07.04 일부 미확인).
- 다른 작업(B)과 겹칠 수 있는 곳: `pac.py` 미확정 변경 조회 한 곳(`dispatch_intents` 제외 조건), `agent_service.py`의 계정 상태 라우트 두 곳과 프록시 접두사, `console.js` 승인 대기 라우트, `console-state.mjs` 지연 단계 한 줄.

## 다음 작업

- 병합 뒤 솔루션 기기에 배포하고 PJ1에서: 같은 쓰기의 동시 호출, 종료 개시 중 호출, 계정 중지 후 연결(DEV-04·DEV-21·G07.02). 성공 조건은 Gitea 이슈 수 등 하위 시스템 효과와 판정 원장의 일치.
- DEV-29: 지속 세션을 가진 서버(이메일·Playwright)에서 세션 바인딩·종료 시 닫기 결정.
- 제품 스택의 Gitea 토큰 사본 위치를 정하면(`GITEA_PROBE_TOKEN_FILE`) `provider_side`가 `unverified`에서 `rejected`로 바뀐다.

## 사용자에게 필요한 입력

없음. 제품 스택에서 제공자 토큰 사본을 게이트웨이에 보여 줄지(비밀 저장소 위치와 접근 범위)는 소유자 결정이 필요하다.
