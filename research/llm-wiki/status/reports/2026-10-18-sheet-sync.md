# 2026-10-18 협업 콘솔 통합 시트 연동

- 작업자: Codex
- 코드 기준: `558e2a0a27b612a7a254a8bb8985ee6af33f73c1`, `10/18-sheet-sync`. 시작 시 clean, 작업 결과 미커밋.
- 시작 근거: 사용자 지정 WBS·백로그 CSV 연동 요구, [콘솔](../../../collaboration-console/README.md), [manifest](../../sheet/manifest.json).
- 완료 조건: 머리글·ID 기반 덮어쓰기, 점수·상태·요약 재계산, 캐시·실패 대체, 로컬 사본 동기화와 격리 시험.

## 결과

`console.py`의 `/api/wbs`가 저장소 스냅샷에 시트 값을 덮어쓰고 신규 ID·목표를 추가한다. 담당·메모·일정은 `owner`·`memo`·`planned_schedule`이다. 상태별 개수는 `summary.status_counts`, 출처·조회 시각·오류·편집 주소는 `sheet`에 제공한다. 백로그는 `/api/backlog` JSON 배열이며 신규 화면은 없다.

`sheet_pull.py`의 표준 라이브러리 CSV 파서·상태 계산을 콘솔과 공유한다. URL별 마지막 정상 값과 실패를 5분 캐시하며 소켓 타임아웃은 5초다. 실패 시 같은 URL의 직전 캐시, 없으면 저장소 사본을 사용한다. 설정은 요청마다 읽고 URL 변경 시 이전 URL의 캐시를 사용하지 않는다. CSV의 중복/빈 ID·열 누락·잘못된 점수는 실패다.

CLI는 URL 또는 `--from-dir`로 두 사본을 갱신한다. manifest 열 이름 집합을 확인하며 순서 변경을 허용한다. 쓰기 전에 모든 입력을 검증한다. `--apply-snapshot`은 기존 ID만 덮어쓰고 요약을 다시 계산한다. 신규 ID를 자동으로 저장소 정본에 추가하지 않는다. 실제 CSV 사본·snapshot은 이번 작업에서 갱신하지 않았다.

## 검증

| 확인 종류 | 명령·환경 | 결과 | 근거 |
| --- | --- | --- | --- |
| 콘솔 전체 시험 | Python 3.10, `python -B -X utf8 -m unittest discover -s research/collaboration-console -p test_console.py -q` | 32개 통과 | 기존 25개 + 시트 연동 7개, 임시 file URL·HTTP API |
| 지정 pytest | `python -X utf8 -m pytest research/collaboration-console/test_console.py -q` | 모듈 미설치, unittest로 대체 | `No module named pytest` |
| CLI 자체 시험 | `python -B -X utf8 research/llm-wiki/tools/sheet_pull.py --self-test` | 통과 | 임시 사본, 머리글 순서 변경·file URL·기존 ID만 반영·반복 적용·manifest 불일치 시 쓰기 중단 |
| JavaScript | `node --check research/collaboration-console/static/app.js` | 통과 | 구문 검사 |
| pyflakes | 변경 Python 3파일 | 모듈 미설치 | `No module named pyflakes` |
| Python 구문·diff | `ast.parse` 3파일, `git diff --check` | 통과 | 새 의존성 없음 |
| 위키 | `capture_status.py`, `build_wiki.py`, `check_wiki.py` | 캡처·목록 생성 통과, 전체 검사 실패 31건 | 기존 compliance provenance 누락 29건·변경하지 않은 endpoint 코드 매핑 불일치 2건. 로컬 `runtime/sheet-sync-wiki-check.txt` |
| 배포·실제 Google CSV·PJ1 | 미실행 | 검증 범위 밖 | 게시 URL 미제공, 제품 코드 변경 없음 |

## 실패·미완료·한계

원격 HEAD 재확인은 GitHub 접속 제한으로 실패했다. 캐시는 프로세스 메모리이며 재시작 시 사라진다. `fetched_at`은 마지막 정상 수신 시각이고 수신 전에는 null이다. UI는 요청대로 실패 시 저장소 기준 문구를 표시하지만, API의 `sheet.source=sheet`와 `error`는 직전 캐시 사용 여부를 구별한다. urllib의 5초는 소켓 제한이며 전체 다운로드 총기한은 아니다. 다중 파일 쓰기의 파일시스템 장애에 대한 원자적 롤백은 없다.

## 다음 작업

메인이 공개 CSV 두 URL과 편집 주소를 runtime 설정에 넣고 실제 시트 변경·5분 후 반영·공개 중단 시 대체를 확인한다. 커밋은 메인 검토 후 수행한다.

## 사용자에게 필요한 입력

게시한 WBS·백로그 CSV URL과 시트 편집 주소. 현재 미제공이며 연동 기본값은 꺼짐이다.
