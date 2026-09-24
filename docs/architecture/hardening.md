# MCP Gateway 아키텍처 구조 개선안

2026-09-24 기준 설계 검토 제안이다. 현재 공통 집행 경로를 유지하면서 실행 상태, 데이터 권한, 검사 환경의 책임을 명확히 하는 방안을 비교한다. **이 PR은 문서만 추가하며 제안한 구조의 구현 완료를 주장하지 않는다.**

## Evidence Basis

`main`의 `45b9f6ed6dd9cb6b6eadfaf2b6cc6ee1ac377967`에서 실행 함수, 승인/receipt, DB, Compose, 정책 재생과 기존 문서를 정적으로 대조했다. [근거 목록](context.md)은 16개 파일의 SHA-256을 기록한다. 이번 작업에서 런타임 전체 시험, 성능 측정, 조직 운영 환경 검증은 수행하지 않았다.

이미 있는 공통 `execute_call`, OPA 기본 차단, 승인 재검증, DB 연결 풀, 내부망 분리, Presidio, 감사 체인 v5와 정책 재생을 설계의 출발점으로 삼았다.

## Constraints

기존 API와 transport, Compose 실습, 과거 감사 이력을 보존하는 점진적 전환을 가정한다. 지연시간과 처리량 목표는 미정이다. 단일 저장소를 유지하고, 새 프록시나 큐 제품을 필수 경로에 추가하지 않는다.

## Opportunity Portfolio

| Opportunity | Evidence | Options | Recommendation | Proposal |
| --- | --- | --- | --- | --- |
| 실행 경로와 권한 경계의 책임 분리 | 공통 실행 함수, 공유 DB 역할, 사후 감사 저장, 고권한 A.I.G 실습 오버레이 | 안 1: 현 구조 유지와 국소 보강 / 안 2: 내부 모듈과 권한 경계의 단계적 분리 | 현재 개발 확장을 전제로 안 2 | [상세 개선안과 구조도](proposals/runtime-boundaries.md) |

우리는 실행 통제를 새로 만들기보다, 기존 통제의 변경 주체와 실패 상태를 코드 및 배치 경계에 명확히 연결할 수 있다. 상세 문서는 현재 구조와 두 대안의 Mermaid 구조도, 증거, 비용, 단계별 적용 및 검증 기준을 포함한다.

## Recommendation Summary

저는 **안 2**를 권고한다. 단일 실행 서비스를 유지한 모듈 분리부터 시작하고, 전송 전 실행 기록과 미확정 상태를 공통화한다. 이어서 migration 자격과 runtime DB 역할을 분리하고, A.I.G의 추가 권한을 Gateway 컨테이너 밖으로 옮긴다. 정책 코드와 데이터의 배포 식별자를 감사 및 replay와 연결한다.

| 핵심 개선 | 필요 이유 | 우선순위 |
| --- | --- | --- |
| 공통 실행 서비스와 순수 계약 모듈 | 정책, 승인, transport, 감사의 변경 책임을 명확히 함 | P1 |
| 실행 journal과 승인/실행 상태 분리 | 프로세스 중단과 응답 유실을 일관되게 미확정으로 처리 | P1 |
| DB 역할 및 migration 분리 | Worker와 Agent의 관리 원장 변경 권한을 축소 | P1 |
| A.I.G 검사 환경 격리 | 검사기의 추가 권한과 장애를 Gateway에서 분리 | P1 |
| 정책 묶음 digest와 캐시 수명주기 | 실제 판단과 증적의 적용 버전을 대조 | P2 |

안 2는 사전 DB 쓰기, 이관 작업, 검사 컨테이너 관리 비용이 늘어난다. 합성 랩 시연만 필요하고 일정이 짧다면 안 1이 합리적이다. 어느 안도 원격 MCP의 정확히 한 번 실행이나 조직 전체 Gateway 우회 차단을 자동으로 보장하지 않는다.

## Next Decisions

검토자는 운영 대상 범위, 미확정 실행의 조사 책임, 관리 API의 별도 프로세스 필요 여부, 성능 예산을 결정하면 된다. 구현을 시작할 때 기준 커밋과의 변경을 다시 확인하고 상세안의 A-D 단계별로 별도 구현 변경을 검토한다.

- [상세 제안](proposals/runtime-boundaries.md)
- [구조화된 분석과 근거 해시](hardening.json)
- [현재 구조 원본](diagrams/runtime-boundaries-before.mmd)
- [권고안 구조 원본](diagrams/runtime-boundaries-owned-boundaries-after.mmd)
