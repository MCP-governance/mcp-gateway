# MCP Governance Security Gateway

MCP 도구 호출을 실행 직전에 검증하는 보안 실습입니다. 사용자·에이전트 신원, Registry 계약, 공급망 증적, OPA/Rego 정책, 승인, 감사 기록을 하나의 Gateway 경로에서 대조합니다.

> **범위:** 합성 계정과 모의 MCP 서버를 쓰는 재현용 랩입니다. 운영망의 SSO, 키 관리, TLS, 호스트 방화벽과 중앙 로그 보존을 대신하지 않습니다.

## 빠른 시작

Docker Compose가 있는 Linux 또는 WSL2에서 새로 복제해 실행합니다.

~~~bash
git clone https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/full_stack_lab
./console.sh up
./console.sh test
~~~

- Console: <http://127.0.0.1:8000>
- Gateway 상태: <http://127.0.0.1:8080/api/health>
- Jaeger: <http://127.0.0.1:16686>
- 합성 관리자: kkg@bob.local / test-password

처음 실행한 복제본에는 고유한 Docker 프로젝트 이름이 `.env`에 저장됩니다. 새 복제본이 다른 실습의 DB 볼륨을 재사용하지 않게 하기 위한 장치입니다. 기존 `.env`와 데이터는 자동 이전하거나 삭제하지 않습니다.

## 호출과 증적 흐름

~~~mermaid
flowchart LR
    U["사용자 / MCP 클라이언트"] -->|"합성 로그인 · 요청"| A["Agent Service"]
    A -->|"JWT + 요청에 결속된 Agent Assertion"| G["Security Gateway"]
    G --> C["Registry · 계약"]
    G --> P["OPA / Rego"]
    G --> D["PostgreSQL 감사 연쇄"]
    G -->|"허용·승인된 호출만"| M["등록 MCP 서버"]
    M --> E["독립 upstream 효과 로그"]
    W["격리 공급망 워커"] -->|"Trivy · Syft · Semgrep · A.I.G mcp-scan"| D
    L["로컬 Ollama 또는 명시한 모델 API"] -.->|도구 제안 / 참고용 검사| A
    L -.->|참고용 검사| W
~~~

모델은 도구를 **제안**합니다. 실행 권한은 Gateway의 계약 확인과 OPA 정책이 결정합니다. 차단 증거는 정책 응답만이 아니라 upstream 효과의 변화 여부로 대조합니다. 응답이 유실되면 실행 여부를 **미확인**으로 기록합니다.

## 내부망 경계

~~~mermaid
flowchart LR
    Browser["호스트 브라우저"] -->|"127.0.0.1:8000"| Console["Console / Agent"]
    Browser -->|"127.0.0.1:8080"| Gateway["Gateway"]
    Browser -->|"127.0.0.1:16686"| Jaeger["Jaeger"]
    Console -->|"agent 내부망"| Gateway
    Gateway -->|"tools 내부망"| MCP["Mock MCP · 호스트 포트 없음"]
    Gateway -->|"policy 내부망"| OPA["OPA"]
    Gateway -->|"data 내부망"| DB["PostgreSQL"]
    Worker["검증 워커"] -->|"scanner 다운로드망"| Source["고정 commit · 취약점 DB"]
    Worker -->|"model 내부망"| Ollama["Ollama · 호스트 포트 없음"]
    Console -->|"model 내부망"| Ollama
    Downloader["일회성 모델 다운로드"] -->|"scanner 다운로드망"| Source
~~~

| 경계 | 실제 설정 | 확인 |
| --- | --- | --- |
| 외부에 보이는 포트 | 8000·8080·16686, A.I.G 실습의 8088 모두 127.0.0.1에만 게시 | Compose 설정과 실행 중 바인딩 검사 |
| 도구 서버 | tools 내부망, 호스트 포트 없음 | Agent Service에서는 이름 확인 불가, Gateway에서는 확인 가능 |
| 정책·데이터 | policy/data 내부망 | 호스트 포트 없음 |
| 로컬 추론 | model 내부망, Ollama Cloud 비활성 | 모델 다운로드 컨테이너만 일시적으로 scanner 망 사용 |
| 원격 접근 | Console 앞의 Tailscale Serve와 별도 앱 인증 | tailnet ACL과 운영 환경 차단은 별도 검증 필요 |

