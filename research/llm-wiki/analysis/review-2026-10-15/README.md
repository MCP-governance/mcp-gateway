# 2026-10-15 통합본 검토와 개선 근거

제품 코드 기준은 `83269c1d070d6289911a8d4d0f8622e3c90f6d5c`, 보고 기준은 `e61e43c76967c05a6eaa3895e1b8e3cefedb5edf`다. 앞선 읽기 전용 검토를 개발 위키의 지속 참조 자료로 정리했다. 이번 문서 통합 기준은 Drive curation `1ad6395e9c357195294aa20ed959b2bebf5b8710`이다. 문서 보강은 제품 수정·위험 수용·새 실행 승인에 해당하지 않는다.

## 먼저 읽을 경로

1. [현재 상태](../../status/current.md)와 [단일 백로그](../../status/backlog.md).
2. [Claude 다음 작업 안내](claude-next-work.md), [DEV-38 실행 경로 제안](dev38-runtime-plan.md).
3. [구조화 검토 항목](recommendations.json), [공식 참고 자료](references.json).
4. [Drive 원본 대조와 50개 정책 연결](../drive-curation/README.md), [시험·증거 계약](../../methodology/evidence-contract.md).

## 1. 현재 상황

실제 MCP를 통한 관리 Claude 사용 경로와 정상/차단 결과가 보존돼 있다. [클린 기기 E2E](../../status/reports/2026-10-15-clean-e2e.md)는 GitHub·MarkItDown 정상 호출, 범위 밖 MarkItDown 요청 2건의 upstream 시도 없음, Context7의 제공자 할당량 오류를 구분한다. 이번 대화의 앞선 읽기 전용 `/api/health` 조회는 실행 revision `83269c1`, 구성 요소 6개 정상, 정책/정책 데이터 해시 일치, MCP 3개 READY를 반환했다. 그 조회의 원문은 새 증거 파일로 보존하지 않았으므로 독립 재현용 배포 증명으로 사용하지 않는다.

현재 WBS 스냅샷은 구현 완료 35/40, 부분 5/40, 단계 가중 57.5%, 최종 검수 완료 0/40이다. 서로 다른 지표다. MarkItDown은 운영자가 실행한 컨테이너이고, 승인 OSS를 제품이 빌드·실행하는 DEV-38은 미구현이다. Codex 자연어 E2E와 엔드포인트 이벤트/판정 원장 상관도 남아 있다. 이번 문서 작업으로 WBS 점수나 실험 카드 상태를 올리지 않는다.

## 2. 코드에서 확인한 개선점

아래의 RV 식별자는 검토 레코드다. 실제 작업의 상태와 완료 조건은 백로그 DEV 식별자에서만 관리한다. JSON에는 기준 판본·함수·행·정규화 코드 해시·근거·검수 조건을 함께 기록한다.

