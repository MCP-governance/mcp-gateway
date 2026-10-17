# LIB-K31 · NIST SP 800-61 Rev. 3: Incident Response Recommendations and Considerations for Cybersecurity Risk Management: A CSF 2.0 Community Profile

사이버보안 인시던트 대응 권고를 NIST CSF 2.0의 위험 관리 활동 전반에 넣는 방법을 정리한 커뮤니티 프로파일이다. 목차상 표 2(준비·교훈)와 표 3(인시던트 대응)에 CSF 하위 범주별 권고(R)와 고려사항(C)이 있다.

## 출처와 확인 수준

- 공식 출처: [NIST SP 800-61 Rev. 3: Incident Response Recommendations and Considerations for Cybersecurity Risk Management: A CSF 2.0 Community Profile](https://csrc.nist.gov/pubs/sp/800/61/r3/final)
- 관련 출처: <https://doi.org/10.6028/NIST.SP.800-61r3>
- 관련 출처: <https://csrc.nist.gov/pubs/sp/800/61/r2/final>
- 유형: 표준·RFC·권고 · 2025년 · NIST Special Publication 800-61 Rev. 3, 2025-04, 48쪽 · `official_publication`
- 저자·발행: Alexander Nelson, Sanjay Rekhi, Murugiah Souppaya, Karen Scarfone
- 판본: 2025년 4월판. Rev. 2(2012-08)는 2025-04-03 폐기되어 Rev. 3으로 대체됨(CSRC 페이지)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: CSRC 페이지(초록·대체 관계), r2 폐기 페이지, PDF의 CSF 하위 범주 표에서 DE.AE-02·06·08, RS.MI-01·02, RC.RP-03·05.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- 하위 범주 DE.AE-02(이상 이벤트 분석)는 SIEM·SOAR 등으로 로그를 지속 모니터링하라고, DE.AE-06은 경보를 대응 도구·인력에 제공하고 특정 경보에 대해 티켓을 자동 생성·할당하는 것을 고려하라고, DE.AE-08은 알려진 오탐을 감안해 기준 충족 시 인시던트를 선언하라고 한다.
- RS.MI-01(인시던트 격리)은 확산 방지를, RS.MI-02(근절)는 지속 수단·진입점 제거의 예로 침해된 사용자 계정 비활성화·악용된 취약점 완화를 든다.
- RC.RP-03은 복원에 쓰는 백업의 무결성을 사용 전에 검증하라고, RC.RP-05는 복원된 자산을 침해 지표로 점검하고 복원 조치의 정확성·적절성을 확인한 뒤 온라인으로 올리라고 한다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-42 | 경보 검증·자동 대응 |
| POL-43 | 경보 검증·자동 대응 |
| POL-50 | 복원 후 재활성화 |

## 우리 솔루션 개발에 사용할 곳

- **POL-42**: 경보 정상 작동 검증 시나리오를 DE.AE-02·06·08에 대응시킨다. 신규 도구·미승인 연결·호출 폭증 경보가 설정 변경 뒤에도 발화하는지, 오탐을 제외하고 인시던트로 선언하는 기준이 있는지 확인한다.
- **POL-43**: 탐지 뒤 '중지·격리·영향 범위 조사'를 RS.MI-01·02의 격리·근절 권고(계정 비활성화 포함)와 대응시키고, 자동 대응과 사람 승인을 구분한다.
- **POL-50**: 복원 전 백업 무결성 검증(RC.RP-03)과 복원 후 점검(RC.RP-05)에 '폐기된 연결·자격이 되살아나지 않았는가'를 우리 점검 항목으로 추가한다. 이 문서에 그 항목은 없다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

PDF 텍스트에서 위 하위 범주만 읽었고 나머지 표와 본문은 읽지 않았다(표 번호는 확인하지 않았다). 일반 조직용 권고이며 MCP·LLM 에이전트를 다루지 않는다. 폐기 자격 재활성화 같은 항목은 문서에 없다.

NIST 간행물: 미국에서 저작권 보호 대상이 아니며 출처 표기를 요청한다고 PDF에 적혀 있다. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
