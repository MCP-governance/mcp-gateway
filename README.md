# Tiny MCP policy-gateway demo

MCP 도구 호출 직전에 정책을 적용하는 최소 실습입니다. 기본 stdio 실습과, 역할·자료등급·권한을 적용한 두 VM Gateway 실습을 함께 제공합니다.

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

## 3. 두 VM 원격 Gateway 데모

계획서의 P1 실행 전 차단 흐름을 두 VM에서 재현합니다.

- `pj1 (192.168.85.129)`: Gateway와 demo client
- `pj2 (192.168.85.130)`: mock MCP server
- 판정: 사용자 역할 × 자료 등급 × `rwx` 권한
- 차단: 권한 없는 외부 전송, 미등록 Tool, MCP 헤더/본문 불일치

WSL에서 저장소를 clone한 뒤 다음 한 번만 실행합니다. SSH 키가 없으면 SSH/SCP가 비밀번호를 요청합니다.

```bash
bash setup-two-vm.sh
```

호스트를 바꾸려면 환경변수로 지정합니다.

```bash
PJ1_SSH=user@10.0.0.11 PJ2_SSH=user@10.0.0.12 bash setup-two-vm.sh
```

Gateway 감사 로그는 `pj1:/tmp/mcp-demo/gateway.jsonl`, 실제 upstream 효과는 `pj2:/tmp/mcp-demo/effects.jsonl`에 기록됩니다.

### 브라우저 GUI로 실습하기

`bash setup-two-vm.sh`가 끝난 뒤 브라우저에서 아래 주소를 엽니다.

```text
http://192.168.85.129:8080/
```

화면에서 역할·도구·자료를 고르고 요청을 보내면, 즉시 통과/차단 결과가 표시됩니다. 아래 두 로그도 3초마다 새로고침됩니다.

- `pj1 Gateway 감사 로그`: 역할, 자료 등급, 필요한 `rwx`, `upstream_called` 확인
- `pj2 upstream 실제 효과`: 허용된 쓰기·외부 전송만 기록되는지 확인

### 현재 쓰는 도구와 라이브러리

| 구분 | 사용 중 | 쓰는 이유 |
| --- | --- | --- |
| Gateway·mock MCP·GUI | Python 3 표준 라이브러리 (`http.server`, `json`, `urllib`, `hashlib`, `argparse`) | 설치 없이 동일한 코드를 두 VM에서 실행 |
| 화면 | 순수 HTML·CSS·JavaScript | Gateway가 `/`에서 직접 제공, 별도 Node.js/React 없음 |
| VM 배포 | WSL의 `ssh`, `scp`, `curl`, Bash | 코드 복사·기동·상태 확인 |
| 기본 실습 | Docker Compose + Python 3.12 Alpine | 기존 stdio 예제를 한 번에 실행 |
| 형상관리 | Git·GitHub | 실습 단계별 브랜치 보존 |

기본 stdio·두 VM 단계에는 MCP SDK, OPA/Rego, Casbin, 데이터베이스, OpenTelemetry를 **설치하지 않았습니다**. 반면 `container_lab/` 확장 단계는 OPA/Rego를 실제 정책 결정점으로 사용합니다.

### 이번에 추가한 룰셋

`two_vm_demo.py` 안의 `ROLE_PERMISSIONS`가 이번 실습의 읽기 쉬운 정책 원본입니다. 이 단계에서는 외부 정책 엔진을 붙이지 않고 한 곳에서만 판정합니다.

| 역할 | 공개 (`public`) | 비중요 (`nonimportant`) | 중요 (`important`) |
| --- | --- | --- | --- |
| 고객 (`customer`) | `r` | - | - |
| 직원 (`employee`) | `r` | `rw` | `r` |
| 관리자 (`admin`) | `rwx` | `rwx` | `rwx` |

- `r`: `read_document`
- `w`: `write_document`
- `x`: `send_external` (외부 전송이라는 실행 권한)

자료 등급은 요청자가 보내는 값이 아니라 `document_id`에 대해 Gateway가 가진 분류표로 결정합니다. 따라서 직원이 중요 자료를 읽을 수 있어도 `x`가 없으면 외부 전송은 upstream에 닿기 전에 차단됩니다. 클라이언트는 아래 7개 사례를 자동 실행합니다: 고객의 공개 읽기 허용, 직원의 비중요 쓰기 허용, 직원의 중요자료 전송 차단, 고객의 중요자료 읽기 차단, 관리자의 중요자료 전송 허용, 미등록 도구 차단, 헤더/본문 불일치 차단.

### 이 단계에서 VM을 더 늘리지 않은 이유

`pj1`은 client·Gateway·감사 로그, `pj2`는 mock MCP server와 실제 효과 로그 역할을 맡습니다. 이 두 증적을 비교하면 “차단된 호출은 upstream 효과가 없다”를 확인할 수 있으므로, 현재 학습 목표에는 세 번째 VM이 필요하지 않습니다.

실무에서는 정책 저장소/감사 수집기 분리, Gateway 우회 방지를 위한 네트워크 정책, 스키마 변경 감지, 중앙 인증을 추가합니다. 다음 학습 단계에서 정책이 많아지면 이 코드의 `ROLE_PERMISSIONS`만 OPA/Rego 또는 Casbin 같은 정책 엔진으로 교체하는 편이 좋습니다. P2 수준의 직접 egress 차단을 실제로 입증하려면 그때 별도 네트워크 격리 VM 또는 컨테이너 네임스페이스를 고려하면 됩니다.

## 4. 라이브러리·공개 MCP 통합 실습 브랜치

`library_lab/`은 별도 브랜치에서 FastAPI, Pydantic, PyCasbin, OpenTelemetry와 공개 `mcp-server-time`을 실제로 연결한 확장판입니다. 자세한 설치·호환성·GUI 주소는 [library_lab/README.md](library_lab/README.md)를 참고합니다.

## 5. 컨테이너·LiteLLM·OPA 통합 실습 브랜치

`container_lab/`은 팀원의 Agent → Gateway → Mock MCP Docker 네트워크 구조와 이 저장소의 역할·자료등급 정책, 실행 증적 방식을 합친 확장판입니다. LiteLLM은 도구 호출을 **제안**하는 모델 경로만 담당하고, Gateway와 OPA가 실제 허용·차단을 결정합니다. AI-Infra-Guard의 MCP-Scan 접근을 축소 적용해 승인된 도구 목록·입력 스키마·도구 설명 변조를 사전 확인한 뒤 Rego에 전달합니다. 실행법과 검증 명령은 [container_lab/README.md](container_lab/README.md)를 참고합니다.

## 6. 전체 MCP Security Gateway 실습

`full_stack_lab/`은 확정한 333 `rwx` Rego 정책, 다섯 판정, Registry/catalog drift 차단, 승인 재검증, PostgreSQL 감사, OpenTelemetry/Jaeger, 공급망 SBOM·취약점 증적을 한 Compose에 묶은 현재 통합판입니다. Streamable HTTP·stdio·legacy SSE를 실제 MCP 호출로 검증하며, GitHub MCP는 인증 및 catalog 승인 전까지 의도적으로 비활성화합니다.

```bash
cd full_stack_lab
./demo.sh
```

Dashboard는 <http://localhost:8080>에서 열립니다. 실습 순서, 예상 결과, 공급망 스캔과 정확한 증명 범위는 [full_stack_lab/README.md](full_stack_lab/README.md)를 참고합니다.
