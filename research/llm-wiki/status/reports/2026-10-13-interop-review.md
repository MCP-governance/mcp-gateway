# 기업 연동 자료와 preflight 독립 검토 — 2026-10-13

검토 범위는 현재 브랜치의 LiteLLM 연동 client, 연동 JSON/문서, 기존 credential 경계다. 제품 배포·고객 secret manager 연결·실제 모델→도구 업무 시험을 수행한 보고가 아니다. 원래 작업자의 미커밋 제품 코드는 변경하지 않았다.

## 확인한 구현

- [preflight.py](../../../../full_stack_lab/integrations/litellm/preflight.py)는 실제 HTTP client와 공식 MCP SDK를 사용한다. 자체 MCP server나 network mock을 만들지 않는다.
- `--validate-only`는 자격 파일을 읽지 않고 통신하지 않는다. 예제 URL은 `.invalid`이며 secret 값이 없다.
- 런타임 자격 파일은 POSIX owner-only regular file이어야 하고 마지막 경로 symlink를 거부한다. 서로 다른 LLM/MCP 자격을 사용하며 provider 오류 본문을 공개 출력하지 않는다.
- shared-token 집계 모드는 validator가 거부한다. `model_selected_tool_call_verified=false`와 `independent_business_effect_verified=false`를 고정해 별도의 모델 응답과 MCP discovery를 업무 E2E 통과로 표시하지 않는다.
- 정적 예제 검사는 Windows에서 통과했다. [check_preflight.py](../../../../full_stack_lab/integrations/litellm/check_preflight.py)의 3개 검사는 WSL Python에서 통과했다. POSIX 자격 검사 때문에 Windows의 같은 단위 실행은 세 번째 검사에서 실패하며, Windows 런타임 지원을 주장하지 않는다.

## 결과의 의미와 남은 조건

| 우선순위 | 발견 | 실제 영향·필요 조치 |
| --- | --- | --- |
| P0 | 기존 Gateway `credential_headers`는 credential file 환경값이 없거나 정확 endpoint 행이 없으면 `{}`를 반환한다. | 공개·무인증 MCP 지원을 위한 동작이다. secret 필수 서버에 대해 anonymous dispatch가 언제나 예방된다는 완료 주장은 부정확하다. 서버 등록의 `credential_required` 계약과 누락 시 dispatch 전 거부를 별도로 설계해야 한다. |
| P0 | 기존 `expires_at=0`은 무기한 자격으로 허용된다. | 유한 lease·회수·Agent freshness 보장은 아직 없다. 기업 공급자 자격은 양수 만료와 최대 stale 시간을 명시하고 provider에서 철회된 실제 자격의 재접근을 시험해야 한다. |
| P1 | preflight는 `trust_env=False`다. | 환경의 `HTTPS_PROXY`·`SSL_CERT_FILE`을 접속 계약으로 사용하지 않는다. 고객 private CA/proxy 연동이 이미 지원된다고 보고할 수 없다. 승인된 hostname·CA·명시 proxy를 검증하는 연결 계약이 필요하다. TLS 검사 해제는 해결책이 아니다. |
| P1 | 현재 field 기본 배치에는 LiteLLM `llm` profile이 활성화되지 않는다. | 정적 Compose 설정과 공식 upstream 기능을 현재 동작으로 쓰지 않는다. 고객의 기존 LiteLLM 경로를 우선 연결하거나 별도 자원·배치 검토 후 승인된 profile을 선택한다. |
| P1 | protected PJ1 하네스는 임의 Python client 실행·토큰 추출을 허용하는 환경이 아니다. | preflight는 승인된 integration 실행 환경과 provisioning이 있을 때만 수행한다. 현재 helper 보호를 우회하지 않는다. 제품 인수 검증은 실제 새 관리형 공식 하네스의 모델→MCP 호출로 한다. |
| 자료 정밀도 | 검토 시점의 50조건 생성기는 대부분 공통 prerequisite/procedure를 복제하며 Secret managers 16조건의 `source_refs`가 비어 있었다. | 각 조건의 실제 설정·정상/음성 절차·현재 코드 함수/행·공식 제품별 출처·실패 수정안을 채워야 기업 도입 추적 자료로 사용할 수 있다. 50개 행 수만으로 조건 세분화가 완료됐다고 보고하지 않는다. |

## 판본·라이선스 확인

2026-10-13 공식 GitHub API에서 실제 Compose tag `v1.102.1`의 commit을 `d09bbae1c6df463e425558f60d460437193635da`로 확인했다. [pyproject.toml](https://github.com/BerriAI/litellm/blob/d09bbae1c6df463e425558f60d460437193635da/pyproject.toml)의 SDK 제약은 MCP 1.x다. 평가 후보 [v1.105.0](https://github.com/BerriAI/litellm/releases/tag/v1.105.0)는 2026-10-11 공개된 release이며 commit `80b9556dd312d18c535ae06884faa97d1fdb8f46`, MCP SDK 2.x 제약을 갖는다. release 판본끼리 협상·capability·session·auth 동작을 각각 시험해야 한다. 문서의 최신 기능을 이전 이미지로 이전하지 않는다.

LiteLLM의 [native Secret Managers](https://docs.litellm.ai/docs/secret_managers/overview)는 공식 문서상 Enterprise 기능이다. [코어 LICENSE](https://github.com/BerriAI/litellm/blob/80b9556dd312d18c535ae06884faa97d1fdb8f46/LICENSE)는 `enterprise/`를 MIT 범위에서 제외한다. Vault 현재 서버 [LICENSE](https://github.com/hashicorp/vault/blob/fdd82cfd09d5f905f29aa98d9fea6d2a77fd5eda/LICENSE)는 BSL이고, OpenBao [LICENSE](https://github.com/openbao/openbao/blob/c760347ffecea6b9baf33345b01ff125b28e73f5/LICENSE)는 MPL-2.0이다. upstream 인기도는 후보 선정 정보이고 호환성·권한 회수·공급망 안전의 실행 증거를 대신하지 않는다.

## 다음 검증

1. 조건별 source/code/prerequisite/procedure/failure-fix를 완성하고 JSON→Excel 재생성 후 ID·행·링크를 검사한다.
2. 고객 LiteLLM의 고정 판본, 허용 모델, TLS origin/CA, virtual key 범위와 별도의 관리형 MCP 신원을 확보한다.
3. 정상 모델 응답과 MCP discovery를 선행 검사한다. 이후 공식 OSS/상용 MCP의 실제 읽기·쓰기 업무에서 fresh managed 하네스→도구 호출→Gateway trace/decision→독립 공급자 효과를 연결한다.
4. secret manager는 공식 Agent/SDK/ESO와 기존 파일 계약을 우선 평가한다. expiry·rotation·권한 철회·불능 후 stale 자격·로그 비밀 노출을 각각 검증한다.
