# 종료·폐기 판정 모델 — 논문을 코드로

> 근거 논문: CISC-W'26 「원격 MCP 서비스 종료 시 권한 회수의 구조적 한계 및 종료 판정 기준 제안」.
> 코드 정본: `full_stack_lab/gateway/app/decommission.py`(판정), `experiments.py`(E1~E3),
> `main.py`의 `/api/termination/*`, Console `#/termination`. 끝에서 끝까지의 검증은
> `full_stack_lab/tests/termination_flow.py`(21개 확인).

## 1. 핵심 주장 (왜 "껐다"가 "끝났다"가 아닌가)

- MCP 서비스를 끊는 것은 스위치가 아니라 **권한 회수**다. 회수 대상은 조직의 강제 경로(Gateway),
  이용 주체별 접근, 단말에 남은 설정, 그리고 **원격 서버가 하위 시스템에 대해 보유한 자격**이다.
- 마지막 것은 MCP 인가 명세상 조직이 회수할 수 없고, 제공자가 고지하지 않으면 **존재조차 열거할 수 없다**.
- RFC 7009 폐기 응답(200)은 무효 토큰에도 똑같이 나오므로 **처리 사실만** 증명한다.
- 그래서 종료는 "했다"가 아니라 **증거로 판정**해야 하고, 판정할 수 없는 경우를 등급으로 드러내야 한다.

## 2. 용어와 데이터

| 논문 | 코드 | 테이블 |
| --- | --- | --- |
| 이용 관계 | `usage_relationships` (id `UR-…`, 서버·조직·목적·제공자·허용 자원) | `usage_relationships` |
| 종료 케이스 | 관계 하나의 종료 절차 | `termination_cases` |
| 회수 대상 | 모집단의 원소 | `revocation_targets` (kind·holder·discovered_by·status·subject_ref·criteria·grade) |
| 증거 | 대상·시점을 특정하는 기록 | `termination_evidence` (kind·subject·source·detail·observed_at·target_id) |

회수 대상 종류(`kind`): `gateway-route`(조직 강제 경로), `gateway-access`(이용 주체별 접근),
`endpoint-config`(단말 MCP 설정), `server-held-credential`(서버 보유 하위 자격), 그 밖에
`client-token`, `refresh-token`, `session`, `api-key`, `webhook`, `dynamic-registration`, `cached-artifact`.

보유 주체(`holder`): `org` / `provider` / `endpoint`. 발견 경로(`discovered_by`): `gateway-ledger`,
`endpoint-agent`, `provider-disclosure`, `operator-manual`, `liveness-probe`.

### 증거 종류 — 무엇을 증명하고 무엇을 못 하나 (`EVIDENCE_KINDS`)

| kind | 상태 증거(C4) | 증명 | 증명 못 함 |
| --- | --- | --- | --- |
| gateway-denial | ✓ | 강제 경로가 이 주체의 호출을 실행 전에 막았다 | 강제 경로 밖의 다른 경로 |
| introspection | ✓ | 인가 서버가 판단하는 토큰 활성 상태 | 자원 서버가 그 상태를 반영하는지 |
| credential-check | ✓ | 하위 시스템에 그 자격이 (없다/있다) | 이미 복제·발급된 다른 자격 |
| provider-attestation | ✓ | 제공자가 대상·시점을 특정해 진술 | 진술의 진위 |
| endpoint-inventory | ✓ | 보고 시점에 단말 설정에서 사라졌다(또는 남았다) | 보고 이후 재설치 |
| revocation-response | ✗ | 폐기 요청이 처리되었다 | 대상이 그때 유효했는지(200은 무효 토큰에도) |
| liveness-probe | ✗ | 주소가 응답하는지 | 조직의 자격이 유효한지 |
| session-termination | ✗ | 세션 종료 요청에 대한 응답 | 세션·토큰의 소멸 |
| operator-statement | ✗ | 담당자가 조치했다고 진술 | 대상의 상태 |

대상 종류별로 C4에 쓰이는 상태 증거(`STATE_EVIDENCE_FOR`): gateway-route/access → gateway-denial,
server-held-credential → credential-check·provider-attestation, endpoint-config → endpoint-inventory,
토큰류 → introspection·credential-check·provider-attestation.

## 3. 절차 (Console의 7단계 = API)

