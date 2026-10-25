# 2026-10-25 위키 구조·최신화 점검 (WIKI-08)

- 작업자: Claude Code(Sonnet 5.5, 세션 wiki-structure, 리더 지시서 S3)
- 코드 기준: main `7687a9e`(10-25 14:59), 브랜치 `claude/wiki-structure-332d12`. 제품 코드는 바꾸지 않았다. 변경 파일은 아래 「적용한 것」.
- 시작 근거: 소유자 지시(10-25) 「wiki 구조가 Opus나 서브에이전트들이 읽기 편한 구조이고, 협업을 위한 최신화가 잘 되어 있는지 체크하고 개선할 부분은 수정」
- 해결할 문제와 완료 조건: 새 에이전트가 5분 안에 ① 지금 상태 ② 규칙 ③ 자기 작업의 결정·보고서를 찾는가, 협업용 최신화가 도는가를 측정하고 구조를 고친다. 변경 전/후 읽기량 표, `check_wiki.py` 오류 0.

## 결과

**읽기량은 줄었고, 낡음을 재는 도구가 생겼다. 결정 기록 분할은 도구와 모의 실행까지 하고 실행은 하지 않았다(리더 몫).**

| 측정 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 새 에이전트가 읽는 필수 묶음(규칙+현황+열린 일) | 8파일·491줄·약 27,600토큰 | 6파일·308줄·약 8,950토큰 |
| 안내가 이어서 가리키는 설계 문서까지 | 12파일·1,208줄·약 48,500토큰 | 9파일·995줄·약 28,900토큰 |
| 결정 한 건을 찾는 비용 | `DECISIONS.md` 2,438줄·약 134,000토큰을 읽거나 grep | `lookup.py D-235` 출력 약 5.4KB, 색인 256줄(약 10,900토큰)에서 번호 검색 |
| 작업 ID의 보고서 찾기 | `status/reports/` 파일 185개를 열어 봄 | 보고서 색인 1파일에서 검색 또는 `lookup.py DEV-72` |
| 현황이 코드보다 늦은지 아는 법 | 없음(`check_wiki.py`는 안 봄) | `check_freshness.py` 10개 항목 |
| 코드 변경 뒤 생성물 재생성 | 커밋 메시지에만 있는 2개 명령(문서화 안 됨) | `refresh_generated.py` 한 명령, 15~20초 |

토큰은 한글 1.3자·기타 3.5자당 1토큰으로 어림한 추정값이다. 「변경 전」은 `HEAD`의 파일 그대로, 「변경 후」는 이 브랜치다. 후자의 필수 묶음은 백로그를 「먼저 볼 것」 블록(12줄)만 센 값이고, 루트 `CLAUDE.md`·`AGENTS.md`·위키 `AGENTS.md`는 Claude Code가 세션 시작에 자동으로 불러오는 파일이라 양쪽에 같이 들어 있다. **새 에이전트가 실제로 5분 안에 찾는지는 사람이나 새 세션으로 시험하지 않았다.** 읽기량과 경로의 측정이다.

## 점검 결과

### 1. 진입점 5개

| 파일 | 역할(의도) | 발견 |
| --- | --- | --- |
| 루트 `AGENTS.md`(102줄) | 규칙 정본 | 「원격 기본 브랜치는 `feat/2026-09-v3.1-field-deploy`」인데 `git ls-remote --symref origin HEAD`는 `main`(10-25 확인). 소유 S2, 리더·S2가 고칠 것 |
| 루트 `CLAUDE.md`(19줄) | AGENTS·위키 AGENTS를 불러오기 | 정상. 위키 README로 가는 안내 한 줄만 있고 읽는 순서는 없었다 |
| `docs/ai/README.md`(54줄) | 설계 문서 지도 | 표에 날짜가 붙은 과거 기록 문서가 섞여 있고(`docs/ai/` 안 `*_20*.md` 12개) 「처음이면 ARCHITECTURE → RUNBOOK → TESTING」만 안내. 결정·현황으로 가는 길이 없었다 → START_HERE 링크와 결정 색인 안내를 넣었다 |
| 위키 `README.md`(80줄) | 위키 첫 화면 | 「지금 상태 (2026-10-23)」 블록이 현황과 같은 수치·문장을 복제했고 10-25 변경을 몰랐다. 「주제별 입구」와 「전체 자료 지도」가 같은 링크를 두 표로 반복 |
| `status/current.md`(67줄) | 지금 상태 | 제목은 10-23인데 D-208까지만 인용(결정 기록은 D-237). 본문이 스스로 모순: 한 곳은 「W11 main 병합」, 다른 곳은 「W11 진행 중, 저장소에 브랜치가 없다」. AIG-02를 「미커밋」으로 적었으나 백로그 행은 main `2b289e1` 병합 |

