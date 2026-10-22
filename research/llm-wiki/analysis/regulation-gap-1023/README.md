# ACK RES-REGS — 국내외 기관 규정·가이드와 MINT 기능 갭 분석

확인일 2026-10-23 · 기준 commit `3a1b2a198ff381a36146a3f84219eb8a304f8a2b` · Agent Hub job `7223c686a477`.

MINT는 MCP 호출 전 권한·계약 검사, 개인정보 검사, 개별 승인, 감사와 종료 증거를 제공한다. 부족한 부분은 모델·업무 시스템 전체의 설명·공정성·권리 행사·생성물 표시와 조직 운영 증빙이다. 기존 규제 개발 계획의 ‘없음’을 그대로 옮기지 않고 현재 코드를 다시 확인했다.

## 평가 범위와 판정

- **충족**: 표에 좁게 정의한 통제가 해당 코드에 있음(정적 구현 범위). **부분**: 관련 기능은 있으나 범위·운영·증거가 부족. **미충족**: 확인한 기능으로 그 요구를 제공하지 못함(모델/조직 책임을 포함하며 법 위반 판정이 아님). **미확인**: 공식 조항을 확인하지 못해 판정보류.
- 출처 확인과 제품 판정은 별도다. PIPC·KISA·ISO의 개별 쪽/조항은 이 PC에 원문이 없어 **미확인**이다. 그 행의 ‘부분’은 기존 note의 요약을 전제로 한 **잠정 기능 대응**이며 규제 충족 수치로 합산할 수 없다. 한국법·EU의 보존 원문과 온라인 최신성도 구분한다.
- 코드 존재·설정·활성화·실제 효과·배포는 다르다. 이번 제품 시험·PJ1·기기 접속·스택 기동은 **미실행**. 정상 기능 보존과 운영 편의를 개발 우선순위로 둔다.
- EU 고위험 제공자/배치자, GPAI 제공자/체계적 위험 GPAI 제공자의 의무를 구분한다. MINT를 도입했다는 사실만으로 고객이 이 행위자가 되거나 의무가 면제되지 않는다. GPAI 모델 제공자의 의무는 공급자 보증 자료로 연결할 범위이며 MINT가 모델 개발을 대신한다는 뜻이 아니다.
- NIST·OWASP·CSA는 권고/위협 분류, ISO는 조직 경영시스템 표준, 한국 금융 가이드는 모범규준이다. 법령 의무·초안·기술 모범사례와 같은 법적 효력으로 합산하지 않는다.

## 기존 자료 재사용과 대조

우선 확인: [컴플라이언스 정본](../compliance/README.md), `notes/*.json`, `requirements.json`, [개발 계획](../compliance/dev-plan/README.md), `catalogs/*.json`, [솔루션 목록](../../solutions/README.md), `papers/LIB-L04~06·L09·M01·M07·M17·I01·I04·I14.md`, `papers/T21.md`, [references-1023](../references-1023/README.md). 시트 `20-reg-docs`·`21-reg-requirements`·`24-reg-capabilities`·`25-reg-proposals`·`29-reg-incident-deadlines`·`30-reg-retention`·`32-reg-clauses` CSV를 대조했다. 일치하는 기존 요구 ID와 안정 키는 [gap.json](gap.json)에 보존했다. 식별자 번호만으로 정책을 대응하지 않았다.

요청된 `analysis/regulation`, `analysis/benchmark`, `analysis/cloud-control-benchmark-1023` 경로는 시작 시 이 checkout에 없었다. 다른 에이전트 산출물이나 원격 미수신 자료가 있을 수 있으므로 ‘조사하지 않았다/기능이 없다’로 바꾸지 않았다. references-1023의 공급자 주장은 코드 증거로 사용하지 않았다.

규모 있는 재조사를 피하려고 `sheet/tabs/39-skill-candidates.csv`와 `solutions/README.md`의 고정 OSS·라이선스 근거를 재사용했다. Microsoft skills 공개 GitHub 검색으로 저장소와 wiki-researcher 경로 존재를 확인했으나 설치·외부 스크립트 실행은 하지 않았다. 기존 기록의 commit `91ec09549ca16bd6c44e6ccdef26d61eb2082f07`, MIT는 과거 증거이고 현재 유지보수/최신 commit은 미확인이다. 실제 적용은 저장소 자체의 근거 추적 방식이며 외부 SKILL을 새로 실행한 것이 아니다.

## 출처·확보일·확인 한계

기존 확보일은 카탈로그 기록이며 이번 재취득을 뜻하지 않는다. 모든 아래 웹 확인/시도일은 2026-10-23(KST)이다. 새 웹 원문 파일을 저장하지 않았으므로 새 원문 바이트 해시는 없다. 기존 파일의 존재와 실제 SHA-256, 코드 SHA-256은 gap.json에 기록했다. 장문 인용·유료 전문 재배포는 하지 않았다.

