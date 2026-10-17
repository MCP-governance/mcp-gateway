# H·I 통합·검증·배포 (2026-10-18 04:50–05:55)

| 작업 | 브랜치·커밋 | 결정 |
| --- | --- | --- |
| H 단일 조회 반환 상한·완료 쓰기 재전송 차단 (DEV-54·55) | `10/18-response-cap` 00db46e | D-125·D-126 |
| I 계약 변경 도구별 제한·SIEM 전달 (DEV-52·61) | `10/18-selective-siem` e74fefa | D-127·D-128 |

구현: Codex gpt-6.1-sol(high). 검토: Sonnet(high) 각 1회 — 둘 다 "수정 후 배포".

## 검토 지적과 처리

| 출처 | 지적 | 처리 |
| --- | --- | --- |
| H 검토 High | `path="//shared"`로 전체 폴더 차단 우회(`posixpath.normpath`가 선행 `//` 보존) | 선행 슬래시 정규화, 회귀 사례 추가 |
| H 검토 High | JSON 문자열 한 겹으로 감싼 대량 레코드가 1건으로 집계 | 여러 줄 문자열은 줄 수로 집계(한 줄은 0), 회귀 사례 추가 |
| H 검토 Low | 정책 대장 시험 ID 중복 | `T-VOLUME-003` |
| I 검토 Medium | dispatch 잠금 변경의 실제 PostgreSQL 경합 미실행 | 격리 실험에서 실행 → 아래 회귀 2건 발견·수정 |
| I 검토 Trivial | 미사용 import | 제거 |
| 메인 실측 | H+I 병합 후 서버 행 공유 잠금을 주체 advisory lock 대기보다 먼저 잡아 종료(FOR UPDATE)가 240건 전송이 끝날 때까지 지연(3회 재현, H 단독은 218 기록·22 거부) | 공유 잠금을 INSERT 직전으로 이동 → 3회 모두 218·22 |
| 메인 실측 | 종료 중 서버로 가는 재전송 쓰기가 `terminated` 대신 `duplicate`로 보고 | 상태 기반 사유 우선(차단 여부는 동일) |
| 메인 실측 | `opa test` 90/91 — `P-VOLUME-002` 우선순위가 `PAC-10`과 중복 | 82로 변경 → 91/91 |

## 검증 (최종 main bb33625)

- 단위: `response_cap_idempotency_test` 12(1 건너뜀: pglast 미설치), `selective_restriction_siem_check` 20, Windows 키트 16.
- 격리 실험(솔루션 기기 `wbs-c-*`, 제품 스택과 분리): `dispatch_intent_pg_check` 실제 PostgreSQL 61건 중 60건,
  `dispatch_effect_lab` 실제 Gitea MCP 56/56. 실패 1건 `pool: a closure announced by another process is applied on the next use`는
  H·I 이전 main(e2a7e72)과 H 단독(33af7da)에서도 실패 — 기존 결함, 별도 작업.
- `opa test` 91/91(기기 컨테이너).
- 배포: `field up` bb33625, `/api/health` 모든 구성요소 정상.
- PJ1 관리형 Claude: github `get_me` 정상(배포 후 회귀 없음). PJ1 시험 계정에는 filesystem MCP가 배정되지 않아
  전체 폴더 차단의 실제 하네스 재현은 미실행(시험 대상 MCP를 Claude가 스스로 승인·배정하지 않음).
- SIEM 전달 워커는 기본 꺼짐(`--with-siem`). 수집기 미연결로 실제 전달은 미실행.
