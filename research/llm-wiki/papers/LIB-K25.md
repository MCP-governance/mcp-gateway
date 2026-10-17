# LIB-K25 · OWASP Cheat Sheet Series: Secrets Management Cheat Sheet

비밀(토큰·API 키·인증서 등) 관리 지침이다. 중앙화·접근 통제·자동화·감사·수명 주기(생성·교체·폐기·만료), CI/CD·클라우드·컨테이너 환경, 탐지와 사고 대응을 다룬다.

## 출처와 확인 수준

- 공식 출처: [OWASP Cheat Sheet Series: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- 관련 출처: <https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets/Secrets_Management_Cheat_Sheet.md>
- 유형: 지침 · 2026년 · OWASP Cheat Sheet Series (마지막 변경 커밋 9550b74f43f2, 2026-10-04) · `official_publication`
- 저자·발행: OWASP Cheat Sheet Series 기여자
- 판본: 저장소 master의 해당 파일, 마지막 변경 커밋 9550b74f43f2(2026-10-04)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 목차, §2.4, §2.6, §2.7, §2.9, §9.2 본문, 파일 최종 커밋.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §2.7.3 폐기: 더 이상 필요 없거나 유출 가능성이 있는 비밀은 안전하게 폐기해 접근을 막아야 하며, TLS 인증서는 인증서 폐지도 포함한다. §2.4는 애플리케이션 재시작이 유출된 자격을 폐기하지 않으며 백엔드 서비스가 만료·폐기할 때까지 쓸 수 있다고 적는다.
- §9.2 사고 대응의 격리 절차는 폐기(노출된 키는 즉시 폐기, 폐기 상태를 식별할 체계 필요), 교체, 삭제(로그·코드의 비밀 제거), 로깅 순이다. §2.6 감사는 만료된 비밀의 재사용 시도, 비밀이 사용된 때와 주체, 인증·인가 오류를 기록하도록 요구한다.
- §2.9는 백업·복원 절차를 정기적으로 시험하고 백업을 암호화·접근 제한·감시하라고 한다. 라이선스는 CC BY-SA 4.0이다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-41 | 공급자 측 자격 회수 |
| POL-45 | 공급자 측 자격 회수 |
| POL-47 | 공급자 측 자격 회수 |
| POL-49 | 공급자 측 자격 회수 |
| POL-14 | 공급자 측 자격 회수 |

## 우리 솔루션 개발에 사용할 곳

- **POL-41·POL-45**: 자격 회수의 판단 기준을 '설정 삭제'가 아니라 '자격을 발급·검증하는 백엔드(제공자) 쪽의 폐기'로 둔다는 근거다. 회수 뒤 이전 값으로의 재접근이 제공자에서 거부되는지(재사용 시도가 감사에 남는지)를 시험 항목으로 둔다.
- **POL-47·POL-49**: 문서 저장소 서비스 계정·외부 제공자 권한의 회수는 제공자 쪽 폐기 확인이 필요하다는 점을 같은 절차에 둔다. 제공자별 회수 API 유무는 별도 확인이 필요하다.
- **POL-14**: 인증정보 평문 노출 방지: 중앙화·접근 통제·탐지(§2.2·2.3·8) 항목을 설정·환경·오류 메시지 점검 체크리스트에 대응시킨다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

목차와 §2.4·2.6·2.7·2.9·9.2의 본문을 읽었다. 나머지 절(CI/CD, 클라우드, 컨테이너, 암호화, 멀티클라우드)은 읽지 않았다. 일반 지침이며 MCP·LLM 환경에 특화되지 않았다.

CC BY-SA 4.0 (CheatSheetSeries 저장소 LICENSE.md). 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
