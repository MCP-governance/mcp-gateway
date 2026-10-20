# 2026-10-20 T5 선언 한계·섀도 MCP 통제 분석

- 작업자: Codex luna
- 코드 기준: `10/20-shadow-controls`, 시작 `ab3ac29a08e992d605502be87656dde8a201981d`, 작업 시작 시 변경 없음. 분석 문서와 보고서만 추가.
- 시작 근거: T5 작업 지시, [통제 방향 검토](../../analysis/direction-1020/control-review.md), [위키 백로그](../backlog.md), `docs/ai/ARCHITECTURE.md`, `SECURITY_BOUNDARIES.md`, `POLICY.md`, `DECISIONS.md` D-155·D-170.
- 해결할 문제와 완료 조건: 도구 행위 분석과 선언 계약 고정의 한계를 코드 행 근거로 명시하고, 보완 수단의 범위, 섀도 MCP 유형별 발견·차단·표시 경계와 기기 검증 여부를 정리한다.

## 결과

[분석 정본](../../analysis/direction-1020/shadow-and-declaration-limits.md)에 선언 계약의 한계, DEV-38·DEV-73·D-155·DLP/poisoning·출력 계약·변경 경보·SBOM의 잡는 것/못 잡는 것, 6종 섀도 MCP 유형별 발견·차단·표시 근거를 표로 정리했다. 판본만 바뀐 경우 승인 설명·입출력 스키마가 같으면 자동 승계될 수 있고, 새 도구 목록 차이는 경보 대상이나 즉시 서버 전체 차단으로 과장할 근거가 없음을 기록했다. `control-review.md`의 방향과 다른 제안은 없으며, 등록 장치 보고 범위 밖의 계정·복사본은 D-170 조직 통제 의존으로 남겼다.

## 검증

| 확인 종류 | 명령·환경·실행 시각 | 결과 | 원본 증거 |
| --- | --- | --- | --- |
| 코드 근거 읽기 | Python UTF-8 읽기 스크립트로 `registry.py`, `core.py`, `selective.py`, `endpoint_plane.py`, `mcp_facade.py`, `server_egress.py`, `ops_response.py`, `integrations.py`, 엔드포인트 수집기 확인 | 문서의 경로·함수·행 기준으로 반영. 런타임 실행 아님 | 새 분석 문서 §1–4 |
| 기존 현장/실기기 보고 확인 | `2026-10-14-e13-local-mcp-natural-language.md`, `2026-10-15-endpoint-evidence.md`, `2026-10-20-user-command-settings.md` 읽기 | 각 보고서의 당시 범위·미완료 경계를 인용. 현재 브랜치 배포 증거로 쓰지 않음 | 각 링크 및 새 분석 표 |
| 위키 검사 | `python -B -X utf8 research/llm-wiki/tools/check_wiki.py --ci-ignored-local-sources` | 통과, 오류 0. 무시된 `local-sources/` 원본 누락 경고는 남음 | 실행 결과 |
| 정적 스타일 | `cd full_stack_lab && python -m pyflakes gateway/app/*.py tests/*.py supply_chain/*.py ../endpoint-agent/*.py field/pc/mcpgw_pc.py` | 미실행: Python 환경에 `pyflakes` 모듈 없음. 코드 변경은 없음 | 실행 결과 |
| 변경 공백 | `git diff --check` | 통과. 새 문서는 위키 검사에서 링크/문서 목록 대상 확인 | 실행 결과 |
| 새 시험·실기기·배포 | 미실행 | 문서 읽기 전용 분석 | 해당 없음 |

## 실패·미완료·한계

- 문서 분석 작업이며 현재 솔루션 기기 배포나 PJ1 검증은 하지 않았다.
- 결과 출력 검사 호출부 행은 이번 대조에서 정확한 호출 행을 고정하지 못해 본문에 생략 경계로 적었다. 해당 위치를 확정한 것으로 가장하지 않는다.
- SBOM 구현 경로와 현재 fleet 적용 여부는 별도 코드 대조를 하지 않았다. 방향 문서의 DEV-76 제안/검토 상태로 한정했다.
- backlog에 T5 ID가 없으므로 갱신할 기존 ID 행을 찾지 못했다. `status/current.md`는 작업 지시에 따라 변경하지 않았다.
- 기존 시험 변경 필요: 없음. 코드·시험·정책 변경이 없으므로 D-번호를 추가하지 않았다.

## 다음 작업

T5 분석 산출물을 기능 검토 기준으로 사용한다. DEV-73·DEV-76의 구현/시험이나 섀도 발견 채널의 실기기 범위 확장은 별도 승인된 작업과 기기 검증에서 다룬다.

## 사용자에게 필요한 입력

없음.
