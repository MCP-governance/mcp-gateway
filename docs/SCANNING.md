# 제2안 Scan Orchestrator / Security Test Zone

검증 기준은 Tencent/AI-Infra-Guard **v4.6.3**의 task API 구현과 배포 파일이다. 공식 Docker Hub 이미지 `zhuquelab/aig-server:v4.6.3`, `zhuquelab/aig-agent:v4.6.3`의 amd64/arm64 manifest가 실제 존재함을 확인했다. `latest` 대신 이 태그를 사용한다.

## Gateway에 연결

`services/gateway.py`의 `create_app()`에서 2안에만 다음 router를 등록한다. `app.state.client`는 기존 공유 HTTPX client를 사용한다.

```python
from services.scanner import router as scan_router
app.include_router(scan_router)
```

- `POST /scans`는 Keycloak admin JWT를 검증하고 `{"target":"demo"}`만 받는다. 대상 URL은 배포자가 지정한 `TEST_TARGETS` JSON에서 가져온다. 임의 URL·파일 경로·인증 헤더·프롬프트·LLM 토큰을 요청 본문으로 받지 않는다.
- `POST /api/v1/app/taskapi/tasks`에 `type=mcp_scan`, `content.prompt=<고정된 검사 대상 URL>`, `thread=1`, `language=en`을 보낸다. upstream `status=0`과 정상 UUID가 확인된 경우에만 HTTP 202를 반환한다.
- `GET /scans/{UUID}`는 admin JWT를 다시 검증한다. 실제 A.I.G 상태를 조회하고 `done`/`completed`인 경우에만 실제 result API를 조회한다. 로그는 응답에서 제외하고 scan 관측 데이터에는 상태·UUID·건수만 담는다.
- 검사 결과가 tool approval을 변경하는 경로는 없다. 승인/차단은 기존 관리자 결정 API에 남는다.
- `POST /scans/trivy-result`는 `X-Service-Token`이 일치할 때에만 고정된 `/scan-reports/trivy.json`을 읽고, Trivy schema 2의 취약점·오구성·secret 건수와 심각도만 반환/관측한다. 요청에서 경로나 결과를 선택할 수 없다. 실제 보고서가 없거나 잘못되었으면 503이다.

## 환경 변수

Gateway 2안에 추가:

```yaml
environment:
  AIG_BASE_URL: http://aig-web:8088
  AIG_USERNAME: public_user
  TEST_TARGETS: '{"demo":"http://test-mcp:8000/mcp"}'
  AIG_SCAN_MODEL: ${AIG_SCAN_MODEL:-}
  AIG_SCAN_MODEL_TOKEN: ${AIG_SCAN_MODEL_TOKEN:-}
  AIG_SCAN_MODEL_BASE_URL: ${AIG_SCAN_MODEL_BASE_URL:-https://api.openai.com/v1}
  TRIVY_REPORT_PATH: /scan-reports/trivy.json
volumes:
  - scan-reports:/scan-reports:ro
networks:
  - control-plane
  - scan-control
```

`AIG_SCAN_MODEL`과 `AIG_SCAN_MODEL_TOKEN`은 함께 설정한다. 키는 서버 측에서만 A.I.G에 전달하며 telemetry/콘솔에 표시하지 않는다. 둘 다 비워 두면 A.I.G의 `public_user` 기본 모델 설정을 사용한다. 어떤 방식으로도 실제 LLM 모델/키가 설정되지 않았다면 A.I.G가 실패를 반환하며, 애플리케이션은 이를 503으로 전달한다. 비용이 드는 LLM 검사는 실제 자격 증명이 있어야 완료를 검증할 수 있다.

공식 CLI는 `API-KEY` 헤더를 지원하지만 **v4.6.3 OSS 서버는 이를 인증하지 않는다**. 서버의 identity middleware는 `username` 또는 `public_user`만 사용한다. 따라서 A.I.G 포트를 외부에 공개하지 않고, Gateway의 admin JWT를 유일한 사용자 검사 진입점으로 둔다.

