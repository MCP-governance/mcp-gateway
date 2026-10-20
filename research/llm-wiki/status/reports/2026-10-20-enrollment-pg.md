# 2026-10-20 G08.01 조직가입·장치 enrollment·활성화·재접속 PostgreSQL 회귀

- 작업자: Codex luna
- 코드 기준: `22238b54f2a5ce1a18c19e0f3968658d264c6c72`, 브랜치 `10/20-enrollment-pg`; 시작 트리 clean. 커밋하지 않음.
- 시작 근거: WBS G08.01 완료 조건, [기능명세·WBS](../../analysis/feature-spec-2026-10-17/README.md), `managed_enrollment_check.py`, `token_revocation_pg_check.py`
- 해결할 문제와 완료 조건: 미승인·미수락 계정의 키트 발급, 등록 대기 중 호출, 비준수·오래된 heartbeat의 격리, 독립 관리자 활성화, 같은 장치 재등록 뒤 이전 토큰을 실제 PostgreSQL에서 확인한다.

## 결과

`enrollment_token()`이 실제 활성 계정만 등록 키트를 받도록 제한했다. 동일 소유자·호스트·플랫폼·로컬 계정으로 다시 등록하면 기존 활성 장치를 같은 DB 트랜잭션에서 폐기하고 폐기 이벤트를 남긴 뒤, 과거 장치의 토큰·MCP 세션도 회수한다. 오래된 heartbeat로 접근이 시도되면 장치 상태를 `quarantined`로 바꾸고 이벤트를 추가한다. 정상 heartbeat는 격리를 풀지 않으며 관리자가 다시 활성화해야 한다.

새 `full_stack_lab/tests/enrollment_pg_check.py`는 실제 DB 행 조회와 관리형 사용자 인증 흐름을 함께 확인한다. Linux의 UID와 Windows의 SID·helper 명령으로 같은 제품 함수를 실행하며, 가입 승인 전/미수락 초대·비활성 계정·1회용/만료 토큰·대기 장치·자가 활성화·정책 불일치·검사 실패·다른 장치 키·180초 초과 heartbeat·재등록 새 epoch를 검사한다. 기존 실행에서 난 세 실패는 시험 실행 함수 `main()`이 모듈 별칭을 가리던 문제와, 장치 소유자를 활성화 actor로 사용한 문제였다. 별칭 충돌을 없애고 DB에 별도 관리자 principal을 등록해 그 principal로 활성화한다.

재등록 회귀는 이전 장치 상태와 기존 토큰의 401 외에 기존 세션의 종료 행과 풀 정리 알림을 확인한다. 알림은 다른 게이트웨이 프로세스에 풀을 닫도록 전파하는 DB 이벤트이며, 이 시험은 실제 연결 풀이 열린 상태에서 소켓이 닫히는 것은 확인하지 않는다. 실제 외부 MCP 도구 호출은 하지 않는다.

제품 보강 이유는 기존 코드에서 키트 발급이 계정 상태를 확인하지 않았고, stale heartbeat는 요청만 거부한 채 DB에 활성 상태를 남겼으며, 재등록은 이전 장치 행·토큰을 회수하지 않았기 때문이다. 이 과제에 지정된 D-번호가 없어 DECISIONS.md에는 새 번호를 만들지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m py_compile full_stack_lab/gateway/app/endpoint_plane.py full_stack_lab/tests/enrollment_pg_check.py` · Windows 작업 트리 | 통과 | 종료 코드 0 |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py` · Windows 작업 트리 | 통과, 24개 정책 경로 존재; 런타임 검증 대기 | 종료 코드 0, `catalogs/threats.json` 갱신 |
| 위키 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` · Windows 작업 트리 | 오류 0; 무시된 로컬 원본 누락 경고 존재 | 종료 코드 0, 검사 JSON `ok: true` |
| 수정 후 구문 검사 | `python -m py_compile full_stack_lab/tests/enrollment_pg_check.py full_stack_lab/gateway/app/endpoint_plane.py` · Windows 작업 트리 | 통과 | 종료 코드 0 |
| pyflakes | 공통 CI 명령 · Windows 작업 트리 | 실행 불가: 현재 Python에 `pyflakes` 모듈 없음 | `No module named pyflakes` |
| 격리 PostgreSQL / managed-user 흐름 | 아래 솔루션 기기 명령 | 미실행 | 미실행 |

## 실패·미완료·한계

수정 후 격리 PostgreSQL 시험을 다시 실행하지 않았다. 실제 Linux·Windows 설치도 이 노트북에서 실행하지 않았다. 새 회귀는 API/DB 제품 함수와 인증 경계를 확인하지만 OS 설치기 자체, 실제 엔드포인트의 helper 동작, 활성 연결 풀이 닫히는 런타임 효과, PJ1 설치는 증명하지 않는다. 재등록 장치의 식별은 소유자·호스트 이름·플랫폼·로컬 사용자 식별자의 조합이므로, 이 식별값이 복제된 장치까지 하드웨어 수준으로 구분하지 않는다. 외부 원격 기본 브랜치 조회는 네트워크 연결 오류로 확인하지 못했다.

## 다음 작업

솔루션 기기에서 격리 실험실을 올린 뒤 새 PostgreSQL 회귀를 실행한다. 이후 실제 Linux·Windows 설치에서 키트 수락·관리자 활성화·heartbeat 복구·이전 토큰 거부를 확인하고 G08.01 검수 상태를 갱신한다.

```bash
cd full_stack_lab
tests/termination_dispatch_lab.sh up
tests/termination_dispatch_lab.sh run enrollment_pg_check.py
tests/termination_dispatch_lab.sh down
```

## 사용자에게 필요한 입력

없음. 실제 설치·PJ1 검수는 저장소 소유자 규칙에 따라 사람이 솔루션 기기에서 실행한다.
