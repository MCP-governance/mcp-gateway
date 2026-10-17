# LIB-K09 · OWASP Cheat Sheet Series: Server-Side Request Forgery Prevention Cheat Sheet

SSRF 방어 지침이다. 애플리케이션이 신뢰하는 식별된 대상에만 요청하는 경우(허용목록)와 임의 외부 주소로 요청해야 하는 경우(차단목록)를 나눠, 애플리케이션 계층의 입력 검증과 네트워크 계층 방어를 함께 쓰는 심층 방어를 설명한다.

## 출처와 확인 수준

- 공식 출처: [OWASP Cheat Sheet Series: Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- 관련 출처: <https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md>
- 유형: 지침 · 2026년 · OWASP Cheat Sheet Series (CheatSheetSeries 저장소, 마지막 변경 커밋 5a2c4d9dc550, 2026-10-04) · `official_publication`
- 저자·발행: OWASP Cheat Sheet Series 기여자
- 판본: 저장소 master의 해당 파일, 마지막 변경 커밋 5a2c4d9dc550(2026-10-04)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: Markdown 원문의 도입·Case 1·Case 2·목차·참고, 저장소 LICENSE.md, 파일 최종 커밋.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 허용목록이 가능하면 IP·도메인·URL 입력을 형식 검증한 뒤 허용된 대상과 엄격 비교하고, 리다이렉트 추종을 끄라고 한다. 도메인 이름 검증용 DNS 조회는 DNS 핀닝(합법 도메인을 내부 IP에 묶는 공격)과 정보 노출 위험이 있다고 경고한다.
- 허용목록을 쓸 수 없는 경우(웹훅 등)는 사설망·루프백·링크로컬 범위를 막는 차단목록이 차선이며 애플리케이션 계층에서 걸러내기가 어렵다고 설명한다. 네트워크 계층 방어 절이 따로 있다(본문은 읽지 않았다). 문서에는 AWS IMDSv2와 'Deny-list (Last Resort)' 절도 있다.
- 문서 구성은 Case 1(식별된 신뢰 앱), Case 2(임의 외부 주소), 각각 Application layer·Network layer 방어다. 라이선스는 CC BY-SA 4.0이다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-10 | 목적지 DNS·서버 outbound |
| POL-26 | 목적지 DNS·서버 outbound |
| POL-40 | 목적지 DNS·서버 outbound |
| POL-24 | 목적지 DNS·서버 outbound |

## 우리 솔루션 개발에 사용할 곳

- **POL-10**: 'DNS·리디렉션·OAuth 조회를 포함한 실제 연결 주소 검증'의 근거다. 호스트 이름 문자열만 보지 않고 해석된 IP를 확인하며 리다이렉트를 따르지 않는 시험(E05 SSRF 정규화)을 설계한다.
- **POL-26·POL-40**: 승인된 외부 수신처만 허용하는 Case 1 방식을 서버 outbound에 적용하고, 승인 대상이 바뀌면 재승인하는 흐름과 연결한다. 임의 외부 주소가 필요한 도구는 Case 2의 차단목록과 네트워크 분리를 함께 요구한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

Markdown 원문의 Case 1·Case 2 본문과 목차를 읽었다. 코드 예제, Orange Tsai 자료, Semgrep 규칙 절은 읽지 않았다. 우리 게이트웨이·서버 outbound에 적용해 시험하지 않았다.

CC BY-SA 4.0 (CheatSheetSeries 저장소 LICENSE.md). 파생물에는 같은 조건이 적용된다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
