# LiteLLM 승인·철회 동기화

MINT에서 도입 승인과 등록이 끝난 HTTP MCP의 서버·승인 도구를 LiteLLM 1.105.0 관리 API에 반영하는 선택 애드온이다(D-208). 구현은 `full_stack_lab/gateway/app/litellm_sync.py`, 로컬 검증과 판본 근거는 [분석](../../research/llm-wiki/analysis/litellm-intervention-1023/sync-implementation.md)에 있다. 배포·실기기 검증은 미실행이다.

## 설정

기본은 꺼짐이다. 기존 `LITELLM_URL`·모델 경로 설정만으로 켜지지 않는다. `MINT_LITELLM_SYNC_URL`이 비어 있으면 스키마 적용·대기열·설정 및 비밀 읽기·HTTP 요청을 모두 건너뛴다.

| 변수 | 값 |
| --- | --- |
| `MINT_LITELLM_SYNC_URL` | 관리 API origin. 경로·쿼리·사용자 정보 없는 `https://호스트:포트` |
| `MINT_LITELLM_SYNC_BINDINGS_FILE` | 읽기 전용 사용자·키·팀·워커 매핑 JSON. Compose 기본 `/registry/litellm-sync.json` |
| `MINT_LITELLM_SYNC_KEY_FILE` | 관리 키가 담긴 비밀 저장소의 마운트 파일 경로. 값은 매 HTTP 요청마다 다시 읽음 |
| `MINT_LITELLM_ADMIN_KEY` | 파일 참조가 없을 때의 환경 변수 비밀. 저장소·로그·대기열에 기록하지 않음 |

환경 변수와 읽기 전용 마운트를 준비한 후 **리더가 솔루션 기기에서 `./console.sh field up`으로만 배포**한다. 이 변경은 기본 모델용 LiteLLM 이미지나 포트 게시를 바꾸지 않는다. 관리 origin은 게이트웨이에서 닿을 수 있어야 한다. 별도 관리 API 계정은 LiteLLM proxy admin 권한이 필요하다. 직원 MINT 토큰·upstream 자격을 이 동기화 경로로 전달하지 않는다.

[매핑 예제](../../addons/litellm/sync-bindings.example.json)의 0으로 채운 키 해시는 형식 예시이며 실사용 키가 아니다. `mint_user_id`는 MINT `principals.user_id`, `litellm_user_id`는 별도의 LiteLLM 사용자다. `key_hashes`에는 LiteLLM 가상 키의 SHA-256만 넣는다. 매핑은 호출자의 주장이 아니라 운영자의 명시적 연결 설정이다.

팀은 구성원 모두가 해당 MINT 승인 범위에 포함될 때만 도구를 부여한다. 관리 API로 다시 읽은 키 소유자·현재 팀 구성원이 매핑과 다르면 전파를 실패시키고 생성한 경로를 삭제한다. 관계없는 서버·도구·벡터 저장소 권한을 보존해 갱신하며, 도구 허용이 없으면 명시적 빈 도구 목록을 쓴다. LiteLLM의 `require_key_mcp_access_defined=true`를 API에서 확인한 뒤에만 서버를 만든다. 이 설정을 애드온이 자동 변경하지 않는다.

갱신은 LiteLLM에 존재하는 OAuth/BYOK 인증 설정과 자격을 보존한다. 자격이 결합된 기존 upstream의 origin 변경은 거부한다. SSE 수신 프로세스는 작업만 공유하고 주 게이트웨이 프로세스가 관리 전파를 수행한다.

`workers`는 각 **단일 워커에 직접 연결되는 origin의 전체 목록**이다. 로드밸런서 주소 하나로 여러 워커의 세션 종료를 입증할 수 없다. 하나의 MINT 관리 영역에서 사용하는 LiteLLM 인스턴스를 대상으로 한다. 여러 독립 MINT가 같은 서버 ID를 공동 관리하는 구성은 지원하지 않는다.

## 전파와 증거

