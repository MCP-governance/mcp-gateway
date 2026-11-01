# 2026-11-01 UI 검수 여섯 항목 반영

- 작업자: Codex
- 코드 기준: `11/01-ui-review`, `e393fc016ec5720284ab925a5dd842122b95012c`. 원격 HEAD도 `main`의 같은 커밋임을 확인했다. 기존 작업 줄기를 사용했고 커밋·푸시하지 않았다.
- 시작 근거: 소유자 지정 `task-fix-review.md`와 `ui-review.md`, D-330.
- 범위: F01·F03·F06·F07·F08·F09. PR #72의 메뉴·탭·KPI·표 구조를 유지했다. F02·F04·F05·F10은 변경하지 않았다.

## 결과

| 항목 | 원인과 변경 | 시험 근거 |
| --- | --- | --- |
| F01 | 공통 연결 SQL은 device_id만 확인하고 값이 없으면 다른 장치 후보도 포함했다. 웹만 복수 후보를 제거해 PC의 최근 후보 선택과 달랐다. 장치 키를 device_id→endpoint_id→workstation 순으로 제한하고 두 경로에 같은 후보 수 검사를 적용했다. 사용자·서버·도구·경로·-30초~+5초는 그대로다. 시간 일치는 보조 연결, 원장 자체 행은 정확 연결, 복수/무후보는 연결 없음이다. | `endpoint_gateway_link_check.py`: SQL 조건·경계·다른 PC·상충 키·무장치·다른 사용자/도구/서버·로컬 경로·복수 후보·두 실제 함수 투영을 검사한다. SQLite에서는 시간 계산 문법만 초 단위로 바꿨으며 실제 PostgreSQL 실행으로 세지 않는다. |
| F03 | 기존 좁은 화면 메뉴는 가로 스크롤이었다. 480px 이하만 2×2와 이름 줄바꿈을 적용하고 입력·버튼 폭을 제한했다. minmax 규칙은 유지했다. | 기존 휴대폰 폭 시험과 추가 CSS/메뉴 4개·건수 시험. 실제 Headless Edge의 390·406·480px 상태/요청 6화면에서 메뉴 2행, 가로 넘침 없음, 입력·버튼 위치 및 KPI를 확인했다. PNG도 열어 확인했다. |
| F06 | 공통 판정 행에서 사유가 사라졌다. 기존 도구 칸에 중복 호출 차단/이용 동의 필요 또는 정책 이름을 표시하며, 미조회 정책 코드는 노출하지 않는다. | Node 시험: 7열 유지, 두 사유 구별, 미확인 대체값 및 HTML 이스케이프. |
| F07 | 웹 경로는 허용/차단색이었고 TUI 커넥터는 브랜드색이었다. 웹·로컬·TUI를 파랑/청록/노랑으로 맞추고 전체 호출 KPI를 중립으로 변경했다. | Node 경로 3종·10열 유지, Python CHIPS/VALUE_ROLES·청록 RGB, 실제 Edge KPI 클래스와 PNG. |
| F08 | 접힌 제목에는 대상·건수만 있었고 일부 경보는 대상 식별자만 제공했다. 조회용 LEFT JOIN으로 호스트/사용자 이름을 보완하고 제목에 서버·도구·최근 초 단위 시각을 추가했다. 식별자는 상세에서 확인한다. 원본 근거와 출처가 다르면 묶지 않는다. | Node 제목·최근 시각·도구·이스케이프·다른 근거 비병합 및 기록 번호만 다른 동일 관측 묶음. Python 조회 JOIN·원본 근거 보존 시험. |
| F09 | 빈 이름도 다음 입력으로 진행했고 목록 잔상·취소 안내가 없었다. TTY에서 입력 전에 화면을 비우고 빈 이름이면 즉시 반환하며 기존 Ctrl+C 복귀를 유지했다. 도움말은 명령별 한 줄이다. | Python 빈 이름·전송 없음·화면 지우기·Ctrl+C 후 같은 페이지 복귀·8명령 도움말·한국어 인자 오류 유지. |

## 검증

지정된 모든 검사를 `full_stack_lab`에서 실행했다. Windows PowerShell에서는 Node glob을 실제 파일 목록으로 확장해 동일 대상을 전달했고 Python UTF-8 환경 변수를 적용했다.

| 검사 | 결과 |
| --- | --- |
| `node --check gateway/app/agent_static/console.js` | 통과 |
| `node --test tests/*.test.mjs tests/intake_one_click_ui_check.mjs tests/intake_d189_ui_check.mjs` | 155건 통과, 생략 0 |
| `PYTHONIOENCODING=utf-8 python tests/console_copy_check.py` | 문제 0 |
| `python tests/open_endpoints.py` | 통과 |
| `python tests/mint_cli_check.py` | 23건 통과 |
| `python tests/kit_screen_check.py` | 28건 통과 |
| `python tests/kit_login_source_check.py` | 55건 통과 |
| `PYTHONUTF8=1 python tests/linux_kit_reinstall_check.py` | 42건 통과 |
| `python tests/kit_simple_mode_check.py` | 14건 통과 |
| `python tests/endpoint_tool_path_check.py` | 통과 |
| `python tests/endpoint_gateway_link_check.py` | 6건 통과 |
| 변경 Python 7파일의 `python -m pyflakes` | 통과 |
| 임시 로컬 UI/Headless Edge 배치 | 390·406·480px × 상태/요청 6화면 통과 |

제품 의존성 추가 없이 표준 라이브러리·기존 HTML/CSS/ANSI 체계를 사용했다. 사전 공개 자료 비교로 [Anthropic frontend-design](https://github.com/anthropics/skills/tree/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design)(해당 스킬 Apache-2.0, 저장소 push 2026-10-28)과 [Rich](https://github.com/Textualize/rich/tree/9d8f9a372cc5916fd4781fec207ced7ddac2f08f)(MIT, 저장소 push 2026-06-23)를 확인했다. 범위는 디자인 지침 및 색 지원 설명/메타데이터까지며 외부 스크립트·코드·새 패키지는 도입하지 않았다. Rich의 최근 push만으로 현재 유지보수를 보장하지 않는다.

## 실패·미완료·한계

- 실제 원장 #243·#245~247의 값, 당시 후보 수 및 활성 장치 키는 조회하지 않았다. 코드에서 확인한 불일치 경로와 합성 반례 시험 결과를 실제 사건의 원인 확정으로 확대하지 않는다.
- 솔루션 배포·Compose 기동·실제 PostgreSQL·지정 시험 PC·실제 MCP/모델 호출은 미실행이다. 브라우저는 합성 데이터를 제공하는 기존 로컬 UI만 확인했다.
- 장치 정보 없는 과거 기록, 같은 시간 범위 복수 후보는 의도적으로 미연결이다. 화면 통과와 실제 집행 효과는 별도다.
- `refresh_generated.py`의 코드 포인터·위협 매핑·현황 스냅샷·보고서/결정 색인 재생성과 `check_wiki.py --ci-ignored-local-sources`·`check_trace.py`·`check_enterprise_analysis.py`는 통과했다. 추적 검사 경고 5개와 신선도 점검의 낡음 4건은 남아 있다. 생성물은 작업 트리에만 있으며 커밋하지 않았다.

## 다음 작업

백로그의 「UI 검수 여섯 항목 반영 후 실기기 대조」를 따른다. 승인된 솔루션 배포 뒤 실제 원장/PC/웹 및 Windows/Linux 터미널 취소를 대조한다.

## 사용자에게 필요한 입력

이번 구현과 로컬 검사에 추가 입력은 없다.
