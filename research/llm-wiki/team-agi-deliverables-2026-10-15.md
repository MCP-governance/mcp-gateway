# Team AGI 산출물 선별: 정책, 기술 구현, 실증 및 평가

2026-10-15에 [산출물 드라이브 폴더](https://drive.google.com/drive/folders/1EB2OLq8lJ-cdUQEW6SePUSln6gef_8kq)의 세 폴더를 확인했다. 이 문서는 개발에 사용할 자료와 기존 위키와의 관계를 기록한다. 드라이브 문서는 요구와 계획의 근거이며 코드 반영, 배포, 실기기 시험의 증거는 별도로 확인한다.

후속 통합 검토(2026-10-15): `10/15-drive-wiki-curation`의 두 커밋을 통합하고 보존된 두 원본을 다시 읽었다. 기존 정책50과 새 판본은 정책명·본문의 공백 제거 대조에서 50/50 동일했다. [판본 비교·정책과 코드/시험 연결·MVP WBS 해설](analysis/drive-curation/README.md)에 결과를 누적했다. 아래의 변경 대조 미완료 표기는 최초 선별 시점의 한계이며 법령 근거 셀·원격 Drive 최신 목록은 이번에도 재검증하지 않았다.

## 선별해 반영한 자료

| 영역 | 드라이브 자료와 판본 | 위키 반영 | 개발에서 쓰는 범위 |
| --- | --- | --- | --- |
| 정책 | [MCP_보안정책50.xlsm](https://drive.google.com/file/d/1NGFWTI_TNnUiDPHupOIfEOyfcB9h5ecM/view), 수정 2026-10-14 | [원본](threats/originals/MCP_보안정책50_2026-10-14.xlsm), [POL-01~50 색인](threats/policies-50-2026-10-14.md) | 도입, 등록과 연결, 호출, 운영, 종료 요구를 코드와 시험 조건에 연결할 때 확인 |
| 정책 | [MCP 보안 관리 프레임워크 V3.0](https://docs.google.com/document/d/1W4-vRSRIvy-8gdBUA7a66GcaYP5Cw6TT1D_9Kaot96c/edit), 수정 2026-09-27 | 이 페이지에 핵심 절차와 정본 연결을 요약, 원문은 드라이브 링크로 유지 | 도입 검토와 위험 판정, 등록과 승인, 배포와 실행통제, 운영과 재평가, 종료와 폐기의 판단기준과 기록 확인 |
| 기술 구현 | [MCP_보안거버넌스_MVP_WBS.xlsx](https://docs.google.com/spreadsheets/d/1Vc51VmIDMruOIZXGeR8QMF-65hhw5opV/edit), 수정 2026-10-03 | [원본](analysis/development-wbs/originals/MCP_보안거버넌스_MVP_WBS_2026-10-03.xlsx), 아래의 범위 해설 | 관리형 Linux 계정과 Claude Code/Codex CLI, 승인 MCP 2~3개를 전제로 한 24개 기능 계획 |

정책표 원본의 세 시트는 POL-01~50 본문, PAC01~50 독스용 표현, PAC01~24 위협 중심 표다. 기존 위키의 [이전 정책 XLSM과 추출본](threats/README.md)은 다른 바이트의 판본이다. 새 원본의 SHA-256은 3319af0c9adb53d8d4f4ea252c2315c1911772b06d6d677e80714cb1b0b90549다. ID가 같아 보여도 변경 대조 전에는 기존 50개 표나 런타임 PAC-01~15와 자동 병합하지 않는다.

프레임워크 V3.0은 서버와 기능의 업무 목적, 소유자, 권한, 데이터와 외부 통신 범위를 도입 전에 확인하고, 승인된 기준 상태를 기록하게 한다. 연결과 호출 시 승인 범위와 실제 집행을 확인하며, 운영 중 중요 변경이나 통제 실패가 있으면 재평가한다. 종료 시 접근과 자격 회수, 데이터 및 증적 처리 결과를 남긴다. 이것은 정책상 요구사항이며 현재 제품에 모두 구현됐다는 뜻은 아니다. 구현 정본은 [아키텍처](../../docs/ai/ARCHITECTURE.md), [통제 경계](../../docs/ai/SECURITY_BOUNDARIES.md), [시험 규칙](../../docs/ai/TESTING.md)에서 확인한다.

MVP WBS는 사용자와 엔드포인트 5개, MCP 도입과 검증 5개, 승인과 카탈로그 4개, 호출과 데이터 통제 4개, 운영과 감사 3개, 종료와 권한 회수 3개로 구성된다. 원본의 적용 오픈소스 열은 도입 후보와 계획이지 설치나 연동 완료 기록이 아니다. 현행 [G01~G10의 40개 검수 작업](analysis/development-wbs/README.md)은 별도 기준이다. 이 24개 기능을 현재 40개 작업의 완료 수에 합산하지 않는다. WBS 원본 SHA-256은 81a86b3e777b2de520abde32ec50df616f64920b3eb95bccea0f5d210580ecae다.

## 이번에 옮기지 않은 자료

| 드라이브 자료 | 판단 |
| --- | --- |
| [MCP_보안정책-추가25.xlsx](https://docs.google.com/spreadsheets/d/1IrvVFRUNMCF3WGOyGyeo0hpzDWO7zmCi/edit), [MCP_보안_정책_근거00.xlsx](https://docs.google.com/spreadsheets/d/16d9h6_1FYYiYw6xRcABK839RII7obZOW/edit) | 24개 정책 계열과 근거 초안이다. 기존 위키에 24개 표, 근거, 위협 매핑이 있어 원본을 중복 게시하지 않았다. 변경 대조가 필요한 경우 드라이브 원본을 다시 확인한다. |
| [MCP_보안_통합관리대장_V1.0.xlsx](https://docs.google.com/spreadsheets/d/1Z3pSM4mTidwrfVXSumkCWSnL1dZ7AH4U/edit) | 정책 운영용 대장이다. 개발 위키의 코드와 시험 근거 정본으로 사용하지 않는다. |
| [pac15-mvp 2 폴더](https://drive.google.com/drive/folders/1Ja-xlx6oiKJ5stKoSG57TH6Lf2-y-WC8) | 별도 PAC-15 예시 코드와 스키마, 시험의 사본이다. 현재 게이트웨이 코드 및 위키의 런타임 PAC 문서와 혼동될 수 있어 이관하지 않았다. |
| [AGI.drawio.png](https://drive.google.com/file/d/1imsKu4hyqNH9_IBmwRU9VV9kMi6FgGat/view) | 2026-09-14의 전체 구성 그림이다. Agent Gateway와 MCP Gateway를 분리한 이전 구상이라 현재 구현 아키텍처 그림으로 게시하지 않았다. 이 폴더에는 실제 시험 보고서나 평가 데이터가 없다. |

과거 버전과 scrap 폴더도 이번 범위에서는 이관하지 않았다. 위 표의 제외는 삭제나 자료 무효 판정이 아니다.

## 확인 범위

드라이브의 파일명, 형식, 수정일을 확인하고 정책표의 세 시트와 MVP WBS 두 시트를 읽었다. 프레임워크 V3.0 본문과 실증 폴더의 그림을 확인했다. 정책표의 매크로는 실행하지 않았고 WBS 수식은 재계산하지 않았다. 원본의 법령과 표준 최신성, Drive 링크의 다른 팀원 접근권한, 제품 코드와 50개 정책의 일대일 구현 상태는 이번 선별에서 검증하지 않았다.
