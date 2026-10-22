# P1 승인·철회 동기화 구현 근거 (2026-10-23)

- 작업: AIG-01-LITELLM-SYNC. 브랜치 `10/23-litellm-sync`, 시작·최종 확인 기준 `e30be961a9a00d7982dd8565e4412c7289e85f4d`.
- 기존 D-191의 `addon.py`·`addons/litellm/*`·`tests/ai_gateway_addon_check.py`를 먼저 읽었다. 호출 판정과 관리 상태 동기화는 별도 경로다. 기존 시험 파일과 기대값은 수정하지 않았다.
- 결정 D-208, [운영 계약](../../../../docs/ai/LITELLM_SYNC.md), [보고](../../status/reports/2026-10-23-litellm-sync.md), [원자 요구사항](sync-requirements.json), [로컬 검증](sync-evidence.json).

## 판본과 읽은 범위

이전 설계 README의 LiteLLM 1.102.0 `f8e456d105` 근거는 이력으로 유지한다. 이번 P1 API 계약은 공식 **v1.105.0** 태그를 읽고, [공식 릴리스](https://github.com/BerriAI/litellm/releases/tag/v1.105.0)가 연결한 commit **`80b9556dd312d18c535ae06884faa97d1fdb8f46`**로 식별했다(릴리스 2026-10-11). 다음 행 번호는 web 도구가 반환한 태그 원문의 **0 기준 줄 번호 + 1**이다.

| 공식 파일 | 읽은 심볼·행(1 기준) | 적용·한계 |
| --- | --- | --- |
| [`mcp_management_endpoints.py`](https://raw.githubusercontent.com/BerriAI/litellm/v1.105.0/litellm/proxy/management_endpoints/mcp_management_endpoints.py) | `get_mcp_gateway_sessions`·`delete_mcp_gateway_sessions` 1329–1383 | GET/DELETE `/v1/mcp/sessions`, user_id 또는 session prefix, 워커 범위. 서버별 선택자는 없음 |
| 같은 파일 | `fetch_mcp_server` 1575–1657, `add_mcp_server` 1658–1745, `edit_mcp_server` 2729–2768 | 서버 GET·POST·PUT. proxy admin 생성은 active지만 runtime 갱신 실패가 성공 응답으로 남을 수 있어 다시 읽음 |
| 같은 파일 | `remove_mcp_server` 2175–2235 | 서버 DELETE. 키·팀 정리를 자동 완료한다고 가정하지 않음 |
| 같은 파일 | `delete_mcp_user_credential` 2271–2297, `delete_mcp_oauth_user_credential` 2366–2401, `list_mcp_server_user_credentials` 2504–2526 | admin user_id 선택 삭제, 서버별 자격 소유자 목록. OAuth status GET은 호출자 본인 범위라 다른 사용자의 확인으로 오용하지 않음 |
| [`server.py`](https://raw.githubusercontent.com/BerriAI/litellm/v1.105.0/litellm/proxy/_experimental/mcp_server/server.py) | `_gateway_session_for`·`get_mcp_gateway_sessions_report` 1177–1212, `terminate_mcp_gateway_sessions` 1241–1250 | 워커 PID·사용자·세션 prefix. live stateful streamable HTTP만 집계하며 SSE/stateless와 다른 워커를 증명하지 않음 |
| [`key_management_endpoints.py`](https://raw.githubusercontent.com/BerriAI/litellm/v1.105.0/litellm/proxy/management_endpoints/key_management_endpoints.py) | `_update_key_row_with_soft_budget` 2260–2269, `info_key_fn` 4039–4163 | 키 해시 조회·갱신, 응답 object_permission 확인. raw 키를 URL에 넣지 않음 |
| [`team_endpoints.py`](https://raw.githubusercontent.com/BerriAI/litellm/v1.105.0/litellm/proxy/management_endpoints/team_endpoints.py) | `update_team` 1950–1955·2319–2329, `team_info` 4485–4492·4553–4588 | 팀 권한·현 구성원 재조회. 이메일만 있는 구성원은 신원 매핑 완료로 세지 않음 |
| [`proxy_server.py`](https://raw.githubusercontent.com/BerriAI/litellm/v1.105.0/litellm/proxy/proxy_server.py) | `get_config_general_settings` 17116–17172 | `/config/field/info`의 field_value로 명시적 키 접근 설정 확인. 설정을 쓰거나 경계를 완화하지 않음 |

[공식 권한 문서](https://docs.litellm.ai/docs/mcp_control)의 도구 권한·명시적 키 접근과 [개인별 자격 문서](https://docs.litellm.ai/docs/mcp_per_user_auth)의 `(user_id, server_id)` 저장 경계도 읽었다. 이 두 문서는 변경 가능한 현재 문서이며 1.105 소스와 동일한 판본으로 간주하지 않는다. 위 표는 소스 열람이며 실행 증거가 아니다.

네트워크 제한으로 로컬 다운로드·원격 HEAD 조회와 immutable commit raw URL 확보는 실패했다. 태그 원문은 web 도구로 열람했고 commit 대응은 공식 릴리스에서 확인했다. **원문 전체 SHA-256·commit URL 바이트 동일성은 확보하지 못했다.** 자체 분석과 로컬 변경 파일의 해시는 `sync-evidence.json`에 남긴다. 원문을 재배포하지 않았다.

## OSS·공개 스킬 검토

GitHub 공개 스킬과 LiteLLM MCP 관리 연동을 검색했다(`site:github.com SKILL.md litellm mcp governance`). 이번 범위를 수행하는 검증된 전용 스킬은 확보하지 못했고 외부 SKILL·스크립트는 실행하지 않았다. LiteLLM 공식 OSS의 관리 API를 사용하며 MCP 서버나 ACL 엔진을 새로 만들지 않았다. 기존 Python 표준 라이브러리 HTTP·TLS·asyncio와 MINT DB·append-only 사건 API로 필요한 연동만 구현했다.

공식 [라이선스](https://raw.githubusercontent.com/BerriAI/litellm/v1.105.0/LICENSE)는 enterprise 디렉터리를 별도 라이선스로 분리하고 그 밖을 MIT로 둔다. 조사한 심볼은 `litellm/` 아래다. 공식 v1.105 릴리스와 후속 공개 활동이 유지보수의 관측 근거이며 장래 지원 보장은 아니다. 스킬 인기 수치와 GitHub 별 수로 채택을 결정하지 않았다. 실제 고객 라이선스·관리 API 권한·인증 설정은 실기기 검수 항목이다.

## 설계와 실패 조건

제공된 `supabase:supabase-postgres-best-practices` 스킬의 `lock-short-transactions`·`lock-advisory` 지침을 DB 검토에 적용했다. 외부 HTTP 동안 행 잠금과 DB 트랜잭션을 유지하지 않는 이유는 MINT의 중지·폐기 enqueue를 지연시키지 않기 위해서다. [PostgreSQL 18 공식 문서 §13.3.5](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS)의 세션 잠금은 commit 뒤에도 유지되고 명시 해제 또는 연결 종료로 풀린다는 계약을 확인했다. DB 실행 검증이나 Supabase 서비스 연결을 뜻하지 않는다.

등록 완료 훅과 5초 상태 대조를 함께 사용한다. 대기열은 서버 ID로 모으고 최신 MINT 상태를 실행 전에 다시 산출한다. 공급망 중지·DISABLED·종료 상태·기한 만료는 철회가 우선한다. 도구 권한은 `object_permission.mcp_tool_permissions`에 넣고 관계없는 권한을 보존한다. 키/팀은 명시적 매핑과 실제 LiteLLM 소유자/구성원을 대조한다. 잘못된 소유자는 권한을 부여하지 않으며 생성한 자체 경로를 제거한다.

성공·실패는 독립된 `litellm-sync` 사건이다. 성공은 원장 쓰기와 대기열 갱신이 함께 커밋된 재조회 관측을 뜻한다. G5 범위는 설정된 LiteLLM 관리 상태이며 외부 공급자 자격 폐기나 종료 등급 전체가 아니다. HTTP 요청 성공 뒤 잘못된 재조회, 워커별 잔존 경로/세션, 자격 잔존, 전파 중 MINT 철회, 모집단 소실은 실패한다. 모집단 소실은 자동 재시도만으로 해소하지 않는다.

세션 advisory lock은 별도 연결에서 전체 전파를 직렬화한다(`DB_POOL_MAX>=2`). 각 HTTP 요청 때 DB 트랜잭션은 열어 두지 않으며 결과·원장만 짧은 트랜잭션에서 커밋한다. 더 최신 enqueue revision이 있으면 이전 시도는 실패로 기록하고 최신 대기 상태·재시도 시각을 덮어쓰지 않는다. 잠금 획득 직후의 취소도 해제를 시도하며 해제 실패 시 연결을 닫는다. 대역 시험은 트랜잭션 밖 HTTP·revision 경쟁·취소 시 해제 호출을 확인하며 실제 PostgreSQL 경합 증거를 대신하지 않는다.

실제 PostgreSQL 잠금·롤백·프로세스 중단, LiteLLM 1.105 분산 캐시 및 실제 호출 가능 여부, 브라우저 렌더링과 PJ1 하네스는 미실행이다. 현재 자동 신규 등록은 자격 없는 HTTP upstream까지다. 인증이 필요한 MCP·stdio를 동작시키려고 자격이나 직원 신원을 낮추지 않는다. 상세 한계와 필요한 설정은 운영 계약에 남겼다.
