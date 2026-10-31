# 저장소 코드 스냅샷

확인 시각: 2026-10-31T14:35:09+09:00

HEAD: `3402278b1473effba80abfb1b7d21cee295d5533` · 로컬 브랜치: `10/28-windows-kit`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M .github/actions/compose-cache/index.cjs
 M .github/ci/compose-cache.test.cjs
 M full_stack_lab/gateway/app/local_sources.py
 M full_stack_lab/supply_chain/dependency_locks.py
 M full_stack_lab/tests/dependency_locks_check.py
 M full_stack_lab/tests/dest_pin_credential_redaction_check.py
 M full_stack_lab/tests/endpoint_stdio_check.py
 M full_stack_lab/tests/field_tls_check.py
 M full_stack_lab/tests/intake_fixture.py
 M full_stack_lab/tests/intake_identity_pg_check.py
 M full_stack_lab/tests/intake_one_click_ast_check.py
 M full_stack_lab/tests/intake_one_click_check.py
 M full_stack_lab/tests/local_run_presets_check.py
 M full_stack_lab/tests/nested_tx_check.py
 M full_stack_lab/tests/nested_tx_refactor_check.py
 M full_stack_lab/tests/oneclick_markers_provenance_check.py
 M full_stack_lab/tests/provenance_verify_check.py
 M full_stack_lab/tests/remaining_controls_check.py
 M full_stack_lab/tests/root_solo_behavior_check.py
 M research/llm-wiki/analysis/integration-cases.json
 M research/llm-wiki/analysis/requirements.json
 M research/llm-wiki/status/backlog.md
 M research/llm-wiki/status/current.md
?? api.py
?? c
?? p3_ui.py
?? q
?? research/llm-wiki/status/reports/2026-10-31-pr69-d299-ci.md
?? sftp_put.py
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `f8dfbc92cdc8f7972a37bcb412fd61a7801a1c55ec9d42900d4ead3c0861c523` |
| `full_stack_lab/gateway/app/pac.py` | `b3f0ad2728cd183117416926433af4a7f4b6ac6b922423d0c42fc07fa7c5cbdf` |
| `full_stack_lab/gateway/app/poisoning.py` | `c676b6259619e5f8eababc13dfe0d69bb5a29c42c2ac31abadb737c871c93c06` |
| `full_stack_lab/gateway/app/idp.py` | `3685b2b442fe9f6cbcf7836a366a0e12fc384d64cf15e14228cb3587d7fc55fe` |
| `full_stack_lab/gateway/app/privacy.py` | `592d7649736ef4580cb9a2faad8f1e661eeacfe68e056512e002e10471081f8f` |
| `full_stack_lab/gateway/app/secret_scan.py` | `daeda53835856b9ea603dfe19d377befa38510759eb58572edfb8b0318b7f951` |
| `full_stack_lab/opa/pac15.rego` | `067f288654d530c538d1438b7a8341b8c42684d24dee880d4971d0503ce0c850` |
| `full_stack_lab/opa/decision.rego` | `b6fe334869e38016dd043489b2c3f63207adc5a54fbef199738517b815a9b904` |
| `endpoint-agent/bootstrap.py` | `73d129b5c572ab9290fc0528aff4f7d0a17ddb5ea663f48740453daa7eb1dee9` |
| `endpoint-agent/managed-linux.py` | `06ae3638334c39d195f09fb87ffb4ec219eee955f333f24584e428107b7a2d2f` |
| `endpoint-agent/enforce-linux.py` | `2ce6a711e2e9dfcc47e2b1ca3cebdf9fe6f39171267312ab42c87b1e822e025c` |
