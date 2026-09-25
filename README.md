# MCP Governance Security Gateway

사내망의 직원 AI 에이전트가 **실제 MCP 서버**를 쓰는 회사를 통째로 띄우고, 모든 도구 호출을
**실행 전에** 판정하는 Gateway와, MCP 이용 관계를 **끝냈다고 말할 수 있는지** 판정하는 종료·폐기
절차까지를 한 저장소에서 재현하는 보안 테스트베드입니다.

> **범위:** 합성 계정과 합성 회사(BoB Corp) 데이터를 쓰는 재현용 랩입니다. 운영망의 SSO, 키 관리,
> TLS, 호스트 방화벽과 중앙 로그 보존을 대신하지 않습니다.

![구성도](docs/ai/architecture.png)

## 무엇이 들어 있나 (v2)

- **BoB Corp**: 회사 DB(PostgreSQL)·Redis·메일(GreenMail)·코드 저장소(Gitea)·인트라넷·공유 드라이브,
  그리고 "외부 인터넷" 모사. 시드 데이터에 개인정보·급여·유출된 비밀·프롬프트 주입 페이지가 있습니다.
- **직원 PC 4대**(ws-ysg·ws-jwj·ws-pse·ws-nkk): 사내망(`office`)의 컨테이너. 직원별 **LiteLLM 가상 키**로
  로컬 LLM(Ollama)을 쓰는 AI 어시스턴트가 OAuth 토큰을 받아 **Gateway의 `/mcp/` 하나로만** 도구를 부릅니다.
  협력사 직원의 PC에는 Gateway를 우회하는 섀도 MCP 설정이 있습니다.
- **실제 MCP 서버 10종**: filesystem · git · fetch · memory · desktop-commander · postgres-mcp · redis ·
  mcp-email-server · gitea-mcp · @playwright/mcp (버전 고정, 계약 해시 잠금).
- **Gateway**: 신원(transport 토큰) → 자원 분류(경로·SQL·URL·수신자·키) → 승인 스키마 검증 →
  **Presidio 개인정보 검사**(나가는 인자) → OPA/Rego(333 권한 행렬 + SSRF·DLP·민감정보 반출·열람→반출 연쇄·
  계약·공급망·종료 통제) → 같은 연결에서 계약 재확인 → 실행 → **결과 개인정보 마스킹** → 해시 체인 감사.
  기록된 정책 입력은 후보 정책에 그대로 재생할 수 있습니다(`./console.sh replay`, MCP 호출 없음).
- **Console**(웹): 활동 로그를 사람이 읽는 문장으로, 승인, 계약 검토, 직원·단말, 도입 신청, 정책,
  그리고 **종료·폐기 판정 워크스페이스**. 웹에서 MCP를 호출하지는 않습니다.
