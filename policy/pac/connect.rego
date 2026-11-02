# METADATA
# title: 등록 및 연결 — 서버 연결·승인 기록·로컬 실행·OAuth
# description: |
#   input.connection.stage 하나를 판정한다.
#     connect  게이트웨이가 MCP 서버 연결(세션)을 열기 전 — 승인 목록·주소·신원·전송 방식·사용자 동의·권한 범위·예외
#     approve  서버 연결 승인을 활성화하기 전 — 승인 기록의 필수 항목
#     launch   로컬 MCP 서버를 시작하기 전 — 승인 실행 설정·실제 권한·격리
#     oauth    원격 서버의 OAuth 인증 서버 선택·메타데이터 조회·scope 요청 전
#     restore  Agent·Gateway 설정을 백업에서 복원한 뒤 그 설정으로 연결·호출하기 전 — 서버마다 한 번
#   입력: input.connection, input.approval(approve), input.facts(now_ns, trusted).
#   데이터: data.pol.servers[서버 ID] 승인 등록부, data.pol.exceptions.
# scope: package
package mcp.pol.connect

import data.mcp.pol.lib
import rego.v1

conn := input.connection

stage := conn.stage

# 등록부에 없는 서버는 빈 객체다. 아래 not 안의 호출 인자가 항상 정의되도록 하기 위해서다(lib.rego 끝의 작성 규칙).
default reg := {}

reg := data.pol.servers[conn.server_id]

decision := lib.decide(findings)

# METADATA
# title: 입력 계약
findings contains lib.finding("INPUT_CONTRACT", "DENY", "연결 입력 계약 위반") if not contract_ok

contract_ok if {
	lib.base_contract_ok
	is_object(conn)
	conn.stage in {"connect", "approve", "launch", "oauth", "restore"}
	is_string(conn.server_id)
	conn.server_id != ""
}

# METADATA
# title: 승인 서버 목록·상태·신원·기간
# description: 등록부에 있고 운영 상태이며 신원과 승인 기간이 맞을 때만 연결한다. 미승인·만료·신원 불일치는 차단.
# custom:
#   pol_id: POL-R-01
#   risk_id: RSK-R-01
#   checkpoint: Gateway 서버 연결 요청 시
findings contains lib.finding("POL-R-01", "DENY", "미승인·만료·신원 불일치 서버") if {
	stage == "connect"
	not server_approved
}

server_approved if {
	reg.state == "active"
	lib.text(reg.identity)
	reg.identity == conn.identity
	lib.approved_entry(reg.approval, "POL-R-01")
}

# METADATA
# title: 예외 승인에 근거한 연결의 만료
# description: 일반 승인이 아니라 예외 승인에 근거한 연결은 예외가 기간 안이고 범위가 현재 요청과 같아야 한다. 종료일을 확인할 수 없으면 차단.
# custom:
#   pol_id: POL-R-02
#   risk_id: RSK-R-01
#   checkpoint: 예외 승인 만료 판정 및 연결·Tool 실행 전
findings contains lib.finding("POL-R-02", "DENY", "예외 승인 만료·확인 불가·범위 불일치") if {
	stage in {"connect", "launch"}
	conn.approval.basis == "exception"
	not lib.exception_for("POL-R-02", conn.server_id, stage)
}

findings contains lib.finding("POL-R-02", "DENY", "승인 근거 확인 불가") if {
	stage in {"connect", "launch"}
	not object.get(conn, ["approval", "basis"], null) in {"normal", "exception"}
}

# METADATA
# title: 연결 승인 기록의 필수 항목
# description: 대상·목적·허용 범위·적용 정책 버전·승인 방식이 기록돼야 승인을 활성화한다. 예외 승인은 최종 승인자와 종료일도 필수. 기록에 실패하면 활성화하지 않는다.
# custom:
#   pol_id: POL-R-03
#   risk_id: RSK-R-01
#   checkpoint: MCP 서버 연결 승인 결정 시
findings contains lib.finding("POL-R-03", "DENY", concat(", ", sort(gaps))) if {
	stage == "approve"
	gaps := lib.unwritten(object.get(input, "approval", {}), ["server_id", "purpose", "scope", "policy_version", "method"])
	count(gaps) > 0
}