모순 하나는 진입점 사이의 **순서**다. 루트 `AGENTS.md`는 `docs/ai/README` 우선, 위키 `README`는 현황→백로그, `docs/ai/README`는 ARCHITECTURE 우선이라 세 곳이 서로 다른 순서를 말했다. 순서는 START_HERE로 모았고 나머지는 거기를 가리킨다.

### 2. 같은 사실의 복제

| 사실 | 같은 값을 쓰는 곳(10-25 `HEAD`) | 정본 |
| --- | --- | --- |
| 진척률 63.3% | 위키 README·현황·백로그·WBS 근거 감사·시트 동기 보고 5곳. 감사 문서는 재계산 62.28%를 따로 적어 두 값이 공존 | 시트 「WBS」 탭 |
| WBS 57개 작업 | Markdown 11개 파일 | 시트 |
| 「되는 것·안 되는 것」 | 위키 README 블록, 현황, 백로그 「먼저 볼 것」, 시트 백로그 | 현황(서술)·백로그 행(근거) |
| 백로그 | `backlog.md` 102행, `sheet/pulled/03-backlog.csv` 74행(10-18), 시트 | 시트 상태, 저장소 근거 |
| 결정 | `DECISIONS.md` 222건, 시트 「결정」 198행(10-23 점검), 색인 없음 | `DECISIONS.md` |

복제 자체보다 복제본이 따로 낡는 것이 문제다. 조치: README의 지금 상태 블록을 걷어내고 링크로 대체했고 현황은 병합 사실·구분만 쓰고 수치는 시트로 보낸다(10-23 값이라는 표시를 붙여 남겼다).

### 3. 찾기 어려운 이름·깊이

- 위키 폴더 15개. `analysis/` 바로 아래만 77개이고 전체 하위 폴더 123개. 이름은 날짜·ID 접미(`review-1020`, `local-endpoints-1021`, `gap-matrix-1023`)라 폴더 이름만으로 내용을 알 수 없다. 이 위키는 이름이 아니라 색인으로 찾아야 한다 → 보고서·결정 색인과 `lookup.py`.
- 파일 1,596개(`sources/` 150·`papers/` 295·`analysis/` 710 등). Markdown 문서 742개(`check_wiki.py` 집계), 줄 수는 `sources/` 129,413줄이 대부분이며 읽는 용도가 아니다.
- 보고서 185파일 중 Markdown 162개, 나머지 23개는 JSON·JSONL·패치 증거. 제목이 `2026-10-23 …`로 날짜를 반복하고 「첫 문장」이 작업자·코드 기준 같은 양식 줄인 보고서가 다수라 색인 도구가 양식 줄을 건너뛴다.
- 결정 번호는 시간순이 아니다. 헤딩 번호 순서가 거꾸로 가는 곳 13쌍(예: D-232 다음 D-230), 빈 번호 15개(D-36~38·D-160·D-162~169·D-171·D-174·D-190). 예약 표(`trace/reserved.md`)에 있는 것은 일부뿐이다.

### 4. `DECISIONS.md` 읽기 비용

2,438줄·279,338자(한글 112,424자)·약 134,000토큰. 헤딩 222개. 10-18 이후 이 파일을 건드린 커밋 176개, 모든 세션이 **파일 끝에 덧붙이는** 구조라 세션 둘 이상이 병렬이면 같은 꼬리에서 병합 충돌이 난다(이번 S1·S2도 같다). 한 파일을 번호대별로 나누면 읽는 양은 줄지만 충돌은 같은 번호대에서 남는다.

### 5. 최신화

