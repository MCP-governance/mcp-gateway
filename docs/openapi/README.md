# OpenAPI 명세

이 디렉터리의 `.json` 파일은 **생성물**입니다. 손으로 고치지 마세요.

```bash
cd full_stack_lab && ./console.sh openapi
```

| 파일 | 서비스 | 포트 |
| --- | --- | --- |
| `gateway.json` | MCP Governance Security Gateway | `127.0.0.1:8080` |
| `agent-service.json` | Agent Service · Console | `127.0.0.1:8000` |

FastAPI가 라우터에서 직접 만들기 때문에 코드와 갈라질 수 없습니다. 손으로 쓴
명세는 합치는 날 반드시 어긋나 있고, 그때 무엇이 맞는지 아무도 모릅니다.

사람이 읽는 명세 — 경계, 인증 주체, 실패의 의미, 합칠 때의 체크리스트 — 는
[../API.md](../API.md)입니다. OpenAPI는 "이 필드가 있다"까지만 말하고
"이 필드를 요청자가 정할 수 없다"는 말하지 않습니다.
