# LIB-G10 · VIPER-MCP: Detecting and Exploiting Taint-Style Vulnerabilities in Model Context Protocol Servers

MCP 서버 도구 핸들러에서 에이전트가 넘긴 입력이 셸, 네트워크, 파일 연산으로 흘러드는 taint 형 취약점을 찾는 프레임워크 VIPER-MCP를 제안한다. 두 단계 정적 분석과 LLM 기반 입력 진화, 엔드투엔드 익스플로잇 검증을 결합해 실제 오픈소스 서버 저장소를 대규모로 스캔했다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [VIPER-MCP: Detecting and Exploiting Taint-Style Vulnerabilities in Model Context Protocol Servers](https://arxiv.org/abs/2605.21392)
- 유형: preprint · 2026년 · arXiv preprint · `preprint`
- 저자·발행: Pengyu Sun, Zifeng Kang, Qishu Jin, Enhao Huang 외
- 확인일: 2026-10-14 / `arxiv_abs_title_matched` — 제목·저자·최초 게시 연도를 공식 페이지와 대조했다.
- 요약 검토: 초록과 문장 단위로 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 39,884개 실제 오픈소스 MCP 서버 저장소를 스캔해 106건의 제로데이 취약점을 확인했다고 보고한다(저자 주장).
- 논문 시점 기준 67개의 CVE ID가 발급되었다고 보고한다.
- 기존 도구가 검증되지 않은 정적 경고만 내거나 고정 페이로드 템플릿에 머문다는 한계를 지적한다.

## 우리 솔루션 개발에 사용할 곳

- 서버 등록 심사 파이프라인에서 등록, 핸들러, 파라미터, 싱크로 이어지는 호출 경로를 정적 점검 규칙으로 옮겨 외부 서버 코드 심사에 활용한다.
- LLM 기반 PoC 생성은 격리 환경에서만 돌리도록 게이트웨이 심사 샌드박스의 요구사항으로 기록한다.
- 발견된 취약 싱크(셸, 파일, 네트워크) 범주를 게이트웨이 정책의 기본 거부 대상 도구 범주로 연결한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

WebFetch 요약으로 확인한 초록 수준만 반영했다. 저자들의 주장이며 독립 재현은 확인하지 못했다. 전문은 미정독이고, v2가 2026년 8월에 개정되었으며 제출일 표기가 검색 결과마다 달라 날짜는 arXiv에서 재확인이 필요하다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

arXiv non-exclusive distribution license 1.0

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