| 항목 | 상태 |
| --- | --- |
| `current.md`·`backlog.md`가 마지막으로 코드와 맞은 시점 | 둘 다 10-23 20:47(`9f3d67e`). 그 뒤 제품 코드 커밋 25개, 결정 D-230~D-237 병합. `check_freshness.py`로 측정 |
| 백로그 블록 | 「먼저 볼 것 (2026-10-23)」과 상태별 건수는 101행 기준이며 표는 102행 |
| 시트 ↔ 위키 | `sheet_pull.py`는 사람이 돌리는 도구이고 설정(`collaboration-console/runtime/sheet-source.json`)이 로컬 전용이라 CI·정기 실행이 없다. `sheet/pulled/*.csv`는 10-18 값(백로그 74행, 저장소 표 102행과 29행 차이: DEV-72~89·AIG·OPS·WIKI-04~07 등) |
| 협업 웹 | 게시 CSV를 5분 캐시로 읽는다(10-23 점검). 이번에 다시 확인하지 않음 |
| `build_sheet_export.py --check` | 불일치: `tabs/33-ent-requirements.csv`, `37-integration-cases.csv`, `45-docs.csv`, `47-trace.csv`, `README.md`, `manifest.json`, `integrity.json`. 37번 등은 내가 만든 파일과 무관하게 이미 어긋난 상태였다 |
| 코드가 바뀌면 | 위협 매핑·요구사항·연동 조건의 코드 해시를 다시 만들어야 CI가 통과한다. 이 절차는 어느 문서에도 없고 보고서 4건·커밋 메시지에만 있었다. 10-18 이후 비병합 커밋 390개 중 **62개(16%)가 이 재생성만 담은 커밋**이고, 위키·문서 전용 커밋은 154개(39%) |

### 6. `check_wiki.py`가 못 잡는 낡음

`check_wiki.py`는 출처·해시·링크·실험 상태를 본다. 다음은 안 본다: (a) 현황·백로그 기준일이 코드·결정보다 늦은 것, (b) 현황이 인용한 최신 결정 번호, (c) 현황 이후 쓰인 보고서, (d) 시트 당겨오기 사본의 나이, (e) 색인류가 소스와 어긋난 것, (f) 진입점 문서끼리의 순서 모순. (a)~(e)는 `check_freshness.py`가 이제 잰다. (f)는 사람이 판단해야 해서 도구화하지 않았다.

## 적용한 것

| 구분 | 파일 | 내용 |
| --- | --- | --- |
| 진입점 | `START_HERE.md`(신규) | 5분 경로, 하려는 일별 읽을 것, 진행 중 세션 4개와 브랜치, 정본 지도, 마칠 때 체크리스트 |
| 도구 | `tools/lookup.py` | ID 하나로 백로그 행·결정·보고서 |
| 도구 | `tools/build_report_index.py` → `status/reports/README.md` | 보고서 162개를 날짜·제목·첫 문장·관련 ID로 색인. `--check`, `--find` |
| 도구 | `tools/split_decisions.py`, `tools/decisions_layout.py` → `status/decisions-index.md` | 결정 색인 생성·`show D-n`·분할 `split --write`(실행 안 함, 계획만)·`check`. 분할 뒤 `DECISIONS.md#d-N` 앵커 링크도 번호대 파일로 돌린다 |
| 도구 | `tools/check_freshness.py` | 위 「못 잡는 낡음」 (a)~(e). 기본은 경고만, `--strict`이면 실패 |
| 도구 | `tools/refresh_generated.py` | 위협 매핑·요구사항 코드 위치·스냅샷·두 색인 재생성과 세 검사를 한 번에 |
| 호환 | `tools/check_trace.py`, `tools/build_sheet_export.py` | 결정 기록이 단일 파일이든 번호대 파일이든 읽는다(현재 동작은 그대로) |
| 정리 | `README.md`(위키) | 지금 상태 블록·「이어서 작업하려면」 삭제, 수치 복제 제거, 입구 표에 색인 행 추가 |
| 정리 | `AGENTS.md`·`CLAUDE.md`(위키), `docs/ai/README.md`, `trace/README.md` | 시작 순서를 START_HERE로, 생성물 재생성 명령 추가, 결정 정본 경로 설명 |
| 현황 | `status/current.md` | 10-25 기준으로 다시 씀: 병합 사실(D-230~D-237)·병합 전 브랜치·진행 중 세션·확인하지 않은 것. 10-23 원본은 `status/history/2026-10-23-current.md`로 보존(링크 경로만 조정) |
| 현황 | `status/backlog.md` | 「먼저 볼 것」을 10-25로: AIG-02 병합 사실 정정, 읽는 법, WIKI-08 행 추가 |

