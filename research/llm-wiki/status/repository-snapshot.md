# 저장소 코드 스냅샷

확인 시각: 2026-10-18T01:10:31+09:00

HEAD: `b7b348849376a9edc5c5d66b8f0c9250ee28a1fc` · 로컬 브랜치: `10/18-field-tls`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M  .github/workflows/verify.yml
 M docs/ai/ARCHITECTURE.md
M  docs/ai/DATA_MODEL.md
UU docs/ai/DECISIONS.md
 M docs/ai/FIELD.md
A  docs/ai/OPS_RESPONSE.md
M  docs/ai/POLICY.md
M  docs/ai/README.md
M  docs/ai/RUNBOOK.md
M  docs/ai/TERMINATION_MODEL.md
M  docs/ai/TESTING.md
MM endpoint-agent/README.md
M  endpoint-agent/agent.py
M  endpoint-agent/install-windows.ps1
M  endpoint-agent/install.cmd
M  endpoint-agent/install.py
MM endpoint-agent/managed-windows.py
M  endpoint-agent/os-observer-windows.py
A  endpoint-agent/runtime-check.py
AM endpoint-agent/setup.ps1
AM endpoint-agent/tests-windows/README.md
AM endpoint-agent/tests-windows/test_windows_kit.py
AM endpoint-agent/tray.ps1
AM endpoint-agent/windows-common.ps1
AM endpoint-agent/windows-trust.ps1
AM endpoint-agent/windows-worker.ps1
A  endpoint-agent/windows_status.py
UU full_stack_lab/compose.field.yaml
M  full_stack_lab/compose.yaml
MM full_stack_lab/console.sh
M  full_stack_lab/field/pc/mcpgw_pc.py
M  full_stack_lab/gateway/Dockerfile
M  full_stack_lab/gateway/app/agent_contract.py
UU full_stack_lab/gateway/app/agent_service.py
M  full_stack_lab/gateway/app/core.py
M  full_stack_lab/gateway/app/decommission.py
M  full_stack_lab/gateway/app/dispatch.py
A  full_stack_lab/gateway/app/disposal.py
M  full_stack_lab/gateway/app/idp.py
M  full_stack_lab/gateway/app/keygen.py
M  full_stack_lab/gateway/app/main.py
A  full_stack_lab/gateway/app/ops_response.py
A  full_stack_lab/gateway/app/ops_tables.sql
A  full_stack_lab/gateway/prepare-windows-python.py
A  full_stack_lab/gateway/windows-python.json
 M full_stack_lab/registry/catalog.toml
 M full_stack_lab/registry/field/catalog.toml
M  full_stack_lab/runtime/Dockerfile
A  full_stack_lab/runtime/image_scan.py
M  full_stack_lab/runtime/worker.py
M  full_stack_lab/supply_chain/intake-worker.Dockerfile
M  full_stack_lab/supply_chain/intake_worker.py
A  full_stack_lab/supply_chain/trivy_scan.py
M  full_stack_lab/tests/field_kit_check.py
 M full_stack_lab/tests/field_tls_check.py
A  full_stack_lab/tests/ops_response_check.py
M  full_stack_lab/tests/termination_flow.py
M  research/collaboration-console/console.py
M  research/development-status-site/dist/data.json
M  research/llm-wiki/analysis/development-wbs/snapshot.json
A  research/llm-wiki/analysis/ops-response-d120-d123/README.md
A  research/llm-wiki/analysis/ops-response-d120-d123/evidence/static-checks.json
A  research/llm-wiki/analysis/ops-response-d120-d123/evidence/unit-tests.txt
A  research/llm-wiki/analysis/ops-response-d120-d123/evidence/wiki-check.json
A  research/llm-wiki/analysis/ops-response-d120-d123/requirements.json
A  research/llm-wiki/analysis/wbs-1017/deploy-ce.json
A  research/llm-wiki/analysis/windows-kit-wizard-tray/README.md
A  research/llm-wiki/analysis/windows-kit-wizard-tray/references.json
A  research/llm-wiki/analysis/windows-kit-wizard-tray/requirements.json
A  research/llm-wiki/analysis/windows-kit-wizard-tray/security-review.md
A  research/llm-wiki/analysis/windows-kit-wizard-tray/validation.json
UU research/llm-wiki/catalogs/threats.json
UU research/llm-wiki/status/backlog.md
 M research/llm-wiki/status/current.md
A  research/llm-wiki/status/reports/2026-10-17-ops-response-d120-d123.md
A  research/llm-wiki/status/reports/2026-10-17-windows-kit-wizard-tray.md
UU research/llm-wiki/status/repository-snapshot.json
UU research/llm-wiki/status/repository-snapshot.md
?? research/llm-wiki/analysis/field-tls-d124/merge-cached-diff-check.log
?? research/llm-wiki/analysis/field-tls-d124/merge-diff-check.log
?? research/llm-wiki/analysis/field-tls-d124/merge-field-kit.log
?? research/llm-wiki/analysis/field-tls-d124/merge-open-endpoints.log
?? research/llm-wiki/analysis/field-tls-d124/merge-pyflakes.log
?? research/llm-wiki/analysis/field-tls-d124/merge-shell-syntax.log
?? research/llm-wiki/analysis/field-tls-d124/merge-tls-unit.log
?? research/llm-wiki/analysis/field-tls-d124/merge-validation.json
?? research/llm-wiki/analysis/field-tls-d124/merge-windows-kit.log
?? research/llm-wiki/status/reports/2026-10-18-field-tls-d124-merge.md
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `402190acbec3362fae2cbc0d442023734740b59cf6f33c51b553f533b3853f50` |
| `full_stack_lab/gateway/app/pac.py` | `a292041f40d1b972607dc766a9daf641452e46f685a079e76b009694f18ec86f` |
| `full_stack_lab/gateway/app/poisoning.py` | `bb63b3094567f96315bd302c996fe3fbecf0e608f080874ea1a0a19e9857dc96` |
| `full_stack_lab/gateway/app/idp.py` | `da269bb5318b7b68e5f8a8ae94b68e2d81a2688db258aab2ce6d69adc854ce28` |
| `full_stack_lab/gateway/app/privacy.py` | `5eeb5df2cd13c2f59a3d946861f1d62cf5f5de6266f41c7b33c88e7fc8ff36b1` |
| `full_stack_lab/gateway/app/secret_scan.py` | `c6d981869e476d64d8b3e646c307f29d223942333fad84eb7e147a05593750db` |
| `full_stack_lab/opa/pac15.rego` | `067f288654d530c538d1438b7a8341b8c42684d24dee880d4971d0503ce0c850` |
| `full_stack_lab/opa/decision.rego` | `b6fe334869e38016dd043489b2c3f63207adc5a54fbef199738517b815a9b904` |
| `endpoint-agent/bootstrap.py` | `b6803fd12966c33655d49b13ec337eecef5626bef1feb7f9c58ce6c1e6159ab0` |
| `endpoint-agent/managed-linux.py` | `017fe09ab14e1e4ba5366d28d8c6a15aa46da458b4bbd30542142d9d7a6efd8f` |
| `endpoint-agent/enforce-linux.py` | `f4da4ea3cff03e29877314911d2bb1d37df12b5fa0bf4458191160bebea82af4` |
