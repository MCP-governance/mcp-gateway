# METADATA
# title: 실행 및 통제 — Tool 호출 한 건
# description: |
#   input.request.stage 하나를 판정한다.
#     request   Tool 호출을 상위 서버로 보내기 전
#     response  결과를 Agent에 돌려주기 전(반환량)
#     list      Tool 목록을 돌려주기 전
#   입력: input.request(호출 내용), input.facts(게이트웨이가 관측·조회한 값), input.response(response·list).
#   데이터: data.pol.servers(등록부·Tool 정의), permission_table, delegations, document_grants, transfers,
#           flows, server_accounts, rate_limits, default_result_limit, exceptions.
#   신원(user·agent)은 transport의 토큰에서 게이트웨이가 정한 값이어야 한다. 인자에 적힌 신원은 쓰지 않는다.
# scope: package
package mcp.pol.call

import data.mcp.pol.lib
import rego.v1

req := input.request

facts := input.facts

stage := req.stage

sensitive_operations := {"delete", "share", "external_send"}

known_operations := {"read", "write", "delete", "share", "external_send", "execute"}

# 등록부·Tool 정의가 없으면 빈 객체다. not 안의 호출 인자가 항상 정의되도록 하기 위해서다(lib.rego 끝의 작성 규칙).
default reg := {}

reg := data.pol.servers[req.server_id]

default tool := {}

tool := reg.tools[req.tool]

# 대상이 객체가 아니면 빈 객체로 본다(필요한 정책이 값 누락으로 차단한다).
default target := {}

target := req.target if is_object(req.target)

decision := lib.decide(findings)

# METADATA
# title: 입력 계약
findings contains lib.finding("INPUT_CONTRACT", "DENY", "호출 입력 계약 위반") if not contract_ok

contract_ok if {
	lib.base_contract_ok
	is_object(req)
	req.stage in {"request", "response", "list"}
	every k in ["id", "user", "agent", "server_id", "tool"] {
		is_string(req[k])
		req[k] != ""
	}
	operation_known
}

operation_known if req.stage == "list"

operation_known if req.operation in known_operations

is_sensitive if req.operation in sensitive_operations

is_sensitive if tool.sensitive == true

# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------

# METADATA
# title: Tool별 자료·작업 권한표
# description: 사용자·서버·Tool·자료 유형·작업 조합이 자료 소유 부서가 승인한 권한표에 있어야 한다. 권한표를 확인할 수 없으면 차단.
# custom:
#   pol_id: POL-003
#   risk_id: RSK-03
#   checkpoint: Tool 등록·권한 변경 및 호출 시
findings contains lib.finding("POL-003", "DENY", "권한표 밖의 자료·작업 조합") if {
	stage == "request"
	not permission_granted
}

# 권한표 항목은 자료 소유 부서가 승인한 것만 센다(lib.approved). 새 권한은 권한표를 바꾼 뒤에만.
permission_granted if {
	some p in lib.approved(data.pol.permission_table, "POL-003")
	p.user == req.user
	p.server_id == req.server_id
	p.tool == req.tool
	p.data_class == target.data_class
	p.operation == req.operation
}

# METADATA
# title: 사용자·Agent 위임 범위
# description: 사용자·Agent·서버·Tool·자료·작업이 모두 현재 위임 범위 안이고 기간이 유효해야 실행한다.
# custom:
#   pol_id: POL-034
#   risk_id: RSK-24
#   checkpoint: Tool 실행 요청마다
findings contains lib.finding("POL-034", "DENY", "위임 범위 밖 또는 만료") if {
	stage == "request"
	not delegated
}

delegated if {
	some d in lib.approved(data.pol.delegations, "POL-034")
	d.user == req.user
	d.agent == req.agent
	d.server_id == req.server_id
	d.tool == req.tool
	d.data_class == target.data_class
	d.operation == req.operation
}

