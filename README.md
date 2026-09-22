# MCP Governance Security Gateway

MCP와 AI Agent의 도구 호출을 **실행 전에** 하나의 강제 경로에서 인증·정책·승인·카탈로그·공급망·감사로 검증하는 보안 실습 저장소입니다.

> 학습·검증용 레퍼런스입니다. 운영 환경에는 조직의 SSO, 키 관리, 네트워크 격리와 별도 관제 체계를 추가해야 합니다.

## 가장 빠른 시작

Docker Compose가 가능한 WSL2/Linux 환경에서 실행합니다.

~~~bash
git clone https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/full_stack_lab
./console.sh
~~~

### Docker가 없는 장비에서

Docker Desktop이 없는 노트북이나 WSL2 한 대에서도 같은 스택을 띄울 수 있습니다.
"환경이 없어서 검증을 못 했다"가 나오지 않게 하는 경로입니다.

~~~bash
cd mcp-gateway/full_stack_lab
./run-native.sh setup    # PostgreSQL 접속 확인 + OPA 바이너리 + venv 2개
./run-native.sh up       # OPA · mock MCP · Gateway · SSE ingress · Agent Service
./run-native.sh baseline # 이 호스트에 설치된 stdio 서버의 계약을 기준선으로 승인
./run-native.sh test     # Rego + core/agent/runtime acceptance
~~~

필요한 것은 PostgreSQL 16+ 한 대와 Python 3.12+뿐입니다. 컨테이너가 주던 격리는
여기 없으므로 **개발·검증용이고 운영 배치 모델이 아닙니다.** 바인딩은 전부
127.0.0.1이고 와일드카드는 기동 자체를 거부합니다.

`baseline`이 따로 있는 이유는 3절에 적었습니다. 자동으로 돌리지 않는 것이 요점입니다.

- MCP Governance Console: <http://localhost:8000>
- Jaeger: <http://localhost:16686>
- 전체 검증: `./console.sh test`
- 공급망 증적 생성: `./console.sh scan`
- 기업 내부망 + Tencent A.I.G 시나리오: `./console.sh reset && ./console.sh corporate-lab`
- 실제 모델 API 테스트베드: Windows에서 `full_stack_lab/start-live-lab.cmd` 더블클릭 또는 WSL에서 `./console.sh live-lab`

현재 기준의 성공 조건은 **Rego 76/76**, core acceptance 91, Agent/API acceptance 99,
runtime acceptance 44 — 모두 실패 0입니다. 같은 명령을 [`.github/workflows/verify.yml`](.github/workflows/verify.yml)이 `main`과 모든 `feat/**` 푸시, `main`으로 가는 PR마다 실행합니다.

### 실행 경계 보강

- OPA 응답의 결정값·필수 필드·제한조건을 검증합니다. 미정의 결정이나 실행할 수 없는 제한은 관찰 모드에서도 차단합니다.
- 정지·잠금 계정은 stdio와 대기 승인에서도 실행할 수 없습니다. 승인 유효기간은 실제 `tools/call` 전달 직전에 다시 확인합니다.
- 감사 기록과 Console은 **실행 확인 / 미실행 / 실행 여부 미확인**을 구분합니다. 응답 유실을 차단 성공으로 세지 않으며, 종료 이후 미확인 호출이 있으면 T3로 판정합니다.
- `./console.sh test`가 위 경계를 검증하는 `runtime_acceptance`도 실행합니다. 재현 방법과 검증 범위는 [실행 경계 검증 기록](docs/runtime-hardening.md)에 정리했습니다.

### 기업 내부망 A.I.G 실습

`full_stack_lab/compose.corporate-lab.yaml`은 Tencent Zhuque Lab의 원본 A.I.G Web·Agent·API Checker를 **Gateway 컨테이너 하나에서** 실행합니다. 별도 A.I.G 전용 컨테이너는 만들지 않으며 기존 데이터 볼륨은 이어 씁니다. 배선 검증용 모의 모델은 기존 공용 `llm-stub`을 재사용합니다. A.I.G UI는 `127.0.0.1:8088`에만 열고, 취약 버전은 패키지 설치 없이 메타데이터 SCA 대상으로만 사용합니다. 통합으로 Gateway가 A.I.G의 스캔 망과 Chromium 권한을 공유하므로 운영망 격리 모델은 아닙니다. 실제 절차와 증적 경계는 [기업 내부망 실습 문서](full_stack_lab/lab/README.md)를 따릅니다.

## 통제 흐름

~~~mermaid
flowchart LR
    U[사용자] --> A[Agent Service]
    A -->|JWT + 60초 Agent Assertion| G[Security Gateway]
    G --> R[Registry / Catalog]
    G --> P[OPA / Rego]
    G --> S[공급망 증적]
    G --> M[승인·감사·증적]
    P -->|허용된 호출만| T[Mock MCP / Upstream]
    W[격리 검증 워커] --> S
~~~

Gateway는 사용자 신원, 에이전트 위임 신원, 도구·메서드·인자, 카탈로그와 공급망 상태, 승인 및 용량 조건을 확인한 뒤에만 upstream 호출을 수행합니다.

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

### 합성 계정

| 역할 | 계정 |
| --- | --- |
| 관리자 | 김경곤 `kkg@bob.local` (거버넌스팀) · 문광석 `mks@bob.local` (보안운영팀) |
| 직원 | 박소은 `pse@bob.local` · 김미소 `miso@bob.local` (보안기술팀) · 양승권 `ysg@bob.local` (플랫폼개발팀) · 정원재 `jwj@bob.local` (데이터분석팀) |
| 협력사 직원 | 권노경 `nkk@bob.local` (협력사 A) |

