# LIB-N05 · My Credentials, Please: Detecting Filesystem Capability Laundering in MCP Servers at Scale

로컬 MCP 서버를 클라이언트가 승인하면 서버 프로세스가 선언된 동작보다 넓은 호스트 파일 권한을 얻는 문제(파일시스템 능력 세탁)를 다룬다. 21,097개 서버를 정적·동적으로 점검해 취약 사례 150건을 확인하고 13건의 공시를 냈다고 보고한다.

## 출처와 확인 수준

- 공식 출처: [My Credentials, Please: Detecting Filesystem Capability Laundering in MCP Servers at Scale](https://arxiv.org/abs/2610.22301)
- 유형: preprint · 2026년 · arXiv preprint (제출 2026-10-15) · `preprint`
- 저자·발행: Zeqian Huang, Mingyue Tang, Aonan Guan 외
- 확인일: 2026-10-23 / `arxiv_api_abstract_read`
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 4,806개 선별 서버 중 16.4%가 기능 분류와 달리 파일시스템 능력을 보였고, Anthropic Git MCP 서버의 CVE 2건을 포함해 공시 13건을 냈다고 밝힌다.

## 우리 솔루션 개발에 사용할 곳

- MINT 직원 PC 키트의 로컬 MCP 승인(D-192)에서 이미지 승인과 별개로 서버가 접근할 수 있는 경로를 계약에 적는 근거로 쓴다.
- 도구 분류가 비파일 기능인 서버에도 파일 접근이 숨어 있을 수 있다는 점을 도입 심사의 능력 추출 항목에 반영한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

arXiv API의 초록·서지만 읽었다. 본문·실험 조건(모델·서버 판본·반복·오탐·미탐)·재현은 확인하지 않았다. 수치는 저자 보고이며 우리 환경 값으로 쓰지 않는다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[출처 manifest](../analysis/refs-update-1023/refs-update-1023.sources.json) · [자료 확보 규칙](../methodology/source-protocol.md)
