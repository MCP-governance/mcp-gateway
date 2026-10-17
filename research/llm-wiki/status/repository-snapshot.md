# 저장소 코드 스냅샷

확인 시각: 2026-10-18T05:05:34+09:00

HEAD: `fd904c24250b6029061283bb8a57fa4efe0b5b17` · 로컬 브랜치: `10/18-selective-siem`

로컬 코드 상태입니다. 배포·활성화·실기기 검증과 실험 성공을 증명하지 않습니다.

## 워킹 트리

```text
M docs/ai/CONSOLE_UI.md
 M docs/ai/DATA_MODEL.md
 M docs/ai/DECISIONS.md
 M docs/ai/OPS_RESPONSE.md
 M docs/ai/POLICY.md
 M full_stack_lab/compose.yaml
 M full_stack_lab/console.sh
 M full_stack_lab/gateway/app/agent_service.py
 M full_stack_lab/gateway/app/agent_static/console.js
 M full_stack_lab/gateway/app/core.py
 M full_stack_lab/gateway/app/dispatch.py
 M full_stack_lab/gateway/app/endpoint_plane.py
 M full_stack_lab/gateway/app/main.py
 M full_stack_lab/gateway/app/mcp_facade.py
 M full_stack_lab/gateway/app/ops_response.py
 M full_stack_lab/gateway/app/ops_tables.sql
 M full_stack_lab/tests/catalog_refresh_check.py
 M full_stack_lab/tests/dispatch_intent_pg_check.py
 M full_stack_lab/tests/termination_lab_support.py
 M research/llm-wiki/analysis/feature-spec-2026-10-17/README.md
 M research/llm-wiki/catalogs/threats.json
 M research/llm-wiki/status/backlog.md
 M research/llm-wiki/status/current.md
 M research/llm-wiki/status/repository-snapshot.json
 M research/llm-wiki/status/repository-snapshot.md
?? full_stack_lab/gateway/app/selective.py
?? full_stack_lab/gateway/app/siem.py
?? full_stack_lab/gateway/app/siem_tables.sql
?? full_stack_lab/siem-secrets/
?? full_stack_lab/tests/selective_restriction_siem_check.py
?? research/llm-wiki/analysis/selective-restriction-siem/
?? research/llm-wiki/status/reports/2026-10-17-selective-restriction-siem.md
```

## 주요 파일 바이트

| 파일 | SHA-256 |
| --- | --- |
| `full_stack_lab/gateway/app/core.py` | `eff5944fbd29a06e5ba174d671f8f954cfbe33e6d95b35fbc5ef10595375c439` |
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
