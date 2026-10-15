# PJ1 9개 도구 자연어 시험 선택 초안

2026-10-14 기준 `analysis/local-tools/tool-capabilities.json`의 92개 광고 스키마 중 9개를 선택했다. 정본 JSON은 [selection.json](selection.json)이며, 그 안의 `tools`에는 선택한 9개 `server:name`의 스키마 원문만 복사했다. 원본 인덱스 SHA-256은 `2577913a174882af7b8876988743d2820b2ccf610e1c44f1ad78d95a082c7f37`이다.

선택은 읽기 전용 discovery/history, Git 저장소 변경, SQL, 브라우저 탐색·페이지 코드처럼 서로 다른 권한 유형을 짧게 보도록 구성했다. Git add/commit은 합성 저장소 안에 독립 효과를 만들기 위한 것이며, SQLite `execute_sql`과 Playwright `browser_evaluate`는 본질상 더 넓은 권한이 있으므로 아래 프롬프트는 합성 fixture 안의 좁은 동작만 요청한다. 자연어 문구 자체는 권한 경계가 아니다.

## ID와 계약 확인

| 그룹 | 정확한 ID | 범위와 주의 |
| --- | --- | --- |
| Git | `git:git_status`, `git:git_log`, `git:git_add`, `git:git_commit` | Git 28개 도구 중 상태·이력 읽기와 파일 stage·commit 쓰기. 일반 status 경로는 검사되지만, GIT_BASE_DIR은 OS sandbox가 아니며 setter/clone의 외부 경로 동작을 안전 보증으로 보면 안 된다. `git_log` 스키마는 `maxCount` camelCase다. |
| DBHub | `sqlite:search_objects`, `sqlite:execute_sql` | 제품 구현은 DBHub(@bytebase/dbhub)지만 인벤토리의 실제 server ID는 `sqlite`. PJ1 tools/list가 이 이름과 같은지 확인하고, `dbhub:`로 임의 변경하지 않는다. `execute_sql`은 다중 문장도 허용하는 원시 SQL이며 write-capable. |
| Playwright | `playwright:browser_navigate`, `playwright:browser_snapshot`, `playwright:browser_evaluate` | 탐색은 URL/network와 페이지 상태 변경, snapshot은 페이지 읽기, evaluate는 임의 page JavaScript 실행. URL schema 자체에는 loopback 제한이 없다. `browser_evaluate`는 fixture 페이지에서만 호출한다. |

세 제품의 기존 시험은 일부 도구만 호출했다. 여기서 선택한 9개가 실제 PJ1에 등록·승인되었거나 아래 자연어 호출이 실행됐다는 뜻은 아니다. 특히 각 입력 스키마는 PJ1 실행 직전 실제 `tools/list`와 대조해야 한다.

## 9개 자연어 프롬프트 초안

아래는 새 managed harness turn에 한 건씩 보낼 초안이다. 대괄호/변수 URL은 실행 전에 PJ1이 준비한 task-local fixture 값으로 치환한다. fixture 준비 전이거나 managed state가 fresh active/compliant가 아니면 실행하지 않는다.

