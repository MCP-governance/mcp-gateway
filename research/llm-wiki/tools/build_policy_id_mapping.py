"""Build analysis/drive-curation/policy-id-mapping.json: POL-01~50 <-> docs PAC50 <-> original PAC24 <-> runtime PAC-01~15.

Deterministic parts (name/body correspondence, number collisions, stale cross references, ledger back-references) are
derived from the workbook extract, pac15.rego and policy_ledger.json. Judgements (runtime PAC relationships, current
implementation status) live in this file's tables and are written once; later edits go to the JSON and
check_policy_id_mapping.py re-derives the deterministic parts.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = ROOT / "analysis/drive-curation/policy-id-mapping.json"
SOURCES = {
    "workbook": "research/llm-wiki/threats/extracted/policies.json",
    "pac15": "full_stack_lab/opa/pac15.rego",
    "ledger": "full_stack_lab/opa/policy_ledger.json",
}
SHEET_POL, SHEET_DOCS, SHEET_ORG = "(본)정책 최종본", "정책 최종본(독스용)", "정책 최종본"
RELATIONSHIPS = ("equivalent-to", "equal-to", "subset-of", "superset-of", "intersects-with", "no-relationship", "unreviewed")

# POL -> docs PAC50 by exact name; these two differ in wording only (reviewed) and POL-18 has no docs row.
RENAMED = {"POL-04": "PAC26", "POL-31": "PAC19"}

# Reviewed body differences between the (본) POL text and its docs PAC text (source = POL, target = docs PAC).
BODY_REVIEW = {
    "POL-10": ("equivalent-to", "교차 참조 번호만 다름(PAC15→PAC26)"),
    "POL-12": ("equivalent-to", "'중앙 게이트웨이'→'MCP 게이트웨이' 표기만 다름"),
    "POL-30": ("equivalent-to", "교차 참조 번호만 다름(PAC15→PAC26)"),
    "POL-44": ("equivalent-to", "교차 참조 번호만 다름(PAC24→PAC45)"),
    "POL-21": ("subset-of", "docs에만 있음: 특정 토큰 형식을 요구하지 않는다, 토큰을 다른 API에 그대로 전달해서는 안 된다"),
    "POL-22": ("subset-of", "docs에만 있음: 게이트웨이 검사로 서버의 접근통제를 대체해서는 안 된다"),
    "POL-26": ("subset-of", "docs에만 있음: 개인정보 제공·위탁·국외 이전의 법적 요건 충족, MCP 승인·동의로 법적 근거를 갈음 금지, 미확인 전송 차단"),
    "POL-31": ("subset-of", "docs에만 있음: 개인정보 최소 수집 준수, 금지 데이터 제거가 불명확하면 차단. 대상 표현이 '도구 입력'"),
    "POL-37": ("subset-of", "docs에만 있음: 서버·기능·규격·권한·정책 변경 대조, 실제 동작 변경 검토, 검토·시험·재승인 후 기록 갱신"),
}

# Current static judgement of the 35 technical controls: the 2026-10-17 status report (workbook sheet '정책 대응').
STATUS_35 = {
    "POL-01": ("일부 구현", "일부 구현", None, "서명 없는 배포물은 검증 대상 없음"), "POL-08": ("일부 구현", "구현", "G02.05", None),
    "POL-10": ("일부 구현", "구현", "G03.05", None), "POL-11": ("구현", "구현", None, None),
    "POL-13": ("일부 구현", "일부 구현", None, "원격 OAuth 인증 과정 미참여"), "POL-14": ("일부 구현", "구현", "G03.08", None),
    "POL-15": ("구현", "구현", None, None), "POL-16": ("일부 구현", "구현", "G08.05", None), "POL-18": ("구현", "구현", None, None),
    "POL-19": ("일부 구현", "일부 구현", None, "에이전트 신원 증명 불가"), "POL-20": ("일부 구현", "일부 구현", None, "검증된 에이전트 주체 없음"),
    "POL-21": ("구현", "구현", None, None), "POL-22": ("구현", "구현", None, None), "POL-23": ("구현", "구현", None, None),
    "POL-24": ("구현", "구현", None, None), "POL-25": ("일부 구현", "일부 구현", None, "외부 서비스 자원 등급은 제공자 보유"),
    "POL-26": ("일부 구현", "구현", "G04.05", None), "POL-27": ("구현", "구현", None, None), "POL-28": ("구현", "구현", None, None),
    "POL-29": ("구현", "구현", None, None), "POL-30": ("구현", "구현", None, None), "POL-31": ("일부 구현", "구현", "G04.06", None),
    "POL-33": ("일부 구현", "구현", "G04.07", None), "POL-35": ("일부 구현", "구현", "G03.06", None),
    "POL-36": ("일부 구현", "구현", "G03.07", None), "POL-37": ("구현", "구현", None, None), "POL-38": ("구현", "구현", None, None),
    "POL-39": ("일부 구현", "구현", "G01.06", None), "POL-40": ("일부 구현", "구현", "G03.05", None),
    "POL-41": ("일부 구현", "일부 구현", None, "제공자 측 무효화 관측 불가"), "POL-42": ("일부 구현", "구현", "G06.05", None),
    "POL-43": ("일부 구현", "구현", "G07.05", None), "POL-44": ("구현", "구현", None, None),
    "POL-45": ("일부 구현", "일부 구현", None, "제공자 측 회수 관측 불가"), "POL-50": ("미구현", "구현", "G07.06", None),
}

# Runtime PAC-01~15 links, judged from pac15.rego definitions, docs/ai/PAC_RUNTIME_2026-10-01.md and the ledger.
# Basis is the requirement set: source=POL, target=PAC. superset-of = POL requires more than the PAC checks.
GROUP = "PAC-01..PAC-15"
RUNTIME = {
    "POL-08": [("PAC-01", "intersects-with", "승인 상태·유효기간 확인은 있고 사용자 동의 확인은 PAC15에 없다"), ("PAC-07", "intersects-with", "등록 주소 대조는 있고 신청자/승인자 분리와 동의는 없다")],
    "POL-10": [("PAC-07", "superset-of", "PAC-07은 실제 접속 대상의 승인만 본다. DNS 재바인딩·OAuth 조회·MCP 서버가 보내는 최종 목적지는 PAC15 밖(PAC_RUNTIME 해석의 한계)")],
    "POL-11": [("PAC-08", "equivalent-to", "서버+기능 유형+ID+정의 허용목록. 구현은 도구만이고 resources·prompts는 범위 밖(crosswalk)")],
    "POL-15": [("PAC-06", "intersects-with", "토큰 대상(aud) 검증은 PAC-06. 서버별 upstream 자격 분리는 브로커 설계 영역")],
    "POL-16": [("PAC-07", "intersects-with", "평문 원격 연결 차단(MCP-TRANSPORT-001, 원장이 PAC-07로 표기). TLS 버전·상대 검증은 PAC15 밖")],
    "POL-19": [("PAC-04", "superset-of", "PAC-04의 agent는 상수(게이트웨이 broker)여서 에이전트 신원 증명이 없다"), ("PAC-06", "intersects-with", "사용자 토큰 검증은 있고 에이전트 신원 토큰은 없다")],
    "POL-20": [("PAC-05", "equivalent-to", "정의는 같으나 구현은 위임 미지원 차단(PAC-05-DELEGATION-UNSUPPORTED)")],
    "POL-21": [("PAC-06", "equivalent-to", "iss·aud·exp·scope 검증. docs PAC10의 '토큰 그대로 전달 금지'는 (본) POL-21 본문에 없다"), ("PAC-14", "intersects-with", "철회 음성군은 PAC-14")],
    "POL-22": [(GROUP, "superset-of", "실행마다 검사하는 PAC15 전체의 합. 이전 허용 결과 재사용 금지·최신 승인 상태는 PAC-13·PAC-14")],
    "POL-23": [("PAC-09", "equivalent-to", "행위(r/w/x) 정규화와 권한")],
    "POL-24": [("PAC-10", "intersects-with", "인자 경로·명령·수신자 정규화는 PAC-10. 원본 스키마 검증(P-INPUT-SCHEMA-001)과 서버 쪽 URI 검증은 PAC 밖")],
    "POL-25": [("PAC-11", "superset-of", "PAC-11은 게이트웨이 분류 자산·등급만. 외부 서비스 자원 등급은 제공자 보유")],
    "POL-26": [("PAC-12", "superset-of", "PAC-12는 목적지·등급 조합만. 동의 일치·변경 재검증·서버 outbound는 PAC 밖"), ("PAC-07", "intersects-with", "최종 목적지 승인은 PAC-07과 겹친다")],
    "POL-27": [("PAC-13", "superset-of", "PAC-13은 요청에 결합된 단회 승인. 호스트의 대상·내용 제시와 고영향 AI 감독 의무는 PAC 밖")],
    "POL-28": [("PAC-15", "intersects-with", "호출량·동시 실행은 PAC-15. 클라이언트 시간 한도와 대기 종료≠서버 중단은 PAC 밖")],
    "POL-29": [("PAC-13", "intersects-with", "비신뢰 콘텐츠 기반 고위험 실행의 승인 요구(P-UNTRUSTED-CONTENT-001, 원장이 PAC-13으로 표기). 새 호출 권한 재검사는 다른 PAC 경로")],
    "POL-33": [("PAC-12", "intersects-with", "외부 전송 목적지·등급은 PAC-12. 서버 간 전달·범용 정보 흐름 추적은 PAC 밖(crosswalk 공백)"), ("PAC-15", "intersects-with", "열람 뒤 전송 연쇄(P-CHAIN-001, 원장이 PAC-15로 표기)")],
    "POL-36": [("PAC-15", "intersects-with", "진행 중 중복(P-RATE-003)만. 응답 유실 뒤 재시도·독립 쓰기 효과는 PAC 밖"), ("PAC-13", "intersects-with", "단회 승인 소비로 같은 승인의 재사용을 막는다")],
    "POL-37": [("PAC-02", "superset-of", "PAC-02는 관찰 구성과 승인 기준의 비교. 검토·시험·재승인·승인 기록 갱신은 PAC 밖")],
    "POL-40": [("PAC-07", "superset-of", "승인 endpoint와 다르면 PAC-07이 거부. 재승인 절차와 MCP 서버 자체 outbound 변경은 PAC 밖")],
    "POL-41": [("PAC-14", "intersects-with", "게이트웨이가 쥔 토큰·자격의 폐기는 PAC-14. 제공자 측 이전 값 무효화는 관측 불가")],
    "POL-42": [("PAC-15", "intersects-with", "반복 차단 이상행위 증적(P-ANOMALY-001, 원장이 PAC-15로 표기). 신규 도구·미승인 연결 경보의 설정 변경 후 동작 확인은 PAC 밖")],
    "POL-43": [("PAC-14", "intersects-with", "중지·철회 신호는 PAC-14. 영향 범위 조사는 PAC 밖")],
    "POL-44": [("PAC-14", "superset-of", "PAC-14는 철회 신호의 반영. 등록·설정·연결 경로 제거와 인증정보 회수 확인은 PAC 밖"), ("PAC-01", "intersects-with", "종료·폐기 이용 관계 차단(MCP-DECOMM-001)이 PAC-01·14로 표기")],
    "POL-45": [("PAC-14", "intersects-with", "게이트웨이 쪽 폐기·철회는 PAC-14. 제공자 측 회수는 관측 불가")],
}
NO_PAC_NOTES = {
    "POL-01": "배포물 출처·무결성은 도입 단계(supply_chain/intake_worker.py)의 일이다. PAC-02는 호출 시점 구성 비교이고 원장 MCP-SUPPLY-001이 PAC-08로 표기되지만 기능 허용목록과 같은 통제가 아니다",
    "POL-13": "PAC15의 PAC-06은 들어오는 토큰 검증이다. 게이트웨이는 원격 서버의 OAuth 클라이언트 흐름에 참여하지 않는다",
    "POL-14": "자격 평문 노출 방지는 설정·환경·오류·훅 점검 영역이며 PAC15 판정이 아니다",
    "POL-18": "Origin·Host 검증은 ingress 코드와 tests/open_endpoints.py 영역이다",
    "POL-30": "출력 통제(MCP-OUTPUT-001)와 검사 장애 차단(P-DATA-INSPECTION-001)은 원장에서 PAC로 표기되지 않는다",
    "POL-31": "입력 민감정보 검사는 Presidio·P-DATA-INSPECTION-001 영역이며 원장에서 PAC로 표기되지 않는다",
    "POL-35": "반환 건수·크기 상한은 PAC15에 없다. P-VOLUME-001(PAC-15 표기)은 중요정보 누적 접근 승격으로 다른 축이다",
    "POL-38": "감사 원장은 PAC15 판정 밖이다",
    "POL-39": "알려진 취약점의 기한·격리는 PAC15 밖이다. 원장 MCP-SUPPLY-001의 PAC-08 표기는 같은 통제가 아니다",
    "POL-50": "PAC-14는 현재 DB의 철회 상태를 읽는다(PAC_RUNTIME). 복원이 DB를 되돌리면 PAC-14만으로는 폐기 연결의 재활성화를 막지 못할 수 있다(설계 추론, 미시험)",
}


def sha256(path: Path, normalize_eol: bool = False) -> str:
    data = path.read_bytes()
    if normalize_eol:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "")


def similarity(a: str | None, b: str | None) -> float:
    return round(difflib.SequenceMatcher(None, norm(a), norm(b)).ratio(), 3)


def load_workbook_rows():
    parsed = json.loads((REPO / SOURCES["workbook"]).read_text(encoding="utf-8"))
    sheets = {}
    for row in parsed["policies"]:
        sheets.setdefault(row["sheet"], {})[row["source_id"]] = row["fields"]
    return sheets, parsed


def runtime_definitions():
    text = (REPO / SOURCES["pac15"]).read_text(encoding="utf-8")
    return {m[1]: {"definition": m[2].strip(), "line": text[:m.start()].count("\n") + 1}
            for m in re.finditer(r"^# (PAC-\d\d): (.+)$", text, re.M)}


def ledger_by_pac():
    ledger = json.loads((REPO / SOURCES["ledger"]).read_text(encoding="utf-8"))["policy_ledger"]
    result: dict[str, list[str]] = {}
    for pid, item in ledger.items():
        for pac in item.get("pac_ids") or []:
            result.setdefault(pac, []).append(pid)
    return {k: sorted(v) for k, v in sorted(result.items())}, ledger


def derive():
    """Deterministic correspondence: everything here is recomputed by check_policy_id_mapping.py."""
    sheets, parsed = load_workbook_rows()
    pol, docs, org = sheets[SHEET_POL], sheets[SHEET_DOCS], sheets[SHEET_ORG]
    docs_by_name = {norm(f.get("정책명")): k for k, f in docs.items() if norm(f.get("정책명"))}
    links = {}
    for pid, f in pol.items():
        docs_id = docs_by_name.get(norm(f["정책명"])) or RENAMED.get(pid)
        name_match = None if not docs_id else ("exact" if norm(docs[docs_id]["정책명"]) == norm(f["정책명"]) else "renamed")
        entry = {"docs_pac_id": docs_id, "docs_name_match": name_match}
        if docs_id:
            entry["docs_body_similarity"] = similarity(f["정책 내용"], docs[docs_id].get("정책 내용"))
            if docs_id in org:
                entry["original_pac_id"] = docs_id
                entry["original_body_similarity"] = similarity(f["정책 내용"], org[docs_id].get("정책 내용"))
                entry["original_name_equal"] = norm(org[docs_id]["정책명"]) == norm(docs[docs_id]["정책명"])
        links[pid] = entry
    collisions = []
    for pid, entry in links.items():
        n = int(pid[4:])
        if entry["docs_pac_id"] and int(entry["docs_pac_id"][3:]) != n:
            same = docs.get(f"PAC{n:02d}", {})
            collisions.append({"pol_id": pid, "pol_name": pol[pid]["정책명"].strip(), "docs_pac_id": entry["docs_pac_id"],
                               "same_number_docs_pac": f"PAC{n:02d}", "same_number_docs_pac_name": (same.get("정책명") or "").strip() or None})
    inverse = {e["docs_pac_id"]: pid for pid, e in links.items() if e["docs_pac_id"]}
    stale = []
    for pid, f in pol.items():
        for m in re.finditer(r"PAC(\d\d)", f["정책 내용"]):
            label = f"PAC{m[1]}"
            by_number = docs.get(label, {}).get("정책명", "").strip()
            counterpart = docs.get(links[pid]["docs_pac_id"] or "", {}).get("정책 내용", "")
            docs_ref = sorted(set(re.findall(r"PAC\d\d", counterpart)))
            stale.append({"in_policy": pid, "label": label, "resolves_by_docs_number_to": {"docs_pac_id": label, "name": by_number, "pol_id": inverse.get(label)},
                          "same_number_pol": {"pol_id": f"POL-{m[1]}", "name": pol.get(f"POL-{m[1]}", {}).get("정책명", "").strip()},
                          "docs_counterpart_cites": docs_ref,
                          "docs_counterpart_cite_resolves_to_pol": [inverse.get(r) for r in docs_ref]})
    return {"pol": pol, "docs": docs, "org": org, "links": links, "collisions": collisions, "stale": stale,
            "workbook_sha256": parsed["sha256"], "workbook_extract_sha256": sha256(REPO / SOURCES["workbook"])}


def build():
    d = derive()
    pol, docs, links = d["pol"], d["docs"], d["links"]
    defs = runtime_definitions()
    by_pac, ledger = ledger_by_pac()
    assert set(RUNTIME) | set(NO_PAC_NOTES) <= set(STATUS_35), "judgement tables must stay inside the 35 technical controls"
    mappings = []
    for pid, f in pol.items():
        e = links[pid]
        in35 = pid in STATUS_35
        item = {"policy_id": pid, "name": f["정책명"].strip(), "scope": "technical_control_35" if in35 else "outside_35"}
        if in35:
            cur, after, wbs, limit = STATUS_35[pid]
            item["status_report"] = {"current": cur, "after_planned_development": after, "planned_wbs_ref": wbs, "automation_limit": limit}
        link_list = []
        if e["docs_pac_id"]:
            sim = e["docs_body_similarity"]
            if sim == 1.0:
                rel, why = "equal-to", "정책명·본문이 공백 제거 후 같다"
            else:
                rel, why = BODY_REVIEW[pid]
            link_list.append({"system": "pac50-docs", "id": e["docs_pac_id"], "relationship": rel, "method": "syntactic" if rel == "equal-to" else "semantic",
                              "name_match": e["docs_name_match"], "body_similarity": sim, "basis": why})
        if "original_pac_id" in e:
            link_list.append({"system": "pac24-original", "id": e["original_pac_id"], "relationship": "unreviewed", "method": None,
                              "name_match": "exact" if e["original_name_equal"] else "differs", "body_similarity": e["original_body_similarity"],
                              "basis": "정책명은 docs PAC와 같고 본문은 전부 다시 쓰여 의미 대조를 하지 않았다"})
        runtime = []
        if in35:
            for target, rel, remark in RUNTIME.get(pid, []):
                members = [f"PAC-{n:02d}" for n in range(1, 16)] if target == GROUP else [target]
                entry = {"system": "runtime-pac15", "id": target, "relationship": rel, "method": "semantic", "remarks": remark,
                         "review": "claude_judgement_2026-10-17_unreviewed",
                         "definition_line": None if target == GROUP else defs[target]["line"],
                         "ledger_policy_ids": sorted({p for m in members for p in by_pac.get(m, [])})}
                runtime.append(entry)
            item["runtime_coverage"] = "none" if not runtime else ("equivalent" if all(r["relationship"] == "equivalent-to" for r in runtime) else "partial")
            if not runtime:
                item["runtime_note"] = NO_PAC_NOTES[pid]
        else:
            item["runtime_coverage"] = "not_assessed"
        item["links"] = link_list + runtime
        gaps = []
        if in35 and item["runtime_coverage"] == "none":
            gaps.append({"kind": "no_runtime_pac", "text": NO_PAC_NOTES[pid]})
        for r in runtime:
            if r["relationship"] in ("superset-of", "intersects-with"):
                gaps.append({"kind": "runtime_pac_covers_part", "pac": r["id"], "text": r["remarks"]})
        if pid in BODY_REVIEW and BODY_REVIEW[pid][0] == "subset-of":
            gaps.append({"kind": "docs_only_clause", "docs_pac": e["docs_pac_id"], "text": BODY_REVIEW[pid][1]})
        item["gaps"] = gaps
        mappings.append(item)
    counts = {}
    for m in mappings:
        if m["scope"] == "technical_control_35":
            key = (m["status_report"]["current"], m["runtime_coverage"])
            counts["%s / 런타임 PAC %s" % key] = counts.get("%s / 런타임 PAC %s" % key, 0) + 1
    return {
        "format": "policy-id-mapping/1", "generated_on": "2026-10-17", "generator": "research/llm-wiki/tools/build_policy_id_mapping.py",
        "purpose": "POL-01~50, 독스용 PAC50, 원본 PAC24, 런타임 PAC-01~15의 대응을 번호 일치가 아니라 정책명·본문·통제 의미로 기록한다. 부분 구현 판정과 런타임 PAC가 덮지 못하는 공백을 같은 표에서 본다.",
        "vocabulary": {
            "origin": "관계값은 NIST OSCAL 통제 매핑 모델의 어휘(equivalent-to, equal-to, subset-of, superset-of, intersects-with, no-relationship)를 차용했다. OSCAL 도구·스키마는 쓰지 않았다(LIB-K01).",
            "direction": "source는 항상 POL. 이 파일은 '요구 항목 집합'을 기준으로 쓴다. superset-of는 POL이 target(PAC)이 검사하는 항목보다 더 요구한다는 뜻(PAC가 일부만 덮음), subset-of는 target이 더 많이 요구한다는 뜻이다. OSCAL 개념 문서의 예는 구현 방식의 수로 세므로 방향이 달라 보일 수 있고, 이 파일은 OSCAL 문서로 변환하지 않았다.",
            "unreviewed": "OSCAL 값이 아니다. 이름은 같지만 본문 의미 대조를 하지 않은 대응",
            "runtime_review": "runtime-pac15 링크는 Claude의 의미 판단(검토 전)이며 구현·검수 완료나 독립 검토 결과가 아니다",
            "method": {"syntactic": "공백 제거 후 문자열 동일", "semantic": "본문을 읽고 의미로 판단"}},
        "systems": [
            {"id": "pol50", "name": "(본)정책 최종본 POL-01~50", "source": SOURCES["workbook"], "sheet": SHEET_POL, "count": len(pol)},
            {"id": "pac50-docs", "name": "정책 최종본(독스용) PAC01~50", "source": SOURCES["workbook"], "sheet": SHEET_DOCS, "count": len(docs),
             "note": "PAC50은 영역만 '등록 및 연결'이고 정책명·본문이 빈 행이다. POL-18(HTTP 요청 출처 검증)에 대응하는 행이 docs에 없다. 빈 PAC50이 그 자리인지는 확인하지 못했다(추론)"},
            {"id": "pac24-original", "name": "정책 최종본 PAC01~24(원본 24개)", "source": SOURCES["workbook"], "sheet": SHEET_ORG, "count": len(d["org"]),
             "note": "docs PAC01~24와 번호·정책명이 1:1로 같다. 본문은 모두 다시 쓰여 공백 제거 동일 0/24"},
            {"id": "runtime-pac15", "name": "게이트웨이 런타임 PAC-01~15", "source": SOURCES["pac15"], "count": len(defs), "definitions": defs,
             "ledger_policy_ids_by_pac": by_pac},
            {"id": "pac-cand", "name": "정책 원장의 pac_candidate_id(PAC-CAND-nn)", "source": SOURCES["ledger"],
             "count": len({v.get("pac_candidate_id") for v in ledger.values() if v.get("pac_candidate_id")}),
             "note": "policy_ledger.json에만 나오며 저장소의 어느 문서도 정의하지 않는다. 번호로 대응시킬 수 없어 이 파일의 매핑에서 제외했다"},
        ],
        "source_hashes": {"workbook_original_sha256": d["workbook_sha256"], "workbook_extract_sha256": d["workbook_extract_sha256"],
                          "pac15_rego_sha256_lf": sha256(REPO / SOURCES["pac15"], True), "policy_ledger_sha256_lf": sha256(REPO / SOURCES["ledger"], True)},
        "status_report_source": {"file": "output/MCP_보안거버넌스_기능명세서_개발WBS_2026-10-17.xlsx", "sheet": "정책 대응", "captured_on": "2026-10-17",
                                 "basis": "개발 브랜치 c0fbab3 정적 판정. 35개 기술통제만 포함(구현 14·일부 구현 20·미구현 1)", "independent_reverification": False,
                                 "planned_wbs_ref": "상위 보고서가 제안한 추가 개발 WBS 번호이며 확정되지 않았다"},
        "number_collisions": {"description": "같은 번호의 POL과 docs PAC가 서로 다른 통제인 경우. 번호로 대응시키면 틀린다", "count": len(d["collisions"]), "items": d["collisions"]},
        "stale_cross_references": {"description": "(본) POL 본문 안의 PAC 번호 참조. docs 시트의 같은 문장은 docs 번호(PAC15·PAC24)를 쓰는데 (본) 시트는 POL 번호로 바꾸면서 'PAC' 접두를 남겼다. 접두 그대로 docs 번호로 읽으면 다른 통제를 가리킨다",
                                   "rule": "(본) 시트에서 PACnn은 POL-nn으로 읽는다", "items": d["stale"]},
        "mappings": mappings,
        "summary": {"policies": len(mappings), "technical_control_35": sum(1 for m in mappings if m["scope"] == "technical_control_35"),
                    "status_current_x_runtime_coverage": counts,
                    "docs_only_clause_policies": [m["policy_id"] for m in mappings if any(g["kind"] == "docs_only_clause" for g in m["gaps"])]},
    }


def main():
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(data["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