# METADATA
# title: 호출마다 새로 내린 판정
# description: 저장된 결과가 아니라 이번 호출에 대해 권한 저장소를 새로 조회한 결과여야 한다. 조회 실패면 차단.
# custom:
#   pol_id: POL-035
#   risk_id: RSK-25
#   checkpoint: Tool 호출 시마다
findings contains lib.finding("POL-035", "DENY", "이번 호출의 권한 조회 실패·재사용") if {
	stage == "request"
	not fresh_permission_lookup
}

fresh_permission_lookup if {
	facts.permission_lookup.status == "ok"
	facts.permission_lookup.request_id == req.id
}

# METADATA
# title: 문서 단위 사용 권한
# description: 문서를 다루는 Tool은 대상 문서까지 사용자·Agent·서버·Tool 조합으로 승인돼 있어야 한다. 문서 ID를 모르면 차단.
# custom:
#   pol_id: POL-036
#   risk_id: RSK-24
#   checkpoint: 각 Tool 호출 시
findings contains lib.finding("POL-036", "DENY", "문서 권한 없음·불명확") if {
	stage == "request"
	tool.document_scoped == true
	not document_granted
}

document_granted if {
	is_string(target.doc_id)
	some g in lib.approved(data.pol.document_grants, "POL-036")
	g.user == req.user
	g.agent == req.agent
	g.server_id == req.server_id
	g.tool == req.tool
	g.doc_id == target.doc_id
}

# ---------------------------------------------------------------------------
# 식별·인증
# ---------------------------------------------------------------------------

# METADATA
# title: 예외 승인에 근거한 Tool 실행의 만료
# custom:
#   pol_id: POL-013
#   risk_id: RSK-10
#   checkpoint: 예외 승인 만료 판정 및 연결·Tool 실행 전
findings contains lib.finding("POL-013", "DENY", "예외 승인 만료·확인 불가·범위 불일치") if {
	stage == "request"
	facts.approval.basis == "exception"
	not lib.exception_for("POL-013", req.server_id, req.tool)
}

findings contains lib.finding("POL-013", "DENY", "승인 근거 확인 불가") if {
	stage == "request"
	not object.get(facts, ["approval", "basis"], null) in {"normal", "exception"}
}

# METADATA
# title: 서버 ID와 Tool 이름의 정확한 조합
# description: 승인 Tool 목록에서 서버 ID와 Tool 이름이 정확히 하나만 맞아야 한다. 다른 서버의 같은 이름이나 비슷한 이름은 차단.
# custom:
#   pol_id: POL-015
#   risk_id: RSK-11
#   checkpoint: Agent Tool 선택·호출 시
findings contains lib.finding("POL-015", "DENY", "승인 목록에 없거나 모호한 서버·Tool 조합") if {
	stage == "request"
	not exact_tool_match
}

exact_tool_match if {
	is_object(reg.tools[req.tool])
	facts.catalog.matches == 1
}

# METADATA
# title: 토큰의 유효성과 대상 서버
# custom:
#   pol_id: POL-016
#   risk_id: RSK-12
#   checkpoint: 토큰을 사용하는 원격 요청마다
findings contains lib.finding("POL-016", "DENY", "무효·만료·다른 서버용 토큰") if {
	stage == "request"
	not token_ok
}

# 시트 검사 시점은 「토큰을 사용하는 원격 요청마다」다. 등록부가 로컬로 정한 서버만 토큰 없이 부른다.
token_ok if {
	facts.token.used == false
	reg.kind == "local"
}

token_ok if {
	facts.token.valid == true
	facts.token.audience == req.server_id
	is_number(facts.token.expires_ns)
	lib.now < facts.token.expires_ns
}

# METADATA
# title: 서버별 인증정보 귀속
# description: 상위 서버에 쓰는 인증정보가 바로 그 서버에 귀속된 것이어야 한다. 인증정보를 쓰지 않는 호출은 used=false로 명시한다.
# custom:
#   pol_id: POL-025
#   risk_id: RSK-19
#   checkpoint: 서버 연결·토큰 선택 시
findings contains lib.finding("POL-025", "DENY", "다른 서버에 귀속된 인증정보") if {
	stage == "request"
	not credential_ok
}

