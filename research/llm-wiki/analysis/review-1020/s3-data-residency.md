# DEV-69 처리 위치·국외 이전 규칙 팩 적대 검토

- 검토 대상: 30fae725ef20db4967635e85b170cb13c0f98abd (feat(v2): 서버 처리·저장 위치 속성과 국외 이전 규칙 팩 (DEV-69, D-138))
- 기준: 09220f515bea70a498b921f4e23eafd605e8444b
- 비교 대상: 로컬 origin/main a020458ca723b735c6e286a0e70b15a4b485f749 (제공된 기준)
- 범위: 읽기 전용 diff·호출 경로·정책·UI·배포 구성 검토. 테스트·배포·PJ1 실행은 하지 않음.

## 결론: 수정 후 병합

규칙은 fail-closed로 연결됐고 직접 신청자 위조 경로는 확인하지 못했다. 다만 기존 github 등록의 위치 정보가 없으면 비공개 등급 호출은 배포 직후 차단된다. 현재 API로 승인된 등록의 위치만 갱신할 수 없어, 운영 전환 경로를 먼저 마련하고 main과 겹치는 파일의 병합 결과를 정리해야 한다.

## 발견 사항

| 번호 | 심각도 | 문제 | 근거 파일:행 | 수정안 |
|---|---|---|---|---|
| 1 | 높음·배포 차단 | residency.facts()는 외부 제공 서버의 등록 위치가 비어 있으면 빈 국가·처리자·근거를 만든다. OPA는 비공개 등급에서 이 상태를 P-RESIDENCY-001로 차단한다. 주어진 현장 상태의 github(제공자 호스팅·내부 등급)는 관련 호출이 내부/중요 데이터로 분류되면 배포 즉시 막힌다. 이 동작은 기본 차단 요구와 일치하지만, 현재 등록 사양만 보완하는 관리 API는 없다. | [residency.py](../../../../full_stack_lab/gateway/app/residency.py#L40), [policy.rego](../../../../full_stack_lab/opa/policy.rego#L62), [core.py](../../../../full_stack_lab/gateway/app/core.py#L567), [agent_service.py](../../../../full_stack_lab/gateway/app/agent_service.py#L1434) | 배포 전에 공급자 근거를 확보하고, 신규 도입 신청의 관리자 계약 검토에 위치 필드를 기록한 뒤 독립 승인·등록을 완료한다. 현재 검토 경로는 HOLD/REMOTE_REVIEWED만 받으며 승인된 요청을 다시 여는 기능이 없다. 새 신청은 기존 활성 서버 ID와 충돌하므로 재등록 시 새 ID와 하네스 경로 전환 또는 별도 승인형 마이그레이션을 준비한다. |
| 2 | 중간·보증 한계 | 신청자가 직접 쓴 위치값이 OPA 입력으로 그대로 흐르는 우회는 확인되지 않았다. 원격 review-contract와 등록은 관리자만 가능하고, 등록 값은 심사에 저장된 전체 registration과 일치해야 한다. 그러나 국가·처리자·evidence_ref·transfer_basis는 문자열/국가코드 형식만 확인한다. 허위 자료를 관리자가 승인하면 그 선언을 사실로 판정한다. | [agent_service.py](../../../../full_stack_lab/gateway/app/agent_service.py#L1434), [agent_service.py](../../../../full_stack_lab/gateway/app/agent_service.py#L1531), [residency.py](../../../../full_stack_lab/gateway/app/residency.py#L21), [policy.rego](../../../../full_stack_lab/opa/policy.rego#L41) | evidence_ref를 확인 가능한 공급자 자료 식별자·해시와 연결하고 심사 화면에서 검토·승인 사실을 남긴다. 현재 범위에서는 이를 독립 실측이나 법적 유효성 검증으로 설명하지 않는다. D-138의 선언 속성 한계와도 일치한다. |

### 요청된 적대 항목 점검

- **등급×국가:** 실제 호출 등급 cls.data_class와 서버·외부 목적지 각각의 처리/저장 국가 합집합으로 판정한다. 국가별 규칙은 등급의 * 기본값을 적용한다. 공개 등급은 위치 누락을 허용하고, 공개 외 등급은 서버·목적지의 주체/근거/처리·저장 국가가 비면 차단한다. 국가코드 유효성은 Gateway 정규화에서 확인한다. 목적지 호스트는 별도 organization.destination_locations를 참조하므로 서버 국내 위치로 대신할 수 없다.
- **기본 차단·예외:** 금지 국가와 위치 누락은 건별 승인으로 풀리지 않는다. 승인 필요만 PAC-13의 독립 승인·요청 digest로 풀리며 digest 기준선에 residency_sha256가 들어간다. approval.granted 단독 값은 사용하지 않는다.
- **관찰 모드:** P-RESIDENCY-가 ALWAYS_ENFORCED에 포함돼 관찰 모드에서도 강제된다. 실행 직전 PAC 재판정이 위치 팩을 다시 읽는다.
- **OPA 우선순위:** P-RESIDENCY-001=48, P-RESIDENCY-002=83; policy_ledger.json 전체에서 우선순위 중복은 없다. 숫자가 작을수록 먼저 선택되는 기존 규칙에서 차단 48은 기존 권한/계약 판정보다 앞선다. 승인 83은 PAC-13(89)보다 먼저 선택되며 다른 승인/차단 후보를 무효화하지 않는다. 집행 우선순위 충돌은 발견하지 못했다.
- **콘솔 규칙:** 추가된 화면은 한국어 라벨·값이며 상태 enum, 개발 번호, 도움말 문단, 약어 표식이나 새 브라우저 코드 주석을 넣지 않았다. 이 diff에서 콘솔 문구 규칙 위반은 발견하지 못했다. 실제 렌더링은 미확인이다.

## 기존 현장 서버의 배포 영향 및 조치

| 서버 | DEV-69 영향 | 배포 전 조치 |
|---|---|---|
| github — api.githubcopilot.com, 제공자 호스팅, 내부 등급 | 비공개 등급 호출의 서버 위치가 없으면 P-RESIDENCY-001 차단. 등록 등급보다 호출 자원의 실제 분류가 높으면 그 등급으로 판정한다. | 공급자 자료에서 처리 국가·저장 국가·처리 주체·위치 근거를 확인한다. 국외 이전이면 transfer_basis를 기록하고 승인 필요 규칙에 따라 건별 승인을 받는다. |
| context7 — 제공자 호스팅, 공개 등급 | 공개 등급이면 위치 누락만으로 DEV-69 차단되지 않는다. 다른 기존 정책은 별도로 적용된다. | 공개 등급이 실제 호출 데이터까지 맞는지 확인한다. 더 높은 등급을 다루면 위치 자료를 확인하고 신규 심사를 거친다. |
| markitdown — 내부 실행기, 공개 등급 | 실제 ACTIVE 실행기이면 deployment=internal; registry/field/catalog.toml의 조직 machine_location에서 KR을 읽는다. 공개 등급이므로 DEV-69 위치 누락 차단은 발생하지 않는다. | ACTIVE 실행기 여부와 KR 조직 배치값을 확인한다. 이 설정값은 실측 증거가 아니다. |

필요 필드는 residency.processing_countries, residency.storage_countries(ISO alpha-2 배열), residency.processor, residency.evidence_ref, residency.transfer_basis다. 신규 신청은 POST /api/mcp-requests, 원격 관리자 계약 검토는 POST /api/mcp-requests/{request_id}/review-contract, 독립 승인과 등록은 POST /api/mcp-requests/{request_id}/approve 및 POST /api/mcp-requests/{request_id}/register 경로다. 위치 변경은 기존 remote_contract.registration와의 일치를 깨므로 기존 승인 내용을 덮을 수 없다. 신규 신청부터 별도 검토·승인을 거쳐야 한다.

## main과 겹치는 파일

git merge-tree는 읽기 전용으로 실행했다. 공통 조상 기준 양쪽이 함께 바꾼 파일은 다음 7개다. 따라서 이 결과를 그대로 병합 완료로 간주하지 않는다.

- docs/ai/DECISIONS.md, docs/ai/POLICY.md
- full_stack_lab/gateway/app/agent_service.py, full_stack_lab/gateway/app/agent_static/console.js, full_stack_lab/gateway/app/core.py, full_stack_lab/gateway/app/main.py
- research/llm-wiki/status/backlog.md

DEV-136 결과 네 축, DEV-67의 보존/만료, DEV-68의 공급자 보증 변경을 main에서 유지하면서 D-138과 두 위치 정책 항목을 추가한다. 게이트웨이 파일은 main의 실행 결과·보증 필드 변경을 보존한 뒤 DEV-69 위치 생성/표시/재판정 변경만 재적용한다. DECISIONS.md·POLICY.md는 양쪽 끝부분의 새 섹션을 모두 보존하고 번호·정책 목록을 확인한다. backlog는 DEV-69 상태 셀만 반영한다. OPA·레지스트리·신규 시험 파일은 이 비교에서 main의 동시 변경 파일이 아니었다.

## 검증 범위와 한계

- 읽은 변경: git diff 09220f5..HEAD; main 비교 기준은 로컬 ref origin/main=a020458.
- 우선순위 중복은 정책 원장 JSON을 정적으로 읽어 확인했다. Rego 실행·기존 시험·게이트웨이 통합·화면 렌더링·배포·PJ1은 실행하지 않았다.
- 로컬 origin/main ref 외 원격 최신성은 확인하지 않았다. 서버 상태와 분류는 작업 지시의 현장 상태를 전제로 했다.
