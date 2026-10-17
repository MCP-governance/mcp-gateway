# OPA 규칙 레이블 → 결정 로그 시험 (2026-10-17)

질문: 규칙에 `# METADATA`의 `labels`(예: 엑셀 POL 번호, 런타임 PAC 번호)를 달면 게이트웨이가 쓰는 OPA에서 결정 로그로 남는가. 근거 문서는 [LIB-K03](../../../papers/LIB-K03.md)(OPA 문서 v1.21.2)이고 이 시험은 저장소 `full_stack_lab/compose.yaml`이 쓰는 이미지와 같은 `openpolicyagent/opa:1.20.2-static`(이미지 ID `d686597918ba…`)으로 했다.

## 방법

- 일회성 컨테이너: `run_probe.sh openpolicyagent/opa:1.20.2-static`이 `opa run --server --set decision_logs.console=true`를 127.0.0.1:18181에만 열고, `cases.json`의 5개 질의를 보낸 뒤 콘솔 결정 로그를 `out-*/decision-log-events.jsonl`로 저장하고 컨테이너를 지운다. compose 스택·솔루션 기기·PJ1은 쓰지 않았다(AGENTS 소유자 규칙 1). 실행 환경은 이 노트북의 WSL(kali) docker다.
- 시험 정책 `policy/probe.rego`는 게이트웨이 `pac15.rego`의 `deny contains "PAC-nn" if { not pacnn }` 모양을 흉내 낸 최소 예제다. 실제 `pac15.rego`·`policy.rego`는 수정하지 않았고 실제 입력도 넣지 않았다. `opa test`(3건)는 PASS(`out-*/opa-test.txt`).

## 관찰 (OPA 1.20.2)

| 사례 | 질의·입력 | 결정 로그 `rule_labels` |
| --- | --- | --- |
| A | `probe/allow`, 승인된 목적지 | `[{probe}, {policy_id: POL-22, probe}]` — 결과가 true일 때 평가된 규칙의 레이블 |
| B | `probe/deny`, 두 규칙 모두 발화 | `[{POL-26, PAC-12, probe}, {POL-27, PAC-13, probe}]` |
| C | `probe/deny`, PAC-12만 발화 | `[{POL-26, PAC-12, probe}]` — 발화하지 않은 PAC-13 레이블은 없다 |
| D | `probe/deny`, 아무 규칙도 발화하지 않음 | `[{probe}]` — 패키지 레이블만. 정책 번호가 남지 않는다 |
| E | `id: ID-PROBE-01` 주석 + `labels` | `rule_labels`는 남지만 **`ids` 필드는 이벤트에 없다** |

결론과 한계:

1. **`labels` → `rule_labels`는 1.20.2에서 동작한다.** 문서(1.21.2)가 말한 필드가 현재 운영 판본에서도 나온다. 먼저 `labels`를 쓰는 설계는 판본 업그레이드 없이 가능하다.
2. **`id` 주석 키는 1.20.2에서 오류 없이 받아들여지지만 결정 로그의 `ids`로 남지 않았다.** `ids`는 1.21.2 문서에만 있고 1.21.x 판본은 시험하지 못했다(이미지를 새로 내려받지 않았다). 정책 번호는 `id`가 아니라 `labels`에 싣는다.
3. **레이블은 '성공적으로 평가된 규칙'에서만 남는다.** `deny contains` 규칙은 발화(본문 참)할 때만 남으므로 이 방식은 **차단 사유의 정책 번호**는 기록하지만 '검사했고 통과했다'는 증거는 아니다(사례 C·D). 통과 증거에는 별도 출력(예: 모든 PAC의 판정 결과)이 필요하다.
4. `rule_labels`는 규칙별 묶음이 아니라 병합된 맵의 목록이다. 헬퍼 규칙·패키지 레이블이 만든 `{probe}` 같은 항목이 섞이므로 소비자는 `policy_id` 키가 있는 항목만 골라야 한다. 정책 번호와 런타임 PAC 번호를 같은 맵에 함께 싣는 편이 짝이 깨지지 않는다.
5. 실제 게이트웨이 정책(`pac15.rego`, `policy.rego`)에 레이블을 달아 보지 않았고, OPA 결정 로그를 읽어 쓰는 코드는 찾지 못했다(`full_stack_lab`에서 `decision_logs`는 compose.yaml 67행뿐이고, 게이트웨이의 `decision_id`는 자체 `decisions` 테이블 키다). 정책 번호를 남기는 현재 경로는 게이트웨이 원장과 `policy_ledger.json`의 `pac_ids`다. 레이블 주석 추가가 기존 `opa test`와 재생 사례(`replay_cases*.json`)에 영향이 없는지는 미확인이다.

## 재현

```bash
# WSL(docker)에서
bash research/llm-wiki/analysis/drive-curation/opa-labels-probe/run_probe.sh openpolicyagent/opa:1.20.2-static
```

| 파일 | SHA-256 앞 16자 |
| --- | --- |
| `out-openpolicyagent_opa_1.20.2-static/decision-log-events.jsonl` | `6b8256b702079004` |
| `policy/probe.rego` | `9c7db6c09c640b31` |
| `policy/probe_id.rego` | `dd24e3cf03a2eeb2` |
| `cases.json` | `14b3c7d59fde250d` |

결정 로그의 `decision_id`·`timestamp`는 실행마다 달라지므로 해시는 이 실행의 값이다. 다른 판본은 이미지 태그만 바꿔 같은 스크립트로 시험하고 `out-*` 폴더가 태그별로 따로 생긴다.