credential_ok if facts.credential.used == false

credential_ok if {
	facts.credential.used == true
	facts.credential.bound_server == req.server_id
}

# ---------------------------------------------------------------------------
# 입력 내용
# ---------------------------------------------------------------------------

# METADATA
# title: 외부 내용을 권한 변경·승인 입력으로 쓰는 흐름
# description: 승인·권한 변경을 뜻하는 요청은 인자에 외부 문서·Tool 결과에서 온 내용이 없다는 관측이 있어야 진행한다.
# custom:
#   pol_id: POL-037
#   risk_id: RSK-26
#   checkpoint: 외부 문서·Tool 결과를 Agent에 전달할 때
findings contains lib.finding("POL-037", "DENY", "외부 내용이 승인·권한 변경 입력으로 쓰임") if {
	stage in {"request", "response"}
	object.get(req, "intent", "call") in {"approval", "permission_change"}
	not facts.provenance.external_content == false
}

findings contains lib.finding("POL-037", "DENY", "알 수 없는 요청 의도") if {
	stage in {"request", "response"}
	not object.get(req, "intent", "call") in {"call", "approval", "permission_change"}
}

# METADATA
# title: 자유 형식 입력의 비밀정보·불필요 개인정보
# description: 입력 검사가 끝나야 하고, 토큰·비밀정보가 남거나 Tool에 승인되지 않은 개인정보 항목이 있으면 전송 차단.
# custom:
#   pol_id: POL-038
#   risk_id: RSK-27
#   checkpoint: 자유 형식 Tool 입력 전송 전
findings contains lib.finding("POL-038", "DENY", "입력 검사 미완료") if {
	stage == "request"
	not facts.inspection.status == "completed"
}

findings contains lib.finding("POL-038", "DENY", "입력 검사 결과 목록 없음") if {
	stage == "request"
	not inspection_lists_ok
}

# 무탐지는 빈 배열로 명시해야 한다. 목록이 없거나 문자열이면 검사 결과를 믿을 수 없다.
inspection_lists_ok if {
	is_array(facts.inspection.secrets)
	is_array(facts.inspection.personal_data)
}

findings contains lib.finding("POL-038", "DENY", "입력에 비밀정보") if {
	stage == "request"
	count(lib.array_or_empty(object.get(facts, ["inspection", "secrets"], []))) > 0
}

findings contains lib.finding("POL-038", "DENY", sprintf("업무 무관 개인정보: %s", [kind])) if {
	stage == "request"
	some kind in lib.array_or_empty(object.get(facts, ["inspection", "personal_data"], []))
	not kind in lib.array_or_empty(object.get(tool, "personal_fields_allowed", []))
}

# METADATA
# title: 명령·API Tool의 작업과 인자
# custom:
#   pol_id: POL-046
#   risk_id: RSK-34
#   checkpoint: 명령·API Tool 호출 시
findings contains lib.finding("POL-046", "DENY", "명령·API로 분류되지 않은 Tool의 실행") if {
	stage == "request"
	req.operation == "execute"
	not object.get(tool, "kind", null) in {"command", "api"}
}

findings contains lib.finding("POL-046", "DENY", "미승인 작업 또는 검증되지 않은 인자") if {
	stage == "request"
	tool.kind in {"command", "api"}
	not command_ok
}

command_ok if {
	req.operation in tool.operations
	facts.arguments_validated == true
}

# METADATA
# title: 승인 입력 스키마
# custom:
#   pol_id: POL-048
#   risk_id: RSK-36
#   checkpoint: Tool 입력 수신 시
findings contains lib.finding("POL-048", "DENY", "스키마 위반·정의되지 않은 항목") if {
	stage == "request"
	not schema_ok
}

schema_ok if {
	facts.schema.valid == true
	facts.schema.undeclared_fields == []
}

# ---------------------------------------------------------------------------
# 목적지·자료 흐름
# ---------------------------------------------------------------------------

