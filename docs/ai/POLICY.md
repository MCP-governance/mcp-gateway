# 정책 (OPA/Rego)

> 파일: `full_stack_lab/opa/`
> - `policy.rego` — 규칙 (`package mcp.authz`, 결과는 `data.mcp.authz.decision`)
> - `policy_test.rego` — 단위 시험(99건)
> - `policy_ledger.json` — 정책 관리대장(정책마다 이름·목적·우선순위·결과·상태·버전·위험/통제 id·예외 허용 여부·의무)
> - `exceptions.json` — 예외 관리대장
> - `data.json` — 운영 제한과 자주 바뀌는 값(제한 실행 값, egress 허용 호스트, 부서 범위 스위치)
>
> Gateway는 `OPA_URL`(`http://opa:8181/v1/data/mcp/authz/decision`)에 입력을 보내고, 실패하면
> `P-CONTROL-FAIL-CLOSED`로 차단한다. OPA는 `--watch` 없이 뜨므로 Rego를 바꾸면 `docker compose restart opa`.

## 1. 판정 구조

1. **후보 전부를 모은다**: 성립한 모든 정책이 `candidate[policy_id] := {decision, reason, restrictions, conditions}`를 만든다.
2. **관리대장 priority로 하나를 고른다**(`selected_id`, 숫자가 작을수록 우선). 진 후보는 `conflicts`에 남는다.
   관리대장에 없는 정책이 후보에 끼면 `P-CONTROL-LEDGER-001`로 차단.
3. **예외**: 고른 정책이 `exceptionable`이고 유효한 예외(적용 상태·기한·범위·보완통제·자가승인 금지·
   완화만 허용)가 범위에 맞으면 effect로 바꾼다. 승인형 예외는 `approval.granted`면 Allow(D-17).
4. 후보가 하나도 없으면 `P-CONTROL-DEFAULT-001` 차단.
5. 결과에 정책 버전·위험/통제 id·의무(obligations)·예외 정보·충돌이 붙는다(`enrich`).

판정 5종: **Allow**(실행) · **Alert**(실행 + 보안 경보) · **Restrict**(제한 값 적용 후 실행) ·
**Approval**(관리자 승인 후 1회 실행) · **Block**(실행 안 함).

## 2. 주요 정책 (우선순위 순, 전체는 Console `#/policy` 또는 `policy_ledger.json`)

| priority | id | 결과 | 조건 |
| --- | --- | --- | --- |
| 1 | P-CONTROL-LEDGER-001 | 차단 | 관리대장에 없는 정책이 후보에 있음 |
| 5 | P-CONTROL-INPUT-001 | 차단 | 필수 입력 누락 |
| 10 | MCP-REGISTRY-001 | 차단 | 미등록 서버 |
| 15 | MCP-DECOMM-001 | 차단 | 이용 관계가 종료 절차 중/폐기 |
| 20 | MCP-REGISTRY-002 | 차단 | 비활성(미승인) 도구 |
| 30 | MCP-SUPPLY-001 | 차단 | 공급망 위험(치명 취약점·미승인 공급자) |
| 40 | MCP-EGRESS-001 | 차단 | 허용 목록 밖 upstream |
| 42 | MCP-EGRESS-002 | 차단 | 인자 목적지 SSRF(회사 시스템 관리 API·메타데이터 주소 등) |
| 45 | MCP-DATA-EGRESS-001 | 차단 | 외부 목적지로 중요 등급 자료나 Presidio가 찾은 개인정보를 보냄(역할 무관, 예외 불가) |
| 46 | P-CHAIN-001 | 차단 | 같은 주체가 최근 10분 안에 중요정보를 읽고 외부로 보냄(`request.sequence_flags`, 관찰 모드에서도 집행) |
| 50 | MCP-CATALOG-001 | 차단 | 승인 계약(설명·스키마·버전 해시) 불일치 |
| 55 | P-APPROVAL-EXPIRY-001 | 차단 | 승인 유효기간 만료 자산 |
| 60 | P-CLASSIFICATION-001 | 차단 | 분류 근거 없는 데이터 |
| 70 | P-RATE-001 | 차단 | 호출량 상한 |
| 71 | P-RATE-002 | 차단 | 동시 실행 상한(이 주체가 지금 돌리는 호출 수) |
| 72 | P-RATE-003 | 차단 | 같은 인자의 같은 호출이 아직 실행 중(중복·재생) |
| 78 | P-DLP-001 | 차단 | 민감정보(주민번호·카드 등) 외부 전송 |
| 79~89 | INPUT_CONTRACT, POLICY_BUNDLE, PAC-01~15 | 차단·승인 | 사실 계약·정책 버전·승인 실행 범위 검사 |
| 90 | P-X-APPROVAL-001 | 승인 | 중요정보의 고위험 실행(x) — 내부 목적지. 외부 반출은 MCP-DATA-EGRESS-001이 먼저 막는다 |
| 95 | P-UNTRUSTED-CONTENT-001 | 승인 | 비신뢰 콘텐츠 기반 고위험 실행 |
| 100 | P-VOLUME-001 | 승인 | 중요정보 누적 접근 |
| 110 | P-DEPT-001 | 승인 | 소관 부서 외 중요정보(`data.department_scope.enabled`, 기본 꺼짐) |
| 120 | P-X-RESTRICT-001 | 제한 | 외부 전송을 제한 값으로(`restrictable ∩ data.restrictions`) |
| 125 | P-X-ALERT-001 | 경고 | 제한할 수 없는 외부 전송 |
| 128~135 | P-UNTRUSTED-CONTENT-002, P-ANOMALY-001, MCP-SHADOW-00x | 경고 | 비신뢰 콘텐츠 열람, 반복 차단, 섀도 MCP 보유자 |
| 130 | P-IMPORTANT-ALERT-001 | 경고 | 중요정보 열람 |
| 136 | P-SCOPE-001 | 경고 | 이용 관계가 허용한 자원 밖(`relationship.in_scope=false`, D-39). 관계가 없는 서버·값이 없는 입력은 판단하지 않는다 |
| 140 | P-AUTHZ-ALLOW-001 | 허용 | PAC 실행 범위 충족 |

