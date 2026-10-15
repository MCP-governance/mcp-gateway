# Managed Linux endpoint: 정적 위험 시나리오

조사 기준은 2026-10-14 (Asia/Seoul), branch `10/14-risk-scenarios`, HEAD `ab6936c64f3578de8360b840f1928681714fa7bb`의 현재 작업 트리입니다. 공유 checkout에는 기존 dirty 파일이 있으므로 해시를 함께 고정했습니다. 이 보고서는 `managed-linux.py`, `enforce-linux.py`, Gateway endpoint plane 및 관련 인증/dispatch 호출자를 읽은 정적 검토입니다. 제품 코드·DB·시스템 설정을 바꾸거나 테스트하지 않았습니다.

## 결론

LOCAL-RISK-08의 핵심 사슬은 코드상 연결되어 있습니다. Linux `checks()`가 AppArmor의 정확한 enforcing profile 행, nftables의 설치 baseline 일치, 보호 설정 파일, 계정 조건을 계산하고, `heartbeat()`는 정확한 플랫폼별 check 집합과 모두 `true`인 결과를 요구합니다. 불일치 heartbeat는 장치를 격리하며, 관리 서비스는 활성·준수 heartbeat일 때만 bearer를 캐시합니다. 격리 상태는 다음 정상 heartbeat만으로 해제되지 않고 별도의 관리자 활성화가 필요합니다. LOCAL-RISK-09/10은 이 하위 작업의 목적과 겹치는 신규 결함을 확인하지 못했습니다.

신규 후보는 하나입니다. 관리자가 장치를 폐기해도 Linux root 서비스의 Unix socket은 저장된 bearer를 최대 120초 캐시 만료까지 같은 UID에 전달할 수 있습니다. 다만 조사한 Gateway 경로는 mint 시점과 MCP 사용 시점에 장치의 현재 `status`, owner, epoch, managed state, heartbeat, policy를 재확인합니다. 따라서 현재 근거로는 MCP 실행 우회가 아니라 **폐기 후 로컬 bearer 전달이 잠시 지속되는 조건부 설계 공백**입니다. “즉시 로컬 자격 전달 중단”이 요구사항인지 먼저 정해야 합니다.

## 후보 STATIC-ENDPOINT-01: 폐기 뒤 로컬 캐시 bearer 전달

`managed-linux.py:231-240`의 `Header.handle()`은 `SO_PEERCRED` UID가 등록 UID와 일치하고 `cache.until`이 지나지 않았는지만 확인한 뒤 `Authorization: Bearer …`를 반환합니다. 장치 상태를 읽거나 Gateway에 폐기 여부를 묻지는 않습니다. `serve()`는 활성·준수 heartbeat 뒤 `access_token`을 120초 동안 저장하고(286-290행), 다음 활성 loop pause를 60초로 설정합니다. 다음 loop에서 오류가 감지되면 cache를 지우지만(308-313행), 관리자 폐기는 원격 DB 변경만 수행하고 로컬 push는 없습니다. 따라서 이미 발급한 bearer의 남은 TTL 동안 같은 UID에서 로컬 helper가 헤더를 반환할 수 있습니다. 두 observer 실행은 각각 최대 40초 timeout을 두고 token 발급 뒤 실행되므로 주기적 확인 시각은 더 늦어질 수 있지만, cache TTL 자체는 발급 후 120초 상한입니다.

반면 `endpoint_plane.revoke_device()`(420-430행)는 DB status를 `revoked`로 갱신합니다. 다음 장치 API 요청은 `authenticate_device()`(433-446행)의 `status='active'` 조건에서 거부되고, token mint route는 발급 전에 device authentication 및 `managed_failure()`를 호출합니다(`idp.py:182-205`). 이미 발급한 access token도 `managed_failure()`에서 현재 device status/owner/managed state/epoch/heartbeat/policy를 검사하며(`endpoint_plane.py:657-670`), 검사 호출이 MCP 계약 인증 및 dispatch preflight에 있습니다(`agent_contract.py:117-140`, `core.py:1470-1483`). 따라서 정적 소스 경로만 보면 로컬 헤더가 한동안 반환되어도 실제 MCP dispatch는 거부되어야 합니다. 이 결론을 런타임 denial/no-dispatch 증거로 취급하지 않았습니다.

재현 가능한 **정적 시나리오**는 합성 상태에서 활성·준수 장치에 토큰을 캐시한 뒤 DB status를 `revoked`로 바꾸고, cache 만료 전 같은 UID에서 helper 요청과 Gateway 요청을 따로 추적하는 것입니다. 예상 결과는 (1) helper가 만료 전 bearer를 반환할 수 있음, (2) fresh mint 거부, (3) 보호된 MCP 경로에서 managed failure, no-dispatch 입니다. 이 시나리오는 실행하지 않았습니다. 수정 논의는 로컬 즉시 회수를 계약으로 요구하는지부터 결정하고, 필요하다면 명시적 짧은 lease/폐기 신호를 설계해야 합니다. 주기 heartbeat가 즉시 push를 제공한다고 가정해서는 안 됩니다.

