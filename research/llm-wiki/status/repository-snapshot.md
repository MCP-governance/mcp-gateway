# 저장소 코드 스냅샷

확인 시각: 2026-10-31T15:12:50+09:00

HEAD: `5cdee2fd469a59469ca7e28c3a3c48a5fd1ea44b` · 로컬 브랜치: `feat/console-ui`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M .github/actions/compose-cache/index.cjs
 M .github/ci/compose-cache.test.cjs
 M VERSION
 M docs/ai/CONSOLE_UI.md
 M docs/ai/architecture/components.psv
 M endpoint-agent/install-windows.ps1
 M endpoint-agent/install.cmd
 M endpoint-agent/setup.ps1
 M endpoint-agent/tray.ps1
 M endpoint-agent/windows-common.ps1
 M endpoint-agent/windows-oneclick.ps1.in
 M endpoint-agent/windows-trust.ps1
 M endpoint-agent/windows-worker.ps1
 M full_stack_lab/field/console/file.caddy
 M full_stack_lab/field/console/none.caddy
 M full_stack_lab/field/console/tailscale.caddy
 M full_stack_lab/gateway/app/agent_static/console.js
 M full_stack_lab/gateway/app/agent_static/i18n-en.mjs
 M full_stack_lab/tests/console-ia.test.mjs
 M research/collaboration-console/install-autostart.ps1
 M research/collaboration-console/run-console.ps1
 M research/collaboration-console/uninstall-autostart.ps1
 M research/llm-wiki/analysis/field-tls-d124/build-wiki.log
 M research/llm-wiki/analysis/field-tls-d124/capture-status.log
 M research/llm-wiki/analysis/field-tls-d124/check-wiki.log
 M research/llm-wiki/analysis/field-tls-d124/diff-whitespace.log
 M research/llm-wiki/analysis/field-tls-d124/kit-offline-regression.log
 M research/llm-wiki/analysis/field-tls-d124/map-threats.log
 M research/llm-wiki/analysis/field-tls-d124/merge-cached-diff-check.log
 M research/llm-wiki/analysis/field-tls-d124/merge-field-kit.log
 M research/llm-wiki/analysis/field-tls-d124/merge-open-endpoints.log
 M research/llm-wiki/analysis/field-tls-d124/merge-tls-unit.log
 M research/llm-wiki/analysis/field-tls-d124/merge-windows-kit.log
 M research/llm-wiki/analysis/field-tls-d124/open-endpoints.log
 M research/llm-wiki/analysis/field-tls-d124/tls-unit.log
 M research/llm-wiki/analysis/integration-cases.json
 M research/llm-wiki/analysis/kit-macos/checks.log
 M research/llm-wiki/analysis/local-endpoints-1021/binding-profile.apparmor
 M research/llm-wiki/analysis/real-env-20261020/e13/control-claude-cfg-145959.out
 M research/llm-wiki/analysis/real-env-20261020/e13/control-claude-fs-145744.out
 M research/llm-wiki/analysis/real-env-20261020/e13/control-claude-ghidra-145931.out
 M research/llm-wiki/analysis/real-env-20261020/e13/control-claude-git-145809.out
 M research/llm-wiki/analysis/real-env-20261020/e13/control-claude-pw-145902.out
 M research/llm-wiki/analysis/real-env-20261020/e13/control-claude-sqlite-145835.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-cfg-145054.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-fs-144647.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-fsx-145502.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-ghidra-145006.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-ghx-145548.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-git-144754.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-pw-144912.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-pwx-145637.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-claude-sqlite-144834.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-codex-cfg-145413.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-codex-fs-145132.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-codex-ghidra-145341.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-codex-git-145203.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-codex-pw-145309.out
 M research/llm-wiki/analysis/real-env-20261020/e13/managed-codex-sqlite-145238.out
 M research/llm-wiki/analysis/real-env-20261020/t3/t3-context7-run1.log
 M research/llm-wiki/analysis/real-env-20261020/t3/t3-context7.log
 M research/llm-wiki/analysis/requirements.json
 M research/llm-wiki/analysis/user-command-settings/new-tests.log
 M research/llm-wiki/analysis/user-command-settings/wiki-build.log
 M research/llm-wiki/analysis/user-command-settings/wiki-check.log
 M research/llm-wiki/experiments/2026-10-20-latency-ab-context7-pj1-run1-aborted.csv
 M research/llm-wiki/experiments/2026-10-20-latency-ab-context7-pj1.csv
 M research/llm-wiki/experiments/local-tools/desktop/blender-requirements.lock
 M research/llm-wiki/experiments/local-tools/desktop/start-blender.ps1
 M research/llm-wiki/experiments/local-tools/desktop/stop-blender.ps1
 M research/llm-wiki/experiments/local-tools/reverse/run_probe.ps1
 M research/llm-wiki/integrations/lab/openbao/app-read.hcl
 M research/llm-wiki/integrations/lab/openbao/operator.hcl
 M research/llm-wiki/integrations/lab/openbao/requirements.lock
 M research/llm-wiki/integrations/lab/openbao/server.hcl
 M research/llm-wiki/status/reports/2026-10-14-risk-implementation.patch
 M research/llm-wiki/status/reports/2026-10-31-organization-policy-tab.md
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `00c06844f2f79acb503cb409f2fd496f5cb09315a399e2891d91787a48098808` |
| `full_stack_lab/gateway/app/pac.py` | `582d0c1892320cc7f248e75a61d35b915fb363cef946d8955f422077960442f5` |
| `full_stack_lab/gateway/app/poisoning.py` | `c676b6259619e5f8eababc13dfe0d69bb5a29c42c2ac31abadb737c871c93c06` |
| `full_stack_lab/gateway/app/idp.py` | `3685b2b442fe9f6cbcf7836a366a0e12fc384d64cf15e14228cb3587d7fc55fe` |
| `full_stack_lab/gateway/app/privacy.py` | `592d7649736ef4580cb9a2faad8f1e661eeacfe68e056512e002e10471081f8f` |
| `full_stack_lab/gateway/app/secret_scan.py` | `daeda53835856b9ea603dfe19d377befa38510759eb58572edfb8b0318b7f951` |
| `full_stack_lab/opa/pac15.rego` | `067f288654d530c538d1438b7a8341b8c42684d24dee880d4971d0503ce0c850` |
| `full_stack_lab/opa/decision.rego` | `e52e3ea4de50e8ae9c4727079579bf86ba5967aebdb4921875d2ab1d3791c26e` |
| `endpoint-agent/bootstrap.py` | `73d129b5c572ab9290fc0528aff4f7d0a17ddb5ea663f48740453daa7eb1dee9` |
| `endpoint-agent/managed-linux.py` | `9706edd153778f2d83f2c34e188f0773d554e8d115a166d4d1290f8f72692b5c` |
| `endpoint-agent/enforce-linux.py` | `2ce6a711e2e9dfcc47e2b1ca3cebdf9fe6f39171267312ab42c87b1e822e025c` |
