# 모델 역할과 사용량 수집 근거

확인일: 2026-10-22(한국 표준시). 이 문서는 공개 지원 범위와 수집 경로를 정리한다. 실제 계정의 모델 사용 권한·남은 양·실행 성공은 별도로 확인해야 한다. 구조화 근거는 [model-policy-sources.json](model-policy-sources.json)에 둔다.

## 운영에 반영할 사실

| 대상 | 확인한 사실 | 적용·한계 |
|---|---|---|
| Opus 5.5 | Anthropic 공식 출시 및 Claude Code 지원 | 상위 지시·넓은 판단 담당. 모델 이름을 고정하고 실제 실행 모델도 기록한다. |
| Fable 5.1 / Mythos 5.1 | Fable은 일반 공개, Mythos는 trusted access 프로그램 대상 | 공개 문서에 이름이 있다고 현재 구독의 접근을 가정하지 않는다. Mythos는 권한 확인 전 비활성. |
| effort | Claude Code는 `--effort`를 지원하며 모델별 척도는 동일하지 않음 | 현행 역할 정책의 고가 검토는 기본·상한 `high`로 `xhigh` 미만을 제한한다. |
| 사이버 안전 정책 | Fable·Opus 등의 보안 관련 작업은 제공자 정책에 따라 다른 모델로 전환되거나 거부될 수 있음 | 요청 모델과 실제 모델을 구분한다. 거부를 재시도로 반복하거나 안전 정책을 우회하지 않는다. |
| Sol / Astra / Luna | 설치된 Codex 모델 캐시에 `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6-luna`와 `high` 지원 표시 확인 | 캐시 목록은 현재 서버 접근 성공 증거가 아니다. 기존 CLI를 사용하고 추가 SDK는 설치하지 않는다. |

## 사용량은 공급자 원본과 수집 시각을 함께 보관

- **Codex:** 공식 stdio `app-server`에서 `initialize` → `initialized` → `account/rateLimits/read`. 추론용 `thread/start`·`turn/start` 없이 한도 읽기만 한다. 출력은 limit ID, 사용 비율, 창 길이, 리셋 시각만 허용한다. 개인 정보·인증 응답은 저장하지 않는다.
- **Claude Code:** 공식 status line JSON의 `rate_limits.five_hour`와 `seven_day`에 `used_percentage`·`resets_at`이 있다. Pro/Max에서는 첫 API 응답 이후 제공되며 필드가 없을 수 있다. 헤드리스 작업에서 status line이 실행된다는 보장은 이 조사에서 확인하지 않았다. 없는 값은 `확인 안 됨`으로 표시한다.
- **Antigravity CLI:** 공식 `/usage`(별칭 `/quota`)는 백엔드의 모델별 한도를 갱신한다. 헤드리스에서는 `agy --print /usage`를 별도 실행한다. `--input-format stream-json`에 슬래시 명령을 넣지 않는다. 실제 조회는 별도 관측으로 저장하고, Gemini 그룹과 Claude/GPT 그룹을 합산하지 않는다.
- 서로 다른 공급자의 비율을 토큰 개수로 합산하지 않는다. 관측한 작업의 토큰 수와 계정 전체의 한도 비율은 별도 지표다. 잔여량을 추측하거나 무제한으로 표시하지 않는다.

## 공개 OSS·스킬 검토

