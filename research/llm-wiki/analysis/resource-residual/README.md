# DEV-08 발급 토큰과 자원 서버의 잔존 재접근

2026-10-20 · Codex sol · D-156 · 브랜치 `10/20-resource-server-residual` · 시작 `bac155a8b78222fc878ff642ea1aa177ddb82fba`.
정본은 이 문서와 [원자 요구사항·코드 지문](requirements.json)이다. [작업 보고](../../status/reports/2026-10-20-resource-server-residual.md)의 실행 결과와
기기 절차를 구분한다. [종료 모델](../../../../docs/ai/TERMINATION_MODEL.md)·[결정 기록](../../../../docs/ai/DECISIONS.md)의 D-146·D-123·D-154를 전제로 한다.

## 확인한 경로와 수정

| 요구사항 | 코드·현재 사실 | 정상·음성·경계·실패·경쟁·복구 증거 |
| --- | --- | --- |
| RS-01 발급 접근 토큰 재접근 | [idp.py](../../../../full_stack_lab/gateway/app/idp.py) `introspection`·`introspect_jti`·`introspect`: 응답 캐시 없음, TTL 0, HTTP `no-store`. 서명·폐기 목록·현재 계정·관리형 인증·SSO 검사 | 새 로컬 시험의 활성→DB 철회 즉시 비활성, 계정/장치 실패, 무효 서명, 서명 폐기 표식. 새 PG 시험의 실제 JWT·철회·401은 미실행 |
| RS-02 갱신 토큰의 현재 발급 가능성 | 같은 파일 `introspection`: 기존 행의 폐기·회전·만료 검사에 계정 없음/중지·관리형 전환·OIDC 전환 시 비활성 추가 | 활성·중지·복구, 알 수 없는/회전/만료 토큰, 서명 폐기, DB 장애 뒤 활성 응답 재사용 없음. 기존 발급/회전 순서는 변경 안 함 |
| RS-03 자원 서버 응답의 우선순위 | [decommission.py](../../../../full_stack_lab/gateway/app/decommission.py) `STATE_EVIDENCE_FOR`에 두 토큰 종류의 `resource-rejection` 누락 보완. `_judge_target`의 기존 잔존 판정 재사용 | 수정 전 새 시험에서 client/refresh 토큰 모두 수락 증거를 무시해 T1, 직접 거부만 있으면 T3(3실패). 수정 후 수락 T2·거부 T1·증거 없음/폐기 전 증거 T3 통과 |
| RS-04 서버 보유 별도 자격 | 같은 파일 `seed_targets`·`collect`·`_resource_verdict`·`revoke_credential`: `server_held_credentials` 고지와 조직 확인 권한 분리, 보호 자원에 같은 PAT 재제시 | 로컬 판정은 목록 부재보다 실제 수락 우선. PG 절차는 Gitea에 전용 PAT를 만들고 상위 JWT 폐기 전 200→이후에도 200→하위 PAT 폐기 뒤 401 및 T2→T1 대상 등급 확인. 기기 미실행 |
| RS-05 업스트림 풀·세션 | [upstream.py](../../../../full_stack_lab/gateway/app/upstream.py) `release_pool`·`_sweep`·`maintain_pool`; [upstream_sessions.py](../../../../full_stack_lab/gateway/app/upstream_sessions.py) `Pool.close`·`borrow`; [mcp_sessions.py](../../../../full_stack_lab/gateway/app/mcp_sessions.py) `terminate` | 기존 종료 개시가 풀 폐기와 세션 종료를 호출. 로컬에서 사용 중 lease·대기자 모두 옛 세대 재사용 거부, close 완료·재호출 0 확인. PG에서는 개시 전 결속한 세션의 개시 후 거부와 최종 dispatch 의도 0 확인 예정 |
| RS-06 실행기 잔존 | [worker.py](../../../../full_stack_lab/runtime/worker.py) `approval_problem`·`run_job`·`reconcile`·`remove_runtime_resources`: 빌드/실행 전 재검사, 종료 시 STOPPING, 제거 잔존이면 재시도 | 로컬 엔진/DB 대역으로 TERMINATING·RETIRED 각각 자원 1개 잔존 시 성공 사건 없음→잔존 0이면 STOPPED/감사 사건. 실제 컨테이너 제거·이미지·다중 워커 미실행 |
| RS-07 T1~T3 범위 | `_judge_target`·`assess`: 발급자 상태만 확인한 토큰 대상 T1과 전체 이용 관계 종료를 구분 | 동일 inactive 상태라도 서명 자체 검증의 만료 공백은 T2, 증거 없음은 T3. 새 PG 절차에서 발급자 T1 대상이 있어도 미확인 대상·게이트웨이 경로가 남은 전체 케이스 T3 확인 예정 |

실행 증거: [로컬 검사 기록](checks.json). 새 [로컬 시험](../../../../full_stack_lab/tests/resource_residual_check.py)은 제품 AST 함수와 표준 라이브러리 풀을 실행하며 DB/인증·엔진 응답만 대역이다.
새 [PostgreSQL 시험](../../../../full_stack_lab/tests/resource_residual_pg_check.py)은 `isolated_disposal()`·실제 발급 함수·폐기 함수·종료 판정을 사용한다.
자체 MCP 서버를 만들지 않는다. Gitea 전용 PAT는 합성 고지 자격 fixture이며 실제 MCP 컨테이너에 주입하지 않는다.
따라서 그 시험도 MCP 서버가 실제로 자격을 보유했다는 증거나 PJ1 하네스 결과로 세지 않는다.

