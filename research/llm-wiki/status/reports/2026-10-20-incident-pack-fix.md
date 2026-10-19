# 2026-10-20 사고 증빙 패키지 오류 수정

- 작업자: Codex luna
- 코드 기준: `001092bcfae8961515e873452314c040d55b6c0f`, 작업 트리 변경 중
- 변경 파일: `full_stack_lab/gateway/app/incidents.py`, `full_stack_lab/gateway/app/incident_pack.py`
- 시작 근거: DEV-66, D-144, 솔루션 기기 `python tests/incident_pack_check.py` 오류
- 해결할 문제와 완료 조건: 평가 시각이 없는 사고도 타이머에서 처리하고, 응답 JSON의 패키지 해시를 재검증할 수 있게 한다.

## 결과

평가 전 사고에서는 `assessed_at`이 NULL일 수 있으며, 과거 행/대역 데이터에서는 열 키가 없을 수도 있어 `list_cases`, `detail`, `check_deadlines`에서 선택 필드로 읽는다. 패키지 생성 때 Python의 `datetime` 기본 문자열 표현(공백 구분)을 사용하고 검증 때 API JSON의 ISO 표현(T 구분)을 사용해 해시가 달라졌다. 패키지 해시의 datetime 기본 직렬화를 ISO 형식으로 통일하고 해시 필드를 제외한 정렬 키 UTF-8 JSON을 유지했다. 시험 단언은 수정하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수 시험 | `python tests/incident_pack_check.py -v`, 로컬 | 4 통과, `psycopg` 부재로 게이트웨이 대역 시험 2건 건너뜀 | 터미널 결과 |
| 해시 왕복 | `python -c` native seal → ISO JSON → verify 검사 | 통과 | 터미널 결과 |
| 정적 검사 | `python -m py_compile gateway/app/incidents.py gateway/app/incident_pack.py tests/incident_pack_check.py` | 통과 | 종료 코드 0 |
| 패치 공백 검사 | `git diff --check` | 통과 | 종료 코드 0 |
| 게이트웨이 이미지 | `python tests/incident_pack_check.py` | 수정 후 미실행 | 솔루션 기기 재확인 필요 |
| PJ1·운영 효과 | 미실행 | 미확인 | — |

## 실패·미완료·한계

로컬에서 `psycopg`가 없어 사고 타이머 경보와 상세 패키지 조립 대역 시험을 직접 실행하지 못했다. 솔루션 기기에서 `python tests/incident_pack_check.py`를 다시 실행해야 한다. 이 수정은 인코딩된 `datetime` 값을 정규화하며, 다른 사용자 정의 객체는 기존처럼 문자열로 직렬화한다.

## 다음 작업

DEV-66의 솔루션 기기 사고 타이머·패키지 해시 결과를 재확인한다.

## 사용자에게 필요한 입력

없음.
