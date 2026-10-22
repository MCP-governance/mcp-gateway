# MINT 개발 통합 시트

정본은 구글 시트 [MINT 개발 통합 시트](https://docs.google.com/spreadsheets/d/1bfD-wfPn_ldwB-AV2o1RAr6DbAtLnQV6JJQd-exJpLI/edit)이고, 이 폴더는 처음 채우기와 저장소 쪽 스냅샷이다.

- 관리 탭(WBS·백로그·결정·배포·자료·기능·구성요소·정책·시험)은 시트에서 고친다. 행은 A열 ID로 찾고, 진척률·상태처럼 수식인 열은 쓰지 않는다.
- 참조·원본 탭은 저장소 원천에서 다시 만든다: 이 스크립트 → 푸시 → 시트 A1의 IMPORTDATA 주소를 새 커밋으로 → 값 고정. 시트에서 고치면 편집 경고가 뜬다.
- 시트 → 저장소: `research/llm-wiki/tools/sheet_pull.py`가 웹 게시된 WBS·백로그 CSV를 이 폴더와 snapshot.json에 반영한다.
- 협업 콘솔 #wbs는 시트의 WBS 값을 5분마다 읽어 snapshot.json 위에 덮어 보여 준다.
- 구조도: [docs/ai/architecture](../../../docs/ai/architecture/README.md)의 노드 ID가 「구성요소」 탭(CMP-)과 같다.

| 탭 | 종류 | 행 수 | 원천 | ID |
| --- | --- | ---: | --- | --- |
| 01 요약 | — | 0 | — | ID |
| 02 WBS | 관리 | 57 | [snapshot.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/development-wbs/snapshot.json); [feature-spec.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/feature-spec-2026-10-17/feature-spec.json); [owners.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/development-status-site/owners.json) | ID |
| 03 백로그 | 관리 | 90 | [backlog.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/status/backlog.md) | ID |
| 04 결정 | 관리 | 178 | [DECISIONS.md](https://github.com/MCP-governance/mcp-gateway/blob/main/docs/ai/DECISIONS.md) | ID |
| 05 개발이력 | 참조 | 648 | git log main | 커밋 |
| 06 배포 | 관리 | 18 | [deploy.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/wbs-1015/deploy.json); [deploy-abd.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/wbs-1017/deploy-abd.json); [deploy-ce.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/wbs-1017/deploy-ce.json); 외 133개(manifest) | ID |
| 07 기능 | 관리 | 64 | [feature-spec.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/feature-spec-2026-10-17/feature-spec.json); [README.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/feature-spec-2026-10-17/README.md); [feature-wbs.csv](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/sheet/seed/feature-wbs.csv) | ID |
| 08 구성요소 | 관리 | 70 | [components.csv](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/sheet/seed/components.csv) | ID |
| 09 MVP 기능 | 원본 | 24 | [MCP_보안거버넌스_MVP_WBS_2026-10-03.xlsx](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/development-wbs/originals/MCP_%EB%B3%B4%EC%95%88%EA%B1%B0%EB%B2%84%EB%84%8C%EC%8A%A4_MVP_WBS_2026-10-03.xlsx); [README.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/drive-curation/README.md) | ID |
| 10 원 계획 | 원본 | 137 | [MCP_보안_거버넌스_Policy_as_Code_WBS_V1.5.xlsm](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/threats/originals/MCP_%EB%B3%B4%EC%95%88_%EA%B1%B0%EB%B2%84%EB%84%8C%EC%8A%A4_Policy_as_Code_WBS_V1.5.xlsm) | ID |
| 11 정책 | 관리 | 50 | [MCP_보안정책50_2026-10-14.xlsm](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/threats/originals/MCP_%EB%B3%B4%EC%95%88%EC%A0%95%EC%B1%8550_2026-10-14.xlsm); [feature-spec.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/feature-spec-2026-10-17/feature-spec.json); [pol-legal-basis.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/pol-legal-basis.json); 외 2개(manifest) | ID |
| 12 정책 상세 | 원본 | 24 | [MCP_보안정책50_2026-10-14.xlsm](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/threats/originals/MCP_%EB%B3%B4%EC%95%88%EC%A0%95%EC%B1%8550_2026-10-14.xlsm) | ID |
| 13 정책 독스용 | 원본 | 50 | [MCP_보안정책50_2026-10-14.xlsm](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/threats/originals/MCP_%EB%B3%B4%EC%95%88%EC%A0%95%EC%B1%8550_2026-10-14.xlsm) | ID |
| 14 추가 정책 | 원본 | 50 | [MCP_보안정책-추가25.xlsm](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/threats/originals/MCP_%EB%B3%B4%EC%95%88%EC%A0%95%EC%B1%85-%EC%B6%94%EA%B0%8025.xlsm) | ID |
| 15 정책 번호 대응 | 참조 | 50 | [policy-id-mapping.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/drive-curation/policy-id-mapping.json); [feature-spec.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/feature-spec-2026-10-17/feature-spec.json); [snapshot-before-wbs-1017.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/development-wbs/snapshot-before-wbs-1017.json) | ID |
| 16 시험 | 관리 | 13 | [experiments.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/experiments.json); [E01-approved-read.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/experiments/E01-approved-read.md); [E02-pii-result-masking.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/experiments/E02-pii-result-masking.md); 외 11개(manifest) | ID |
| 17 위협 | 참조 | 24 | [threats.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/threats.json) | ID |
| 18 로컬 도구 위험 | 참조 | 13 | [local-tool-risks.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/local-tool-risks.json) | ID |
| 19 권한 근거 | 참조 | 12 | [endpoint-permission-references.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/endpoint-permission-references.json) | ID |
| 20 규제 문서 | 참조 | 61 | [requirements.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/requirements.json) | ID |
| 21 규제 요구 | 참조 | 1223 | [requirements.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/requirements.json) | ID |
| 22 주제×관할 | 참조 | 19 | [compliance-requirements.xlsx](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/compliance-requirements.xlsx) | ID |
| 23 규제 계획 요약 | 참조 | 7 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json); [requirements.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/requirements.json) | ID |
| 24 규제 능력 | 참조 | 7 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 25 규제 개발 제안 | 참조 | 7 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 26 규제 보강 | 참조 | 5 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 27 규제 결정 대기 | 참조 | 8 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 28 규제 첫 스프린트 | 참조 | 6 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 29 사고 기한 | 참조 | 44 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 30 보존 기간 | 참조 | 16 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 31 관할 요약 | 참조 | 13 | [requirements.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/requirements.json) | ID |
| 32 규제 근거 조항 | 참조 | 124 | [dev-plan.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/compliance/dev-plan/dev-plan.json) | ID |
| 33 기업 요구 | 참조 | 80 | [requirements.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/requirements.json) | ID |
| 34 코드 구조 | 참조 | 801 | [code-structure.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/code-structure.json); git show b63943272081338ae454eeaff4821b931ea36df9:full_stack_lab/gateway/app/classify.py; git show b63943272081338ae454eeaff4821b931ea36df9:full_stack_lab/gateway/app/core.py; 외 2개(manifest) | ID |
| 35 제품 기능 대조 | 참조 | 21 | [competitor-mapping.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/competitor-mapping.json) | ID |
| 36 연동 대상 | 참조 | 7 | [integrations.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/integrations.json) | ID |
| 37 연동 시험 | 참조 | 50 | [integration-cases.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/integration-cases.json) | ID |
| 38 MCP 대상 | 참조 | 14 | [mcp-candidates.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/mcp-candidates.json) | ID |
| 39 스킬 후보 | 참조 | 9 | [skill-candidates.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/skill-candidates.json) | ID |
| 40 OSS 재사용 | 참조 | 8 | [oss-reuse.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/oss-reuse.json); [_brief.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/oss-deep/_brief.md); [contextforge-hooks.md](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/oss-deep/contextforge-hooks.md); 외 9개(manifest) | ID |
| 41 제품 분석 | 참조 | 9 | [solutions.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/solutions.json) | ID |
| 42 논문 | 참조 | 264 | [papers.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/papers.json) | ID |
| 43 레퍼런스 갱신 | 참조 | 5 | [reference-updates.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/reference-updates.json) | ID |
| 44 도입 기록 | 참조 | 22 | [imports.json](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/catalogs/imports.json) | ID |
| 45 자료 | 관리 | 698 | [AI_GATEWAY_ADDON.md](https://github.com/MCP-governance/mcp-gateway/blob/main/docs/ai/AI_GATEWAY_ADDON.md); [ARCHITECTURE.md](https://github.com/MCP-governance/mcp-gateway/blob/main/docs/ai/ARCHITECTURE.md); [BENCHMARK_AGT_2026-10-05.md](https://github.com/MCP-governance/mcp-gateway/blob/main/docs/ai/BENCHMARK_AGT_2026-10-05.md); 외 686개(manifest) | ID |
| 46 기업 현황 | 참조 | 10 | [MCP_기업호환성_검증대장.xlsx](https://github.com/MCP-governance/mcp-gateway/blob/main/research/llm-wiki/analysis/outputs/01a13365-enterprise/MCP_%EA%B8%B0%EC%97%85%ED%98%B8%ED%99%98%EC%84%B1_%EA%B2%80%EC%A6%9D%EB%8C%80%EC%9E%A5.xlsx) | ID |
| 47 추적 | 참조 | 1450 | [DECISIONS.md](https://github.com/MCP-governance/mcp-gateway/blob/main/docs/ai/DECISIONS.md); [components.psv](https://github.com/MCP-governance/mcp-gateway/blob/main/docs/ai/architecture/components.psv); [policy_ledger.json](https://github.com/MCP-governance/mcp-gateway/blob/main/full_stack_lab/opa/policy_ledger.json); 외 12개(manifest) | ID |

ID: 작업 G01.01, 기능 F-01(원본 순서), 정책 POL-01, 백로그 DEV-01/WIKI-01/AIG-01/RM-01/OPS-01, 결정은 제목의 D-번호(선행 0 포함), 시험 E01, OSS OSS-01, 자료 DOC-001, 배포 DEP-01, 커밋 7자 SHA. 참조표는 원본 ID를 보존한다. 여러 ID는 ` · `로 구분한다. 추적 탭은 모든 계열 ID의 정의 위치·참조 위치·관련 ID이며 규칙은 research/llm-wiki/trace/README.md다.

자료·배포 번호는 manifest의 id_registry에 보존하며 새 항목에만 번호를 추가한다. 이 파일과 스냅샷을 함께 보존한다. 원 계획은 원본 행 번호, MVP는 기능 순번, 코드 구조는 파일::함수, 규제 근거는 능력:요구 ID를 쓴다.

연구 백로그의 원본 RES-01은 관리 번호 WIKI-02로 옮기고 근거 자료·id_registry에 원본 번호를 보존한다. 규제 개발 제안의 A열은 RES-01을 유지하며 백로그 열로 WIKI-02에 연결한다.

연결 열:
- WBS: 기능 → features; 정책 → policies; 백로그 → backlog; 결정 → decisions; 시험 → experiments; 구성요소 → components
- 백로그: WBS → wbs; 결정 → decisions
- 결정: 백로그 → backlog; WBS → wbs; 커밋 → commits
- 개발이력: 결정 → decisions; 백로그 → backlog; WBS → wbs; 기기 배포 → deploys
- 배포: 커밋 → commits
- 기능: 정책 → policies; WBS → wbs
- 구성요소: WBS → wbs; OSS 재사용 → oss-reuse
- 정책: 기능 → features; WBS → wbs; 관련 추가 개발 → wbs; 요구 ID → reg-requirements; 번호 대응 → policy-id-map
- 정책 번호 대응: 정책 → policies; 독스용 번호 → policies-docs; 원본 번호 → policies-detail; 검수 작업 → wbs
- 시험: 정책 → policies; WBS → wbs; 백로그 → backlog
- 위협: 원본 ID → policies-detail; 위험 ID → local-tool-risks
- 로컬 도구 위험: 원본 통제 → policies-detail
- 규제 요구: 규제 문서 → reg-docs; 정책 → policies
- 규제 능력: 제안 → reg-proposals
- 규제 개발 제안: 백로그 → backlog; 능력 → reg-capabilities; 선행 → backlog; 결정 대기 → reg-decisions
- 규제 보강: ID → backlog
- 규제 첫 스프린트: 백로그 → backlog
- 사고 기한: ID → reg-requirements; 규제 문서 → reg-docs; 정책 → policies
- 보존 기간: ID → reg-requirements; 규제 문서 → reg-docs; 정책 → policies
- 관할 요약: 시행 전·초안 → reg-docs
- 규제 근거 조항: 능력 → reg-capabilities; 요구 ID → reg-requirements; 규제 문서 → reg-docs
- 코드 구조: 기준 커밋 → commits
- 제품 기능 대조: 요구 ID → ent-requirements
- MCP 대상: 시험 → experiments
- OSS 재사용: 시험 → experiments
- 레퍼런스 갱신: 시험 → experiments; 기존 자료 → papers
- 도입 기록: 원천 ID → papers

```powershell
python -B -X utf8 research/llm-wiki/tools/build_sheet_export.py
python -B -X utf8 research/llm-wiki/tools/build_sheet_export.py --check
python -B -X utf8 research/llm-wiki/tools/build_sheet_export.py --self-test
```

Python 3.12와 openpyxl이 필요하다. `--flat`은 셀 안 줄바꿈을 ` / `로 바꾼다. `--check`는 재생성 없이 원천과 저장된 파일을 대조하고 중복·형식·스냅샷 불일치 시 실패한다. 연결 누락은 원천의 명시 ID를 보존하고 integrity.json에 보고한다.

백로그 상태(위에서 먼저 맞는 규칙 적용): 보류·중단·폐기·범위 밖·사용자 결정·결정 대기 → 보류; 미착수·착수 전 → 미착수; 구현·수정·배포·실기기·통과·반영·설치가 있고 미구현·미완료·미실행·미배포·남음·필요·후속·대기·일부가 없으면 구현 완료(검수 전); 초안·설계·조사·검토·계획·정의·문서가 있고 구현·수정·배포·실기기·통과·설치가 없으면 설계·조사; 나머지는 진행 중. 이는 진행 원문 분류이며 단계 점수를 갱신하지 않는다.

기능↔WBS: 기능 레코드 또는 리뷰 표의 동일 기능에 작업 ID가 있으면 ‘명시’. 그 외 정책이 겹치면서 기능명이 작업명에 포함되거나, 공통 일반어를 제외한 기능명 토큰 2개(또는 4자 이상 토큰 1개)가 작업명에 있을 때만 ‘정책 일치’. 그 외는 빈 값이다. 연결 근거는 작업 ID마다 기록한다.

배포: 성공한 field up, 재설치·활성화 JSON 또는 날짜·대상·SHA·실행 표현이 함께 기록된 문장만 수록한다. 1~3차·중간·최종·(배포)처럼 SHA가 명시된 목록은 각 기록을 보존한다. 계획·미실행·실패는 제외한다. 설치 완료 뒤 활성화 대기는 설치 기록으로 보존한다. 현재 보고서에 기록된 배포와 현재 가동 상태는 별개다.

결정 참조의 선행 0은 원문 제목에 맞춘다(D-7 → D-07). 커밋 메시지의 D 번호는 토큰 전체로 대조해 D-12와 D-120을 구분한다. 진척률·상태 수식 열은 빈 값이며 manifest에서 formula=true다.

CSV는 UTF-8(BOM 없음), LF, RFC 4180 인용을 사용한다. 선행 =/+/@는 전각 문자로 바꾸며 셀은 45,000자까지 보존한다. 경로는 main 기준 GitHub URL이다. generated_at은 결정적 재생성을 위해 HEAD 커밋 시각이다. raw_base의 <커밋>은 푸시 후 채운다.

자료: 원문 사본 Markdown(sources·local-sources)은 제외하되 sources/README.md와 originals의 다른 파일은 포함한다. 생성물 sheet/README.md는 자기 참조를 피하기 위해 자료에서 제외한다. 파일명 날짜를 우선하고 없으면 Git 마지막 수정일을 쓴다. Git에 없는 파일의 날짜는 빈 값이다. 명시적 대체 문구를 우선하며 보고·이력·스냅샷은 기록, 나머지는 정본이다.

정책 번호 대응의 검수 작업은 feature-spec의 POL↔WBS 대응 중 기존 40개 스냅샷에 있던 작업만 연결한다. 원본 mapping JSON에는 검수40 직접 연결이 없다. 코드 구조의 동명 메서드는 JSON 기준 커밋의 클래스·중첩 함수명을 붙여 구별한다. 기업 현황은 원본 집계이며 현재 JSON 행 수로 덮어쓰지 않는다.

기업 검증대장 흡수: 요구사항 → ent-requirements; 코드구조 → code-structure; 기능대조 → competitor-map; 연동대상 → integrations; 연동시험 → integration-cases; MCP대상 → mcp-candidates; 실험계획 → experiments; 연구근거 → reference-updates; OSS스킬 → skill-candidates / oss-reuse.
추가 탭 enterprise-summary: 기업 검증대장의 ‘현황’는 별도 집계 표여서 보존.
