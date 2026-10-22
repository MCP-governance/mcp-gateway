# 2026-10-22 OPS-INTAKE-PACKAGING-R3

- 작업자: Codex, implement. Agent Hub job `wf-OPS-INTAKE-PACKAGING-R3-implement-0`.
- 코드 기준: `10/22-runtime-recovery`, 시작 commit `62bafc49ec3f360415d229e24ee10b519c7cbe94`, 시작 작업 트리 clean. 기존 레인 유지, 결과 미커밋.
- 시작 근거: 사용자가 전달한 2026-10-22 12:50 KST 솔루션 호스트 관측. `intake_worker.py:28`의 `ModuleNotFoundError: No module named 'supplier_metadata'`, 재시작 1368→1369, OOMKilled=false. 이 작업의 직접 호스트 관측은 아니다.
- 해결할 문제와 완료 조건: 이미지에 필요한 로컬 모듈 누락을 스택 없이 재현하고 최소 소스 수정과 오프라인 회귀를 완료한다. 배포 검증은 별도 인계한다.

## 결과

제품 소스 변경은 `full_stack_lab/supply_chain/intake-worker.Dockerfile:41`의 `COPY --chown=worker:worker supplier_metadata.py /app/supplier_metadata.py` 한 줄이다. Compose의 실제 build context는 `./supply_chain`이다. 워커의 import(`intake_worker.py:28`)와 `validate`의 metadata 수집 호출(`:313`), `supplier_metadata.collect`의 데이터 전용 처리 및 기존 검사를 대조했다. 기존 import가 맞고 이미지 복사 목록이 빠져 있었다. 정책·신원·승인·스캐너 판정·실행 사용자·소유권 경계 변경은 없다. 기존 설계 복구이며 새 설계 결정은 없다.

새 파일 `full_stack_lab/tests/intake_worker_packaging_test.py`의 시험 **1개**는 AST로 워커의 로컬 import 의존성을 재귀 추적하고, Dockerfile의 명시적 Python COPY 입력만 저장소 내부 임시 디렉터리에 복사하여 `PathFinder`로 모듈 해석을 확인한다. 저장소의 `sys.path`가 누락을 가리는 것을 방지한다. 워커 포함 5개 로컬 모듈을 검사하며 unittest 및 기존 `run_local_suite.py`의 파일명 규칙으로 발견된다. 기존 시험의 assertion은 변경하지 않았다.

수정 전 동일 시험은 `supplier_metadata` 누락으로 실패했다. 워커의 실제 28행 import AST만 별도로 실행해 같은 예외를 재현하고, 수정 후에는 복사된 모듈의 `collect` 함수로 해석됨을 확인했다. 워커 전체 import·main 루프·DB·스캐너는 실행하지 않았다.

문서 변경은 이 보고서, 현황의 범위별 추가 항목, 백로그의 해당 작업 한 행, 위키 규칙에 따른 `status/repository-snapshot.json`과 `status/repository-snapshot.md`다. 기존 제품 완료 수치는 변경하지 않았다. 검사 증거는 [분석 기록](../../analysis/ops-intake-packaging-r3/checks.json)에 보존한다.

## 검증

