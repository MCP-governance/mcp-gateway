# 도입 한 화면 승인 — 구현·근거·검증 범위

기준 `217da74ed4731eb006ce3c167b17fec835b66155`, 브랜치 `10/20-intake-one-click`, 담당 Codex sol. 2026-10-20 소유자 지시를 구현했다. 기존 시험 기대값 충돌을 확인한 뒤 제품 코드 변경을 중단했으며 전체 회귀·배포 완료가 아니다.

- [원자 요구사항과 코드·시험 연결](requirements.json)
- [실행 명령·시각·종료 코드·표준 출력/오류](verification.json)
- [작업 보고·전후 화면 항목·기기 시험·기존 시험 변경 필요](../../status/reports/2026-10-20-intake-one-click.md)
- [설계 결정 D-184~187](../../../../docs/ai/DECISIONS.md)

## 재사용과 출처

| 자료 | 판본·확인 범위 | 실제 적용·제약 |
| --- | --- | --- |
| [MCP Tools 명세](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | 2025-11-25 고정 명세의 도구 목록·스키마·annotations와 사람 확인 문구, 10-20 웹 본문 확인 | SDK의 전체 도구 목록과 기존 계약 해시 재사용. annotations는 신뢰할 수 없는 힌트이므로 자동 승인이 아니다 |
| [ToolHive OSS](https://github.com/stacklok/toolhive)·[기존 판본 분석](../../solutions/toolhive-runtime.md) | Apache-2.0, v0.54.0 태그 `1ce13bbbbbe1ed9a3f40fea03ed1a42533f04cea`. 10-20 공개 검색에서 프로젝트·레지스트리 자료를 재확인. 이번에 소스를 새로 클론하거나 유지보수 전체 이력을 검사하지 않음 | 등록 메타데이터와 실행 경계를 비교했으며 의존성·실행 코드로 도입하지 않음. 외부 런타임을 승인/정책 엔진 대체로 쓰지 않음 |
| [공개 ToolHive 스킬 검토 이력](../../solutions/toolhive-runtime.md) | 기존 위키의 고정 스킬 검토를 재사용. 이번 고정 raw SKILL URL 재확보는 캐시 미스로 실패 | 외부 SKILL의 설치·자격 출력·로컬 실행 지시를 실행하지 않음. 새로운 외부 스킬을 적용하지 않음 |
| 기존 MINT 코드 | 시작 커밋 `217da74`의 discover·행위 제안·범위/인자 제한·독립 승인·검사 gate·원격 계약·등록·EOL 함수 | 표준 라이브러리·기존 Pydantic/SDK/DB 계층 사용. 새 제품 의존성·mock MCP·정책 ID 없음 |

## 검증 수준

새 순수 함수 8개, 실제 제품 함수 본문을 추출하고 DB/HTTP를 대역으로 둔 11개, 화면 템플릿/이스케이프 6개를 실행했다. 함수 추출 시험은 실제 모듈 import·FastAPI 라우팅·DB 트랜잭션/잠금·서명 검증·MCP 실행의 증거가 아니다. `intake_one_click_check.py`의 이미지용 동일 흐름 11개는 로컬에서 생략되었으며 기기 이미지에서 별도로 실행해야 한다.

실제 MCP/하네스 표본은 0이고 정상·공격·장애·경합·복구의 반복 N≥30, 지연 N≥100은 미실행이다. 통제 성공률·오탐/미탐·신뢰구간을 계산할 표본이 없다. WSL은 `WSL/Service/E_ACCESSDENIED`로 접근 거부되어 기존 `wbs-c-*` 랩의 존재도 확인하지 못했다. 랩 up/run/down, 스택 기동, SSH 배포, 실제 직원 데이터 처리는 실행하지 않았다.

기존 위험 순수 시험 2개는 새로운 승인 규칙과 충돌해 실패했다. 기존 파일을 수정하거나 실패를 통과로 바꾸지 않았다. pyflakes는 미설치라 실행 도구 자체가 실패했다. 세부 결과와 인계 조건은 작업 보고에 있다.
