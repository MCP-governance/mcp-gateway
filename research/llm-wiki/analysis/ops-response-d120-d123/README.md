# 운영 대응 — D-120~D-123

기준 `0eb013b37864e27bcb041145c9b9cea928f03d8d`, 작업 트리 `10/17-ops-response`. DEV-50·60·62·63의 코드와 로컬 단위 시험을 구현했다. 배포·실제 MCP·실기기 효과는 검증하지 않았다.

- [원자 요구사항·코드·시험 연결](requirements.json)
- [운영 설정·복귀·초기화 절차](../../../../docs/ai/OPS_RESPONSE.md)
- [작업 보고](../../status/reports/2026-10-17-ops-response-d120-d123.md)
- [로컬 단위 시험 원본](evidence/unit-tests.txt)
- [정적 검사 결과](evidence/static-checks.json)
- [위키 검사 결과](evidence/wiki-check.json)

## 적용 범위

| 개발 | 구현 | 로컬 증거 | 기기에서 남은 것 |
| --- | --- | --- | --- |
| DEV-50 / D-120 | Trivy 파서 공유·불변 이미지·7일 DB 기준·CRITICAL 최초 발견 기한·검사 실패/초과 격리·원장 추가 | 경계값·실패·순서 뒤의 취약점·동일 이미지 결속 | 실제 Trivy·DB 캐시·실행 컨테이너 제거·재시작·경쟁 |
| DEV-60 / D-121 | 로드 정책 해시·정상/합성 6건·실제와 공통인 경보 저장·독립 표식 | 잘못된 정책 ID·OPA 장애·정책 변경·경보 저장 실패는 실패 | 실제 OPA 정책 ID·DB 경보 저장·통계 불변 |
| DEV-62 / D-122 | DRIFT/반복 이상 판정→서버 비활성·실행 중지·명시적 관리자 복귀 | 대상 설정·중지 상태·복귀 이후 판정 필터 | 실제 부하·dispatch 경쟁·거짓 양성·수동 복귀 |
| DEV-63 / D-123 | 선행 서명 기록·별도 볼륨·서명 head·기동/주기 DB 재차단 | 실제 Ed25519·손상/절단·중간 쓰기·경쟁 쓰기·DB 대역 복원 | cryptography 연동·Linux flock/fsync·실제 백업 복원·오래된 자격 거부 |

Windows에는 제품 의존성이 없어 DB·HTTP는 코드 단위 대역을 사용했고 Ed25519는 설치된 OpenSSL을 사용했다. 제품 `cryptography`가 설치된 환경에서는 같은 시험이 제품 키 함수를 직접 사용한다. 실제 MCP 서버 대역은 새로 만들지 않았다.

## 근거와 OSS 검토

- [기능명세·WBS](../feature-spec-2026-10-17/README.md), [공백 레퍼런스](../../papers/policy50-gap-references.md), [KEV](../../papers/LIB-K19.md), [EPSS](../../papers/LIB-K21.md), [SP 800-61r3](../../papers/LIB-K31.md), [SP 800-34r1](../../papers/LIB-K32.md)의 기존 확보 자료를 읽었다. 이 자료는 격리·검증·복원 후 확인의 설계 근거다. KEV 연방 기관 기한을 제품 기본 기한으로 옮기거나 EPSS 확률을 CRITICAL과 동치로 처리하지 않았다.
- [aquasecurity/trivy v0.74.0](https://github.com/aquasecurity/trivy/releases/tag/v0.74.0), 릴리스 커밋 `e1fd17a` 표시와 [Apache-2.0](https://raw.githubusercontent.com/aquasecurity/trivy/v0.74.0/LICENSE)를 공식 페이지에서 확인했다. 유지보수 중인 릴리스 페이지와 [고정 판본 Report/Metadata](https://raw.githubusercontent.com/aquasecurity/trivy/v0.74.0/pkg/types/report.go)의 `SchemaVersion`·`Metadata.ImageID` 필드를 읽었다. 실제 적용은 기존 Trivy CLI·공유 파서이며 외부 코드를 복사하거나 실행하지 않았다. 컨테이너 태그의 레지스트리 digest·전체 commit은 확보하지 못했고 빌드·실행도 하지 않았다.
- GitHub 공개 스킬은 [anthropics/skills의 webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing), [본문](https://raw.githubusercontent.com/anthropics/skills/main/skills/webapp-testing/SKILL.md), [Apache-2.0](https://raw.githubusercontent.com/anthropics/skills/main/skills/webapp-testing/LICENSE.txt)을 탐색했다. 브라우저·로컬 서버 시험 중심이라 이 작업의 순수 단위 검증에는 채택하지 않았다. 최신 커밋과 유지보수 이력은 페이지에서 확보하지 못했다. 스크립트·설치·서버 기동 지시는 실행하지 않았다.
- Ed25519는 저장소의 keygen·raw base64url 방식과 기존 `cryptography` 의존성을 재사용한다. 폐기 전용 키를 분리하여 JWT 발급 경계를 보존한다. 새 제품 의존성은 없다.

## 검증 한계

위키 검사 실패는 결과 원본에 남겼다. 원문 provenance 누락과 통합 위협 매핑 해시 갱신은 메인 통합 작업이다. `status/current.md`는 변경하지 않았다. 코드·시험 해시는 `requirements.json`에 연결하며 추후 통합 시 다시 고정해야 한다.
