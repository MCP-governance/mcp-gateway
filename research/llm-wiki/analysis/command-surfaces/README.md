# 하네스가 셸로 시작하는 명령 표면과 관리 경계 (D-147, DEV-49·DEV-42)

- 조사일: 2026-10-20. 처음 목록(Codex luna)은 저장소 안 근거만 썼고, 공식 문서·고정 소스로 다시 대조해 정정했다.
- 대상 판본: PJ1 실기기 Claude Code 2.1.288·Codex CLI 0.160.0(아키텍처 고정값 2.1.282·0.157.0).
- 위협(RV-02): 하네스가 시작한 명령이 하네스 프로필 아래에서 헤더 헬퍼를 실행하면 게이트웨이 토큰을 얻는다. Bash 도구는 `-tool` 프로필로 분리됐다(D-104).

## 출처

| 출처 | 확보 | SHA-256(앞 16자) | 읽은 범위 |
| --- | --- | --- | --- |
| https://code.claude.com/docs/en/settings-reference.md | 2026-10-20 | `ceea02f535e42d16` | statusLine·disableAllHooks·allowManagedHooksOnly·apiKeyHelper·otelHeadersHelper·awsCredentialExport·awsAuthRefresh·fileSuggestion 항목, "Status line and file suggestion gates" |
| https://code.claude.com/docs/en/settings | 2026-10-20 | — (요약 조회) | 우선순위, 관리 설정의 잘못된 항목 처리 |
| https://developers.openai.com/codex/enterprise/managed-configuration.md | 2026-10-20 | `d139c3bd64dcebcc` | Requirements·managed_config 구분, `allow_managed_hooks_only` |
| https://developers.openai.com/codex/hooks.md | 2026-10-20 | `57166ef03e705973` | 훅 위치·신뢰·`[features].hooks` |
| https://developers.openai.com/codex/config-reference.md | 2026-10-20 | `fe48af085a53345c` | `notify` 형식 |
| openai/codex `rust-v0.160.0`(a956835), `rust-v0.157.0` | 2026-10-20 | — | `codex-rs/config/src/config_requirements.rs` `ConfigRequirementsToml.allow_managed_hooks_only`, `codex-rs/hooks/src/engine/discovery.rs` `HookDiscoveryPolicy::allows` (Apache-2.0) |

문서 원문은 재배포하지 않고 URL·해시·읽은 범위만 남긴다.

## 표면 목록

| 하네스·표면 | 관리 잠금 | MINT 적용 | 남은 경계 |
| --- | --- | --- | --- |
| Claude Code 사용자·프로젝트·플러그인 훅 | `allowManagedHooksOnly`(관리 전용) | 세 관리 경로(엔드포인트 정책·PC 키트·워크스테이션) | D-112 PJ1 음성 시험 |
| Claude Code `statusLine`·`subagentStatusLine`·`fileSuggestion` | 같은 키가 관리 값만 남긴다(관리 값이 없으면 꺼짐) | 위와 같음 | 대화형 화면 실기기 미시험 |
| Claude Code `apiKeyHelper`·`otelHeadersHelper`·`awsCredentialExport`·`awsAuthRefresh` | 관리 전용 잠금 키 없음. 형식이 문자열이라 `null`은 잠금이 아니다 | 두지 않음(관리 값으로 덮으면 모델 인증이 바뀜) | AppArmor. 이 경로의 프로필 전환은 실기기 미확인 |
| Claude Code 관리 밖 MCP 서버(stdio 명령 포함) | `allowManagedMcpServersOnly`·`allowedMcpServers` | 기존(D-53) | — |
| Codex 사용자·프로젝트·세션·플러그인 훅 | `requirements.toml` 최상위 `allow_managed_hooks_only = true` | 세 관리 경로 | PJ1 기준선: 훅 bash가 `-codex-tool` 프로필에서 `touch` 실행 거부 |
| Codex `notify` | 요구 사항 키 없음. `managed_config.toml`은 사용자가 바꿀 수 있는 기본값 | 두지 않음 | AppArmor. 실기기 미확인 |
| Codex 관리 밖 MCP 서버 | `requirements.toml` `[mcp_servers.*].identity` | 기존 | — |
| Codex `shell_environment_policy` | 환경 변수 상속 범위일 뿐 새 명령 표면이 아니다 | — | — |
| 사용자 슬래시 명령·스킬 | 프롬프트 확장이며 실행은 도구(Bash)를 거친다 | — | `-tool` 프로필(D-104) |

## 실기기 확인

- 2026-10-20 배포 전 기준선(PJ1, `managed-pj1` Codex 홈에 사용자 `hooks.json`, `codex exec --dangerously-bypass-hook-trust`): SessionStart·UserPromptSubmit 훅이 발견·실행됐고 둘 다 실패했다. dmesg: `profile="mcpgw-managed-pj1-codex-tool" name="/usr/bin/touch" ... DENIED`. 표식 파일 없음.
- 2026-10-20 배포 후(a61c7fa, PJ1 요구 사항 파일 05:34 갱신): 같은 시험에서 `hook:` 줄이 없고 표식도 없다. 훅이 발견 단계에서 제외됐다. 같은 세션의 정상 응답과 context7 MCP 호출(게이트웨이 경유)은 유지됐다.
