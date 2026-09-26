# 검토 근거 목록

- 저장소: https://github.com/MCP-governance/mcp-gateway
- 기준 커밋: `45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967`
- 확인일: 2026-09-24
- 소스 차이: 분석 시 기준 커밋과 일치
- 방법: 정적 소스 및 배치 문서 대조. 취약점 스캔이나 운영 효과 시험을 수행하지 않음
- collection SHA-256: `001fc42f109171185422ece33599e86733a63f7facbd87813c94cf04f529ff4f`
- 계산 방법: 아래 파일을 경로 오름차순으로 정렬한 `[{path,sha256},...]`를 JSON 키 정렬 및 공백 없는 UTF-8로 직렬화한 뒤 SHA-256 계산
- 선행 대화나 비공개 문서를 근거 파일로 포함하지 않음

| 파일 | SHA-256 |
| --- | --- |
| [.github/workflows/verify.yml](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/.github/workflows/verify.yml) | `b56486adff5c8c0daecceb4a10b7d14ee92dc29093a55c655bcb44ea3e70f033` |
| [docs/PDF-INTEGRATION-2026-09.md](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/docs/PDF-INTEGRATION-2026-09.md) | `ca31f11350c0f3c7e7b9331171baad17ac6234d91b23e4238694ad1263fd9209` |
| [docs/runtime-hardening.md](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/docs/runtime-hardening.md) | `3f9edfcae0909cfe28d19c47688797872a0fedb550ac291f5fd69c6cbeceebbd` |
| [full_stack_lab/CONTROL_PLANES.md](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/CONTROL_PLANES.md) | `91845d31e1ef51d7f17c3ad20367712043417629af8e8acb3ca9aa453a7c741a` |
| [full_stack_lab/NETWORK.md](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/NETWORK.md) | `d69be01510604cf374c5a36d157fe2e6f4fb2d3e32a8ee46b7482f26bd493c5b` |
| [full_stack_lab/compose.corporate-lab.yaml](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/compose.corporate-lab.yaml) | `a8d2e747f31e60d904bd51402a60aab1947c5c35765ead748ab4a801c6f53ab6` |
| [full_stack_lab/compose.local-llm.yaml](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/compose.local-llm.yaml) | `78854f7c5899b08afb0ff3a2dbbcabed89c59d12aebd74fdcab4903f37f29833` |
| [full_stack_lab/compose.yaml](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/compose.yaml) | `75224d4d6413bef1f2b4a8a65bea1c49d301224d8595b81d8ca876bd134e87be` |
| [full_stack_lab/gateway/app/agent_gateway.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/agent_gateway.py) | `bf1ca71ba86f8918851983fd0a243b455c27b507066ce0c1dcd8737471fc45e3` |
| [full_stack_lab/gateway/app/agent_service.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/agent_service.py) | `d57f41b043a303735fc9355fd6a2c1fd304b560540d47decd37461d20387692d` |
| [full_stack_lab/gateway/app/agent_tables.sql](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/agent_tables.sql) | `c6094ea5b22ad3275a89b1b32b23e3e0e973f83d99fd6c67f93b624b24b10fdd` |
| [full_stack_lab/gateway/app/core.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/core.py) | `72e38d8174f8bc639ba30415f6f195ca995f9e3335ca58c50ad35cd2a008d46d` |
| [full_stack_lab/gateway/app/db.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/db.py) | `0ecca90094806ea07d3f6b9a780a5e9cfdaf64173c2024a83d8d818096c3f45c` |
| [full_stack_lab/gateway/app/main.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/main.py) | `27400dd35e989cc5ac3bf503648c3084806d9c5a2a80721d41d1c98c84989589` |
| [full_stack_lab/gateway/app/mcp_facade.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/mcp_facade.py) | `0991be2f62593780274dc442bd0833c2c88528351364342dd35a10d8815fc3ec` |
| [full_stack_lab/gateway/app/replay.py](https://github.com/MCP-governance/mcp-gateway/blob/45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967/full_stack_lab/gateway/app/replay.py) | `9e401235c27e1953e25c8f30ddc16a91be1959947eb8c4a450e98b120eb8e761` |

상세 제안의 E1~E6는 독자의 편의를 위한 근거 묶음이다. 실제 무결성 목록은 위의 16개 파일이다. 제안에 인용한 행 번호는 기준 커밋에 한정된다.

외부 용어와 기능 참고: [MCP 2025-11-25 Architecture](https://modelcontextprotocol.io/specification/2025-11-25/architecture), [OPA Bundles](https://www.openpolicyagent.org/docs/management-bundles), [PostgreSQL Privileges](https://www.postgresql.org/docs/current/ddl-priv.html). 외부 문서는 위 소스 해시 집합에 포함하지 않았다.
