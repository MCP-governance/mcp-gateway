# 예약·폐기 번호

이 저장소의 정본에 아직(또는 더는) 정의가 없지만 번호를 잡아 둔 ID다. [검사기](../tools/check_trace.py)는 이 표의 ID를 「정의됨」으로 본다.
규칙은 [README](README.md)의 「예약·폐기」 절이다. 정의가 정본에 들어오면 이 표의 줄을 지운다(같은 ID가 두 곳에 있으면 중복 정의 오류).
폐기된 번호는 다시 쓰지 않는다. 열 순서는 ID, 상태(예약·폐기·제안·충돌), 자리, 사유다.

| ID | 상태 | 자리 | 사유 |
| --- | --- | --- | --- |
| D-36 | 예약 | Proxy 브랜치 | 투명 MCP 리버스 프록시 결정. 이 저장소에는 없고 번호가 겹치지 않게 비워 둔다(DECISIONS.md 머리말) |
| D-37 | 예약 | Proxy 브랜치 | 위와 같다 |
| D-38 | 예약 | Proxy 브랜치 | 위와 같다. LiteLLM 비교 문서가 이 번호를 부른다 |
| D-160 | 예약 | 10/20-enrollment-pg | 장치 재등록과 오래된 heartbeat 처리 결정. 이 브랜치에서 병합되기 전 |
| D-171 | 예약 | 방향 갱신 10-20 | RM-01용으로 잡아 두고 아직 쓰지 않았다 |
| D-173 | 예약 | 10/21-sheet-runtime-completion | RM-03 국외 처리 심사 결속 결정. 병합되기 전 |
| D-174 | 예약 | 10/20-dev72-design | DEV-72 사용자 확인 단계 결정. 병합되기 전 |
| D-190 | 충돌 | 10/21-sheet-runtime-completion · 10/22-hierarchical-agents · 10/22-runtime-recovery | 원격 세 브랜치가 서로 다른 결정을 이 번호로 정의했다. 쓰지 않고, 각 브랜치는 병합 전에 다음 빈 번호로 옮긴다 |
| P-AUTHZ-DENY-001 | 폐기 | D-25 · D-66 | 333 권한 시절 정책. 과거 감사 기록의 id는 그대로 남는다 |
| P-DEPT-001 | 폐기 | D-66 | 부서 범위 정책. 위와 같다 |
| P-CONFIRM-001 | 예약 | 10/20-dev72-design | D-174가 만드는 사용자 확인 정책. 병합되기 전 |
| P-HARNESS-001 | 제안 | docs/ai/BENCHMARK_GATEWAYS.md | 하네스 신고값 경보 제안. 구현하지 않았다 |
| MCP-SESSION-001 | 제안 | research/llm-wiki/analysis/review-1020/g0702-session-termination.md | 410 선차단의 원장 기록용 정책 제안. 구현하지 않았다 |
| E14 | 충돌 | research/llm-wiki/analysis/arch-review-1018/codex-sol-review.md | 구조 검토에서 연결선(edge)에 붙인 번호다. 시험 번호로 쓰지 않는다 |
| E15 | 충돌 | research/llm-wiki/analysis/arch-review-1018/codex-sol-review.md | 구조 검토에서 연결선(edge)에 붙인 번호다. 시험 번호로 쓰지 않는다 |
| E16 | 충돌 | research/llm-wiki/analysis/arch-review-1018/codex-sol-review.md | 구조 검토에서 연결선(edge)에 붙인 번호다. 시험 번호로 쓰지 않는다 |
| E17 | 충돌 | research/llm-wiki/analysis/arch-review-1018/codex-sol-review.md | 구조 검토에서 연결선(edge)에 붙인 번호다. 시험 번호로 쓰지 않는다 |
| E18 | 충돌 | research/llm-wiki/analysis/arch-review-1018/codex-sol-review.md | 구조 검토에서 연결선(edge)에 붙인 번호다. 시험 번호로 쓰지 않는다 |
| E19 | 충돌 | research/llm-wiki/analysis/arch-review-1018/codex-sol-review.md | 구조 검토에서 연결선(edge)에 붙인 번호다. 시험 번호로 쓰지 않는다 |
