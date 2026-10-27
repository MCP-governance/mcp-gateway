# 개발 현황 — 2026-10-25

지금 상태만 담는다. 열린 일의 담당·완료 조건·근거는 [백로그](backlog.md) 한 곳, 진척률·상태·담당의 정본은 구글 [MINT 개발 통합 시트](https://docs.google.com/spreadsheets/d/1bfD-wfPn_ldwB-AV2o1RAr6DbAtLnQV6JJQd-exJpLI/edit) 「WBS」·「백로그」 탭이다. 같은 사실을 여기와 백로그 두 곳에 쓰지 않는다. 10-23 판 원본은 [이력](history/2026-10-23-current.md), 처음 오는 에이전트의 읽기 순서는 [START_HERE](../START_HERE.md).

## 10-25 기준

- **main**: `7687a9e`(10-25 14:59 KST). 10-23 저녁 이후 D-230~D-237이 병합됐다(아래 표). 이 문서는 병합까지만 확인했다. 기기 배포·PJ1 실측은 D-235에 [작업 보고](reports/2026-10-25-github-per-user.md)가 있을 뿐 나머지는 위키에 배포 기록이 없다.
- **병합 전**: 브랜치 `10/25-policy-sync-split`(`cbc5195`)에 D-238(관리형 정책을 통제 해시로만 판정, D-198·D-212 대체)이 있다. 제품 코드와 분석 해시가 이 브랜치에서 갱신됐고 main에는 없다. 병합 뒤에는 D-번호로 인용한다.
- **진행 중인 세션 4개**(소유자 지시 10-25: 키트 편의·Windows 우선, 릴리즈 패키징, 위키 구조, 실사용 버그 시험): 이름·브랜치·소유 범위는 [START_HERE](../START_HERE.md#3-지금-진행-중인-세션-10-25)에 둔다. 결과는 완료 뒤 `reports/2026-10-25-*`와 백로그에 들어온다.
- **리팩토링·최적화 제안서(10-25 저녁, 코드 변경 없음)**: main `cdef0bb` 기준 진단과 재설계안을 [analysis/refactor-proposal-1025](../analysis/refactor-proposal-1025/README.md)에 두었다(코드 감사·외부 레퍼런스 110건 포함, [보고](reports/2026-10-25-refactor-proposal.md), 백로그 WIKI-09). 핵심 사실: `tools/call` 한 건이 DB 체크아웃 약 35회·SQL 약 49문장·폐기 목록 동기 서명 검증 5회 이상(정적 집계), 시험 189개 중 CI 연결 45개, CI 한 번 15~18분(실측). 채택 범위는 소유자 결정 대기.
- **이 문서가 확인하지 않은 것**: 시트 값은 10-23 이후 다시 읽지 않았다(WBS 57개 작업의 단계 가중 진척 63.3%, 최종 검수 완료 0개는 10-23 값이며 [WBS 단계 근거 감사](../analysis/wbs-evidence-1023/README.md)의 재계산 62.28%와 기준선이 다르다). D-230~D-237의 PJ1·pj3 실기기 결과도 확인하지 않았다.

## 10-27 정책 90개 PaC

- 팀 시트 POL-001~090을 `policy/`의 Rego PaC로 옮겼다(D-261). 65개 정책에 판정, 25개는 솔루션·제외(사유는 `policy/TRACE.md`). 시험 505건(독립 반례 144 포함) 통과, CI에 추적 검사. 게이트웨이 판정 경로에는 아직 연결하지 않았다. [분석](../analysis/pac-policy90-1027/README.md)·[보고](reports/2026-10-27-pac-policy90.md)

## 10-27 사내 저장소·콘솔 HTTPS·메뉴 통합 (PR #67, 브랜치 `10/27-internal-repo-console-only`)

- D-262: 직원은 사내 저장소를 바로가기로 읽기만 하고 내려받기·클론·쓰기는 막는다. 평문 `:8000` 콘솔은 HTTPS로 리디렉트.
- D-263 → D-264: PC 소스 빌드는 되돌렸다. 승인 소스 MCP는 솔루션 런타임에서 실행하고 키트는 연결만 한다.
- D-265: 관리자 메뉴 13개 → 9개(Codex sol 구현, 메인 검토).
- 실측(기기 `:8000` 시험 배치, pj1 VM): MarkItDown 신청→검증(LOW)→승인(사내 저장소 게시)→솔루션 런타임 ACTIVE→원클릭 등록 READY→
  pj1 키트에 자동 반영(서버 2/2 연결 정상). 목적지 미승인 호출은 `PAC-01` 차단.
- 도구 범위 심사(목적지 `raw.githubusercontent.com`) → 런타임 재시작(2세대, egress 허용 목록은 시작 때 적용) → pj1 `tools/call`
  `Allow`·`P-AUTHZ-ALLOW-001`·`upstream_executed` true(README 변환 결과 수신). 미승인 `example.com`은 `PAC-01` 차단 유지.
- D-266: 심사의 외부 전송 등급 기본값을 서버 데이터 등급으로(원클릭 제안·콘솔), PAC-12 차단에 사유. 실측: 「공개」 심사 →
  `PAC-12 — 데이터 등급 「내부」의 외부 전송이 승인되지 않았습니다…`, 「내부」 심사 → `Allow`·실행. 같은 쓰기 인자 반복은 `P-RATE-003`(중복 실행 방지, 의도).
- 남은 것: 메뉴·심사 화면 육안 확인, 위키 생성물 재생성(병합 직전).

## 10-26 리팩토링 0단계

- 0-1·0-2·0-3·0-4·0-6·0-7을 main에 병합했다(#38~#41·#43·#44, D-251·D-252). 0-5(#42)·0-8(#45)·범위 밖 키트 다운로드(#46)는 병합 전이다.
- 통과 조건: 기준선 1건·`nested_tx` 린트 0건·CI 시험 연결(고아 0)은 충족. 목록 동시 100건은 부하 실행 3회 모두 오류 0이나 허용·거절 시나리오가 불합격이다. PR CI는 15.9~19.7분으로 10분 목표를 못 채웠다.
- 기기 배포·PJ1 확인은 하지 않았다. 남은 것: 위협 추적 독립 재검토(D-252), 부하 시험 안정화, 소유자 결정(HTTPS 전환, 관리형 Codex 샌드박스 A/B).
- 상세: [작업 보고](reports/2026-10-26-refactor-stage0.md), 백로그 DEV-91.

## 10-23 저녁 이후 main에 병합된 결정

본문은 `python research/llm-wiki/tools/split_decisions.py show D-번호`로 읽는다. 보고서가 있는 것은 [보고서 색인](reports/README.md)에서 찾는다.

| 결정 | 내용 | main 병합 |
| --- | --- | --- |
| D-230 | 삭제된 계정 복구, 재가입 안내, PC 연결·도구 목록 화면(노션 버그 3건) | `861a860` |
| D-231 | 키트 방화벽 규칙을 Ubuntu 22.04(nftables 1.0.2) 문법으로 | `e256e4c` |
| D-232 | Linux 키트 Ubuntu 20.04~26.04 호환, 16.04·18.04는 첫 줄에서 안내하고 중단 | `a8664a5` |
| D-233 | 하네스가 승인 MCP를 알아보도록 관리형 메모리에 서버·도구 렌더링, 공급자 오류는 차단처럼 보이지 않게 | `4c879b4` |
| D-234 | 승인한 MCP의 기본 사용 대상은 전체 직원, 승인 화면에서 신청자만·지정 직원으로 좁힘 | `7281556` |
| D-235 | GitHub는 직원별 계정 연결(암호화 저장), 공유 토큰은 지정한 사람 전용 — [보고](reports/2026-10-25-github-per-user.md) | `12839f3` |
| D-236 | 직원은 Gitea에 들어가지 않고 콘솔 「승인된 MCP」에서 승인된 소스를 받는다 | `93b2db1` |
| D-237 | 사용 대상 변경은 서버 상세에서, 「내 연결」·사용 대상을 수용 시험 항목으로 | `10d7668` |

## 되는 것·안 되는 것 (10-23 확인분 그대로, 10-25에 다시 확인하지 않음)

상세와 증거 ID는 [10-23 현황](history/2026-10-23-current.md)과 [백로그](backlog.md)의 해당 행에 있다. 여기에는 구분만 둔다.

- **main 병합·기기 배포·실제 호출 기록이 있음**: 직원 PC 키트 Linux(PJ1) 설치→활성화→Claude로 승인 MCP 호출, Windows(pj3) 설치→활성화→트레이 연결(DEV-84), 로컬 MCP 원클릭 승인(DEV-83), Windows 한 파일 설치(DEV-89), 회원가입 수정(DEV-82), LiteLLM 애드온 판정 API(AIG-01).
- **병합됐으나 실제 환경 확인 전**: LiteLLM 승인·철회 동기화(AIG-02, main `2b289e1`, LiteLLM 1.105·PostgreSQL·PJ1 검증 전), 하위 경로 신청(DEV-88, 시험 기록 없음), 10-21 기능 묶음(대부분 대역 시험까지).
- **안 되는 것·미확인**: macOS 키트 실설치(DEV-87, 맥북 필요), Windows·Codex 하네스 모델 호출(DEV-84, 모델 로그인 필요), 실제 PostgreSQL 경합 일부(DEV-73~80·OPS-01).
- **열림**: DEV-81 — 같은 UID/SID의 다른 프로세스가 헤더 소켓·파이프의 bearer를 얻을 수 있고, 직원 PC 키트는 이를 막지 못한다.

| 변경 | main | 상세 |
| --- | --- | --- |
| 회원가입 결함 4건 수정 | `1c59a00` | [DEV-82](backlog.md) |
| AI 게이트웨이 애드온(LiteLLM) | `db8cb13` | [보고](reports/2026-10-22-ai-gateway-addon.md), D-191 |
| 로컬 MCP 원클릭 승인 | `f591d1c`~`85ead96`, `6a6c2af` | [보고](reports/2026-10-22-local-mcp-oneclick.md), D-192 |
| 키트 정상 경로 실측 | `969d80d` | [보고](reports/2026-10-22-kit-e2e.md) |
| ID 정의·참조 추적 | `f42ea03` | [보고](reports/2026-10-22-id-trace.md), D-194 |
| PR #36 시트 기준 잔여 구현·CI 복구 | `0000c05` | [보고](reports/2026-10-22-ci-completion.md), D-195 |
| 활성화 직후 지연·차단 사유 인자 표시 | `e27d3ca`, `48bb19e` | [보고](reports/2026-10-22-w10-ux.md) |
| macOS 키트 | `7b7ad6d` | [보고](reports/2026-10-22-kit-macos.md), D-196 |
| 저장소 하위 경로 도입 신청 | `3a1b2a1` | [DEV-88](backlog.md) |
| LiteLLM 개입 지점 설계 | `4968d7b` | [설계](../analysis/litellm-intervention-1023/README.md) |
| 레퍼런스 3종 조사 | `8d3b1a8` | [보고](reports/2026-10-23-references-3.md), WIKI-05 |
| 클라우드 감사·AI 통제 벤치마크 | `0f57d0c` | [보고](reports/2026-10-23-cloud-control-benchmark.md), WIKI-06 |
| 정책 동기화: 통제 해시만으로 판정 | 통합 브랜치 `10/25-integrate`에 병합, main 병합 대기 | [보고](reports/2026-10-25-policy-sync-split.md), D-238, DEV-90 |

## 시트와 위키의 연결 (10-25 점검)

- 협업 웹은 시트의 WBS·백로그 게시 CSV를 5분 캐시로 읽는다(10-23 확인). 저장소의 `sheet/pulled/` 사본은 10-18 값이고, `sheet_pull.py`를 돌리는 정기 실행이 없다.
- 시트 「결정」·「개발이력」·「자료」 탭은 저장소 내보내기보다 늦다. 저장소 내보내기(`sheet/`)도 `build_sheet_export.py --check`가 `tabs/37-integration-cases.csv` 등의 불일치를 낸다(10-25 측정). 근거와 고치는 순서는 [10-25 위키 구조 보고](reports/2026-10-25-wiki-structure.md).
- 낡음 점검: `python research/llm-wiki/tools/check_freshness.py`(경고만 낸다).

## 다음 작업

소유자 우선순위(10-22~25): 정상 기능 > 엔드포인트 키트·로컬 MCP > OS 무관 원클릭 설치 > 실사용 시험 > 콘솔 정리 > 조사. 10-25에는 키트 간편 모드·Windows GUI/TUI, 릴리즈 패키징, 위키 구조, PJ1 실사용 버그 시험이 병렬로 돈다.

1. 세션 4개의 결과를 리더가 병합하고 D-238 브랜치(`10/25-policy-sync-split`)와의 순서를 정한다.
2. 병합 뒤 생성물 재생성: `python research/llm-wiki/tools/refresh_generated.py`.
3. 열린 일은 [백로그 「먼저 볼 것」](backlog.md#먼저-볼-것-2026-10-25)을 따른다: DEV-87, DEV-83·84(모델 로그인 필요), AIG-02·AIG-01 실제 연동, DEV-88 시험, DEV-81.
4. 시트 정비: 「결정」·「개발이력」·「자료」 탭 다시 가져오기(WIKI-07 제안).

## 과거 결과를 찾을 때

[이력 목차](history/README.md)(기간별 보존), [보고서 색인](reports/README.md)(작업 ID·결정 번호로 검색), [결정 색인](decisions-index.md).
