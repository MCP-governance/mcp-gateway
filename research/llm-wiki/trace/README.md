# ID 추적 규칙

시트·문서·코드·룰셋이 서로 부르는 번호를 한 곳에서 읽고, 어긋나면 CI가 잡도록 정한 규칙이다. 소유자 지시(10-22): 문서 사이의 번호와 참조 연결을 추적할 수 있게 한다.

원칙은 셋이다. (1) ID마다 **정의 정본이 하나**다. (2) 다른 곳은 그 ID를 **부르기만** 한다. (3) 새 번호는 **`--next`로만** 받는다.

## 계열과 정의 정본

정의 건수는 2026-10-22 기준이다. 형식은 정규식이고, 검사기는 이 표를 `check_trace.py` 위쪽 `FAMILIES`에서 읽는다.

| 계열 | 형식 | 정의 정본(여기에 있어야 정의) | 건수 |
| --- | --- | --- | ---: |
| 결정 | `D-n`(1~9는 `D-01`) | `docs/ai/DECISIONS.md`의 `## D-n 제목`(번호대별로 나눈 뒤에는 `docs/ai/decisions/D-*.md`, 검사기가 둘 다 읽는다) | 185 |
| 백로그 | `DEV-nn` `WIKI-nn` `AIG-nn` `RM-nn` `OPS-nn` | `research/llm-wiki/status/backlog.md` 표의 첫 열(상태 정본은 구글 시트 「백로그」) | 89 |
| 백로그 옛 번호 | `RES-01` | 위 표의 한 줄. 시트 번호는 `WIKI-02`(manifest `backlog_aliases`) | 1 |
| WBS 작업 | `Gnn.nn` | `research/llm-wiki/analysis/development-wbs/snapshot.json`의 `items[].id` | 57 |
| 기능 | `F-nn` | `analysis/feature-spec-2026-10-17/feature-spec.json`의 `feature_spec` 순서(첫 항목이 F-01). 순서를 바꾸지 않는다 | 64 |
| 정책 | `POL-nn` | `research/llm-wiki/threats/policies-50.md`의 `## POL-nn` | 50 |
| 시험 | `Enn` | `catalogs/experiments.json`(카드는 `experiments/Enn-*.md`) | 19 |
| 구성요소 | `CMP-nn` | `docs/ai/architecture/components.psv` | 75 |
| OSS 재사용 | `OSS-nn` | `analysis/oss-reuse.json` | 8 |
| 배포·자료 | `DEP-nn` `DOC-nnn` | `sheet/manifest.json`의 `id_registry`(`build_sheet_export.py`가 발급, 손으로 쓰지 않는다) | 18·696 |
| 위협 | `TH-nn` | `catalogs/threats.json` | 24 |
| 로컬 도구 위험 | `LOCAL-RISK-nn` | `catalogs/local-tool-risks.json` | 13 |
| 런타임 정책 | `P-영역-nnn` `MCP-영역-nnn` `PAC-nn` `ENDPOINT-영역-nnn` | `full_stack_lab/opa/policy_ledger.json`의 `policy_ledger` 키. 집행은 `opa/policy.rego`·`opa/pac15.rego`·`gateway/app/*.py`가 같은 ID를 부른다 | 72 |
| 원본 PAC | `PACnn`(하이픈 없음) | `analysis/drive-curation/policy-id-mapping.json`의 `systems`(독스용 PAC01~50). 런타임 `PAC-01~15`와 다른 체계이며 위협·통제 내용으로만 대응한다 | 50 |
| 제품 기능 대조 | `CMP-nnn`(세 자리) | `analysis/competitor-mapping.json`. 구성요소 `CMP-nn`(두 자리)과 접두어만 같다 | 21 |
| 커밋 | 7자 SHA | git이 정본이라 검사하지 않는다 | — |

범위 밖: 규제 대장 자체의 번호(`REQ-`·`RQ-`·`CAP-`·`CTL-`·`RSK-`), 시트가 파생해 붙이는 `PLAN-`·`MVP-`, 브랜치 안에서만 쓰는 임시 이름. 이 번호는 각자의 시트 탭이 정본이다.

## 연결 표기

- 표·시트 칸 안에서 여러 ID는 ` · `로 잇는다(`D-191 · DEV-84`). 쉼표·줄바꿈을 쓰지 않는다.
- 이어진 번호 묶음 `DEV-66·67·69`, 범위 `DEV-50~52`는 검사기가 풀어 읽는다. 접두어가 다른 범위(`POL-01~POL-50`)는 양 끝만 센다.
- 문장에서는 ID를 그대로 쓰고 링크가 필요하면 정의 정본의 줄로 건다. `D-7`과 `D-07`은 같은 결정이다(시트 규칙, 한 자리는 선행 0).
- 결정이 다른 결정을 대체하면 대체되는 결정 첫머리에 `일부 대체: D-189`처럼 적는다.

## 코드·시험·커밋에 쓰는 법