생성물(`catalogs/threats.json`, `analysis/enterprise*`, `analysis/requirements.json`, `analysis/integration-cases.json`, `status/repository-snapshot.*`)은 수정하지 않았다. `refresh_generated.py`를 시험 삼아 돌렸을 때 바뀐 4개 파일은 `git checkout`으로 되돌렸다. `.github/**`, `docs/ai/DECISIONS.md`, `status/reports/2026-10-25-*`(다른 세션 파일)도 건드리지 않았다.

## 검증

| 확인 종류 | 명령·환경 | 결과 |
| --- | --- | --- |
| 정적 검사 | `pyflakes`(신규·수정 도구 8개) | 오류 0 |
| 위키 | `check_wiki.py --ci-ignored-local-sources` | 오류 0(마지막 실행 결과는 아래 최종 확인) |
| ID 추적 | `check_trace.py`, `--self-test` | 오류 0, self-test PASS |
| 기업 분석 | `check_enterprise_analysis.py`, `test_enterprise_code_refresh.py` | 통과 |
| 협업 콘솔 | `research/collaboration-console/test_console.py` | 32개 통과 |
| 색인 | `build_report_index.py --check`, `split_decisions.py index --check` | 최신 |
| **분할 모의 실행** | 커밋 뒤 `split --write` → 위 검사 전부 → `git checkout`으로 원복 | 아래 |

분할 모의 실행(이 작업 트리에서만, 되돌림): 222건을 5개 파일(47·50·50·38·37건)로 나눴고 분할 전후 본문이 한 건도 다르지 않았다(`split`이 자체 비교). 그 상태에서 `check_trace.py`(오류 0), `check_enterprise_analysis.py`, `test_enterprise_code_refresh.py`, 협업 콘솔 시험이 통과했고 `check_wiki.py`는 당시 아직 없던 이 보고서 링크 외 오류가 없었다. `docs/ai/FIELD.md`·`POLICY.md` 등 8개 앵커 링크가 번호대 파일로 바뀌었고 두 번째 실행은 0개(멱등). `build_sheet_export.py --check`는 `45-docs`·`47-trace`·README·manifest·integrity가 다시 만들라고 한다(예상된 결과이며 「결정」 탭은 불일치가 아니었다).

시험하지 않은 것: 실제 새 에이전트·사람이 5분 안에 찾는지, `refresh_generated.py`를 CI에서 돌렸을 때, 윈도우가 아닌 환경(CI는 Linux 3.12)의 줄바꿈 차이 외의 동작, 분할 뒤 `gap-matrix-1023/build.py` 재실행.

## 실패·미완료·한계

- `docs/ai/DECISIONS.md` 분할은 지시대로 실행하지 않았다.
- 이 브랜치에는 238번 결정이 없다(`10/25-policy-sync-split`에만). 그래서 START_HERE·현황이 D-238을 ID로 인용하지 못한다(`check_trace`가 정의 없는 참조로 본다). 병합 뒤 「238번 결정」을 `D-238`로 바꾼다.
- START_HERE의 세션 표는 리더 지시서와 `list_sessions`를 옮긴 것이다. 세션이 끝나거나 바뀌면 사람이 고친다(자동화하지 않음).
- `status/reports/README.md`는 지금 있는 보고서만 센다. 다른 세션이 올 `2026-10-25-*` 보고서는 색인에 없다 → 병합 뒤 `refresh_generated.py`.
- `analysis/gap-matrix-1023/` 문서는 `DECISIONS.md#L줄` 링크와 줄 근거를 쓴다. 분할 뒤에는 그 줄이 없다. 역사 자료로 두고 `build.py`를 다시 돌릴 때 `decisions_layout`을 쓰게 고쳐야 한다.
- 시트(구글)는 읽지도 쓰지도 않았다. 시트 갱신은 리더 몫이다.

## 리더가 할 것

### 1. 병합 뒤 순서(S1·S2 병합이 끝난 다음)

```bash
python research/llm-wiki/tools/split_decisions.py split            # 계획 확인
python research/llm-wiki/tools/split_decisions.py split --write    # 분할 + 색인 + 앵커 링크 수정
python research/llm-wiki/tools/split_decisions.py check
python research/llm-wiki/tools/refresh_generated.py                # 색인·코드 해시·검사
python research/llm-wiki/tools/build_sheet_export.py               # 시트 내보내기 다시 만들기
python research/llm-wiki/tools/build_sheet_export.py --check
```