# METADATA
# title: 외부 전송의 최종 수신지
# description: 주소 이동 뒤의 최종 호스트가 이 Tool의 승인 수신지이고 해석된 IP가 모두 공인 주소여야 전송한다.
# custom:
#   pol_id: POL-040
#   risk_id: RSK-29
#   checkpoint: Tool의 외부 전송 시과 주소 이동 후
findings contains lib.finding("POL-040", "DENY", "미승인 최종 수신지") if {
	stage == "request"
	req.operation == "external_send"
	not egress_destination_ok
}

# 새 수신지는 보안 관리자가 Tool 정의의 egress_hosts(필요하면 egress_ip_ranges)에 올린 뒤에만.
egress_destination_ok if {
	facts.egress.final_host in tool.egress_hosts
	lib.all_public(facts.egress.resolved_ips)
	lib.within_ranges(facts.egress.resolved_ips, object.get(tool, "egress_ip_ranges", null))
}

# METADATA
# title: 외부 전송의 자료·수신자·목적 조합
# custom:
#   pol_id: POL-041
#   risk_id: RSK-29
#   checkpoint: 자료 외부 전송 시
findings contains lib.finding("POL-041", "DENY", "승인되지 않은 자료·수신자·목적 조합") if {
	stage == "request"
	req.operation == "external_send"
	not transfer_approved
}

transfer_approved if {
	some t in lib.approved(data.pol.transfers, "POL-041")
	t.data_class == target.data_class
	t.recipient == req.recipient
	t.purpose == req.purpose
}

# METADATA
# title: 파일 요청의 실제 경로
# description: 심볼릭 링크와 상위 이동을 푼 실제 경로가 승인 폴더 안이어야 한다. 경로를 받았는데 실제 경로를 모르면 차단.
# custom:
#   pol_id: POL-042
#   risk_id: RSK-30
#   checkpoint: 문서·파일 요청의 경로 해석 후
findings contains lib.finding("POL-042", "DENY", "허용 폴더 밖 파일") if {
	stage == "request"
	file_request
	not path_inside_root
}

# 파일 Tool(승인 폴더가 정해진 Tool)이거나 요청에 경로 항목이 있으면 경로 검사를 한다. 요청 경로가 null이어도 빠지지 않는다.
file_request if is_array(tool.roots)

file_request if "path" in object.keys(target)

path_inside_root if {
	lib.text(target.path)
	resolved := facts.path.resolved
	is_string(resolved)
	not contains(concat("", ["/", resolved, "/"]), "/../")
	some root in tool.roots
	under(resolved, root)
}

under(p, root) if p == root

under(p, root) if startswith(p, concat("", [trim_right(root, "/"), "/"]))

# METADATA
# title: 서버 간 자료·인증정보 전달
# description: 다른 서버에서 온 자료는 출발·수신 서버쌍·자료·목적이 승인된 경우만 넘긴다. 인증정보는 어떤 경우에도 넘기지 않는다.
# custom:
#   pol_id: POL-044
#   risk_id: RSK-32
#   checkpoint: 서버 A의 자료·인증정보를 서버 B에 넘기기 전
findings contains lib.finding("POL-044", "DENY", "인증정보의 서버 간 전달") if {
	stage == "request"
	not facts.data.contains_credential == false
}

findings contains lib.finding("POL-044", "DENY", "승인되지 않은 서버 간 전달") if {
	stage == "request"
	is_string(req.source_server)
	req.source_server != req.server_id
	not flow_approved
}

# 출처 항목이 있는데 서버 ID 형식이 아니면 「서버 간 전달 아님」으로 보지 않는다.
findings contains lib.finding("POL-044", "DENY", "출처 서버 형식 오류") if {
	stage == "request"
	"source_server" in object.keys(req)
	not lib.text(req.source_server)
}

flow_approved if {
	some f in lib.approved(data.pol.flows, "POL-044")
	f.source_server == req.source_server
	f.dest_server == req.server_id
	f.data_class == target.data_class
	f.purpose == req.purpose
}

