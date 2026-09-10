# Library MCP integration lab

기존 표준 라이브러리 Gateway와 별개로, 오픈소스 라이브러리를 실제 호출해 보는 실습입니다.

## 구성

- **FastAPI + Uvicorn**: Gateway HTTP API와 GUI
- **Pydantic**: Gateway 입력 모델 검증
- **PyCasbin**: `role × data_class × rwx` 중 공개 자료 읽기(`public`, `r`) 판정
- **OpenTelemetry SDK**: Gateway 판정과 공개 MCP 호출 span을 `gateway.log`에 출력
- **mcp-server-time**: 공개 오픈소스 MCP 서버를 실제 stdio subprocess로 실행

`mcp-server-time==2026.8.18`은 현재 `mcp<2`를 요구합니다. 따라서 Gateway 라이브러리 환경과 공개 MCP 환경을 분리했습니다. 이는 패키지 충돌을 숨기지 않고 외부 MCP 호환성을 검증하는 실습입니다.

## 실행

WSL에서 실행합니다.

```bash
cd library_lab
bash setup-library-lab.sh
```

브라우저에서 다음 주소를 엽니다.

```text
http://192.168.85.129:8090/
```

`customer`, `employee`, `admin`은 공개 자료의 시간 조회를 통과합니다. `guest`는 Casbin이 `P-CASBIN-001`으로 차단하며 공개 MCP subprocess를 시작하지 않습니다.

## 범위와 주의

- 이 실습은 공개 시간 정보만 조회하며, 외부 계정·파일·DB·API 키를 사용하지 않습니다.
- 공개 MCP는 Gateway가 만든 managed stdio subprocess 안에서만 호출합니다. 사용자가 별도로 `mcp_server_time`을 직접 실행하면 이 Gateway 정책을 우회할 수 있습니다.
- 실제 환경은 승인된 패키지 버전·해시/SBOM 검증, 격리된 실행 계정, 네트워크 egress 정책, 중앙 인증을 추가합니다.
