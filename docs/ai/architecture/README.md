# MINT 아키텍처 구조도

| 파일 | 내용 |
| --- | --- |
| [mint-architecture.drawio](mint-architecture.drawio) | 편집 원본(draw.io 3페이지: 전체 아키텍처 · 망·배치 · 엔드포인트 키트). 아이콘은 개별 이미지라 옮기거나 바꿀 수 있고, 노드마다 구성요소 ID(`CMP-`)·상태·관련 작업이 데이터로 붙어 있다 |
| mint-architecture-1~3.png | 미리보기 |
| [build_architecture.py](build_architecture.py) | 배치 정의 → draw.io·SVG 생성 (`python -X utf8 build_architecture.py` → `MINT_아키텍처.drawio`, `preview/`) |
| [build_design.py](build_design.py) | 같은 배치를 Claude Design 캔버스 아트보드로 변환 |
| [components.psv](components.psv) | 구성요소 75개 원본(통합 시트 「구성요소」 탭의 시드) |
| [icons/](icons/sources.json) | 아이콘 원본과 출처·라이선스 |

노드의 `구성요소` ID는 통합 시트 「구성요소」 탭, `작업` ID는 「WBS」·「백로그」 탭과 같다. 1쪽은 순차 판정·관리면·격리 실행을, 2·3쪽은 배치와 키트 절차를 보여준다. 선은 노랑=MCP 호출, 파랑=제어·데이터, 자주=모델 호출, 청록 점선=Tailscale, 회색 점선=개발 예정·연동 대상, 빨강 점선=차단.
