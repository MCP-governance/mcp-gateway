# 저장소 코드 스냅샷

확인 시각: 2026-10-28T20:41:50+09:00

HEAD: `0c0bb1512865ff72a53fb120a7442ad7a17b0ff0` · 로컬 브랜치: `10/28-endpoint-stdio`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M CHANGELOG.md
 M deploy/README.md
 M deploy/compose.yaml
 M deploy/mint.sh
 M docs/ai/ARCHITECTURE.md
 M docs/ai/decisions/D-101-150.md
 M docs/ai/decisions/D-151-200.md
 M docs/ai/decisions/D-251-300.md
 M endpoint-agent/local-runner.py
 M endpoint-agent/managed-windows.py
 M endpoint-agent/stdio_source.py
 M endpoint-agent/stdio_windows.py
 M endpoint-agent/tests-windows/test_endpoint_stdio.py
 M full_stack_lab/compose.field.yaml
 M full_stack_lab/compose.yaml
 M full_stack_lab/console.sh
 M full_stack_lab/gateway/app/agent_service.py
 M full_stack_lab/gateway/app/agent_static/console.js
 M full_stack_lab/gateway/app/core.py
 M full_stack_lab/gateway/app/disposal.py
 M full_stack_lab/gateway/app/local_sources.py
 M full_stack_lab/gateway/app/main.py
 M full_stack_lab/gateway/app/ops_response.py
 M full_stack_lab/gateway/app/pac.py
 M full_stack_lab/gateway/app/registry.py
 M full_stack_lab/gateway/app/sbom_impact.py
 M full_stack_lab/gateway/app/upstream.py
 D full_stack_lab/runtime/Dockerfile
 D full_stack_lab/runtime/image_scan.py
 D full_stack_lab/runtime/recipes/markitdown-mcp.Dockerfile
 D full_stack_lab/runtime/recipes/markitdown-mcp.toml
 D full_stack_lab/runtime/worker.py
 M full_stack_lab/supply_chain/intake-worker.Dockerfile
 M full_stack_lab/supply_chain/intake_worker.py
 M full_stack_lab/tests/approved-mcp-console.test.mjs
 M full_stack_lab/tests/approved_mcp_download_check.py
 M full_stack_lab/tests/endpoint_source_api_check.py
 M full_stack_lab/tests/endpoint_stdio_check.py
 M full_stack_lab/tests/event_kind_labels_check.py
 M full_stack_lab/tests/intake_one_click_ast_check.py
 M full_stack_lab/tests/intake_one_click_check.py
 M full_stack_lab/tests/ops_response_check.py
 M full_stack_lab/tests/resource_residual_check.py
 D full_stack_lab/tests/runtime_rollback_check.py
 D full_stack_lab/tests/runtime_rollback_provenance_check.py
 D full_stack_lab/tests/runtime_rollback_queue_check.py
 D full_stack_lab/tests/runtime_rollback_reconcile_check.py
 D full_stack_lab/tests/runtime_worker_check.py
 M full_stack_lab/tests/sbom_impact_check.py
 M full_stack_lab/tests/server_egress_check.py
 M full_stack_lab/tests/transfer_grade_check.py
 M research/llm-wiki/analysis/endpoint-stdio/README.md
 M research/llm-wiki/analysis/endpoint-stdio/requirements.json
 M research/llm-wiki/analysis/resource-residual/README.md
 M research/llm-wiki/analysis/threat-trace-review-1020/README.md
 M research/llm-wiki/status/backlog.md
 M research/llm-wiki/status/current.md
 M research/llm-wiki/status/decisions-index.md
 M research/llm-wiki/status/reports/2026-10-28-endpoint-stdio.md
 M research/llm-wiki/status/reports/README.md
 M research/llm-wiki/status/repository-snapshot.json
 M research/llm-wiki/status/repository-snapshot.md
 M research/llm-wiki/threats/control-map.md
?? BRIEF-endpoint-stdio.md
?? full_stack_lab/supply_chain/dependency_locks.py
?? full_stack_lab/tests/dependency_locks_check.py
?? research/llm-wiki/analysis/endpoint-stdio/local-suite-round2-first.json
?? research/llm-wiki/analysis/endpoint-stdio/test-results-round2.json
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `f09aaa35512ea52179af7056920314b61ff58c9b1406720d71cf19ff6cbe0f08` |
| `full_stack_lab/gateway/app/pac.py` | `b3f0ad2728cd183117416926433af4a7f4b6ac6b922423d0c42fc07fa7c5cbdf` |
| `full_stack_lab/gateway/app/poisoning.py` | `c676b6259619e5f8eababc13dfe0d69bb5a29c42c2ac31abadb737c871c93c06` |
| `full_stack_lab/gateway/app/idp.py` | `3685b2b442fe9f6cbcf7836a366a0e12fc384d64cf15e14228cb3587d7fc55fe` |
| `full_stack_lab/gateway/app/privacy.py` | `592d7649736ef4580cb9a2faad8f1e661eeacfe68e056512e002e10471081f8f` |
| `full_stack_lab/gateway/app/secret_scan.py` | `daeda53835856b9ea603dfe19d377befa38510759eb58572edfb8b0318b7f951` |
| `full_stack_lab/opa/pac15.rego` | `067f288654d530c538d1438b7a8341b8c42684d24dee880d4971d0503ce0c850` |
| `full_stack_lab/opa/decision.rego` | `b6fe334869e38016dd043489b2c3f63207adc5a54fbef199738517b815a9b904` |
| `endpoint-agent/bootstrap.py` | `73d129b5c572ab9290fc0528aff4f7d0a17ddb5ea663f48740453daa7eb1dee9` |
| `endpoint-agent/managed-linux.py` | `41fea271149445ec233f7ce92992a1042a4b826b8b4c87b3926e0944b4a624d5` |
| `endpoint-agent/enforce-linux.py` | `2ce6a711e2e9dfcc47e2b1ca3cebdf9fe6f39171267312ab42c87b1e822e025c` |
