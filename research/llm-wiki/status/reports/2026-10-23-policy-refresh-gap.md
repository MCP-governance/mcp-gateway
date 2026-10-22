# 서버 승인 직후 기존 MCP가 끊기는 결함 — 2026-10-23

## 원인
- `full_stack_lab/gateway/app/endpoint_plane.py` `managed_policy`(777행~)가 서버 경로·허용 목록·파일 내용을 모두 `policy_hash`에 넣는다(851행).
- `managed_failure`(969행~)가 장치가 보고한 해시와 토큰의 `device_policy`를 **현재 전체 해시와 통째로 비교**한다(981행). 서버 하나가 늘면 해시가 바뀌어 PC가 새 정책을 적용(키트 루프 60초 주기)하기 전까지 `ENDPOINT-MANAGED-001`.
- 판정 경로: 전송 인증 `agent_contract.py:181`, 호출 직전 `core.py:1717`(`_call_upstream`)·`core.py:2259`(결정), 토큰 점검 `idp.py:341·370`, 토큰 발급 `idp.py:203`. heartbeat(`endpoint_plane.py:860~`)는 낡은 해시를 비준수로 보고 격리한다(갱신 직전 보고가 겹치는 경합).

## 수정 (D-198)
- heartbeat가 해시 일치 시 장치가 설치한 서버 목록을 `detail.policy_servers`로 기록.
- `_held_policy`: 그 목록으로 정책을 다시 렌더링해 보고 해시와 같고 현재 서버의 부분집합이면 "서버 추가만". 방화벽 허용 목록·프록시·헤더 도우미·게이트웨이 주소 변경은 렌더링이 달라 매칭되지 않아 지금처럼 즉시 차단. 제거된 서버·기록 없음·낡은 토큰도 차단. 토큰 발급은 정확 일치만.
- `managed_failure(..., server=)`: 서버 추가만이면 가진 서버는 통과, 새 서버는 "PC가 새 정책을 적용하면 사용" 으로 보류. 호출 직전 두 곳에서 `server_id`를 넘긴다.
- heartbeat는 같은 판정으로 구성 해시를 비교(compliant), 응답의 `policy_hash`는 현재 값.

## 시험
- 신규 `full_stack_lab/tests/managed_policy_gap_check.py` 4건 통과(서버 추가→기존 허용·새 서버 보류, 허용 목록·프록시·헬퍼 변경→차단, 제거·기록 없음·낡은 토큰·mint→차단, heartbeat 준수/드리프트). CI `verify.yml`에 추가.
- 기존 `user_command_settings_check.py` 15건(기대값 불변, 발췌 목록에 `_held_policy`만 추가)·`managed_token_cache_check`·`managed_helper_unavailable_check`·`dispatch_recheck_check`·`open_endpoints.py` 통과. pyflakes 깨끗. `managed_enforcement_check`는 Windows에서 `grp` 부재로 기존에도 실패(Linux 전용).
- 미실행: 실제 PC·PJ1·DB 통합.

## 한계·배포 후 확인
- 갱신 주기(키트 루프 60초)·즉시 갱신 신호는 키트 파일이라 재설치로만 바뀐다. 서버 쪽에는 즉시 갱신 신호 경로가 없다(`heartbeat_seconds`를 키트가 읽지 않음). 이 변경은 주기를 건드리지 않는다.
- 배포 직후 첫 heartbeat(60초 이내)가 `policy_servers`를 기록한 뒤부터 적용된다(그 전에는 지금처럼 엄격).
- `local_jobs`(로컬 실행) 정책 비교는 그대로 엄격.
- PJ1 확인: 활성 기기에서 서버 하나를 승인한 직후 60초 동안 기존 서버 호출이 계속 성공하고, 새 서버는 PC 적용 후 사용 가능. 허용 목록 등 통제를 바꾸면 즉시 차단되는지도 확인.