| 대상 | 고정 커밋·라이선스 | 판정 |
|---|---|---|
| [LangGraph](https://github.com/langchain-ai/langgraph) | `3cd57c038ad827d05f80c6488adea9994156c58c` · MIT · archive 아님 | 설치된 LangGraph·SQLite 체크포인트를 재사용한다. 이 HEAD를 설치 휠의 커밋이라고 주장하지 않는다. |
| [langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py) | `88859b34017ac3569bbd4a3092c7e77593a0a960` · MIT · archive | 신규 의존성으로 넣지 않는다. README도 직접 도구를 통한 supervisor pattern을 권장한다. |
| [anthropics/skills](https://github.com/anthropics/skills) | `dbd4588f9e1033efb41dad4bef2f7947c8993d44` · archive 아님 | 공개 스킬 목록과 `claude-api`·`skill-creator` 메타데이터만 검토했다. `claude-api/LICENSE.txt`는 Apache-2.0이며 저장소 전체에 확대하지 않는다. 외부 스크립트·자격 출력·설치 명령은 실행하지 않았다. |

## 공식 출처

1. [Opus 5.5 출시](https://www.anthropic.com/claude-opus-5-5)
2. [Fable 5.1·Mythos 5.1 출시와 접근 범위](https://www.anthropic.com/claude-fable-and-mythos-5-1)
3. [Claude Code 모델·effort·fallback](https://code.claude.com/docs/en/model-config)
4. [Claude Code status line 데이터](https://code.claude.com/docs/en/statusline)
5. [Codex app-server 프로토콜](https://learn.chatgpt.com/docs/app-server)
6. [Antigravity 모델별 한도](https://www.antigravity.google/docs/cli/commands/usage)
7. [Antigravity 헤드리스 명령](https://www.antigravity.google/docs/cli/headless/)

## 사람이 읽는 운영 시트

콘솔의 기존 `runtime/sheet-source.json`과 저장소 시트 안내에서 **MINT 개발 통합 시트**(`1bfD-wfPn_ldwB-AV2o1RAr6DbAtLnQV6JJQd-exJpLI`)를 일치 확인했다. 기존 WBS·백로그의 값·수식·검증은 보존하고, 역할·판단 권한·한도 관측 범위·실행 상태는 한 개의 `에이전트 운영` 탭에서 읽도록 한다. 시트는 사람용 요약이며 실제 큐·체크포인트·사용량 관측 시각은 기존 1000번 웹 콘솔을 기준으로 확인한다.

2026-10-22에 [운영 탭](https://docs.google.com/spreadsheets/d/1bfD-wfPn_ldwB-AV2o1RAr6DbAtLnQV6JJQd-exJpLI/edit#gid=1049) `A1:H25`와 [백로그](https://docs.google.com/spreadsheets/d/1bfD-wfPn_ldwB-AV2o1RAr6DbAtLnQV6JJQd-exJpLI/edit#gid=1003) `A76:H76`의 `OPS-COORD-01` 한 건을 작성하고 읽기로 대조했다. 이미 생성된 운영 탭을 재사용했고 WBS는 수정하지 않았다. 백로그 상태의 기존 여섯 선택지, 행 서식과 `I1` 배열 수식을 보존했다. Google Sheets 실제 화면을 100% 배율로 확인했고 긴 열은 가로 스크롤로 읽는다.

| 계정·범위 | 한국 시각 관측 | 잔여량 | 리셋 시각(한국 표준시) |
|---|---|---|---|
| Codex 5시간 | 2026-10-22 18:08 | 81% | 2026-10-22 23:02 |
| Codex 주간 | 2026-10-22 18:08 | 47% | 2026-10-27 15:33 |
| Antigravity Gemini 주간 | 2026-10-22 18:05 | 28% | 2026-10-28 20:22 |
| Claude Code | 실제 잔여량 미확인 | 확인 안 됨 | 사용자가 알려 준 해제 시각을 존중해 19:05까지 실행 보류 |

관측값은 실시간 보장이 아니며 모델 접근 성공을 뜻하지 않는다. 14:15의 Antigravity Claude/GPT 그룹 100%는 과거 관측으로 남겼다. 운영 시트는 현행 정책의 정상 4단계, 최대 16단계·실행 시작 18회·수정 1회, 전체 60회/시간·제공자별 30회/시간·동일 제공자 최소 5초를 설명한다. 이 숫자는 무한 반복 방지 상한이며 정상 단계에 고정 대기를 넣는 주기가 아니다. 새 역할 경로의 실제 실행·장시간 안정성은 구현·시험 결과와 구분해 확인한다.