비밀번호는 모두 `.env`의 `MOCK_SSO_PASSWORD`이고 기본값은 `test-password`입니다.
계정의 정본은 `principals` 관리대장 한 곳이며, 애플리케이션 상수에는 없습니다 —
있었을 때 사람이 늘 때마다 배포가 필요했습니다.

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
| [full_stack_lab/NETWORK.md](full_stack_lab/NETWORK.md) | 망 경계 설계와 Tailscale 적용 기준 (일부 미구현, 문서에 명시) |
| [docs/API.md](docs/API.md) | 통합용 API 명세. `./console.sh openapi`가 기계용 명세를 생성 |
| [research/](research/README.md) | 레퍼런스 조사와 설계 자료 |

v1.5에서 구버전 실습(`container_lab/`, `library_lab/`, 루트의 two-VM·stdio 최소 예제)을 제거했습니다. 정책 원본이 네 곳으로 갈라져 있으면 어느 것이 정본인지 저장소가 답하지 못합니다. 제거된 코드는 [`2026-09-v1.4-product-console-supply-chain`](https://github.com/MCP-governance/mcp-gateway/tree/2026-09-v1.4-product-console-supply-chain) 태그에 그대로 남아 있습니다.

## 검토·브랜치 원칙

- 하나의 릴리스 후보는 main 대상의 통합 PR 하나로 검토합니다. 직렬 스택 PR은 개별 병합하지 않습니다.
- 독립 작업은 `feat/YYYY-MM-vX.Y-내용`, 통합 후보는 `release/YYYY-MM-vX.Y-내용` 또는 검토용 브랜치를 사용합니다.
- 통합 PR이 기존 작업을 대체하면 기존 PR을 닫고, 포함 관계를 확인한 뒤 해당 원격 작업 브랜치만 삭제합니다.
- 병합된 기준점은 annotated tag로 남깁니다. 현행 태그는 [v0.1부터 v1.4까지](https://github.com/MCP-governance/mcp-gateway/tags) 보존됩니다.

## 증명 범위와 한계

- 기본 모델은 결정론적 모의 모델입니다. provider 경로는 로컬 HTTP wire stub과
  **로컬 LLM(Ollama · `qwen2.5:0.5b`, 397MB)** 으로 검증했습니다. 0.5B 모델은 전체
  도구 스키마를 받으면 CPU에서 첫 응답까지 1분을 넘기는 경우가 있어 상한을 120초로
  두었고, 도구 선택이 틀리는 경우도 있습니다. **그래도 판정은 정책이 합니다** —
  모델이 무엇을 제안하든 게이트웨이가 막을 것은 막는 것이 이 구조의 요점입니다.
  특정 상용 모델의 정확도·비용·rate limit은 별도 시나리오 시험이 필요합니다.
- GitHub MCP와 외부 제공자 호출은 인증·카탈로그 승인 전까지 의도적으로 비활성입니다.
- AI 코드 감사(mcp-scan)는 저장소 코드를 외부 LLM endpoint로 보냅니다. 코드 반출이 불가한 조직은 로컬 모델만 연결해야 합니다.
- 이 Gateway의 효과는 모든 MCP 도구 호출이 이 강제 경로를 통과할 때만 성립합니다.
  우회 경로를 **발견**하는 것은 엔드포인트 평면이고(→ [CONTROL_PLANES.md](full_stack_lab/CONTROL_PLANES.md)),
  **차단**하는 것은 네트워크 평면입니다(→ [NETWORK.md](full_stack_lab/NETWORK.md)).
  v1.7에서 발견의 범위가 설정 파일에서 내부망 리스너까지 넓어졌고 egress 판단이
  정책으로 들어왔지만, 게이트웨이를 지나지 않는 호출의 실제 차단은 여전히 조직의
  네트워크 장비 몫입니다.
- pip·npm으로 설치하는 stdio 서버는 도구 Schema가 그 서버의 의존성 버전에 따라
  달라집니다. `db/init.sql`에 박힌 승인 해시는 어느 한 빌드의 값이라 다른 호스트에서는
  정당한 설치도 드리프트로 잡힙니다. 그래서 `POST /api/registry/{id}/approve-contract`
  (Console의 '계약 재승인')가 있고, 무엇이 무엇으로 바뀌었는지를 사유와 함께 기록에
  남깁니다. 기동할 때 자동으로 승인하지 않는 것이 요점입니다 — 그러면 계약 고정이라는
  통제 자체가 사라집니다.
- 종료 판정의 모집단(C1)은 제공자가 하위 위임 자격을 고지해야 확정됩니다. 고지가 없으면 판정은 T3이며, 이것은 구현의 한계가 아니라 MCP 인가 명세와 RFC 7009가 만드는 구조적 한계입니다 → [TERMINATION.md](full_stack_lab/TERMINATION.md).
- 로컬 성공은 운영 배포 검증이 아닙니다. 실제 환경에서는 IdP 연동, 비밀 관리, TLS/mTLS, egress 제어, 독립 로그 보존을 검증해야 합니다.

상세 실행 절차, 테스트 시나리오, 구성값과 한계는 [full_stack_lab/README.md](full_stack_lab/README.md)를 기준 문서로 사용합니다.
