# Risk scenario solution references

2026-10-14에 확인한 공식 OSS 비교 자료입니다. 이번 조사는 설치나 런타임 변경 없이 진행했습니다. 기존 endpoint 권한 카탈로그와 E12/E13에서 이미 다루는 Linux `SO_PEERCRED` snapshot 의미, MCP tool annotation 신뢰 한계, freshness 시나리오는 반복 설명하지 않고, 이를 heartbeat·attestation·revocation transaction 설계에 적용할 수 있는 공식 사례를 추가했습니다. 기계 판독용 URL, commit, license, 읽은 범위, SHA-256 및 적용 한계는 [solution-references.json](solution-references.json)에 있습니다.

## 비교 사례

| 사례 | 검증된 upstream 동작 | 현재 위험에 연결할 점 | 주요 한계 |
|---|---|---|---|
| Kubernetes v1.35 Lease | kubelet이 Lease의 `spec.renewTime`을 갱신하고 control plane이 노드 가용성 판단에 사용 | LOCAL-RISK-08/E12에서 heartbeat age와 health 증거를 분리합니다. 신선한 시간표시만으로 방화벽·프로필 검사가 참이라고 인정하지 않고, 장치 identity와 검사 세대에 묶인 상태를 검사합니다. | Kubernetes의 API identity/authorization이 있는 control plane 사례입니다. Lease 자체가 endpoint 측정이나 커널 정책 증명은 아닙니다. |
| SPIRE v1.15.3 Workload API | Unix socket peer credentials를 caller attestation 입력으로 사용합니다. 별도 Broker API는 mTLS 및 allowlist를 사용하며 해당 릴리스 문서에서 experimental로 구분합니다. | LOCAL-RISK-10 및 Linux socket 경계에서 UID 확인 이후 실제 identity/attestor selector를 어떻게 결합하는지 비교합니다. UID 일치만으로 같은 UID의 모든 프로세스에 동일한 권한 근거가 생기지 않습니다. | SPIRE 서버, trust domain, 등록/attestor 설정이 필요하며 로컬 MCP sandbox가 아닙니다. root/호스트 관리자는 peer credential만으로 차단하지 못합니다. |
| etcd v3.6.7 Txn | compare 조건과 If/Then/Else 작업을 하나의 트랜잭션으로 원자 적용 | epoch/generation 확인과 revoke/refresh 변경을 같은 atomic boundary로 두고, 동시 issue·refresh 대 revoke에서 한 쪽만 유효한 최종 상태가 되는지 시험하는 패턴입니다. 현재 저장소가 PostgreSQL이면 etcd를 도입하라는 뜻이 아니라 PostgreSQL 동등 연산으로 검증합니다. | 모든 관련 writer가 동일한 compare/version 규칙을 따라야 합니다. Txn은 그 자체로 downstream 캐시나 이미 발급된 자격을 폐기하지 않습니다. |
| PostgreSQL 17.11 / 17 docs | `SELECT FOR UPDATE`는 트랜잭션 종료까지 행 변경 경쟁을 직렬화하지만, 잠금 뒤 실제 상태 변경 없이 commit하면 대기 writer는 이후 실행할 수 있습니다. 동시성·격리 오류와 앱 일관성 주의가 공식 문서화되어 있습니다. | DEV-16과 managed admission에서 generation 비교, refresh rotation/reuse, revoke를 같은 DB 트랜잭션 안에 넣어야 할 근거입니다. 응답코드뿐 아니라 경쟁 후 committed row, revoke된 계열, successor row 개수를 확인합니다. | DB 행 잠금은 endpoint나 OS 권한 경계가 아닙니다. 모든 writer가 같은 규약을 따르고 deadlock/serialization 오류를 올바르게 재시도해야 합니다. |

## 코드 및 시험 연결

- **LOCAL-RISK-08 / E12 freshness:** 정상 경우에는 enrolled device, fresh heartbeat, device epoch, 현재 policy hash가 admission 경계에서 맞아야 합니다. 음성 경우에는 stale/replayed epoch, 빠진 검사, 또는 fresh heartbeat와 실패 검사가 함께 들어오는 입력을 거부하거나 quarantine해야 합니다. failed check가 실제로 서버에서 거부되는지는 timestamp만 보고 추론하지 말고 시험으로 확인합니다. 독립 효과는 heartbeat TTL을 JWT 만료보다 짧게 둔 뒤 TTL 경과 후 managed admission을 다시 시도해 확인합니다. 확인 후보는 `full_stack_lab/gateway/app/endpoint_plane.py::managed_checks`, `managed_failure`, `heartbeat`입니다.
- **LOCAL-RISK-10 / E13 Unix identity:** socket owner/mode, peer UID, broker가 선택한 device/account context를 분리해 확인합니다. 잘못된 UID·미등록 PID/selector·철회된 identity를 거부하고, same-UID 사례에서는 UID check 하나로 프로세스 독립성을 주장하지 않습니다. OS socket ACL과 AppArmor/service boundary는 프로토콜 identity와 독립적으로 확인합니다. 확인 후보는 `endpoint-agent/managed-linux.py::serve_user_broker`, `checks`입니다.
- **Epoch/revoke 및 DEV-16 race:** generation을 읽은 후 commit 전 revoke/epoch 증가를 끼워 넣는 경쟁을 만듭니다. 현재 `full_stack_lab/gateway/app/idp.py`의 refresh 경로에는 가족 단위 advisory lock과 refresh row `FOR UPDATE`가 있으므로, 이 직렬화가 가족 철회 및 managed device revoke/admission 순서까지 보장한다고 넓혀 말하지 말고 실제 동시 시험으로 구분합니다. stale generation transaction이 commit하지 못하고, 하나의 refresh만 성공하며, 취소된 token family의 유효 후속 자격이 남지 않는지 committed row로 확인합니다. rollback 및 deadlock/serialization retry 뒤에도 partial successor 상태가 없는지 별도 확인합니다. 다른 확인 후보는 `full_stack_lab/gateway/app/endpoint_plane.py::revoke_device`, `managed_failure`입니다.
- **LOCAL-RISK-09/10 evidence boundary:** 프로세스 이름 일치, 클라이언트의 정상 주장, 최근 timestamp만으로 관리형 권한이 활성화되지 않는지 확인합니다. identity, policy/config hash, generation, OS enforcement가 없을 때는 unknown/unverified 상태가 유지되는지 독립 검증합니다.

이 항목들은 조사에서 도출한 검증 제안이며 현재 구현·실기기 결과를 뜻하지 않습니다. 정본 JSON에 각 참조의 SHA-256 범위와 적용 한계, source commit, license 및 접근 시각을 기록했습니다. SHA-256은 고정 raw source 파일 바이트에 대해 구했고, versioned docs 페이지는 브라우저로 읽었으며 로컬 원문 사본은 만들지 않았습니다.
