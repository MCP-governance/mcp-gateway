# MCP Governance Security Gateway

MCP 도구 호출을 실행 직전에 검증하는 보안 실습입니다. 사용자·에이전트 신원, Registry 계약, 공급망 증적, OPA/Rego 정책, 승인, 감사 기록을 하나의 Gateway 경로에서 대조합니다.

사용자 제공 PDF와 읽기 전용 draw.io 구조도를 반영한 설계·정책·테스트·재설치 절차는 [PDF 반영 설계·재설치·검증 기록](docs/PDF-INTEGRATION-2026-09.md)에 있습니다. 이번 버전은 Presidio의 실제 Analyzer/Anonymizer, 외부 수신처·동일 세션 연쇄 정책, 감사 체인 v5, 후보 정책 재생을 포함합니다.

> **범위:** 합성 계정과 모의 MCP 서버를 쓰는 재현용 랩입니다. 운영망의 SSO, 키 관리, TLS, 호스트 방화벽과 중앙 로그 보존을 대신하지 않습니다.

## 빠른 시작

Docker Compose가 있는 Linux 또는 WSL2에서 새로 복제해 실행합니다.

~~~bash
git clone https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/full_stack_lab
./console.sh up
./console.sh test
./console.sh replay 100
~~~

- Console: <http://127.0.0.1:8000>
- Gateway 상태: <http://127.0.0.1:8080/api/health>
- Jaeger: <http://127.0.0.1:16686>
- 합성 관리자: kkg@bob.local / test-password

처음 실행한 복제본에는 고유한 Docker 프로젝트 이름이 `.env`에 저장됩니다. 새 복제본이 다른 실습의 DB 볼륨을 재사용하지 않게 하기 위한 장치입니다. 기존 `.env`와 데이터는 자동 이전하거나 삭제하지 않습니다.

### Docker 네트워크 주소 풀이 소진된 경우

