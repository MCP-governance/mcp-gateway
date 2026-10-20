# 2026-10-20 DEV-02 계약 오염 정규화 후보·보류 평가 규율

- 작업자: Codex sol
- 코드 기준: 브랜치 `10/20-poisoning-corpus`, 시작 `1c7edc9c7320a4f54ee41e9f058d7d8debd31e20`, 시작 작업 트리 깨끗함. 커밋·푸시 없음. 원격 HEAD 조회는 GitHub 연결 실패로 미확인.
- 변경 파일: `full_stack_lab/gateway/app/poisoning.py`, 새 `full_stack_lab/tests/poisoning_corpus_check.py`, D-158, 이 보고서, DEV-02 마지막 상태 칸, `analysis/poisoning-d158/` 정본과 로컬 결과, `catalogs/threats.json` 재생성.
- 시작 근거: DEV-02, [10-15 측정](2026-10-15-inspection-corpus.md), D-100/D-101의 좁은 결과 규칙·공개 코퍼스 분할 규율.
- 해결할 문제와 완료 조건: 계약 오염 재현율 증가와 정상 오탐 0을 같은 분할에서 검증한다. 현재는 구현 후보·로컬 회귀까지 진행했으며 공개 dev/held-out 검증과 필수 pyflakes 검사가 남아 **수용 완료가 아니다**.

## 결과

계약 검토에만 ROT13·역순·글자 띄우기·leetspeak를 해독해 기존 규칙으로 다시 읽는다. 설명·입력 스키마 모두에 적용되고 결과 보류·인자 검사는 유지한다. 새 정책·DB·의존성·외부 모델 호출·자체 MCP 서버는 없다. 원문과 기존 탐지 결과도 유지한다.

새 시험 파일은 순수 회귀와 공개 코퍼스 비교 CLI를 제공한다. 기존 평가기의 builder·텍스트 해시 분할을 재사용하며 원문 189개의 고정 URL·바이트 수·SHA-256과 표본 수를 검증한다. dev 원문만 열람할 수 있고 마지막 held-out 비교는 동결 지문·dev 수용 조건·1회 사용 기록으로 보호한다. 기존 시험 기대값은 수정하지 않았다.

**공개 수치를 이번에 재현하지 못했다.** 캐시가 없고 다운로드는 `WinError 10013`으로 실패했다. dev CLI도 첫 캐시 파일 누락으로 비정상 종료했고 결과 파일·held-out 소비 기록은 생성되지 않았다. 공개 dev 미탐은 0건 열람, held-out 채점도 0회다. MCPTox 표현 규칙은 dev 자료 없이 확대하지 않았다. 같은 작성자의 합성 회귀는 공개 dev 개선 근거로 쓰지 않는다.

| MCPTox 분할 | 과거 TP/FN/FP/TN | 과거 재현율·정밀도 | 이번 기준/개선 후 재현율·정밀도·오탐 |
| --- | --- | --- | --- |
| dev | 152/136/0/197 | 0.5278 / 1.0000 | 미측정 / 미측정 |
| held-out | 102/95/0/145 | 0.5178 / 1.0000 | 미측정 / 미측정(채점 0회) |

과거값은 [10-15 JSON](2026-10-15-inspection-corpus-results.json)의 `totals_after`이며 이번 기준 실행값이 아니다. [분석 정본](../../analysis/poisoning-d158/README.md)에 공개·로컬 표, 유형별 실패·한계, OSS/스킬 검색·고정 판본·라이선스, 원자 요구사항→호출자→시험→효과와 재현 명령을 남겼다.

실행한 로컬 비교는 같은 작성자의 합성 공격 4개에서 0/4→4/4, 정상 28개에서 오탐 0→0이다. 재현율 0→1, 정밀도 미정의→1이며 독립 검증이 아니다. 실제 OSS 도구 스키마 저장소 사본 92개(ghidra·git·sqlite·blender·playwright)의 오탐은 0→0. 요청된 github·context7·markitdown의 설명·스키마 사본은 없으므로 해당 3종 검증은 미실행이다. [로컬 원본 집계](../../analysis/poisoning-d158/local-results.json).

## 검증

실행일은 2026-10-20 KST. 기본 Python 3.10의 `re._parser` 지원 제약을 피하기 위해 준비된 Codex 런타임 CPython 3.12.14를 사용했다. 제품의 임포트나 스캐너를 대역으로 바꾸지 않았다.

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 순수 회귀 | Python 3.12.14 `full_stack_lab/tests/poisoning_corpus_check.py` | 9/9 통과: 설명·스키마 해독, 정상군, 결과/인자 범위, 20만자 경계, 지표·검사기 실패, 보류 동결/동시 사용·재사용 거부, 캐시 부재·해시 불일치 실패 | 새 시험 파일, CLI 출력 |
| 기존 자체 점검 | Python 3.12.14 `full_stack_lab/gateway/app/poisoning.py` | `poisoning self-check OK`(기존 기대값·병리 입력 시간 제한 유지) | 기존 파일 직접 실행 |
| 로컬 전후 비교 | `poisoning_corpus_check.py --evaluate local` + 시작 커밋 파일 | 통과, 합성 TP 0→4·FP 0→0, OSS 92개 FP 0→0 | [JSON](../../analysis/poisoning-d158/local-results.json) |
| 공개 dev 재현 | `poisoning_corpus_check.py --evaluate dev` | 실패: 캐시 `fb8f78f378e39b97a32e58f6` 없음, 성공 결과 미생성 | `FileNotFoundError`, 종료 1 |
| Python 구문 | Python 3.12.14 `-m py_compile` 변경 Python 2개 | 통과 | 종료 0 |
| JavaScript 구문 | `node --check full_stack_lab/gateway/app/agent_static/console.js` | 통과 | 종료 0 |
| CI pyflakes | `cd full_stack_lab` 뒤 지정된 `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` | 미완료: `No module named pyflakes`, 새 경고 수 미검증 | 종료 1; WSL도 `E_ACCESSDENIED` |
| 위협 매핑 | `python research/llm-wiki/tools/map_threats.py`(3.12.14) | 24개 재생성 통과 | `catalogs/threats.json` |
| 위키 | `check_wiki.py --ci-ignored-local-sources` | 오류 0; Git 제외 원문 부재 경고 유지 | `ok=true`, `errors=[]` |
| 공백·인코딩 | `git diff --check`, 변경 파일 UTF-8(BOM 없음)·LF 검사 | 통과 | 종료 0, 바이트 검사 |

