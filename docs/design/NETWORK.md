# 망 경계와 Tailscale

> **v1 시기 문서.** 여기의 설계 근거(왜 그렇게 나눴는가)는 v2에도 유효하지만, 경로·포트·서비스 이름·파일 위치는 v1 기준이다. 현재 구성은 [../ai/ARCHITECTURE.md](../ai/ARCHITECTURE.md), 결정 기록은 [../ai/DECISIONS.md](../ai/DECISIONS.md).

이 문서는 현재 Docker 내부망과 호스트 경계, tailnet을 붙일 때의 검증 조건을 정리합니다.
여기 적힌 tailnet ACL과 조직 신원 연동은 **저장소에 구현되어 있지 않습니다.**

## 1. 지금의 경로 통제는 무엇에 기대고 있는가

Gateway의 효과는 **모든 MCP 도구 호출이 이 강제 경로를 통과할 때만** 성립합니다.
지금 그것을 보장하는 것은 정책 코드가 아니라 다음 두 가지 배치입니다.

| 장치 | 위치 | 성립 범위 |
| --- | --- | --- |
| upstream MCP에 host port가 없음 | [`compose.yaml`](compose.yaml)의 `mock-http-mcp`, 내부 `tools` 망 | Docker 네트워크 안 |
| Console·Gateway·Jaeger가 loopback에만 게시 | `127.0.0.1:8000/8080/16686` | 이 호스트 안 |
| A.I.G 실습 UI가 loopback에만 게시 | `127.0.0.1:8088` | 이 호스트 안 |
| Ollama 추론 서비스가 내부 `model` 망에만 연결 | `ollama`에 `ports` 없음; 다운로드 전용 컨테이너는 별도 | 같은 Compose 프로젝트 안 |
| Agent Service가 `tools` 망에 없음 | `gateway`만 승인된 MCP 리스너에 접근 | 같은 Compose 프로젝트 안 |

Ollama의 로컬 API에는 자체 인증이 없으므로 `model` 망에만 두고 포트를 게시하지 않습니다. 모델 다운로드는 `scanner` 망의 일회성 `ollama-pull`이 맡으며, 추론 서비스에는 `OLLAMA_NO_CLOUD=1`을 적용합니다.

두 번째가 무너지면 [README 13절](README.md)이 "의도적으로 열어두었다"고 적은 무인증
읽기 API — `/api/state`, `/api/effects`, `/api/policy/ledger`, `/api/monitor/summary`,
`/api/supply-chain/coverage` — 가 그대로 노출됩니다. 그 목록은 **loopback 바인딩을
전제로 한 결정**이었습니다.

Compose의 게시 주소는 loopback으로 고정했습니다. `./console.sh`는 기존
`BIND_ADDR`/`AIG_BIND_ADDR` 설정에 다른 주소가 남아 있으면 기동을 거절합니다.
네트워크 분리는 해당 Compose 프로젝트의 컨테이너에 적용됩니다. 다른 호스트나
Docker 외부의 MCP 클라이언트까지 Gateway 통과를 강제하지는 않습니다. 또한
`edge`에 붙은 서비스와 다운로드용 `scanner` 망에는 호스트의 외부 경로가
있으므로 조직 egress 방화벽의 대체물로 취급하면 안 됩니다.

## 2. 이전 two-VM 구성에서 무엇이 잘못됐는가

v1.5에서 삭제한 `setup-two-vm.sh` / `two_vm_demo.py`는 Gateway와 upstream MCP를
두 VM으로 나눠 "upstream 효과"를 대조하는 실습이었습니다. 방향 자체의 오류가
네 군데 있었고, 같은 오류가 tailnet을 붙일 때 그대로 재발할 수 있습니다.

### 2.1 사설 IP를 신원으로 취급했다 (핵심 오진)

`PJ1_SSH=pj1@192.168.85.129`, `PJ2_SSH=pj2@192.168.85.130`처럼 하이퍼바이저 NAT
대역을 하드코딩했습니다. 문제는 주소가 깨지기 쉽다는 것이 아니라 **사설 IP가
신원이 아니라는 것**입니다. 같은 서브넷에 들어온 모든 것이 곧바로 신뢰 대상이
됩니다. "내부망이니까 안전하다"는 전제가 통제를 대신하고 있었습니다.