| 검토 | 작업 | 관찰과 최소 개선 | 확인 수준 |
| --- | --- | --- | --- |
| RV-01 | DEV-41 | `review.derived_constraints`는 목적지 목록이 비면 `^https://`를 생성한다. 빈 목록은 목적지 불허로 해석하고 중첩/배열 주소와 실제 outbound를 함께 통제한다. | 정적 코드 동작 확인, 실제 우회 미실행 |
| RV-02 | DEV-42 | Linux 프로필은 Bash만 `-tool`로 옮기고 sh는 하네스 권한을 유지한다. 관리 설정에는 `allowManagedHooksOnly`가 없다. 사용자 훅·관련 명령 표면을 닫고 헬퍼 접근 음성 시험을 추가한다. | 우회 위험 후보, 토큰 획득 재현 아님 |
| RV-03 | DEV-43 | 전송 의도 SQL은 서버 행만 잠그고 주체 행은 잠그지 않는다. 서버 잠금 대기와 계정 중지 commit을 교차하는 시험 후 잠금 규약을 정한다. | DB 경쟁 후보, 실행 미재현 |
| RV-04 | DEV-44 | 인자 제약을 만들 때 원본의 `$defs`·루트 복합 스키마를 보존하지 않는다. 원본 계약 검증과 권한 제약을 별도로 합성하거나 미지원 형태를 명시한다. | 정적 호환성 문제 |
| RV-05 | DEV-44 | 비객체 structuredContent를 항상 제거하고 outputSchema는 승인 계약에 포함하지 않는다. 협상 판본별 결과 보존과 출력 계약 잠금이 필요하다. | 정적 호환성/계약 공백 |
| RV-06 | DEV-44 | discovery와 실행 직전 목록 경로는 첫 `list_tools()` 결과만 사용한다. pagination을 포함한 SDK 동작을 확인하고 전체 목록을 공통 경로에서 검수한다. | 코드 후보, 페이지형 실제 서버 미시험 |
| RV-07 | DEV-38 | 검사한 소스와 내부 미러는 대조하지만 image digest·실행 ID·endpoint 연결 근거가 없다. | 코드와 E2E 보고에서 확인한 제품 공백 |
| RV-08 | DEV-45 | 재산정기가 시험 이름의 마지막 행과 rc만으로 실행을 선택한다. run_id·소스·이미지·환경·원본 증거에 결박한다. | 산정 코드/보존 로그 확인 |
| RV-09 | DEV-45 | WBS 증거 파일 17개 중 raw 해시 불일치 6개: 5개는 CRLF/LF 차이, 1개는 변경된 생성기다. 원본/정규화 해시와 기준 commit을 분리한다. | 바이트 재계산, 변조 판정 아님 |
| RV-10 | DEV-46 | 텍스트 규칙의 탐지 점수와 실제 에이전트의 비승인 효과를 분리하고 독립 한국어·출처별 평가를 추가한다. | 기존 평가 결과와 방법론 검토 |

### 명세 판본과 안전 근거

[MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#structured-content)는 객체형 structuredContent를 설명한다. [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#structured-content)는 outputSchema에 맞는 모든 JSON 값을 허용한다. GitHub의 당시 협상 판본은 E2E JSON에 없으므로 그 응답 자체를 신형 규격 위반이라고 확정하지 않는다. `mcp==2.2.0`의 현재 광고 출력 스키마 검증과 MINT의 **승인 출력 계약 고정**은 별개다.

현재 fallback은 원래 JSON과 변환 후 문자열에 주입 검사를 적용하고 이후 개인정보/비밀 검사를 거친다. fallback 자체가 검사를 우회한다는 근거는 없다. 직원 토큰을 upstream으로 전달하지 않는 자격 분리, 주체·endpoint·자격 해시별 HTTP 풀, 절대 경로 launcher도 확인했다. HTTP 연결 재사용을 MCP 프로토콜 세션 재사용이라고 부르지 않는다.

OWASP의 [SSRF 방어](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)는 입력과 네트워크 제어를 함께 다룬다. 임의 HTTPS 허용, redirect, DNS 변경은 각각 확인해야 한다. Claude의 [관리 훅 제한](https://code.claude.com/docs/en/hooks#hook-locations)과 [sh/direct-exec 실행 형태](https://code.claude.com/docs/en/hooks#exec-form-and-shell-form)는 DEV-42의 조사 근거이며 설치 판본에서도 확인해야 한다. PostgreSQL의 [행 잠금](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS)은 DEV-43의 경쟁 시험 설계 근거다.

## 3. 다음 작업과 목표 기능 연결

| 목표 | 우선 적용할 보강 | 완료를 판단할 증거 |
| --- | --- | --- |
| G01 도입 | DEV-38의 source→build→image 연결 | 검증 커밋·레시피·의존성·image digest 대조 |
| G02 승인·계약 | 독립 승인 유지, DEV-44 출력/복합 계약 | 승인 전 미노출, 변경 뒤 재승인, 정상 계약 보존 |
| G03 호출 권한 | DEV-41·43 | 빈 목적지/미심사 자원 거부, 철회 경쟁의 독립 효과 0 |
| G04 데이터·주입 | DEV-44·46 | 표현별 마스킹, 오탐/미탐과 공격 효과·정상 업무 결과 분리 |
| G05 엔드포인트 | DEV-42·35 | 훅/셸 음성군과 승인 하네스 정상군, 비관리 UID 범위 명시 |
| G06 감사 | DEV-39·45 | model→MCP request→decision→intent→endpoint→외부 효과 연결 |
| G07 종료 | DEV-38·29와 기존 종료 모델 연결 | 실행 정지·자격 거부·잔존 파일·복원 뒤 재접근 확인 |
| G08 사용성 | DEV-39 | 새 관리 Claude/Codex 세션의 정상·거부·오류·복구 |
| G09 성능 | DEV-29·37 | cold/warm p50/p95, 실패·quota·gateway/upstream 구간 구분 |
| G10 개발·근거 | DEV-36·45, WIKI-01 | 고정 판본 배포·검사 실행 ID·변경 시 재검수 |

추천 순서는 권한 경계 검증 → MarkItDown 자동 실행의 세로 경로 → 두 하네스의 호출 증거 연결 → 종료·복구 검수 → 세션 성능 개선이다. 현재 DEV-29·35 별도 브랜치는 문서 제안이며 병합하지 않았다. DEV-35 제안의 D-107은 통합본 D-107~109와 충돌하므로 향후 병합 때 재번호화한다.

## 4. 프로젝트 운영과 위키 공백

- 기기 직접 복사 7회와 기능 누락은 [보고서](../../status/reports/2026-10-15-clean-e2e.md)에 기록돼 있다. DEV-36은 작업 브랜치→검사→통합→고정 판본 배포로 정리한다. [DORA](https://dora.dev/capabilities/deployment-automation/)의 동일 산출물 배포·버전 관리 원칙을 참고한다.
- WBS의 달성 이력과 현재 유효성을 나눈다. 과거 점수는 보존하고 새 코드의 현재 증거에는 `유효/재검수/실패`를 붙이는 안을 DEV-45에서 검토한다. 단일 점수로 출시 가능성을 표현하지 않는다.
- `status/current.md`의 과거 결과가 최신 상태와 섞이지 않도록 현재 요약과 [변경 이력](../../status/history-2026-10-15.md)을 나눴다. 문서 날짜와 실기기 관측 날짜를 별도로 읽는다.
- Drive 원본 50개 정책은 기존 50개와 이름·본문을 대조했다. 숫자나 신규 파일 수를 추가 구현 수로 세지 않는다. 법령 근거 셀의 최신성·법적 적용성은 이번 기술 검토 범위가 아니다.
- 전체 Markdown 구조·카탈로그·링크를 점검하고 각 영역 진입 문서를 읽었다. 167개 연구 자료의 전문 재검토나 모든 코드 본문 감사를 한 것은 아니다. [탐색 지도](../../papers/development-reading-guide.md)로 다음 작업에 필요한 근거를 먼저 찾는다.

## 5. 해석과 재현 한계

기존 [코퍼스 결과](../../status/reports/2026-10-15-inspection-corpus.md)는 결과 규칙 재현율 약 49.5%, 계약 오염 약 52.4%를 보고한다. 같은 출처에서 나눈 held-out과 작성자가 만든 한국어 표본의 한계가 있다. [MCPTox](https://ojs.aaai.org/index.php/AAAI/article/view/40895)의 에이전트 공격 효과 평가와 정적 문자열 탐지를 혼합하지 않는다. 의미 분류기 도입은 후보이며 새 의존성·성능·오탐 평가 전에는 제품 기능으로 적지 않는다.

이번 검토에서 실제 우회·DB 경쟁·새 MCP 실행·실기기 회수 시험은 하지 않았다. 위험 후보는 재현/반박 결과에 따라 수정한다. 현재 위험을 고쳤다는 뜻으로 이 문서를 인용하지 않는다.