환경: Windows PowerShell, Python 3.10.5. 2026-10-22 KST의 로컬 검사이며 정확한 명령·UTC 시각·출력·종료 코드는 [checks.json](../../analysis/ops-intake-packaging-r3/checks.json)에 있다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 누락 재현 | `py -3 -B -X utf8 -m unittest discover -s full_stack_lab/tests -p intake_worker_packaging_test.py -v`, 수정 전 | 예상 실패 1개, 누락 모듈 이름 일치 | [before.txt](../../analysis/ops-intake-packaging-r3/before.txt) |
| 실제 import 문장 | Dockerfile COPY 입력을 격리 배치하고 워커 28행만 실행 | 수정 전 ModuleNotFoundError, 수정 후 격리 모듈 해석 통과 | [수정 전](../../analysis/ops-intake-packaging-r3/import-before.txt), [수정 후](../../analysis/ops-intake-packaging-r3/import-after.txt) |
| 패키징 회귀 | 위 unittest 명령, 수정 후 | 1개 통과 | [checks.json](../../analysis/ops-intake-packaging-r3/checks.json) |
| 기존 회귀 | tests 디렉터리에서 `py -3 -B -X utf8 -m unittest intake_one_click_check.SuggestionCheck -v` | 8개 통과, 공급자 metadata의 불신 입력/잘못된 JSON 검사 포함 | checks.json |
| 정적 검사 | `py -3 -B -X utf8 full_stack_lab/tests/open_endpoints.py`, `schema_check.py` | 무인증 1개·인증 필요 95개 문서 대조, SQL 제약 12개 통과 | checks.json |
| 문법 | supply_chain Python 5파일과 새 회귀 1파일의 `compile(..., 'exec')` | 6파일 통과, 바이트코드 파일 미생성 | checks.json |
| lint | `py -3 -B -m pyflakes` supply_chain 5파일과 새 회귀 파일 | 실행 불가: `No module named pyflakes`, 통과 아님 | checks.json |
| 위키/공백 | capture_status.py, build_wiki.py, check_wiki.py --ci-ignored-local-sources 및 `git diff --check` | 스냅샷·목록·공백 통과. 새 미추적 디렉터리 링크를 파일 링크로 수정 후 위키 오류 0·경고 119로 통과 | [wiki-checks.json](../../analysis/ops-intake-packaging-r3/wiki-checks.json) |
| 프로토콜·실제 모델·하네스·upstream 효과 | 이번 범위에서 실행하지 않음 | 미실행 | 없음 |
| 이미지 빌드·배포·정책 해시 | 이번 범위에서 실행하지 않음 | 미확인 | 없음 |

## 실패·미완료·한계

- 원격 HEAD 재확인용 `git ls-remote --symref origin HEAD`는 github.com:443 연결 제한으로 실패했다. 우회하지 않았다. 브랜치 변경·index 변경·커밋·push·merge 없음.
- 로컬 Python은 이미지의 Python 3.12와 다르다. pyflakes 미설치, 전체 워커 import/스캐너 및 DB 회귀는 미실행이다. `datetime.UTC`를 쓰는 워커를 Python 3.10에 맞추거나 대역으로 바꾸지 않았다. metadata의 Python 3.12 tomllib 경로도 이번 기존 시험으로 입증하지 않는다.
- 새 시험은 현재 Dockerfile의 한 줄짜리 명시적 Python 파일 COPY 형식을 검사한다. Docker 전체 문법·pip 의존성·실제 이미지 layer·플랫폼 실행을 검증하지 않는다.
- 위키 검사는 CI 옵션으로 수행했다. 경고 119개는 누락된 무시 대상 로컬 원문 경고 등을 포함하며, 원문을 확보하거나 재검증한 것으로 세지 않는다. 초기 링크 오류와 수정 후 결과를 모두 보존했다.
- SSH·Docker image build·Compose·서비스 재시작·배포·자격 변경·보안 정책 완화는 수행하지 않았다. 사용자 전달 재시작 횟수의 안정화 및 실제 도입 처리는 미확인이다.
- 변경은 미커밋 작업 트리에 보존한다. 외부 공개 스킬/OSS 도입이 필요한 신규 기능이나 규모 있는 설계 변경이 아닌 기존 패키징 복구다.

## 다음 작업

OPS-INTAKE-PACKAGING-R3 산출물을 조정자에게 인계하여 검토 후 별도 승인된 솔루션 기기 재빌드·배포에서 import 오류/재시작 증가 해소와 PJ1 실제 도입 흐름 검증을 연결한다.

## 사용자에게 필요한 입력

없음. 이번 구현 범위는 완료했으며 배포 권한을 요청하지 않는다.