BIND_ADDR로 LAN이나 전체 인터페이스에 직접 게시하는 설정은 받지 않습니다. Tailscale을 쓸 때는 [망 경계 문서](full_stack_lab/NETWORK.md)의 Serve 경로로 **Console만** 전달합니다. 이 랩의 Docker 망 분리는 다른 MCP 클라이언트가 Gateway를 우회하는 경로까지 강제 차단하지 않습니다. 그 차단은 엔드포인트 정책과 조직 네트워크에서 검증해야 합니다.

## 로컬 LLM과 오픈소스 검사기

~~~bash
cd full_stack_lab
./console.sh local-llm
~~~

첫 실행은 [Ollama](https://github.com/ollama/ollama)의 고정 버전 이미지와 기본 qwen2.5:0.5b 모델을 내려받습니다. 이후 Ollama는 내부 model 망에서만 추론하고 호스트 포트를 열지 않습니다. Agent Service는 OpenAI 호환 API로 도구 제안을 받고, Tencent [AI-Infra-Guard](https://github.com/Tencent/AI-Infra-Guard)의 Web·Agent·API Checker와 mcp-scan은 같은 로컬 모델을 사용할 수 있습니다. A.I.G는 **실습 오버레이**로 Gateway 컨테이너에서 실행하며 브라우저 UI는 <http://127.0.0.1:8088>입니다.

0.5B 모델의 코드 감사 결과는 `advisory`(참고용)로 저장하며 자동 차단 근거에 넣지 않습니다. 로컬 프로필의 무거운 재감사는 Console에서 직접 요청합니다. test-double 배선 결과도 차단 근거에 넣지 않습니다. 두 모드의 새 보고서는 기존 live 보고서를 지우지 않습니다. 모델을 바꾸려면 `.env`의 `LOCAL_LLM_MODEL`을 지정하고 다시 실행합니다. 모델 품질과 GPU 사용 여부는 배치 환경에서 따로 검증해야 합니다.

- 기본 검증: ./console.sh test (결정론적 모의 모델)
- 기업 내부망 배선 실습: ./console.sh corporate-lab (test-double 결과)
- 외부 또는 조직 제공 모델: ./console.sh live-lab (코드·MCP 응답의 전송 경계 확인 필요)
- 로컬 모델 중지: ./console.sh local-stop (DB와 모델 데이터 유지)

A.I.G 외에도 워커는 [Trivy](https://github.com/aquasecurity/trivy), [Syft](https://github.com/anchore/syft), [Semgrep](https://github.com/semgrep/semgrep)을 실행합니다. 각 도구의 보고서를 승인된 서버의 고정 source_ref에 귀속하고, 실제 설치·실행 없이 취약 버전 메타데이터를 검사할 수 있습니다.

## Console과 검증

Console은 운영 현황, 도입, 검증, 위험, 엔드포인트, 종료, 정책, 신원, 도구 실행, 감사를 역할별로 보여줍니다. 작은 화면에서도 목록과 조작 버튼이 읽히도록 반응형 배치를 적용했고, [Noto Sans KR](full_stack_lab/gateway/app/agent_static/fonts/OFL.txt)을 자체 제공해 폐쇄망에서도 폰트 CDN이 필요 없습니다.

~~~bash
./console.sh status
./console.sh test
./console.sh scan
~~~

검증은 Rego 정책, Gateway/Agent/API/실행 경계, 계약 드리프트, OPA 장애 시 기본 차단, 실제 포트 바인딩과 도구망 분리를 확인합니다. 자세한 시나리오와 한계는 [통합판 설명](full_stack_lab/README.md), [실행 경계](docs/runtime-hardening.md), [관리 평면](full_stack_lab/CONTROL_PLANES.md), [종료 절차](full_stack_lab/TERMINATION.md)에 있습니다.

## 운영으로 옮기기 전에

이 저장소는 강제 경로 **안의** 호출만 통제합니다. 합성 로그인은 조직 SSO가 아니고, Compose 내부망은 호스트 방화벽이나 tailnet ACL이 아닙니다. Gateway와 격리 워커의 바깥쪽 네트워크 경로, 외부 모델로 보내는 코드, A.I.G 실습의 높은 컨테이너 권한은 [망 경계 문서](full_stack_lab/NETWORK.md)와 [기업 실습 문서](full_stack_lab/lab/README.md)의 범위대로 별도 검토가 필요합니다.
