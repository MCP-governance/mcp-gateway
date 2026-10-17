# 저장소 코드 스냅샷

확인 시각: 2026-10-17T21:48:46+09:00

HEAD: `9537c0b494a0c4d45c615caa4797674f273d270f` · 로컬 브랜치: `10/17-session-reuse`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M docs/ai/ARCHITECTURE.md
 M docs/ai/DECISIONS.md
 M docs/ai/PAC_MAPPING.md
 M docs/ai/TESTING.md
 M full_stack_lab/gateway/app/core.py
 M full_stack_lab/gateway/app/decommission.py
 M full_stack_lab/gateway/app/experiments.py
 M full_stack_lab/gateway/app/main.py
 M full_stack_lab/gateway/app/mcp_facade.py
 M full_stack_lab/gateway/app/oidc.py
 M full_stack_lab/gateway/app/secret_scan.py
 M full_stack_lab/gateway/app/upstream.py
 M full_stack_lab/opa/policy_ledger.json
 M full_stack_lab/tests/mcp_result_contract_check.py
 M research/llm-wiki/analysis/upstream-session-reuse/README.md
 M research/llm-wiki/catalogs/threats.json
 M research/llm-wiki/status/backlog.md
 M research/llm-wiki/status/repository-snapshot.json
 M research/llm-wiki/status/repository-snapshot.md
 M research/llm-wiki/threats/control-map.md
 M research/llm-wiki/tools/map_threats.py
?? full_stack_lab/gateway/app/destination.py
?? full_stack_lab/gateway/app/upstream_sessions.py
?? full_stack_lab/tests/dest_pin_credential_redaction_check.py
?? full_stack_lab/tests/dest_pin_transport_check.py
?? full_stack_lab/tests/upstream_session_reuse_test.py
?? research/llm-wiki/analysis/dest-pin-credential-redaction/
?? research/llm-wiki/analysis/upstream-session-reuse/code-evidence.json
?? research/llm-wiki/analysis/upstream-session-reuse/review-integration-validation.json
?? research/llm-wiki/analysis/upstream-session-reuse/stage2.md
?? research/llm-wiki/status/reports/2026-10-17-dest-pin-credential-redaction.md
?? research/llm-wiki/status/reports/2026-10-17-upstream-session-reuse-stage2.md
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `80dd8356b0dc0e334423ab284a698a937b61cf57967044108e7154eccce74e7a` |
| `full_stack_lab/gateway/app/pac.py` | `a292041f40d1b972607dc766a9daf641452e46f685a079e76b009694f18ec86f` |
| `full_stack_lab/gateway/app/poisoning.py` | `bb63b3094567f96315bd302c996fe3fbecf0e608f080874ea1a0a19e9857dc96` |
| `full_stack_lab/gateway/app/idp.py` | `4923af424e115db096c688c3d5dc1f0c1285cef63ab1ab4efa39d76375861b5d` |
| `full_stack_lab/gateway/app/privacy.py` | `5eeb5df2cd13c2f59a3d946861f1d62cf5f5de6266f41c7b33c88e7fc8ff36b1` |
| `full_stack_lab/gateway/app/secret_scan.py` | `c6d981869e476d64d8b3e646c307f29d223942333fad84eb7e147a05593750db` |
| `full_stack_lab/opa/pac15.rego` | `067f288654d530c538d1438b7a8341b8c42684d24dee880d4971d0503ce0c850` |
| `full_stack_lab/opa/decision.rego` | `b6fe334869e38016dd043489b2c3f63207adc5a54fbef199738517b815a9b904` |
| `endpoint-agent/bootstrap.py` | `e813b91655123ade200eb06d373ec4b8dafa1124b6f0f6ad75bea18cfc2dd4c3` |
| `endpoint-agent/managed-linux.py` | `58e3a7d66ee7e990bc9f2e9c45797df3e587a47259489ee7a5a8464f2771a14c` |
| `endpoint-agent/enforce-linux.py` | `1252105f172ce246ce60a5fde9cf832e433bb136b21ac68d35c41527e54d84f4` |
