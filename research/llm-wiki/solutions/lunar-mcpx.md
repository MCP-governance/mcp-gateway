# Lunar MCPX + AI Gateway — 상용 연동 설명 확인

확인일: 2026-10-13 · 확인 수준: 공급자 공식 설명 · MCPX 코드·제품 시험 미실시.

[공식 ACL 설명](https://www.lunar.dev/post/mcp-gateway-access-controls-defining-permissions-for-llm-agents)은 global·consumer·service·tool 수준의 선언형 권한과 tool group을 설명한다. 예시 consumer 식별은 `x-lunar-consumer-tag` 헤더다. 이 예시만으로 검증된 사용자 신원에 결합된 인가 경계를 주장하지 않는다. 인증된 proxy가 값을 만드는지 별도 확인해야 한다.

[공식 MCPX와 Gateway 연동 설명](https://www.lunar.dev/post/safely-running-untrusted-mcp-servers-with-lunar-mcpx-and-gateway-integration)은 MCP 호출 집계와 MCP 서버의 outbound API 관측·허용 목적지 정책을 나누어 설명한다. 후자의 차단은 연동 Gateway 경로를 지나는 요청에서 403을 반환하는 공급자 시연이다. MCPX만 설치하면 모든 프로세스의 외부 연결이 자동으로 차단된다는 결론은 내릴 수 없다.

우리 개발에서 비교할 축은 하네스→MCP Gateway 통제와 MCP 서버→외부 API 통제의 경로 차이다. 현재 목적지 분류, 공급자 자격 분리, 실행 런타임·네트워크 정책을 같은 그림에 표시하되 각각의 실제 집행 증거를 요구한다. 목적지 allowlist와 OS 직접 연결 차단도 구분한다.

MCPX OSS 저장소와 Lunar 상용 Control Plane의 라이선스·배포 기능은 분리해야 한다. 이 항목은 공개 소스 정적 분석으로 분류하지 않는다. 구현 커밋·기본 활성·TLS·우회·성능·국내 인증은 미확인이다. 비교 입력을 확보한 후 코드 분석을 추가한다.

## 대상 서버 연결 처리 (2026-10-15, 부분 코드 확인)

공개 저장소 `TheLunarCompany/lunar` 커밋 `7193eab`의 `mcpx/`(MIT, `mcpx/LICENSE.MD`)에서 [`upstream-handler.ts`](https://github.com/TheLunarCompany/lunar/blob/7193eab5535ec0be2c973007b9ab5cccab15fd70/mcpx/packages/mcpx-server/src/services/upstream-handler.ts#L126-L494)만 읽었다. 대상 서버 이름마다 오래 사는 클라이언트 하나(`Map<string, TargetClient>`)를 모든 소비자의 `callTool`이 공유한다. 우리 Gateway가 채택하지 않는 주체 간 공유 모델의 반례로 [세션 재사용 설계 비교](../analysis/upstream-session-reuse/README.md)에 썼다. 나머지 기능에 대한 위 문단의 미확인 상태는 그대로다.