1. 원클릭을 포함한 `core.register_server` 완료 시 영속 대기열에 넣는다. 워커는 등록 승인 사건·intake ID·현재 운영 상태·기한·활성 사용자·검토된 도구를 다시 읽는다.
2. `/v1/mcp/server` POST 또는 PUT, `/key/update`·`/team/update`의 `object_permission.mcp_tool_permissions`를 갱신한다. 원래 MINT 서버 이름을 유지하고 LiteLLM 관리 ID는 결정적으로 생성한다. 관리 표식이 다른 기존 서버는 인수하지 않는다.
3. `core.deregister_server`, 공급망을 포함한 `ops_response.suspend`, 종료 개시·폐기 종결에서 다시 대기열에 넣는다. 5초 주기의 상태 대조가 훅 이후 중단·상태 변경·기한 만료를 보완한다.
4. 철회는 자격 소유자 목록을 먼저 확보하고 서버를 삭제한다. 키·팀에는 빈 도구 권한을 쓰고 BYOK·OAuth 저장 자격을 삭제한다. 매핑 및 자격 목록에서 열거한 사용자별로 각 워커의 `/v1/mcp/sessions` DELETE를 수행한다. 집계 세션은 서버별 선택자가 없어 해당 사용자의 다른 MCP 세션도 종료될 수 있다. 다른 사용자의 세션은 종료하지 않는다.
5. 서버·키·팀·자격·각 워커의 서버 및 세션을 GET으로 재조회한다. 성공 응답만으로 완료하지 않는다. 전파 중 MINT 상태가 바뀌면 기존 승인 완료로 기록하지 않으며 철회 상태를 다시 적용한다.
6. `review.record_event`로 `approval_events(kind=litellm-sync)`에 G5 관측을 추가한다. 관측 시각, 기대 상태와 지문, 재조회한 도구·잔여 자격·세션 수, 워커 PID·선택자 해시, 실패 종류를 남긴다. 원문 HTTP 응답·관리 키·직원 토큰은 남기지 않는다.

`litellm_sync_jobs`는 수정 가능한 재시도 상태이고 원장이 아니다. PostgreSQL 세션 advisory lock으로 자체 워커 간 키·팀의 읽기/병합/쓰기를 직렬화한다. 잠금용 연결 하나를 예약하므로 `DB_POOL_MAX`는 2 이상이어야 한다(기본 10). HTTP 전파 동안 DB 트랜잭션이나 대기열 행 잠금을 유지하지 않아 중지·폐기 요청의 enqueue를 막지 않는다. 네트워크 작업이 끝난 뒤 잠금을 해제하도록 종료 취소를 처리한다. 사건 추가와 결과 상태 갱신만 짧은 DB 트랜잭션으로 함께 커밋한다. 도중 더 최신 revision이 들어오면 새 대기 상태·즉시 재시도는 보존하고 이전 시도는 실패 사건으로 기록한다. DB 기록 실패나 프로세스 중단 뒤에도 재조회하며 다시 적용한다. 실패 재시도 간격은 5초부터 최대 300초다.

화면은 등록부의 상태 칩에 `동기화 대기`·`동기화 실패`·`동기화 완료`를 표시한다. 등록 해제된 관리 대상 행도 남겨 실패를 볼 수 있다. 켜지 않은 설치에는 칩을 추가하지 않는다.

## 증거의 한계

- 현재 자동 생성은 자격 없는 HTTP upstream이다. 로컬 stdio/실행 주소와 자격이 든 URL은 등록하지 않고 실패로 남긴다. 별도 OAuth·BYOK·공유 자격의 신규 발급 및 인증 설정 복제는 구현하지 않았다. 이미 저장된 BYOK·OAuth의 철회는 처리한다. 기존 직원 토큰 전달형 애드온과 별개의 관리 경로다.
- 자격 목록 확보 실패 상태에서 서버를 삭제하면 소유자 모집단이 소실될 수 있다. 이 경우 `inventory_unknown`을 영속 보존하여 재시도의 빈 목록만으로 완료하지 않는다. 자동 증거 복구는 불가능하며 별도 모집단 재구성과 검토가 필요하다.
- 관측은 설정된 LiteLLM 관리 상태와 열거한 워커·사용자 범위다. 외부 제공자가 발급한 토큰의 원격 폐기, 이미 전송된 호출의 취소·효과 원복, SSE·stateless 요청 종료, 미열거 워커는 입증하지 않는다. 이 사건만으로 종료 모델의 T1을 부여하지 않는다.
- LiteLLM 관리자의 동시 권한 편집, 전파 대기 동안의 외부 호출, 읽기 이후의 외부 변조를 원자적으로 막지 않는다. 기존에 확인된 상태는 외부 변조 감시 증거가 아니다. 실제 호출 가능 여부와 분산 캐시 반영은 리더의 LiteLLM 1.105·PJ1 시험이 남는다.
