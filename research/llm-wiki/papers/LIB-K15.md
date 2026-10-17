# LIB-K15 · SPIRE — SPIFFE Runtime Environment (spiffe/spire v1.15.4)

SPIRE는 이종 호스팅 환경의 소프트웨어 사이에 신뢰를 세우는 API 툴체인이다. 실행 중인 소프트웨어를 증명(attest)하고 SVID를 발급해 워크로드 사이의 mTLS 또는 JWT 서명·검증을 가능하게 한다. SPIFFE API를 구현한 런타임이다.

## 출처와 확인 수준

- 공식 출처: [SPIRE — SPIFFE Runtime Environment (spiffe/spire v1.15.4)](https://github.com/spiffe/spire)
- 관련 출처: <https://github.com/spiffe/spire/releases>
- 유형: 도구·OSS · 2026년 · GitHub spiffe/spire 릴리스 v1.15.4 (2026-10-15), Apache-2.0 · `open_source_release`
- 저자·발행: SPIFFE 프로젝트(SPIRE 기여자)
- 판본: v1.15.4(2026-10-15). 저장소 메타데이터상 2026-10-16 푸시
- 확인일: 2026-10-17 / `page_text_read` — 공식 페이지 본문을 읽었다(절 단위 정독 아님). 읽은 범위: README 앞부분, 저장소 메타데이터, 최신 릴리스 메타데이터.
- 요약 검토: 출처 페이지 본문과 대조했다.
- 배포: `public-under-license` — 서지와 자체 요약만 보관하고 원문은 복제하지 않는다.

## 읽은 내용

- README는 SPIRE가 실행 중인 소프트웨어를 증명해 SVID를 발급하며, 워크로드가 비밀 저장소·DB·클라우드 제공자에 안전하게 인증하는 데에도 쓸 수 있다고 설명한다. 릴리스에 SPIRE Server와 SPIRE Agent 바이너리가 함께 들어 있다.
- 저장소 메타데이터상 라이선스는 Apache-2.0이며 보관(archived) 상태가 아니고 릴리스 v1.15.4가 2026-10-15에 게시됐다.

## 메우는 정책50 공백

| 정책 | 공백 |
| --- | --- |
| POL-19 | 에이전트 신원·위임 |
| POL-20 | 에이전트 신원·위임 |

## 우리 솔루션 개발에 사용할 곳

- **POL-19·POL-20**: SPIFFE 표준을 실제로 발급·검증하는 구현의 후보다. 하네스·endpoint-agent·게이트웨이 사이의 신원 발급을 SPIRE로 할지, 기존 Keycloak 토큰 경로로 충분한지 비교하는 단계의 입력이다(DEV-43). 에이전트(LLM) 수준의 위임 증명은 SPIRE 범위 밖이다.

적용 항목은 개발 후보이며 우리 구현이나 배포에서 검증된 기능이 아니다. 이 자료를 읽었다는 사실이 해당 정책의 구현·검수 완료를 뜻하지 않는다.

## 한계와 사용 조건

README와 저장소·릴리스 메타데이터만 읽었다. 코드·구성·증명(attestor) 플러그인·운영 요구사항은 열지 않았고 설치·시험하지 않았다. 기존 위키의 OSS 심층 분석 기준(커밋·함수 고정)에는 못 미치는 서지 수준 등록이다.

GitHub 저장소 메타데이터의 SPDX가 Apache-2.0이다(LICENSE 파일 본문은 열지 않았다). 코드를 복제하지 않는다.

[검증 기록](../analysis/evidence/references/policy50-gap-fill-2026-10-17.json) · [정책50 공백 지도](policy50-gap-references.md) · [자료 확보 규칙](../methodology/source-protocol.md)
