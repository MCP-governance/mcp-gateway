# MINT 아키텍처 구조도

## 현재판 (2026-10-23)

| 파일 | 내용 |
| --- | --- |
| [mint-architecture-ko.png](mint-architecture-ko.png) · [en](mint-architecture-en.png) | 구성도. 왼쪽에서 오른쪽으로 도구 호출이 지나는 순서, 양방향 화살표는 요청·응답, 이름 아래 회색 글자는 오픈소스의 목적 |
| [mint-architecture-roles-ko.png](mint-architecture-roles-ko.png) · [en](mint-architecture-roles-en.png) | 같은 도면에 영역별 역할(A~K)과 도구 호출 순서(1~6)를 붙인 판 |
| [mint-architecture-ko.drawio](mint-architecture-ko.drawio) · [en](mint-architecture-en.drawio) | 편집 원본(아이콘 내장) |
| mint-architecture-ko.svg · en.svg | 벡터 원본 |
| [generator-1023/](generator-1023/build_architecture.py) | 생성기. `python generator-1023/build_architecture.py [표시]` → `generator-1023/export/`. 렌더러(`base_renderer.py`)는 10-21판, 아이콘은 `icons/raw` |

10-21판과 달라진 점: 직원 PC의 사용자 계정을 위로, 배치를 요청 흐름 순서로, 직원 PC⇄솔루션·솔루션⇄MCP 서버·LLM의 상호작용을 양방향으로,
오픈소스마다 목적을 표시, 로컬 MCP 격리 실행(구현됨)·원클릭 키트(Windows·macOS 시험)·LiteLLM 동기화(기본 꺼짐)·실제 등록 MCP를 반영.

## 이전판 (2026-10-18)

| 파일 | 내용 |
| --- | --- |
| [mint-architecture.drawio](mint-architecture.drawio) | 편집 원본(draw.io 3페이지: 전체 아키텍처 · 망·배치 · 엔드포인트 키트). 아이콘은 개별 이미지라 옮기거나 바꿀 수 있고, 노드마다 구성요소 ID(`CMP-`)·상태·관련 작업이 데이터로 붙어 있다 |
| mint-architecture-1~3.png | 미리보기 |
| [build_architecture.py](build_architecture.py) | 배치 정의 → draw.io·SVG 생성 (`python -X utf8 build_architecture.py` → `MINT_아키텍처.drawio`, `preview/`) |
| [build_design.py](build_design.py) | 같은 배치를 Claude Design 캔버스 아트보드로 변환 |
| [components.psv](components.psv) | 구성요소 75개 원본(통합 시트 「구성요소」 탭의 시드) |
| [icons/](icons/sources.json) | 아이콘 원본과 출처·라이선스 |

노드의 `구성요소` ID는 통합 시트 「구성요소」 탭, `작업` ID는 「WBS」·「백로그」 탭과 같다. 1쪽은 순차 판정·관리면·격리 실행을, 2·3쪽은 배치와 키트 절차를 보여준다. 선은 노랑=MCP 호출, 파랑=제어·데이터, 자주=모델 호출, 청록 점선=Tailscale, 회색 점선=개발 예정·연동 대상, 빨강 점선=차단.
