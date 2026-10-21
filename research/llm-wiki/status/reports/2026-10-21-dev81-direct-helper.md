# 2026-10-21 DEV-81 F1 직접 실행 관문과 parser 결함

- 작업자: Codex sol (autopilot), 임시 통합 담당
- 시작 기준: clean `main`, fetch·fast-forward 후 `204579981ac02956a3ee40301f251ee99af9de6e`. 원격 HEAD는 `main`으로 재확인.
- 브랜치: `10/21-dev81-direct-helper`.
- 시작 근거: DEV-81 F1, D-183, loop 대기열 우선순위. 한 항목만 처리.
- **메인 판단 필요: 병합하지 않는다. F1 직접 실행은 미완료이며 강제 단계는 켜지 않았다.**

## 결과

고정 Codex 0.158.0의 헤더 헬퍼는 항상 `sh -c`로 실행된다. 설정을 절대 경로로 바꾸는 것으로 해결되지 않는다. 다른 vendor 경로나 자격 전달 체계를 임의로 만들지 않았다.

실제 AppArmor parser로 검사하자 기존 강제 프로필의 pathname 소켓 주소 규칙이 문법 오류로 거부됐다. `bound_profile`의 후보를 파일 경로 권한과 익명 소켓의 로컬 연산으로 정정해 경고·강제 렌더링 컴파일 2건을 통과시켰다. 기존 오류 표본은 보존하고 실패를 음성 대조로 재현했다. abstract 소켓 접속 권한을 넓히지 않았다.

다만 기존 `header_broker_label_check.py:199`가 바로 그 잘못된 주소 문자열을 요구한다. **기존 시험은 한 줄도 변경하지 않았다.** 기대값 변경 판단과 실제 커널 경계 확인이 남아 있으므로 브랜치만 보존한다.

분석·공식 문서·판본·라이선스·소스 행·동작 한계는 [분석 정본](../../analysis/dev81-direct-helper/README.md), 실제 명령·출력·시각·hash는 그 하위 JSON에 있다. 문서 수집은 소스 확인이며 실제 vendor 하네스 실행 증거가 아니다.

## 검증

| 종류 | 실행·환경 | 결과·원본 |
| --- | --- | --- |
| 실제 문법 검사 | WSL AppArmor parser 4.1.7, `-Q -T` | 경고·강제 2/2, 과거 오류 표본 거부. [출력](../../analysis/dev81-direct-helper/parser-results.json) |
| 새 AST 추출 단위 시험 | Python 3.12, `header_broker_pathname_check.py` | 4/4. [명령·출력](../../analysis/dev81-direct-helper/checks.json) |
| 기존 AST 추출 시험 | `header_broker_label_check.py` | 19 통과·1 실패(199행의 잘못된 문법 단언), 기존 파일 무변경 |
| 전체 로컬 회귀 | 지정 venv, `run_local_suite.py` | 최종 집계는 아래 완료 기록과 [파일별 JSON](../../analysis/dev81-direct-helper/local-suite.json) 참조 |
| 정적 검사 | pyflakes, 새 Python 수집기 포함 | [원시 결과](../../analysis/dev81-direct-helper/checks.json) |
| 위키 | `map_threats.py` 후 `check_wiki.py --ci-ignored-local-sources` | 완료 기록 참조. 검토 동결 hash는 갱신하지 않음 |
| 실제 모델·하네스·MCP·upstream 효과 | 미실행 | 새 mock MCP 없음 |
| 커널 적재·기기 배포·PJ1·계정·자격 변경 | 미실행 | 이번 운영 금지 범위 준수 |

## 실패·미완료·한계

기존 잘못된 문법을 단언하는 시험이 실패하므로 실패 증가 금지 관문과 기존 기대값 무변경 관문을 충족하지 못한다. 메인이 단언을 바꾸기 전 병합 금지다. parser 컴파일은 파일 소켓 권한·커널 레이블·실제 하네스 정상/음성/경쟁/복구 효과를 입증하지 않는다. WSL은 커널 인터페이스 부재 경고를 출력했다.

지원 판본의 Claude 구현은 이번에 확인하지 못했다. 로컬 설치 판본을 지원 판본으로 대체하지 않았다. Windows·PC 키트의 같은 사용자 노출과 웹 Origin 실측도 남아 있다. `status/current.md`는 loop 공통 규칙에 따라 건드리지 않고, 이 보고와 백로그·queue에 인계한다.

## 다음 작업

메인은 기존 199행 단언과 문법 정정 후보를 검토한다. DEV-81 F1은 계속 열림이며 직접 실행 지원 판본 또는 별도 검토된 인증 경로가 필요하다. 강제 승격 전 실제 커널·정상군·동일 UID 공격군·실패·복구 확인은 별도 수행한다.

## 완료 기록

지정 Python 3.12의 최종 전체 회귀는 **89 통과·2 실패·18 외부 의존 생략(109파일)**이다. 지시 기준 89·1·18보다 실패가 1 증가했다. 실패 파일은 기존 `threat_trace_mapping_check.py`와 이번 문법 수정에 따른 `header_broker_label_check.py`뿐이다. 새 시험은 4/4, 기존 헤더 시험은 19/20, pyflakes는 종료 0이다. 기존 시험 파일·기대값·단언은 변경하지 않았다.

`map_threats.py`는 24개 정책을 재생성했고 stale 검토 파일은 20개다. 이어 실행한 `check_wiki.py --ci-ignored-local-sources`는 종료 0·오류 0이었다. 위협 검토 동결 hash를 고쳐 통과시키지 않았다. Gemini 독립 검토 결과와 브랜치 push 여부는 아래 후속 기록에 남긴다.

## 사용자에게 필요한 입력

없음. 판단 요청은 queue의 「메인 판단 필요」로 남긴다.

## 방향 제안

공식 하네스의 executable/argv 직접 실행 지원을 우선 확보한다. 셸 상속 허용·부모 PID 신뢰·환경 변수 토큰·새 MCP 중계로 우회하지 않는다. 기존 결정 D-183의 강제 승격 보류를 유지한다.
