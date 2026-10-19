# 2026-10-20 사용자 명령 헬퍼 검사 PJ1 실기기 시험 (D-148)

- 기준: main c986fdd 배포, PJ1 관리 에이전트 파일을 저장소 판으로 교체(원본 백업 `/var/tmp/mint-agent-backup-20261020061038`), 시험 스크립트는 메인 scratchpad `d148_pj1.sh`·`d148b_pj1.sh`.
- 대상: PJ1 관리 계정 `managed-pj1`, 장치 `managed-5a714737-…`. 게이트웨이 상태는 `endpoint_agents`에서 읽었다.

## 결과

| 단계 | 1차(apiKeyHelper) | 2차(헬퍼 수정 후, Codex 프로필 notify) |
| --- | --- | --- |
| 새 에이전트 보고 | `user_command_helpers: true`, 표식 true | 같음 |
| 키 추가 → 다음 heartbeat | 격리, 발견 `.claude/settings.json`·`apiKeyHelper` | 격리, 발견 `.codex/*.config.toml`·`notify`(파일 이름 미노출) |
| 격리 중 하네스 호출 | Claude 자체가 apiKeyHelper 실패로 중단 | MCP 연결 실패 표시(헤더 헬퍼 자격 확인 안내), 인증 대기 캐시 없음 |
| 원복 | 준수 보고, 격리 유지 | 같음 |
| 관리자 재활성화 | active | active |
| 복구 뒤 호출 | **실패**: markitdown·context7·github가 `mcp-needs-auth-cache.json`에 남아 OAuth 인증 필요로 표시 | **성공**: markitdown 변환 정상 |

## 원인과 수정

격리 중 헤더 헬퍼가 자격 없이 종료하면 Claude Code는 인증 없이 연결해 401을 받고 OAuth 서버로 판단해 캐시한다. 공식 MCP 문서(code.claude.com/docs/en/mcp, 2026-10-20 조회)는 헬퍼가 `Authorization`을 내면 거부돼도 연결 실패로만 처리한다고 적는다. Linux·Windows 헬퍼가 자격을 못 얻으면 고정 값 `Bearer endpoint-not-active`를 내게 바꿨다. 1차 시험이 만든 캐시 파일은 백업(`/var/tmp/mint-d148-needs-auth-cache.json`) 뒤 지웠다.

## 남은 것

- PJ1 에이전트 파일은 저장소 판으로 교체된 상태다(정식 키트 재설치 절차는 미실행).
- Codex 하네스의 격리·복구 동작은 이번에 보지 않았다.
- 런처 `-c/--config`·`CODEX_HOME`·`CLAUDE_CONFIG_DIR` 고정은 다음 작업이다.
