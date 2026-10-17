# LIB-K13 · RFC 9334: Remote ATtestation procedureS (RATS) Architecture

통신 상대가 의도한 동작 상태에 있는지를 증거(Evidence)를 만들고 전달하고 평가하는 참여자와 메시지로 나누어 설명하는 아키텍처 문서다. 프로세서 구조·클레임 내용·프로토콜에 중립적이다.

## 출처와 확인 수준

- 공식 출처: [RFC 9334: Remote ATtestation procedureS (RATS) Architecture](https://www.rfc-editor.org/rfc/rfc9334)
- 관련 출처: <https://www.rfc-editor.org/rfc/rfc9334.txt>
- 유형: 표준·RFC·권고 · 2023년 · IETF RFC 9334 (Informational), 2023-01, 46쪽 · `ietf_rfc`
- 저자·발행: H. Birkholz, D. Thaler, M. Richardson, N. Smith, W. Pan
- 판본: 2023년 1월 발행본(draft-ietf-rats-architecture-22). 표준 트랙이 아닌 Informational 문서
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: 초록·상태, 목차, §4.1, §8.4, §10 도입부, RFC Editor 메타데이터(JSON).
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- §4.1 역할: Attester는 증거를 만들고, Verifier는 증거를 평가해 Attestation Results를 만들며, Relying Party는 그 결과와 자체 평가 정책으로 동작(접근 허용 등)을 정한다. 평가 정책은 Verifier Owner·Relying Party Owner가 따로 설정한다.
- §5는 Passport 모델과 Background-Check 모델을 구분한다. §8.4는 부적합 결과가 Attester를 '권한 없음, 교정 필요'로 취급하는 데 쓰일 수 있다고 설명한다.
- §10 신선도: 증거·결과가 만들어진 시점(epoch)을 만료 임계와 비교하며, 증거 생성 직후 Attester 상태나 평가 정책이 바뀌는 경쟁 조건은 항상 가능하다고 명시한다. 목표는 최신성을 수용 가능한 범위로 좁히는 것이다. 방법은 동기화 시계(§10.1), nonce(§10.2), epoch ID(§10.3)다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-19 | 에이전트 신원·위임 |
| POL-20 | 에이전트 신원·위임 |

## 우리 솔루션 개발에 사용할 곳

- **POL-19**: '요청의 이름이나 외부 설명만으로 신원을 인정하지 않는다'를 역할 분리로 표현한다. 하네스·endpoint-agent가 만든 증거를 별도 검증 주체가 평가하고 게이트웨이(Relying Party)는 그 결과만 소비하는 구조의 어휘로 쓴다(설계 제안).
- **POL-20**: 위임 유효기간·철회 반영 지연을 신선도 모델의 만료 임계와 경쟁 조건 용어로 정리해, 철회 직후 호출 시험의 허용 지연 기준을 명시한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

초록, §4.1 역할, §8.4, §10 도입부를 읽고 나머지는 목차로만 확인했다. 장치·환경의 상태 증명 아키텍처이며 LLM 에이전트의 신원이나 사용자 위임을 직접 다루지 않는다. MCP에 대한 바인딩 표준은 확인하지 못했다.

IETF Trust 저작권 및 BCP 78·IETF Trust Legal Provisions 적용. 본문을 복제하지 않고 서지·자체 요약만 보관한다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
