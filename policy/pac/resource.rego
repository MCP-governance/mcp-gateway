# METADATA
# title: Resource·Prompt — 서버 제공 템플릿과 자료
# description: |
#   현재 게이트웨이는 Resource·Prompt를 중개하지 않아 모두 거부한다(시트 분류 「구현 불가·제외」의 사유).
#   이 패키지는 중개를 도입할 때 붙일 판정이다. 그때까지는 어떤 경로도 이 패키지의 ALLOW로 열리지 않는다.
#   input.request.stage:
#     prompt_use       서버 제공 Prompt 템플릿을 쓰기 전
#     resource_read    Resource 내용을 반환하기 전
#     resource_list    Resource 목록을 돌려주기 전
#     resource_update  Resource 내용·출처 변경을 반영하기 전
#   데이터: data.pol.servers[서버 ID].prompts / resource_sources.
# scope: package
package mcp.pol.resource

import data.mcp.pol.lib
import rego.v1

req := input.request

facts := input.facts

stage := req.stage

default reg := {}

reg := data.pol.servers[req.server_id]

decision := lib.decide(findings)

# METADATA
# title: 입력 계약
findings contains lib.finding("INPUT_CONTRACT", "DENY", "Resource·Prompt 입력 계약 위반") if not contract_ok

contract_ok if {
	lib.base_contract_ok
	is_object(req)
	req.stage in {"prompt_use", "resource_read", "resource_list", "resource_update"}
	every k in ["user", "server_id"] {
		is_string(req[k])
		req[k] != ""
	}
}

# METADATA
# title: Prompt 템플릿 승인본
# description: 템플릿 내용 해시가 승인본과 같고, 차단된 지시 유형이 없고, 요청 사용자에게 사용 권한이 있을 때만 쓴다. 미승인 변경본은 재심사 전까지 쓰지 않는다.
# custom:
#   pol_id: [POL-007, POL-067]
#   risk_id: [RSK-06, RSK-47]
#   checkpoint: Prompt 템플릿 도입·갱신 심사, 서버 제공 Prompt 템플릿 변경 시
findings contains lib.finding("POL-067", "DENY", "승인본과 다른 Prompt 템플릿") if {
	stage == "prompt_use"
	not prompt_matches_approved
}

findings contains lib.finding("POL-007", "DENY", "차단된 지시 유형") if {
	stage == "prompt_use"
	not facts.prompt_scan.blocked_types == []
}

findings contains lib.finding("POL-007", "DENY", "Prompt 사용 권한 없음") if {
	stage == "prompt_use"
	not prompt_acl_ok
}

prompt_matches_approved if {
	lib.text(req.prompt)
	lib.text(facts.prompt_sha256)
	reg.prompts[req.prompt].sha256 == facts.prompt_sha256
}

# 권한 조회 결과는 이번 요청의 사용자와 대상(Prompt 이름·Resource ID)에 대한 것이어야 한다.
prompt_acl_ok if {
	facts.acl.user_can == true
	facts.acl.user == req.user
	lib.text(req.prompt)
	facts.acl.prompt == req.prompt
}

resource_acl_ok if {
	facts.acl.user_can == true
	facts.acl.user == req.user
	facts.acl.resource_id == facts.resource.resolved_id
}

# METADATA
# title: Resource 반환의 사용자 권한
# custom:
#   pol_id: POL-043
#   risk_id: RSK-38
#   checkpoint: Resource 내용을 반환하기 시
findings contains lib.finding("POL-043", "DENY", "권한 없음·파일 ID 판정 실패") if {
	stage == "resource_read"
	not resource_readable
}

resource_readable if {
	lib.text(facts.resource.resolved_id)
	resource_acl_ok
}

# METADATA
# title: 변경된 Resource 목록의 노출
# description: 목록에는 지금 사용자에게 허용되고 삭제되지 않은 Resource만 둔다. 삭제 목록을 모르면(배열 아님) 차단한다.
# custom:
#   pol_id: POL-065
#   risk_id: RSK-31
#   checkpoint: Resource 목록 추가·삭제·변경 시
findings contains lib.finding("POL-065", "DENY", "삭제·권한 밖 Resource 노출") if {
	stage == "resource_list"
	not resource_list_ok
}

resource_list_ok if {
	lib.subset(input.response.resources, facts.permitted_resources)
	is_array(facts.deleted_resources)
	every r in input.response.resources {
		not r in facts.deleted_resources
	}
}

# METADATA
# title: 중요 Resource의 출처·변경 범위
# custom:
#   pol_id: POL-066
#   risk_id: RSK-46
#   checkpoint: 중요 Resource 내용·출처 변경 시
findings contains lib.finding("POL-066", "DENY", "미승인 출처·변경 범위") if {
	stage == "resource_update"
	not resource_change_approved
}

resource_change_approved if {
	facts.change.source in reg.resource_sources
	facts.change.within_approved_scope == true
}
