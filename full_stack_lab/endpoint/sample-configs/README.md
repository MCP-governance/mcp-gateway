# 합성 엔드포인트 설정

엔드포인트 평면이 무엇을 보는지 시연하기 위한 **합성** 클라이언트 설정입니다.
실제 PC의 설정이 아니며, 여기 적힌 주소 중 사내 CRM 항목은 존재하지 않습니다.

`./console.sh endpoint`를 실행하면 에이전트가 이 디렉터리를 읽고 Registry와
대조해 다음과 같이 분류합니다.

| 설정 항목 | 분류 | 왜 |
| --- | --- | --- |
| `합성 문서 MCP` (`mock-http-mcp:9000`) | `registered` | Registry의 `mock-http`와 대조됨 |
| `time` (`python -m mcp_server_time`) | `registered` | Registry의 `mock-stdio`와 대조됨 |
| `github` | `registered` 또는 `retired-residue` | 이 서버의 종료 케이스를 열면 잔존으로 바뀝니다 |
| `local-notes` | `shadow` | 어느 등록 서버와도 대조되지 않음 |
| `internal-crm` | `shadow` | 위와 같음 |

실제 PC의 설정을 보려면 `.env`에 경로를 주고 다시 올립니다. 마운트는 읽기
전용이고 에이전트에는 쓰기 경로가 없습니다.

```dotenv
ENDPOINT_CONFIG_SOURCE=/mnt/c/Users/<계정>/AppData/Roaming/Claude
```

에이전트는 서버 이름·전송·주소만 보냅니다. `env`와 `headers`는 읽는 즉시
버립니다. 사람들의 API 키가 인벤토리 테이블에 쌓이면 그 테이블이 조직에서 가장
위험한 표가 됩니다.
