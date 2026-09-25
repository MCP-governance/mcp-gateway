# 정책 (OPA/Rego)

> 파일: `full_stack_lab/opa/`
> - `policy.rego` — 규칙 (`package mcp.authz`, 결과는 `data.mcp.authz.decision`)
> - `policy_test.rego` — 단위 시험(85건)
> - `policy_ledger.json` — 정책 관리대장(정책마다 이름·목적·우선순위·결과·상태·버전·위험/통제 id·예외 허용 여부·의무)
> - `exceptions.json` — 예외 관리대장
> - `data.json` — 자주 바뀌는 값(제한 실행 값, egress 허용 호스트, 부서 범위 스위치)
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
| 78 | P-DLP-001 | 차단 | 민감정보(주민번호·카드 등) 외부 전송 |
| 80 | P-333-DENY-001 | 차단 | 최소권한 미충족(333 행렬) |
| 90 | P-X-APPROVAL-001 | 승인 | 중요정보의 고위험 실행(x) — 내부 목적지. 외부 반출은 MCP-DATA-EGRESS-001이 먼저 막는다 |
| 95 | P-UNTRUSTED-CONTENT-001 | 승인 | 비신뢰 콘텐츠 기반 고위험 실행 |
| 100 | P-VOLUME-001 | 승인 | 중요정보 누적 접근 |
| 110 | P-DEPT-001 | 승인 | 소관 부서 외 중요정보(`data.department_scope.enabled`, 기본 꺼짐) |
| 120 | P-X-RESTRICT-001 | 제한 | 외부 전송을 제한 값으로(`restrictable ∩ data.restrictions`) |
| 125 | P-X-ALERT-001 | 경고 | 제한할 수 없는 외부 전송 |
| 128~135 | P-UNTRUSTED-CONTENT-002, P-ANOMALY-001, MCP-SHADOW-00x | 경고 | 비신뢰 콘텐츠 열람, 반복 차단, 섀도 MCP 보유자 |
| 130 | P-IMPORTANT-ALERT-001 | 경고 | 중요정보 열람 |
| 140 | P-333-ALLOW-001 | 허용 | 최소권한 충족 |

Gateway 쪽(OPA 밖)에서 나오는 판정: `P-INPUT-SCHEMA-001`(승인 스키마 위반), `P-DATA-INSPECTION-001`
(Presidio 입력 검사 불능, priority 2010), `MCP-OUTPUT-001`(실행됐지만 결과 보류 — 크기·주입 표지·출력 개인정보
검사 불능), `MCP-UPSTREAM-001`(상위 오류), `P-CONTROL-FAIL-CLOSED`(OPA 불능), `P-MONITOR-001`(관찰 모드).

OPA 입력의 개인정보 관련 필드: `request.pii_types`(Presidio 엔터티 유형만 — 값은 넣지 않는다),
`request.sequence_flags`, `request.dlp`(분류기의 정규식 DLP 라벨, `P-DLP-001`), `destinations[].external`.
정책 집합 버전은 PDF 통합 병합으로 **2.1.0**.

### 정책 재생 (`app/replay.py`, `./console.sh replay [N]`)
감사 행에 저장된 정책 입력(`decisions.policy_input`, 체인 v6)과 `opa/replay_cases.json`의 합성 라벨 사례
10건을 후보 OPA(`REPLAY_POLICY_DIR`, 기본 `./opa`)에 다시 질의한다. MCP는 호출하지 않는다. 결과의
`counts`(same/changed/newly_executable/newly_nonexecuting)는 사람이 해석하고, 합성 사례의
`missed_attacks`·`false_blocks`는 0이어야 한다(`tests/replay_check.py`). 정책을 바꾸기 전에 돌려
"이 변경으로 어제의 호출 중 무엇이 새로 실행되는가"를 본다.

## 3. 333 행렬 (계약 정상·승인 없음일 때의 기본)

| 역할 \ 등급·행위 | 공개 r/w/x | 내부 r/w/x | 중요 r/w/x |
| --- | --- | --- | --- |
| 협력사 직원 | 허용/차단/차단 | 차단/차단/차단 | 차단/차단/차단 |
| 직원 | 허용/차단/차단 | 허용/허용/차단 | 경보/차단/차단 |
| 관리자 | 허용/허용/경보 | 허용/허용/경보 | 허용/허용/승인 |

Console `#/policy`가 OPA에 27칸을 직접 질의해 보여 준다. `policy_test.rego`의
`test_permission_matrix_matches_recorded_baseline`이 이 표가 바뀌면 실패한다.

## 4. 예외 (`exceptions.json`)
- **EXC-001** 협력사 직원의 외부 감사 사본 1건(`/shared/confidential/audit/external-audit-copy-2026.md`,
  `read_text_file`) 열람: `P-333-DENY-001` 차단 → Alert, 기한 2026-12-31.
- **EXC-002** 플랫폼개발팀의 개발 샌드박스 `start_process`(x): `P-333-DENY-001` 차단 → Approval(건별 승인),
  기한 2026-12-31.

예외가 성립하려면: 상태 "적용", 기한 있음, 범위(scope) 비어 있지 않음, 보완통제 있음, 요청자≠승인자,
기한 안, **완화만**(원래 판정보다 약한 effect). 예외로 완화된 호출에는 `evidence.enhanced`,
`exception.monitored`, `alert.security` 의무가 붙는다.

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
