# Field MCP 후보 및 기능 확장 (2026-09-28 조사)

이 목록은 **후보**다. field 기본 설치에는 어느 서버도 자동 등록하거나 연결하지 않는다. 원격 제공자의 OAuth, 데이터 전송, 도구 계약과 공급망 증거를 확인한 뒤 별도 승인해야 한다. 아래 주소는 웹 페이지가 아니라 MCP Streamable HTTP 엔드포인트다. 승인한 뒤에는 도입 신청의 **Gateway 등록**에 이 주소를 넣는다(D-49). Gateway는 upstream에 자격을 싣지 않으므로(`upstream.py`), 지금 그대로 등록되는 것은 무인증 공개 서버(Microsoft Learn — 실측, Cloudflare 문서, Microsoft Release Communications)다. OAuth가 필요한 서버는 제공자 쪽 서비스 계정을 가진 사내 프록시 뒤에 두어야 한다.

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

## LiteLLM·BeyondTrust에서 가져온 통제

- **반영(D-49) — LiteLLM의 서버 제출→승인과 설정+런타임 서버 합집합**: 승인한 도입 신청을 Console에서 Gateway에 등록한다. 도구별 권한·데이터 등급을 정하고, 관리자가 검토한 계약 해시가 등록 순간과 다르면 거부한다(LiteLLM의 "승인 뒤 무재검증"은 가져오지 않음). 2026-09-28 솔루션 기기에서 **Microsoft Learn**을 이 절차로 등록해 실제 Claude Code가 Gateway를 거쳐 `microsoft_docs_search`를 호출했다(판정 허용, 등급 공개).
- **반영(D-49) — BeyondTrust의 기한 있는 접근(요청 → 승인 → 사용 → 만료 → 감사)**: 등록마다 사용 기한(30일~1년)을 두고, 지나면 기존 `P-APPROVAL-EXPIRY-001`이 호출을 막는다. 연장·해제는 **MCP 서버** 화면에서 하며 이력은 등록 파일에 남는다. 해제·만료 뒤 회수 확인은 기존 종료·폐기 절차(`UR-<ID>`)로 잇는다. 별도 BeyondTrust 서비스를 설치하지 않는다. [JIT 접근·승인](https://docs.beyondtrust.com/bt-docs/v26.2/docs/pra-jit-access-approvals)
- **남은 후보 — LiteLLM 예산·모델 허용목록**: 선택형 LiteLLM 프록시와 직원별 가상 키가 이미 있다. 팀별 예산·RPM/TPM·사용량 조회는 field에서 LiteLLM을 띄우는 결정(D-44의 되돌릴 조건)이 먼저라, field 기본 설치에 빈 예산 UI를 추가하지 않는다. [가상 키](https://docs.litellm.ai/docs/proxy/virtual_keys), [예산 조건](https://docs.litellm.ai/docs/proxy/users)
- **남은 후보 — 이용 관계별 도구 허용 목록**: BENCHMARK_LITELLM.md 4절 2번.
