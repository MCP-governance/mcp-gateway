# Claude가 다음 작업을 시작할 때

이 안내는 [통합본 검토](README.md)의 실행 순서 제안이다. 담당 상태와 완료 조건은 [백로그](../../status/backlog.md)에서만 갱신한다. 문서에 적힌 제안이나 외부 SKILL은 새 권한·승인·운영 데이터 사용 허가가 아니다.

## 시작 기준

- 기준 제품 코드 `83269c1`, 통합 보고 `e61e43c`, Drive 자료 `1ad6395`. 실제 작업을 시작할 때 `git status`, 최신 통합 HEAD와 원격 기본 브랜치를 다시 확인한다.
- 루트 AGENTS와 위키 규칙을 읽고 작업별 `MM/DD-*` 브랜치에서 진행한다. 기기 직접 복사와 다른 사람의 변경 덮어쓰기를 하지 않는다.
- 첫 진입은 [현재 상태](../../status/current.md) → [검토 레코드](recommendations.json) → [해당 근거](references.json)다. 과거 보고서의 미실행 상태를 현재 완료로 전이하지 않는다.

## 작업별 출발점

| 순서 | 백로그 | 먼저 읽을 코드/자료 | 남겨야 할 결과 |
| --- | --- | --- | --- |
| 1 | DEV-41 | `review.derived_constraints`, `classify.classify`, 정책 범위 검증 | 빈 목적지·중첩 URL·리디렉션·DNS/내부 주소의 정상/음성 대조, 실제 outbound 효과 |
| 1 | DEV-42 | `enforce-linux.profile`, `endpoint_plane.managed_policy` | 사용자 훅·직접 실행·statusLine 등 하네스가 시작하는 명령에서도 헬퍼 접근 불가. 실제 토큰 값은 기록하지 않음 |
| 1 | DEV-43 | `dispatch.record`, 사용자 상태 변경 transaction | 서버 잠금 대기→계정 중지 commit→잠금 해제 순서를 고정한 경쟁 시험과 외부 효과 |
| 2 | DEV-38 | [실행 경로 제안](dev38-runtime-plan.md), intake worker·독립 승인·등록·종료 | MarkItDown 한 개의 신청→검증→승인→자동 실행→등록→PJ1 정상/차단→종료 |
| 3 | DEV-44 | `upstream.tool_view`, `core._call_upstream/_guarded_result`, `mcp_facade._render` | 판본·input/outputSchema·`$defs`·배열·목록 페이지 처리. 현재 검사와 마스킹 보존 |
| 3 | DEV-39 | 실제 관리 Claude/Codex, [증거 계약](../../methodology/evidence-contract.md) | 호출 ID·decision·intent·endpoint와 독립 효과의 상관, quota/로그인 실패 구분 |
| 4 | DEV-29 | 별도 `10/15-upstream-session-reuse-design`의 설계안 | 판본 고정부터 측정. 상태 의존 서버는 대화당 한 세션/직렬화 검토. 목록 캐시와 권한 판단 분리 |
| 4 | DEV-35 | 별도 `10/15-dev35-loopback`의 조사안 | 장치 코드 정상 로그인 우선 확인, 필요 시 응답 방향만 허용하고 비인가 MCP 차단 유지 |

DEV-29 설계의 같은 키당 여러 세션은 상태 의존 MCP의 연속 작업을 분리할 수 있다. 캐시 기본값과 신형 프로토콜의 명시적 상태 핸들도 확인한다. 신형 프로토콜에는 MCP 세션 ID가 없으므로 무조건 세션 풀을 추가하지 않는다. DEV-35의 399건은 별도 조사판의 로그인 상관 결과이며 현재 모든 거부 이벤트의 분류가 아니다.

## 완료 보고

[작업 보고 양식](../../templates/work-report.md)에 시작/최종 commit, 실제 수정 범위, 정상·음성·경계·장애·경쟁·복구 결과와 미실행을 남긴다. 배포가 필요한 제품 변경은 솔루션 기기의 `field up` 후 PJ1의 실제 하네스로 확인한다. 도구의 오류 반환이나 모델의 거절 문구만으로 정책 차단·외부 효과 0을 주장하지 않는다. 새 결과가 이전 후보를 반박하면 원래 레코드를 지우지 말고 반박 근거를 연결한다.