| 출처 | 공식 URL·위키 | 기존 확보일 | 이번 확인 범위·한계 |
| --- | --- | --- | --- |
| PIPC 개인정보위 생성형 AI 개인정보 처리 안내서(2025.8) | [공식 자료](https://pipc.go.kr/np/cop/bbs/selectBoardArticle.do?bbsId=BS074&mCode=C020010000&nttId=11410) · LIB-L05 | 2026-10-17 | **발표·첨부명 확인; 개별 쪽 본문은 미확인**. 위키 note 재사용. 이 PC에 local-only 원문 없음. 보도자료를 조항 검증으로 세지 않음. |
| KR-ACT 인공지능기본법 2026.7.21 판본 | [공식 자료](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=282791&efYd=20260721) · LIB-L04 | 2026-10-17 | **공식 판본 표제 확인; 온라인 조항 본문 미확인**. 사용자 제공 ZIP의 법제처 인쇄본·보존 추출본 제31~35조 대조. 공식 직접 취득본으로 세지 않음. 최신 개정 완전성은 미확인. |
| KR-DECREE 인공지능기본법 시행령·시행령(안) | [공식 자료](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=198073) | 이번 웹 확인만 | **2026.8.20 시행 판본·제22조 확인; 요청한 안 및 핵심 위임 조항 미확인**. 2025년 안과 현재 시행령을 혼동하지 않음. 공포본 안내는 https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=282879&viewCls=lsRvsDocInfoR 에서 표제만 확인. |
| FSC 금융분야 AI 가이드라인 2021.7.8 | [공식 자료](https://www.fsc.go.kr/no010101/76206) | 이번 웹 확인만 | **공식 보도자료 주요내용 확인; 첨부 PDF 열기 실패**. 법률 자체가 아닌 모범규준. 원문 세부 조항 번호는 미확인; 보도자료의 항목명만 사용. |
| FSC-DRAFT 금융분야 AI 가이드라인 개정방향 2025.12.22 | [공식 자료](https://www.fsc.go.kr/no010101/85908) | 이번 웹 확인만 | **개정방향·가이드라인(안) 게시 확인; 최종본·효력 미확인**. 2021판을 최신 확정판이라 부르지 않음. 개정안과 현행 적용 문서는 구분. |
| NIS 국가정보원 생성형 AI 활용 보안 가이드 | [공식 자료](https://www.nis.go.kr/) | 이번 웹 확인만 | **미확인**. 공식 홈페이지 본문 공백 및 공식 도메인 검색으로 요청 원문 특정 실패. 외부 재게시 PDF는 채택하지 않음. NIS는 국가정보원의 영문 약칭으로 중복 기관 계산 안 함. |
| KISA AI 보안 레드티밍 가이드 2026.7 | [공식 자료](https://www.krcert.or.kr/kr/bbs/view.do?bbsId=B0000127&menuNo=205021&nttId=72125&pageIndex=1) · LIB-L06 | 2026-10-17 | **공식 게시·목차 확인; 개별 쪽 본문 미확인**. 기존 https://www.kisa.or.kr/401/form?postSeq=3713 은 502. 보호나라 등록일은 7.8, 위키 KISA 본사이트 기록은 7.7이므로 같은 게시일로 합치지 않음. local-only 원문 없음. |
| EU EU AI Act 2024/1689 고위험 의무 | [공식 자료](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-26) · LIB-M01 | 2026-10-17 | **EC 조문 9·14·26 확인; 나머지는 보존 원문 대조, 최신성 미확인**. EUR-Lex는 JS 봇 차단. EC article-9·article-14도 확인. 공식 서비스의 설명 요약과 조문 본문을 구별. |
| EU-GPAI EU AI Act GPAI 의무 | [공식 자료](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-53) · LIB-M01 | 2026-10-17 | **EC 제53·55조 본문 확인**. 추가 URL https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-55 . 오픈소스 예외·체계적 위험 해당성을 별도 확인해야 함. |
| EU-DATE 위키의 EU 개정·적용일 기록 | [공식 자료](https://data.europa.eu/eli/reg/2026/1744/oj) · LIB-M16 | 2026-10-17 | **미확인(JS 봇 차단)**. 위키가 적은 개정 사실과 2027.12.2/2028.8.2 일정은 이번에 공식 본문 재확인 못 함. 본 분석에서 확정 적용일·제품 기한으로 사용하지 않음. |
| NIST NIST AI RMF 1.0 (2023.1) | [공식 자료](https://www.nist.gov/itl/ai-risk-management-framework) · LIB-M07 | 2026-10-17 | **공식 소개 확인·보존 공식 PDF 추출본 대조**. 자발적 프레임워크. 이번 읽기는 GOVERN 1.6·1.7·3.2, MEASURE 2.7, MANAGE 4.1 및 관련 단락. |
| NIST-GAI NIST AI 600-1 (2024.7) | [공식 자료](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf) · LIB-M17 | 2026-10-17 | **공식 PDF 선택 절 확인**. 64쪽 PDF. GV-1.7, GV-6.1, MS-2.7, MG-2.4 대조. 나머지 전 항목 충족 평가 아님. |
| ISO ISO/IEC 42001:2023 | [공식 자료](https://www.iso.org/standard/42001) · LIB-L09 | 2026-10-17 | **표준 명칭·경영시스템 범위 확인; 조항 본문 미확인**. 기존 note는 local-only OCR 기반. 이 PC에 원문 없음. 유료 표준 전문을 재배포하거나 공개 소개만으로 조항 검증·인증 충족을 선언하지 않음. |
| LLM OWASP LLM Top 10 2025 | [공식 자료](https://genai.owasp.org/llm-top-10/) · LIB-I04 | 2026-10-14 | **공식 10항목 명칭·개요 확인**. 목록을 법적 의무로 바꾸지 않음. 세부 완화책 전부를 읽은 것은 아님; 아래 통제는 MINT에 대한 분석 제안. |
| ASI OWASP Agentic Top 10 2026 | [공식 자료](https://genai.owasp.org/download/52117/?tmstv=1765059207) · LIB-I01 | 2026-10-14 | **공식 PDF 57쪽 중 표지·목차·요약·선택 정의 확인**. December 2025, Version 2026. ASI01~10 명칭을 PDF에서 확인해 기존 LIB-I01의 명칭 미확인을 이번 분석 범위에서 보완. 항목별 모든 완화책 검증 아님. CC BY-SA 4.0 표기; 전문 복제 없음. |
| CSA CSA MAESTRO 2025.2.6 | [공식 자료](https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro) · LIB-I14 | 2026-10-14 | **공식 글 §3.2 A~D 확인**. www 호스트 접근 실패 후 비-www 공식 URL 성공. 산업 위협 모델링 블로그이며 법령·인증 표준·독립 효과 연구가 아님. |
| MCP MCP 보안 모범사례 2026-07-28 경로 | [공식 자료](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) · T21 | 2026-10-13 | **공식 본문 선택 절 확인**. Token Passthrough, SSRF, State Handle Hijacking, Confused Deputy, Scope Minimization. URL에 포함된 판본과 최신 명세 동일성을 추정하지 않음. |

## 요구 조항 → MINT 기능 → 판정 → 개발 제안

출처별 자세한 검증 상태는 위 표가 우선한다. 아래 줄 번호는 기준 commit의 현재 파일과 대조한 위치이며 코드 hash·정확한 줄 문자열은 gap.json에 고정했다. 검증 프로필은 뒤 표에 정의하고 모두 이번 실행은 미실행이다.

### 국내

| ID·출처·요구 조항 | 요구 요약 | MINT 기능(코드 파일:행) | 판정·관계 | 가져올 것·개발 제안 |
| --- | --- | --- | --- | --- |
| KR01 · PIPC<br>쪽 8~9 목적 설정 | 처리 목적과 최소 수집 범위를 명시 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P1: 도구별 업무 목적·적법근거·담당자 증빙을 승인 자료와 결속 · V1 |
| KR02 · PIPC<br>쪽 16 PbD·쪽 30 입출력 필터 | 개인정보 입력·출력 최소화 | [gateway/app/core.py:2330](../../../../full_stack_lab/gateway/app/core.py#L2330) execute_call/input inspection<br>[gateway/app/core.py:1953](../../../../full_stack_lab/gateway/app/core.py#L1953) _inspected_result<br>[gateway/app/privacy.py:117](../../../../full_stack_lab/gateway/app/privacy.py#L117) analyze | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P2: 한국어 정상 유사값과 민감정보의 오탐·미탐을 함께 측정 · V2 |
| KR03 · PIPC<br>쪽 19 서비스형 LLM | 공급자 데이터 보관·재이용 조건 검토 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/upstream.py:40](../../../../full_stack_lab/gateway/app/upstream.py#L40) credential_headers | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P1: LLM 공급자 학습 재이용·보존·하위처리자 계약 근거까지 확장 · V3 |
| KR04 · PIPC<br>쪽 17~18 영향평가 | 개인정보 흐름과 새로운 침해요인 평가 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/residency.py:60](../../../../full_stack_lab/gateway/app/residency.py#L60) facts | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P1: MCP·모델·메모리·최종 수신자까지 흐름 증빙 연결 · V3 |
| KR05 · PIPC<br>쪽 35 권리 행사·쪽 37 대화 이력 | 정보주체 삭제·처리정지 및 보관 정책 지원 | [gateway/app/retention.py:31](../../../../full_stack_lab/gateway/app/retention.py#L31) floor<br>[gateway/app/core.py:1970](../../../../full_stack_lab/gateway/app/core.py#L1970) _audit_payload | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P4: 원장·대화·학습 데이터별 보존/삭제 책임과 증거 구분 · V4 |
| KR06 · PIPC<br>쪽 36 자동화된 결정 | 설명·인적 개입·재검토 권리 지원 | [gateway/app/high_impact.py:25](../../../../full_stack_lab/gateway/app/high_impact.py#L25) explanation<br>[gateway/app/core.py:1636](../../../../full_stack_lab/gateway/app/core.py#L1636) _call_upstream/high-impact binding | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P5: 업무 결정 ID와 설명·이의신청·재처리 증빙 연결 · V5 |
| KR07 · KR-ACT<br>제31조제1항 | AI 기반 서비스임을 사전 고지 | [gateway/app/high_impact.py:25](../../../../full_stack_lab/gateway/app/high_impact.py#L25) explanation | **미충족**<br>갭 | P5: 고객 서비스의 고지 증빙 참조를 대장에 연결; 호출 승인과 구분 · V5 |
| KR08 · KR-ACT<br>제31조제2항 | 생성형 AI 결과물 표시 | [gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result | **미충족**<br>갭 | P5: 생성물 표시는 결과물을 제공하는 앱에서 구현하고 증빙 연결 · V5 |
| KR09 · KR-ACT<br>제33조제1항 | 고영향 AI 해당성 사전 검토 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **부분**<br>이미 있음 + 갭 | P1: 법정 해당성 검토자·판본·근거를 제품 위험 점수와 별도 저장 · V3 |
| KR10 · KR-ACT<br>제34조제1항제1호 | 고영향 AI 위험관리 방안 운영 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail<br>[gateway/app/decommission.py:717](../../../../full_stack_lab/gateway/app/decommission.py#L717) assess | **부분**<br>이미 있음 + 갭 | P1: 시스템 전체 위험 등록부와 정기 재평가 연결 · V6 |
| KR11 · KR-ACT<br>제34조제1항제2호 | 최종결과 주요 기준·학습 데이터 개요 설명 | [gateway/app/high_impact.py:25](../../../../full_stack_lab/gateway/app/high_impact.py#L25) explanation | **부분**<br>이미 있음 + 갭 | P5: 호출 정책 사유와 모델/업무 결과의 설명을 구분해 제공 · V5 |
| KR12 · KR-ACT<br>제34조제1항제4호 | 사람의 관리·감독 | [gateway/app/core.py:1636](../../../../full_stack_lab/gateway/app/core.py#L1636) _call_upstream/high-impact binding<br>[gateway/app/review.py:64](../../../../full_stack_lab/gateway/app/review.py#L64) require_independent<br>[gateway/app/review.py:85](../../../../full_stack_lab/gateway/app/review.py#L85) solo_mode_enabled | **부분**<br>이미 있음 + 갭 | P5: 감독자 역량·번복·실제 중단 효과 및 단독 모드 조건 확인 · V1 |
| KR13 · KR-ACT<br>제34조제1항제5호 | 안전성·신뢰성 조치 문서 보관 | [gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision<br>[gateway/app/supplier_assurance.py:94](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L94) export_rows<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail | **부분**<br>이미 있음 + 갭 | P1: 모델/서비스 판본·평가 문서·조치 책임자까지 증빙 묶음 확장 · V4 |
| KR14 · KR-ACT<br>제35조제1항 | 기본권 영향평가 노력 및 취약계층 고려 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **부분**<br>이미 있음 + 갭 | P1: 영향받는 집단·취약계층·구제수단을 영향평가 입력에 추가 · V3 |
| KR15 · KR-DECREE<br>시행령(안) 핵심 위임 조항 | 안·공포본·현행본 및 안전성 기준 구분 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **미확인**<br>갭 | P0: 공식 안/공포본/현행본 확보 후 위임 조항별 delta 확정 · V0 |
| KR16 · FSC<br>주요내용 ❶ 내부통제 | 책임·조직·위험관리 정책 수립 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/review.py:64](../../../../full_stack_lab/gateway/app/review.py#L64) require_independent | **부분**<br>이미 있음 + 갭 | P1: 금융기관의 책임 조직·경영진 보고·정기 심사 자료 연결 · V3 |
| KR17 · FSC<br>주요내용 ❷ 학습 데이터 | 학습 데이터 조사·검증 및 오남용 방지 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope | **부분**<br>이미 있음 + 갭 | P1: 모델 데이터 출처·사용권·품질 증빙을 공급자 자료로 수집 · V3 |
| KR18 · FSC<br>주요내용 ❸ 공정성 | 불합리한 소비자 차별 점검 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **미충족**<br>갭 | P5: 금융 업무별 집단 성능·편향 평가를 외부 모델 평가와 연결 · V5 |
| KR19 · FSC<br>주요내용 ❹ 설명·권리 | 소비자 설명과 권리 행사 보장 | [gateway/app/high_impact.py:25](../../../../full_stack_lab/gateway/app/high_impact.py#L25) explanation | **부분**<br>이미 있음 + 갭 | P5: 소비자 설명·이의신청·재심 처리 기록 연결 · V5 |
| KR20 · FSC-DRAFT<br>2025.12.22 개정방향 | 최종 통합본과 적용 범위 확인 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate | **미확인**<br>갭 | P0: 공식 최종 가이드라인 게시 여부와 2021판 대체 관계 확인 · V0 |
| KR21 · NIS<br>원문 조항 미확인 | 국정원 생성형 AI 보안 요구를 확정해야 함 | [gateway/app/core.py:2330](../../../../full_stack_lab/gateway/app/core.py#L2330) execute_call/input inspection<br>[gateway/app/destination.py:20](../../../../full_stack_lab/gateway/app/destination.py#L20) PinnedBackend.connect_tcp | **미확인**<br>갭 | P0: 공식 원문 확보 후 조항을 확정; 일반 보안 기능을 NIS 충족으로 세지 않음 · V0 |
| KR22 · KISA<br>쪽 22~24 교전 규칙·범위 | 레드티밍 허용 범위·중단 조건 합의 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/decommission.py:717](../../../../full_stack_lab/gateway/app/decommission.py#L717) assess | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P6: 실제 OSS MCP 시험 계획에 승인 범위·금지 행위·복구 조건 연결 · V6 |
| KR23 · KISA<br>쪽 25~29 평가·시나리오 | 정상/공격 성능과 재현 조건을 함께 기록 | [gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P2: 판정·정책 ID·독립 효과·지연·반복 결과를 원자 요구와 연결 · V2 |
| KR24 · KISA<br>쪽 36 영향 분석 | 실행 전 권한·실행 경계·추적 가능성 검증 | [gateway/app/core.py:2188](../../../../full_stack_lab/gateway/app/core.py#L2188) execute_call<br>[gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P6: 실제 MCP 부작용·측면이동·복구를 원장 밖 수신자에서도 검증 · V6 |
| KR25 · PIPC<br>쪽 20 국외이전 | 국외 처리 근거와 수신자·위치를 심사 | [gateway/app/residency.py:60](../../../../full_stack_lab/gateway/app/residency.py#L60) facts<br>[gateway/app/residency.py:94](../../../../full_stack_lab/gateway/app/residency.py#L94) enabled | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P1: 위치 신고와 실제 처리 국가·이전 적법근거 확인을 분리 · V3 |
| KR26 · KR-ACT<br>제32조제1항·제2항 | 기준 이상 학습 연산량 시스템의 위험관리와 결과 제출 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail<br>[gateway/app/incidents.py:235](../../../../full_stack_lab/gateway/app/incidents.py#L235) report | **부분**<br>이미 있음 + 갭 | P1: 모델 공급자의 적용성·안전성 평가·제출 근거 연결; 연산량 기준 미확인 · V6 |

### EU

| ID·출처·요구 조항 | 요구 요약 | MINT 기능(코드 파일:행) | 판정·관계 | 가져올 것·개발 제안 |
| --- | --- | --- | --- | --- |
| EU01 · EU<br>Art.9(1)~(7) | 고위험 시스템 생애주기 위험관리·시험 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/core.py:1662](../../../../full_stack_lab/gateway/app/core.py#L1662) _call_upstream/contract recheck | **부분**<br>이미 있음 + 갭 | P1: 용도·예견 오용·잔여 위험·정기 재평가 연결 · V6 |
| EU02 · EU<br>Art.12(1)~(3) | 고위험 시스템의 자동 기록 기능 | [gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>이미 있음 + 갭 | P4: MCP 호출 밖 모델·업무 사건의 추적과 로그 완전성 확인 · V4 |
| EU03 · EU<br>Art.13(1)~(3) | 배치자가 이해할 사용 지침·한계 제공 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/supplier_assurance.py:94](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L94) export_rows | **부분**<br>이미 있음 + 갭 | P1: 의도된 사용·정확도·금지 용도·변경 통지의 공급자 문서 연결 · V3 |
| EU04 · EU<br>Art.14(1)~(4) | 사람 감독·중단·번복 지원 | [gateway/app/core.py:1636](../../../../full_stack_lab/gateway/app/core.py#L1636) _call_upstream/high-impact binding<br>[gateway/app/decommission.py:717](../../../../full_stack_lab/gateway/app/decommission.py#L717) assess | **부분**<br>이미 있음 + 갭 | P5: 자동화 편향·감독자 권한·정지 후 업무 영향까지 검증 · V5 |
| EU05 · EU<br>Art.15(1)~(5) | 정확도·강건성·사이버보안 | [gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result<br>[gateway/app/core.py:2330](../../../../full_stack_lab/gateway/app/core.py#L2330) execute_call/input inspection<br>[gateway/app/core.py:2396](../../../../full_stack_lab/gateway/app/core.py#L2396) execute_call/policy failure | **부분**<br>이미 있음 + 갭 | P2: 정책 차단 성능과 모델 정확도/편향/견고성의 측정 분리 · V2 |
| EU06 · EU<br>Art.17(1) | 제공자의 품질관리시스템 | [gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision<br>[gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **부분**<br>이미 있음 + 갭 | P1: 조직 QMS·책임·공급자·시정조치 문서와 연결; 제품 인증 주장 금지 · V3 |
| EU07 · EU<br>Art.26(6) | 통제 가능한 자동 로그를 원칙상 최소 6개월 보관 | [gateway/app/retention.py:31](../../../../full_stack_lab/gateway/app/retention.py#L31) floor<br>[gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>이미 있음 + 갭 | P4: 관할·대상 로그·다른 법의 예외와 실제 백업 복구 보존을 검증 · V4 |
| EU08 · EU<br>Art.27(1) | 해당 배치자의 기본권 영향평가 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **부분**<br>이미 있음 + 갭 | P1: 영향 집단·피해·감독·구제수단·법정 서식 차이를 보완 · V3 |
| EU09 · EU-GPAI<br>Art.53(1)(a)~(b) | GPAI 제공자 기술문서와 하류 통합자 정보 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/supplier_assurance.py:94](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L94) export_rows | **부분**<br>이미 있음 + 갭 | P1: Annex XI/XII 항목별 모델 공급자 자료·판본·갱신 근거 연결 · V3 |
| EU10 · EU-GPAI<br>Art.53(1)(c)~(d) | 저작권 정책과 학습 콘텐츠 공개 요약 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate | **미충족**<br>갭 | P1: GPAI 제공자 책임 문서를 수집; MCP 라이선스 심사로 대체하지 않음 · V3 |
| EU11 · EU-GPAI<br>Art.55(1)(a)~(b) | 체계적 위험 GPAI의 모델 적대 평가·위험 완화 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result | **부분**<br>이미 있음 + 갭 | P2: 모델 공급자의 평가 보고서·기준·재검증 증거 연결 · V2 |
| EU12 · EU-GPAI<br>Art.55(1)(c)~(d) | 중대 사고 추적·보고와 모델/인프라 보안 | [gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail<br>[gateway/app/incidents.py:235](../../../../full_stack_lab/gateway/app/incidents.py#L235) report | **부분**<br>이미 있음 + 갭 | P6: 공급자·당국 통지 책임과 실제 보고 증빙 연결 · V6 |

### NIST·ISO

| ID·출처·요구 조항 | 요구 요약 | MINT 기능(코드 파일:행) | 판정·관계 | 가져올 것·개발 제안 |
| --- | --- | --- | --- | --- |
| NI01 · NIST<br>GOVERN 1.6·1.7 | 자산 목록 및 안전한 단계적 종료 | [gateway/app/supplier_assurance.py:94](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L94) export_rows<br>[gateway/app/decommission.py:717](../../../../full_stack_lab/gateway/app/decommission.py#L717) assess | **부분**<br>이미 있음 + 갭 | P6: MCP 외 모델·하네스·메모리·하류 시스템 의존성 연결 · V6 |
| NI02 · NIST<br>GOVERN 3.2·MANAGE 4.1 | 감독 역할·사후 모니터링·피드백·복구 | [gateway/app/review.py:64](../../../../full_stack_lab/gateway/app/review.py#L64) require_independent<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail | **부분**<br>이미 있음 + 갭 | P1: 책임자·이의제기·복구 훈련과 정기 검토 기록 연결 · V6 |
| NI03 · NIST<br>MEASURE 2.7 | 보안·복원력 평가 문서화 | [gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision<br>[gateway/app/core.py:2396](../../../../full_stack_lab/gateway/app/core.py#L2396) execute_call/policy failure | **부분**<br>이미 있음 + 갭 | P2: 정상 사용 성공률·장애·복구와 효과 근거를 함께 보존 · V2 |
| NG01 · NIST-GAI<br>GV-1.7-001·002 | 비활성화와 폐기 후 데이터·의존성 위험 고려 | [gateway/app/decommission.py:717](../../../../full_stack_lab/gateway/app/decommission.py#L717) assess<br>[gateway/app/retention.py:31](../../../../full_stack_lab/gateway/app/retention.py#L31) floor | **부분**<br>이미 있음 + 갭 | P6: 진행 호출·자격 회수·외부 잔존 데이터 효과를 독립 확인 · V6 |
| NG02 · NIST-GAI<br>GV-6.1-006·007·009 | 공급자 목록·조달 실사·계약상 평가 근거 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/core.py:1662](../../../../full_stack_lab/gateway/app/core.py#L1662) _call_upstream/contract recheck | **부분**<br>이미 있음 + 갭 | P1: 모델 공급자 데이터/지재권/평가 근거를 MCP 심사와 연결 · V3 |
| NG03 · NIST-GAI<br>MS-2.7-004·007·009 | 보안 지표·레드팀·정기 효과 검증 | [gateway/app/core.py:2330](../../../../full_stack_lab/gateway/app/core.py#L2330) execute_call/input inspection<br>[gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result<br>[gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>이미 있음 + 갭 | P2: 실제 하네스·실제 OSS MCP·정상 대조군의 반복 및 오탐/미탐 측정 · V2 |
| IS01 · ISO<br>6.1.2·6.1.3·6.1.4(기존 note) | 위험 평가·처리·영향평가 문서화 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P1: 조직 위험 기준·잔여 위험 승인·적용 통제와 SoA 연결(조항 미확인) · V3 |
| IS02 · ISO<br>A.5.2·9.2.1·10.2(기존 note) | 영향평가·내부감사·시정조치 | [gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail | **부분**<br>상세 근거 미확인·잠정<br>이미 있음 + 갭 | P1: 조직 운영의 감사/검토/시정 증빙 연결(조항 미확인) · V3 |

### OWASP LLM Top 10

| ID·출처·요구 조항 | 요구 요약 | MINT 기능(코드 파일:행) | 판정·관계 | 가져올 것·개발 제안 |
| --- | --- | --- | --- | --- |
| LL01 · LLM<br>LLM01 프롬프트 인젝션 | 외부 지시가 도구 행동을 바꾸는 위험 축소 | [gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result<br>[gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope | **부분**<br>이미 있음 + 갭 | P2: 우회·인코딩·한국어·멀티턴 공격과 정상 문서 대조 · V2 |
| LL02 · LLM<br>LLM02 민감정보 노출 | 도구 입력·응답 개인정보·비밀 노출 축소 | [gateway/app/core.py:2330](../../../../full_stack_lab/gateway/app/core.py#L2330) execute_call/input inspection<br>[gateway/app/core.py:1953](../../../../full_stack_lab/gateway/app/core.py#L1953) _inspected_result<br>[gateway/app/core.py:1970](../../../../full_stack_lab/gateway/app/core.py#L1970) _audit_payload | **부분**<br>이미 있음 + 갭 | P2: 원장·오류·짧은 문자열까지 잔여 개인정보 검사 · V2 |
| LL03 · LLM<br>LLM03 공급망 | 승인하지 않은 도구·구성요소 변경 제한 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/core.py:1662](../../../../full_stack_lab/gateway/app/core.py#L1662) _call_upstream/contract recheck | **부분**<br>이미 있음 + 갭 | P3: SBOM·출처 증명·공급자 변경과 승인 재사용 불가 검증 · V3 |
| LL04 · LLM<br>LLM04 데이터·모델 오염 | 학습·검색·메모리 오염 통제 | [gateway/app/core.py:1662](../../../../full_stack_lab/gateway/app/core.py#L1662) _call_upstream/contract recheck<br>[gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result | **부분**<br>이미 있음 + 갭 | P3: MCP 계약 검사와 학습/벡터 데이터 오염 검증을 구분해 연동 · V2 |
| LL05 · LLM<br>LLM05 부적절한 출력 처리 | 도구 결과 형식·크기·콘텐츠 검증 | [gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result<br>[gateway/app/core.py:1953](../../../../full_stack_lab/gateway/app/core.py#L1953) _inspected_result | **부분**<br>이미 있음 + 갭 | P2: 최종 소비 앱의 SQL/HTML/명령 실행 경계도 별도 검증 · V2 |
| LL06 · LLM<br>LLM06 과도한 자율성 | 도구·자산·동작 최소 권한 및 승인 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/core.py:1636](../../../../full_stack_lab/gateway/app/core.py#L1636) _call_upstream/high-impact binding | **부분**<br>이미 있음 + 갭 | P3: 기본 권한·동적 도구·승인 경합·도구 밖 우회 비교 · V1 |
| LL07 · LLM<br>LLM07 시스템 프롬프트 유출 | 프롬프트 내 비밀과 인가 의존 축소 | [gateway/app/upstream.py:40](../../../../full_stack_lab/gateway/app/upstream.py#L40) credential_headers<br>[gateway/app/core.py:1953](../../../../full_stack_lab/gateway/app/core.py#L1953) _inspected_result | **부분**<br>이미 있음 + 갭 | P2: 모델 프롬프트·대화 저장소 유출을 별도 평가; 토큰 분리와 구분 · V2 |
| LL08 · LLM<br>LLM08 벡터·임베딩 취약점 | 검색 저장소 권한·오염 경계 검증 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope | **부분**<br>이미 있음 + 갭 | P3: 검색 객체별 ACL·메타데이터 출처·교차 사용자 검색 시험 연동 · V1 |
| LL09 · LLM<br>LLM09 허위정보 | 모델 최종 답변 사실성 평가 | [gateway/app/high_impact.py:25](../../../../full_stack_lab/gateway/app/high_impact.py#L25) explanation<br>[gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result | **미충족**<br>갭 | P5: 출처 대조·업무 정답·사용자 정정 절차를 모델/앱에서 검증 · V5 |
| LL10 · LLM<br>LLM10 무제한 자원 소비 | 도구 호출·결과 자원 상한 | [gateway/app/core.py:1431](../../../../full_stack_lab/gateway/app/core.py#L1431) _reserve_call<br>[gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result | **부분**<br>이미 있음 + 갭 | P2: MCP 상한과 LLM 토큰·비용·반복 루프 예산을 분리 검증 · V2 |

### OWASP Agentic Top 10

| ID·출처·요구 조항 | 요구 요약 | MINT 기능(코드 파일:행) | 판정·관계 | 가져올 것·개발 제안 |
| --- | --- | --- | --- | --- |
| AS01 · ASI<br>ASI01 목표 탈취 | 목표 조작의 실행 피해 제한 | [gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result<br>[gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope | **부분**<br>이미 있음 + 갭 | P2: 다단계 업무의 목적 이탈·정상 수행률 검증 · V2 |
| AS02 · ASI<br>ASI02 도구 오용 | 호출 권한·인자·실행 경계 적용 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/core.py:1662](../../../../full_stack_lab/gateway/app/core.py#L1662) _call_upstream/contract recheck | **부분**<br>이미 있음 + 갭 | P3: 허용 도구 안의 위험한 조합·독립 효과 검증 · V1 |
| AS03 · ASI<br>ASI03 신원·권한 남용 | 검증 신원과 최소 권한 사용 | [gateway/app/mcp_facade.py:46](../../../../full_stack_lab/gateway/app/mcp_facade.py#L46) _caller<br>[gateway/app/upstream.py:40](../../../../full_stack_lab/gateway/app/upstream.py#L40) credential_headers<br>[gateway/app/pac.py:30](../../../../full_stack_lab/gateway/app/pac.py#L30) delegation | **부분**<br>이미 있음 + 갭 | P3: bearer 탈취·주체 혼동·위임 위조 및 관리 계정 우회 검증 · V1 |
| AS04 · ASI<br>ASI04 에이전트 공급망 | 도구·서버·연동 변경 심사 | [gateway/app/supplier_assurance.py:25](../../../../full_stack_lab/gateway/app/supplier_assurance.py#L25) validate<br>[gateway/app/core.py:1662](../../../../full_stack_lab/gateway/app/core.py#L1662) _call_upstream/contract recheck | **부분**<br>이미 있음 + 갭 | P3: 모델·스킬·프레임워크 의존성까지 별도 공급망 책임 연결 · V3 |
| AS05 · ASI<br>ASI05 예기치 않은 코드 실행 | 미승인 실행 효과 제한 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/core.py:1636](../../../../full_stack_lab/gateway/app/core.py#L1636) _call_upstream/high-impact binding | **부분**<br>이미 있음 + 갭 | P3: 게이트웨이 밖 셸·SDK와 MCP 실행기 격리 경계를 구분 검증 · V1 |
| AS06 · ASI<br>ASI06 메모리·문맥 오염 | 지속 기억과 교차 호출 문맥 오염 방지 | [gateway/app/core.py:1337](../../../../full_stack_lab/gateway/app/core.py#L1337) _flow_sources<br>[gateway/app/core.py:1922](../../../../full_stack_lab/gateway/app/core.py#L1922) _guarded_result | **부분**<br>이미 있음 + 갭 | P2: 원문/변환/요약 후 재사용과 외부 메모리 변조 정상 대조 · V2 |
| AS07 · ASI<br>ASI07 에이전트 간 통신 | 에이전트 간 상호 인증·신뢰 경계 확보 | [gateway/app/mcp_facade.py:46](../../../../full_stack_lab/gateway/app/mcp_facade.py#L46) _caller<br>[gateway/app/pac.py:30](../../../../full_stack_lab/gateway/app/pac.py#L30) delegation | **부분**<br>이미 있음 + 갭 | P3: MCP 직원 신원을 A2A 에이전트 신원으로 세지 않음; 표준/EDR 연동 검토 · V1 |
| AS08 · ASI<br>ASI08 연쇄 장애 | 격리·상한·장애 대응과 복구 | [gateway/app/core.py:1431](../../../../full_stack_lab/gateway/app/core.py#L1431) _reserve_call<br>[gateway/app/core.py:2396](../../../../full_stack_lab/gateway/app/core.py#L2396) execute_call/policy failure<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail | **부분**<br>이미 있음 + 갭 | P6: 검사기 장애·지연·중복 호출의 하류 효과·복구 훈련 · V6 |
| AS09 · ASI<br>ASI09 사람-에이전트 신뢰 악용 | 승인자를 속이는 요청과 자동화 편향 축소 | [gateway/app/high_impact.py:25](../../../../full_stack_lab/gateway/app/high_impact.py#L25) explanation<br>[gateway/app/review.py:64](../../../../full_stack_lab/gateway/app/review.py#L64) require_independent | **부분**<br>이미 있음 + 갭 | P5: 승인 요약 진실성·피로·근거 확인과 정상 승인 소요 검증 · V5 |
| AS10 · ASI<br>ASI10 일탈 에이전트 | 지속 이탈의 탐지·중지·책임 추적 | [gateway/app/core.py:1337](../../../../full_stack_lab/gateway/app/core.py#L1337) _flow_sources<br>[gateway/app/decommission.py:717](../../../../full_stack_lab/gateway/app/decommission.py#L717) assess<br>[gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>이미 있음 + 갭 | P6: MCP 밖 행동 가시성 한계와 OS/업무 연동 증거 구분 · V6 |

### CSA MAESTRO·MCP

| ID·출처·요구 조항 | 요구 요약 | MINT 기능(코드 파일:행) | 판정·관계 | 가져올 것·개발 제안 |
| --- | --- | --- | --- | --- |
| CS01 · CSA<br>§3.2 A 계층별 분석 | 7계층별 자산·신뢰 경계·위협 분해 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/core.py:1990](../../../../full_stack_lab/gateway/app/core.py#L1990) _record_decision | **부분**<br>이미 있음 + 갭 | P3: 기반 모델·데이터·프레임워크·인프라·평가·보안·생태계 책임 연결 · V3 |
| CS02 · CSA<br>§3.2 B 교차 계층 위협 | 관측·데이터·권한 경계를 넘는 공격 분석 | [gateway/app/core.py:1337](../../../../full_stack_lab/gateway/app/core.py#L1337) _flow_sources<br>[gateway/app/core.py:1970](../../../../full_stack_lab/gateway/app/core.py#L1970) _audit_payload | **부분**<br>이미 있음 + 갭 | P2: 도구 결과→메모리→후속 도구 및 로그 유출 사슬 검증 · V2 |
| CS03 · CSA<br>§3.2 D 구현·모니터링 | 위험 우선순위와 지속 재검토 | [gateway/app/risk_tier.py:77](../../../../full_stack_lab/gateway/app/risk_tier.py#L77) assess<br>[gateway/app/incidents.py:155](../../../../full_stack_lab/gateway/app/incidents.py#L155) detail | **부분**<br>이미 있음 + 갭 | P1: 계층별 잔여 위험·담당·시험 근거를 기존 대장과 연결 · V3 |
| MC01 · MCP<br>Token Passthrough | 직원 토큰을 upstream으로 넘기지 않음 | [gateway/app/mcp_facade.py:46](../../../../full_stack_lab/gateway/app/mcp_facade.py#L46) _caller<br>[gateway/app/upstream.py:40](../../../../full_stack_lab/gateway/app/upstream.py#L40) credential_headers | **충족**<br>이미 있음(정적 범위) | P3: 전용 자격 resource/principal/expiry와 잘못된 audience 음성 회귀 유지 · V1 |
| MC02 · MCP<br>SSRF | 연결 직전 목적지 DNS/IP 검증 | [gateway/app/destination.py:20](../../../../full_stack_lab/gateway/app/destination.py#L20) PinnedBackend.connect_tcp | **충족**<br>이미 있음(정적 범위) | P3: 승인 내부 목적지·외부 DNS 재결속·IPv6·메타데이터 주소 회귀 유지 · V1 |
| MC03 · MCP<br>State Handle Hijacking | 세션을 인증 주체·장치·서버와 결속 | [gateway/app/mcp_sessions.py:21](../../../../full_stack_lab/gateway/app/mcp_sessions.py#L21) active | **충족**<br>이미 있음(정적 범위) | P3: 세션 재사용·철회·종료 경합과 복구를 실제 전송 경계에서 확인 · V1 |
| MC04 · MCP<br>Confused Deputy·Scope Minimization | 클라이언트별 동의와 최소 scope 확인 | [gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope<br>[gateway/app/upstream.py:40](../../../../full_stack_lab/gateway/app/upstream.py#L40) credential_headers | **부분**<br>이미 있음 + 갭 | P3: MINT의 OAuth 역할별 동의·redirect/state/issuer 경계를 별도 점검 · V1 |
| MC05 · MCP<br>Local MCP Server Compromise·stdio Transport Security | 로컬 서버의 실행·환경·권한 경계 보호 | [gateway/app/mcp_facade.py:46](../../../../full_stack_lab/gateway/app/mcp_facade.py#L46) _caller<br>[gateway/app/pac.py:69](../../../../full_stack_lab/gateway/app/pac.py#L69) scope | **부분**<br>이미 있음 + 갭 | P3: 관리형 실행기·OS 강제와 비관리 계정·다른 셸의 우회를 구분 검증 · V1 |

## 기존 계획을 현재 코드로 정정한 부분과 중요한 제한

1. DEV-66: 사고 패키지·기한·보고 기록이 **이미 있음**(`incidents.detail/report`). 외부 당국 제출과 관할 조항의 최신성·보고 의무자 결정은 갭이다. 새 패키지를 중복 구현하지 않는다.
2. DEV-67: 보존 하한 설정·봉인 검증은 **이미 있음**. `retention.py:1`이 실제 삭제를 소유자 결정까지 보류한다고 명시한다. 보존 설정이 개인정보 삭제·파기 완료를 뜻하지 않는다. append-only 원칙을 변경하지 않았다.
3. DEV-68~71: 공급자 보증·대장 내보내기, 처리/저장 국가, 중대 영향 호출 승인, 위험 평가 입력이 **이미 있음**. 다만 `residency.enabled:94`의 관할 팩 설정, 입력 자료의 진실성, 최종 업무 결정 설명·권리 처리와 실제 외부 효과는 갭이다.
4. `core._audit_payload:1970`은 긴 문자열의 앞부분을 남기고 짧은 문자열은 보존할 수 있다. ‘응답 본문 미보관’에서 ‘모든 요청/로그에 개인정보 없음’을 추론하면 안 된다. 입력 검사·등급·예외/ignore 경로와 원장 열을 합성 PII로 확인해야 한다.
5. `core.execute_call:2411`의 관찰 모드는 일부 차단/승인 결과를 허용으로 바꾼다. 집행 모드를 확인하지 않고 ‘항상 차단’으로 표현하지 않는다. `review.solo_mode_enabled:85`의 root 단독 모드는 독립 승인 면제가 아니다. `require_independent:64`의 동일인 거절 및 등급별 승인자 수를 유지한 상태에서 운영 설정과 표시·감사 관측의 한계를 확인해야 한다.
6. [SECURITY_BOUNDARIES](../../../../docs/ai/SECURITY_BOUNDARIES.md)의 관리 계정·OS·bearer·셸/SDK 우회 경계를 유지한다. 하네스 clientInfo/User-Agent는 기록이며 신뢰 신원으로 승격하지 않는다. MCP 중지와 모델·외부 저장소·SaaS 데이터의 폐기는 별개다.
7. LiteLLM의 LLM 프록시 경로와 MCP 집계/실행 경로는 별개다. 기존 [LiteLLM 분석](../../solutions/litellm.md) 및 [MCP 코드 분석](../oss-deep/litellm-mcp-path.md)을 재사용하며 이번에 LLM 입력/최종 답변의 전면 중재나 비용 통제를 검증하지 않았다. MCP 출력 검사로 생성물 표시·환각·학습 데이터 오염을 충족 처리하지 않는다.
8. EU 일정: 기존 LIB-M01/M16의 적용일 변경 기록은 공식 개정 원문 재확인이 막혀 **미확인**이다. 이 분석은 요구 내용 대응이며 적용일 확정이나 고객별 적용성 판단을 제공하지 않는다. 고위험 로그 최소 6개월도 해당 행위자가 통제하는 로그와 타법 예외 범위에 한한다.

## 개발 제안 우선순위와 기존 기능 재사용

| 제안 | 우선순위·정상 기능/운영 효과 | 기존 기능에서 가져올 것·갭 |
| --- | --- | --- |
| P0 공식 조항·판본 확인 | 먼저 확정; 근거 없는 기능 추가 방지 | 시행령 안/현행, NIS, 금융 최종본, ISO 전문·PIPC/KISA 상세·EU 적용일의 미확인 해소 |
| P1 증빙 연결 보강 | 반복 입력 줄이고 심사 담당자에게 근거 재사용 | DEV-68/69/71 대장에 법적 역할·판본·증빙 만료·모델 공급자 문서·책임 조직을 연결. 새 승인 체계 중복 금지 |
| P2 정상/공격 효과 측정 | 정상 문서 오차단·지연을 먼저 가시화 | 기존 코퍼스·한국어 PII·실제 MCP 시험을 재사용해 오탐/미탐·정상 업무 성공·자원 소모를 독립 측정. 규칙 개수나 차단 수를 효과로 대체하지 않음 |
| P3 권한·공급망·연결 경계 검증 | 승인된 연결의 예측 가능성과 빠른 복구 | 기존 PAC·계약·세션·자격·실행기 경계에 잘못된 역할/자산·변경·경합·복구 증거 연결. 직원 토큰 전달·권한 완화 금지 |
| P4 증거 최소화·보존 설계 | 필요한 증거를 찾고 불필요한 본문 복사 축소 | DEV-67 봉인/백업 검증·원장 미리보기 개인정보 잔존 조사. 실제 삭제는 append-only 원칙과 소유자 결정 해결 전 구현 제안 상태 |
| P5 업무 설명·권리 연계 | 정상 승인·이의 제기·재검토 동선 단순화 | DEV-70 승인 증빙을 업무 결정 ID·설명·번복과 연결. 최종 모델 설명·편향 평가는 고객 앱/공급자 책임과 연계 |
| P6 운영 훈련·종료 효과 | 장애 시 원인·담당·복구 상태 확인 | DEV-66 및 C1~C4/T1~T3 모델을 재사용해 당국 보고 책임·진행 호출·자격 회수·외부 데이터 잔존을 독립 검증 |

새 의존성·mock MCP·정책/설계 변경·제품 UI 변경은 하지 않았다. 제안 채택·구현 단계에서 고정 OSS/공식 SDK·라이선스·유지보수와 실제 사용 범위를 다시 검토한다.

## 원자 요구별 시험 조건과 증거 수준

각 행의 V 번호는 아래 정상·음성·경계·실패·경쟁·복구 조건으로 연결된다. 요구별 구체 데이터와 실사용 권한은 실행 계획에서 고정한다. 기존 시험 파일 존재는 통과 증거가 아니다.

| 프로필 | 수용 조건 |
| --- | --- |
| V0 | 문서 확인: 공식 원문·판본·조항·시행 상태 대조. 차단/미열람이면 미확인 유지. |
| V1 | 권한: 정상 승인 호출 성공 / 잘못된 주체·범위 거부 / 만료 직전·직후 / IdP·정책 장애 차단 / 승인·철회·전송 경쟁 / 재인증·재승인 후 복구. decision와 policy_id, 독립 수신 효과 확인. |
| V2 | 검사·성능: 정상 한국어·업무 문서 / PII·비밀·주입 공격 / 길이·건수·유사값 경계 / 검사기 오류·시간초과 / 동시 호출·예산 소진 / 정상 복구. 반복·오탐·미탐·지연·업무 성공과 독립 노출 건수 기록. |
| V3 | 도입·변경: 승인된 고정 OSS 정상 / 미승인 commit·계약·근거 누락 거부 / 만료·지원 종료 경계 / scanner·메타데이터 장애 / 심사 중 변경·철회 경쟁 / 새 판본 재심사 복구. 판본·license·hash·검토자 연결. |
| V4 | 증거·보존: 정상 원장/내보내기 / 변조·미리보기 개인정보 노출 / 보존 하한·구간 경계 / DB·서명목록 장애 / 수집 중 내보내기·봉인 경쟁 / 백업 복구 후 부활 탐지. 삭제는 현재 보류이므로 실행 성공 주장 금지. |
| V5 | 사람·업무: 정상 고지·승인·설명 / 자가 승인·허위 설명·권리 누락 / 영향 등급·만료 경계 / 설명 자료 불능 / 승인·범위 변경 경쟁 / 번복·재검토 후 업무 효과. 모델 평가와 호출 정책을 별도 측정. |
| V6 | 운영·종료: 정상 도구 업무 / 비정상 연쇄·접근 잔존 / 진행 호출·기한 경계 / 네트워크·관측·폐기 장애 / cutover·중복 실행 경쟁 / 독립 자격 거부·하류 데이터·복구 확인. 실제 OSS와 격리 계정·합성 데이터만 사용. |

기존 시험 후보(이번 미실행): `full_stack_lab/tests/{high_impact_check,intake_risk_tier_check,supplier_assurance_check,data_residency_check,residency_transfer_review_check,ledger_retention_check,incident_pack_check,mcp_result_contract_check,mcp_result_services_check,oauth_negative_pg_check,session_termination_check,termination_flow,korean_pii_eval,inspection_corpus_eval}.py`. 실행 환경과 대역/실제 의존성은 각 파일 및 docs/ai/TESTING.md가 우선한다. 로컬 스택을 띄우지 않으며 후속 실환경 검증은 리더가 솔루션 기기→PJ1 순서로 수행한다.

## 재생성과 실제 검사

`py -3 -B -X utf8 research/llm-wiki/analysis/regulation-gap-1023/build.py`는 이 README·gap.json을 생성한다. 원본 note·CSV·코드 내용은 변경하지 않는다. 행·hash·기존 요구 키·출처·링크 검사의 실제 결과는 [작업 보고](../../status/reports/2026-10-23-regulation-gap.md)를 따른다. 소스 확인을 제품 실행 성공으로 세지 않는다.