| 단계 | Console | API | 비고 |
| --- | --- | --- | --- |
| 1 이용 관계 확정 | 관계 카드 | `GET /api/termination/relationships` | 준비도(최선 등급) 포함 |
| 2 강제 경로 차단 | "종료 시작" | `POST /api/termination/cases {relationship_id, reason}` | 즉시 `MCP-DECOMM-001`, `cutover_at` 기록 |
| 3 모집단 열거(C1) | 회수 대상 표 | (케이스 개시 시 자동) + `POST …/cases/{id}/targets` | 제공자 몫은 고지 없으면 UNVERIFIABLE 자리표시 |
| 4 회수 조치(C2) | "조직 권한으로 폐기", "상태 기록" | `POST …/targets/{id}/revoke-credential`, `PUT …/targets/{id}` | |
| 5 상태 증거(C4) | "증거 수집", "증거 등록" | `POST …/cases/{id}/collect {kinds}`, `POST …/cases/{id}/evidence` | kinds: gateway·endpoint·credentials·liveness·session |
| 6 판정 | "판정" | `POST …/cases/{id}/assess` | 대상별 C1~C4·등급, 케이스 등급 |
| 7 종결 | "종결" | `POST …/cases/{id}/close {note, risk_acceptance}` | T3는 위험 수용 근거 필수 |

부가: `GET …/report`(판정서 JSON), `GET …/disclosure-request`(제공자 고지 요청서 Markdown),
`POST …/reopen {reason}`(종결 후 새 대상 발견), `GET /api/termination/drill/{server}`(끊지 않고
최선 등급 계산), `POST /api/lab/restore/{server}`(실습용 복원).

### 모집단 자동 열거 (`seed_targets`)
1. `gateway-route` 1건 — 조직의 강제 경로.
2. `gateway-access` — cutover 이전에 이 서버를 부른 모든 주체(판정 원장 기준, **프로브 제외** D-12).
3. `endpoint-config` — 단말 인벤토리에서 이 서버를 가리키는 설정(섀도·잔존 포함).
4. 제공자 배치면: 고지된 `server_held_credentials`마다 1건, 고지가 없으면 **UNVERIFIABLE** 1건
   ("존재 여부조차 열거할 수 없음").

### 증거 수집이 하는 일 (`collect`)
- `gateway`: 대상 주체의 이름으로 실제 호출을 Gateway에 보내 `MCP-DECOMM-001`로 막히는지 본다
  (`client.agent = termination-probe`). 막히면 대상 REVOKED, 회수 시각은 **cutover**로 고정.
- `endpoint`: 인벤토리에서 지문이 사라졌는지. 사라졌으면 REVOKED, 회수 시각은 관찰 시각.
- `credentials`: Gitea 관리 API(Sudo)로 토큰 존재 확인. 없으면 REVOKED. **있으면 그 사실도 상태 증거**.
- `liveness`/`session`: 처리 증거(C4 불충족). E2 측정을 증거로 남긴다.

## 4. 판정 규칙 (`_judge_target`)

각 대상에 대해:

- **C1 모집단**: 대상이 `UNVERIFIABLE`이면 미충족("대상의 존재·범위를 열거할 수 없다").
- **C4 증거 접근**: 그 대상 종류의 **상태 증거**가 회수 시각 이후에 하나라도 있으면 충족.
  회수됨이든 아직 있음이든 상태를 특정하면 된다 → 이것이 T2를 가능하게 한다. 처리 증거만 있으면
  "(○○은 요청 처리만 증명)"을 붙여 미충족.
- **C2 수행 권한**: 상태가 REVOKED/EXPIRED가 아니면 미충족. 제공자 보유 자격은 추가로
  **제공자 증명** 또는 **조직의 직접 확인(credential-check, 조직이 확인 수단을 가진 경우)**이 회수를
  보여야 충족.
- **C3 연속성**: Gateway 경로·접근 대상은 cutover 이후 **실행된 호출**이나 **실행 여부 미확인 호출**이
  있으면 미충족. 상태 비저장 토큰은 회수 시각부터 만료까지의 공백(초)을 기록(E1). 회수됐지만
  무효를 확인한 증거가 없으면 "전파 완료 미확인". 회수 전이면 판단 불가로 미충족.

등급: **C1 또는 C4 미충족 → T3**(잔존 범위 산정 불가), 아니면 **C2 또는 C3 미충족 → T2**(상한만
설정 가능), 모두 충족 → **T1**. 케이스 등급은 대상 중 **최저**. 대상이 0개이거나 cutover 이후
실행 여부 미확인 호출이 있으면 케이스는 T3.

