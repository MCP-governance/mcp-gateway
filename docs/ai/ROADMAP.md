# 남은 일과 한계

> 우선순위 순. 끝낸 항목은 지우지 말고 `~~취소선~~ (커밋)`으로 남긴다.

## 1. 다음에 할 일

1. **엔드포인트 평면의 차단** — 지금은 섀도 MCP를 *발견*하고 증적만 강화한다(`MCP-SHADOW-*`).
   ws-nkk의 `fs-direct`가 동작하지 않는 이유는 망 분리(office↛tools)이지 에이전트의 차단이 아니다.
   실제 조직에서는 egress 허용목록·DNS가 해야 한다 → `docs/design/CONTROL_PLANES.md`.
2. **v1 잔재 테이블 정리** — `agent_sessions`, `agent_runs`, `agent_gateway_receipts`(쓰지 않음).
   `agent_tables.sql`에서 CREATE를 빼고 `v2_tables.sql`에 DROP … IF EXISTS.
3. **도입 신청 → 레지스트리 연결** — 승인된 신청은 아직 `catalog.toml`에 자동으로 들어가지 않는다(사람이
   카탈로그·compose·잠금을 편집). 승인 시 카탈로그 초안(PR)을 만드는 흐름이 필요하다.
4. **공급망 검사와 v2 서버** — `intake_worker`의 서버 검사는 `source_ref`를 git ref로 가정한다. v2의
   `source_ref`는 `패키지@버전`이다. npm/PyPI 아티팩트를 받아 SBOM을 만드는 경로가 필요하다.
5. **제공자 증명 양식** — `provider-attestation` 증거는 자유 서술이다. 대상 식별자·시점·서명 필드를 강제하면
   C4 판단을 자동화할 수 있다.
6. **E1의 자원 서버 모사 확대** — 지금은 "서명만 검증하는 자원 서버" 하나. introspection을 캐시하는 서버
   (TTL 동안 수락)를 추가하면 C3 공백의 스펙트럼을 보여 줄 수 있다.
7. **Console 부가 기능** — 활동 로그 CSV 내보내기, 케이스 판정 이력 비교, 관찰 모드 요약(`/api/monitor/summary`) 화면.
8. **CI 시간** — `verify` job이 MCP 런타임 이미지를 매번 빌드한다. GHCR 캐시(`docker/build-push-action` + cache-to)로 줄일 수 있다.

## 2. 알려진 한계 (의도적으로 남김)

- 합성 로그인은 조직 SSO가 아니다. 비밀번호는 모두 `test-password`.
- Compose 내부망은 호스트 방화벽·tailnet ACL이 아니다. 여러 호스트로 나누면 `docs/design/NETWORK.md`의
  설계가 선행되어야 한다.
- LLM 모드의 업무 결과는 qwen2.5:1.5b 품질에 좌우된다. 정책 검증은 scripted 모드로 한다.
- 종료 판정의 C1은 제공자 고지에 의존한다. 고지가 없으면 T3이고 엔진은 T1을 주지 않는다 — 구현의
  한계가 아니라 논문이 특정한 구조적 한계다. 도입 시 종료 조건 합의가 유일한 완화.
- `server_version`은 mcp-proxy가 자기 SDK 버전을 보고한다(D-03). 패키지 버전 고정은 이미지 빌드가 보장한다.

## 3. 처리한 것 (2026-09-25)
- ~~origin/main의 PDF 통합(cc086e5·45b9f6e) 병합: Presidio 입력 검사·출력 마스킹, MCP-DATA-EGRESS-001, P-CHAIN-001, 위험 점수, 정책 재생을 v2 구조로 이식(D-20~D-23)~~

## 3-1. PDF 통합에서 이어서 할 일
- Presidio 인식기 정확도를 실제 한국어 업무 문서로 측정(현재는 합성 식별자 정규식 + 기본 인식기 일부).
- 위험 점수를 Console 목록 정렬·경보 기준으로 쓰기(지금은 표시만, 판정 근거 아님).
- 정책 재생 결과를 Console에서 보기(지금은 `reports/policy-replay.json`).

## 4. 처리한 것 (2026-09-24)
- ~~Console 전면 재작성, 종료 판정 워크스페이스~~ (5567111)
- ~~Gateway 읽기 API 인증, Console 프록시 역할 경계~~ (5567111)
- ~~프로브 호출이 모집단을 불리는 문제~~ (5567111)
- ~~`/mcp/` 401 + RFC 9728 챌린지, 승인형 예외가 실행되지 않던 문제, acceptance v2, 보안 회귀, 검사기, CI 재작성, v1 잔재 삭제~~
