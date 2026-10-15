# 2026-10-15 업스트림 MCP 세션 재사용 설계 비교

- 작업자: Claude Code(통합 세션이 시작한 하위 세션)
- 코드 기준: `b301e42`(`10/15-wbs-implementation`)에서 만든 브랜치 `10/15-upstream-session-reuse-design`. 제품 코드 변경 없음. 변경 파일: [설계 비교](../../analysis/upstream-session-reuse/README.md), [DECISIONS.md 제안](../../../../docs/ai/DECISIONS.md), [백로그 DEV-29](../backlog.md), [현황](../current.md), [솔루션 항목](../../solutions/README.md) 3건, 이 보고서
- 시작 근거: DEV-29, D-79, 10-15 지연 관찰(`decisions.timings`·`GET /api/latency`)
- 해결할 문제와 완료 조건: 세션 재사용·계약 목록 캐시·상태 의존 서버 지원의 지연 절감·위험·완화·시험 계획과 추천안을 근거와 함께 위키에 남기고 `check_wiki`를 통과한다. 구현은 사용자 결정 뒤.

## 결과

- 선택지 4개를 비교했다. 조사 중 찾은 **(d) 협상 판 고정**은 세션 수명을 바꾸지 않고 SDK 2.2.0의 `server/discover` 탐색 왕복(구형 서버)이나 핸드셰이크·종료 요청 전체(신형 서버)를 없앤다. 추천 순서는 (d) → (a) 세션 재사용(다운스트림 세션 단위, D-79 개정) → (b) 읽기 도구 한정 목록 캐시(별도 결정)다. github 원격 MCP 한 건 추정 3.0 s → 2.8 s → 2.25 s → 1.0 s.
- 규격 판단이 바뀌는 사실: MCP 2026-07-28 규격은 프로토콜 세션과 `initialize`를 없앴고 `tools/list`에 `ttlMs`·`cacheScope`를 요구한다. 세션 바인딩은 구형(`2025-11-25`) 서버를 위한 과도기 기능이다. 등록 서버 10개 중 9개가 구형, Gitea MCP 1.7.0이 신형이다.
- 숨은 위험 하나를 찾았다. SDK 2.2.0 `Client`는 기본으로 서버 `ttlMs`를 따르는 클라이언트별 응답 캐시를 켠다. 지금은 호출마다 새 `Client`라 무해하지만, 세션을 재사용하면 실행 직전 `list_tools()`가 조용히 캐시를 돌려줄 수 있다. 재사용 `Client`는 `cache=None`이어야 한다(불변식 I8, 시험 T7).
- 10-14 보고에서 "미열람·2차 자료"였던 ContextForge 레지스트리·ADR-032와 Microsoft mcp-gateway 세션 라우팅을 고정 커밋으로 읽어 대체했다. 결론(호출자 간 공유 금지, 다운스트림 세션 단위 바인딩)은 같다. ContextForge는 실행 전 업스트림 `tools/list` 재확인을 하지 않는다는 차이를 기록했다. Lunar MCPX는 서버당 공유 클라이언트(채택하지 않는 반례)로 확인했다.
- `DECISIONS.md`에는 D-번호 없이 "제안 (결정 대기)"로 넣었다. 같은 시각 다른 세션이 결정 번호를 쓰고 있어 채택 때 번호를 붙인다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python research/llm-wiki/tools/check_wiki.py` (2026-10-15) | 통과(오류·경고 0) | 명령 출력 |
| 소스 읽기 | 고정 커밋 정적 검토: 규격 `86f6e0c`, SDK `mcp==2.2.0` wheel(SHA-256 `bde982589473a060ae145e3406e9a5333fe538c97229ba841f5a7f92be004f81`), ContextForge `5735c9d`, Microsoft `3594c4e`, MCPX `7193eab` | 확인 | [설계 비교 2절](../../analysis/upstream-session-reuse/README.md) 행 링크 |
| 프로토콜 | — | 미실행 | — |
| 실제 모델·하네스 | — | 미실행 | — |
| upstream 효과 | — | 미확인 | — |
| 배포·정책 해시 | 배포 없음 | 해당 없음 | — |

## 실패·미완료·한계

- 지연 절감은 10-15 관찰 범위값의 산술 추정이다. `close` 구간과 탐색 왕복 비용은 측정하지 않았다.
- SDK·OSS는 정적으로 읽었고 실행하지 않았다. github 원격 MCP가 실제 협상하는 판, 하네스가 Gateway에 구형·신형 중 무엇으로 붙는지(신형이면 다운스트림 세션 ID가 없어 2단계 재사용이 일어나지 않음), mcp-email-server의 상태 의존 여부는 미확인이다.
- 시험 T1–T12는 계획이며 실행하지 않았다. 구형·상태 의존 서버 시험에는 실험실에 공개 OSS Playwright MCP 이미지를 더해야 한다.

## 다음 작업

- DEV-29: 사용자 결정 뒤 1단계 구현(연결 구간을 `discover`·`initialize`로 세분 기록, T12), 2단계 구현과 T1–T7·T9–T11, 3단계는 따로 결정 후 T8. 각 단계 배포 뒤 PJ1에서 승인된 github·context7으로 `GET /api/latency` 전후 비교.

## 사용자에게 필요한 입력

- 1단계 구현 승인 여부, 2단계로 D-79를 개정할지와 수명 값(유휴 60초·최대 10분), 3단계로 읽기 도구의 재확인을 30초 이내 확인으로 완화할지.