그 뒤 손으로: (1) `START_HERE.md`·`current.md`의 「238번 결정」을 `D-238`로, 세션 표를 정리, (2) `docs/ai/README.md`의 DECISIONS 행에 「번호대 파일은 `decisions/`」 한 줄, (3) 루트 `AGENTS.md`의 「결정을 내리면 `DECISIONS.md`에」 문장은 그대로 둬도 된다(안내문이 `decisions/`로 보낸다), (4) 새 결정은 가장 큰 번호대 파일 끝에 쓰고 50개를 넘으면 `split --write`가 새 파일을 만든다. 분할은 이 경로에 의존하는 도구(`check_trace`, `build_sheet_export`)를 이미 두 구조 모두 읽게 해 둔 상태에서 한다.

### 2. CI 줄 제안(`.github/workflows/research-wiki.yml`, 내가 수정하지 않음)

```yaml
      - run: python research/llm-wiki/tools/build_report_index.py --check
      - run: python research/llm-wiki/tools/split_decisions.py index --check
      - run: python research/llm-wiki/tools/split_decisions.py check      # 분할 뒤에만 의미 있음
      - run: python research/llm-wiki/tools/check_freshness.py             # 경고만, 실패하지 않음
```

주의: 앞의 두 줄은 보고서·결정을 추가한 커밋이 색인을 다시 만들지 않으면 CI를 깨뜨린다. 지금도 코드 커밋의 16%가 해시 재생성인 상황에 실패 지점을 더하는 것이므로, `refresh_generated.py`를 전 에이전트 규칙(위키 `AGENTS.md`에 이미 넣음)으로 정착시킨 뒤에 추가하길 권한다. 먼저 `check_freshness.py` 한 줄만 넣어도 된다.

### 3. 다른 세션·파일에 전할 것

- 루트 `AGENTS.md`(S2 소유): 원격 기본 브랜치 서술을 `main`으로, 「먼저 읽을 것」 맨 위에 `research/llm-wiki/START_HERE.md` 한 줄.
- S1: 위키 해시 재생성은 `python research/llm-wiki/tools/refresh_generated.py`(이 브랜치가 병합돼야 있다). 병합 전에는 기존대로 `map_threats.py` + `build_enterprise_analysis.py --refresh-code-only`.
- 시트: 「결정」·「개발이력」·「자료」·「백로그」(WIKI-08 행, DEV-72~89 누락분 확인) 갱신, `sheet/pulled/` 다시 당겨오기.

## 방향 제안

1. **생성 해시를 커밋하지 않는 쪽으로**: 코드 변경 커밋의 16%가 해시 재생성이다. 코드 위치·해시를 CI가 매번 계산해 비교하는 도구로 바꾸거나(저장 안 함), 병합 드라이버로 생성물은 항상 재생성 값을 택하게 하면 병합 충돌과 CI 실패가 함께 줄어든다. 이번에는 구조만 건드리는 범위라 제안으로 남긴다.
2. **결정은 파일당 한 건**(`decisions/D-238.md`)이 병렬 세션에 가장 안전하다. 번호대 분할은 읽기 비용만 줄이고 추가 충돌은 남는다. 분할 도구를 쓴 뒤 충돌이 계속되면 다음 단계로 둔다.
3. **백로그 행에서 서술을 빼기**: 행이 길어(124줄에 약 16,700토큰) 표 전체를 읽을 수 없다. 상태는 시트, 서술은 보고서로 보내고 행은 ID·작업·완료 조건·한 줄 상태·링크만 두면 표가 1/4로 준다. 시트가 정본이라는 결정과 맞다.
4. **시트 당겨오기 자동화**: 게시 CSV는 공개 URL이라 CI/정기 작업으로 `sheet_pull.py`를 돌릴 수 있다. 지금 설정이 로컬 `runtime/`에 있어 못 돈다. 설정을 환경 변수로 받게 하면 7일 지연이 사라진다.
5. **세션 표 자동화**: START_HERE의 세션 표를 협업 콘솔 기록(`console.py emit`)에서 생성하면 사람이 고칠 곳이 하나 줄어든다.

## 다음 작업

WIKI-08 백로그 행의 남은 일: 분할 실행, CI 줄, 시트 갱신, 방향 제안 1~3 중 리더가 고른 것.

## 사용자에게 필요한 입력

없음. 분할 실행 시점과 CI 줄 추가는 리더 판단.
