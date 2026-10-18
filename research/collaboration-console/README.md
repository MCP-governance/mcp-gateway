# 개발 현황 허브 — 협업 콘솔 + WBS + Codex 실행 로그

이 웹 화면은 **에이전트들의 실제 소통·작업 상태와 [WBS 현황](../development-status-site/README.md)을 사용자가 함께 보는 콘솔**입니다. Discord 스타일 다크 UI에 채널 `#개요` · `#wbs` · `#작업`(task_id별 스레드) · `#codex-실행` · `#검증`으로 나뉘어 있습니다. 연구 자료와 최종 보고는 [LLM 연구 위키](../llm-wiki/README.md)의 Markdown으로 유지합니다. 제품 게이트웨이 콘솔과 별도이며 Python 표준 라이브러리만 사용합니다(새 의존성·CDN·외부 폰트 없음).

저장소 루트에서 실행합니다.

```powershell
python -X utf8 research/collaboration-console/console.py serve
```

기본은 **http://127.0.0.1:1000** 입니다(`--port` 기본값 1000). 같은 Tailscale 사설망의 다른 PC에서도 보게 하려면 이 PC의 Tailscale IP에 바인딩합니다. 쓰기 API는 전혀 열지 않는 읽기 전용 화면입니다.

```powershell
python -X utf8 research/collaboration-console/console.py serve --host 100.111.15.33 --port 1000
```

`--host 0.0.0.0`처럼 모든 인터페이스에 바인딩하면 경고를 출력합니다. 특정 Tailscale IP처럼 좁은 주소에 바인딩하세요. 매일 자동으로 띄우려면 [`install-autostart.ps1`](install-autostart.ps1)로 Windows 작업 스케줄러에 등록합니다(아래 "매일 자동 실행" 참조).

서버를 켜 두면 2초마다 새 기록이 반영되고, `#wbs` 채널은 매 요청마다 [`development-wbs/snapshot.json`](../llm-wiki/analysis/development-wbs/snapshot.json)을 다시 읽으므로 재생성 빌드 단계 없이 최신 값을 보여 줍니다. Windows에서 백그라운드 실행할 때는 `Start-Process -WindowStyle Hidden`을 사용합니다. 종료는 그 서버 프로세스만 중단합니다.

## 통합 시트 연동

[`sheet-source.example.json`](sheet-source.example.json)을 `runtime/sheet-source.json`으로 복사하고,
`wbs_csv`·`backlog_csv`에 각 탭의 **웹에 게시(CSV)** URL, `sheet_url`에 시트 편집 주소를 넣습니다.
설정 파일이 없거나 해당 CSV URL이 비면 기존 저장소 사본을 사용합니다. 설정은 요청마다 읽으므로 재시작이 필요 없습니다.
CSV는 머리글 이름과 ID로 연결하며 5분 캐시·요청 타임아웃 15초를 적용합니다. 실패 시 같은 URL의 마지막 정상 캐시,
없으면 저장소 스냅샷으로 돌아갑니다. 실패도 5분 캐시하며 URL 변경 시 이전 URL의 캐시를 재사용하지 않습니다.
잘못된 머리글·중복 ID·0/0.5/1 이외 점수도 조회 실패로 처리합니다.

`/api/wbs`는 기존 근거를 보존하면서 점수·담당(`owner`)·진행 메모(`memo`)·계획 일정(`planned_schedule`)을 덮어쓰고,
새 ID·목표를 추가합니다. 빈 점수는 0, 진척은 5개 평균이며 상태·전체·목표별 요약을 다시 계산합니다.
`sheet`에는 실제 값의 출처(`sheet`/`snapshot`), 마지막 정상 조회 시각(`fetched_at`, 조회 전 `null`), 오류(`error`), 편집 주소(`url`)가 들어갑니다.
상단은 정상 시 `시트 기준 HH:MM`, 실패 시 `저장소 스냅샷 기준`과 시트 링크를 표시합니다. 마지막 정상 캐시를 쓰는 실패에서도 이 대체 문구를 사용합니다.
`/api/backlog`는 CSV 머리글을 키로 하는 JSON 배열입니다. 캐시가 없으면 `sheet/tabs/03-backlog.csv`를 사용하며 화면은 추가하지 않습니다.

