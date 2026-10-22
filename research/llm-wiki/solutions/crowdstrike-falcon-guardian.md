# CrowdStrike Falcon Guardian — 공식 발표 문서 확인

확인일: 2026-10-23 · 확인 수준: 공급자 공식 보도자료·블로그 본문 읽기 · 제품 시험·코드 없음(상용, 코드 미공개).

## 대상 특정

사용자 지칭 "CrowdStrike Falcon Guardian"은 이름이 그대로 일치하는 제품이 있다. 2026-09-01 Fal.Con에서 발표한 AI 에이전트 런타임 보안 제품이며, 이전 제품 Falcon AI Detection and Response(AIDR)의 후속·상위 제품으로 소개된다([C1 보도자료](https://www.crowdstrike.com/en-us/press-releases/crowdstrike-unveils-falcon-guardian-ai-agent-security/), [C2 공식 블로그](https://www.crowdstrike.com/en-us/blog/falcon-guardian-defines-next-generation-of-ai-security)). Charlotte AI(SOC용 에이전트 제품군)는 다른 제품이므로 대상에서 제외했다. 사용자가 Guardian이 아닌 다른 Falcon 제품을 의도했는지는 확인하지 못했다(불확실성: 낮음).

## 공식 자료가 말하는 기능(요약)

| 구분 | 공급자 설명 | 상태 표기 |
| --- | --- | --- |
| 에이전트 발견·인벤토리 | 센서가 알려진·미등록(shadow) AI 에이전트를 찾고 실행·휴면 에이전트, 배포자, 보안 상태를 목록화 | 발표 시점 제공으로 서술 |
| 런타임 가시성 | 프롬프트·신원·도구 호출·스킬·MCP 서버를 하위 시스템 실행과 인과 사슬로 연결(「지원하는 에이전트」 한정) | 제공으로 서술 |
| 에이전트 접근 통제 | 관리 엔드포인트에서 실행을 허용할 에이전트 종류를 정하고 나머지는 실행 차단 | 제공으로 서술 |
| 탐지·대응 | 에이전트 세션과 하위 실행을 하나의 조사로 재구성, 영향 범위(blast radius) 산정, 악성 행위 자동 차단 | 제공으로 서술 |
| AI Gateway | 모델·서비스·MCP 인프라와의 통신에 대한 중앙 통제점. 사용자·에이전트·엔드포인트·신원·자산·보안 상태를 정책 판단에 사용 | 블로그: pre-beta, Q4 GA 계획 |
| 관리형 서비스 | Falcon Complete for Guardian(24/7 MDR)은 Q3 내 제공 예고, OverWatch Cross-Domain은 제공 중(Guardian 동시 보유 필요) | 일부 예고 |
| SIEM 연계 | 에이전트 텔레메트리를 Falcon Next-Gen SIEM에 1차 데이터로 적재 | 제공으로 서술 |

## 확인 범위와 불일치

- 지원 플랫폼: 보도자료는 Windows·macOS, 블로그는 Windows·macOS·Linux로 다르게 쓴다. 어느 쪽이 현재 범위인지 공식 자료만으로 정하지 못했다.
- 호출 단위 통제: 블로그는 MCP·도구 호출을 인과 사슬에 연결한다고만 쓰고, 개별 MCP 호출을 어떻게 검사·차단하는지는 설명하지 않는다. 미확인이다. 2차 분석 한 건은 MCP 서버 접근 통제를 로드맵으로 분류했으나 본문은 확인하지 않았다.
- 콘솔 화면: 공식 글에 화면 구성·탐지 대응 화면 설명이 없다. 화면 구성은 미확인이다.
- 성능·비용·「SIEM 비용 절감」 문구는 공급자 주장이며 검증하지 않았다. 블로그 면책 문구가 미출시 기능을 구매 판단에 쓰지 말라고 명시한다.
- 2차 보도(SiliconANGLE, BizTech 등)는 검색 결과 요약만 보았고 본문은 보존하지 않았다.

## MINT 관련 한 줄

OS 센서 기반으로 「어떤 에이전트가 어디서 무엇을 했는가」를 엔드포인트에서 보는 방식이다. MINT는 게이트웨이를 통과하는 MCP 호출을 실행 전에 판정한다. 관점이 다르며 비교·제안은 [references-1023 분석](../analysis/references-1023/README.md)에 둔다.

출처 해시·확보 시각은 [출처 목록](../analysis/references-1023/sources.json). 공급자 페이지 원본은 ignored `local-sources/`에만 두고 공개 저장소에는 요약·링크·해시를 둔다.
