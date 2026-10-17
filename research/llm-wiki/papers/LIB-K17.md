# LIB-K17 · OpenSSF Scorecard v5.6.0 — 점검 항목 문서 (ossf/scorecard docs/checks.md)

오픈소스 프로젝트의 보안 상태를 20개 점검 항목(Binary-Artifacts, Branch-Protection, Code-Review, Dependency-Update-Tool, Maintained, Pinned-Dependencies, SAST, Security-Policy, Signed-Releases, Token-Permissions, Vulnerabilities 등)으로 자동 평가하는 도구의 점검 설명서다. 항목마다 위험도, 점수 기준, 개선 방법을 적는다.

## 출처와 확인 수준

- 공식 출처: [OpenSSF Scorecard v5.6.0 — 점검 항목 문서 (ossf/scorecard docs/checks.md)](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
- 관련 출처: <https://github.com/ossf/scorecard>
- 유형: 도구·OSS · 2026년 · GitHub ossf/scorecard 릴리스 v5.6.0 (2026-10-12), Apache-2.0 · `open_source_release`
- 저자·발행: Open Source Security Foundation (Scorecard 기여자)
- 판본: v5.6.0. docs/checks.md 마지막 변경 커밋 f746d2ee21e5(2026-10-15)
- 확인일: 2026-10-17 / `full_text_selected_sections_read` — 원문의 지정 절·조문을 직접 읽었다. 읽은 범위: docs/checks.md의 항목 목록과 Signed-Releases·Maintained·Security-Policy·Dependency-Update-Tool·Vulnerabilities 절, 저장소·릴리스 메타데이터, 파일 최종 커밋.
- 요약 검토: 지정한 절을 원문에서 직접 읽고 요약했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- Signed-Releases(위험도 High)는 GitHub 저장소의 최근 릴리스 5개 자산에서 서명 파일 이름(*.minisig, *.asc, *.sig, *.sign, *.sigstore, *.sigstore.json, *.intoto.jsonl)을 찾는다. 현재 GitHub 저장소만 지원한다.
- Maintained(High)는 보관(archived) 프로젝트에 최저점을, 직전 90일 동안 주 1회 이상 커밋이 있으면 최고점을 준다. 문서는 활동 없음이 항상 문제는 아니라고도 단서를 단다. Vulnerabilities(High)는 OSV 서비스로 열린 취약점을 확인한다.
- Security-Policy(Medium)는 SECURITY.md 존재와 내용(취약점 처리·공개 일정)을 본다. Dependency-Update-Tool(High)은 Dependabot·Renovate 사용 여부를 본다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-01 | 공급망 출처·취약점 대응 |
| POL-03 | 공급망 출처·취약점 대응 |
| POL-39 | 공급망 출처·취약점 대응 |

## 우리 솔루션 개발에 사용할 곳

- **POL-01·POL-03**: 도입 검토 기록에 '배포자·유지보수·서명·보안 정책' 항목을 점검 도구의 기계 판독 결과(항목별 점수·근거)로 첨부한다. 지원 종료·수정 경로 불명확(POL-03)은 Maintained·Security-Policy 점수를 참고 신호로만 쓴다.
- **POL-39**: Vulnerabilities 점검과 Dependency-Update-Tool 결과를 운영 의존성의 알려진 취약점 점검(재검사 주기) 입력으로 비교한다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

점검 설명서 전체 목차와 위 항목의 본문만 읽었다. 점수는 휴리스틱이며 안전 보증이 아니다. Scorecard를 실행하지 않았고 GitHub 외 저장소는 일부 항목이 지원되지 않는다. 우리가 도입하는 MCP 서버에 적용해 보지 않았다.

GitHub 저장소 메타데이터의 SPDX가 Apache-2.0이다(LICENSE 파일 본문은 열지 않았다). 문서를 복제하지 않는다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
