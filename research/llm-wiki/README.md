# MCP Governance 개발 연구 위키

MCP 보안 거버넌스 솔루션 개발에 필요한 논문·기술문서, 제품·소스 분석, 구축 방법론, 실험 자료를 한곳에 관리합니다. Markdown이 정본이며 Claude Code와 Codex가 같은 파일을 읽고 작업 현황을 갱신합니다.

## 바로 시작

| 할 일 | 시작 문서 |
| --- | --- |
| 현재 개발 상태와 다음 작업 보기 | [개발 현황](status/current.md) · [백로그](status/backlog.md) |
| 논문·기술문서와 확보한 원문 찾기 | [연구 자료](papers/README.md) |
| 상용 제품과 실제 오픈소스 코드 비교 | [솔루션 분석](solutions/README.md) |
| 통제를 설계하고 구현하기 | [구축 방법론](methodology/engineering-workflow.md) · [통제 설계](methodology/control-design.md) |
| 시험할 MCP와 재현 절차 찾기 | [실험 자료](experiments/README.md) |
| 위협표와 구현·실험을 연결하기 | [위협·정책 매핑](threats/README.md) |
| Claude/Codex에게 작업 맡기기 | [에이전트 공통 규칙](AGENTS.md) · [작업 지시 양식](templates/task-prompt.md) |

## 연구 문서와 개발 협업 콘솔

위키는 Markdown과 JSON으로 유지합니다. 웹은 **Codex와 Claude의 실제 소통, 작업 담당·상태, 수행한 검증을 사용자가 보는 [개발 협업 콘솔](../collaboration-console/README.md)**입니다. 연구 문서와 최종 현황 보고는 이 폴더에 저장합니다.

```bash
python research/llm-wiki/tools/build_wiki.py
python research/llm-wiki/tools/check_wiki.py
```

MD를 고친 뒤 위 명령으로 문서 목록과 원본 해시·출처·링크·실험 상태를 확인합니다. 웹 문서 번들은 생성하지 않습니다. XLSM을 다시 추출할 때는 `requirements.txt`의 라이브러리가 필요합니다. 협업 콘솔은 저장소 루트에서 실행합니다.

```bash
python -X utf8 research/collaboration-console/console.py serve
```

접속 주소는 `http://127.0.0.1:18766`입니다. 솔루션 실행 스택과 별도이며 이 PC에서만 접속합니다. 실제 공개 메시지와 작업 보고를 로컬 JSONL에 추가하면 콘솔에 반영됩니다. 기록이 없으면 빈 상태로 표시하며 작업·메시지를 만들어 넣지 않습니다.

## 자료와 결과를 읽는 기준

원문 확보, 선별 읽기, 소스 확인, 프로토콜 시험, 실제 모델·하네스 시험, 운영 배포 검증을 구분합니다. 자료를 가져온 날짜를 연구 결과의 재현 날짜로 취급하지 않습니다. 자료 수와 협업 기록 수는 연구 완료율이 아닙니다.

기존 공모전 위키에서는 MCP/OAuth·에이전트 보안·도구 오염·호출 통제에 필요한 공개 자료를 선별 이관했습니다. 공모전 초안과 일반 법제 자료 전체를 복제하지 않았습니다. [자료 확보 규칙](methodology/source-protocol.md)에 원본과 출처, SHA-256, 추출·검토 상태를 남기는 방식을 설명합니다.

공개 Git 저장소에는 재배포 조건을 확인한 원문과 우리 분석을 올립니다. 재배포 허가가 불명확한 원본·전문 MD는 이 PC의 `local-sources/`에 보존하며 Git과 웹의 본문에 포함하지 않습니다. Claude/Codex는 이 PC에서 해당 파일을 직접 읽을 수 있습니다. 다른 PC에는 분석·출처·해시가 전달되며 원본은 공식 제공처에서 따로 확보합니다.

구현 정본은 [설계](../../docs/ai/ARCHITECTURE.md), [통제 경계](../../docs/ai/SECURITY_BOUNDARIES.md), [시험 규칙](../../docs/ai/TESTING.md)입니다. 이 위키는 개발 연구와 상태 보고를 모으고 정본의 근거를 연결합니다.

## 공통 작업 흐름

1. `status/current.md`에서 현재 코드 기준과 남은 작업을 확인합니다.
2. 논문·코드·위협 근거를 골라 검증 가능한 통제 하나를 정합니다.
3. 성공 조건과 실패·미실행 조건을 먼저 쓰고 구현합니다.
4. 수행한 검증의 원본 증거를 저장하고 [작업 보고서](templates/work-report.md)를 작성합니다.
5. `status/current.md`, `status/backlog.md`, 관련 분석을 갱신하고 실제 공유 메시지·작업 상태·검증 결과를 협업 콘솔 기록기에 남깁니다.

자료가 부족하면 URL, 파일 위치, 필요한 시험 환경·권한을 보고서의 `사용자에게 필요한 입력`에 구체적으로 남깁니다. 자격증명은 Git에 넣지 않습니다.