`all predefined address pools have been fully subnetted`는 Docker가 새 Compose 네트워크에 배정할 주소 대역을 찾지 못했다는 뜻입니다. 각 복제본은 격리를 위해 여러 네트워크를 만들므로, 사용을 마친 **해당 복제본**의 `full_stack_lab`에서 `./console.sh down`을 실행한 뒤 다시 `./console.sh up`을 실행하세요. `down`은 컨테이너와 그 복제본의 네트워크를 내리며 이름 있는 DB 볼륨은 보존합니다. 실행 중인 다른 프로젝트의 네트워크를 일괄 삭제하지 마세요. 여러 스택을 동시에 유지해야 한다면 [Docker 주소 풀 설정](https://docs.docker.com/engine/network/#automatic-subnet-allocation)에서 호스트 환경에 맞는 더 작은 네트워크 크기를 설정하세요. Docker 데몬 설정 변경에는 데몬 재시작이 필요하므로 실행 중인 다른 스택을 확인한 후 적용합니다.

### Docker가 없는 장비에서

네이티브 경로는 Presidio Analyzer/Anonymizer REST 서비스 두 개를 별도로 준비한 개발 장비에서 사용할 수 있습니다. Compose 클린 설치가 기본 검증 경로입니다.

~~~bash
cd mcp-gateway/full_stack_lab
./run-native.sh setup    # PostgreSQL 접속 확인 + OPA 바이너리 + venv 2개
./run-native.sh up       # OPA · mock MCP · Gateway · SSE ingress · Agent Service
./run-native.sh baseline # 이 호스트에 설치된 stdio 서버의 계약을 기준선으로 승인
./run-native.sh test     # Rego + core/agent/runtime acceptance
~~~

PostgreSQL 16+, Python 3.12+, OPA와 별도 Presidio REST 서비스가 필요합니다. URL과 실행 방법은 [재설치 문서](docs/PDF-INTEGRATION-2026-09.md#기존-네이티브-경로)에 있습니다. 컨테이너가 주던 격리는
여기 없으므로 **개발·검증용이고 운영 배치 모델이 아닙니다.** 바인딩은 전부
127.0.0.1이고 와일드카드는 기동 자체를 거부합니다. `baseline`이 따로 있는 이유는
[운영으로 옮기기 전에](#운영으로-옮기기-전에)의 stdio 서버 항목에 적었습니다.
자동으로 돌리지 않는 것이 요점입니다.

## 호출과 증적 흐름

~~~mermaid
flowchart LR
    U["사용자 / MCP 클라이언트"] -->|"합성 로그인 · 요청"| A["Agent Service"]
    A -->|"JWT + 요청에 결속된 Agent Assertion"| G["Security Gateway"]
    G --> C["Registry · 계약"]
    G --> P["OPA / Rego"]
    G --> X["Presidio 입력 검사 · 출력 마스킹"]
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

현재 기준의 성공 조건은 **Rego 76/76**, core acceptance 91, Agent/API acceptance 99,
runtime acceptance 46 — 모두 실패 0입니다. 같은 명령을 [`.github/workflows/verify.yml`](.github/workflows/verify.yml)이 `main`과 모든 `feat/**` 푸시, `main`으로 가는 PR마다 실행합니다.

## 검증하는 통제

| 영역 | 적용 원리 | 확인 방법 |
| --- | --- | --- |
| 사용자·에이전트 신원 | 짧은 수명의 서명된 Agent Assertion을 사용자·에이전트·도구 호출 봉투에 결속 | 위조, 재사용, actor 또는 요청 변경을 401로 차단 |
| 계정 관리대장 | 사용자별 bcrypt 해시와 계정 상태(`active`/`disabled`/`locked`)를 DB에 보관 | 정지된 계정은 **이미 발급된 토큰으로도** 차단 |
| 정책 집행 | OPA/Rego가 역할·자료등급·도구·메서드·입력을 결정론적으로 판정 | 허용/차단과 실제 upstream 호출 여부를 함께 확인 |
| Registry·공급망 | 승인된 카탈로그·스키마·설명·SBOM/취약점 증적을 호출 전에 대조 | drift 또는 정책 위반 시 실행 전 거부 |
| AI 코드 감사 | 격리 워커가 고정 commit을 다시 복제해 mcp-scan 실행. 검증 통과·재감사 주기에 자동 큐잉 | 워커 lease·생존 신호·취소·재시도를 Console에서 확인 |
| 승인·감사 | 승인 재검증, 영수증 복구, 변조 탐지 가능한 감사 연쇄 | 요청·판정·upstream 증적을 Console과 DB에서 추적 |
| 전주기 종료·폐기 | 종료 개시가 곧 차단이고, 회수 대상·증거·판정이 관리대장 행으로 남음 | C1~C4를 계산해 T1/T2/T3 등급을 내고, T3는 위험 수용 없이 종결 불가 |
| 엔드포인트 평면 | 클라이언트 설정과 **내부망 MCP 리스너**를 Registry와 대조 | 강제 경로 밖의 경로를 발견하고 그 사람의 호출 증적을 강화 |
| 장치 자격 분리 | 엔드포인트 에이전트는 사람 계정이 아니라 범위 제한 장치 키로 보고 | 그 키로는 관리자 API가 열리지 않고 남의 엔드포인트도 덮어쓸 수 없음 |
| 목적지·전송 통제 | 등록 서버의 endpoint를 egress 허용목록·전송 보호와 대조 | 허용 목록 밖 목적지와 평문 원격 연결을 실행 전 거부 |
| 계약 재승인 | 검토를 마친 계약 변경을 사유와 함께 승인본으로 승격 | 무엇이 무엇으로 바뀌었는지가 재승인 기록으로 남음 |
| 운영 안전장치 | monitor mode, 요청량 제한, idempotency·세션 경계 | enforce 전환과 과부하·중복 요청 사례 검증 |
| 전송 호환성 | Streamable HTTP, stdio, legacy SSE 경로를 동일 정책 경로로 수렴 | 각 transport의 MCP 호출 acceptance test |

### 정책 추적성

정책 하나하나가 **MCP 보안 통합관리대장 V1.0**의 실제 행을 가리킵니다.

| 필드 | 가리키는 곳 |
| --- | --- |
| `risk_ids` | 위험 목록 `RSK-01` ~ `RSK-32` |
| `requirement_ids` | 보안요구사항 `REQ-01` ~ `REQ-35` |
| `control_ids` | 보안통제 `CTL-01` ~ `CTL-35` |
| `pac_candidate_id` | PaC 연계 시트 `PAC-CAND-01` ~ `PAC-CAND-30` |

v1.6까지의 `RSK-001`/`SR-001`/`CTL-001`은 이 저장소가 임의로 만든 번호였고,
관리대장을 열어도 대응하는 행이 없었습니다. 추적성은 "ID가 적혀 있다"가 아니라
"그 ID가 관리대장에 있다"입니다.

v1.7에서 PaC 후보 5개를 정책으로 구현했습니다.

| 정책 | 통제 | 무엇을 막는가 |
| --- | --- | --- |
| `MCP-TRANSPORT-001` | CTL-24 | 평문 원격 MCP endpoint (RSK-24 중간자) |
| `MCP-EGRESS-001` | CTL-25 | 허용 목록 밖 목적지 (RSK-25 SSRF·내부망 탐색) |
| `P-UNTRUSTED-CONTENT-001/002` | CTL-13 | 인자 안의 비신뢰 지시 (RSK-12 간접 인젝션) |
| `P-ANOMALY-001` | CTL-28 | 반복 인가 거부 (RSK-27 탐색 행위) |
| `MCP-SHADOW-002` | CTL-03·CTL-28 | 망에서 발견된 미등록 리스너 (RSK-01) |

### 333 권한 모델

`333`은 **역할 3 × 데이터 등급 3 × 행위 3 = 27칸 권한 매트릭스**입니다. 강조하는 이유는 이 27칸이 이 실습의 **정책 어휘 전부**이고, 그래서 "빠뜨린 조합"이 존재할 수 없기 때문입니다. 27칸 전체가 기준선으로 고정되어 있고 `acceptance.py`의 `rego-333-cells`가 매번 27칸을 그대로 대조합니다.

| | public | nonimportant | important |
| --- | --- | --- | --- |
| **partner** | `r` | `-` | `-` |
| **employee** | `r` | `rw` | `r` |
| **admin** | `rwx` | `rwx` | `rwx` |

`x`는 외부 전송 또는 고위험 실행입니다. 표에 없는 권한은 기본 차단입니다.

다만 **권한이 있다는 사실만으로 단순 Allow가 되지는 않습니다.** 27칸은 출발점이고, 그 위에 승인(`Approval`)·제한(`Restrict`)·경보(`Alert`)·누적 승격·Registry/공급망/예외/정책 관리대장 판정이 겹칩니다. 자세한 내용은 [full_stack_lab/README.md](full_stack_lab/README.md) 4절입니다.

## 저장소 안내

| 경로 | 용도 |
| --- | --- |
| [full_stack_lab/](full_stack_lab/README.md) | **현재 유일한 통합판.** Agent Service, Gateway, OPA, PostgreSQL 감사, Jaeger, 공급망·AI 코드 감사 |
| [full_stack_lab/CONTROL_PLANES.md](full_stack_lab/CONTROL_PLANES.md) | **엔드포인트단·네트워크단·관리 평면의 분리.** 무엇이 어디에 깔리는가 |
| [full_stack_lab/TERMINATION.md](full_stack_lab/TERMINATION.md) | **전주기의 마지막.** 종료 절차와 C1~C4 / T1~T3 판정 기준 |
| [full_stack_lab/NETWORK.md](full_stack_lab/NETWORK.md) | Docker 내부망·게시 포트 경계와 Tailscale 적용 기준 (tailnet 부분은 미구현, 문서에 명시) |
| [docs/API.md](docs/API.md) | 통합용 API 명세. `./console.sh openapi`가 기계용 명세를 생성 |
| [아키텍처 구조 개선안](docs/architecture/hardening.md) | 공통 실행 경로, 실행 상태, DB 권한과 검사 환경의 단계적 분리 제안. 현재 구현과 후속 검증 기준 구분 |
| [대시보드 UX 개선과 검증](docs/dashboard-ux-review.md) | 공식 디자인 레퍼런스, 실제 콘솔 변경, 다섯 관점의 교차 검토와 검증 범위 |
| [research/](research/README.md) | 레퍼런스 조사와 설계 자료 |

v1.5에서 구버전 실습(`container_lab/`, `library_lab/`, 루트의 two-VM·stdio 최소 예제)을 제거했습니다. 정책 원본이 네 곳으로 갈라져 있으면 어느 것이 정본인지 저장소가 답하지 못합니다. 제거된 코드는 [`2026-09-v1.4-product-console-supply-chain`](https://github.com/MCP-governance/mcp-gateway/tree/2026-09-v1.4-product-console-supply-chain) 태그에 그대로 남아 있습니다.

## 검토·브랜치 원칙

- 하나의 릴리스 후보는 main 대상의 통합 PR 하나로 검토합니다. 직렬 스택 PR은 개별 병합하지 않습니다.
- 독립 작업은 `feat/YYYY-MM-vX.Y-내용`, 통합 후보는 `release/YYYY-MM-vX.Y-내용` 또는 검토용 브랜치를 사용합니다.
- 통합 PR이 기존 작업을 대체하면 기존 PR을 닫고, 포함 관계를 확인한 뒤 해당 원격 작업 브랜치만 삭제합니다.
- 병합된 기준점은 annotated tag로 남깁니다. 현행 태그는 [v0.1부터 v1.4까지](https://github.com/MCP-governance/mcp-gateway/tags) 보존됩니다.

## 운영으로 옮기기 전에

이 저장소는 강제 경로 **안의** 호출만 통제합니다. 합성 로그인은 조직 SSO가 아니고, Compose 내부망은 호스트 방화벽이나 tailnet ACL이 아닙니다. Gateway와 격리 워커의 바깥쪽 네트워크 경로, 외부 모델로 보내는 코드, A.I.G 실습의 높은 컨테이너 권한은 [망 경계 문서](full_stack_lab/NETWORK.md)와 [기업 실습 문서](full_stack_lab/lab/README.md)의 범위대로 별도 검토가 필요합니다.

- GitHub MCP와 외부 제공자 호출은 인증·카탈로그 승인 전까지 의도적으로 비활성입니다.
- AI 코드 감사(mcp-scan)는 저장소 코드를 설정한 LLM endpoint로 보냅니다. 코드 반출이 불가한 조직은 로컬 모델만 연결해야 합니다.
- pip·npm으로 설치하는 stdio 서버는 도구 Schema가 그 서버의 의존성 버전에 따라
  달라집니다. `db/init.sql`에 박힌 승인 해시는 어느 한 빌드의 값이라 다른 호스트에서는
  정당한 설치도 드리프트로 잡힙니다. 그래서 `POST /api/registry/{id}/approve-contract`
  (Console의 '계약 재승인')가 있고, 무엇이 무엇으로 바뀌었는지를 사유와 함께 기록에
  남깁니다. 기동할 때 자동으로 승인하지 않는 것이 요점입니다 — 그러면 계약 고정이라는
  통제 자체가 사라집니다.
- 종료 판정의 모집단(C1)은 제공자가 하위 위임 자격을 고지해야 확정됩니다. 고지가 없으면 판정은 T3이며, 이것은 구현의 한계가 아니라 MCP 인가 명세와 RFC 7009가 만드는 구조적 한계입니다 → [TERMINATION.md](full_stack_lab/TERMINATION.md).

상세 실행 절차, 테스트 시나리오, 구성값과 한계는 [full_stack_lab/README.md](full_stack_lab/README.md)를 기준 문서로 사용합니다.
