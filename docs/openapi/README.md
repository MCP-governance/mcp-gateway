# OpenAPI 명세

이 디렉터리의 `.json` 파일은 **생성물**입니다. 손으로 고치지 마세요.

이미 기동된 승인 환경에서 생성합니다. 개발 노트북·WSL에 스택을 띄우지 않습니다. 솔루션 기기는 `./console.sh field up`을 쓰며 운영 배포 검증은 GitHub CI 일회용 스택에서 합니다.

```bash
cd full_stack_lab && ./console.sh openapi
```

| 파일 | 서비스 | 포트 |
| --- | --- | --- |
| `gateway.json` | MCP Governance Security Gateway | `127.0.0.1:${GATEWAY_PORT:-8080}` |
| `agent-service.json` | Console · IdP | `127.0.0.1:${CONSOLE_PORT:-8000}` |

명세는 실행 컨테이너의 FastAPI 라우터에서 생성합니다. 체크인한 JSON은 마지막 생성 시점의 스냅숏이므로 현재 소스·배포 이미지와 다를 수 있습니다.
표의 포트는 CI 기본 스택의 loopback 주소입니다. 현장·운영 배포는 Caddy HTTPS를 통해 접근하며 인증·경로 분기는 [FIELD.md](../ai/FIELD.md)를 따릅니다.

현재 코드에는 엔드포인트 자기 조회·요청(`/api/endpoint/self`, `/api/endpoint/self/requests`), 호출 후 훅 수집(`/api/endpoint/tool-events`),
기간·페이지·미열람 경보 조회(`/api/audit/alerts`) 등이 있습니다. JSON에 없으면 해당 배포 판본에서 다시 생성해 비교합니다.
엔드포인트 API의 장치 자격과 직원·관리자 토큰은 서로 다른 권한 경계이며, 스키마 존재가 무인증 사용이나 실기기 통과를 뜻하지 않습니다.

사람이 읽는 명세 — 경계, 인증 주체, 실패의 의미, 합칠 때의 체크리스트 — 는
[../API.md](../API.md)입니다. OpenAPI는 "이 필드가 있다"까지만 말하고
"이 필드를 요청자가 정할 수 없다"는 말하지 않습니다.
