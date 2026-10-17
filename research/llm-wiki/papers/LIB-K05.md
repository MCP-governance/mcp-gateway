# LIB-K05 · Regal — Rego 린터·디버거·언어 서버 (open-policy-agent/regal v0.43.0)

Regal은 Rego 정책용 린터·디버거·언어 서버다. 규칙 색인 페이지에 111개 규칙이 Bugs·Custom·Idiomatic·Imports·Performance·Style·Testing 범주로 나열되어 있고, 조직이 직접 정한 규칙(Custom Rules)을 강제할 수 있다고 README가 밝힌다.

## 출처와 확인 수준

- 공식 출처: [Regal — Rego 린터·디버거·언어 서버 (open-policy-agent/regal v0.43.0)](https://github.com/open-policy-agent/regal)
- 관련 출처: <https://www.openpolicyagent.org/projects/regal>
- 관련 출처: <https://www.openpolicyagent.org/projects/regal/rules>
- 유형: 도구·OSS · 2026년 · GitHub open-policy-agent/regal 릴리스 v0.43.0 (2026-09-29), Apache-2.0 · `open_source_release`
- 저자·발행: Open Policy Agent 프로젝트(Regal 기여자)
- 판본: v0.43.0. 이전 주소 StyraInc/regal은 open-policy-agent/regal로 리디렉션된다(GitHub API 확인). README의 OPA 배지는 v1.21.0
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: 저장소 메타데이터, README, 규칙 색인 페이지, 릴리스 v0.43.0, 최신 커밋 SHA.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- README의 목표에 흔한 실수·버그·비효율 식별, 모범 사례·스타일 안내, 조직별 맞춤 규칙 강제가 들어 있다.
- 규칙 색인은 111개 규칙을 7개 범주로 보이며 Testing 범주가 별도로 있다. 문서 사이트에는 Custom Rules·CI/CD·Pre-Commit Hooks·Language Server 항목이 있다.
- 저장소 메타데이터상 라이선스는 Apache-2.0이고 보관(archived) 상태가 아니며 2026-10-14에도 푸시가 있었다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-01~POL-50 | 정책 번호 체계 표류 |
| POL-37 | 정책 변경 시험·동치 분석 |

## 우리 솔루션 개발에 사용할 곳

- **정책 번호 체계 표류**: 조직 규칙으로 '모든 규칙에 title·labels 주석(POL 번호) 필수'를 린트에서 강제하면 규칙과 정책 번호 연결이 빠진 변경을 CI에서 막을 수 있다(설계 제안, Custom Rules 구현 가능 여부는 미확인).
- **POL-37**: 정책 파일 변경 때 Regal과 `opa test`를 함께 돌려 구성 변경 검토의 자동 검사 단계로 쓴다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

README와 규칙 색인 페이지만 읽었다. 개별 규칙 문서, Custom Rules 작성법, 소스 코드는 열지 않았고 우리 Rego에 실행하지 않았다. 규칙 수 111은 문서 열람 시점 값이다.

GitHub 저장소 메타데이터의 SPDX가 Apache-2.0이다(LICENSE 파일 본문은 열지 않았다). 본문·코드를 복제하지 않는다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
