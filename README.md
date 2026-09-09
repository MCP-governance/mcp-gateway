# Tiny MCP policy-gateway demo

MCP 도구 호출 직전에 단 하나의 읽기 전용 룰셋을 적용하는 최소 실습입니다. `read_document`는 통과하고, 쓰기 성격의 `delete_document`는 실행 전에 차단됩니다.

## 1. 자동 실습

WSL Kali 터미널에서 실행합니다.

```bash
cd ~/mcp-gateway
docker compose run --build --rm demo
```

다음 문구가 나오면 성공입니다.

```text
PASS: read_document allowed; delete_document blocked
```

컨테이너 안의 `demo.py`는 MCP 흐름인 `initialize` → `tools/list` → `tools/call`을 실제로 보냅니다. 마지막 두 호출의 결과는 다음과 같습니다.

| 호출 | 룰셋 판단 | 결과 |
| --- | --- | --- |
| `read_document(id=demo-1)` | 허용 목록에 있음 | `ALLOWED: document demo-1` |
| `delete_document(id=demo-1)` | 허용 목록에 없음 | `BLOCKED by read-only ruleset` |

## 2. 직접 호출해 보기

아래 명령으로 서버를 연 뒤, JSON 한 줄씩 붙여 넣습니다.

```bash
docker compose run --rm -i demo python server.py
```

먼저 초기화합니다.

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26"}}
```

허용되는 읽기 호출입니다.

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"read_document","arguments":{"id":"demo-1"}}}
```

차단되는 쓰기 호출입니다.

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"delete_document","arguments":{"id":"demo-1"}}}
```

## 이 실습에서 확인할 의의

1. **통제 시점**: 모델이 도구를 고른 뒤라도, 실제 작업이 시작되기 전 `tools/call` 지점에서 정책으로 중단할 수 있습니다. 차단은 단순 경고가 아니라 호출 결과 `isError: true`로 귀결됩니다.
2. **최소 권한**: 기본 허용 목록을 읽기 도구 하나로 좁히면, 프롬프트 인젝션이나 모델의 실수로 쓰기 도구가 선택돼도 그 호출은 통과하지 못합니다.
3. **Gateway의 조건**: 이 효과는 모든 도구 호출이 이 검사 지점을 반드시 거칠 때만 성립합니다. MCP 클라이언트가 다른 서버·로컬 도구를 직접 호출할 수 있으면 이 룰셋은 그것을 막지 못합니다.

## 일부러 넣지 않은 것

이 코드는 개념 검증용 stdio 서버입니다. 사용자·에이전트 인증, 도구 스키마/설명 변경 검증, 원격 MCP 프록시, 감사 로그, 네트워크 차단은 포함하지 않았습니다. 실제 Gateway에서는 승인된 도구 목록뿐 아니라 호출자 권한, 입력값, 변경 이력, 감사 증적까지 같은 강제 경로에서 확인해야 합니다.

가장 작은 확장 실험은 `server.py`의 `ALLOWED_TOOLS`를 `{"read_document", "delete_document"}`로 바꾼 뒤 다시 실행하는 것입니다. 차단 결과가 허용으로 바뀌는 것을 통해, 정책 설정 한 줄이 실행 권한을 결정한다는 점을 확인할 수 있습니다.