- 코드 주석·docstring은 **왜**를 적는 자리에 ID를 괄호로 붙인다: `(DEV-73, D-175)`. 이미 있는 ID만 쓴다. 아직 없으면 먼저 정의(`--next`)한다.
- 시험이 가짜 판정을 만들 때도 `policy_id`는 정책 장부에 있는 값을 쓴다(`P-AUTHZ-ALLOW-001`, `P-X-APPROVAL-001`). 임의 이름은 정의 없는 참조로 잡힌다.
- 커밋 메시지는 제목 끝 괄호에 관련 ID를 적는다: `feat(v2): … (D-191 · DEV-84)`. 시트의 개발이력 탭이 이 번호로 결정·백로그·WBS를 연결한다.
- 룰셋 변경은 `policy_ledger.json`에 키를 추가하는 같은 커밋에서 rego·Python이 그 ID를 쓴다. 장부에 없는 ID는 오류다.
- 정정은 지우지 않고 옛 표기를 남긴다: `D-175(→ D-193으로 재번호, 10-22)`. 시점 보존 문서(`status/reports/`, `status/history-*`, `snapshot-before-*`)는 당시 번호를 그대로 두고 정정만 덧붙인다. 이 문서들의 정의 없는 참조는 오류가 아니라 경고다.

## 새 번호 받기

```powershell
python -B -X utf8 research/llm-wiki/tools/check_trace.py --next D      # 결정
python -B -X utf8 research/llm-wiki/tools/check_trace.py --next DEV    # DEV·WIKI·AIG·RM·OPS 중 접두어를 고른다
python -B -X utf8 research/llm-wiki/tools/check_trace.py --next G08    # 목표 G08의 다음 작업
```

계열 키는 `D DEV WIKI AIG RM OPS G## F POL E CMP OSS DEP DOC TH LR`다. 이 명령은 `git fetch`로 원격을 새로 받은 뒤 작업 트리·로컬 브랜치·`origin/*` 브랜치 끝점 전부의 정의 정본을 읽어 가장 큰 번호 + 1을 낸다(네트워크가 없으면 `--no-fetch`). 번호를 받으면 **그 자리에서** 정의 줄(제목이라도)을 쓰고 가장 먼저 푸시한다. 푸시 전에는 남이 같은 번호를 받을 수 있다. 번호를 받고도 정의를 늦출 사정이 있으면 아래 「예약」에 한 줄을 넣어 푸시한다.

10-22 사고(D-190 한 번호를 원격 브랜치 세 곳이 서로 다른 결정으로 정의)는 이 절차가 없던 탓이다. 병합하면서 겹친 번호를 발견하면 나중에 병합하는 쪽이 `--next`로 새 번호를 받아 옮기고 정정 표기를 남긴다.

## 예약·폐기

[reserved.md](reserved.md)는 정본에 정의가 없지만 번호를 잡아 둔 ID 표다. 검사기는 표의 ID를 정의된 것으로 보고 `--next`도 건너뛴다.

- 예약: 다른 브랜치에서 정의되어 아직 병합되지 않은 번호, 먼저 잡아 둔 번호.
- 제안: 문서가 제안했지만 구현하지 않은 정책 ID.
- 폐기: 지운 정책 ID. 다시 쓰지 않는다. 과거 감사 기록에는 남는다.
- 충돌: 서로 다른 뜻으로 이미 쓰인 번호. 쓰지 않는다.

정본에 정의가 들어오면 표의 줄을 지운다(두 곳에 있으면 중복 정의 오류).

## 검사기

```powershell
python -B -X utf8 research/llm-wiki/tools/check_trace.py              # 검사. 오류가 있으면 종료 코드 1
python -B -X utf8 research/llm-wiki/tools/check_trace.py -v           # 경고 전체
python -B -X utf8 research/llm-wiki/tools/check_trace.py --self-test  # 검사기 자체 시험
python -B -X utf8 research/llm-wiki/tools/check_trace.py --export     # 추적표 CSV 갱신(openpyxl 필요)
```

| 종류 | 내용 |
| --- | --- |
| 오류 | 중복 정의(같은 ID가 두 곳). 정의 없는 참조(예약표에도 없음). 형식 위반(`DEV-1`, `POL-100`, `D-007`). 정의의 형식 위반 |
| 경고 | 정의만 있고 참조가 0인 ID. 시점 보존 문서에만 나오는 정의 없는 ID. 정의 없는 `Enn`·`F-nn`(다른 뜻과 겹치기 쉬워 경고로만 본다) |

훑는 대상은 저장소의 문서·코드·룰셋 텍스트이며 원문 사본(`sources/`), 추출본(`threats/extracted/`), 시트 생성물(`sheet/`, 단 `sheet/seed/` 제외), 검사기 자신과 시험용 가짜 ID가 든 파일은 뺀다. 예외가 필요하면 `check_trace.py`의 `SKIP_FILES`·`HISTORY`에 한 줄을 넣고 이유를 주석으로 적는다. CI(`research-wiki.yml`)가 오류만 실패로 본다.

새 접두어를 만들 때는 같은 커밋에서 (1) `check_trace.py`의 `FAMILIES`와 정의 수집(`collect_defs`), (2) 이 표, (3) `build_sheet_export.py`의 `PATTERNS`(시트에 올릴 경우)를 함께 고친다.

## 추적표(시트 「추적」 탭)

`--export` 또는 `build_sheet_export.py`가 `research/llm-wiki/sheet/tabs/47-trace.csv`를 만든다. 열은 ID, 계열, 제목, 정의 위치, 참조 수, 참조 위치(파일 다섯 곳까지), 관련 ID(같은 줄이나 같은 절에 함께 나온 ID, 많이 나온 순 열 개)다. 구글 시트는 다른 참조 탭처럼 A1의 IMPORTDATA 주소를 새 커밋의 `tabs/47-trace.csv`로 바꿔 읽는다. `DOC-`·`DEP-` 행은 `manifest.json`을 읽으므로 내보내기를 한 번 더 돌려야 새 번호가 반영된다.
