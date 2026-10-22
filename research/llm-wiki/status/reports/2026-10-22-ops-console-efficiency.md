# 2026-10-22 OPS-CONSOLE-EFFICIENCY

- 작업자: Codex, implement. 조정자가 검토를 전달하며 다른 에이전트 호출 없음.
- 코드 기준: 시작 `62bafc49ec3f360415d229e24ee10b519c7cbe94`, `10/22-runtime-recovery`, 이전 작업 staged 변경 12개 존재. 작업 도중 이전 패키징 작업이 `6a33afe521f0b84e5a41734d9077e4d25cf853bc`로 외부 커밋됨. 본 작업은 브랜치 전환·커밋·push·merge 없음.
- 시작 근거: OPS-CONSOLE-EFFICIENCY. 완료 조건은 숨김/변경 없는 뷰 재생성·백그라운드 폴링을 줄이고 전달·커서·필터·선택 작업·접근성을 유지하는 최소 변경과 회귀다.
- 상세 근거: [호출 경로·원자 요구사항·한계](../../analysis/ops-console-efficiency/README.md), [검사 원본](../../analysis/ops-console-efficiency/checks.json), [범위·행·해시](../../analysis/ops-console-efficiency/scope.json).

## 결과

`app.js`에서 선택 채널/변경된 데이터만 그리며 피드의 필터 결과가 같으면 기존 DOM을 유지한다. 문서가 숨겨지면 예약 폴링을 취소하고 복귀 시 마지막 커서로 즉시 재개한다. 요청 겹침을 막고 진행 중 숨김이면 후속 조회를 생략한다. 기존 커서 감소·중복 배제·최근 1,000건 의미를 유지했다. 검색·작성자·따라가기·WBS 필터·선택 작업을 보존하고 작업 목록 갱신 시 초점을 복원했다. 새 프레임워크/의존성 없음.

## 검증

| 확인 종류 | 명령·환경 | 결과 | 증거 |
| --- | --- | --- | --- |
| 문법 | Node 24.21.0 `node --check research/collaboration-console/static/app.js` | 통과 | checks.json |
| 새 동작 회귀 | `node --test research/collaboration-console/test_frontend.mjs` | 1개 통과, DOM/타이머/fetch 대역 | checks.json |
| 기존 Node | `node --test full_stack_lab/tests/console-state.test.mjs` | 15개 통과 | checks.json |
| 기존 협업 콘솔 | Python 3.10.5 `py -3 -B -X utf8 -m unittest discover -s research/collaboration-console -p test_console.py -v` | 31통과/1실패: 알려진 SheetSync `assertNotIn("owner", snapshot["items"][0])` 유지 | checks.json |
| 문서·범위 | 위키 목록·`check_wiki.py --ci-ignored-local-sources`·diff·보존 대조 | 목록 650개, CI 검사 오류 0/ignored 원문 경고 119개, diff 통과; 이전 작업 10개 Git 정규화 동일·공유 현황/백로그는 추가만 있음 | checks.json, wiki-ci.json, scope.json |
| 실제 브라우저·메모리·현재 서비스 반영 | 실행 안 함 | 미검증 | — |

## 실패·미완료·한계

알려진 SheetSync 기준선 실패는 시험/스냅샷/시트 코드를 수정하거나 기대값을 완화하지 않았다. 일반 위키 검사는 ignored 로컬 원문 provenance 29개 누락으로 실패하며 기존 CI 모드 결과와 구분한다. 원격 HEAD는 네트워크 실패로 미확인. 실제 브라우저의 키보드·Escape·스크린리더·시간 장기 동작은 미실행이다. 메모리 누수·절감량과 Codex 렌더러 12.8GB의 인과관계는 미측정이며 해결을 주장하지 않는다. 로컬 구현/검사 결과이며 배포·서비스 재시작·신규 웹사이트 실행·자격/정책 변경 없음. 이전 작업의 파일과 증거는 보존했다.

## 다음 작업

조정자가 변경 diff와 검사 증거를 검토한다.

## 사용자에게 필요한 입력

없음.
