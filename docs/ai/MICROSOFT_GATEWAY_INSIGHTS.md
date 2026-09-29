# Microsoft MCP Gateway 비교와 적용

2026-09-29 기준 공개 [README](https://github.com/microsoft/mcp-gateway)와
[Portal 설명](https://github.com/microsoft/mcp-gateway/blob/main/portal/README.md)을 읽고,
우리 [정본 아키텍처](ARCHITECTURE.md)·[남은 일](ROADMAP.md)과 비교했다. 배포·성능·보안 강도를 실측 비교한 문서는 아니다.

| 관심사 | Microsoft MCP Gateway | 우리 솔루션 |
| --- | --- | --- |
| 중심 문제 | Kubernetes의 MCP 서버·도구 등록, 배포, 상태, 세션별 라우팅 | 직원 하네스의 호출을 실행 전에 신원·계약·자원·개인정보·OPA 정책으로 판정 |
| 관리 | `/adapters`·`/tools` API와 상태·로그·시험 포털 | 도입 신청·승인, Git 카탈로그와 계약 잠금, 감사·종료 Console |
| 권한 | Entra ID와 서버·도구 접근 역할 | 토큰 신원에 더해 도구 인자에서 자원·행위를 분류하고 Rego로 집행 |
| 단말 | 서버 운영이 주 대상 | Endpoint Agent가 섀도 설정·리스너·잔존을 관측 |

## 채택할 것

1. **승인에서 등록 변경으로 넘기기.** 승인된 신청의 검증 커밋, 격리 스캔 요약,
   관리자 검토, 종료 조건을 `GET /api/mcp-requests/{id}/registration-draft`와 Console의
   **등록 변경안**으로 내보낸다. 관리자 전용이며 승인·검증 증거가 없으면 거절한다.
   `catalog.toml`을 자동 수정하지 않는다. 신청에는 `server_id`·실행 endpoint·배포 이미지·
   도구별 r/w/x가 없고, 검증용 `scan_ref`는 카탈로그의 `package@version`과 다르다.
2. **운영 상태를 승인 근거에 연결하기.** 현재 `/api/registry`는 서버 상태와 계약 상태,
   `/api/health`는 준비된 서버 수를 보여 준다. 등록 PR에는 배포 뒤 READY/DRIFT,
   승인 스키마, 하네스 연결, 정책 차단 시험 결과를 붙인다. Kubernetes pod 로그 기능은
   Kubernetes를 실제 배포 대상으로 정했을 때 검토한다.
3. **세션 고정은 필요가 확인되면 적용하기.** Microsoft의 분산 세션 저장소와 세션별
   라우팅은 여러 복제본의 상태 유지 문제에 맞는다. 우리 랩은 해당 운영 요건과 장애
   증거가 없으므로 지금 구현하지 않는다.

## 등록 변경 순서

`VALIDATED` → 관리자 `APPROVED` → **등록 변경안 복사** → Git PR에서 실행 정보·도구
권한·분류·이용 관계 검토 → 카탈로그·Compose·관리형 하네스 설정 반영 → 실제 서버에서
계약 잠금 생성·diff 검토 → 배포·검증. 앞의 승인은 뒤의 활성화를 뜻하지 않는다.

Microsoft의 선택형 내장 에이전트는 공개 README상 평가용 단일 복제본 기능이다.
우리 Gateway의 정책 판정이나 Endpoint Agent를 대체하는 구성으로 취급하지 않는다.