findings contains lib.finding("POL-R-03", "DENY", "다른 서버의 승인 기록") if {
	stage == "approve"
	not input.approval.server_id == conn.server_id
}

findings contains lib.finding("POL-R-03", "DENY", "예외 승인의 최종 승인자·종료일 누락") if {
	stage == "approve"
	input.approval.method == "exception"
	not exception_record_complete
}

findings contains lib.finding("POL-R-03", "DENY", "승인 기록 저장 실패") if {
	stage == "approve"
	not input.approval.recorded == true
}

findings contains lib.finding("POL-R-03", "DENY", "알 수 없는 승인 방식") if {
	stage == "approve"
	not object.get(input, ["approval", "method"], null) in {"auto", "manual", "exception"}
}

exception_record_complete if {
	lib.text(input.approval.approver)
	is_number(input.approval.not_after_ns)
	input.approval.not_after_ns > lib.now
}

# METADATA
# title: 승인 인증 서버
# description: 인증 서버의 주소와 ID가 이 서버에 승인된 인증 서버 목록과 일치해야 인증 요청을 보낸다. 신규 인증 서버는 보안 관리자가 등록부에 올린 뒤에만 쓴다.
# custom:
#   pol_id: POL-R-08
#   risk_id: RSK-R-05
#   checkpoint: 인증 서버 선택·접속 전
findings contains lib.finding("POL-R-08", "DENY", "미승인 인증 서버") if {
	stage == "oauth"
	not auth_server_approved
}

auth_server_approved if {
	some a in reg.auth_servers
	a.address == conn.auth_server.address
	a.id == conn.auth_server.id
}

# METADATA
# title: 인증 서버 정보 조회 목적지
# description: 메타데이터 조회 주소가 승인 조회 목적지일 때만 조회한다.
# custom:
#   pol_id: POL-R-11
#   risk_id: RSK-R-06
#   checkpoint: 인증 서버 정보 조회 시
findings contains lib.finding("POL-R-11", "DENY", "미승인 인증 서버 정보 조회 주소") if {
	stage == "oauth"
	not metadata_request_approved
}

metadata_request_approved if conn.metadata.request_host in reg.metadata_hosts

# METADATA
# title: 인증 서버 정보 조회의 DNS·리다이렉트 뒤 최종 접속지
# description: 최종 접속 호스트가 승인 목적지이고 해석된 IP가 모두 공인 주소여야 한다. 해석 결과가 없으면 차단.
# custom:
#   pol_id: POL-R-12
#   risk_id: RSK-R-06
#   checkpoint: 인증 서버 정보 조회의 DNS·리다이렉트 후
findings contains lib.finding("POL-R-12", "DENY", "내부 보호 주소 또는 미승인 최종 접속지") if {
	stage == "oauth"
	not metadata_final_ok
}

metadata_final_ok if {
	conn.metadata.final_host in lib.array_or_empty(reg.metadata_hosts)
	lib.all_public(conn.metadata.resolved_ips)
}

# METADATA
# title: 연결 권한 범위
# description: 연결이 사용자·Agent에게 주는 Tool·자료 접근권한과 OAuth scope가 업무별 승인 범위 안이어야 연결·인증을 진행한다. 범위 확대는 보안 관리자가 등록부의 승인 범위를 바꾼 뒤에만.
# custom:
#   pol_id: POL-R-15
#   risk_id: RSK-E-01
#   checkpoint: 연결 권한 요청·갱신 시
findings contains lib.finding("POL-R-15", "DENY", sprintf("승인 범위 밖 권한: %v", [p])) if {
	stage == "connect"
	some p in lib.array_or_empty(conn.requested_access)
	not p in lib.array_or_empty(object.get(reg, "approved_access", []))
}

findings contains lib.finding("POL-R-15", "DENY", "요청 권한 확인 불가") if {
	stage == "connect"
	not is_array(object.get(conn, "requested_access", null))
}

