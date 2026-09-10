# LiteLLM + Gateway + OPA 컨테이너 실습

이 실습은 “LLM이 어떤 도구를 고를지”와 “그 도구를 실제로 실행해도 되는지”를 분리해 보여준다.

```text
브라우저/Agent ──> LiteLLM ──> 로컬 OpenAI 호환 모의 모델
       │                         (도구 호출 제안만 함)
       └────────> Gateway ──> OPA ──> Mock MCP ──> 효과 증적
                         │                ▲
                         └── 거부면 여기서 끝 ┘
```

LiteLLM은 모델 요청을 중계하고 도구 호출 제안을 관측하는 E0 역할이다. 허용/차단은 Gateway의 사전 실행 검사와 OPA 정책이 맡는다. `verifier`는 Gateway의 주장과 Mock MCP 효과 파일을 읽기 전용으로 비교한다.

## 시작하기

WSL 또는 Docker가 가능한 쉘에서 저장소 루트로 이동한 뒤 실행한다.

```bash
git switch feat/container-litellm-policy-lab
cd container_lab
mkdir -p runtime/audit runtime/effects
docker compose up --build -d
docker compose ps
```

브라우저에서 `http://localhost:8000`을 연다. GUI의 빠른 버튼 네 개는 아래 결과를 보여 준다.

| 사용자 | 요청 자료 | 기대 결과 |
| --- | --- | --- |
| 고객 | 공개 | 통과, Mock MCP 효과 1개 |
| 고객 | 중요 | 차단, `upstream_called: false`, 효과 0개 |
| 직원 | 비중요 | 통과, Mock MCP 효과 1개 |
| 관리자 | 중요 | 통과, Mock MCP 효과 1개 |

GUI 결과에서 `request_id`를 복사해 독립 검증을 실행한다.

```bash
docker compose --profile verify run --rm verifier <request_id>
```

차단 결과라면 다음과 비슷한 출력이 정상이다.

```json
{"status":"PASS","decision":"DENY","upstream_called":false,"matching_effects":0}
```

## 눈으로 보는 세 지점

1. `model_evidence`: LiteLLM 경유 도구 제안이다. 원문 프롬프트와 원문 모델 응답은 저장하지 않고 SHA-256 값만 남긴다.
2. `gateway`: OPA의 `ALLOW`/`DENY`, 정책 ID, `upstream_called`을 보여 준다. 이것이 차단 지점이다.
3. `verifier`: 공유 로그를 읽기 전용으로 비교해 “차단인데도 효과가 생겼는지” 또는 “허용인데 효과가 정확히 하나인지”를 판정한다.

Gateway는 `X-Agent-Assertion` HMAC을 확인한다. 즉 브라우저가 보낸 역할 문자열을 그대로 믿지 않고, 이 실습에서 신뢰한 Agent가 역할·도구·인자 해시를 묶어 서명한 경우에만 정책 입력으로 사용한다. 실제 환경에서는 이 자리를 IdP 발급 JWT, mTLS, 워크로드 아이덴티티로 바꾼다.

## 정책 모델

| 역할 | 공개 | 비중요 | 중요 |
| --- | --- | --- | --- |
| 고객 | `r` | - | - |
| 직원 | `r` | `rw` | - |
| 관리자 | `rwx` | `rwx` | `rwx` |

현재 Mock MCP는 `read_file` 하나뿐이라 실제 실행은 `r`만 시험한다. `w`, `x`는 이후 `write_file`, `delete_file`을 추가할 때 같은 OPA 정책 표에 연결할 예약된 권한이다. 자료는 모두 합성 파일이며, 경로도 Gateway와 Mock MCP 양쪽에서 화이트리스트로 다시 검사한다.

## 스키마 변경 차단 실습

Mock MCP가 승인된 `read_file` 입력 스키마에 `encoding` 필드를 몰래 추가했다고 가정할 수 있다.

```bash
MCP_SCHEMA_MODE=drift docker compose up --force-recreate -d mock-mcp
```

그 뒤 어떤 사용자로 요청해도 Gateway가 업스트림 카탈로그 해시와 승인 해시가 다르다고 보고 `MCP-CHANGE-001`로 차단한다. 실습이 끝나면 `MCP_SCHEMA_MODE=approved`로 같은 명령을 다시 실행한다.

## 최소 검증과 관찰

```bash
docker compose build gateway
docker compose run --rm --no-deps gateway python -m app.test_policy
docker compose logs gateway --tail 50
```

이 self-check는 경로 등급화와 HMAC 역할 위·변조 방지를 검사한다. Docker가 실행되지 않는 경우에는 먼저 WSL/VM 메모리 문제를 해결해야 실제 컨테이너 검증을 주장할 수 있다.

## 팀원 작업과의 결합 방식

팀 저장소의 `main`은 Agent → Gateway → Mock MCP라는 서비스 분리, internal 네트워크, 헬스체크, capability drop이라는 좋은 출발점을 제공한다. 그 구조를 이 실습판의 Compose에 반영하고 다음을 추가했다.

| 팀 `main`의 출발점 | 이 브랜치의 확장 |
| --- | --- |
| 키워드 기반 도구 선택 | LiteLLM 경유의 OpenAI 호환 tool-call 제안 |
| 공개 경로 하나만 허용 | 역할·자료등급·rwx OPA 정책 |
| 정적 Gateway 조건문 | 승인 계약·업스트림 스키마 해시 재검사 |
| 실행 응답만 확인 | Gateway 감사 로그 + Mock MCP 효과 증적 + 읽기 전용 verifier |

팀의 `miso` 브랜치는 `main`의 파일을 모두 지운 빈 브랜치여서 병합 대상에서 제외했다. 소유권 충돌을 피하려고 팀 저장소를 수정하거나 강제 병합하지 않고, 우리 저장소에 결합 실습판을 별도 디렉터리로 만들었다.

## 의도적으로 아직 넣지 않은 것

- PostgreSQL, Redis, React 대시보드, Prometheus는 이 첫 실습의 허용/차단 증명에 필요하지 않아 제외했다.
- 외부 LLM API 키도 필요 없다. LiteLLM은 같은 컨테이너망의 OpenAI 호환 모의 모델로 향한다. 실제 모델을 붙일 때만 `litellm-config.yaml`의 `api_base`와 비밀값을 배포 비밀 저장소로 바꾼다.
- LiteLLM 기본 이미지는 공식 빠른 시작 경로의 `main-latest`를 사용한다. 오래 두는 환경에서는 이미지 digest 고정·취약점 점검으로 바꾼다.
- Docker 내부망은 이 Compose 안에서 Mock MCP 직접 접근을 줄이는 장치일 뿐이다. 모든 우회 경로를 막는 P2 네트워크 통제를 주장하지 않는다.

참고: [LiteLLM MCP 개요](https://docs.litellm.ai/docs/mcp), [LiteLLM Docker Quick Start](https://docs.litellm.ai/docs/proxy/docker_quick_start), [LiteLLM Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys)
