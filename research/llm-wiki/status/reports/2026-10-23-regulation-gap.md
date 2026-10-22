# ACK RES-REGS — 2026-10-23 국내외 규제 갭 분석

- Agent Hub job: `7223c686a477` · 작업자: Codex.
- 기준 commit: `3a1b2a198ff381a36146a3f84219eb8a304f8a2b`, 현재 작업 브랜치 `10/23-research-codex`.
- 시작 시 다른 작업자의 미추적 `2026-10-21-pglast-license.md`를 보존했다.
- 원격 HEAD 재확인: `git ls-remote --symref origin HEAD`는 GitHub 443 연결 실패. 새 작업 브랜치 `git switch -c 10/23-regulation-gap`는 `.git/refs` 쓰기 거부. 현재 브랜치에서 연구 파일만 작성했으며 커밋·push는 하지 않았다.
- 범위: 기존 규제 note·요구 JSON·규제 CSV 및 코드 정적 대조, 공식 웹 선택 확인. 정책·제품 코드·실사용 권한 변경 없음.

## 결과

[분석 README](../../analysis/regulation-gap-1023/README.md)에 국내외 요구·위협 74개를 조항/항목 → 코드 파일:행 → 충족/부분/미충족/미확인 → 개발 제안으로 연결했다. [구조화 근거](../../analysis/regulation-gap-1023/gap.json)에 출처 17개, 코드 앵커 31개의 SHA-256·기준 줄·기존 요구 키와 실행 상태를 보존한다. [생성기](../../analysis/regulation-gap-1023/build.py)로 재생성할 수 있다.

기존 규제 계획의 DEV-66~71 중 사고 증빙·보존 설정·공급자 보증·국외 처리·중대 영향 호출·위험 평가 입력은 현재 코드에 있다. 남은 갭은 최종 모델/업무 설명·공정성·생성물 표시·정보주체 권리 행사·조직 운영·실제 외부 효과다. MCP 코드의 존재를 법 준수·배포·효과 증거로 바꾸지 않았다. 단독 운영 모드도 독립 승인 면제로 간주하지 않는다.

기존 `analysis/compliance`·`catalogs`·`solutions`·`papers`·`references-1023`와 규제 CSV를 우선 재사용했다. 요청의 regulation·benchmark·cloud-control-benchmark-1023 경로는 이 checkout 시작 시 없었다. 외부 공급자 마케팅 수치와 다른 에이전트의 결론은 구현/효과 증거로 채택하지 않았다.

## 검증

| 확인 종류 | 실제 명령·환경 | 결과 | 근거 |
| --- | --- | --- | --- |
| 재생성 | `py -3 -B -X utf8 research/llm-wiki/analysis/regulation-gap-1023/build.py` / Windows 로컬 | 74행·17출처·31코드 앵커 생성 | gap.json |
| 산출물 정합성 | `py -3 -B -X utf8 research/llm-wiki/analysis/regulation-gap-1023/verify.py` | **통과**, 오류 0. 74행·17출처·31코드 앵커의 현재/기준 commit hash·157로컬 링크·기존 요구 연결 16건 대조 | [검사 원본](../../analysis/regulation-gap-1023/validation.json) |
| Markdown 목록 | `py -3 -B -X utf8 research/llm-wiki/tools/build_wiki.py` | **통과**, Markdown 679개 집계 | [전체 검사 원본](../../analysis/regulation-gap-1023/checks.json) |
| 전체 위키 | `py -3 -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | **실패**, 기존 agent_service.py 위협 매핑 hash 불일치 2건, ignored 원문 부재 경고 119건. 신규 보고서/검사 링크 누락은 작성 후 해소 | checks.json |
| 저장소 스냅샷 | `py -3 -B -X utf8 research/llm-wiki/tools/capture_status.py` | **통과**, 로컬 코드 전용·배포/실험 false, 기준 commit 일치 | checks.json |
| 변경 형식 | `git diff --check` | **통과**, 출력 없음 | 로컬 명령 결과 |
| 공식 웹 | 2026-10-23 KST, 공식 기관 페이지·PDF 선택 열람 | source별 확인/미확인 및 URL·날짜를 README/gap.json에 기록 | README 출처 표 |
| 프로토콜·실제 하네스·upstream 효과·배포 | 실행하지 않음 | **미실행** | 사용자 금지 범위 준수 |

검사 실패를 연구 전체 통과로 보고하지 않는다. 신규 문서 자체의 검사 결과와 저장소 전체의 기존 실패를 구분한다. 초기 `python`·`rg`는 PATH에 없어 실패했고 `py -3`·표준 라이브러리/PowerShell로 대체했다. 초기 임시 조회의 문법 오류는 조회 코드를 수정해 재확인했으며 제품 실패로 세지 않았다.

## 실패·미완료·한계

- 국정원 원문 조항, 시행령 안/현행 핵심 위임 조항, 금융 최종 통합본, ISO 전문·PIPC/KISA 세부 조항은 **미확인**. 기존 local-only 사본이 이 PC에 없어 상세 note를 전제로 잠정 대응했고 공식 웹 게시 사실만으로 조항 검증을 주장하지 않았다.
- 한국법은 사용자 제공 ZIP의 보존 인쇄본 제31~35조와 공식 판본 표제를 대조했다. 현재 개정 완전성은 미확인이다. EU 개정 2026/1744와 위키의 변경 적용일은 공식 원문 봇 차단으로 **미확인**이며 확정 기한에 사용하지 않았다.
- 관할 팩의 기본 비활성 가능성, 관찰 모드, 원장 요청 미리보기 잔존, 실제 삭제 보류, 관리되지 않는 OS/계정·셸/SDK 우회가 제한이다. 코드 정적 충족을 운영 충족으로 환산하지 않는다.
- 기존 위키의 위협 매핑 hash 불일치는 이번 연구 범위에서 재생성하지 않았다. 다른 작업자의 근거를 현재 코드 hash로 덮어쓰지 않았다.
- 새 브랜치와 원격 HEAD 확인은 환경 제한으로 미완료. 리더 커밋 전 미추적 연구 파일과 현황·백로그·스냅샷 차이를 검토해야 한다.

## 다음 작업

리더가 P0 미확인 공식 원문·판본을 확보해 각 조항과 적용 상태를 대조하고 이 매트릭스의 잠정 판정을 확정한다.

## 사용자에게 필요한 입력

없음. 새 실사용 권한·실데이터·기기 접속은 요청하지 않았다.