### 2.2 우회 경로가 네트워크로 막혀 있지 않았다

Gateway는 `http://$PJ2_HOST:9001/mcp`로 upstream을 불렀고, upstream의 인증은
공유 베어러 `MCP_DEMO_UPSTREAM_TOKEN` 하나였습니다. 같은 서브넷의 누구든 그 토큰
하나로 **Gateway를 건너뛰고** upstream을 직접 호출할 수 있습니다. 정책·감사·승인이
모두 정상 동작해도 그 경로 하나가 전부를 무효로 만듭니다.

### 2.3 전송 구간이 평문이었고 상호인증이 없었다

두 VM 사이는 평문 HTTP였습니다. 서버가 자신이 누구인지 증명하지 않고, 클라이언트도
증명하지 않습니다. 토큰만 지나가는 채널이었습니다.

### 2.4 배포가 `ssh + nohup`이었다

`StrictHostKeyChecking=accept-new`로 붙어 `nohup python3 ... &`로 띄우고 PID 파일로
관리했습니다. 재시작·감시·로그 보존이 없고, 호스트 키 신뢰가 첫 접속에 위임됩니다.

## 3. tailnet을 붙인다면 무엇이 정본인가

Tailscale을 "원격 접속 편의"로 쓰면 2.1의 오진을 그대로 반복합니다. 이 프로젝트에서
tailnet을 쓰는 이유는 하나입니다. **Gateway와 upstream을 IP가 아니라 노드 신원으로
묶어, 우회가 애플리케이션의 주장이 아니라 네트워크의 사실이 되게 하는 것.**

### 3.1 ACL이 정본이다

```jsonc
// tailnet 정책 파일 (Tailscale admin)
{
  "tagOwners": {
    "tag:mcp-gateway":  ["group:platform"],
    "tag:mcp-upstream": ["group:platform"],
    "tag:mcp-reviewer": ["group:platform"]
  },
  "acls": [
    // upstream MCP에 접근할 수 있는 것은 Gateway뿐이다.
    // 공유 토큰이 유출돼도 다른 노드는 TCP 연결 자체가 되지 않는다.
    { "action": "accept", "src": ["tag:mcp-gateway"],
      "dst": ["tag:mcp-upstream:9000"] },
    // 심사자는 Console만 본다. upstream에는 닿지 않는다.
    { "action": "accept", "src": ["tag:mcp-reviewer"],
      "dst": ["tag:mcp-gateway:8000"] }
  ],
  "ssh": []
}
```

주소를 쓰지 않습니다. `100.x` 주소조차 하드코딩하지 않고 MagicDNS 이름
(`mcp-upstream`, `mcp-gateway`)을 씁니다. 2.1의 재발을 막는 것은 오버레이 자체가
아니라 **주소가 아닌 태그로 쓴 이 규칙**입니다.

### 3.2 Funnel은 쓰지 않는다

`tailscale funnel`은 공개 인터넷에 노출합니다. 이 실습의 무인증 읽기 API가 그 뒤에
있으면 안 됩니다. 쓰는 것은 tailnet 내부 전용인 `tailscale serve`입니다.

```bash
# Console만 tailnet에 노출한다. Gateway API(8080)는 노출하지 않는다.
tailscale serve --bg --https=443 http://127.0.0.1:8000
```

### 3.3 `tailscale serve`의 신원 헤더는 조건부로만 신뢰할 수 있다

`tailscale serve`는 프록시하면서 `Tailscale-User-Login` / `Tailscale-User-Name`
헤더를 붙입니다. 여기가 이전 시도에서 가장 놓치기 쉬운 지점입니다.

**그 헤더를 애플리케이션이 그대로 신뢰하려면, 애플리케이션에 도달하는 경로가
그 프록시 하나뿐이어야 합니다.** 같은 호스트에서 `curl http://127.0.0.1:8000`으로
직접 치면서 헤더를 손으로 붙이면 위조됩니다. 즉:

- 이 실습처럼 loopback 게시를 유지하고 `tailscale serve`를 Console 앞에 세우거나,
- 별도 배포에서 프록시 이외의 경로를 네트워크 규칙으로 차단해야 합니다.

