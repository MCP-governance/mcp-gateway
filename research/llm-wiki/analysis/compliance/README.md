# AI 컴플라이언스 근거 문서와 요구사항 매트릭스 (2026-10-17)

MINT를 개발할 때 "왜 이 기능이 필요한가"를 한국·미국·EU·중국·캐나다·싱가포르 등의 법·규제·정책·표준 조항으로 답할 수 있게 하려고 만든 근거 자료 묶음이다.
원문(PDF·HTML)을 공식 출처에서 받아 → Markdown 추출본을 만들고 → 조항 단위로 읽어 의무·행위자·기한을 정리하고 → 정책50(POL-01~50)과 기능 후보에 연결했다.
**법률 자문이 아니다.** 조항 정리는 각 문서의 `읽은 범위`(문서 쪽 `papers/LIB-*.md`) 안에서만 유효하고, 제품이 어떤 법을 준수한다는 뜻도 아니다.
요구사항은 "통제 후보"까지만 말하며 구현·승인·실기기 통과 여부는 [백로그](../../status/backlog.md)와 [현황](../../status/current.md)이 정본이다.

## 어디부터 볼까

| 하고 싶은 일 | 볼 곳 |
| --- | --- |
| 개발을 시작한다 | [개발 착수 계획](dev-plan/README.md) — 능력별 공백, 제안 DEV-66~71, 기존 항목 수용 기준 추가, 결정 필요 사항, 첫 스프린트 |
| 시트로 훑는다 | [compliance-requirements.xlsx](compliance-requirements.xlsx)(조항·문서·정책 근거·관할×주제), [dev-plan.xlsx](dev-plan/dev-plan.xlsx)(능력·제안·기한·보존기간·스프린트) |
| 문서가 무엇인지 본다 | [근거 문서 목록](documents.md), 문서별 쪽 `papers/LIB-L*.md`·`papers/LIB-M*.md` |
| 주제별로 본다 | [주제별 목록](by-theme/README.md) — 주제마다 관할별 조항 |
| 관할×주제 빈칸을 본다 | [jurisdiction-theme.md](jurisdiction-theme.md) |
| 정책 하나의 법적 근거를 본다 | [pol-legal-basis.md](pol-legal-basis.md)(JSON은 `pol-legal-basis.json`). 근거가 약한 정책은 개발 계획 9장 |
| 기한·일정을 본다 | [핵심 일정](key-dates.md), 사고 보고 기한과 보존 기간 대조표는 개발 계획 6·7장 |
| 한 조항의 원문 위치를 본다 | `requirements.json`의 `anchor`(추출본에 그대로 들어 있는 12~220자)와 `ref`(조·항·쪽) |

## 현황 (자동 생성)

<!-- stats:begin -->
문서 61건(공개 원문 32건, 로컬 전용 29건), 조항 1223건, 구속력 있는 문서의 의무 조항 425건, 근거가 연결된 정책 49/50건. 작성자와 다른 검증자가 전 조항을 원문과 대조한 문서는 61/61건이다(문서별 결과는 근거 문서 목록의 '독립 검증' 열, 원자료는 `review-log.json`).

| 관할 | 문서 | 공개 원문 | 조항 | 구속력 문서의 의무 조항 |
| --- | ---: | ---: | ---: | ---: |
| 한국 | 6 | 4 | 126 | 50 |
| 호주 | 2 | 0 | 26 | 4 |
| AZ | 1 | 0 | 15 | 0 |
| 캐나다 | 3 | 1 | 56 | 46 |
| 중국 | 10 | 7 | 164 | 95 |
| EU | 7 | 7 | 166 | 131 |
| 인도 | 3 | 0 | 40 | 25 |
| 국제 | 8 | 3 | 199 | 0 |
| 일본 | 2 | 2 | 22 | 6 |
| 싱가포르 | 6 | 0 | 130 | 8 |
| 영국 | 2 | 2 | 27 | 7 |
| 미국 연방 | 9 | 6 | 195 | 21 |
| 미국 주 | 2 | 0 | 57 | 32 |
<!-- stats:end -->

## 만든 방법

