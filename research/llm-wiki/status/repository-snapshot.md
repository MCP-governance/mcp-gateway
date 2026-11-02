# 저장소 코드 스냅샷

확인 시각: 2026-11-02T15:18:36+09:00

HEAD: `76c63c1de720e52dcf3067c29de5aaa797a5a12f` · 로컬 브랜치: `feat/console-ui`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M  docs/ai/decisions/D-301-350.md
M  full_stack_lab/gateway/app/agent_static/console.js
M  full_stack_lab/gateway/app/organization_policies.json
M  full_stack_lab/gateway/app/organization_policy.py
M  full_stack_lab/tests/audit_call_filter_check.py
M  full_stack_lab/tests/console-ia.test.mjs
M  full_stack_lab/tests/dest_pin_credential_redaction_check.py
M  full_stack_lab/tests/endpoint_auto_activation_check.py
M  full_stack_lab/tests/harness_detect_check.py
M  full_stack_lab/tests/managed_policy_gap_check.py
M  policy/README.md
M  policy/TRACE.md
M  policy/pac/call.rego
M  policy/pac/call_test.rego
M  policy/pac/catalog.rego
M  policy/pac/connect.rego
M  policy/pac/connect_test.rego
M  policy/pac/intake.rego
M  policy/pac/intake_test.rego
M  policy/pac/lib.rego
M  policy/pac/ops.rego
M  policy/pac/ops_test.rego
M  policy/pac/resource.rego
M  policy/pac/resource_test.rego
M  policy/pac/zz_adversarial_test.rego
M  policy/source/classification.json
A  policy/source/renumbering.json
M  policy/source/sheet.json
M  policy/tools/build_catalog.py
M  policy/tools/build_console_catalog.py
M  policy/tools/trace.py
 M research/llm-wiki/analysis/integration-cases.json
 M research/llm-wiki/analysis/requirements.json
 M research/llm-wiki/catalogs/threats.json
M  research/llm-wiki/status/current.md
M  research/llm-wiki/status/decisions-index.md
A  research/llm-wiki/status/reports/2026-11-02-pac-policy-update.md
UU research/llm-wiki/status/reports/README.md
M  research/llm-wiki/status/repository-snapshot.json
M  research/llm-wiki/status/repository-snapshot.md
M  research/llm-wiki/tools/check_trace.py
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `d9198a7b01b52aae208b072e1a68610eadd59f28c22731de14d55b0e4868835b` |
| `full_stack_lab/gateway/app/pac.py` | `b3f0ad2728cd183117416926433af4a7f4b6ac6b922423d0c42fc07fa7c5cbdf` |
| `full_stack_lab/gateway/app/poisoning.py` | `c676b6259619e5f8eababc13dfe0d69bb5a29c42c2ac31abadb737c871c93c06` |
| `full_stack_lab/gateway/app/idp.py` | `3685b2b442fe9f6cbcf7836a366a0e12fc384d64cf15e14228cb3587d7fc55fe` |
| `full_stack_lab/gateway/app/privacy.py` | `592d7649736ef4580cb9a2faad8f1e661eeacfe68e056512e002e10471081f8f` |
| `full_stack_lab/gateway/app/secret_scan.py` | `daeda53835856b9ea603dfe19d377befa38510759eb58572edfb8b0318b7f951` |
| `full_stack_lab/opa/pac15.rego` | `067f288654d530c538d1438b7a8341b8c42684d24dee880d4971d0503ce0c850` |
| `full_stack_lab/opa/decision.rego` | `b6fe334869e38016dd043489b2c3f63207adc5a54fbef199738517b815a9b904` |
| `endpoint-agent/bootstrap.py` | `73d129b5c572ab9290fc0528aff4f7d0a17ddb5ea663f48740453daa7eb1dee9` |
| `endpoint-agent/managed-linux.py` | `f0663c02332d3a9f152e2c29a9d17a2fd44ff410ebfa3ae73ca38991a5b9c412` |
| `endpoint-agent/enforce-linux.py` | `2ce6a711e2e9dfcc47e2b1ca3cebdf9fe6f39171267312ab42c87b1e822e025c` |
