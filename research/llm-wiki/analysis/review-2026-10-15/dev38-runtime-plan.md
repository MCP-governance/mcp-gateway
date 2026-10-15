# DEV-38 승인 소스 MCP 자동 실행 경로 제안

상태: **구현됨(D-114, 10-15)** — 이 문서는 설계 당시의 제안으로 보존한다. 구현과 시험 근거는 [작업 보고](../../status/reports/2026-10-15-dev38-runtime.md). [백로그 DEV-38](../../status/backlog.md)의 완료 조건을 구체화한다. 첫 대상은 이미 실기기에서 사용한 Microsoft MarkItDown의 검증 커밋이다. 임의 저장소의 README에서 실행 명령을 자동 추출하는 기능은 첫 범위에서 제외한다.

## 현행 경계

`full_stack_lab/supply_chain/intake_worker.py`는 저장소를 정적 검사한다. 저장소 코드를 실행하지 않는다. `agent_service`는 승인 소스와 내부 미러 archive를 대조한다. `core.register_server`는 승인·커밋과 관리자가 제공한 endpoint를 확인한다. [10-15 E2E](../../status/reports/2026-10-15-clean-e2e.md)의 MarkItDown은 운영자가 컨테이너를 직접 빌드·실행했다. 따라서 현재 source tree SHA를 실행 image SHA나 빌드 보증으로 해석하면 안 된다.

## 최소 흐름

`승인 유지 확인 → 내부 미러의 고정 커밋 → 지원 레시피로 격리 빌드 → 이미지 검사 → digest 지정 실행 → MCP 계약 확인 → 등록 활성화`

도입 승인 상태는 그대로 두고 실행 job 상태를 분리한다. 최소 상태는 QUEUED, BUILDING, BUILT, STARTING, VERIFYING, ACTIVE와 FAILED, CANCELLED, STOPPED다. 화면 표기는 기존 제품 용어 규칙에 맞춘다. DB·API·UI를 새 범용 오케스트레이터로 확대하지 않고 기존 PENDING 등록/작업 claim 패턴을 검토해 재사용한다.

## 반드시 이어야 할 근거

| 대상 | 기록·검증 |
| --- | --- |
| 승인 | intake ID, 독립 승인자, 승인/위험수용 만료, 소스 commit/tree SHA |
| 빌드 입력 | 내부 미러, 레시피 SHA, base image digest, dependency lock/hash, builder 판본 |
| 빌드 결과 | job/attempt ID, 시작·종료, 산출 image digest, image SBOM·검사 결과, 비밀 제거 로그 hash |
| 실행 | runtime ID, image digest, 제한된 mount·UID·망·자원, 내부 endpoint |
| 활성화 | 현재 승인 재확인, MCP 판본·전체 목록·승인 계약 hash, endpoint/runtime 일치 |
| 종료 | Gateway 거부, 프로세스 정지, 자격 철회, 볼륨·캐시 잔존, 복원 뒤 재호출 결과 |

이미지 tag나 서버가 반환한 이름만으로 연결하지 않는다. [SLSA v1.2](https://slsa.dev/spec/v1.2/build-provenance)의 입력·builder·invocation·subject 구분과 [BuildKit provenance](https://docs.docker.com/build/metadata/attestations/slsa-provenance/)를 참고한다. 이 형식을 활용하는 것만으로 SLSA 수준을 달성했다고 주장하지 않는다.

## 실행 권한과 네트워크

- Gateway/Console/정적 검사 워커에 Docker socket이나 임의 shell 실행 기능을 추가하지 않는다. 고정된 job만 받는 빌드/실행 경계를 둔다.
- 실행 root filesystem 읽기 전용, 비특권 UID, cap-drop ALL, no-new-privileges, 게시 포트 없음, 제한된 임시 공간·CPU·메모리·PID·시간을 검토한다. 실제 레시피 동작과 호스트 조건에서 검증한다.
- 빌드에는 업무 자격을 주지 않는다. 필요한 패키지·base image 통신과 실행 시 업무 목적지를 분리한다. build secret은 image layer·ARG·로그에 남기지 않는다.
- 승인된 hostname 문자열만 확인해서는 redirect·DNS 변경·MCP 자체의 outbound를 통제할 수 없다. 실제 연결 시점의 목적지 정책을 적용한다. 지원 불가능한 transport는 보류한다.

[ToolHive 검토](../../solutions/toolhive-runtime.md)는 런타임 재사용 후보다. MINT의 승인·정책·감사·관리형 하네스 경로를 유지하며 실행 수명 관리만 비교한다. ToolHive client 자동 등록으로 직원 하네스가 MINT 밖 endpoint를 직접 사용하지 않게 한다.

## 경합·실패·복구 조건

| 조건 | 예상 결과·독립 확인 |
| --- | --- |
| 중복 클릭/워커 2개 | 한 generation당 실행물 1개. label/job ID로 실제 실행 수 확인 |
| 생성 후 DB 기록 전 프로세스 사망 | 기존 실행물 재발견·정리 또는 연결. 새 실행물을 맹목적으로 중복 생성하지 않음 |
| 오래된 워커가 늦게 완료 | attempt ownership/generation이 맞을 때만 결과 반영 |
| 빌드/기동 중 승인 만료·철회 | 최종 활성화 거부. 이전 승인으로 새 endpoint 노출 없음 |
| source/image digest 불일치 | 실행/등록 거부. 이름·tag가 같아도 거부 |
| 스캐너 장애·timeout·disk full | 실패 상태와 비밀 제거 증거. 빈 결과를 통과로 세지 않음 |
| MCP 시작 실패·계약 불일치 | 등록 ACTIVE 전환 없음. 실패 실행물 정리와 감사 기록 |
| 서비스 재시작 | 현재 승인·실행 digest·계약을 재확인하고 복구. 종료된 항목 부활 금지 |
| 종료 | 기존 C1~C4/T1~T3로 판단. 컨테이너 삭제를 provider 회수 완료로 전이하지 않음 |

완료 시험은 실제 MarkItDown으로 정상 URL 변환, 범위 밖 파일·호스트·redirect 요청, 위 경합·실패·복구를 대조하고 PJ1 관리 Claude에서 자연어 호출한다. mock MCP를 만들지 않는다. 시험 리소스와 원복 범위를 한정한다. 권한 경계는 [RV-01/DEV-41](README.md), 실행 근거는 [증거 계약](../../methodology/evidence-contract.md)과 함께 검수한다.