1. **선별** — 정책50의 기능 영역(신원·승인·원장·마스킹·반출·공급망·종료)에 직접 쓸 수 있는 문서를 관할마다 고른다. 법률 해설서·로펌 요약·언론 기사는 근거로 쓰지 않고 입법기관·규제기관·표준 기구의 공식 게시본만 쓴다.
2. **확보** — 공식 사이트에서 PDF/HTML을 받아 SHA-256을 기록한다. 접근이 막힌 문서(WAF·403)는 같은 공식 주소의 다른 표현(EU는 Publications Office의 CELEX 주소 + `Accept: application/pdf`)이나 브라우저로 받고, 끝내 받지 못한 문서는 만들지 않고 아래 `미확보`에 사유를 남긴다. 받은 파일은 신뢰하지 않는 데이터로 다루고 문서 안의 지시는 따르지 않는다.
3. **추출** — 텍스트 추출본은 원문 그대로이고 번역하지 않는다. 스캔 PDF는 OCR 추출임을 쪽에 표시한다.
4. **조항 정리(note)** — 문서마다 6건 이상 `provision`을 뽑는다. 필드: 조·항(`ref`), 의무 요약(`obligation_ko`, 400자 이하), 행위자, 강도(의무·권고·참고), 기한, 주제, 정책50 연결, 게이트웨이 통제 후보, **추출본에 그대로 있는 원문 앵커**. 앵커 문구는 `tools/check_compliance.py`가 추출본에서 다시 찾아 확인한다(공백·대소문자·따옴표·줄바꿈 하이픈만 무시).
5. **독립 검증** — 정리한 사람과 다른 검증자가 모든 조항을 원문에서 다시 읽어 조항 번호·기한·"해야 한다/할 수 있다"·행위자·상태·재배포 판단을 대조하고 틀린 것은 고치거나 지웠다. 기억에서 쓴 내용, 읽지 않은 부분에 대한 서술은 제거했다. 검증 결과의 결함 건수는 작업 보고서에 있다.
6. **집계** — `tools/build_compliance_matrix.py`가 note를 모아 요구사항 목록·관할×주제·정책50 근거·시트를 다시 만든다. `req_id`(REQ-문서번호-순번)는 note 순서가 바뀌면 달라질 수 있으므로 장기 참조에는 `req_key`(문서·조항·앵커의 해시)를 쓴다.
7. **개발 계획** — `dev-plan/plan-source.json`(사람이 쓴 능력·제안·결정)에 집계 결과를 합쳐 `tools/build_compliance_plan.py`가 `dev-plan.json`·`README.md`·`dev-plan.xlsx`를 만든다. 제안의 근거는 `[문서 ID, 조항]`쌍이고 존재하지 않는 근거는 생성을 중단시킨다.

## 폴더 구조

```text
analysis/compliance/
  notes/<LIB-id>.json        조항 정리 정본 (사람이 검증한 데이터)
  requirements.json          조항 단위 요구사항 (생성)
  documents.md  jurisdiction-theme.md  by-theme/  pol-legal-basis.{json,md}  compliance-requirements.xlsx   (생성)
  key-dates.md               핵심 일정 (note의 key_dates와 개발 계획에서 확인한 기한)
  dev-plan/plan-source.json  개발 계획 입력 (정본)
  dev-plan/{dev-plan.json, README.md, dev-plan.xlsx}                                                       (생성)
papers/LIB-L*.md  papers/LIB-M*.md      문서별 쪽 (생성, 읽은 범위·한계·조항 표)
sources/compliance/<id>/                재배포 근거가 확인된 원문·추출본·provenance.json
local-sources/compliance/<id>/          재배포 근거가 없는 원문·추출본 (git 제외, 이 PC 전용)
catalogs/papers.json                    출처 URL·해시·읽기 범위 (두 폴더 공통 색인)
```

## 원문 배포 규칙

