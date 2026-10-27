# METADATA
# title: 공통 판정 도구
# description: |
#   모든 체크포인트 패키지가 쓰는 결과 형식, 판정 집계, 예외·허용 목록의 기간 처리, 값 누락 검사, 주소 검사.
#   시트 「정책 실행 규칙」의 판정 원칙을 코드로 옮긴 것이다:
#     - 기준 미충족·필수값 누락·검증 실패는 현재 요청만 차단한다(fail-closed).
#     - 모든 예외·허용 항목은 정책 ID·대상·범위·종료일을 가지며, 만료 항목은 조회에서 빠진다.
#     - 예외의 최종 승인 주체는 정책마다 정해져 있다(보안 관리자 / 자료 소유 부서 / 예외 없음).
package mcp.pol.lib

import data.mcp.pol.catalog
import rego.v1

# ---------------------------------------------------------------------------
# 결과 형식
# ---------------------------------------------------------------------------

# 효과의 강도. 한 요청에 여러 정책이 걸리면 가장 강한 효과가 최종 결과다.
#   DENY     차단(시트의 차단·거부·중단)
#   MANUAL   사람 판단 전까지 차단(시트의 「보안 관리자 판단 전까지 차단」)
#   CONFIRM  요청 사용자 본인의 확인을 받은 뒤 한 번 진행(시트 POL-053·054)
#   RESTRICT 제한 허용(시트의 「공개자료 조회만 허용」·「한도까지 제한」)
#   ALERT    진행하되 경보
rank := {"DENY": 5, "MANUAL": 4, "CONFIRM": 3, "RESTRICT": 2, "ALERT": 1}

finding(pol_id, effect, reason) := {"policy_id": pol_id, "effect": effect, "reason": reason}

# 체크포인트 패키지의 findings를 하나의 결과로 모은다. 모르는 효과는 차단으로 센다:
# 오타 하나로 차단이 사라지는 일을 막기 위해서다.
# policy_ids·reasons는 최종 효과를 낸 정책만, all_policy_ids는 걸린 정책 전부다(감사 기록용 —
# DENY에 가려진 MANUAL·CONFIRM도 남긴다).
decide(findings) := {"effect": "ALLOW", "policy_ids": [], "reasons": [], "all_policy_ids": []} if {
	count(findings) == 0
}

decide(findings) := {"effect": effect, "policy_ids": ids, "reasons": reasons, "all_policy_ids": all_ids} if {
	count(findings) > 0
	top := max({strength(f.effect) | some f in findings})
	effect := effect_of(top)
	ids := sort({f.policy_id | some f in findings; strength(f.effect) == top})
	reasons := sort({sprintf("%s: %s", [f.policy_id, f.reason]) | some f in findings; strength(f.effect) == top})
	all_ids := sort({f.policy_id | some f in findings})
}

strength(effect) := rank[effect] if rank[effect]

strength(effect) := 5 if not rank[effect]

effect_of(n) := e if {
	some e, v in rank
	v == n
}

# ---------------------------------------------------------------------------
# 입력 계약
# ---------------------------------------------------------------------------

# 판정 입력은 게이트웨이가 검증된 출처에서만 만든다. trusted 표식과 현재 시각이 없으면 어떤 규칙도 믿을 수 없다.
base_contract_ok if {
	input.facts.trusted == true
	is_number(input.facts.now_ns)
}

now := input.facts.now_ns

# 값이 없거나 비었으면 「확인 불가」. 0과 false는 값이 있는 것으로 본다(불리언·수치 항목용).
filled(obj, key) if {
	v := object.get(obj, key, null)
	v != null
	v != ""
	v != []
	v != {}
}

missing(obj, keys) := {k | some k in keys; not filled(obj, k)}

# 사람이 적는 기록 항목(문서·승인 기록·표시 정보)은 비어 있지 않은 문자열이나 비어 있지 않은 배열이어야 한다.
# false·0·{}는 「기록했다」로 보지 않는다.
written(obj, key) if {
	v := object.get(obj, key, null)
	is_string(v)
	trim_space(v) != ""
}

written(obj, key) if {
	v := object.get(obj, key, null)
	is_array(v)
	count(v) > 0
}

unwritten(obj, keys) := {k | some k in keys; not written(obj, k)}

text(v) if {
	is_string(v)
	trim_space(v) != ""
}

# 0 이상의 정수(카운터·한도). 음수·소수·문자열은 집계 오류로 본다.
count_value(v) if {
	is_number(v)
	v >= 0
	v == floor(v)
}

# 배열이 아닌 값을 빈 배열로 바꾼다. 「없음」과 「확인 불가」를 가르는 규칙은 이것을 쓰지 않는다.
array_or_empty(v) := v if is_array(v)

array_or_empty(v) := [] if not is_array(v)

subset(items, allowed) if {
	is_array(items)
	is_array(allowed)
	every item in items {
		item in allowed
	}
}

# ---------------------------------------------------------------------------
# 기간·예외
# ---------------------------------------------------------------------------

# 종료일 전이고(종료일 필수), 시작일이 있으면 시작일 뒤인 항목.
in_period(e) if {
	is_number(e.not_after_ns)
	now < e.not_after_ns
	started(e)
}

