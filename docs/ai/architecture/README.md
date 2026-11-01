# MINT 아키텍처 구조도

## 현재판 (2026-11-01)

2판은 전체 구성 → 영역 구분 → 확대·기능 집중 → 시나리오별 역할과 단계군 순서로 읽는다.
대표 PNG는 [전체 구성도](v2-1101/p01.png)·[영역 구분](v2-1101/p02.png), 전체 29쪽은 아래 SVG다. 시나리오 6개는 역할별 흐름과 단계군별 「전체에서 보기」로 나뉜다.

| 번호 | 제목 |
| --- | --- |
| [01](v2-1101/p01.svg) | 전체 구성도 |
| [02](v2-1101/p02.svg) | 영역 구분 |
| [03](v2-1101/p03.svg) | 직원 PC |
| [04](v2-1101/p04.svg) | 진입 · 호출 통제 |
| [05](v2-1101/p05.svg) | 엔드포인트 관리 · 경보 |
| [06](v2-1101/p06.svg) | 콘솔 · 도입 검증 |
| [07](v2-1101/p07.svg) | 원장 · 추적 |
| [08](v2-1101/p08.svg) | 외부 연동 |
| [09](v2-1101/p09.svg) | 로컬 MCP |
| [10](v2-1101/p10.svg) | 기본 기능 · 기본 커넥터 |
| [11](v2-1101/p11.svg) | 장치 토큰 |
| [12](v2-1101/p12.svg) | MCP 도입 · 역할별 흐름 |
| [13](v2-1101/p13.svg) | MCP 도입 · 전체에서 보기 — 요청 · 신청 |
| [14](v2-1101/p14.svg) | MCP 도입 · 전체에서 보기 — 검증 · 승인 |
| [15](v2-1101/p15.svg) | MCP 도입 · 전체에서 보기 — 등록 · 적용 |
| [16](v2-1101/p16.svg) | MCP 호출 · 동의 · 승인 · 역할별 흐름 |
| [17](v2-1101/p17.svg) | MCP 호출 · 동의 · 승인 · 전체에서 보기 — 호출 · 판정 |
| [18](v2-1101/p18.svg) | MCP 호출 · 동의 · 승인 · 전체에서 보기 — 중계 · 응답 · 기록 |
| [19](v2-1101/p19.svg) | 미등록 MCP 탐지 · 역할별 흐름 |
| [20](v2-1101/p20.svg) | 미등록 MCP 탐지 · 전체에서 보기 — 차단 · 관찰 · 경보 |
| [21](v2-1101/p21.svg) | 미등록 MCP 탐지 · 전체에서 보기 — 확인 · 요청 |
| [22](v2-1101/p22.svg) | 승인 로컬 MCP 호출 · 역할별 흐름 |
| [23](v2-1101/p23.svg) | 승인 로컬 MCP 호출 · 전체에서 보기 |
| [24](v2-1101/p24.svg) | 기본 기능 · 커넥터 차단 · 역할별 흐름 |
| [25](v2-1101/p25.svg) | 기본 기능 · 커넥터 차단 · 전체에서 보기 — 사용 · 기록 |
| [26](v2-1101/p26.svg) | 기본 기능 · 커넥터 차단 · 전체에서 보기 — 차단 · 적용 |
| [27](v2-1101/p27.svg) | 변조 감지 · 격리 · 복구 · 역할별 흐름 |
| [28](v2-1101/p28.svg) | 변조 감지 · 격리 · 복구 · 전체에서 보기 — 감지 · 격리 |
| [29](v2-1101/p29.svg) | 변조 감지 · 격리 · 복구 · 전체에서 보기 — 복구 · 재사용 |

### 생성기

원본은 [generator-1101/build_v2.py](generator-1101/build_v2.py), 아이콘 출처·라이선스는 [icons/sources.json](icons/sources.json)이다.
저장소에는 p01~p29 SVG와 p01·p02 PNG가 있다. 전체 PNG·PDF·PPTX는 생성기로 내보낸다.
Python 3, Chrome, Pillow·PyMuPDF·python-pptx가 필요하다. 현재 PNG 렌더러의 Chrome 실행 경로는 Windows용 `CHROME` 상수로 지정되어 있으므로 실행 환경을 먼저 확인한다.

```bash
cd docs/ai/architecture/generator-1101
python -X utf8 build_v2.py 1101
```

표시는 선택 인자이며 생략하면 현재 시각을 쓴다. 출력은 생성기 폴더 아래 `export/MINT_구조도_<표시>/p01.svg`·`p01.png` 등이며,
전체 생성 시 같은 `export/`에 `MINT_구조도_<표시>.pdf`·`.pptx`를 만든다. PDF·PPTX는 쪽별 래스터 이미지를 담고 벡터 원본은 SVG다.
`python -X utf8 build_v2.py 1101 1,2`는 전체 SVG와 지정 쪽 PNG만 만들며 PDF·PPTX를 만들지 않는다.

### 10-23판과 달라진 점

한 장의 구성·역할 도면에서 전체·영역·확대·기능 집중과 역할별 시나리오로 나눴다. 기본 간편 모드, 설치 시 MINT 로그인,
승인 소스의 엔드포인트 stdio 실행, 기본 기능·커넥터의 벤더 직접 경로와 관리형 설정 차단, 장치 토큰·훅 보고·경보·격리 복구를 반영한다.
도식은 설계·구현 설명이며 플랫폼별 집행이나 실기기 통과 증거는 [개발 현황](../../../research/llm-wiki/status/current.md)과 연결된 보고서에서 별도로 확인한다.

## 이전판 (2026-10-23)

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
