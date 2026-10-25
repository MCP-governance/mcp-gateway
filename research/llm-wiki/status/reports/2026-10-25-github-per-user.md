# 2026-10-25 GitHub 직원별 계정 연결 (D-235)

- 작업자: Claude Code
- 코드 기준: 71af968 위 브랜치 `10/25-github-per-user`, 실제 변경은 커밋 d9fe21a의 `user_credentials.py`·`upstream.py`·`core.py`·`agent_service.py`·`decommission.py`·`console.js` 등
- 시작 근거: 소유자 결정(10-25) 「GitHub는 직원별로 각자 계정을 연결」, 백로그 없음(리더 지시)
- 해결할 문제와 완료 조건: 운영자 공유 토큰 하나가 전체 직원의 GitHub 호출에 쓰이고 자격 없는 직원은 익명 401 「오류」를 받던 문제. 직원이 각자 연결한 자격을 쓰고, 없으면 상위 서비스를 부르지 않고 연결 방법을 알린다.

## 결과

구현됨: 암호화 저장(AES-GCM, `USER_CREDENTIAL_KEY`), 선택 순서(직원 연결 → 운영자 파일의 그 직원 행 → 없음, 같은 endpoint 여러 행), `MCP-CREDENTIAL-001` 차단과 안내, 콘솔 「내 연결」(토큰 붙여넣기·장치 인증·해제), 계정 삭제·중지·잠금과 이용 관계 종료 때 삭제·회수 증거, 값 없는 원장 사건. 배포·실기기 검증은 하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | pyflakes, `node --check console.js`, `node --test tests/*.test.mjs` 48건, `open_endpoints.py` | 통과 | |
| 단위 | `tests/user_credential_check.py` 23건 (Windows·WSL), `credential_binding_check`(WSL), `upstream_session_reuse_test` 40건, `fresh_requester_check` 10건 | 통과 | 대역 DB·GitHub |
| 프로토콜 | GitHub 장치 인증 RFC 8628 전이(대역) | 통과 | 실제 GitHub 아님 |
| 실제 모델·하네스 | PJ1 | 미실행 | |
| upstream 효과 | 실제 GitHub 토큰·OAuth App | 미실행(금지) | |
| 배포·정책 해시 | 기기 배포 | 미확인 | |

## 실패·미완료·한계

D-235 한계 항목 참조: OAuth App 토큰이 GitHub MCP에서 받아들여지는지 미확인, 장치 흐름 상태는 단일 프로세스 메모리, 연결 없는 상태의 계약 확인은 운영자 행 필요.

## 다음 작업

리더 배포 뒤 PJ1(aaaa)에서: 미연결 호출 차단 문구, 토큰 연결 후 호출, 해제 후 다시 차단.

## 사용자에게 필요한 입력

장치 인증을 쓰려면 조직의 GitHub OAuth App(Device Flow 사용) client id. 없으면 토큰 붙여넣기만 보인다.