findings contains lib.finding("POL-R-15", "DENY", sprintf("승인 범위 밖 scope: %v", [s])) if {
	stage == "oauth"
	some s in lib.array_or_empty(conn.requested_scopes)
	not s in lib.array_or_empty(object.get(reg, "approved_scopes", []))
}

findings contains lib.finding("POL-R-15", "DENY", "요청 scope 확인 불가") if {
	stage == "oauth"
	not is_array(object.get(conn, "requested_scopes", null))
}

# METADATA
# title: 연결 방식별 기본 설정
# description: 원격은 HTTPS만, 로컬은 승인된 실행 설정이 등록부에 있을 때만 시작한다.
# custom:
#   pol_id: POL-R-18
#   risk_id: RSK-R-09
#   checkpoint: 원격 연결·로컬 서버 시작 시
findings contains lib.finding("POL-R-18", "DENY", "원격 평문 연결") if {
	stage == "connect"
	conn.kind == "remote"
	not conn.transport.scheme == "https"
}

findings contains lib.finding("POL-R-18", "DENY", "로컬 승인 실행 설정 없음") if {
	stage in {"connect", "launch"}
	conn.kind == "local"
	not launch_registered
}

# 빈 설정·빈 해시를 승인 설정으로 보지 않는다.
launch_registered if {
	lib.text(reg.launch.executable)
	is_array(reg.launch.args)
	is_object(reg.launch.env)
	lib.text(reg.launch.sha256)
}

findings contains lib.finding("POL-R-18", "DENY", "알 수 없는 연결 방식") if {
	stage in {"connect", "launch"}
	not object.get(conn, "kind", null) in {"remote", "local"}
}

# METADATA
# title: 로컬 서버 시작 설정
# description: 실제 실행 파일·인자·환경 변수·실행 파일 해시가 승인 설정과 모두 같아야 시작한다.
# custom:
#   pol_id: POL-R-20
#   risk_id: RSK-R-11
#   checkpoint: 로컬 서버 시작·설정 변경 시
findings contains lib.finding("POL-R-20", "DENY", sprintf("승인 실행 설정과 다름: %s", [k])) if {
	stage == "launch"
	some k in ["executable", "args", "env", "sha256"]
	not launch_field_matches(k)
}

findings contains lib.finding("POL-R-20", "DENY", "실행 파일 해시 확인 불가") if {
	stage == "launch"
	not launch_hash_known
}

launch_field_matches(k) if conn.launch[k] == reg.launch[k]

launch_hash_known if {
	lib.text(conn.launch.sha256)
	lib.text(reg.launch.sha256)
}

# METADATA
# title: 로컬 서버의 실제 권한과 격리
# description: 실제 권한이 승인 범위 안이면 허용. 권한을 확인할 수 없거나 넘어도 승인 격리 환경이 공개자료 조회만 강제하면 제한 허용, 아니면 실행 차단.
# custom:
#   pol_id: POL-I-08
#   risk_id: RSK-I-07
#   checkpoint: 로컬 서버 시작 및 Tool 호출 전
findings contains lib.finding("POL-I-08", "RESTRICT", "권한 초과·미확인 — 격리 환경에서 공개자료 조회만") if {
	stage == "launch"
	not permissions_within_approval
	isolation_enforced
}

findings contains lib.finding("POL-I-08", "DENY", "과도한 권한이고 격리를 강제할 수 없음") if {
	stage == "launch"
	not permissions_within_approval
	not isolation_enforced
}

permissions_within_approval if lib.subset(conn.launch.observed_permissions, reg.permissions)

isolation_enforced if {
	conn.launch.isolation.verified == true
	conn.launch.isolation.public_read_only == true
	conn.launch.isolation.internal_data_blocked == true
}

# METADATA
# title: 사용자 연결 승인 화면과 동의
# description: 제공자·주소·기능이 표시됐고 사용자가 바로 이 서버에 동의했을 때만 연결한다.
# custom:
#   pol_id: POL-R-21
#   risk_id: RSK-R-12
#   checkpoint: 사용자 서버 연결 동의 전
findings contains lib.finding("POL-R-21", "DENY", "필수 정보 미표시 또는 이 서버에 대한 동의 없음") if {
	stage == "connect"
	not consent_given
}

