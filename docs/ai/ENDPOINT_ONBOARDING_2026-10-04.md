# 엔드포인트 연결 단순화 조사 (2026-10-04)

직원 PC를 게이트웨이에 붙이는 과정을 "콘솔 로그인 → 설치 파일 받기 → 실행 → 권한 허용"으로 줄이기 위한 레퍼런스 조사.
현재 우리 흐름은 압축 해제, `sudo python3 … install`, 하네스 바이너리 수동 배치, 관리 계정 전환, `codex login`까지 손이 많다.

## 레퍼런스 3종

| | 직원 클릭/입력 | 관리자가 하는 일 | 인증 전달 | OS 강제 |
|---|---|---|---|---|
| **IBM ContextForge** (MCP Gateway) | 클라이언트 설정 JSON에 2~3개 값(`MCP_AUTH` 토큰, `MCP_SERVER_URL`)을 직접 넣고 래퍼(`mcpgateway.wrapper`) 설치 | JWT 토큰 발급(`create_jwt_token`), 가상 서버 구성 | 정적 JWT를 env로, 래퍼가 SSE로 게이트웨이에 전달 | 없음(래퍼는 사용자 공간 프로세스) |
| **Microsoft Windows ODR + Intune/Entra + APIM** | 에이전트별 권한 허용 1클릭(호스트 단위, 서버마다 아님), OAuth면 브라우저 로그인 1회 | Intune로 `managed-settings`(ADMX/plist/HKLM) 배포, Entra 앱 등록, APIM에서 OAuth/PRM·Credential Manager 구성 | APIM이 PRM(RFC 9728) 광고 → 클라이언트가 브라우저 로그인 후 토큰 재시도. 상류 토큰은 Credential Manager가 주입 | **있음**: ODR가 MCP 서버를 별도 Windows 세션·별도 에이전트 사용자 계정·승인 자원만 접근으로 격리(AppContainer류). 패키지 앱은 항상 격리 |
| **LiteLLM** (가상 키·팀 온보딩) | `lite login`(브라우저 SSO) 1회 → `lite configure`/`lite claude`가 env·설정 파일을 자동 기록. 수동값 "dozens → 1" | SSO 연결, 팀·키 권한(`x-litellm-api-key`), MCP 서버 등록 | 가상 키를 헤더로. `lite login`은 SSO 후 단기 세션 자격을 자동 발급 | 없음 |

출처:
- IBM: [mcp-context-forge](https://github.com/ibm/mcp-context-forge), [STDIO Wrapper](https://ibm.github.io/mcp-context-forge/using/mcpgateway-wrapper/)
- Microsoft: [MCP on Windows overview](https://learn.microsoft.com/en-us/windows/ai/mcp/overview), [MCP containment](https://learn.microsoft.com/en-us/windows/ai/mcp/servers/mcp-containment), [Claude Code managed settings](https://code.claude.com/docs/en/managed-settings), [APIM으로 MCP 노출](https://learn.microsoft.com/en-us/azure/api-management/export-rest-mcp-server), [APIM MCP 인증](https://techcommunity.microsoft.com/blog/appsonazureblog/mcp-in-azure-using-api-management-for-authentication-access-logging--governance/4532139)
- LiteLLM: [Client Setup](https://docs.litellm.ai/docs/proxy/client_setup/overview), [CLI SSO](https://docs.litellm.ai/docs/proxy/cli_sso), [Claude Code Gateway](https://docs.litellm.ai/docs/tutorials/claude_code_gateway)

## 가져올 것

1. **LiteLLM `lite login`/`lite configure` 모델** — 설치 마지막에 하네스 모델 로그인을 자동 안내·실행하고, 설정 파일·env를
   도구가 대신 기록한다. 우리도 설치기가 관리형 설정을 전부 쓰고, 끝에 `codex login`을 그 계정 컨텍스트에서 자동 실행한다.
2. **Microsoft의 "권한 허용은 호스트 단위 1회"** — 서버마다 동의를 받지 않는다. 우리는 OS 관리자 승격(sudo/UAC) 1회가
   그 자리를 차지한다. 설치 = 그 1회 승격 안에서 모든 구성을 끝낸다.
3. **Intune `managed-settings` 배포 경로** — 이미 우리 managed-settings/requirements.toml 위치는 MS 규격과 같다. 유지.
4. **APIM의 PRM 기반 자동 토큰** — 하네스가 401을 받으면 헤더 헬퍼가 자동 재발급하는 지금 구조와 같은 철학. 유지.

## 버릴 것 / 우리가 더 강한 것

- ContextForge·LiteLLM은 **OS 강제가 없다**(래퍼·env 키만). 직원이 env를 지우거나 다른 클라이언트를 쓰면 우회된다.
  우리는 AppArmor·UID 방화벽·게이트웨이 판정을 유지한다 — 이게 연구의 핵심이므로 단순화를 이유로 약화하지 않는다.
- IBM식 "직원이 JSON에 토큰 붙여넣기"는 버린다. 토큰이 설정 파일에 남고 손이 많다. 헤더 헬퍼(소켓/파이프) 유지.
- Windows ODR의 별도 에이전트 사용자 계정 격리는 우리의 "관리 계정 + 방화벽" 모델과 목적이 같다. 직원 계정이 관리자면
  ODR처럼 별도 계정을 자동 생성하는 방향으로 간다(아래 D-71).

## 적용 (D-71)

목표 흐름: **콘솔 로그인 → "내 PC 연결" → OS별 설치 파일 버튼 → 실행 → sudo/UAC 1회 → 끝.** 이후 평소 계정에서 `codex`·`claude`.

설치기(`endpoint-bootstrap`)가 승격 1회 안에서 대신 하는 일:
1. 필수 패키지 설치(gcc·nftables·AppArmor 도구). 없으면 배포 패키지 관리자로 설치.
2. 공식 Codex(같은 릴리스 `codex-code-mode-host` 포함)·Claude를 승인 경로에 배치하고 해시 검증. 키트에 동봉하거나
   관리자가 지정한 출처에서 받는다.
3. 직원 계정이 일반 계정이면 그 계정에 바로 적용. 관리자 계정이면 관리 계정을 자동 생성하고, 직원 계정의 `codex`·`claude`를
   관리 계정으로 실행하는 shim을 건다(별도 전환 없음). Windows는 비밀번호 없는 교차 계정 실행이 없어 일반 계정 생성 후 로그인 안내.
4. 프록시·헤더 헬퍼·관리형 설정 자동 구성. 실패하면 rollback 후 원인 한 줄.
5. 이미 설치돼 있으면 자동 rollback 후 재설치(같은 파일 한 번).
6. 끝에 관리 계정 컨텍스트에서 하네스 모델 로그인을 자동 안내·실행.

활성화는 관리자 콘솔 클릭 유지(소유자 결정 2026-10-04). 콘솔 "내 PC 연결"은 설명 문단 없이 OS별 설치 파일 버튼만.