정상군은 fresh active/compliant 상태와 현재 policy에서 등록 UID helper 응답 후 Gateway가 수락하는 경우입니다. 음성군은 다른 UID가 socket을 사용해 bearer를 못 받는 경우입니다. 경계군은 폐기 직후, TTL 직전, TTL 이후 helper 및 Gateway 결과를 각각 기록하는 경우입니다. race군은 한 handler가 lock 안에서 token을 복사한 다음 서비스 thread가 `cache.clear()`를 호출하는 경우입니다. `sendall()`이 lock 밖에서 수행되므로 이미 복사된 응답 하나는 clear 후에도 보내질 수 있습니다. 이는 로컬 credential delivery의 시간 경쟁이며, Gateway 효과 차단은 별도 검증해야 합니다.

`SO_PEERCRED` 검사는 UID 단위입니다. `chmod 0600` socket과 UID 비교는 다른 UID를 막지만, 같은 UID로 실행되는 모든 프로세스를 구별하지 못합니다. 이는 공유 계정이 한 principal이라는 현재 모델의 경계로 분류하며, 서로 다른 UID 사이의 우회 근거는 아닙니다.

## 활성화·heartbeat·principal binding 경로

- 설치 시 `consume_enrollment()`은 미사용·미만료 enrollment token과 활성 principal을 transaction 안에서 확인하고, owner token·device epoch·local username/UID를 장치에 묶은 뒤 `managed_required=true`로 설정합니다 (`endpoint_plane.py:513-539`).
- `managed_policy()`는 저장된 device epoch를 요구하고 Gateway의 승인 MCP 경로 및 정책 파일을 구성합니다 (`542-602`).
- `heartbeat()`는 서버에서 다시 만든 policy hash, config hash, 플랫폼별 정확한 check key와 모든 `true`를 대조합니다 (`610-635`). 불일치 시 quarantine이며 heartbeat만으로 활성 상태가 되지 않습니다.
- `activate_managed()`는 본인 소유 장치 활성화를 거부하고 관리자 활성화 요청 시 active status, expected/current policy hash, 최근 180초 heartbeat, config hash, 모든 true인 enforcement checks를 SQL 조건으로 재확인합니다 (`638-654`). 정적 코드는 경합 시 검토한 정책과 다른 증거로 활성화되는 명백한 길을 보이지 않습니다.
- `managed_failure()`는 claim의 `device_id`로 device를 찾고 principal token과 owner token, active status, managed state, epoch, heartbeat age, current policy를 대조합니다 (`657-670`).
- `enforce-linux.py:67-77`은 UID별 nft output chain에 명시 Gateway 주소·포트 예외 뒤 reject를 만들고, `80-140`은 harness·entry·credential helper 각각의 AppArmor profile과 px/ix 전이를 생성합니다. `managed-linux.py:98-122`은 실제 nft table을 저장된 정규 baseline과 대조하고 네 개 profile의 정확한 enforcing 행을 요구합니다. 정적 검토만으로는 loaded kernel rule 본문·실제 process label/transition·기동 중 정책을 입증하지 않습니다.

## 테스트 행렬

JSON의 `scenario_matrix`에 정상, 음성, 경계, race 및 활성화 조건을 기계 판독 형태로 기록했습니다. 이를 DB 보존 동적 시험이나 격리 DB 시험의 성공 건수로 세지 않았습니다. 실행/커널 증거 상태는 모두 `not run`입니다. 권장 검증은 합성 endpoint/principal/token만 사용하는 환경에서 helper bearer 반환 여부와 Gateway denial/no-dispatch를 별도 관측하고, revoke 시점과 monotonic cache expiry를 상관시키는 것입니다.

## 범위와 증거 한계

LOCAL-RISK-08은 기존 위험 매핑의 진술과 현재 작업 트리의 함수 흐름을 정적으로 대조했을 뿐 이전 수정의 재시험을 하지 않았습니다. LOCAL-RISK-09/10은 신규 finding이 없다는 뜻이며 전체 수집/저장 경로 재감사를 의미하지 않습니다. DB 트랜잭션 타이밍, 배포 소스 일치, systemd scheduling, 실제 Unix socket credential, AppArmor attachment/transition, nftables 집행, 실제 툴 호출 결과는 확인되지 않았습니다. 코드 수정, 테스트, 로컬 socket probe, DB 연결 및 실기기/kernel 변경은 모두 미실행입니다.

JSON에는 각 코드 대상·라인, 재현 조건, 기대 관측, source SHA-256 및 미실행 증거 상태가 포함되어 있습니다.
