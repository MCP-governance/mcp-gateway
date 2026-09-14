# MCP Governance Security Gateway

MCP와 AI Agent의 도구 호출을 실행 전에 하나의 강제 경로에서 인증·정책·승인·카탈로그·감사로 검증하는 보안 실습 저장소입니다. 현재 통합 개발 기준은 v1.2이며, 실제 실행과 세부 증적은 [full_stack_lab/README.md](full_stack_lab/README.md)에 정리되어 있습니다.

> 학습·검증용 레퍼런스입니다. 운영 환경에는 조직의 SSO, 키 관리, 네트워크 격리와 별도 관제 체계를 추가해야 합니다.

## 가장 빠른 시작

Docker Compose가 가능한 WSL/Linux 환경에서 실행합니다.

~~~bash
git clone https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/full_stack_lab
./demo.sh
~~~

- 합성 사용자 Workspace: <http://localhost:8000>
- 거버넌스 Dashboard: <http://localhost:8080>
- 전체 검증: <code>./demo.sh test</code>
- 공급망 증적 생성: <code>./demo.sh scan</code>

현재 기준의 성공 조건은 Rego 12/12, core acceptance 52/52, Agent/API acceptance 61/61입니다.

## 통제 흐름

~~~mermaid
flowchart LR
    U[사용자] --> A[Agent Service]
    A -->|JWT + 짧은 수명의 Agent Assertion| G[Security Gateway]
    G --> R[Registry / Catalog]
    G --> P[OPA / Rego]
    G --> M[승인·감사·증적]
    P -->|허용된 호출만| T[Mock MCP / Upstream]
~~~

Gateway는 사용자 신원, 에이전트 위임 신원, 도구·메서드·인자, 카탈로그와 공급망 상태, 승인 및 용량 조건을 확인한 뒤에만 upstream 호출을 수행합니다.

## 현재 통합판에서 검증하는 통제

| 영역 | 적용 원리 | 확인 방법 |
| --- | --- | --- |
| 사용자·에이전트 신원 | 짧은 수명의 서명된 Agent Assertion을 사용자·에이전트·도구 호출 봉투에 결속 | 위조, 재사용, actor 또는 요청 변경을 401로 차단 |
| 정책 집행 | OPA/Rego가 역할·자료등급·도구·메서드·입력을 결정론적으로 판정 | 허용/차단과 실제 upstream 호출 여부를 함께 확인 |
| Registry·공급망 | 승인된 카탈로그·스키마·설명·SBOM/취약점 증적을 호출 전에 대조 | drift 또는 정책 위반 시 실행 전 거부 |
| 승인·감사 | 승인 재검증, 영수증 복구, 변조 탐지 가능한 감사 연쇄 | 요청·판정·upstream 증적을 Dashboard와 DB에서 추적 |
| 운영 안전장치 | monitor mode, 요청량 제한, idempotency·세션 경계 | enforce 전환과 과부하·중복 요청 사례 검증 |
| 전송 호환성 | Streamable HTTP, stdio, legacy SSE 경로를 동일 정책 경로로 수렴 | 각 transport의 MCP 호출 acceptance test |

## 저장소 안내

| 경로 | 용도 |
| --- | --- |
| [full_stack_lab/](full_stack_lab/README.md) | 현재 권장 통합판: Agent Service, Gateway, OPA, PostgreSQL 감사, Jaeger, 공급망 검증 |
| [container_lab/](container_lab/README.md) | LiteLLM 제안 경로와 OPA 집행 경로를 분리한 컨테이너 실습 |
| [library_lab/](library_lab/README.md) | FastAPI, Pydantic, PyCasbin, 공개 MCP 연동 학습판 |
| <code>two_vm_demo.py</code>, <code>setup-two-vm.sh</code> | Gateway와 mock MCP를 두 VM으로 분리해 upstream 효과를 대조하는 실습 |
| <code>compose.yaml</code>, <code>server.py</code>, <code>demo.py</code> | 최소 stdio MCP 정책 차단 예제 |
| [research/](research/README.md) | 레퍼런스 조사와 설계 자료 |

## 검토·브랜치 원칙

- 하나의 릴리스 후보는 main 대상의 통합 PR 하나로 검토합니다. 직렬 스택 PR은 개별 병합하지 않습니다.
- 독립 작업은 feat/YYYY-MM-vX.Y-내용, 통합 후보는 release/YYYY-MM-vX.Y-내용 또는 검토용 브랜치를 사용합니다.
- 통합 PR이 기존 작업을 대체하면 기존 PR을 닫고, 포함 관계를 확인한 뒤 해당 원격 작업 브랜치만 삭제합니다.
- 병합된 기준점은 annotated tag로 남깁니다. 현행 태그는 [v0.1부터 v1.1까지](https://github.com/MCP-governance/mcp-gateway/tags) 보존됩니다.

## 증명 범위와 한계

- 기본 모델은 결정론적 모의 모델이며, 실제 상용 LLM의 안전성을 입증하지 않습니다.
- GitHub MCP와 외부 제공자 호출은 인증·카탈로그 승인 전까지 의도적으로 비활성화합니다.
- 이 Gateway의 효과는 모든 MCP 도구 호출이 이 강제 경로를 통과할 때만 성립합니다. 우회 경로는 별도 네트워크·플랫폼 통제가 필요합니다.
- 로컬 성공은 운영 배포 검증이 아닙니다. 실제 환경에서는 IdP 연동, 비밀 관리, TLS/mTLS, egress 제어, 독립 로그 보존을 검증해야 합니다.

상세 실행 절차, 테스트 시나리오, 구성값과 한계는 [full_stack_lab/README.md](full_stack_lab/README.md)를 기준 문서로 사용합니다.
