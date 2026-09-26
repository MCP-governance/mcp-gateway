# 검증 기록

WSL Python 3.12, Docker Engine 29.8.1에서 실행했다.

- Python unit tests: 28 passed.
- Pyflakes, Compose config, git diff --check 통과.
- 실제 Keycloak 26.7.4 로그인/사용자와 관리자 권한 분리.
- 공식 MCP SDK 2.2.0 서버 초기화/도구 발견/원문 echo/내부·외부 API 호출.
- 실제 OPA 1.20.2, Presidio 2.2.364의 민감정보 차단.
- OTel Collector 0.153.0 → Evidence Processor → Analyzer → PostgreSQL 18 증적 저장.
- 세 증적 소스와 Presidio 발견에 따른 위험 분류 확인.
- 실제 LLM 모델 추론은 자격 증명이 없어 실행하지 않았다.

Presidio 이미지에 이미 포함된 en_core_web_lg를 사용해 격리망에서 모델을 다운로드하지 않는다.

## 실제 기기 배치(field-deploy) 검증 기록

로컬(Windows, Docker 엔진 없음)에서 확인한 것:

- `tests/test_field_pc.py`: 가짜 Keycloak(device grant의 대기 응답·승인·거부, 갱신, RFC 7009 폐기, OpenID 설정)과 가짜
  `/mcp/demo`를 상대로 키트의 로그인 → 하네스 설정(헬퍼 명령만, 토큰 원문 없음, Codex 사용자 설정 보존·멱등) → 환경을
  비운 헬퍼 동시 실행에서 갱신 1번 → `doctor` → `uninstall`(폐기 요청). 쓰기 전 충돌 확인, 관리형 파일.
- 같은 가짜 서버에 이 PC의 **실제 Claude Code 2.1.179와 Codex CLI 0.157.1**을 붙였다: `claude mcp list`가 `demo`를
  `✔ Connected`로 보고, Codex는 접근 토큰이 만료된 뒤 `http_headers_helper`로 갱신된 토큰을 받아 `initialize`했다.
- `tests/test_field_deploy.py`: `prepare.py`의 loopback/field 렌더링(생성물은 `outputs/`), realm의 `mcp-cli` 클라이언트,
  Caddyfile이 Keycloak에는 `/realms/mcp/*`·`/resources/*`만 넘기고 `/admin*`·다른 realm은 `handle` 안에서 404로 막는지,
  `docker compose -f compose.yaml -f compose.field.yaml config`에서 Caddy만 `${APPLIANCE_BIND}:443`에 게시되는지.

CI(`.github/workflows/verify.yml`의 `field` 작업)가 확인하는 것: `./field/appliance.sh up`으로 실제 Keycloak·Caddy를 띄워
issuer가 `https://mcp-gw.internal/realms/mcp`인지, 사내망 주소에서 `/admin/`과 master realm이 404인지, 관리 콘솔이
loopback 주소(`KC_HOSTNAME_ADMIN`)로 리다이렉트되는지, `mcp-cli`의 device 엔드포인트가 응답하는지, 키트 `setup`·`doctor`와
실제 Claude Code(`claude mcp list` 연결됨)·Codex CLI(`codex mcp get`), `uninstall`.

확인하지 못한 것: 사람이 브라우저에서 device 코드를 승인하는 단계(CI는 Direct Access Grants가 켜진 `mcp-gateway` 클라이언트로
로그인한다), 실제 Windows·macOS PC의 인증서 저장소, WSL2 미러 네트워킹과 Windows 방화벽 규칙.
