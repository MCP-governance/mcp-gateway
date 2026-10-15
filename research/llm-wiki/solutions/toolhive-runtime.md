# ToolHive 런타임 재사용 검토

확인일 2026-10-15. 고정 판본 `v0.54.0`, 검토 commit `14c6066a4d62aa07c090b27804d20d190a334a45`, Apache-2.0. [공식 릴리스](https://github.com/stacklok/toolhive/releases/tag/v0.54.0), [고정 라이선스](https://github.com/stacklok/toolhive/blob/14c6066a4d62aa07c090b27804d20d190a334a45/LICENSE). 실제 설치·운영 성능·전이 의존성의 전체 라이선스 검수는 하지 않았다.

## DEV-38에서 검토할 범위

[공식 개요](https://docs.stacklok.com/toolhive/)의 컨테이너 실행·수명 관리·권한·비밀·네트워크 격리를 재사용 후보로 삼는다. MINT의 독립 승인, 사용자/자산 권한, OPA, 계약 잠금, 감사 원장, C1~C4/T1~T3를 대체하는 안은 아니다. 선택 전에 기존 Docker 실행기와 필요한 연동 코드·운영 의존성을 비교한다.

| 가져올 후보 | 확인할 경계 |
| --- | --- |
| 컨테이너 실행·정지·복구 | 승인 source→image digest→runtime ID→MINT endpoint 근거 유지 |
| stdio 브리지 | HTTP 노출 범위와 오류/취소·종료, 주체 간 상태 분리 |
| permission profile | 기본 network가 아니라 명시한 mount·capability·목적지 집합 |
| secrets 연동 | 직원 MCP 토큰과 업무 자격 분리, 회전/철회·로그 노출 검사 |

## 기본값과 한계

[Custom permissions](https://docs.stacklok.com/toolhive/guides-cli/custom-permissions)의 custom server 기본 network profile은 outbound 전체 허용이므로 승인 목적지 제한을 따로 설정해야 한다. [Network isolation](https://docs.stacklok.com/toolhive/guides-cli/network-isolation)은 HTTP/HTTPS egress proxy 기반이며 raw TCP 데이터베이스 통신까지 같은 방식으로 보호한다고 가정하지 않는다. client 자동 등록이 직원 하네스에 직접 endpoint를 추가하면 MINT 강제 경로가 깨질 수 있으므로 채택 범위에서 제외한다.

[공개 공식 스킬](https://github.com/stacklok/toolhive/blob/14c6066a4d62aa07c090b27804d20d190a334a45/skills/toolhive-cli-user/SKILL.md)은 문서 탐색 대상으로만 읽었다. 설치·명령·에이전트 실행 지시로 적용하지 않았다.

BuildKit `v0.34.0`도 빌드 후보일 뿐이다. [공식 rootless 설명](https://github.com/moby/buildkit/blob/v0.34.0/docs/rootless.md)의 `--oci-worker-no-process-sandbox`는 프로세스 격리 제약 때문에 비권장이다. Gateway에 Docker socket을 붙이거나, 빌드 작업에 업무 자격을 넣는 근거로 쓰지 않는다.

도입 여부와 rollback 조건은 구현 전 DECISIONS에서 정하고 [DEV-38 검수](../analysis/review-2026-10-15/dev38-runtime-plan.md)로 확인한다. 현재는 후보 상태다.
