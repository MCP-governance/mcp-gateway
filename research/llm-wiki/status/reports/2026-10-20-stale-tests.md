# 2026-10-20 오래 실패한 시험 분류
- 작업자: Codex luna
- 코드 기준: `a7aa43a1970333a28aaf9050ebaa476d8673c098`, 시작 시 작업 트리 clean, 브랜치 `10/20-stale-tests`
- 시작 근거: 사용자 제공 10-20 이전 기준 commit `8983311`에서도 동일했던 16개 게이트웨이 이미지 실행 실패 로그
- 해결할 문제와 완료 조건: 파일별 환경 의존·오래된 시험·제품 회귀를 근거로 분류하고, 환경 의존 목록을 TESTING 문서에 추가하며, 기대값을 바꾸지 않는 시험 대역 보정 제안을 분석 문서로 남긴다. 코드·시험은 수정하지 않는다.

## 결과

16개 중 환경 의존 13개, 기존 제품 계약 변경을 반영하지 못한 대역 3개, 확인된 제품 회귀 0개로 분류했다. (b) 세 건은 최소 제안 diff만 보고서에 기록했다. 게이트웨이 제품 코드와 시험 파일은 수정하지 않았다. 분류·근거·한계·diff는 [분석 결과](../../analysis/stale-tests-1020/README.md)에 있다.

`docs/ai/TESTING.md`에 “게이트웨이 이미지 단독 실행 대상 아님” 표를 추가했다. 기존 TESTING 설명과 각 파일 상단 설명, `console.sh test` 호출 구성을 근거로 환경 요건을 연결했다.

백로그에는 이번 작업을 대표하는 ID가 없어 상태 칸을 수정하지 않았다. `status/current.md`도 요청대로 수정하지 않았다.

## 검증

| 검증 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 정적 소스·이력 대조 | 파일 설명·호출부·제품 심볼·git blame/log, 로컬 읽기 전용, 2026-10-20 | 완료; 16개 분류와 D-123/D-149 경로 확인 | `analysis/stale-tests-1020/README.md` |
| Python 정적 검사 | `cd full_stack_lab`; `python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` | 실패: 현재 Python 3.10 환경에 `pyflakes` 모듈이 없음 | 터미널 출력: `No module named pyflakes` |
| 위협 매핑 | Gateway·endpoint 코드 미변경 | 해당 없음 | 이번 문서 전용 변경은 실행 조건 아님 |
| 위키 CI 검사 | `python research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 성공, `errors: []`; 누락 ignored local-sources 경고 유지 | 명령 JSON 출력 |
| 산출물 인코딩 | 추가·수정한 Markdown 3개 UTF-8 BOM/LF 확인 | 통과 | 모두 no-BOM, LF-only |
| gateway 이미지·실제 랩·PJ1 | 이번 문서/분류 작업 범위 | 미실행 | 사람의 적대 검증 및 기기 실행 필요 |
| 원격 기본 브랜치 확인 | `git ls-remote --symref origin HEAD` | 네트워크 연결 거부 | 분석 결과에 한계 기록 |

## 실패·미완료·한계

기기 로그에 정확한 서비스 상태와 JSON-RPC 오류 본문이 없어 production 런타임 회귀 여부를 독립 재현하지 않았다. 분류는 저장소 코드·설정과 제공된 로그로 제한한다. `pyflakes`는 현재 PC의 Python 3.10에 없어 실행되지 않았다. `oauth_rotation_check.py`, `protocol_versions_check.py`, `system_metrics_check.py`는 Codex sol 적대 검토 뒤에만 대역을 고친다.

Codex sol 적대 검토에서 제안의 폐기 파일 격리 누락, Markdown diff의 역슬래시 개수, 프로토콜 시험의 `/app` import 우선과 baseline 이미지 판본 불확실성을 지적했다. 분석 문서의 제안을 보완했다. protocol 시험은 현재 HEAD의 대역 불일치는 확인했지만, 제공된 이전 로그의 원인은 확정하지 않았다.

## 다음 작업

- Codex sol이 (b) 세 건의 diff와 기대값 불변 여부를 적대 검토한다.
- 적대 검토 승인 이후 별도 허가된 시험 수정 작업에서 대역을 보정하고, 새 파일 시험 정책에 맞게 검증한다.
- (a) 항목은 표에 연결된 격리 랩·VM·계정 절차에서 실행한다.

## 사용자에게 필요한 입력

없음. 공급자·field 시험 자격은 이 조사에서 요구하거나 기록하지 않았다.