## TTL·자격·실행 경계

- introspection 응답 TTL은 0이다. 외부 자원 서버가 자체 캐시를 쓰는지/얼마나 쓰는지는 미확인이다. `no-store`만으로 외부 인가 캐시를 강제 폐기했다고 주장하지 않는다.
- MCP SDK 클라이언트는 `cache=None`. 대화 연결 풀은 기본 유휴 60초·수명 600초이며 토큰 활성 캐시가 아니다. 종료 때는 TTL을 기다리지 않고 해당 풀을 폐기한다.
- 다른 게이트웨이 프로세스의 풀 폐기는 DB 사건을 기본 2초 간격으로 확인한다. 사건 전달 실패·진행 중 I/O·정비 작업 시간까지 포함한 제거 상한은 보장하지 않는다. 새 전송 거부는 별도 최종 `dispatch.record`의 현재 상태 검사다.
- 실행기 기본 poll은 5초지만 실행 중 빌드/조회/장애 재시도로 늦어질 수 있다. 종료 API가 즉시 컨테이너 제거를 완료하는 것은 아니다. 운영 실행기의 제거/잔존 사건을 추가로 확인해야 한다.
- 게이트웨이 토큰 폐기는 조직 전체 신원의 폐기와 서버별 이용 관계 종료가 다르다. 관계 종료 때문에 다른 서버에 쓰는 직원 토큰 전체를 폐기하지 않는다. 기존 토큰으로 해당 관계에 새 전송은 불가하지만 다른 허용 관계의 신원 인증은 유지될 수 있다.
- 서명만 검증하는 자원 서버는 유효한 JWT를 `exp` 전까지 계속 수락할 수 있다. 이를 막는 새 서버나 토큰 형식을 만들지 않는다. 기존 E1 함수의 로컬 서명 검증 비교를 실제 자원 서버 요청으로 부르지 않는다.
- 확인한 자원·자격·시점에 한정한다. 외부 캐시/복제/미고지 하위 자격은 별도 모집단과 재접근 관측이 필요하다. 게이트웨이 introspection만으로 그 자원의 C4를 채우지 않는다.
- D-123 서명 목록은 복원 차단이지 자원 서버 폐기 증명이 아니다. D-154 회전 커밋→서명 append 사이 장애/과거 DB 복원의 공백은 이번 변경으로 닫히지 않는다.

## 공개 스킬·OSS·명세 대조

구현 전 GitHub 검색으로 `oauth token revocation introspection skills` 및 기존 의존성 PyJWT를 확인했다. 외부 스킬의 스크립트·자격 출력 예시는 실행하지 않았다.

| 출처·판본·라이선스 | 읽은 범위·채택 | 고정·유지보수 확인의 한계 |
| --- | --- | --- |
| [RFC 7662 §4](https://www.rfc-editor.org/rfc/rfc7662.html#section-4), 2015 표준 | 자원 서버의 introspection 캐시가 철회 후 잔존 접근 창을 만들며 `exp` 이후 캐시 금지. 내부 캐시를 새로 만들지 않는 근거 | 구현/실행 증거가 아닌 규범. 외부 TTL은 이 문서로 추정하지 않음 |
| [PyJWT `2.14.0` api_jwt.py](https://github.com/jpadilla/pyjwt/blob/2.14.0/jwt/api_jwt.py), [MIT](https://github.com/jpadilla/pyjwt/blob/master/LICENSE) | 기존 `requirements.txt`의 `PyJWT==2.14.0` 및 서명/issuer/audience 검증 API 재사용 | 태그 소스 열람, upstream commit SHA와 기기 설치 판본은 미확인. 새 의존성 없음 |
| [Zoom OAuth 공개 스킬](https://github.com/zoom/skills/blob/main/skills/oauth/SKILL.md), [MIT](https://github.com/zoom/skills/blob/main/LICENSE) | 검색 결과의 토큰 생명주기 범위만 후보 확인. Zoom 전용 흐름이므로 MINT 구현에는 미채택 | main commit API/이력 조회 실패, 고정 commit·유지보수 검증 미완. 설치/스크립트 실행/코드 복사 없음 |
| [기존 SDK 분석](../oss-deep/deps-sdk-authlib-opa.md), MCP SDK `v2.2.0`, `9972c21aa42054fb1450c5fc614761ed11847ec6`, MIT | 기존 분석의 Client/캐시·취소 범위와 현재 `cache=None`·동일 task 해제 코드 대조. 새 풀/캐시 라이브러리 도입 없음 | commit은 기존 분석의 고정값이며 이번 네트워크 재조회 결과가 아님. 실제 컨테이너 SDK와 일치 여부·유지보수 현재 상태는 기기 확인 필요 |

원격 HEAD는 시작 시 `git ls-remote --symref origin HEAD`를 실행했으나 github.com:443 연결이 거부됐다.
이번 변경은 현재 브랜치·현재 시작 commit 기준이며 원격 최신성은 주장하지 않는다. 외부 전문을 저장/재배포하지 않고 링크·자체 요약만 남겼다.
