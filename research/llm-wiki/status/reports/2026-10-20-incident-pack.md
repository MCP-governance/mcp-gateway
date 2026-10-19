# 2026-10-20 사고 증빙 패키지와 관할별 보고 기한 타이머

- 작업자: Codex luna
- 코드 기준: `9761dc6167696015dac00bd7a619fe0c8b1a0345`, 시작 시 작업 트리 깨끗함, 브랜치 `10/20-incident-pack`
- 시작 근거: DEV-66, 규제 근거 개발 계획 2장·6장, D-144
- 해결할 문제와 완료 조건: 관리자가 사고 영향 범위를 원장 질의로 묶고 호출 수·체인 검증·패키지 해시를 확인하며, 관할 팩의 보고 기한 경과를 경보한다.

## 결과

- `incident_cases`와 기존 추가 전용 `approval_events`를 사용해 관리자 인증 API에서 사고 생성·목록·상세 패키지·보고 완료를 처리한다.
- 원장 호출 조회와 건수 집계, 전체 해시 사슬 검증은 같은 반복 읽기 스냅샷에서 수행한다. 패키지는 결과 네 축·승인/철회·연결 중지 이력·관할 기한과 SHA-256을 포함한다. 요청·응답 본문은 포함하지 않고 주체 식별자는 해시 참조로 표시한다.
- field 레지스트리에 관할 JSON 팩을 두고 일반·field 전용 레지스트리 마운트에서 읽는다. 단계별 기한과 팩 운영값에 따른 임박·초과 경보를 처리한다. 평가 시각·수정 가능 시점이 없거나 법정 시한이 불명확한 단계는 `수동 확인 필요`; 타이머 heartbeat가 없으면 `확인 불가`로 표시한다.
- 감사 기록 화면에서 사고별 관할 단계와 기한, 타이머 상태를 보여 주며 선택 시 패키지 건수·해시 사슬·해시를 확인한다.
- D-144에 RQ-01~RQ-08의 권장 선택과 근거·한계를 기록했다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수·대역 시험 | `python -X utf8 tests/incident_pack_check.py` (`full_stack_lab/`) | 6개 중 4개 통과, DB 기반 2개는 `psycopg` 부재로 건너뜀 | 터미널 출력 |
| 정적 구문 | `python -m py_compile gateway/app/incident_pack.py gateway/app/incidents.py gateway/app/main.py gateway/app/ops_response.py tests/incident_pack_check.py` (`full_stack_lab/`) | 통과 | 터미널 출력 |
| 콘솔 구문 | `node --check gateway/app/agent_static/console.js` (`full_stack_lab/`) | 통과 | 터미널 출력 |
| 관할 팩 형식 | `python -X utf8 -c "import json; from pathlib import Path; p=Path('registry/field/incident_jurisdictions.json'); print(len(json.loads(p.read_text(encoding='utf-8'))['packs']))"` (`full_stack_lab/`) | 9개 관할 팩 | 터미널 출력 |
| diff 공백 검사 | `git diff --check` | 통과 | 터미널 출력 |
| 정적 분석 | `python -m pyflakes full_stack_lab/gateway/app/incident_pack.py full_stack_lab/gateway/app/incidents.py full_stack_lab/gateway/app/main.py full_stack_lab/gateway/app/ops_response.py full_stack_lab/tests/incident_pack_check.py` | 실패: pyflakes 미설치 | 터미널 출력 |
| 실제 DB·기기 | 솔루션 기기 / PJ1 | 미실행 | 사람 확인 필요 |
| 브라우저 | 솔루션 기기 콘솔 | 미실행 | 사람 확인 필요 |

## 실패·미완료·한계

- 해시 사슬이 손상된 경우에도 패키지는 검증 실패 상태를 포함한다. 패키지 해시는 서명이 아니며 원장 진위의 외부 부인 방지 증명은 아니다.
- 관할 팩은 계획서의 조사 표에 근거한 잠정 데이터다. 경보 선행 시간은 팩의 운영 기준이지 법정 기한이 아니다. 규제 적용성·평가 시각·시행령 위임 값은 법적 판단이 아니며 해당 단계는 수동 확인 필요로 남는다.
- DB 마이그레이션, 반복 읽기 동시성, 경과 경보 DB 기록, 브라우저 표시, 실제 배포·PJ1 하네스는 아직 확인하지 않았다.
- 시작 시 원격 HEAD 재확인을 시도했으나 GitHub 연결이 막혀 최신 원격 기준은 확인하지 못했다. 작업은 이미 생성된 `10/20-incident-pack` 브랜치와 커밋을 기준으로 했다.

## 다음 작업

- DEV-66: 솔루션 기기에서 마이그레이션과 관리자 API를 실행하고, PJ1에서 합성 사고 원장 건수·봉인 해시·경보를 검증한다.

## 사용자에게 필요한 입력

없음. 실제 기기·PJ1 검증은 담당자가 런북에 따라 수행한다.
