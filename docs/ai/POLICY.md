# 정책 (OPA/Rego)

D-120~D-123 운영 대응은 기존 정책 ID와 계약 비활성·종료 경계를 사용한다. 새 OPA ID나 관리대장 행을 추가하지 않았다. 경보 자체 시험은 실제 로드된 OPA의 `decision`·`policy_id`와 합성 경보 기록을 대조하며 `decisions`에 합성 요청을 쓰지 않는다. [운영 대응](OPS_RESPONSE.md).

DEV-68 공급자 지원 종료는 도입 등록의 `valid_until` 상한으로 적용한다. 지원 종료일 다음 날부터 기존 `P-APPROVAL-EXPIRY-001` 만료 경로가 호출을 차단하고 재승인을 요구한다. 공급자 필수 정보·등록부 내보내기는 [D-137](DECISIONS.md#d-137-도입-서버-공급자-보증을-승인에-묶고-eol은-승인-만료로-연결한다) 참조.

DEV-71 도입 신청의 위험 등급은 신청 입력의 표 산정이고 새 OPA 정책 ID를 만들지 않는다. 등급은 승인 방식(관리자 1명·2명·사유)만 정하며, 입력이 없는 기존 승인 서버는 30일 유예 뒤 같은 `valid_until` 만료 경로로 재승인 대기가 된다. [D-143](DECISIONS.md#d-143-도입-신청의-위험-등급은-신청자가-적은-입력의-표-산정으로-승인-방식은-등급이-정하고-기존-승인-서버는-30일-유예-뒤-재승인-대기로-한다-2026-10-20-dev-71) 참조.

> 파일: `full_stack_lab/opa/`
> - `policy.rego` — 규칙 (`package mcp.authz`, 결과는 `data.mcp.authz.decision`)
> - `policy_test.rego` — 단위 시험(91건)
> - `policy_ledger.json` — 정책 목록(정책마다 이름·목적·우선순위·결과·상태·버전·위험/통제 id·의무)
> - `data.json` — 운영 제한과 자주 바뀌는 값(제한 실행 값, egress 허용 호스트)
> - `residency.json` — `registry/data_residency.json`에서 생성한 처리·저장 국가 규칙
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
| 47 | P-FLOW-001 | 차단 | 같은 주체가 최근 10분 안에 다른 서버에서 중요정보를 읽은 뒤 쓰기·실행·공급자 호스팅 호출을 하는데 받는 도구가 그 서버를 심사받지 않음(`request.flow_sources`·`tool.accepts_from`, 공급자 호스팅은 심사로도 못 풂, 관찰 모드에서도 집행, D-133). 설정 `FLOW_MATCH_MODE`가 기본 `coarse`면 읽은 모든 서버가 출처이고, `content`면 호출 내용이 읽은 내용과 같거나 비교할 수 없는 서버만 출처다. 대조 결과는 `request.flow_observed`, 모드는 `request.flow_match_mode`에 기록(D-142) |
| 48 | P-RESIDENCY-001 | 차단 | 처리·저장 위치나 국외 이전 규칙 확인 불가, 또는 이전 금지(D-138) |
| 50 | MCP-CATALOG-001 | 차단 | 승인 계약(설명·스키마·버전 해시) 불일치 |
| 55 | P-APPROVAL-EXPIRY-001 | 차단 | 승인 유효기간 만료 자산 |
| 60 | P-CLASSIFICATION-001 | 차단 | 분류 근거 없는 데이터 |
| 70 | P-RATE-001 | 차단 | 호출량 상한 |
| 71 | P-RATE-002 | 차단 | 동시 실행 상한(이 주체가 지금 돌리는 호출 수) |
| 72 | P-RATE-003 | 차단 | 실행 중·미확인 또는 완료 변경 이력 보존 기간 안의 같은 호출(D-126) |
| 73 | P-VOLUME-002 | 차단 | 단일 읽기의 전체 선택자·요청 건수 상한(D-125, 게이트웨이 사전 검사) |
| 78 | P-DLP-001 | 차단 | 민감정보(주민번호·카드 등) 외부 전송 |
| 79~89 | INPUT_CONTRACT, POLICY_BUNDLE, PAC-01~15 | 차단·승인 | 사실 계약·정책 버전·승인 실행 범위 검사 |
| 80 | PAC-05-DELEGATION-UNSUPPORTED | 차단 | 대리 실행을 주장하는데 전송 계층에서 검증한 에이전트 신원이 없음(D-94). Console에는 "지원 안 함"으로 표시 |
| 83 | P-RESIDENCY-002 | 추가 승인 | 처리·저장 국가 규칙이나 국외 이전 근거에 따라 건별 승인 필요(D-138) |
| 90 | P-X-APPROVAL-001 | 승인 | 중요정보의 고위험 실행(x) — 내부 목적지. 외부 반출은 MCP-DATA-EGRESS-001이 먼저 막는다 |
| 95 | P-UNTRUSTED-CONTENT-001 | 승인 | 비신뢰 콘텐츠 기반 고위험 실행 |
| 100 | P-VOLUME-001 | 승인 | 중요정보 누적 접근 |
| 120 | P-X-RESTRICT-001 | 제한 | 외부 전송을 제한 값으로(`restrictable ∩ data.restrictions`) |
| 125 | P-X-ALERT-001 | 경고 | 제한할 수 없는 외부 전송 |
| 128~135 | P-UNTRUSTED-CONTENT-002, P-ANOMALY-001, MCP-SHADOW-00x | 경고 | 비신뢰 콘텐츠 열람, 반복 차단, 섀도 MCP 보유자 |
| 130 | P-IMPORTANT-ALERT-001 | 경고 | 중요정보 열람 |
| 136 | P-SCOPE-001 | 경고 | 이용 관계가 허용한 자원 밖(`relationship.in_scope=false`, D-39). 관계가 없는 서버·값이 없는 입력은 판단하지 않는다 |
| 140 | P-AUTHZ-ALLOW-001 | 허용 | PAC 실행 범위 충족 |
| 2013 | P-HIGH-IMPACT-001 | 추가 승인 | 중대 영향 도구의 개별 사람 승인·설명 열람 필요. 게이트웨이 로컬 집행(D-139) |

Gateway 쪽(OPA 밖)에서 나오는 판정: `P-INPUT-SCHEMA-001`(승인 스키마 위반), `P-INPUT-FIELD-001`(도구 심사의 허용 입력 항목 밖, D-131), `P-CONSENT-001`(실행될 호출에 본인의 유효한 사용자 동의 없음, 확인 요청 생성, D-134), `P-DATA-INSPECTION-001`
(Presidio 입력 검사 불능, priority 2010), `MCP-OUTPUT-001`(실행됐지만 결과 보류 — 크기·주입 표지·출력 개인정보
검사 불능), `MCP-UPSTREAM-001`(상위 오류), `P-CONTROL-FAIL-CLOSED`(OPA 불능), `P-MONITOR-001`(관찰 모드).

`P-HIGH-IMPACT-001`은 도구 심사의 `high_impact=true`에 대해 개별 사람 승인을 강제한다(D-139, POL-27·38·22).
영향 영역은 고용·급여, 신용, 법적 효력, 급부, 계약, 서비스 접근이다. 관리대장 priority는 **2013**, 결과는 **추가 승인**이다.
OPA의 DB 없는 불리언 `approval.granted`만으로 인적 개입 증빙을 검증할 수 없으므로 게이트웨이에서 집행한다.
관찰 모드 투영 뒤, 실행 전에 적용하며 집행 중인 선행 차단은 유지한다. 승인 재실행은 기존 모든 정책을 다시 거친다.
최종 전송 트랜잭션은 현재 도구 범위와 승인 사건·요청 지문을 대조하고 승인 행을 한 번 소비한다. 기한·철회·재사용·심사 범위 변경은 전송을 막는다.
같은 트랜잭션에서 주체 행과 현재 심사 조건·등급을 덮는 동의 행을 공유 잠그고, 동의 만료는 intent INSERT의 실제 시각으로 확인한다(D-140). 중요정보 열람 원장 기록과 최종 흐름 조회는 같은 주체별 잠금을 쓴다. 판정 때보다 흐름 출처가 늘면 `P-FLOW-001`, 유효 동의가 없으면 `P-CONSENT-001`, 최종 검사·커밋 실패는 `P-CONTROL-FAIL-CLOSED`로 전송하지 않는다. intent 커밋이 먼저인 호출은 이미 전송 가능 호출로 기록되므로 뒤의 철회가 외부 효과를 되돌리지는 않는다.
승인자는 설명 증빙을 열람한 기록과 검토 근거가 있어야 승인할 수 있다. 번복은 별도 사건과 철회 시각으로 남기며 **이미 실행된 효과를 복구하지 않는다**.
개인정보 본문 없는 설명·개입·판정 번들은 관리자 인증의 `/api/approvals/{id}/evidence`에서 조회·내보낸다.
개입 이력의 처리자는 현재 표시 이름으로 보이고 없으면 `—`다. 내보내기의 감사 주체 식별자는 유지한다.
OPA만 실행하는 정책 재생은 이 로컬 통제를 검증하지 않는다. [호출 경로·원자 요구사항·한계](../../research/llm-wiki/analysis/high-impact/README.md).

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
Console 등록 서버는 도구마다 사람이 승인한 범위(목적·자산·행위·외부 목적지)가 있어야 켜지고(D-91), 범위가 없는 도구는
`MCP-REGISTRY-002`로 거부됩니다. 승인 기한 만료·철회·계약 변경은 각각 `P-APPROVAL-EXPIRY-001`·`MCP-REGISTRY-001`·
`MCP-CATALOG-001`이며 자동 연장은 근거가 그대로일 때만 합니다(D-93).
원격 도입은 독립 검토·승인을 받은 도구별 `parameter_constraints`가 필요합니다.
정적 grant의 역할명이나 관리자 지위로 범위를 넓히지 않습니다.

이전 D-25의 `authorization.grants`와 27칸은 제거했습니다. 기존 감사 기록은 보존합니다.
Console 정책 화면은 현재 capability와 검토된 원격 승인 범위를 보여 줍니다.
구체적인 사실 생성, 범위, 원본 대비 세 통합 변경과 남은 한계는
[PAC 런타임 통합](PAC_RUNTIME_2026-10-01.md)에 기록합니다.

## 4. 예외

계약의 `known_tools_only`·`metadata_safe`는 D-127부터 요청 도구의 영향 범위로 계산한다. 전체 `exact_match=false`만으로 정상 도구까지 거부하지 않는다. 영향 미확정·해시 불일치·승인되지 않은 도구는 계속 차단한다. Rego 결과·우선순위·조직/자산 권한·감사 체인 규칙은 변경하지 않았다. [운영 대응](OPS_RESPONSE.md)에 적용·복구와 SIEM 전달 경계를 기록한다.

예외 등록부는 없습니다(2026-10-03 제거). 정책을 완화해야 하면 정책 목록과 규칙을 바꾸고 시험을 고칩니다.
333 권한 시절의 `P-AUTHZ-DENY-001`·`P-DEPT-001`과 예외 EXC-001·002는 삭제했고, 과거 감사 기록의 해당 id는 그대로 둡니다.

## 5. 정책을 추가·수정하는 법
1. `policy.rego`에 `candidate["NEW-ID"] := {...} if { … }` 추가(입력은 `object.get`으로 기본값 처리 —
   값이 없을 때 조용히 허용되지 않게).
2. `policy_ledger.json`에 같은 id로 관리대장 항목(필수 항목 누락 시 시험 실패): priority·결과·상태·버전·
   목적·조건·집행·위험/통제/요구사항 id·환경·의무·담당·시행일.
3. `policy_test.rego`에 정상/경계 시험.
4. 값이면 `data.json`.
5. `docker run --rm --entrypoint /opa -v "$PWD/opa:/policy:ro" openpolicyagent/opa:1.20.2-static test /policy -v`
6. `docker compose restart opa` 후 `./console.sh test`.
7. 새 판정이 업무 흐름에 보이면 `workstation/scenarios/*.toml`에 한 건 추가.

## 처리·저장 위치 규칙 (D-138 / DEV-69)

| 번호 | 정책 | 결과 |
| --- | --- | --- |
| P-RESIDENCY-001 | 처리·저장 위치 전송 차단 | 차단 |
| P-RESIDENCY-002 | 국외 이전 건별 승인 | 추가 승인 |

`registry/data_residency.json`의 `residency.rules`는 데이터 등급→ISO 국가 코드→`allow`/`approval`/`deny`다.
`*`는 명시되지 않은 국가의 기본값이다. 처리·저장 국가의 합집합과 모든 외부 목적지를 각각 평가하며 하나라도 금지면 차단한다.
내부 이상 등급은 국가·처리 주체·위치 근거가 없으면 차단한다. 공개 외 데이터가 조직 소재 국가 밖으로 나가고 이전 근거가 없으면 국가 규칙이 허용이어도 건별 승인 대상이다.
팩 누락·재생성 누락·실제 OPA 로드값 불일치도 차단하며 관찰 모드에서 완화하지 않는다.

기본값은 공개 전송 허용, 내부 데이터 KR 허용/그 밖 승인 필요, 중요 데이터 KR 허용/그 밖 금지인 **잠정 조직 설정**이다.
국가별 법적 허용 여부나 개인정보 국외 이전의 적법성을 확정하지 않는다. 기존 개인정보 반출·PAC-12·서버 간 흐름 차단은 별도로 적용한다.
허용 판정은 기존 `P-AUTHZ-ALLOW-001` 등으로 기록되고 위치 사실은 `policy_input.pac.facts.residency`에 보존된다.
승인은 기존 PAC-13 독립 승인·기한·일회용 검사를 재사용하며 위치/목적지/팩 변경 시 digest가 바뀐다. 금지는 승인으로 풀리지 않는다.
차단 우선순위는 48, 승인 필요는 83으로 기존 계약·권한 차단을 우회하지 않는다.

```bash
cd full_stack_lab
python3 registry/render_residency.py          # 조직 정본 변경 후 생성, 두 JSON을 함께 검토
python3 registry/render_residency.py --check
# 솔루션 기기에서만: ./console.sh field up
```

원격 서버의 위치 속성은 계약 검토 사양과 승인 해시에 포함한다. 기존 승인 사양과 다르면 새 도입 검토가 필요하다.
내부 서버는 카탈로그 `organization.machine_location`을 사용하고 외부 목적지는 `organization.destination_locations`의 정확한 호스트별 선언을 사용한다.
공급자 주소의 DNS/IP나 URL의 국가 접미사로 처리 위치를 추정하지 않는다.
[설정·한계·시험](../../research/llm-wiki/analysis/dev69-data-residency/README.md).
