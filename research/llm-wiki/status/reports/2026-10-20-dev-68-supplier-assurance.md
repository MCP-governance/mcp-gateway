# 2026-10-20 DEV-68 공급자 보증·등록부 내보내기·지원 종료 경보

- 작업자: Codex luna
- 코드 기준: 시작 commit `09220f515bea70a498b921f4e23eafd605e8444b`, 브랜치 `10/20-supplier-assurance`, 시작 시 clean. 원격 HEAD 확인은 네트워크 연결 실패로 미완료.
- 변경 파일: `full_stack_lab/gateway/app/supplier_assurance.py`, `agent_service.py`, `core.py`, `main.py`, `agent_static/console.js`, `full_stack_lab/tests/supplier_assurance_check.py`, `docs/ai/DECISIONS.md`, `docs/ai/POLICY.md`, 이 보고서, `status/backlog.md`의 DEV-68 마지막 칸.
- 시작 근거: DEV-68, [규제 근거 개발 계획](../../analysis/compliance/dev-plan/README.md) 2장·CAP-3·RQ-04, [정책 ID 매핑](../../analysis/drive-curation/policy-id-mapping.json)의 POL-03·07·01·39.
- 해결할 문제와 완료 조건: 필수 공급자 보증이 없는 서버의 승인을 막고, 대장과 일치하는 JSON·CSV 내보내기와 생성 해시를 제공하며, 지원 종료 뒤 기존 승인 만료 경로로 호출을 차단한다.

## 결과

- 승인 시 공급자 법인명, 공급자 연락처, 보안 연락처, 지원 종료일, 취약점 공개 정책 HTTPS URL을 필수 검사한다. 누락·지난 날짜·잘못된 URL은 한국어 사유로 거부한다. 승인 증거와 런타임 대장에 같은 값을 보존한다. 하위 처리자 여부, SBOM/VEX 제출 여부, 계약 근거 참조, 종료 전략 메모는 선택 항목으로 함께 보존하고 내보낸다.
- 지원 종료일 다음 날 00:00 UTC를 승인 유효기한의 상한으로 두고, 자동 연장도 그 상한을 넘지 않게 했다. 만료 이후 기존 `P-APPROVAL-EXPIRY-001`이 실행을 막고 Console은 재승인 대기로 표시한다. 새 OPA 정책 ID와 DB 열은 추가하지 않았다.
- 관리자 인증 API `/api/registry/export?format=json|csv`는 런타임 대장의 도입 서버 행을 ID 순으로 반환한다. JSON 본문 또는 `X-Registry-SHA256` 응답 헤더에 동일 행 정본의 SHA-256을 제공한다. Console에 두 형식의 내보내기 버튼, 승인 입력란, 서버 상세 필드와 30일 내 지원 종료 경보를 추가했다.
- 기존 시험 기대값은 변경하지 않았다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 검사 | `python -m py_compile full_stack_lab/gateway/app/supplier_assurance.py full_stack_lab/gateway/app/agent_service.py full_stack_lab/gateway/app/core.py full_stack_lab/gateway/app/main.py full_stack_lab/tests/supplier_assurance_check.py` | 통과 | 로컬 종료 코드 0 |
| 정적 검사 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 로컬 종료 코드 0 |
| 단위 검사 | `python -B -X utf8 full_stack_lab/tests/supplier_assurance_check.py` | 순수 검사 4건 통과, 게이트웨이 승인 API 1건은 FastAPI 미설치로 건너뜀 | 로컬 unittest 출력 |
| 회귀 검사 | `node --test full_stack_lab/tests/console-state.test.mjs` | 15건 통과 | 로컬 Node 테스트 출력 |
| 인증 경로 검사 | `python -B -X utf8 full_stack_lab/tests/open_endpoints.py` | 통과: 공개 1개·인증 필요 74개 | 로컬 검사 출력 |
| 공백 검사 | `git diff --check` | 통과 | 로컬 종료 코드 0 |
| 정적 분석 | `python -m pyflakes ...` | 미실행: 이 PC에 pyflakes 모듈 없음 | `No module named pyflakes` |
| 배포·실기기 | 솔루션 기기 `field up`, PJ1 실제 하네스 | 미실행 | — |

## 실패·미완료·한계

- 현재 PC에는 FastAPI가 없어 관리자 승인 API 통합 검사는 건너뛰었다. `supplier_assurance_check.py`는 게이트웨이 이미지에서 재실행해야 한다.
- 등록부 값은 승인자가 입력한 연락처·정책 주소다. 제공자 측 실재·연락 가능성·문서 내용은 자동 확인하지 않는다. CSV와 JSON 해시는 같은 정렬 행 집합에 대한 식별값이며 서명·감사 원장 증명은 아니다.
- 등록부는 MINT 런타임 항목을 내보내며 DORA 정보 등록부의 전체 공식 서식 적합성은 평가하지 않았다. 실기기에서 실제 만료 차단과 OPA 판정, 등록부 응답/다운로드는 아직 확인하지 않았다. 원격 기본 브랜치 확인은 네트워크 오류로 확인하지 못했다.

## 다음 작업

DEV-68: 솔루션 기기에서 `python -B -X utf8 tests/supplier_assurance_check.py`와 기존 Gateway 확인을 실행하고, PJ1에서 필드 누락 차단·내보내기 대장 일치·지원 종료 만료 차단/재승인을 확인한다.

## 사용자에게 필요한 입력

없음
