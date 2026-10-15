# LIB-E05 · Transaction Tokens

신뢰 도메인 안에서 사용자 또는 워크로드의 신원과 인가 맥락을 호출 체인 전체에 전달하는 짧은 수명의 서명 JWT(트랜잭션 토큰)를 정의한다. 원래 요청의 맥락(예: 호출자 IP, 파라미터)을 담아 하류 서비스가 원 액세스 토큰을 재사용하지 않고도 검증할 수 있게 한다.

## 출처와 확인 수준

- 공식 출처: [Transaction Tokens](https://datatracker.ietf.org/doc/draft-ietf-oauth-transaction-tokens/)
- 유형: 명세·제안 · 2026년 · IETF Internet-Draft · `ietf_internet_draft`
- 저자·발행: A. Tulshibagwale, G. Fletcher, P. Kasselman
- 확인일: 2026-10-14 / `page_title_matched` — 제목을 공식 페이지와 대조했다.
- 요약 검토: 출처 페이지와 수치·용어를 대조하고 의심 문장은 원문으로 확인했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 토큰은 특정 트랜잭션에 묶이며 원 호출의 세부 정보를 담는다고 정의한다.
- 발급은 토큰 교환(RFC 8693) 기반의 트랜잭션 토큰 서비스가 맡고, 전달은 Txn-Token HTTP 헤더로 한다고 규정한다.

## 우리 솔루션 개발에 사용할 곳

- 게이트웨이가 MCP 도구 호출마다 트랜잭션 토큰을 발급해 하류 MCP 서버에 전달하면, 하네스의 원 액세스 토큰을 노출하지 않고도 원 요청 맥락을 넘길 수 있다.
- 트랜잭션 토큰 식별자를 게이트웨이 감사 원장 항목과 연결하면 다단계 호출의 근원 요청을 추적할 수 있다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다.

## 한계와 사용 조건

rev 11(2026-07-30) 데이터트래커 요약만 확인했고 본문 세부 조항은 읽지 않았다. 워킹그룹 상태는 Waiting for Write-Up이며 RFC는 아직 발행되지 않았다. 요약 초안은 조사 에이전트가 작성했고 위 검토 수준까지 확인했다. 발행처 표기는 확인하지 않았다.

라이선스 미확인: 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[서지 대조 기록](../analysis/evidence/references/reference-fill-2026-10-14.json) · [자료 확보 규칙](../methodology/source-protocol.md)