# METADATA
# title: Tool의 URL 접속 목적지
# custom:
#   pol_id: POL-047
#   risk_id: RSK-35
#   checkpoint: Tool의 URL 접속 전·DNS/주소 이동 후
findings contains lib.finding("POL-047", "DENY", "내부 보호 주소 또는 허용 범위 밖 URL") if {
	stage == "request"
	tool.fetches_url == true
	not url_destination_ok
}

url_destination_ok if {
	facts.egress.final_host in tool.url_destinations
	lib.all_public(facts.egress.resolved_ips)
	lib.within_ranges(facts.egress.resolved_ips, object.get(tool, "url_ip_ranges", null))
}

# ---------------------------------------------------------------------------
# 양·속도
# ---------------------------------------------------------------------------

# METADATA
# title: 한 번당 반환량
# description: 실제 반환 건수와 크기가 한도 이하일 때만 그대로 반환한다. 넘으면 한도까지 제한(RESTRICT), 크기나 한도를 모르면 차단.
# custom:
#   pol_id: POL-049
#   risk_id: RSK-37
#   checkpoint: 문서 조회 결과 반환 시
findings contains lib.finding("POL-049", "RESTRICT", "한도 초과 결과 — 한도까지 제한") if {
	stage == "response"
	sizes_known
	limit_known
	over_result_limit
}

findings contains lib.finding("POL-049", "DENY", "반환량 또는 한도 확인 불가") if {
	stage == "response"
	not sizes_known
}

findings contains lib.finding("POL-049", "DENY", "반환량 또는 한도 확인 불가") if {
	stage == "response"
	not limit_known
}

default result_limit := {}

result_limit := tool.result_limit

result_limit := data.pol.default_result_limit if not tool.result_limit

sizes_known if {
	lib.count_value(input.response.items)
	lib.count_value(input.response.bytes)
}

limit_known if {
	lib.count_value(result_limit.max_items)
	lib.count_value(result_limit.max_bytes)
}

over_result_limit if input.response.items > result_limit.max_items

over_result_limit if input.response.bytes > result_limit.max_bytes

# METADATA
# title: 반복 조회·대량 추출
# description: 사용자·Tool별 시간창 조회 문서 수가 한도 이내이고 차단 패턴이 없을 때만 계속 조회한다.
# custom:
#   pol_id: POL-050
#   risk_id: RSK-37
#   checkpoint: 반복 조회·대량 추출 중
findings contains lib.finding("POL-050", "DENY", "시간창 조회량 초과·차단 패턴·확인 불가") if {
	stage == "request"
	req.operation == "read"
	not volume_ok
}

# 업무별 한도 상향은 자료 소유 부서가 Tool 정의의 window_document_limit을 바꾼 뒤에만.
volume_ok if {
	lib.count_value(facts.usage.window_documents)
	lib.count_value(tool.window_document_limit)
	facts.usage.window_documents <= tool.window_document_limit
	facts.usage.blocked_pattern == false
}

# METADATA
# title: 호출량·동시 실행 상한
# description: 사용자·Agent·Tool 단위 각각의 시간창 호출량과 동시 실행 수가 승인 상한 이내여야 받는다. 상한이나 집계를 모르면 차단.
# custom:
#   pol_id: POL-056
#   risk_id: RSK-41
#   checkpoint: Gateway Tool 호출 수용 전
findings contains lib.finding("POL-056", "DENY", sprintf("%s 단위 호출량·동시 실행 상한 초과·확인 불가", [scope])) if {
	stage == "request"
	some scope in ["user", "agent", "tool"]
	not within_rate(scope)
}

within_rate(scope) if {
	limit := data.pol.rate_limits[scope]
	used := facts.usage[scope]
	lib.count_value(used.window_calls)
	lib.count_value(used.concurrent)
	lib.count_value(limit.window_calls)
	lib.count_value(limit.concurrent)
	used.window_calls <= limit.window_calls
	used.concurrent <= limit.concurrent
}

# ---------------------------------------------------------------------------
# 서버 계정
# ---------------------------------------------------------------------------

