# OPS-CONSOLE-EFFICIENCY — 협업 콘솔 폴링·렌더링

- 시작 commit: `62bafc49ec3f360415d229e24ee10b519c7cbe94`, 브랜치 `10/22-runtime-recovery`.
- 시작 시 이전 OPS-INTAKE-PACKAGING-R3의 12개 staged 파일이 있었다. 작업 도중 외부에서 `6a33afe521f0b84e5a41734d9077e4d25cf853bc`로 커밋되었으며 본 작업은 Git 변경 명령을 실행하지 않았다. 해당 파일·기존 snapshot은 보존했다.
- 범위: `research/collaboration-console/static/app.js`, 동작 회귀 1개, 문서와 이 증거. 서버·게이트웨이·정책·자격증명 변경 없음. 원격 HEAD 확인은 GitHub 연결 실패로 미확인.

## 호출 경로와 결정

`static/index.html`은 `app.js`를 defer로 읽는다. 초기 `poll()`과 `setTimeout(poll, 2000)`은 `/api/events?after=<cursor>` → `/api/runs` → `/api/wbs`를 순서대로 조회하고 `render()`를 호출했다. `render()`는 숨긴 채널까지 모두 그렸으며 `renderFeed()`는 최대 1,000개 이벤트를 매번 삭제/재생성했다. 채널 버튼·필터·작업 버튼·WBS 상세의 호출자도 수정 전에 확인했다. 서버의 `EventLog.snapshot()`은 줄 번호 커서와 최신 1,000건을 반환하고 작업은 작성자별 최신 task 이벤트로 집계한다. `RunLog.snapshot()`은 실행별 최신 값 200건이다.

새 의존성 없이 기존 render 함수·필터·DOM 생성 함수를 재사용했다. 스냅샷 내용이 같으면 참조를 유지하고, 고정 키 Map은 마지막 렌더 입력만 저장한다. 피드는 WeakMap에 마지막 이벤트 참조와 따라가기 값을 저장한다. 선택한 채널만 렌더하며 사이드바 배지는 계속 갱신한다. 작업 지연/멤버 최근 활동은 시간 경계가 바뀌면 다시 그린다. 작업 목록 재생성 시 동일 작업/작성자 버튼에 초점을 복원한다. WBS 목표 선택은 옵션 갱신 뒤 복원한다. 결정은 [D-190](../../../../docs/ai/DECISIONS.md)에 남겼다.

`document.hidden`·`visibilitychange`와 타이머 취소를 사용한다. 이미 시작한 요청은 중단하지 않고 완료값을 적용하며 숨김 상태의 후속 조회와 채널 렌더링을 생략한다. 복귀 시 즉시 조회하되 진행 중인 폴링이 있으면 겹치지 않는다. 보이는 문서의 2초 주기와 이벤트 API·커서·병합·최근 1,000건 보존 범위는 유지한다. 서버 커서 감소 시 기존처럼 이벤트를 지우고 반환 커서를 채택한다. 감소 이전 커서에 가려 반환되지 않은 과거 이벤트를 다시 조회하는 기능은 추가하지 않았다.

## 요구사항·검증 연결

| 요구사항 | 구현 심볼 | 조건과 실제 검사 |
| --- | --- | --- |
| OCE-01 변경 없는/숨긴 채널은 DOM 재생성 안 함 | `renderChanged`, `render`, `renderFeed`, `updateSnapshot` | 실제 스크립트를 Node VM에서 실행. 초기 비선택 채널 replaceChildren 0회, idle 피드/멤버/작업/실행/WBS 노드 동일, 필터 밖 새 이벤트도 피드 동일 |
| OCE-02 숨김 중 폴링 예약 취소·복귀·경합 안전 | `poll`, `visibilitychange` | 숨김 타이머 0, 요청 추가 0; 복귀 커서 유지, 반복 visibility 이벤트로 요청 겹침 없음; 요청 중 숨김이면 후속 조회 없음 |
| OCE-03 전달·커서·한도·장애 복구 보존 | `poll` | 새 이벤트 반영, 중복 없음, 최근 1,000건, 감소 커서 clear/adopt, fetch 오류 시 커서 유지·연결 끊김과 다음 조회 복구 |
| OCE-04 필터·선택 작업·키보드 보존 | 기존 필터 리스너, `renderTaskList`, `renderWbs` | 작성자/검색/따라가기·검증 필터·WBS 검색/목표/상태 유지, 선택 task 유지, native 버튼·초점 복원·상세 열기/닫기·aria-live HTML 유지, 10분 지연 표식 갱신 |

실행 원본과 도구 버전은 [checks.json](checks.json), 범위별 파일/심볼 행·SHA-256과 불변 파일 대조는 [scope.json](scope.json)에 기록한다. 새 검사는 `research/collaboration-console/test_frontend.mjs` 한 개다. 브라우저 대신 최소 DOM/fetch/시계 대역이므로 실제 키보드 이벤트·Escape·레이아웃·스크린리더 검수는 미실행이다. 기존 Python 시험의 알려진 SheetSync 단정 실패를 그대로 남겼다. 위키 목록 650개, 기존 `--ci-ignored-local-sources` 모드는 [오류 0/경고 119개](wiki-ci.json)다. 일반 모드는 ignored 원문 provenance 29개 누락으로 실패한다. 초기 검사 중 미작성 checks.json 링크 2건도 실패했으며 파일 생성 후 CI 검사에서 해결을 확인했다.

`capture_status.py`의 기존 capture 함수를 재사용하되 출력 ROOT만 이 작업 폴더로 지정해 [범위별 snapshot](status/repository-snapshot.json)을 남겼다. 이전 작업의 전역 snapshot을 덮어쓰지 않았다. raw 바이트와 Git blob 비교 일부가 다른 것은 기존 CRLF 정규화이며, `git hash-object` 대조로 이전 작업 10개 불변과 공유 현황/백로그 추가만 있음을 확인했다.

## 한계

메모리·heap·DOM 수 장기 추이·CPU·GC·프로세스 commit을 측정하지 않았다. 보고된 Codex 렌더러 12.8GB와 이 페이지의 인과관계, 메모리 누수 존재/해결, 메모리 절감량을 주장하지 않는다. 숨긴 채널은 마지막 렌더 입력/DOM을 보관하므로 숨김 시 메모리를 해제한다는 변경도 아니다. 이벤트/실행 보존 개수와 고정 캐시 키는 유한하지만 이것이 누수 부재의 측정 증거는 아니다. 서비스 기동·재시작·배포·새 웹사이트는 실행하지 않았다. 현재 1000 서비스에 새 파일이 반영되었는지 미확인이다.

다음 작업: 조정자가 이 diff와 검사 증거를 검토한다.
