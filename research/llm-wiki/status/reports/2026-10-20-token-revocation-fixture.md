# 2026-10-20 token_revocation_pg_check 복구와 회전 기록 순서 (D-154)

- 기준: main 751aee9, 브랜치 `10/20-token-revocation-fixture`(Claude, Codex 한도 중).
- 기존 시험 변경(적대 검증 대기): ① `isolated_disposal()`로 서명 폐기 목록 초기화(D-123 이후 필수), ② 장치 폐기 뒤 상태 기대값 403 → {401, 403}(G07.04가 장치 토큰을 서명 목록에 기록해 401이 먼저 남).
- 제품 변경: `idp.token` refresh 회전의 서명 기록을 커밋 뒤로(D-154). 수정 전 실험실에서 "실패한 발급 뒤 갱신 토큰이 계속 동작" 실패 재현.

| 시험(격리 실험실 PostgreSQL) | 결과 |
| --- | --- |
| token_revocation_pg_check | 22/22 |
| restore_residual_pg_check | 10/10 |
| oauth_negative_pg_check | 11/11 |
| dispatch_recheck_pg_check | 280/280 |