Gateway 쪽(OPA 밖)에서 나오는 판정: `P-INPUT-SCHEMA-001`(승인 스키마 위반), `P-DATA-INSPECTION-001`
(Presidio 입력 검사 불능, priority 2010), `MCP-OUTPUT-001`(실행됐지만 결과 보류 — 크기·주입 표지·출력 개인정보
검사 불능), `MCP-UPSTREAM-001`(상위 오류), `P-CONTROL-FAIL-CLOSED`(OPA 불능), `P-MONITOR-001`(관찰 모드).

OPA 입력의 개인정보 관련 필드: `request.pii_types`(Presidio 엔터티 유형만 — 값은 넣지 않는다),
`request.sequence_flags`, `request.dlp`(분류기의 정규식 DLP 라벨, `P-DLP-001`), `destinations[].external`.

호출 상한 관련 필드(`context`)는 **판정 전에 Gateway가 원자적으로 예약한 뒤의 값**이다.
`recent_calls`는 끝난 호출 + 지금 도는 호출(이번 것 포함), `active_calls`는 이 주체가 지금 돌리는 수,
`duplicate_in_flight`는 같은 인자의 같은 호출이 아직 안 끝났는지다(`core._reserve_call`,
`call_reservations` 테이블 + 주체별 advisory lock). 값이 없는 입력(구버전·재생 사례)은 판단하지 않는다.
정책과 PAC-01~15의 대응은 [PAC_MAPPING.md](PAC_MAPPING.md), 관리대장의 `pac_ids`에도 같은 값이 있다.
정책 집합 버전은 PDF 통합 병합으로 2.1.0, 권한 번들 분리(D-25)로 **2.2.0**.

### 정책 재생 (`app/replay.py`, `./console.sh replay [N]`)
감사 행에 저장된 정책 입력(`decisions.policy_input`, 체인 v6)과 `opa/replay_cases.json`의 합성 라벨 사례
10건을 후보 OPA(`REPLAY_POLICY_DIR`, 기본 `./opa`)에 다시 질의한다. MCP는 호출하지 않는다. 결과의
`counts`(same/changed/newly_executable/newly_nonexecuting)는 사람이 해석하고, 합성 사례의
`missed_attacks`·`false_blocks`는 0이어야 한다(`tests/replay_check.py`). 정책을 바꾸기 전에 돌려
"이 변경으로 어제의 호출 중 무엇이 새로 실행되는가"를 본다.

## 3. PAC15와 capability

`opa/pac15.rego`·`decision.rego`의 실행 조건을 `policy.rego`가 Gateway 판정으로 수집합니다.
`INPUT_CONTRACT`와 `POLICY_BUNDLE`도 집행하며, PAC 차단은 monitor·예외로 완화하지 않습니다.
`registry/capabilities.json`은 주체·서버·행위·자원·환경·기한을 명시한 제한적 랩 권한입니다.
원격 도입은 독립 검토·승인을 받은 도구별 `parameter_constraints`가 필요합니다.
정적 grant의 역할명이나 관리자 지위로 범위를 넓히지 않습니다.

이전 D-25의 `authorization.grants`와 27칸은 제거했습니다. 기존 감사 기록은 보존합니다.
Console 정책 화면은 현재 capability와 검토된 원격 승인 범위를 보여 줍니다.
구체적인 사실 생성, 범위, 원본 대비 세 통합 변경과 남은 한계는
[PAC 런타임 통합](PAC_RUNTIME_2026-10-01.md)에 기록합니다.

## 4. 예외 (`exceptions.json`)

과거 333 인가를 완화하던 EXC-001·002는 종료했습니다.
PAC·입력 계약·정책 묶음은 예외 완화 대상이 아닙니다.
그 밖의 예외는 적용 상태·기한·범위·보완통제·요청자와 승인자 분리를 검사합니다.

## 5. 정책을 추가·수정하는 법
1. `policy.rego`에 `candidate["NEW-ID"] := {...} if { … }` 추가(입력은 `object.get`으로 기본값 처리 —
   값이 없을 때 조용히 허용되지 않게).
2. `policy_ledger.json`에 같은 id로 관리대장 항목(필수 항목 누락 시 시험 실패): priority·결과·상태·버전·
   목적·조건·집행·위험/통제/요구사항 id·환경·예외 허용·의무·담당·시행일.
3. `policy_test.rego`에 정상/경계/예외 시험.
4. 값이면 `data.json`, 예외면 `exceptions.json`.
5. `docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy -v`
6. `docker compose restart opa` 후 `./console.sh test`.
7. 새 판정이 업무 흐름에 보이면 `workstation/scenarios/*.toml`에 한 건 추가.
