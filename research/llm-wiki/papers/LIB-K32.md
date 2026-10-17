# LIB-K32 · NIST SP 800-34 Rev. 1: Contingency Planning Guide for Federal Information Systems

정보시스템 비상계획(ISCP)의 목적·절차·형식을 설명하는 지침이다. 계획 수립 과정(§3: 정책·영향 분석·예방 통제·전략·시험·유지보수), 백업·복구 전략(§3.4.1), 활성화·복구·복원(reconstitution) 단계(§4)와 부록의 계획 서식을 다룬다.

## 출처와 확인 수준

- 공식 출처: [NIST SP 800-34 Rev. 1: Contingency Planning Guide for Federal Information Systems](https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final)
- 관련 출처: <https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-34r1.pdf>
- 유형: 표준·RFC·권고 · 2010년 · NIST Special Publication 800-34 Rev. 1, 2010-05 (2010-11-11 갱신), 149쪽 · `official_publication`
- 저자·발행: Marianne Swanson, Pauline Bowen, Amy Wohl Phillips, Dean Gallup, David Lynes
- 판본: 2010년 5월판(갱신 2010-11-11). CSRC 페이지에 2023-03-17자 계획 공지(문의 안내)만 있고 폐기 표시는 없었다
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: CSRC 페이지, PDF 표지·고지·목차, §4.4 본문, 부록 A 목차, 용어 검색.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §4.4 복원 단계는 복구가 끝나고 정상 운영을 재개하기 전에 시스템 기능을 시험·검증하는 활동이며, 복구 검증(동시 처리 포함)과 계획 비활성화의 두 활동으로 구성된다. 부록 A 서식에 데이터 검증 시험, 기능 검증 시험, 복구 선언, 정리(cleanup)가 있다.
- §3.4.1은 백업 방법과 복구 전략을, §3.5는 시험·교육·훈련을 다룬다.
- 본문 전체 텍스트에서 '자격증명(credential)'·'폐기(revoked)' 용어는 나타나지 않았다. 암호(password)는 시험 절차 예시와 무선 설명에서만 나온다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-50 | 복원 후 재활성화 |
| POL-46 | 복원 후 재활성화 |

## 우리 솔루션 개발에 사용할 곳

- **POL-50**: 복원 후 검증 단계(§4.4)를 우리 복원 시험 절차의 뼈대로 쓰되, '폐기된 MCP 서버·도구·자격이 복원으로 되살아나지 않았는지'는 이 문서에 없으므로 별도 검증 항목으로 추가해야 한다. 이 공백은 이 문서로 메워지지 않는다.
- **POL-46**: 복구·복원 시 잔존 프로세스 정리를 복원 단계의 cleanup 항목에 대응시킨다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

2010년 판이며 목차와 §4.4 본문, 부록 목차만 읽었다. 연방 정보시스템용이고 클라우드·컨테이너·MCP 환경을 다루지 않는다. 용어 부재 확인은 PDF 추출 텍스트 검색 결과다.

NIST 간행물: 저작권 보호 대상이 아니며 출처 표기를 요청한다고 PDF에 적혀 있다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
