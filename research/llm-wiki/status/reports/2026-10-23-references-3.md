# 2026-10-23 레퍼런스 3종 조사 (Falcon Guardian · 젠아이랩스 · GensOps)

- 작업자: Claude Code(조사 레인, Sonnet 5.5)
- 코드 기준: `origin/main` `7b7ad6d`에서 분기한 `10/23-references-3`. 제품 코드 변경 없음, 문서·카탈로그·출처 목록만 추가
- 시작 근거: 소유자 지시(10-23) 「CrowdStrike Falcon Guardian / 젠아이랩스 AI-native 개발 사례 / GensOps 운영 관제 플랫폼을 참고 레퍼런스로 활용」
- 해결할 문제와 완료 조건: 세 대상을 공식 자료로 특정하고, MINT에 가져올 것·이미 있는 것·차별점·가져오지 않을 것을 근거와 함께 위키에 남긴다. 구현은 하지 않는다.

## 결과

| 지칭 | 특정 | 근거 |
| --- | --- | --- |
| Falcon Guardian | CrowdStrike가 2026-09-01 발표한 AI 에이전트 런타임 보안 제품(Falcon AIDR 후속) | 공식 보도자료·블로그(C1·C2) |
| 젠아이랩스 AI-native 개발 | 젠아이랩스(GenAI Labs) 사례 글 「AI-native 회사가 일하는 방법」(2026-10-01) | 공식 사이트(G1·G3) |
| GensOps | 같은 회사의 전사 운영 관제 플랫폼 v1.8.0(사내 운영, 외부 가입 없음) | 제품 페이지·사례 글·데모(G2·G3·G5) |

- 추가 카드 3개: [Falcon Guardian](../../solutions/crowdstrike-falcon-guardian.md), [젠아이랩스 AI-native 개발](../../solutions/genailabs-ai-native-dev.md), [GensOps](../../solutions/genailabs-gensops.md). `solutions/README.md`와 `catalogs/solutions.json`(3건 추가)에 반영했다.
- 비교·방향 제안 R-1~R-7: [references-1023 분석](../../analysis/references-1023/README.md). 출처 9건의 URL·확보 시각·SHA-256·읽은 범위는 [sources.json](../../analysis/references-1023/sources.json), 원본은 ignored `local-sources/references-1023/`.
- 공개 코드는 세 대상 모두 없다(공식 사이트에 저장소 링크 없음, `github.com/genailabs` 공개 저장소 0개·소유 관계 미확인). commit 고정 분석은 해당 없음.
- 정정: 분석 초안이 「허용 하네스 목록」 통제를 제안했으나 저장소 불변식(하네스 신원은 기록만, 판정에 쓰지 않음)과 충돌해 제안에서 제외하고 「가져오지 않을 것」으로 옮겼다.
- 재배포: 젠아이랩스 이용약관 제18조가 영리 목적 복제·배포를 제한하고 CrowdStrike 페이지는 저작권 표기가 있어, 원본은 공개 저장소에 두지 않고 요약·링크·해시만 두었다. 장문 인용 없음.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `check_wiki.py --ci-ignored-local-sources`, `check_trace.py` | 아래 「검사 결과」 | 터미널 출력 |
| 프로토콜 | 해당 없음(제품 시험 없음) | 미실행 | |
| 실제 모델·하네스 | 해당 없음 | 미실행 | |
| upstream 효과 | 해당 없음 | 미확인 | |
| 배포·정책 해시 | 해당 없음 | 미확인 | |

검사 결과는 이 보고서 말미에 기록한다.

## 실패·미완료·한계

- 세 대상의 기능은 모두 공급자·회사 주장이며 시험하지 않았다. 수치(테스트 수, 생산성, 비용 절감, 가동률)는 자체 기록이다.
- 미확인: Falcon Guardian의 호출 단위 MCP 통제, 콘솔 화면, 지원 OS(보도자료와 블로그가 다름), AI Gateway 출시, Falcon Complete GA 시점(2차 보도 일부가 달리 씀, 본문 미보존). GensOps의 승인 흐름이 코드로 강제되는지, 알림·수집 방식. GuardTrail 판정 로직. GenAI Shield 상세.
- 2차 보도 4건은 검색 결과 요약만 보았고 본문을 보존하지 않았다.
- MINT 쪽 「이미 있는 것」은 `docs/ai`와 위키 문서를 읽은 범위이며 코드·Console 화면을 새로 열어 확인하지 않았다.
- `status/backlog.md`는 바꾸지 않았다(제안은 작업 목록이 아님).

## 다음 작업

R-1~R-7은 소유자가 채택 여부를 정한다. 채택하면 R-1(시험 0건 통과 방지)부터 현재 실행기가 이미 막는지 확인하고 백로그에 ID를 부여한다.

## 사용자에게 필요한 입력

R-7(내장 도구 판정 범위 확장 여부)은 제품 범위 결정이므로 소유자 판단이 필요하다. 나머지는 없음.

## 검사 결과 (2026-10-23)

- `check_wiki.py --ci-ignored-local-sources`: 오류 0. 경고는 기존 ignored `local-sources/policy/*` 부재 안내뿐이며 이번 `references-1023` 원본은 존재한다.
- `check_trace.py`: 오류 0, 경고 6(기존 시점 보존 문서·참조 0 항목, 이번 변경과 무관).
