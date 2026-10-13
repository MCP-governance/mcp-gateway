# Codex × Claude 개발 협업 콘솔

이 웹 화면은 **에이전트들의 실제 소통과 작업 상태를 사용자가 보는 콘솔**입니다. 연구 자료와 최종 보고는 [LLM 연구 위키](../llm-wiki/README.md)의 Markdown으로 유지합니다. 제품 게이트웨이 콘솔과 별도이며 Python 표준 라이브러리만 사용합니다.

저장소 루트에서 실행합니다.

```powershell
python -X utf8 research/collaboration-console/console.py serve
```

브라우저에서 **http://127.0.0.1:18766**을 엽니다. 서버를 켜 두면 2초마다 새 기록이 반영됩니다. Windows에서 백그라운드 실행할 때는 `Start-Process -WindowStyle Hidden`을 사용합니다. 종료는 그 서버 프로세스만 중단합니다.

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

현재 요청 모델은 **`claude-sonnet-5-5`**, effort는 **`xhigh`**로 고정되어 있습니다. 사용자가 다른 모델을 지정하면 이 설정을 먼저 바꿉니다. 지원되지 않거나 CLI가 다른 모델을 반환하면 실패로 기록하고 자동 대체하지 않습니다. CLI `system.model` 또는 `assistant.message.model`이 요청과 일치하면 모델 확인 결과를 기록합니다. effort의 서버 적용 여부는 해당 필드 없이 독립적으로 확인할 수 없습니다. API의 보조 모델 사용량은 주 모델 확인과 구분합니다.
Claude Code 자체가 만드는 로컬 알림의 모델 필드 `<synthetic>`는 실제 제공자 모델이 아니므로 모델 비교에서만 제외합니다. 해당 알림의 공개 본문은 그대로 기록하며 다른 실제 모델 이름은 계속 거부합니다.

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

## 보관·접근·검증

`runtime/events.jsonl`은 추가만 하는 로컬 기록이며 `.gitignore`로 제외합니다. 요청 파일·원시 결과·로그도 `runtime/`에 두고 공개 Git에 올리지 않습니다. 자격증명 패턴은 쓰기 전과 HTTP 응답 전 마스킹합니다. 자동 마스킹은 모든 형식의 비밀 탐지를 보장하지 않으므로 공유 보고에는 필요한 내용만 넣습니다.

HTTP는 `127.0.0.1`에만 바인딩하며 고정 정적 파일, `/api/events`, `/health`만 읽습니다. HTTP에서 기록 작성·파일 조회·명령 실행은 지원하지 않습니다. 다른 Host·Origin 요청과 경로 탐색을 거부합니다. 미연결·빈 기록·오류·갱신 지연을 구별하여 표시합니다. 최근 1,000개 기록을 보여 주며 전체 원본은 JSONL에 보존됩니다.

```powershell
python -X utf8 research/collaboration-console/test_console.py
python -X utf8 research/llm-wiki/tools/check_wiki.py
```

검사는 다중 작성 보존, 잘못된 이벤트, 비밀·내부 사고 제외, HTTP 읽기 전용·localhost 제한·경로 탐색 차단과 안전한 화면 렌더링을 확인합니다. 실제 브라우저와 실제 Claude CLI 호출은 별도 검증 결과를 기록합니다.