## Compose 추가 예시

이름은 기존 네트워크/서비스 정의에 맞춘다. A.I.G agent가 접근하는 `security-test-zone`에는 검사 전용 MCP 복제본을 놓는다. 운영 MCP 서버·운영 DB·호스트 Docker socket을 검사 agent에 연결하지 않는다. LLM API와 GitHub를 사용하려면 해당 zone의 통제된 외부 연결이 필요하다.

```yaml
services:
  aig-web:
    image: zhuquelab/aig-server:v4.6.3
    environment:
      APP_ENV: production
      UPLOAD_DIR: /app/uploads
      DB_PATH: /app/db/tasks.db
      AIG_API_CHECKER_URL: http://aig-agent:8000
    volumes:
      - aig-data:/app/data
      - aig-db:/app/db
      - aig-logs:/app/logs
      - aig-uploads:/app/uploads
    networks: [scan-control, security-test-zone]
    depends_on:
      aig-agent:
        condition: service_healthy
    healthcheck:
      test: [CMD, curl, -f, http://localhost:8088/]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 5s
  aig-agent:
    image: zhuquelab/aig-agent:v4.6.3
    environment:
      AIG_SERVER: aig-web:8088
      AIG_API_CHECKER_ROOT_PATH: /api-checker
      AIG_API_CHECKER_DATA_DIR: /api-checker-data
      AIG_API_CHECKER_MAX_JOBS: 2
    volumes:
      - aig-api-checker-data:/api-checker-data
    # Upstream v4.6.3's browser/agent runtime requires these settings.
    cap_add: [SYS_ADMIN]
    security_opt: [seccomp:unconfined]
    shm_size: 2gb
    networks: [security-test-zone]
    healthcheck:
      test: [CMD, gosu, "agent:agent", /app/api-checker-venv/bin/python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
  trivy:
    image: aquasec/trivy:0.74.0
    profiles: [scan]
    command: [fs, --scanners, "vuln,misconfig,secret", --format, json, --output, /scan-reports/trivy.json, --exit-code, "0", /target]
    volumes:
      - ./scan-target:/target:ro
      - scan-reports:/scan-reports
      - trivy-cache:/root/.cache/trivy
    networks: [security-test-zone]
networks:
  scan-control:
    internal: true
  security-test-zone: {}
volumes:
  scan-reports: {}
  aig-data: {}
  aig-db: {}
  aig-logs: {}
  aig-uploads: {}
  aig-api-checker-data: {}
  trivy-cache: {}
```

`docker compose --profile scan run --rm trivy`가 성공한 뒤 기존 내부 client로 `POST /scans/trivy-result`를 호출하면 normalize/OTel 경로에 들어간다. `/scan-reports` 쓰기 권한은 Trivy job만 가진다. DB 업데이트/검사 실패 시 이전 파일과 혼동되지 않도록 job 실행 전에 기존 보고서를 지우거나 실행별 report volume을 사용한다.

## 검증된 API 출처

- [공식 v4.6.3 CLI](https://github.com/Tencent/AI-Infra-Guard/blob/v4.6.3/skills/aig-scanner/scripts/aig_client.py): task payload, username/API-KEY, status/result 순서.
- [공식 API 구현](https://github.com/Tencent/AI-Infra-Guard/blob/v4.6.3/common/websocket/api.go): status envelope와 기본 모델 실패.
- [공식 server identity middleware](https://github.com/Tencent/AI-Infra-Guard/blob/v4.6.3/common/websocket/server.go): OSS username 처리.
- [공식 Compose](https://github.com/Tencent/AI-Infra-Guard/blob/v4.6.3/docker-compose.yml): healthcheck·agent 권한·v4.6.3 checker 설정.
- [공식 release Docker workflow](https://github.com/Tencent/AI-Infra-Guard/blob/v4.6.3/.github/workflows/docker-publish.yml): 이미지 이름과 태그 배포.