둘 중 하나를 하지 않은 채 헤더를 신뢰하면, 헤더는 인증이 아니라 요청서입니다.
이것은 이 저장소가 `/tool-call`에 대해 이미 내린 결론과 같습니다 — **신원은
호출자가 정할 수 없다.**

### 3.4 tailnet은 조직 OIDC를 대체하지 않는다

[README 13절](README.md)의 결정은 "운영에서는 조직 OIDC를 연결한 reverse proxy에서
읽기 경로도 보호한다"입니다. tailnet은 그 앞단계인 **망 경계**만 담당합니다.
tailnet 신원은 디바이스·계정 신원이고, 이 실습의 역할(`partner`/`employee`/`admin`)
매핑과 정책 판정은 여전히 Gateway가 합니다. 둘을 같은 것으로 취급하면 디바이스를
가진 사람이 곧 역할을 가진 사람이 됩니다.

## 4. 지금 저장소에 반영된 것

| 항목 | 상태 |
| --- | --- |
| 게시 포트를 loopback으로 고정 (`compose.yaml`, 기업 실습 오버레이) | 반영. 8000/8080/16686/8088 |
| 예전 `BIND_ADDR`/`AIG_BIND_ADDR`의 다른 주소 거절 (`console.sh`) | 반영 |
| `model` 내부망의 Ollama, 분리된 다운로드 컨테이너 | 반영. 로컬 모델 프로필에서만 실행 |
| `tools`에서 Agent Service 분리 | 반영. Gateway만 도구 서버에 연결 |
| tailnet ACL, `tailscale serve`, 신원 헤더 연동 | **미구현.** 이 문서의 3절이 설계 기준 |
| upstream MCP를 별도 호스트로 분리 | **미구현.** 삭제한 two-VM 실습을 tailnet 기준으로 다시 만들 때의 대상 |

## 5. 붙였을 때 무엇을 확인해야 완료인가

기능이 도는 것과 통제가 서는 것은 다릅니다. 아래가 통과 조건입니다.

1. `tag:mcp-reviewer` 노드에서 upstream MCP 포트로 TCP 연결이 **되지 않는다.**
   (토큰을 알아도, 애플리케이션 응답을 받기 전에 연결이 막혀야 한다.)
2. `tag:mcp-gateway` 노드에서만 upstream `tools/call`이 성공한다.
3. tailnet 밖(같은 물리 LAN, 다른 노드)에서 Console·Gateway API에 닿지 않는다.
4. `tailscale serve` 없이 직접 `127.0.0.1:8000`에 붙어 `Tailscale-User-Login`
   헤더를 위조한 요청이 **역할을 얻지 못한다.**
5. `./console.sh test`의 기존 완료 조건이 그대로 통과한다. 망 경계를 바꾸면서
   정책 경로가 조용히 달라지지 않았다는 증거가 필요하다.


---

## 6. v1.7에서 관리 평면으로 들어온 것

egress 허용목록의 **판단**은 이제 정책이 합니다. 여전히 미구현인 것은 **차단**입니다.

| 구성요소 | 위치 | 하는 일 |
| --- | --- | --- |
| `opa/data.json` → `egress.allowed_hosts` | 관리 평면 | 등록 서버가 붙어도 되는 목적지 |
| `MCP-EGRESS-001` (priority 40) | 정책 | 허용 목록 밖 목적지는 실행 전 차단 |
| `MCP-TRANSPORT-001` (priority 35) | 정책 | 평문 원격 endpoint는 권한 판단 이전에 차단 |
| `endpoint_scan_policy` | 관리 평면 | 엔드포인트가 탐색해도 되는 내부 대역 |

**이 목록은 네트워크 장비의 egress 허용목록과 같은 값이어야 합니다.** 둘이 갈라지면
게이트웨이는 막는데 망은 통과시키거나, 그 반대가 됩니다. 앞쪽은 우회로를 남기고
뒤쪽은 장애로 나타납니다.

그리고 이 판단은 **게이트웨이를 지나는 호출**에만 걸립니다. 지나지 않는 호출은
여전히 이 평면이 보지도 막지도 못합니다. 발견은 엔드포인트 평면이 하고
(→ [CONTROL_PLANES.md](CONTROL_PLANES.md) 1절), 차단은 조직의 네트워크 장비 몫입니다.
