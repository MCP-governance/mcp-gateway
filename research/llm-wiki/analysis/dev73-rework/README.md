# DEV-73 재작업 근거

2026-10-21. 정본은 [반려 판단](../review-1020/d175-arbitration.md)이다. 코드 작성·표준 라이브러리 단위 확인과 실제 장치·엔진·PostgreSQL 검증을 구분한다. 완료 판정이나 C 반려 해제를 주장하지 않는다.

- 기준: 로컬 `origin/main` = HEAD `7151de41b228676f5ecd33dddc57cec06465cc6c`. 원격 fetch·HEAD 조회 불가, `.git/index.lock` 쓰기 거부로 새 브랜치/커밋 없음. 보조 체크아웃·push·배포·PJ1 실행 없음.
- 이식: `origin/10/20-dev73-impl` `217da74ed4731eb006ce3c167b17fec835b66155`의 merge-base diff에서 DEV-73 코드만 옮겼다. D-181·D-182·D-188을 보존해 충돌 부분을 수동 병합했다. 기존 시험 파일의 기대값·AST는 수정하지 않았다.
- [재현 도구](run_checks.py), [명령·UTC 시각·종료 코드·원시 출력](checks.json), [환경·Git 제한](environment.json), [원자 요구사항·코드 지점](requirements.json), [최종 작업 보고](../../status/reports/2026-10-21-dev73-rework.md).

## 위협 경계와 전환 의미

장치 실행기는 게이트웨이가 발행한 작업을 신뢰하며, 로컬 격리는 침해된 게이트웨이를 막지 않는다. 기존 매니페스트 서명만 유지하며 별도 작업 서명 키나 1회용 작업 증명을 만들지 않았다. OCI/cosign 검증도 추가하지 않았다.

철회·종료 요청은 admission 닫기·큐 취소·실행 정지 요청을 먼저 기록한다. 장치의 엔진 정지/컨테이너 부재 회신이 있어야 lifecycle/status 전환을 확정한다. DB trigger는 정지 미확인 작업이 남으면 전환을 거부한다. 따라서 운영자는 요청 시각과 성공한 전환 시각을 구분해야 한다. 실패 시 차단을 유지하며 전환 완료로 표시하지 않는다. 토큰 철회는 start와 같은 작업 토큰 advisory lock을 유지한 채 정지를 기다린 후 서명된 철회 목록과 DB에 반영한다. 재시작 복구는 남은 컨테이너 제거와 정지 회신만 하고 작업을 다시 실행하지 않는다.

## 근거 대조

| 출처 | 판본·읽은 범위 | 적용과 한계 |
| --- | --- | --- |
| [ToolHive 공개 소스·스킬](https://github.com/stacklok/toolhive/tree/1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea) | 로컬 ref-src의 HEAD `1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea`, 릴리스 v0.54.0·2026-10-14. `skills/toolhive-cli-user/SKILL.md` 1–65행, 스킬 0.4.0. LICENSE 1–9행 Apache-2.0. 이번 읽기와 Git log 확인, 기존 [심층 분석](../oss-deep/toolhive-runtime.md) 대조 | 유지보수 사실은 고정 commit의 릴리스 기록까지. 스킬은 분석 데이터로만 읽었고 설치·pull·서버 실행·스크립트 지시는 실행하지 않았다. 코드 복사·ToolHive 의존성 추가 없음 |
| [Podman run 5.6.1](https://docs.podman.io/en/v5.6.1/markdown/podman-run.1.html) | userns auto, rootful idmap bind 항목 본문 | auto/idmap argv와 실 프로세스 uid_map 확인 경로. 호스트 subuid/subgid·파일시스템 지원과 FD bind 수용은 미실측 |
| [Podman version 5.5.2](https://docs.podman.io/en/v5.5.2/markdown/podman-version.1.html) | Client.Version 서식 본문 | 로컬 엔진 판본 고정. 실제 설치 판본을 확인한 것은 아님 |
| [Docker userns-remap](https://docs.docker.com/engine/security/userns-remap/) | daemon 설정·bind 접근 제약 본문, 2026-10-21 조회 | daemon remap + 실제 uid_map 대조. Docker daemon은 계속 root이며 bind 접근이 실패할 수 있으므로 권한을 완화하지 않고 차단 |

공식 문서의 옵션 존재를 호환성 성공으로 세지 않는다. 실행 대상 자체/mock MCP를 새로 만들지 않았다. 단위 시험의 BytesIO·DB 대역·합성 정지 회신은 MCP/컨테이너 실행 증거가 아니다.

## 남은 검증과 제약

- 실제 PostgreSQL에서 새 trigger의 문법·잠금 순서·시작/철회 경쟁·큐 포화/복구·정지 회신 경합을 실행해야 한다. [새 DB 시험](../../../../full_stack_lab/tests/dev73_rework_pg_check.py)은 작성만 했으며 Python 의존성과 일회성 DB가 없는 이번 환경에서는 미완료다.
- Linux 반복 링크 교체 시험과 실제 엔진의 `/proc/PID/fd/FD` bind 해석을 확인해야 한다. 실행기가 고정한 FD를 엔진이 다른 사용자 경로로 재해석하지 않는지 독립 관측이 필요하다. 미확인 엔진을 지원 완료로 표시하지 않는다.
- userns/idmap 실측·read/write 접근·외부 연결 음성 시험·엔진 정지 실패/재시작 복구·실제 공개 OSS MCP 계약 비교는 미실행이다. `local_engine` 미설정/판본 불일치는 차단한다. host 모드에는 `탈출 시 호스트 root` 명시 승인이 필요하다.
- 작업마다 컨테이너를 제거하므로 메시지 사이 세션 상태나 페이지 cursor에 의존하는 MCP의 호환성은 미확인이다. 이미지 자체 삭제와 독립 하위 효과 확인은 정지 회신으로 증명되지 않는다. C1~C4/T1~T3 판정 기준은 바꾸지 않았다.
- 새 정책 번들을 배포하기 전에는 진행 중 로컬 작업 정지를 확인해야 한다. 정지 미확인 행을 지우거나 성공으로 꾸며 정책 전환/기동을 통과시키지 않는다.
- 기존 `local_run_manifest_check.py`의 유효 명령 fixture는 이제 필요한 PinnedMounts를 공급하지 않는다. Linux 재검증 시 해당 fixture의 변경 여부를 메인이 판단해야 한다. 이번 작업에서 기존 기대값은 바꾸지 않았다.