| 등급 | 이름 | 의미 |
| --- | --- | --- |
| T1 | 종료 | 모든 대상이 네 기준 충족. 종료를 진술할 수 있다 |
| T2 | 부분 종료 | 모집단·증거는 확정, 회수나 전파가 미완. 잔존 범위의 상한을 말할 수 있다 |
| T3 | 판단 불가 | 모집단을 열거 못 했거나 상태 증거가 없다. 잔존 범위를 산정할 수 없다 |

### 종료 준비도 드릴 (`drill`) — 들일 때 묻는 질문
- 제공자 배치인데 자격 고지 조항이 없으면 최선 **T3**("C1 성립 불가").
- 고지는 있으나 폐기 기록 제출도 조직 확인 수단도 없으면 최선 **T2**.
- 그 외 **T1**. 논문 5.2: 이 증거는 **종료 시점에 소급해 얻을 수 없으므로** 도입 심사(`#/intake`의
  종료 조건 체크)가 유일한 완화다.

### 종결 규칙
- ASSESSED 상태에서만 종결. 새 증거·대상이 들어오면 판정이 무효화되어(`_invalidate`) 다시 판정해야 한다.
- T3는 `risk_acceptance`(누가 무엇을 받아들이는지) 없이 종결 불가.
- 종결 시 서버 lifecycle RETIRED·status DISABLED, 관계 TERMINATED.

## 5. 실험 E1~E3 (`python -m app.experiments e1|e2|e3`, 5회 반복)

| 실험 | 측정 | 이 랩의 결과 | 판정 모델과의 연결 |
| --- | --- | --- | --- |
| E1 토큰 폐기 | RFC 7009 응답, 조사, 상태 비저장 자원 서버, Gateway, refresh | 폐기 200(재폐기·쓰레기 토큰도 200), 조사 inactive, 서명만 보는 자원 서버는 **만료까지 599초 수락**, Gateway 즉시 차단, **refresh로 새 토큰 발급 가능** | 200은 C4 불충족 사유, 만료까지의 공백은 C3 → T2 |
| E2 세션 종료 | 10종에 initialize → DELETE → 같은 세션 재호출 | 8종은 세션 자체를 발급하지 않음(stateless), email·playwright는 DELETE 200 후 404 | 세션 계층에는 조직이 원용할 종료 수단이 거의 없다 |
| E3 서버 보유 자격 | 상위 토큰 완전 폐기·조사 후 gitea PAT로 하위 접근 | 여전히 200, 제공자 쪽 폐기(204) 뒤 401 | 고지 없으면 C1 → T3, 조직이 하위 시스템 관리자면 C2·C4 확보 → T1 |

`tests/experiments_check.py`가 이 findings가 논문 주장과 같은지 확인한다(`./console.sh test`).

## 6. 실습 시나리오 (termination_flow.py가 자동으로 하는 것)

- **UR-GITEA-DEV**(고지 있음·조직이 Gitea 관리자): 개시 → 수집(PAT 아직 있음) → 판정 **T2** →
  "조직 권한으로 폐기"(DELETE 204 = 처리 증거, 재확인 = 상태 증거) → 판정 **T1** → 종결 → 복원.
- **UR-EMAIL-ASSIST**(고지 없음): 개시 → UNVERIFIABLE 대상 → 판정 **T3** → 위험 수용 없는 종결 거부 →
  고지 요청서 생성 → 위험 수용과 함께 종결 → 복원.

## 7. 구현 함정

- 증거가 회수 시각보다 **앞서** 기록되면 C4가 인정하지 않는다. `revoke_target(at=…)`로 회수 시각을
  cutover(게이트웨이 경로) 또는 관찰 시각(단말·하위 시스템)에 맞춘다.
- `oauth_issued_tokens.jti`는 text, 폐기 목록은 uuid → `_revoke_family`에서 `jti::uuid`.
- v1 CHECK 제약이 새 kind를 거부해 케이스가 반쯤 열린 적이 있다 → `v2_tables.sql`이 제약을 다시
  만들고, `open_case`는 대상 시드 실패 시 케이스·cutover를 되돌린다(원자적).
- 실습 복원은 폐기된 Gitea PAT를 되살리지 않는다 → `./console.sh restore-token gitea` (D-18).
