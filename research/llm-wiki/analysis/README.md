# 기업 제공 요구사항과 호환성 분석

기업 제공 검토에 필요한 조건을 독립 레코드로 관리한다. 기능 이름이나 파일 존재를 완료로 세지 않는다. 이 자료는 프로젝트의 버전별 지식 정본이며 Excel은 정본에서 재생성하는 검토 화면이다.

| 자료 | 내용·단위 |
| --- | --- |
| [통합본 검토·Claude 인계](review-2026-10-15/README.md) | 코드 관찰10건·공식 근거19건·목표10개와 후속 검수. 구현/재현 상태 구분 |
| [Drive 정책·WBS 대조](drive-curation/README.md) | 정책50 이름/본문 동일성·원본 셀·코드/DEV 후보 매핑, MVP24와 G목표 연결 |
| [로컬 앱·MCP와 엔드포인트 권한](local-tools/README.md) | 실제 공개 MCP5개 설치·연결, 스키마92개 기능 분류, 권한 반례·10개 위험매핑·키트 회귀 |
| [요구사항](requirements.json) | 16개 영역·80개 원자 조건. 통과 기준·음성 입력·현재 증거·공백·우선순위 |
| [코드 구조](code-structure.json) | 47개 Python 모듈·794개 함수 AST 구조, imports·call expressions·16단계 경로·hash |
| [제품 대조](competitor-mapping.json) | 8개 제품·21개 구체 관찰. 고정 파일/판본·행·공식문서·부분 대응 조건 |
| [연동 대상](integrations.json) | LiteLLM과 비밀 저장소/전달6개 제품의 경로·인증·라이선스·공백 |
| [연동 시험](integration-cases.json) | LiteLLM34개·secret16개 독립 조건. 모두 미실행 |
| [MCP 대상](mcp-candidates.json) | 상용/공개 OSS14개 후보. package/version·출처·metadata hash·라이선스·실험 연결 |
| [논문 재검토](reference-updates.json) | 정식 저널3·학회1·게재처 미확인 preprint1. 기존2건 재검토 포함 |
| [공개 스킬](skill-candidates.json) · [OSS 활용](oss-reuse.json) | commit·라이선스·실측 stars·검토 범위·실제 적용/후보 상태 |
| [Excel](outputs/01a13365-enterprise/MCP_기업호환성_검증대장.xlsx) | 10개 시트. 필터·고정 행/식별 열·요구사항 상태 집계·근거 링크 |

`source_only`는 코드 후보를 연결한 상태이며 해당 조건의 충족을 뜻하지 않는다. `gap`은 전체 조건을 충족하는 구현/운영 증거가 없다. `verified_unit`은 명시한 단위 회귀만 통과했다. `verified_field`는 해당 입력의 실제 관리형 하네스·독립 효과·원복 증거가 있을 때만 사용한다. 새 조건 대장의 실기기 통과는 현재0이다. 과거 특정 하네스 표본은 별도 보고서를 유지한다.

코드 구조는 전체 AST 목록과 일부 수동 추적을 구분한다. AST의 call expression은 동적 dispatch 해결·모든 본문 정독·보안 감사 완료가 아니다. 모든 함수의 전체 표현 목록은 JSON에 보존하고 Excel은 함수·행·표현 수와 정본 경로를 제공한다. 실제 신원→정책→효과 경로와 구체 발견은 [호출 경로 분석](README-code.md)을 읽는다.

고정 분석의 LiteLLM1.102.0, Compose1.102.1, 새 평가 후보1.105.0은 서로 다른 판본이다. 공급자 현재 문서를 옛 배포판에 그대로 전이하지 않는다. registry metadata hash는 설치 아티팩트의 byte hash와 다르며 설치·기동 증거가 아니다. 라이선스가 혼재하거나 판본별 미확인인 후보는 도입 전 추가 확인한다.

## 갱신과 팀 검토

1. 요구사항 ID를 유지하며 코드/제품/논문 판본·읽은 범위·반례·실험을 추가한다. 조건 변경 시 변경 이유와 이전 근거를 보존한다.
2. 공식 상용/OSS MCP에 합성 데이터를 준비하고 정상·음성·경계·장애·경쟁·원복을 실행한다. 결과는 원본 hash와 비밀 제거 projection을 연결한다.
3. 상태는 가장 강한 **해당 조건의 증거**로 변경한다. SDK serialization이나 metadata 조회를 end-to-end 통과로 올리지 않는다.
4. `build_enterprise_analysis.py`는 최초 생성 이후 기존 조건·상태·시험 증거를 보존하고 구조·hash·행 연결만 갱신한다. 조건 변경은 사람이 ID·변경 이유·이전 근거를 검토해 반영한다. 링크 갱신은 새 코드의 의미·새 실행 결과를 자동 검증하지 않는다.
5. Excel 생성은 `build_enterprise_workbook.mjs`. Codex bundled `@oai/artifact-tool`을 사용하며 `CODEX_NODE_MODULES`로 제공된 runtime을 지정할 수 있다. 라이브러리가 없으면 자동 다운로드하지 않는다. JSON→Excel 방향이며 Excel에서 수정한 결과는 근거와 함께 JSON에 검토 반영한다. 기본 실행은 export·수식 검사를 수행하고 `--previews`로 미리보기를 추가한다. 현재 Windows bundled renderer는 render/export 후 native 종료 오류가 발생할 수 있어 저장 XLSX의 ZIP/XML·수식·화면 검증과 프로세스 종료 상태를 따로 기록한다.

원본 XLSM 두 개와 PAC01~24는 [위협표](../threats/README.md)에 보존돼 있다. 이 새 요구사항 ID는 별도 체계다. 번호가 비슷하다는 이유로 자동 대응시키지 않고 위협·통제·효과가 일치할 때 연결한다. 전체 조직의 법적/인증 요구 충족을 이 대장만으로 선언하지 않는다.

## 2026-10-15 근거 최신성 정리

기존 분석의 코드/시험 hash 불일치 53건을 확인한 뒤 구조 근거를 현재 판본으로 갱신했다. 바뀐 시험 파일을 참조한 5개 조건의 옛 실행은 [보존 레코드](review-2026-10-15/historical-test-anchors.json)와 historical_test_evidence로 옮기고 현재 검수는 재확인 대상으로 뒀다. 실행을 새로 수행했다고 기록하거나 과거 run의 hash를 바꾸지 않았다. REQ-10-04는 명세 판본별 결과 형식과 출력 계약을 구분하도록 조건 이력을 남겼다. 이 JSON 갱신 뒤 기존 Excel은 과거 검토 산출물이며 자동 최신이라고 보지 않는다.