started(e) if not "not_before_ns" in object.keys(e)

started(e) if {
	is_number(e.not_before_ns)
	e.not_before_ns <= now
}

# 허용 목록·권한표·등록부 항목의 승인. 시트 판정 원칙: 모든 허용 항목은 정책 ID·대상·범위·종료일을 갖고,
# 만료 항목은 조회에서 빠진다. 여기에 승인 상태·승인자와, 시트가 그 정책에 정한 승인 주체
# (보안 관리자·자료 소유 부서)를 더해 본다. 「예외 심사 대상 아님」 정책의 목록은 주체를 따지지 않는다.
approved_entry(e, pol_id) if {
	in_period(e)
	e.status == "approved"
	text(e.approved_by)
	role_matches(e, pol_id)
}

role_matches(_, pol_id) if catalog.policies[pol_id].exception_approver == "none"

role_matches(e, pol_id) if {
	catalog.policies[pol_id].exception_approver in {"security_admin", "data_owner"}
	e.approved_by_role == catalog.policies[pol_id].exception_approver
}

approved(entries, pol_id) := [e |
	some e in array_or_empty(entries)
	approved_entry(e, pol_id)
]

# 판정을 건너뛰는 시한부 예외. 시트의 「예외 심사」는 대부분 승인 목록을 바꾸는 절차이므로(승인 전에는 차단)
# 이 함수는 예외 자체가 정책인 곳(POL-013 예외 승인, POL-070 기한 연장)에서만 쓴다.
exception_for(pol_id, target, scope_item) if {
	catalog.policies[pol_id].exception_approver in {"security_admin", "data_owner"}
	some e in approved(data.pol.exceptions, pol_id)
	e.policy_id == pol_id
	e.target == target
	scope_item in e.scope
}

# ---------------------------------------------------------------------------
# 주소
# ---------------------------------------------------------------------------

# 공인 주소가 아닌 대역: 루프백·사설·링크 로컬·CGNAT·벤치마크·문서용·멀티캐스트·예약.
# IPv4 매핑 IPv6(::ffff:0:0/96)는 넣지 않는다: Go의 net은 IPv4 주소를 그 형태로 다뤄 모든 IPv4가 걸린다.
# "::ffff:10.0.0.1" 같은 매핑 주소는 위 IPv4 대역이 그대로 잡는다(시험 test_pol_023_block_ipv4_mapped_private).
protected_cidrs := [
	"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
	"192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
	"224.0.0.0/4", "240.0.0.0/4",
	"::/128", "::1/128", "64:ff9b::/96", "100::/64", "2001:db8::/32", "fc00::/7", "fe80::/10", "ff00::/8",
]

# 단일 주소만 인정한다. cidr_contains는 두 번째 인자로 대역("8.8.8.0/24")도 받기 때문이다.
valid_ip(ip) if {
	is_string(ip)
	not contains(ip, "/")
	net.cidr_contains("0.0.0.0/0", ip)
}

valid_ip(ip) if {
	is_string(ip)
	not contains(ip, "/")
	net.cidr_contains("::/0", ip)
}

protected_ip(ip) if {
	some c in protected_cidrs
	net.cidr_contains(c, ip)
}

# 해석된 주소가 하나 이상 있고 모두 올바른 공인 주소일 때만 참이다. 형식이 틀린 값은 공인으로 보지 않는다.
all_public(ips) if {
	is_array(ips)
	count(ips) > 0
	every ip in ips {
		valid_ip(ip)
		not protected_ip(ip)
	}
}

# 승인 대역이 정해져 있으면 해석된 주소가 모두 그 안이어야 한다(시트 「승인 주소·허용 IP 범위」).
within_ranges(_, ranges) if not is_array(ranges)

within_ranges(ips, ranges) if {
	is_array(ranges)
	every ip in ips {
		some r in ranges
		net.cidr_contains(r, ip)
	}
}

# ---------------------------------------------------------------------------
# Rego의 not 함정 (이 패키지 전체의 작성 규칙)
# ---------------------------------------------------------------------------
# `not a.b == "x"`처럼 == 비교만 있는 식은 a.b가 없어도 not이 참이 된다. 그러나 `in`·함수·내장 함수
# (is_array·count·object.get 밖의 모든 호출)는 인자가 정의되지 않으면 OPA가 호출을 not 밖으로 끌어내
# 규칙 전체가 정의되지 않는다 — 차단해야 할 때 아무 결과도 나오지 않는다(fail-open).
# 그래서 not 안의 호출 인자는 항상 object.get(…, 기본값)으로 정의된 값을 넘기거나 보조 규칙으로 감싼다.
# object.get도 첫 인자가 객체가 아니면(null·문자열) 오류 → 정의되지 않음이 되므로, 중간 값이 null일 수 있으면
# 보조 규칙으로 감싼다. sprintf 등 결과 식별값도 같다(값이 없으면 결과 자체가 사라진다).
# 「검사 완료」와 「결과 목록」은 함께 본다 — 완료인데 목록이 없거나 배열이 아니면 무탐지가 아니라 확인 불가다.
# 각 정책의 시험에는 값이 빠진 반례가 있어야 한다.
