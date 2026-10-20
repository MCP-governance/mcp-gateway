# 2026-10-20 S7 출력 계약 적대 검증

- 작업자: Codex luna
- 코드 기준: `3ea141c239080bbd83f8e49911d2c8983d98ffe1`, 브랜치 `10/20-output-contract-review`; 기존 미추적 `2026-10-20-loopback-test.md` 보존
- 시작 근거: DEV-44 / S7 / D-149, [출력 계약 연구](../../analysis/output-contract-d149/README.md)
- 해결할 문제와 완료 조건: 기존 시험 변경 4건의 기대값 완화 여부 판정, 출력 계약 공격 경로 확인, 확실한 결함 최소 수정, 판정·근거·한계를 분석 정본에 기록

## 결과

기존 시험 변경은 `catalog_refresh_check.py` A, `contracts_check.py` A, `dispatch_recheck_check.py` A로 채택했다. `selective_restriction_siem_check.py`는 B로 판정하고 버전 승격 대역에도 승인·관측 출력 해시 비교를 추가했다. 어느 변경에서도 과거 실패를 통과시키도록 기대값을 완화한 부분은 없었다.

기존 승인 해시 부재가 출력 스키마 부재의 canonical hash로 해석되어 outputSchema를 광고하지 않는 기존 도구의 승인을 유지한다. 외부 `$ref` 해석 차단, 마스킹 뒤 스키마 재검증, 2025-06-18·2025-11-25 객체 보존과 2026-07-28 JSON 값 보존, 최종 dispatch SQL·같은 연결 재확인의 출력 해시 비교를 코드에서 확인했다. 스키마 검사 전 깊이 64·컨테이너 10,000개·약 256 KiB 상한을 추가했다. `isError=true`도 검사하는 D-149 선택은 유지하고 공식 SDK와의 차이를 한계로 기록했다.

세부 판정과 코드 경로는 [S7 적대 검토](../../analysis/review-1020/s7-output-contract.md)에 기록했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수·DB 대역 검사 | `python -B -X utf8 full_stack_lab/tests/output_contract_check.py --pure` | 통과, 9건 | 콘솔 결과 |
| Python 구문 | `python -m py_compile full_stack_lab/gateway/app/output_contract.py full_stack_lab/gateway/app/core.py full_stack_lab/gateway/app/upstream.py full_stack_lab/tests/output_contract_check.py full_stack_lab/tests/selective_restriction_siem_check.py` | 통과 | 콘솔 결과 |
| JavaScript 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 콘솔 결과 |
| 정적 분석 | `python -m pyflakes` 변경 Python 파일 | 미실행: pyflakes 모듈 없음 | `No module named pyflakes` |
| diff 공백 검사 | `git diff --check` | 통과 | 콘솔 결과 |
| 게이트웨이 이미지 | 미실행 | 미실행 | 솔루션 기기에서 실행 필요 |
| 프로토콜·실제 하네스 | 미실행 | 미실행 | PJ1에서 판본별 호출 필요 |
| upstream 효과 | 미실행 | 미확인 | 상용/공개 MCP 대상으로 확인 필요 |
| 배포·DB 전환·경쟁 | 미실행 | 미확인 | 솔루션 기기에서 검증 필요 |

## 실패·미완료·한계

schema 상한은 복잡한 정상 스키마를 거부할 수 있고 정규식의 병적 역추적 시간은 별도 통제되지 않았다. 공식 SDK는 오류 응답의 outputSchema 검증을 생략하는 구현이 있어, MINT의 stricter 동작이 모델 재시도 흐름에 미치는 영향은 상호운용성 검증이 필요하다. Python 3.10 및 게이트웨이 이미지 의존성 제약으로 이미지 시험은 사람의 실행이 필요하다.

## 다음 작업

DEV-44 기기·PJ1 시험: 솔루션 기기에서 `output_contract_check.py` 전체와 관련 게이트웨이 체크를 실행하고, PJ1 하네스에서 2025-06-18·2025-11-25·2026-07-28 정상/오류/불일치 결과를 확인한다. 실제 DB 전환·동시 호출에서 최종 전송 전 출력 해시 재확인을 확인한다.

## 사용자에게 필요한 입력

없음. 실제 기기·PJ1 실행은 담당자가 수행한다.