| # | 도구 ID | 예상 인자 (schema 기준) | 프롬프트 | 실제 효과 관찰·복구 |
| ---: | --- | --- | --- |
| 1 | `git:git_status` | `{"includeUntracked":true}` | “합성 시험 저장소의 현재 상태를 확인해줘. 변경 파일, staged/unstaged/untracked 항목과 clean 여부만 요약해줘. 실제 프로젝트나 다른 저장소는 열지 마.” | Gateway 호출기록과 합성 저장소의 독립 git status 대조. |
| 2 | `git:git_log` | `{"maxCount":3,"oneline":true}` | “같은 합성 시험 저장소에서 최근 커밋 3개를 한 줄 형식으로 보여줘. patch나 서명 상세는 요청하지 마.” | 저장소의 `git log -3 --oneline`과 응답 비교. 복구: 읽기 전용이라 불필요. |
| 3 | `git:git_add` | `{"paths":["notes.md"]}` | “합성 시험 저장소의 사전 준비된 notes.md 파일 하나만 stage해줘. 전체 파일, ignored 파일, 다른 경로는 추가하지 마.” | staged path가 정확히 `notes.md` 하나인지 independently 확인. `all`, `force`를 사용하지 않음. 중단 시 task-owned 합성 저장소만 기록 baseline으로 재생성. |
| 4 | `git:git_commit` | `{"message":"test: PJ1 synthetic MCP harness","amend":false,"allowEmpty":false,"noVerify":false}` | “방금 stage한 합성 notes.md만 커밋해줘. 메시지는 `test: PJ1 synthetic MCP harness`로 하고 amend, allow-empty, hook 우회는 사용하지 마. 실제 프로젝트에는 커밋하지 마.” | 합성 저장소에서 새 HEAD·commit message·포함 path를 `git log`와 `git status`로 독립 확인. 이는 fixture 안에 의도된 지속 변경이며 사용자 저장소에서 실행하지 않음. 독립 관찰 후 task 서버를 종료하고 검증된 폐기 저장소만 재생성해 초기 HEAD 복구를 확인. |
| 5 | `sqlite:search_objects` | `{"object_type":"table","detail_level":"names","limit":20}` | “격리된 합성 SQLite 데이터베이스에서 table 객체 이름만 찾아줘. 상세 내용은 names 수준, 최대 20개로 제한하고 업무 DB에는 연결하지 마.” | 예상 합성 DB의 table 이름만 응답되는지 DB 자체와 대조. 읽기 전용이라 복구 불필요. |
| 6 | `sqlite:execute_sql` | `{"sql":"SELECT id, label FROM demo_items ORDER BY id LIMIT 10"}` | “격리된 합성 SQLite DB에서 `SELECT id, label FROM demo_items ORDER BY id LIMIT 10`만 실행해줘. 변경·다중 SQL문·ATTACH·파일이나 확장 기능은 사용하지 마.” | 단일 SELECT만 전달됐는지 tool arguments 및 DB 독립 연결과 row count 전후로 확인. 단일 SELECT라 복구 불필요; 이 제한은 프롬프트이며 런타임 권한 경계가 아님. |
| 7 | `playwright:browser_navigate` | `{"url":"<exact pre-provisioned loopback fixture URL>"}` | “하네스가 제공한 정확한 task-local loopback 합성 fixture URL `[PJ1이 제공한 fixture URL]`로만 이동해줘. 다른 URL로 이동하거나 폼 제출, 링크 클릭은 하지 마.” | 실제 tool arguments에서 URL이 사전 검증한 정확한 loopback fixture와 일치하는지 검사하고 페이지 origin을 확인. 프롬프트만으로 URL 집행을 주장하지 않음. 관찰 후 isolated profile을 fixture 시작으로 되돌리거나 닫음. |
| 8 | `playwright:browser_snapshot` | `{}` | “현재 열린 합성 fixture 페이지의 접근성 snapshot을 응답으로 반환해줘. filename은 지정하지 말고 로컬에 파일을 저장하지 마.” | fixture의 합성 텍스트·접근성 tree 확인. `filename` 미지정이라 host에 결과 저장을 요청하지 않음; 파일 복구 불필요. |
| 9 | `playwright:browser_evaluate` | `{"function":"() => ({ title: document.title, text: document.body.innerText })"}` | “현재 합성 fixture 페이지에서 읽기 전용으로 document.title과 document.body.innerText만 반환해줘. DOM 수정, 이벤트 발생, 네트워크 요청, 파일 저장은 하지 마.” | generated `function` argument가 title/body text를 읽기만 하는지 확인하고 응답을 synthetic fixture와 대조하고 부작용 없는지 확인. 페이지를 fixture 외로 바꾼 뒤 evaluate를 실행하지 않음. |

## 실행 전제와 판정 경계

- P1–P4는 task-owned disposable Git repository의 새 하네스 working directory에서만 실행한다. GIT_BASE_DIR 값을 repo confinement으로 간주하지 말고 exact fixture path, baseline, `notes.md`를 확인한다. 특히 add/commit은 사용자 프로젝트 상태를 복구하는 시험이 아니므로 운영/업무 repository에서 금지한다.
- P5–P6는 DSN과 현재 DB name이 합성 fixture임을 확인하고 `demo_items` 사전 행을 독립 확인한다. 업무/운영 DB URL은 사용하지 않는다.
- P7–P9는 독립 관리 profile에서 제공된 정확한 loopback fixture만 사용한다. URL 도구 인자는 자연어 제한을 넘을 수 있으므로 실제 인자/최종 origin을 검사한다. evaluate는 임의 JavaScript 실행 권한이므로 fixture 밖에서는 호출하지 않는다.
- Parent/operator는 fresh managed endpoint, 정확한 PJ1 server/tool ID, Gateway 판정과 실제 도구 invocation을 한 쌍으로 확인해야 한다. protocol direct call, local unit test, schema presence만으로 자연어 하네스 통과를 기록하지 않는다.
- 이 artifact는 선택·프롬프트 설계만 한다. PJ1 runtime call 미실행이며, 92개 전체 검증이나 E12/E13 완료, 모든 endpoint bypass 차단을 주장하지 않는다.