# METADATA
# title: 서버 계정으로 여는 문서의 사용자 권한
# description: 서버 계정으로 문서를 열 때 요청 사용자에게도 그 문서 작업 권한이 있어야 한다.
# custom:
#   pol_id: POL-051
#   risk_id: RSK-38
#   checkpoint: 서버 계정으로 문서를 열기 시
findings contains lib.finding("POL-051", "DENY", "사용자에게 없는 문서 권한") if {
	stage == "request"
	not facts.server_account.used == false
	not user_acl_ok
}

# ACL 조회 결과는 이번 요청의 사용자·문서에 대한 것이어야 한다.
user_acl_ok if {
	facts.acl.user_can == true
	facts.acl.user == req.user
	facts.acl.doc_id == target.doc_id
}

# METADATA
# title: 서버 계정의 승인 범위
# custom:
#   pol_id: POL-052
#   risk_id: RSK-38
#   checkpoint: 서버 계정 권한 부여·사용 시
findings contains lib.finding("POL-052", "DENY", "서버 계정 승인 범위 밖 접근") if {
	stage == "request"
	not facts.server_account.used == false
	not server_account_in_scope
}

# 계정 범위 확대는 자료 소유 부서가 server_accounts를 바꾼 뒤에만. documents가 정해져 있으면 문서까지 본다.
server_account_in_scope if {
	scope := data.pol.server_accounts[req.server_id]
	req.operation in scope.operations
	target.data_class in scope.data_classes
	account_document_in_scope(scope)
}

account_document_in_scope(scope) if not "documents" in object.keys(scope)

account_document_in_scope(scope) if target.doc_id in scope.documents

# ---------------------------------------------------------------------------
# 민감 작업의 사용자 확인
# ---------------------------------------------------------------------------

# METADATA
# title: 민감 기능의 사용자 확인 대상 분류(실행 단계)
# description: 삭제·공유·외부 전송 호출인데 Tool이 사용자 확인 대상으로 분류돼 있지 않으면 차단하고, 분류돼 있어도 이번 호출의 확인이 없으면 사용자 확인을 받는다(확인값의 검증은 POL-053·054).
# custom:
#   pol_id: POL-010
#   risk_id: RSK-09
#   checkpoint: 삭제·공유·외부 전송 Tool 호출 시
findings contains lib.finding("POL-010", "DENY", "민감 기능이 사용자 확인 대상으로 분류되지 않음") if {
	stage == "request"
	is_sensitive
	not tool.requires_confirmation == true
}

findings contains lib.finding("POL-010", "CONFIRM", "실행 시 유효한 사용자 확인 필요") if {
	stage == "request"
	is_sensitive
	not is_object(object.get(facts, "confirmation", null))
}

# METADATA
# title: 민감 작업의 사용자 확인과 표시값·실제값 일치
# description: 확인이 없으면 요청 사용자 본인에게 확인을 받는다(CONFIRM). 확인이 있는데 표시한 값과 실제 호출 값이 다르면 차단.
# custom:
#   pol_id: POL-053
#   risk_id: RSK-09
#   checkpoint: 삭제·공유·외부 전송 Tool 실행 시
findings contains lib.finding("POL-053", "CONFIRM", "사용자 본인 확인 필요") if {
	stage == "request"
	is_sensitive
	not is_object(object.get(facts, "confirmation", null))
}

findings contains lib.finding("POL-053", "DENY", "확인한 값과 실제 호출 값이 다름") if {
	stage == "request"
	is_sensitive
	is_object(object.get(facts, "confirmation", null))
	not confirmation_matches_call
}

confirmation_matches_call if {
	c := facts.confirmation
	c.server_id == req.server_id
	c.tool == req.tool
	c.operation == req.operation
	c.target == object.get(target, "doc_id", object.get(target, "path", null))
	c.recipient == object.get(req, "recipient", null)
	c.arguments_sha256 == facts.arguments_sha256
}

