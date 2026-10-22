"""Reviewed locations and registry-owned policy data. No IP geolocation or caller claims."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# ISO 3166-1 alpha-2 assigned codes; names and unofficial codes do not grant a location.
COUNTRIES = frozenset("""AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP
KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW""".split())


def sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalize(value: dict | None) -> dict:
    value = {} if value is None else value
    keys = {"processing_countries", "storage_countries", "processor", "evidence_ref", "transfer_basis"}
    if not isinstance(value, dict) or set(value) - keys:
        raise ValueError("처리·저장 위치 항목이 올바르지 않습니다.")
    result = {}
    for key in ("processing_countries", "storage_countries"):
        codes = value.get(key, [])
        if not isinstance(codes, list) or len(codes) > 249 or any(not isinstance(c, str) or c not in COUNTRIES for c in codes):
            raise ValueError("국가는 ISO 국가 코드 두 자리 대문자 목록이어야 합니다.")
        result[key] = sorted(set(codes))
    for key in ("processor", "evidence_ref", "transfer_basis"):
        text = value.get(key, "")
        if not isinstance(text, str) or len(text) > 500:
            raise ValueError("처리 주체·위치 근거·이전 근거는 500자 이하여야 합니다.")
        result[key] = text.strip()
    return result


def location(spec: dict, organization: dict) -> dict:
    raw = organization.get("machine_location") if spec.get("deployment") == "internal" else spec.get("residency")
    try:
        return normalize(raw)
    except ValueError:
        return normalize(None)


def load_pack(path: Path = Path("/policy/residency.json"), source: Path | None = Path("/registry/data_residency.json")) -> dict:
    # A missing/broken pack becomes an invalid fact, so OPA can record a named denial.
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))["residency"]
        validate_pack(pack)
        if source is not None and json.loads(source.read_text(encoding="utf-8"))["residency"] != pack:
            return {}
        return pack
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def facts(spec: dict, organization: dict, cls, pack: dict) -> dict:
    server_location = location(spec, organization)
    review = spec.get("residency_review") or {}
    binding = transfer_review_digest(cls.server, spec, server_location, pack)
    # Only the independently reviewed server inherits this grant. Tool destinations
    # remain separate targets even when they happen to name the same country.
    reviewed = bool(binding and isinstance(review, dict) and review.get("reviewed_by")
                    and review.get("approval_sha256") == binding)
    targets = [{"id": cls.server, **server_location, "transfer_reviewed": reviewed}]
    # A server's machine location says nothing about an address passed to a tool.
    for host in sorted({d.host for d in cls.destinations if d.external}):
        try:
            target = normalize((organization.get("destination_locations") or {}).get(host))
        except ValueError:
            target = normalize(None)
        targets.append({"id": host, **target})
    return {"enabled": enabled(organization), "grade": cls.data_class, "targets": targets, "pack_sha256": sha256(pack)}


def transfer_review_digest(server_id: str, spec: dict, value: dict, pack: dict) -> str:
    """A location review is reusable only for this provider and this policy revision."""
    if spec.get("deployment") != "provider" or not spec.get("intake_id") or not spec.get("endpoint"):
        return ""
    try:
        normalized = normalize(value)
        validate_pack(pack)
    except (ValueError, TypeError):
        return ""
    if not all(normalized.values()):
        return ""
    return sha256({"server_id": server_id, "endpoint": spec["endpoint"],
                   "intake_id": spec["intake_id"], "location": normalized, "pack": pack})


def enabled(organization: dict) -> bool:
    return organization.get("jurisdiction_pack_enabled", False) is not False


def require_location(value: dict, grade: str, organization: dict) -> None:
    if enabled(organization) and grade != "public" and not all(value.get(key) for key in (
            "processing_countries", "storage_countries", "processor", "evidence_ref")):
        raise ValueError("처리·저장 위치가 없습니다. 추가 정보에서 위치와 근거를 입력하세요.")


def validate_pack(pack: dict) -> None:
    if not isinstance(pack, dict) or set(pack.get("rules", {})) != {"public", "nonimportant", "important"}:
        raise ValueError("등급별 위치 규칙이 모두 필요합니다.")
    home = pack.get("home_countries")
    if not isinstance(home, list) or not home or any(c not in COUNTRIES for c in home):
        raise ValueError("조직 소재 국가가 필요합니다.")
    for rules in pack["rules"].values():
        if not isinstance(rules, dict) or "*" not in rules or any(
                country not in COUNTRIES | {"*"} or action not in {"allow", "approval", "deny"}
                for country, action in rules.items()):
            raise ValueError("국가별 위치 규칙이 올바르지 않습니다.")
