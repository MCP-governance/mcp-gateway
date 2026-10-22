# 2026-10-22 LiteLLM 중앙 MCP에서 MINT 추가 역할 분석

- 작업자: Codex
- 코드 기준: 원격 HEAD `main` 재확인, 시작 `62bafc49ec3f360415d229e24ee10b519c7cbe94`, clean에서 별도 브랜치 `10/22-litellm-mint-opportunities`. LiteLLM 고정 clone `f8e456d105af921213267d0ef801ca08b8fdbc0b`, package 1.102.0, clean.
- 시작 근거: 사용자 요청 “wiki에 코드분석한거랑 litellm 공식 기능설명에 있는거 읽어보고 … 가능성을 가져오라”; DEV-47.
- 해결할 문제: 중복 기능을 제외하고 MINT의 추가 역할·연동 형태·검증 조건을 근거와 연결한다.

## 결과

[정본 분석](../../analysis/litellm-mint-opportunities-20261022.md)에 읽기 범위·판본·기능 중복·세 후보·접점·한계·포기 조건을 기록했다. [공식 자료 manifest](../../analysis/litellm-mint-opportunities-20261022.sources.json)에 공개 HTML 8개를 URL·시각·SHA-256과 연결했다. 원본은 ignored local-sources에 두었다.

신규 구현은 없다. LiteLLM의 pin·사후 가드레일·등록 승인·자격 회수를 차별점으로 제시했던 범위를 줄였다. 10-20의 중앙 연동 예비 확인을 놓쳤던 대화도 정정한다. 원격 62bafc4까지의 변화는 위협 추적 문서이며, 기존 2045799 대비 이번 관련 제품 코드·심층 분석에 차이는 없었다.

## 검증

| 확인 종류 | 방법 | 결과 |
| --- | --- | --- |
| 자료 읽기 | 위키 심층 분석 전체·요약·연동 보고, 관련 MINT 코드와 고정 LiteLLM pre/post 경로 | 정적 확인, 범위는 분석 본문에 명시 |
| 공식 자료 | 현재 MCP 기능별 안내·1.103 릴리스·1.104 시점 OWASP 매핑 | 8개 HTML 확보·hash 기록, 판본 혼합 금지 |
| 문서 정합 | capture_status / build_wiki / check_wiki --ci-ignored-local-sources | HEAD 62bafc4, Markdown 648개, check_wiki ok=true·오류 0·경고 119. 경고를 제품 기능 통과로 해석하지 않음 |
| 신규 자료 정합 | HTML SHA-256 재계산·manifest JSON·신규 Markdown 상대 링크·git diff --check | HTML 8/8 hash 일치, 링크 유효, diff 공백 검사 통과 |
| 프로토콜·실제 모델·하네스·upstream 효과·배포 | 이번 미실행 | 기존 보고 결과를 이번 통과로 승격하지 않음 |

## 실패·미완료·한계

현재 공식 문서와 고정 1.102.0 코드의 차이를 최신 소스 전체 분석으로 메우지 않았다. 특히 pin·신규 세션 종료의 전체 현재 구현과 모든 plugin 입구는 미추적이다. 실제 중앙 승인·사용자 위임·차단 효과·원격 자격 회수·성능·고객 수요는 미확인이다. 제품 전체 부재나 MINT 우위를 단정하지 않는다.

## 다음 작업

DEV-47의 기존 동일 조건 재현과 DEV-43·44, DEV-38·76·77에 본 분석의 좁은 검증을 연결한다. 새로운 대형 구현 백로그를 만들거나 수치를 올리지 않는다.

## 사용자에게 필요한 입력

이번 분석에는 없음. 실제 검증에서는 대상 LiteLLM 판본·배포 설정과 승인된 업무/계정·MCP를 정해야 하며 비밀 값은 문서에 적지 않는다.
