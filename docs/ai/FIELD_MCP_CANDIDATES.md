# Field MCP 후보 및 기능 확장 (2026-09-28 조사)

이 목록은 **후보**다. field 기본 설치에는 어느 서버도 자동 등록하거나 연결하지 않는다. 원격 제공자의 OAuth, 데이터 전송, 도구 계약과 공급망 증거를 확인한 뒤 별도 승인해야 한다. 아래 주소는 웹 페이지가 아니라 MCP Streamable HTTP 엔드포인트다.

## 정상 원격 MCP 5종

| 후보 | 주소 | 시험할 경계 | 공식 자료 |
| --- | --- | --- | --- |
| GitHub MCP | `https://api.githubcopilot.com/mcp/` | 저장소 읽기와 쓰기 권한 분리, 사용자 토큰 | [GitHub 문서](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/extend-copilot-chat-with-mcp) |
| Linear 읽기 전용 | `https://mcp.linear.app/mcp/readonly` | OAuth 2.1, 읽기 전용 도구와 토큰 범위 | [Linear 문서](https://linear.app/docs/mcp) |
| Cloudflare 문서 | `https://docs.mcp.cloudflare.com/mcp` | 공개 문서 검색의 메타데이터·응답 검사 | [Cloudflare 문서](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/) |
| Microsoft Learn | `https://learn.microsoft.com/api/mcp` | 무인증 공개 원격 MCP, 변동하는 도구 목록 | [Microsoft 문서](https://learn.microsoft.com/en-us/training/support/mcp-developer-reference) |
| Atlassian Rovo v2 | `https://mcp.atlassian.com/v2/mcp` | OAuth 2.1, 도구 발견과 페이지네이션 | [Atlassian 문서](https://developer.atlassian.com/cloud/rovo-mcp/) |

## 알려진 취약 버전 2종

실행용이 아니라 **메타데이터 기반 차단 시험 후보**다. 실제 취약 패키지는 조직망이나 실사용 저장소에 연결하지 않는다.

| 패키지·버전 | 검증할 통제 | 근거 |
| --- | --- | --- |
| `@modelcontextprotocol/server-filesystem@0.6.2` | 허용 디렉터리 안의 심볼릭 링크를 통한 경로 검증 우회 탐지. `0.6.3` 이상 수정 계열과 비교 | [GHSA-q66q-fx2p-7w4m](https://github.com/modelcontextprotocol/servers/security/advisories/GHSA-q66q-fx2p-7w4m), [npm 버전](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem?activeTab=versions) |
| `mcp-server-git==2025.11.25` | `--repository` 제한 밖의 `repo_path` 접근 차단. `2025.12.18` 수정본과 비교 | [GHSA-j22h-9j4x-23w5](https://github.com/advisories/GHSA-j22h-9j4x-23w5), [PyPI 버전](https://pypi.org/project/mcp-server-git/2025.11.25/) |

## 엣지 케이스 3종

| 후보 | 주소·형태 | 점검할 상황 | 공식 자료 |
| --- | --- | --- | --- |
| MCP Feature Reference Server | `https://example-server.modelcontextprotocol.io/mcp` | OAuth, 도구·리소스·프롬프트, 대량 리소스의 페이지네이션과 세션 | [공식 예제 저장소](https://github.com/modelcontextprotocol/example-remote-server) |
| Cloudflare Browser Run | `https://browser.mcp.cloudflare.com/mcp` | 웹 콘텐츠와 스크린샷의 비신뢰 출력, 크기 제한·외부 목적지 | [Cloudflare 서버 목록](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/) |
| Microsoft Release Communications | `https://www.microsoft.com/releasecommunications/mcp` | 무인증, 브라우저 GET의 405와 정상 MCP 초기화 구분 | [Microsoft 문서](https://learn.microsoft.com/en-us/microsoft-365/admin/manage/mrc-mcp) |

## LiteLLM·BeyondTrust에서 가져올 다음 통제

- **LiteLLM**: 이 저장소에는 이미 선택형 LiteLLM 프록시와 직원별 가상 키가 있다. 팀별 예산·모델 허용목록·RPM/TPM·사용량 조회는 기존 PostgreSQL 연결을 이용해 확장할 수 있다. 예산 집행은 DB 없이 작동하지 않으므로 field 기본 설치에 빈 예산 UI를 추가하지 않는다. [가상 키](https://docs.litellm.ai/docs/proxy/virtual_keys), [예산 조건](https://docs.litellm.ai/docs/proxy/users)
- **BeyondTrust**: 기존 10분 승인 유효기간과 종료 시 자격 회수를 `신청 → 승인 → 실행 → 만료/폐기 → 감사`의 시간 제한 접근 흐름으로 화면에서 연결하는 것이 적합하다. 이번 field 개선은 가입 승인, 검증된 저장소 게시, A.I.G 작업 추적을 그 흐름에 더했다. 별도 BeyondTrust 서비스를 설치하지 않는다. [JIT 접근·승인](https://docs.beyondtrust.com/bt-docs/v26.2/docs/pra-jit-access-approvals)
