# LIB-K12 · NIST SP 800-52 Rev. 2: Guidelines for the Selection, Configuration, and Use of Transport Layer Security (TLS) Implementations

연방 시스템의 TLS 구현 선택·구성·사용 지침이다. 서버가 FIPS 기반 암호 스위트의 TLS 1.2를 지원하고 2024-01-01까지 TLS 1.3을 지원하도록 요구하며, 인증서·TLS 확장 지침을 준다. 서버 지침(§3)과 클라이언트 지침(§4)이 나뉘어 있다.

## 출처와 확인 수준

- 공식 출처: [NIST SP 800-52 Rev. 2: Guidelines for the Selection, Configuration, and Use of Transport Layer Security (TLS) Implementations](https://csrc.nist.gov/pubs/sp/800/52/r2/final)
- 관련 출처: <https://doi.org/10.6028/NIST.SP.800-52r2>
- 관련 출처: <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-52r2.pdf>
- 유형: 표준·RFC·권고 · 2019년 · NIST Special Publication 800-52 Rev. 2, 2019-08, 72쪽 · `official_publication`
- 저자·발행: Kerry A. McKay, David A. Cooper
- 판본: 2019년 8월판. CSRC 페이지에 '2026-05-07 계획 공지: 현재 검토 중(Crypto Publication Review Project)' 표시가 있다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: CSRC 페이지(초록·계획 공지), PDF 표지·고지·목차, §4.2.2 본문.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §3(서버)은 프로토콜 버전, 서버 키·인증서, 암호 지원, 확장, 클라이언트 인증, 세션 재개·early data를 다루고 §4(클라이언트)는 같은 항목을 클라이언트 관점으로 다룬다.
- §4.2.2: 클라이언트는 서버 인증서의 폐지 확인을 수행해야 하며(shall), 폐지 정보는 서버가 제공하는 OCSP 응답, 로컬 저장소의 CRL·OCSP, 설정된 OCSP 응답기, 인증서 AIA의 OCSP, CRL 배포점 등에서 얻는다.
- CSRC 페이지에 2026-05-07자 검토 중 공지가 있어, 후속 개정(Rev. 3 등)이 나올 수 있다. 추측한 Rev. 3 초안 주소(/r3/ipd)는 404였고 Rev. 3의 존재 여부는 확인하지 못했다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-16 | 전송 TLS |

## 우리 솔루션 개발에 사용할 곳

- **POL-16**: 게이트웨이가 TLS 클라이언트로 업스트림 MCP 서버 인증서의 폐지 확인(OCSP/CRL)을 하는지 확인할 기준(§4.2.2)과 서버 쪽 프로토콜 버전 요건(§3.1)을 RFC 9325와 함께 적용한다. 폐지 확인 실패 시 동작(열림/닫힘)을 정책으로 정하고 시험 항목으로 둔다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

PDF의 목차와 §4.2.2 본문, CSRC 페이지의 초록·계획 공지만 읽었다. 연방 정부 요구 중심이며 민간 도입의 의무가 아니다. 현재 검토 중이라 내용이 바뀔 수 있다. 우리 구성에 적용하지 않았다.

NIST 간행물: 미국에서 저작권 보호 대상이 아니며 출처 표기를 요청한다고 PDF에 적혀 있다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