로컬 사본을 갱신하려면 다음을 실행합니다. 두 CSV와 스냅샷을 모두 검증한 뒤 파일을 쓰며, manifest의 열 이름 집합이 다르면 중단합니다(열 순서 변경은 허용).
`--apply-snapshot`은 같은 ID의 점수·담당·메모·일정과 계산 요약을 갱신하고 바뀐 ID를 출력합니다. 새 ID는 스냅샷에 추가하지 않습니다.

```powershell
python -B -X utf8 research/llm-wiki/tools/sheet_pull.py
python -B -X utf8 research/llm-wiki/tools/sheet_pull.py --wbs-csv <CSV-URL> --backlog-csv <CSV-URL> --apply-snapshot
python -B -X utf8 research/llm-wiki/tools/sheet_pull.py --from-dir <CSV-폴더> --apply-snapshot
python -B -X utf8 research/llm-wiki/tools/sheet_pull.py --self-test
```

## 공개 기록 남기기

```powershell
python -X utf8 research/collaboration-console/console.py emit --author Codex --kind task --task-id solution-audit --state running --body "솔루션 코드와 연구 자료를 대조하고 있습니다."
python -X utf8 research/collaboration-console/console.py emit --author Codex --kind message --task-id solution-audit --state running --body-file research/collaboration-console/runtime/request.txt
```

`--stdin`은 UTF-8 표준 입력을 받습니다. 긴 요청은 `--body-file`을 사용하여 셸 명령 문자열에 넣지 않습니다. 로컬 Python 호출도 가능합니다.

```python
from console import EventLog
EventLog().append("Codex", "check", "solution-audit", "passed", "수행한 검사와 실제 결과")
```

한 줄 JSON 이벤트는 `timestamp`(시간대 포함 ISO 8601), `author`(`Codex`, `Claude`, `User`, `System`), `kind`(`message`, `task`, `check`), `task_id`, `state`, `body`, 선택적 `session_id`로 구성됩니다. 작업 상태는 `queued`, `running`, `waiting`, `completed`, `passed`, `failed`, `blocked`, `cancelled`를 사용합니다. 같은 `task_id`와 작성자의 마지막 **task 이벤트**가 담당자·작업 상태를 결정합니다. 같은 작업에 협력하는 Codex와 Claude의 상태는 각각 보존합니다. 메시지나 검증 결과로 작업 전체가 자동 완료되지 않습니다.

공유할 답변, 실제 작업 보고, 수행한 검증 결과만 기록합니다. 계획한 검사를 통과로, 요청한 모델 설정을 실제 사용 증거로 표시하지 않습니다. 내부 사고 과정은 기록하지 않습니다. 작업이 멈췄거나 결과가 바뀌면 상태를 명시적으로 갱신합니다. 10분 이상 갱신되지 않은 진행 작업은 화면에서 상태 확인 대상으로 표시합니다.

제품 자원 지표의 네트워크 값은 콘솔 서비스에서 설정된 게이트웨이 호스트·포트까지의 DNS·TCP 연결 시간(`console_gateway_tcp`)입니다. 애플리케이션 health 검사에는 DB·정책·의존 서비스 처리 시간이 포함되므로 이를 네트워크 지연으로 표시하지 않습니다. TCP 연결 성공만으로 게이트웨이·정책 엔진의 준비 상태를 판정하지 않습니다. CPU 측정 간격이 30초를 넘으면 기준값을 다시 잡고 다음 정상 간격까지 미측정으로 표시합니다.

## Claude CLI 공개 출력 연결

```powershell
python -X utf8 research/collaboration-console/console.py claude --task-id claude-audit --prompt-file research/collaboration-console/runtime/claude-request.txt --executable claude --allowed-tools Read,Grep,Glob --permission-mode plan --max-turns 30
```

현재 요청 모델은 **`claude-sonnet-5-5`**, effort는 **`xhigh`**로 고정되어 있습니다. 사용자가 다른 모델을 지정하면 이 설정을 먼저 바꿉니다. 지원되지 않거나 CLI가 다른 모델을 반환하면 실패로 기록하고 자동 대체하지 않습니다. **응답 모델은 제공자 응답이 실어 온 값만 인정합니다**: `assistant.message.model`(실제 응답)과 `result.modelUsage`의 모델 이름. `system.init.model`은 CLI가 해석한 요청 값을 되돌려 줄 뿐이라(존재하지 않는 모델을 요청해도 그대로 돌아옵니다) `cli_model`로만 남기고 확인으로 세지 않습니다. effort의 서버 적용 여부는 해당 필드 없이 독립적으로 확인할 수 없습니다. `modelUsage`에 요청과 다른 보조 모델이 있어도 주 모델 확인과 구분합니다.
Claude Code 자체가 만드는 로컬 알림의 모델 필드 `<synthetic>`는 실제 제공자 모델이 아니므로 모델 비교에서만 제외합니다. 해당 알림의 공개 본문은 그대로 기록하며 다른 실제 모델 이름은 계속 거부합니다.