# METADATA
# title: 확인값의 주체·1회 사용·기간
# description: 확인값은 요청 사용자 본인이 했고, 이 호출에 예약됐으며, 아직 쓰이지 않았고, 기간 안이어야 한다. 1회 소비의 원자성은 게이트웨이가 판정 전에 예약으로 보장한다.
# custom:
#   pol_id: POL-054
#   risk_id: RSK-39
#   checkpoint: 민감 작업 확인값을 적용할 때
findings contains lib.finding("POL-054", "DENY", "다른 사용자·재사용·만료 확인값") if {
	stage == "request"
	is_object(object.get(facts, "confirmation", null))
	not confirmation_usable
}

confirmation_usable if {
	c := facts.confirmation
	c.confirmed_by == req.user
	c.reserved_for == req.id
	c.used == false
	is_number(c.expires_ns)
	lib.now < c.expires_ns
}

# ---------------------------------------------------------------------------
# 감사·상태
# ---------------------------------------------------------------------------

# METADATA
# title: 감사 기록 불가 시 새 호출 차단
# description: 이번 호출의 실행 전 기록이 중앙 저장소나 보호된 임시 저장소에 저장됐어야 받는다(recorded). 진행 중 호출의 중단과 장애 알림은 게이트웨이(솔루션)가 한다.
# custom:
#   pol_id: POL-058
#   risk_id: RSK-42
#   checkpoint: Tool 호출 허용·거부·실패·예외 시
findings contains lib.finding("POL-058", "DENY", "감사 기록을 남길 저장소 없음") if {
	stage == "request"
	not facts.audit.central_writable == true
	not facts.audit.buffer_writable == true
}

findings contains lib.finding("POL-058", "DENY", "이번 호출의 실행 전 기록 실패") if {
	stage == "request"
	not facts.audit.recorded == true
}

# METADATA
# title: 운영 중 Tool 명세 변경
# custom:
#   pol_id: POL-063
#   risk_id: RSK-44
#   checkpoint: Tool 설명·입력·버전 변경 감지 시
findings contains lib.finding("POL-063", "DENY", "승인값과 다른 Tool 정의") if {
	stage == "request"
	not contract_unchanged
}

contract_unchanged if {
	is_string(tool.approved_contract_sha256)
	facts.catalog.observed_contract_sha256 == tool.approved_contract_sha256
}

# METADATA
# title: 저장된 Tool 목록의 소유자·권한
# description: 목록을 캐시에서 꺼냈다면 그 캐시의 소유자가 지금 사용자여야 하고, 보여 주는 Tool은 모두 지금 사용자에게 허용된 것이어야 한다.
# custom:
#   pol_id: POL-064
#   risk_id: RSK-45
#   checkpoint: 저장된 Tool 목록 조회·재사용 시
findings contains lib.finding("POL-064", "DENY", "다른 사용자 캐시 또는 권한 밖 Tool 노출") if {
	stage == "list"
	not tool_list_ok
}

tool_list_ok if {
	cache_owner_ok
	lib.subset(input.response.tools, facts.permitted_tools)
}

cache_owner_ok if input.response.cached == false

cache_owner_ok if {
	input.response.cached == true
	input.response.cache_owner == req.user
}

# METADATA
# title: 긴급 중지된 서버·Tool
# custom:
#   pol_id: POL-081
#   risk_id: RSK-57
#   checkpoint: 심각한 미승인 변경·비정상 호출 확정 시
findings contains lib.finding("POL-081", "DENY", "긴급 중지된 서버·Tool") if {
	stage in {"request", "list"}
	suspended
}

suspended if reg.state == "suspended"

suspended if tool.state == "suspended"

# METADATA
# title: 폐기된 서버·Tool
# custom:
#   pol_id: POL-082
#   risk_id: RSK-58
#   checkpoint: 서버·Tool 폐기 결정 시
findings contains lib.finding("POL-082", "DENY", "폐기된 서버·Tool") if {
	stage in {"request", "list"}
	retired
}

retired if reg.state in {"decommissioning", "decommissioned"}

retired if tool.state == "retired"