- **논문 구현**: 「원격 MCP 서비스 종료 시 권한 회수의 구조적 한계 및 종료 판정 기준 제안」(CISC-W'26)의
  이용 관계 단위 판정(C1 모집단·C2 수행 권한·C3 연속성·C4 증거 접근 → T1/T2/T3)과 실험 E1~E3.

## 빠른 시작

Docker Engine이 있는 Linux 또는 WSL2에서:

~~~bash
git clone https://github.com/MCP-governance/mcp-gateway.git
cd mcp-gateway/full_stack_lab
./console.sh up          # 첫 실행은 이미지 빌드와 모델 다운로드로 수십 분 (LLM 없이: --no-llm)
./console.sh workday     # 네 직원의 하루 업무
./console.sh watch       # 다른 창에서: Gateway 판정을 한 줄씩
./console.sh test        # 전체 검증
~~~

- Console: <http://localhost:8000> — `kkg@bob.local` / `test-password` (관리자)
- 포트가 겹치면 `.env`에 `CONSOLE_PORT`·`GATEWAY_PORT`·`JAEGER_PORT`·`GITEA_PORT`를 지정합니다.

### Docker 네트워크 주소 풀이 소진된 경우

`all predefined address pools have been fully subnetted`는 Docker가 새 Compose 네트워크에 배정할 주소 대역을
찾지 못했다는 뜻입니다. 이 랩은 격리를 위해 네트워크를 11개 만들므로, 같은 호스트에서 여러 복제본을 동시에
띄우면 기본 주소 풀이 바닥납니다. 사용을 마친 **해당 복제본**의 `full_stack_lab`에서 `./console.sh down`을
실행한 뒤 다시 시작하세요(`down`은 컨테이너와 네트워크만 내리고 볼륨은 보존합니다). 실행 중인 다른 프로젝트의
네트워크를 일괄 삭제하지 마세요. 여러 스택을 계속 유지해야 한다면
[Docker 주소 풀 설정](https://docs.docker.com/engine/network/#automatic-subnet-allocation)에서 더 작은 네트워크
크기를 설정합니다(데몬 재시작이 필요하므로 실행 중인 다른 스택을 먼저 확인).

## 검증

`./console.sh test`가 한 번에 돌리는 것: Rego 단위 시험 90건 · 분류기 self-check · Gateway 인수 시험 12건
(개인정보 마스킹·반출 차단·열람→반출 연쇄 포함) · 직원 업무 시나리오 21건의 기대 판정 대조 · 종료 판정 흐름 21건 ·
보안 회귀(망 분리 실제 소켓, loopback 게시, 토큰 없는 읽기 API, 역할 경계, 로그아웃 즉시 효력, OPA·상위 서버·
Presidio 장애 시 실패 안전, 감사 변조 탐지, 계약 잠금) · 정책 재생(합성 공격·정상 사례) · 논문 실험 E1~E3 결과 대조. CI([`.github/workflows/verify.yml`](.github/workflows/verify.yml))가
`main`·`feat/**` 푸시와 PR마다 같은 명령을 실행합니다. 상세: [docs/ai/TESTING.md](docs/ai/TESTING.md).

## 333 권한 모델

**역할 3 × 데이터 등급 3 × 행위 3 = 27칸.** 행위는 도구 이름이 아니라 인자에서 정합니다
(`SELECT`=r, `UPDATE`=w, DDL·외부 메일·외부 목적지=x). 모르는 자원은 important로 봅니다.

| 역할 \ 등급 | 공개 r/w/x | 내부 r/w/x | 중요 r/w/x |
| --- | --- | --- | --- |
| 협력사 직원 | 허용/차단/차단 | 차단/차단/차단 | 차단/차단/차단 |
| 직원 | 허용/차단/차단 | 허용/허용/차단 | 경보/차단/차단 |
| 관리자 | 허용/허용/경보 | 허용/허용/경보 | 허용/허용/승인 |

27칸은 출발점입니다. 그 위에 계약·레지스트리·SSRF·DLP·종료·예외·누적 접근 정책이 우선순위로 겹칩니다
→ [docs/ai/POLICY.md](docs/ai/POLICY.md). 정책마다 `risk_ids`(RSK-01~32)·`requirement_ids`(REQ-01~35)·
`control_ids`(CTL-01~35)·`pac_candidate_id`가 **MCP 보안 통합관리대장 V1.0**의 실제 행을 가리킵니다.

## 종료·폐기 판정

서비스를 "껐다"는 것은 권한 회수가 끝났다는 뜻이 아닙니다. 케이스를 여는 순간 Gateway가 그 이용 관계의
호출을 모두 막고(차단이 회수보다 먼저), 회수 대상(강제 경로·이용 주체·단말 설정·**제공자가 하위 시스템에
보유한 자격**)마다 증거를 모아 네 기준으로 판정합니다. RFC 7009 폐기 응답(200)은 처리 사실만 증명하므로
상태 증거로 치지 않고, 제공자가 보유 자격을 고지하지 않으면 모집단을 열거할 수 없어 **T3(판단 불가)**이며
위험 수용 없이 종결되지 않습니다. → [docs/ai/TERMINATION_MODEL.md](docs/ai/TERMINATION_MODEL.md)

## 저장소 안내

| 경로 | 용도 |
| --- | --- |
| [full_stack_lab/](full_stack_lab/README.md) | 통합 랩 전체(Compose·Gateway·Console·MCP 서버·회사·직원 PC·시험) |
| [docs/ai/](docs/ai/README.md) | **설계·운영·시험 문서** (다음 작업자는 여기부터) |
| [docs/API.md](docs/API.md) | API 요약. `./console.sh openapi`가 기계용 명세 생성 |
| [docs/design/](docs/design/) | v1 시기 설계 배경(통제 평면 분리, 망 경계·Tailscale) |
| [docs/PDF-INTEGRATION-2026-09.md](docs/PDF-INTEGRATION-2026-09.md) | 20쪽 PDF 요구사항(런타임 통제·정책 수명주기) 대조 기록과 v2 이식 내용 |
| [AGENTS.md](AGENTS.md) | AI 에이전트 작업 규칙과 깨면 안 되는 불변식 |
| [research/](research/README.md) | 레퍼런스 조사 |

v1(모의 MCP 서버·웹에서 도구 실행)은 태그로 보존되어 있습니다. v2는 모의 서버와 time 서버를 모두
실제 서버로 바꾸고, 도구 호출 주체를 웹에서 직원 PC의 에이전트로 옮겼습니다.

## 검토·브랜치 원칙

- 하나의 릴리스 후보는 main 대상의 통합 PR 하나로 검토합니다.
- 독립 작업은 `feat/YYYY-MM-vX.Y-내용`, 통합 후보는 `release/YYYY-MM-vX.Y-내용`.
- 병합된 기준점은 annotated tag로 남깁니다.

## 운영으로 옮기기 전에

- 이 저장소는 강제 경로 **안의** 호출을 통제합니다. 섀도 MCP는 발견·증적 강화까지이고, 실제 차단은
  네트워크 평면(egress 허용목록·DNS)의 몫입니다 → [docs/design/CONTROL_PLANES.md](docs/design/CONTROL_PLANES.md).
- 합성 로그인은 조직 SSO가 아니고, Compose 내부망은 호스트 방화벽이나 tailnet ACL이 아닙니다
  → [docs/design/NETWORK.md](docs/design/NETWORK.md).
- 계약 잠금(`registry/contracts.lock.json`)은 한 빌드의 값입니다. 서버 버전을 올리면 diff를 검토하고
  `./console.sh contracts --update`로 갱신합니다. 기동 시 자동 승인(TOFU)은 하지 않습니다.
- AI 코드 감사(mcp-scan)는 저장소 코드를 설정한 LLM endpoint로 보냅니다. 코드 반출이 불가한 조직은
  로컬 모델만 연결해야 합니다.
