# METADATA
# title: 실행 및 통제 — 호출마다
# description: |
#   게이트웨이 mcp.decision이 모으는 형식({policy_id, effect: DENY|APPROVAL|ALERT})의 findings를 낸다.
#   새 팩은 decision.rego의 all_findings에 한 줄 추가로 붙는다.
#   input.facts는 게이트웨이가 검증된 출처에서만 채운다(인자 해시도 게이트웨이가 정규화한 요청에서 계산).
package mcp.pol.call

import rego.v1

req := input.request

facts := input.facts

# METADATA
# title: 민감 작업 확인값 — 같은 호출·같은 값·1회·기간 안
# description: |
#   1회 소비의 원자성은 Rego가 보장하지 못한다. Rego는 「미사용으로 예약된 확인값」만 인정하고,
#   예약(잠금·상태 변경)은 게이트웨이가 판정 전에 한다(제품의 dispatch 예약과 같은 방식).
# custom:
#   pol_id: [POL-052, POL-053]
#   risk_id: [RSK-09, RSK-39]
findings contains {"policy_id": "POL-053", "effect": "APPROVAL"} if {
	req.operation in {"delete", "share", "external_send"}
	not confirmation_valid
}

confirmation_valid if {
	c := facts.confirmation
	c.reserved_for == req.id
	facts.now_ns < c.expires_ns

	# 시트는 관리자 승인이 아니라 「해당 사용자의 명시적 동의」를 요구한다.
	c.confirmed_by == facts.identity.user
	c.server_id == req.server_id
	c.tool == req.tool
	c.operation == req.operation
	c.target == req.target
	c.recipient == req.recipient
	c.arguments_sha256 == facts.arguments_sha256
}

# METADATA
# title: 결과 수·크기 한도 — 응답 단계
# description: 요청한 수가 아니라 실제 반환된 수·바이트를 본다. Tool별 한도가 없으면 기본 한도를 쓴다.
# custom:
#   pol_id: POL-048
#   risk_id: RSK-37
findings contains {"policy_id": "POL-048", "effect": "DENY"} if {
	input.stage == "response"
	over_limit(input.response, tool_limit(req.tool))
}

# object.get(data, …)은 data 전체(시험 포함)를 읽어 순환이 되므로 경로를 직접 쓴다. 한도가 없으면 빈 객체.
tool_limit(tool) := l if {
	l := data.result_limits[tool]
} else := l if {
	l := data.default_result_limit
} else := {}

over_limit(resp, limit) if resp.items > limit.max_items

over_limit(resp, limit) if resp.bytes > limit.max_bytes

# 크기를 모르면 한도 안이라고 볼 수 없다. 빠진 키는 object.get으로 null로 바꿔야 not이 「모름」을 잡는다.
over_limit(resp, _) if not is_number(object.get(resp, "items", null))

over_limit(resp, _) if not is_number(object.get(resp, "bytes", null))

# 한도가 정해지지 않았으면 기본 한도도 없는 것이다 — 통과시키지 않는다.
over_limit(_, limit) if not is_number(object.get(limit, "max_items", null))

over_limit(_, limit) if not is_number(object.get(limit, "max_bytes", null))

# METADATA
# title: 감사 기록 불가 시 새 호출 차단(제한된 예시)
# description: |
#   저장소의 상태 표시만 본다. 「현재 호출의 기록 성공」과 진행 중 호출 중단은 솔루션(원장·실행기)이 한다.
# custom:
#   pol_id: [POL-057, POL-059]
#   risk_id: RSK-42
findings contains {"policy_id": "POL-057", "effect": "DENY"} if {
	not facts.audit.central_writable == true
	not facts.audit.buffer_writable == true
}

# METADATA
# title: 서버 간 인증정보 전달 금지
# custom:
#   pol_id: POL-043
#   risk_id: RSK-32
findings contains {"policy_id": "POL-043", "effect": "DENY"} if {
	req.source_server != req.server_id
	facts.data.contains_credential == true
}
