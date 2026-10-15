# MCP 목표 기능 · WBS 현황판

제품 Console과 별도의 개발 검수 화면이다. 목표 G01–G10을 작업 40개로 나누고, 구현·회귀·배포·실제환경·검수의 근거별 점수를 보여 준다. 자동 갱신/실시간 제품 로그 연동이 아닌 검수 스냅샷이다.

- [WBS 정본](../llm-wiki/analysis/development-wbs/README.md) · [JSON](../llm-wiki/analysis/development-wbs/snapshot.json)
- [로그 수정·Linux 검증 보고](../llm-wiki/status/reports/2026-10-14-endpoint-telemetry-fix.md)
- [데스크톱 미리보기](preview-log-fix.png)
- 로컬 미리보기: <http://127.0.0.1:18767/>
- [게시된 웹 현황판](https://mcpgw-status-20261014.sleek-stoat-4347.chatgpt.site) — 소유자만 접근. [배포 확인](../llm-wiki/analysis/development-wbs/site-publication.json)
- Sites 프로젝트: `appgprj_6acf597681388191b21cd74641403939`; source `3e1529ac89e0218c114b487852ab164c14faf8cd`, native deployment `succeeded` 확인.

JSON/Markdown은 저장소 정본이며 사이트는 그 조회용 복사본이다. secret·사용자 key/token·개인 연락처·내부 주소·제품 인증 자료는 사이트에 넣지 않는다. 근거 경로·hash·판본·검증 한계와 안전한 표본 요약만 싣는다. 제품 API, MCP 호출, 외부 JS/폰트·분석 도구 의존성은 없다.

## 다시 생성

2026-10-15 재산정은 `python -X utf8 research/development-status-site/rescore_1015.py`로 만든다. 10-14 스냅샷을 `snapshot-before-wbs-1015.json`으로 보존하고, [근거 파일](../llm-wiki/analysis/wbs-1015/README.md)(병합 소스 회귀·배포 기록·기기 조회)을 단정하며 새 근거가 있는 작업만 바꾼다. 아래는 10-14 로그 수정 때의 방법이다.

저장소 루트에서 `python -X utf8 research/development-status-site/build_snapshot.py --after-log-fix`를 실행한다. 수정 전 스냅샷을 보존하고 새 source/실행 SHA, 실제 PJ1 자동 수집·복구와 전용 DB 검증을 대조하여 [정본 JSON](../llm-wiki/analysis/development-wbs/snapshot.json), [산정표](../llm-wiki/analysis/development-wbs/README.md), `dist/data.json`을 만든다. 수정 전 감사 hash는 역사로 보존하고, 이번 검수 source/실행 SHA와 독립 결과를 검사한다. 이전 목표의 점수는 재검수 없이 올리지 않는다. 기본 옵션 없는 옛 빌드는 수정 전 소스 기준이므로 현재 source 변경에서 실패한다.

`dist/index.html`, `app.js`, `style.css`, `data.json`은 표준 정적 파일이다. 별도 backend나 설치 패키지가 필요 없다. 새 판본 게시에는 Sites의 동일 project_id 및 별도 출판 checkout을 사용한다. 인증 토큰은 저장소·스크립트·manifest·로그에 보존하지 않는다.
