# LIB-K16 · Sigstore: Software Signing for Everybody

소프트웨어 서명을 널리 쓰이게 하려는 시스템 Sigstore를 제안한다. ACME와 비슷한 프로토콜로 OIDC를 통해 개발자를 인증해 서명을 기존 신원에 묶고, 일회용(ephemeral) 키로 키 관리 부담을 줄이며, 아티팩트·신원 로그로 투명성을 제공한다고 초록이 설명한다.

## 출처와 확인 수준

- 공식 출처: [Sigstore: Software Signing for Everybody](https://doi.org/10.1145/3548606.3560596)
- 관련 출처: <https://dl.acm.org/doi/10.1145/3548606.3560596>
- 유형: 논문 · 2022년 · Proceedings of the 2022 ACM SIGSAC Conference on Computer and Communications Security (CCS '22), pp. 2353–2367, ACM, 2022-11-07 · `official_publication`
- 저자·발행: Zachary Newman, John Speed Meyers, Santiago Torres-Arias
- 판본: ACM 판 2022-11-07 게재(Crossref). 초록은 OpenAlex·Semantic Scholar의 ACM 메타데이터로 대조
- 확인일: 2026-10-17 / `bibliographic_and_abstract_checked` — 서지와 초록을 출판사·집계 메타데이터와 대조했다(본문 정독 아님). 읽은 범위: Crossref 서지, OpenAlex·Semantic Scholar 초록 메타데이터. ACM 원문 미열람.
- 요약 검토: 초록을 원문·출판사 메타데이터와 직접 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 세 가지 메커니즘은 OIDC 기반 신원 연결, 일회용 키 서명, 아티팩트·신원 로그를 통한 사용자 검증이다.
- 초록은 공급망 침해(XCodeGhost, SolarWinds) 사례를 들어 서명의 낮은 채택률을 문제로 삼고, 쿠버네티스·Distroless 같은 핵심 소프트웨어에 대한 220만 건 이상의 서명을 보고한다.
- ACM 판은 CC BY 4.0(Crossref VoR 라이선스, OpenAlex·Semantic Scholar의 오픈액세스 표기)이다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-01 | 공급망 출처·취약점 대응 |
| POL-39 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-01**: '배포자의 서명이나 해시 등 승인된 방법으로 검증'에서 서명 검증 항목을 '서명자 신원(OIDC 발급자·주체)과 투명성 로그 포함 여부'까지 확장하는 근거다. 기록할 값: 서명자 신원, 로그 항목 식별자, 검증 시각(DEV-38 승인 소스 검증과 연결).
- **POL-39**: 서명 검증 실패·부재를 도입 보류 사유로 기록하는 시험 사례를 설계할 때 참고한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

ACM 디지털 라이브러리는 봇 차단(HTTP 403)이라 열지 못했다. 서지는 Crossref, 초록은 OpenAlex·Semantic Scholar의 집계 메타데이터로만 대조했고 논문 본문은 읽지 않았다. 현재 Sigstore 서비스 구성·정책은 확인하지 않았다.

CC BY 4.0 (Crossref 라이선스 정보). 저자·제목·출처를 표기한다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
