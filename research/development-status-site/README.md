# MCP 목표 기능 · WBS 현황판

제품 Console과 별도의 개발 검수 데이터다. 목표 G01–G10을 작업으로 나누고, 구현·회귀·배포·실제환경·검수의 근거별 점수를 보여 준다. 자동 갱신/실시간 제품 로그 연동이 아닌 검수 스냅샷이다.

**2026-10-17부터 이 정본 JSON의 화면은 독립 `dist/` 정적 사이트가 아니라 [개발 협업 콘솔](../collaboration-console/README.md)의 `#wbs` 채널에서 본다.** 콘솔 서버가 매 요청마다 `snapshot.json`을 다시 읽으므로 별도 빌드·복사 단계가 없다. `dist/data.json`은 Google Sheets 등 다른 소비자를 위해 계속 생성되지만 더 이상 브라우저로 직접 서빙하지 않는다.

- [WBS 정본](../llm-wiki/analysis/development-wbs/README.md) · [JSON](../llm-wiki/analysis/development-wbs/snapshot.json)
- [로그 수정·Linux 검증 보고](../llm-wiki/status/reports/2026-10-14-endpoint-telemetry-fix.md)
- [데스크톱 미리보기](preview-log-fix.png) — 10-14 당시 독립 사이트의 과거 기록
- [게시된 웹 현황판](https://mcpgw-status-20261014.sleek-stoat-4347.chatgpt.site) — 10-14 당시 독립 사이트 게시 이력. 소유자만 접근. [배포 확인](../llm-wiki/analysis/development-wbs/site-publication.json)
- Sites 프로젝트: `appgprj_6acf597681388191b21cd74641403939`; source `3e1529ac89e0218c114b487852ab164c14faf8cd`, native deployment `succeeded` 확인.

- 공유 Google 시트(다른 장치에서 이어서 보기): [MINT 개발 WBS](https://docs.google.com/spreadsheets/d/1bfD-wfPn_ldwB-AV2o1RAr6DbAtLnQV6JJQd-exJpLI/edit). `python -X utf8 research/development-status-site/sheet_rows.py --owners research/development-status-site/owners.json`이 `WBS!A1`부터 쓸 2차원 배열을 만들고, 작업이 끝날 때마다 바뀐 행만 Sheets 커넥터로 갱신한다. 점수 정본은 snapshot.json이고 시트의 진척률·상태·요약은 수식이다. 진행 중 담당·메모는 `owners.json`.

JSON/Markdown은 저장소 정본이며 사이트는 그 조회용 복사본이다. secret·사용자 key/token·개인 연락처·내부 주소·제품 인증 자료는 사이트에 넣지 않는다. 근거 경로·hash·판본·검증 한계와 안전한 표본 요약만 싣는다. 제품 API, MCP 호출, 외부 JS/폰트·분석 도구 의존성은 없다.

## 다시 생성

2026-10-17 확장(57개, 추가 개발 포함)은 `python -X utf8 research/development-status-site/extend_1017.py`로 만든다. 10-15 40개 판을 `snapshot-before-wbs-1017.json`으로 보존하고 [기능명세 기록](../llm-wiki/analysis/feature-spec-2026-10-17/feature-spec.json)의 작업을 더한다. 결과를 보려면 `research/llm-wiki/analysis/development-wbs/snapshot.json`을 읽는 [협업 콘솔](../collaboration-console/README.md)을 `python research/collaboration-console/console.py serve`로 띄우고 `#wbs` 채널을 연다.

2026-10-15 재산정은 `python -X utf8 research/development-status-site/rescore_1015.py`로 만든다. 10-14 스냅샷을 `snapshot-before-wbs-1015.json`으로 보존하고, [근거 파일](../llm-wiki/analysis/wbs-1015/README.md)(병합 소스 회귀·배포 기록·기기 조회)을 단정하며 새 근거가 있는 작업만 바꾼다. 아래는 10-14 로그 수정 때의 방법이다.

저장소 루트에서 `python -X utf8 research/development-status-site/build_snapshot.py --after-log-fix`를 실행한다. 수정 전 스냅샷을 보존하고 새 source/실행 SHA, 실제 PJ1 자동 수집·복구와 전용 DB 검증을 대조하여 [정본 JSON](../llm-wiki/analysis/development-wbs/snapshot.json), [산정표](../llm-wiki/analysis/development-wbs/README.md), `dist/data.json`을 만든다. 수정 전 감사 hash는 역사로 보존하고, 이번 검수 source/실행 SHA와 독립 결과를 검사한다. 이전 목표의 점수는 재검수 없이 올리지 않는다. 기본 옵션 없는 옛 빌드는 수정 전 소스 기준이므로 현재 source 변경에서 실패한다.

`dist/data.json`은 표준 정적 JSON이며 `sheet_rows.py` 등 다른 소비자가 계속 읽는다. 과거(10-14~10-17) `dist/index.html`·`app.js`·`style.css`는 독립 정적 사이트였고 Sites에 게시한 이력은 위 링크로 보존한다. 지금은 같은 역할을 협업 콘솔의 `#wbs` 채널이 맡는다. 인증 토큰은 저장소·스크립트·manifest·로그에 보존하지 않는다.