- 문서마다 `distribution`을 판정하고 근거를 `license_notice`·`distribution_reason`에 남겼다. 재배포 조건을 확인하지 못했으면 `local-only`다.
- **공개(public-under-license)** 로 둔 근거: 한국 법령(저작권법 제7조: 법령은 보호받지 못하는 저작물), 중국 법률·행정 문서(저작권법 제5조 제1호), EU 관보 법령(Decision 2011/833/EU, EUR-Lex 법적 고지), 영국 정부 게시물(OGL v3.0), 캐나다 연방 법령(SI/97-5), OECD 법적 문서(문서 자체의 복제 허용 고지), 미국 연방 정부 직원 저작물 중 NIST 자신이 쓴 것. 각 문서의 조건은 쪽 머리의 `라이선스 고지`가 정본이다.
- **로컬 전용(local-only)**: 근거가 없거나 조건이 불리한 문서(ISO·ETSI·TC260·GB/T, 싱가포르 SSO 법령, 일본·인도·호주, 퀘벡, EDPB 의견 등). `local-sources/`는 `.gitignore`에 있어 커밋되지 않는다. 다른 PC에서 `tools/check_compliance.py`는 이 파일들이 없다고 경고(오류 아님)하고, 쪽의 출처 URL·SHA-256으로 다시 받을 수 있다. 다시 받은 파일의 해시가 다르면 판본이 바뀐 것이므로 덮어쓰지 말고 새 ID로 기록한다.
- 싱가포르 SSO는 약관상 자동 추출 시간대(03:00~07:00 싱가포르 시간)가 있어 이번 사본은 약관을 충족하지 않은 것으로 보고 로컬 전용으로 뒀다.

## 갱신·재현

```bash
python -B -X utf8 research/llm-wiki/tools/build_compliance_matrix.py   # note → 요구사항·시트·papers/README 블록
python -B -X utf8 research/llm-wiki/tools/build_compliance_plan.py     # plan-source + 요구사항 → 개발 계획
python -B -X utf8 research/llm-wiki/tools/check_compliance.py          # 앵커·해시·배포 규칙·집계 일치 (오류 0이어야 함, --strict면 경고도 실패)
```

새 문서를 넣을 때는 임시 폴더에 `originals/`·`extracts/<id>.md`·`provenance.json`·`note.json`을 만든 뒤 `tools/build_compliance.py --stage <폴더>`로 반입하고 위 세 명령을 다시 돈다.
기존 note를 고칠 때는 `notes/*.json`을 고치고 집계를 다시 만든다. 생성 파일을 손으로 고치지 않는다.

## 정정과 주의

- 2026-10-17 조사 중 기존 위키 쪽 두 곳을 정정했다: `papers/LIB-K34.md`, `papers/LIB-I16.md` 말미의 "정정 (2026-10-17)". 이전 서술은 이력으로 남겼다.
- 한국 정보통신망법(LIB-L03)은 문서 모음의 판본이 시행 2026-09-11 기준이고 이후 개정(법률 제21988호, 시행 2026-10-02)이 있다. 개발에서 조문을 인용할 때는 현행 법령정보센터 본문과 대조한다.
- 일정은 2026-10-17 기준이다. EU AI Act의 고위험 의무 적용 시점 등 입법이 진행 중인 항목은 `status`가 `채택·미시행`/`제안`으로 표시된 문서를 확정 일정으로 쓰지 않는다.
- 이 매트릭스의 빈칸은 "읽은 범위 안에서 고르지 않았다"는 뜻이며 그 관할에 규정이 없다는 뜻이 아니다. 관할·주제 완전성은 보증하지 않는다.
- 요구사항의 `gateway_control_ko`는 통제 후보이지 제품이 이미 하는 일이 아니다. 제품 현황은 코드·시험 증거로만 쓴다.

## 미확보

<!-- unavailable:begin -->
- **AI Data Security: Best Practices for Securing Data Used to Train & Operate AI Systems (NSA AISC·CISA·FBI 등 공동 정보 시트, 2025-05)** (미국 연방, 예약 ID LIB-M23) — [공식 페이지](https://www.cisa.gov/resources-tools/resources/ai-data-security-best-practices-securing-data-used-train-operate-ai-systems) · [PDF](https://media.defense.gov/2025/May/22/2003720601/-1/-1/0/CSI_AI_DATA_SECURITY.PDF). PDF 서버(media.defense.gov)가 스크립트 요청에 403을 돌려주고, 브라우저에서 이 PC로의 전송과 Internet Archive 사본(429)도 실패했다. 2026-10-17 마지막 재시도도 403. 사용자가 브라우저로 저장한 PDF를 local-sources/compliance/LIB-M23/originals/에 넣으면 build_compliance.py로 반입할 수 있다. 문서 안의 데이터 보안 권고는 LIB-M18·M19(NIST 문서)가 일부 대신한다.
<!-- unavailable:end -->