## 실행 기록 (실행마다 한 줄)

`runtime/runs.jsonl`은 Claude·Codex 실행마다 추가만 하는 기록이며 마지막 레코드가 그 실행의 현재 상태입니다. 화면의 **실행 기록**과 `GET /api/runs`가 이 값을 보여 줍니다. 모든 값은 CLI의 실제 출력에서만 채웁니다. 요청한 값으로 응답 모델을 채우거나 없는 오류를 만들지 않습니다.

| 항목 | 값 | 출처 |
| --- | --- | --- |
| 요청 모델·강도 | `requested` | 실행에 넘긴 인자 |
| 응답 모델 | `observed.models`, `observed.usage_models`, `model_check` = `confirmed`·`mismatch`·`unreported` | Claude: 위 두 필드. Codex `exec --json`은 응답 모델을 보고하지 않으므로 항상 `unreported`(공개 이슈 openai/codex#14736) |
| 턴에 적용된 값 | `applied` | Codex 세션 파일의 `turn_context`(요청 쪽 값이며 응답이 아님, 모델·강도 두 키만 읽음) |
| 결과 | `outcome` = `completed`·`turn_error`·`usage_limit`·`task_failed`·`model_mismatch`·`cancelled`·`running` | 아래 |
| 도구 호출 | `tool_calls`, `no_tool_call`(끝난 실행이 0건일 때) | Claude `tool_use` 블록, Codex `command_execution`·`mcp_tool_call`·`file_change`·`web_search` 항목 |
| 게이트웨이 기록 | `gateway.state` = `unverified`·`none`·`recorded` | 아래 |

- **턴 오류**: 제공자·CLI가 턴을 오류로 끝냈다. Claude는 `assistant.error`(예: `authentication_failed`)나 `result.is_error`·`error_*` 유형, Codex는 `turn.failed`·`error`.
- **사용량 한도**: 위 오류 중 한도 신호가 있는 것. `assistant.error = rate_limit`, `result.api_error_status = 429`, `rate_limit_event.status = rejected`, Codex `codex_error_info = usage_limit_exceeded`, 또는 오류 본문의 한도 문구. `rate_limit_event`의 `allowed_warning`은 한도 오류가 아니다(실행의 `rate_limit`에 값만 남긴다).
- **작업 실패**: 제공자 오류 없이 프로세스가 실패했다(종료 코드 0이 아님, 완료 결과 레코드 없음, CLI를 시작하지 못함).
- **도구 호출 0건**: 오류든 정상이든 도구 호출이 0건인 끝난 실행에 붙는 표지. 한도 오류로 시작도 못 한 실행이 게이트웨이에 기록이 없는 것은 게이트웨이 결함이 아니다.
- **게이트웨이 기록**: 콘솔은 게이트웨이를 조회하지 않는다. 기본은 `unverified`다. 실행 시간대의 게이트웨이 판정 기록을 실제로 조회한 사람이 건수를 넘긴다.

```powershell
python -X utf8 research/collaboration-console/console.py gateway-records --run-id <CLAUDE_SESSION 또는 CODEX_SESSION 값> --count 0 --source "decisions id 801-805 조회"
```

`--count 0`은 `none`, 1 이상은 `recorded`로 남고 화면은 도구 호출 수와 함께 읽습니다("호출 자체가 없음"과 "호출은 있었으나 기록 없음"을 구분).

원시 CLI 출력은 `runtime/raw/<실행 ID>.jsonl`에 마스킹 없이 그대로 보관하며 Git에 올리지 않고 HTTP로 제공하지 않습니다. 화면·`/api/runs`·이벤트 기록은 마스킹한 값만 씁니다.

한계: 사용량 한도 분류는 실제 출력에서 본 필드(`rate_limit_event`, `assistant.error`, Codex 세션 파일의 `usage_limit_exceeded`)와 문구에 기댄다. Claude의 한도 거부 출력은 이 PC에서 직접 재현하지 못했고, 시험은 실제 레코드의 필드 이름으로 만든 스트림을 쓴다(시험 파일에 표시). Codex 성공 스트림은 공개 문서의 항목 유형(`agent_message`, `command_execution`, `turn.completed`)을 따르며 이 PC의 Codex가 모델 미지원 오류를 내서 성공 실행을 직접 받지 못했다.

## Codex CLI 공개 출력 연결

```powershell
python -X utf8 research/collaboration-console/console.py codex --task-id codex-audit --prompt-file research/collaboration-console/runtime/codex-request.txt --model gpt-6.1-sol --effort high -C C:\worktrees\10-17-dev-hub --sandbox read-only
```

요청은 `codex exec --json --skip-git-repo-check -s <sandbox> -m <model> -c model_reasoning_effort=<effort> -C <cwd> -`의 stdin으로 전달합니다. `-C`/`--cwd`는 codex 자신의 `-C`/`--cd`로도 전달하고 하위 프로세스의 작업 디렉터리로도 쓰여, 작업별 worktree에서 실행할 수 있습니다. 공개 `agent_message` 본문과 도구 호출의 **종류**만 이벤트 기록에 남기고 명령·결과는 남기지 않습니다. 완료·실패 기록에는 원본(마스킹 없는) CLI 로그의 `runtime/raw/` 내 경로를 요약 뒤에 덧붙입니다. WSL의 Codex를 쓰면 `--prefix-file`에 인자 배열을 저장합니다(Claude와 같음).

실행 파일을 `--executable`·`--prefix-file`로 지정하지 않고 `PATH`에도 없으면, Windows의 `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe` 아래에서 **가장 최근에 빌드된 버전**을 자동으로 찾습니다(여러 버전이 나란히 설치돼 있을 때 최신판을 쓰기 위함).

같은 네이티브 Codex 스레드를 이어가려면 `--resume`에 `CODEX_NATIVE_SESSION`으로 출력된 thread id를 그대로 넘깁니다. 내부적으로 `codex exec resume <thread id> ...`를 실행합니다.

```powershell
python -X utf8 research/collaboration-console/console.py codex --task-id codex-audit --resume <실제-Codex-thread-id> --prompt-file research/collaboration-console/runtime/continuation.txt --model gpt-6.1-sol --effort high -C C:\worktrees\10-17-dev-hub
```

WSL CLI를 쓸 때 `runtime/claude-prefix.json`에 **인자 배열**을 저장합니다. `--cd` 경로는 실제 저장소 WSL 경로로 바꿉니다.

```json
["wsl.exe", "-d", "kali-linux", "--cd", "/mnt/c/Users/bobysg/bob/프로젝트/mcp-gateway-enforcement", "--", "/usr/local/bin/claude"]
```

```powershell
python -X utf8 research/collaboration-console/console.py claude --task-id claude-audit --prompt-file research/collaboration-console/runtime/claude-request.txt --prefix-file research/collaboration-console/runtime/claude-prefix.json --allowed-tools Read,Grep,Glob --permission-mode plan --max-turns 30
```

요청은 Claude 프로세스의 stdin으로 전달합니다. stdout `stream-json`에서 assistant의 공개 `text`와 도구 **이름**, Read/Grep/Glob의 대상 파일 경로만 기록합니다. `thinking`, 검색 패턴·명령 등 도구 입력, 도구 결과 전문은 저장하지 않습니다. `--allowed-tools`는 CLI의 `--tools`와 `--allowedTools` 모두에 적용하여 활성 도구도 지정한 목록으로 제한합니다. 실행 중 20초마다 실제 CLI 프로세스 생존 상태를 남기며 종료·실패·중단을 세션 상태로 기록합니다. stderr는 실패 때만 최근 30줄의 마스킹된 요약을 기록합니다. 인증과 명령 실행 권한은 실제 Claude CLI 설정을 따릅니다.

CLI가 반환하는 실제 세션 UUID는 로컬 `runtime/<task-id>.session.json`의 `native_session_id`에 보존하며 `CLAUDE_NATIVE_SESSION`으로 출력합니다. 이벤트의 `session_id`는 실행별 기록 상관관계 ID이므로 Claude의 재개 ID와 다릅니다. 턴 제한에 도달해도 결과 유형과 실패 이유를 기록하고 기존 검토 맥락을 유지하여 재개할 수 있습니다.

```powershell
python -X utf8 research/collaboration-console/console.py claude --task-id claude-audit --resume <실제-Claude-세션-UUID> --prompt-file research/collaboration-console/runtime/continuation.txt --prefix-file research/collaboration-console/runtime/claude-prefix.json --allowed-tools Read,Grep,Glob --permission-mode plan --max-turns 15
```

## 매일 자동 실행 (Windows)

```powershell
powershell -File research/collaboration-console/install-autostart.ps1 -BindHost 100.111.15.33 -Port 1000
```

Windows 작업 스케줄러에 로그온 시 + 매일 09:00 트리거로 등록합니다. 실행 전마다 해당 host:port가 이미 열려 있는지 TCP로 확인하고, 열려 있으면 조용히 건너뛰어 중복 실행하지 않습니다(`-MultipleInstances IgnoreNew`로도 한 번 더 막습니다). `pythonw.exe`(없으면 `python.exe` + 숨긴 창)로 띄우며, 실행 로그는 `runtime/autostart.log`에 남습니다. 실행에 실패하면 1분 간격으로 최대 3번 재시도합니다.

**방화벽 인바운드 허용은 이 스크립트를 평범하게 실행하는 동안 하지 않습니다.** 관리자 권한이 필요하고 호스트를 바꾸는 작업이라, `Open-ConsoleFirewallRule` 함수로 분리해 두었고 `-OpenFirewall`을 명시해야만 실행됩니다. 소유자가 팀원 접속을 열기로 결정한 뒤 별도로 실행하세요.

```powershell
powershell -File research/collaboration-console/install-autostart.ps1 -OpenFirewall -Port 1000   # 관리자 권한, 100.64.0.0/10(Tailscale)만 허용
```

제거는 `powershell -File research/collaboration-console/uninstall-autostart.ps1`입니다(작업 스케줄러 등록과 생성된 런처만 지우며, 방화벽 규칙은 만들었을 때만 수동으로 `Remove-NetFirewallRule`을 안내합니다).

## 보관·접근·검증

`runtime/events.jsonl`은 추가만 하는 로컬 기록이며 `.gitignore`로 제외합니다. 요청 파일·원시 결과·로그도 `runtime/`에 두고 공개 Git에 올리지 않습니다. 자격증명 패턴(`Bearer`, `sk-`/`ghp_`/`github_pat_`, JWT, `Authorization:`, `*_PASSWORD`/`*_TOKEN`/`*_API_KEY` 등)은 쓰기 전과 HTTP 응답 전 마스킹합니다. 자동 마스킹은 모든 형식의 비밀 탐지를 보장하지 않으므로 공유 보고에는 필요한 내용만 넣습니다.

HTTP는 `--host`로 지정한 주소(기본 `127.0.0.1`)에만 바인딩하며 고정 정적 파일, `/api/events`, `/api/runs`, `/api/wbs`, `/health`만 읽습니다. HTTP에서 기록 작성·파일 조회·명령 실행은 지원하지 않습니다(쓰기는 모두 로컬 `emit`/`claude`/`codex` CLI로만 합니다). Host 헤더는 `127.0.0.1`·`localhost`·실제 바인딩 주소만 허용하고, 그 외 Host·Origin 요청과 경로 탐색을 거부합니다(DNS 리바인딩 방지). 응답에는 CSP(`default-src 'self'` 등)·`X-Content-Type-Options`·`Referrer-Policy` 헤더를 붙입니다. 미연결·빈 기록·오류·갱신 지연을 구별하여 표시합니다. 최근 1,000개 기록을 보여 주며 전체 원본은 JSONL에 보존됩니다. `/api/wbs`는 [`development-wbs/snapshot.json`](../llm-wiki/analysis/development-wbs/snapshot.json)을 매 요청 다시 읽어 그대로 돌려줍니다 — 별도 빌드·복사본이 없으므로 그 파일을 갱신하면 다음 2초 폴링에서 바로 반영됩니다.

```powershell
python -X utf8 research/collaboration-console/test_console.py
python -X utf8 research/llm-wiki/tools/check_wiki.py
```

검사는 다중 작성 보존, 잘못된 이벤트, 비밀·내부 사고 제외, HTTP 읽기 전용·localhost 제한·경로 탐색 차단과 안전한 화면 렌더링을 확인합니다. 실행 기록은 실제 CLI 출력(`fixtures/`의 Claude 인증 실패·Codex 모델 거부, 저장소에 보존된 PJ1 성공 로그)으로 요청 대비 응답 모델, 턴 오류·사용량 한도·작업 실패의 구분, 도구 호출 0건, 게이트웨이 기록 상태, 원시 출력의 비공개를 확인합니다. 실제 브라우저와 실제 Claude CLI 호출은 별도 검증 결과를 기록합니다.