최종 내용 대조에서 PowerShell 파이프의 한글 손실과 그 문자열 치환으로 인한 DEV-61 숫자 변경을 발견했다. DEV-61은 시작 커밋과 같게 복원했고 새 D-158·DEV-02 상태는 `apply_patch`의 UTF-8 원문으로 교정했다. 백로그는 DEV-02 마지막 칸만 바뀌었는지, 결정 문서는 기존 본문이 보존되는지 별도 대조했다.

## 실패·미완료·한계

- 공개 dev 재실행·미탐 유형 분류·실제 운영 3종 정상군·마지막 held-out 비교는 미완료다. 정상 오탐 0과 MCPTox 재현율 개선의 최종 수용 조건을 아직 충족했다고 주장하지 않는다.
- 과거 인코딩 결과 112/182 및 잔여 70/182는 결과 경로 수치다. 새 해독은 계약 전용이므로 그 수치 개선으로 바꾸지 않았다. 복합 인코딩·의역·독립 한국어 코퍼스·의미 분류기는 미해결이다.
- 계약 검토당 최대 4회 추가 스캔 비용이 생긴다. 기존 병리 입력 시간 제한은 통과했지만 네이티브 성능·큰 카탈로그의 지연·자원 경계는 기기 검증이 남았다.
- Python 네이티브 엔진 동등성, 이미지, 실제 MCP/프로토콜·하네스·업스트림 효과·배포·정책 해시 확인은 미실행이다. 로컬 스키마 판정은 운영 효과 증거가 아니다.
- held-out 1회 기록은 동일 dev 보고서의 실수 재채점을 막는 절차 통제다. 운영자의 기록 삭제·복제까지 강제할 수 없으므로 독립 실행 기록이 필요하다.

## 기존 시험 변경 필요

없음. 기존 시험 파일·기대값을 수정하지 않았고 기존 자체 점검을 통과했다. 필수 pyflakes 검사는 도구 부재로 검증하지 못했으므로 사람의 동일 명령 실행이 남는다.

## 다음 작업

DEV-02 상태를 공개 수용 검증 대기로 둔다. [기기 재현 순서](../../analysis/poisoning-d158/README.md#재현-순서솔루션-기기)에 따라 원문 캐시를 복원해 dev부터 비교하고, dev 규칙 보강·운영 정상군 검토 후 코드를 동결해 held-out을 마지막에 한 번 실행한다. 기기에서 `tests/poisoning_corpus_check.py`, 기존 `tests/textscan_parity_check.py`, 지정 CI pyflakes를 실행한다. 별도 스택이나 mock MCP를 띄우지 않는다.

## 사용자에게 필요한 입력

새 업무 권한·실사용 데이터 결정은 없음. 검증 환경에 고정 원문 캐시 189개, 평가용 PyYAML, CI pyflakes, github·context7·markitdown의 실제 도구 설명·스키마 사본이 필요하다. 비밀값은 기록하거나 요구하지 않는다.

## 기기 확인 (Claude, 2026-10-20)

- 운영 서버 도구 31개(context7·github·markitdown 등) 설명에 새 규칙을 적용해 발견 0(오탐 0). 공개 코퍼스 재현율은 원문 캐시가 없어 미측정 — 다음 작업.

## 공개 코퍼스 실측 (Claude, 2026-10-20)

WSL에서 `inspection_corpus_eval.py build`(9,463건, dev 5,679)로 표본을 다시 만들고 솔루션 기기 게이트웨이 이미지에서 `run`을 D-158 이전(7e125a3^1)·이후(main)로 실행했다.

| 경로 | 분할 | D-158 이전 | D-158 이후 |
| --- | --- | --- | --- |
| catalog(MCPTox) | dev | 재현율 0.5278, 오탐 0 | 0.5278, 0 |
| catalog(MCPTox) | held-out | 0.5178, 0 | 0.5178, 0 |
| catalog 평균 지연 | — | 0.215·0.233 ms | 0.294·0.323 ms(약 +37%) |

- D-158 해독 후보 4종은 이 코퍼스에서 재현율 변화가 없다(놓친 사례에 해당 인코딩이 없음). 카탈로그 갱신 때만 돌므로 유지하고, 효과 없음으로 기록한다.
- 별도 발견: result 경로 오탐 66건(fp_rate 3.3%) — 10-15 보고의 0과 다르다. pokeapi BOM 접두 파일 20/20, pokeapi JSON 응답 20/88, cpython 코드 파일 18/30, 문서 페이지 일부. 이후 추가된 응답 상한·인코딩 검사와의 충돌로 보이며 원인 분류를 다음 작업으로 둔다.

