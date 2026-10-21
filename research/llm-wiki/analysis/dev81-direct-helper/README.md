# DEV-81 F1 직접 실행 관문과 AppArmor 문법 재현 (2026-10-21)

시작 기준 `204579981ac02956a3ee40301f251ee99af9de6e`, 브랜치 `10/21-dev81-direct-helper`.
**F1 열림·강제 승격 보류·main 병합 금지 후보**다. 기기·PJ1·실제 하네스·MCP에 접근하지 않았다.

## 고정 판본에서 확인한 직접 실행 제약

- [공식 Codex 설정](https://learn.chatgpt.com/docs/config-file/config-reference)의 `http_headers_helper`는 문자열 명령이다. 문서만으로 shell 없는 실행을 주장하지 않는다.
- [Codex 0.158.0의 run_helper](https://github.com/openai/codex/blob/064c6b8c737f5b41d171fdda80bd9ef10ad06eb3/codex-rs/rmcp-client/src/http_headers.rs#L431), 435·440·447행: Unix에서 항상 `sh` 프로세스를 만들고 `-c`와 설정 문자열을 전달한다. 절대 경로 한 개나 `exec /고정/헬퍼`로 설정해도 셸에 들어가는 AppArmor 전이가 먼저 일어난다. 현재 고정 판본에서는 설정만으로 이 관문을 닫을 수 없다.
- [수집기](collect_sources.py)와 [판본·라이선스·hash·행](sources.json): 릴리스 tag object를 commit과 대조했다. Apache-2.0 코드를 실행·변경·포크하지 않고 해당 함수만 읽었다. 현재 기본 브랜치 전체에서 대체 기능이 없다는 주장은 하지 않는다.
- 기존 보고의 Claude Code 셸 경유 판단은 유지하되 **이번에는 Claude 2.1.282 구현을 검증하지 못했다**. 노트북 WSL 패키지 2.1.199와 Windows 패키지 2.1.291은 정본의 지원 판본과 달라 그 실행을 정상군으로 대체하지 않았다. 로그인·모델 호출 없음.
- 공개 스킬은 `openai/skills`, 기존 AppArmor 프로필 OSS는 `roddhjav/apparmor.d`를 탐색했다. 각 HEAD·마지막 push·보관 상태·라이선스 API 결과는 `sources.json`에 있다. skills의 저장소 라이선스는 API에서 null이므로 개별 스킬 재배포 권한을 추정하지 않는다. 적용 가능한 고정 direct-exec 스킬은 확보하지 않았으며 외부 스크립트·프로필 채택은 없다. `openai-docs`는 공식 문서 확인에만 사용했다.

## 새로 실행해 확인한 문법 결함

기존 [강제 프로필 표본](../local-endpoints-1021/binding-profile.apparmor)을 실제 AppArmor parser 4.1.7에 `-Q -T`로 전달하면 30행의 `peer=(addr="/run/mcpgw-unit.sock")`가 `invalid value for addr`로 거부된다. 전용 소켓 파일 경로를 abstract 주소 조건에 넣은 것이 원인이다. 기존 문자열 단위 시험이 이를 통과시켰다.

[공식 AppArmor 4.0 문법](https://www.apparmor.net/man/4.0/apparmor.d/#unix-socket-rules)은 파일 경로를 가진 Unix 소켓을 파일 규칙으로 중재하고 `addr=`를 abstract/anonymous 소켓에 쓴다고 구분한다. 따라서 후보는 다음과 같다.

- 하네스·고정 헬퍼의 `/run/<프로필>.sock rw`와 진입·도구 프로필의 해당 파일 `deny rw`를 유지한다.
- 유효하지 않은 pathname `unix … peer=(addr=…)` 조건을 제거한다. 광범위한 abstract 접속 허용으로 대체하지 않는다.
- 익명 클라이언트 소켓의 생성·조회·옵션·종료만 `type=stream addr=none`으로 허용한다. abstract 소켓의 connect/send/receive를 새로 허용하지 않는다.
- 셸·companion의 도구 프로필 전이, 헬퍼 실행 거부, ptrace 거부, SO_PEERCRED/SO_PEERSEC 검사, 기본 `warn`은 유지한다. 파일 소켓에서 `unix peer=label` 조건으로 서버 신원이 보장된다고 주장하지 않는다. `/run` 소켓 소유·권한과 브로커의 클라이언트 검증은 기존 별도 경계다.

수정 후보의 경고·강제 렌더링은 모두 오프라인 컴파일에 성공했다. 과거 표본의 실패도 같은 수집기에서 음성 대조로 재현했다. [재현 스크립트](check_parser.py) · [원시 결과](parser-results.json). `-Q`는 커널에 적재하지 않는다. WSL 커널 인터페이스 부재 경고가 있어 **커널 집행·실제 연결·레이블/복구 효과는 미검증**이다.

## 원자 요구사항과 남은 판단

| 요구 | 조건·시험 | 결과·한계 |
| --- | --- | --- |
| F1-DIRECT | 공식 고정 하네스에서 셸 없이 헤더 헬퍼 호출 | Codex 0.158.0은 항상 셸을 호출. 직접 실행 미구현, Claude 지원 판본 미검증 |
| F1-PARSER | 정상 경고·강제 렌더링과 이전 오류 표본 | parser 4.1.7: 정상 2/2, 이전 오류 재현 1/1. 커널 로드 없음 |
| F1-BOUNDARY | 셸·companion은 도구 프로필, 헬퍼·소켓 거부 유지 | 새 AST 추출 시험 4건. 실제 프로세스·경쟁·복구 시험은 미실행 |
| F1-REGRESSION | 기존 AST 추출 시험을 변경 없이 실행 | `header_broker_label_check.py:199`가 잘못된 pathname 주소 문자열을 요구해 실패. 단언 변경은 메인 판단 필요 |

전체 회귀와 개별 명령·시각·원시 출력·코드 hash는 [checks.json](checks.json), 파일별 결과는 [local-suite.json](local-suite.json)에 보존한다. 원본 검토 동결 hash나 기존 시험의 기대값·단언은 바꾸지 않았다. DEV-03의 stale 검토는 이번 항목에서 처리하지 않는다.

## 방향 제안 (미채택)

1. 메인은 parser 결함과 기존 199행 단언의 충돌을 검토하고, pathname 파일 규칙에 맞는 새 시험 기준을 결정한다. 이번 후보는 실패 수가 늘므로 병합하지 않는다.
2. 지원하는 공식 하네스에 executable/argv 직접 실행 기능이 있는 고정 판본을 확보하거나, upstream에 해당 기능을 제안한 뒤 검토한다. vendor 패치·새 자격 전달 아키텍처는 이번에 만들지 않는다.
3. 현재 경고 단계를 유지한다. 강제 승격은 별도 승인·실제 하네스 정상/같은 UID 공격/커널 장애/복구 증거 확보 뒤에만 판단한다. Windows·키트·브라우저 Origin 공백은 유지한다.

WBS 불일치: 백로그의 parser 「미실행」은 이번 **후보**에서만 오프라인 실행으로 진전됐다. F1 직접 실행 완료나 main/기기 반영으로 올리지 않는다. 과거 표본·검토·실행 결과를 덮어쓰지 않았다.

## 독립 검토 상태

Agent Hub `3b6a132c5605`, 요청 Gemini `gemini-3.8-flash-medium`: 헤드리스 command 권한 거부로 결과 미생성·종료 1·needs_attention. A/B/C 판정은 없다. [실행 메타데이터](review-status.json). 권한 설정을 변경하거나 직접 재시도하지 않았으며 main에 병합하지 않는다.