consent_given if {
	c := conn.consent
	is_object(c.shown)
	count(lib.unwritten(c.shown, ["provider", "address", "functions"])) == 0
	c.decision == "accept"
	c.server_id == conn.server_id
}

# METADATA
# title: 동의의 재사용 범위
# description: 동의한 사용자·서버·기능이 지금 요청과 같고 기간 안일 때만 이전 동의를 쓴다.
# custom:
#   pol_id: POL-R-22
#   risk_id: RSK-R-12
#   checkpoint: 사용자 연결 동의 적용 시
findings contains lib.finding("POL-R-22", "DENY", "동의 대상 불일치 또는 기간 만료") if {
	stage == "connect"
	not consent_applies
}

consent_applies if {
	c := conn.consent
	is_string(conn.user)
	c.user == conn.user
	c.server_id == conn.server_id
	lib.subset(conn.requested_functions, c.functions)
	lib.in_period(c)
}

# METADATA
# title: 운영 서버 접속 주소 변경
# description: 연결하려는 주소가 승인 등록부의 주소와 같아야 한다. 새 주소는 보안 관리자가 등록부에 반영(재승인)한 뒤에만 연결한다.
# custom:
#   pol_id: POL-O-11
#   risk_id: RSK-O-09
#   checkpoint: 운영 서버 접속 주소 변경·연결 시
findings contains lib.finding("POL-O-11", "DENY", "등록부에 없는 새 접속 주소") if {
	stage == "connect"
	not conn.address == reg.address
}

# METADATA
# title: 서버별 인증정보 귀속(연결 단계)
# description: 연결에 쓰는 인증정보가 바로 그 서버에 귀속된 것이어야 한다. 인증정보를 쓰지 않는 연결은 used=false로 명시한다.
# custom:
#   pol_id: POL-R-14
#   risk_id: RSK-R-08
#   checkpoint: 서버 연결·토큰 선택 시
findings contains lib.finding("POL-R-14", "DENY", "다른 서버에 귀속됐거나 확인 불가한 인증정보") if {
	stage in {"connect", "oauth"}
	not connect_credential_ok
}

connect_credential_ok if conn.credential.used == false

connect_credential_ok if {
	conn.credential.used == true
	conn.credential.bound_server == conn.server_id
}

# METADATA
# title: 폐기 서버의 신규 연결
# custom:
#   pol_id: POL-D-01
#   risk_id: RSK-D-01
#   checkpoint: 서버·Tool 폐기 결정 시
findings contains lib.finding("POL-D-01", "DENY", "폐기된 서버") if {
	stage in {"connect", "launch", "oauth"}
	reg.state in {"decommissioning", "decommissioned"}
}

# METADATA
# title: 백업에서 복원된 서버 연결
# description: 복원된 주소·허용 Tool·접근권한이 현재 유효한 승인 등록부와 맞고 폐기·만료되지 않은 서버일 때만 복원 설정으로 연결·호출한다. 다시 쓸 연결은 신규 도입·승인을 거친다.
# custom:
#   pol_id: POL-D-09
#   risk_id: RSK-D-09
#   checkpoint: Agent·Gateway 설정의 백업 복원 직후 및 연결·Tool 호출 전
findings contains lib.finding("POL-D-09", "DENY", "폐기·만료·미승인 연결의 복원") if {
	stage == "restore"
	not restored_server_current
}

findings contains lib.finding("POL-D-09", "DENY", "복원 설정이 현재 승인과 다르거나 확인 불가") if {
	stage == "restore"
	not restored_config_matches
}

# 승인 기간·승인자는 승인 서버 목록(POL-R-01)의 기준으로 본다.
restored_server_current if {
	reg.state == "active"
	lib.approved_entry(reg.approval, "POL-R-01")
}

restored_config_matches if {
	lib.text(conn.restored.address)
	conn.restored.address == reg.address
	is_array(conn.restored.tools)
	every t in conn.restored.tools {
		reg.tools[t].state == "active"
	}
	lib.subset(conn.restored.access, lib.array_or_empty(object.get(reg, "approved_access", [])))
}
