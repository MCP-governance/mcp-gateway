"""Ingest staged compliance documents (originals, extract, provenance, note.json) into the research wiki.

For each document id under --stage:
  * copies the original, the Markdown extract and provenance.json to sources/compliance/<id>/ (public-under-license)
    or local-sources/compliance/<id>/ (git-ignored, local-only),
  * keeps the canonical note at analysis/compliance/notes/<id>.json,
  * writes papers/<id>.md and upserts the catalogs/papers.json record.
Run from the repository root:  python -B -X utf8 research/llm-wiki/tools/build_compliance.py --stage <dir> [--ids LIB-L01 ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODAY = "2026-10-17"
THEME_KO = {
    "human_oversight": "인간 감독", "logging_records": "기록·로그", "transparency_labelling": "투명성·표시", "data_protection_lawful_basis": "개인정보 적법 근거",
    "data_minimisation_retention_deletion": "최소화·보유·파기", "cross_border_transfer": "국외 이전", "automated_decision_rights": "자동화된 결정 권리",
    "security_risk_management": "보안 위험 관리", "secure_development_supply_chain": "보안 개발·공급망", "incident_reporting": "사고 보고",
    "access_control_identity": "접근 통제·신원", "third_party_management": "제3자 관리", "risk_impact_assessment": "위험·영향 평가",
    "governance_accountability": "거버넌스·책임", "testing_red_teaming_robustness": "시험·레드티밍·견고성", "agentic_ai": "에이전트 AI",
    "scope_applicability": "적용 범위", "penalties_enforcement": "제재·집행", "other": "기타"}
KIND = {"statute": "law", "regulation": "law", "directive": "law", "decree": "law", "executive_order": "policy", "regulator_guidance": "guide", "framework": "guide",
        "standard": "standard", "code_of_practice": "guide", "national_standard": "standard", "draft": "spec"}
KIND_KO = {"statute": "법률", "regulation": "규정·규칙", "directive": "지침(Directive)", "decree": "시행령·명령", "executive_order": "행정명령", "regulator_guidance": "규제기관 지침",
           "framework": "프레임워크", "standard": "표준", "code_of_practice": "실천 규약", "national_standard": "국가 표준", "draft": "초안"}
STRENGTH_KO = {"mandatory": "의무", "recommended": "권고", "informative": "참고"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esc(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


RELATED = {
    "LIB-L01": ("LIB-K36", "같은 법·같은 판본(법률 제21445호, 시행 2026-09-11)을 앞서 선별 조문 수준으로 등록한 항목. 이 문서가 전문과 조항별 정리를 맡는다."),
    "LIB-L04": ("LIB-I16", "같은 법을 앞서 메타데이터 수준으로 등록한 항목. 그 판본 표기는 정정됐고 이 문서가 현행 판본 전문을 맡는다."),
    "LIB-L09": ("LIB-K34", "같은 표준을 앞서 메타데이터 수준으로 등록한 항목. 그 항목의 조항 번호 확인 기록은 이 문서의 OCR 사본으로 갱신됐다."),
}


def page(note: dict, prov: dict, public: bool, rel: dict) -> str:
    L = [f"# {note['id']} · {note['title']}", ""]
    L.append(note["summary_ko"] + "\n")
    L.append("## 출처와 확인 수준\n")
    L.append(f"- 공식 출처: [{note['title']}]({note['official_page_url']})")
    L.append(f"- 유형: {KIND_KO.get(note['instrument_type'], note['instrument_type'])} · {'구속력 있음' if note['binding'] else '구속력 없음(권고·참고)'} · 관할 `{note['jurisdiction']}` · 언어 `{note['language']}`")
    L.append(f"- 발행: {note['issuer']}")
    L.append(f"- 판본·상태: {note.get('edition', '')} / 상태 `{note['status']}` (2026-10-17 확인)")
    L.append(f"- 주요 일자: {note['key_dates']}")
    L.append(f"- 원문 확보: `{prov['kind']}` {prov['bytes']:,} bytes, SHA-256 `{prov['sha256']}`" + (f", {prov['pages']}쪽" if prov.get("pages") else "") + (" (이미지 PDF를 OCR한 추출)" if prov.get("ocr_used") else ""))
    L.append(f"- 보존 위치: {'공개 저장소 ' if public else '로컬 전용(git 제외) '}`{rel['original']}` · 추출 `{rel['extract']}`")
    if note["id"] in RELATED:
        L.append(f"- 관련 기존 자료: [{RELATED[note['id']][0]}]({RELATED[note['id']][0]}.md) — {RELATED[note['id']][1]}")
    L.append(f"- 읽은 범위: {note.get('reading_scope_ko', '')}")
    L.append(f"- 배포: `{note['distribution']}` — {note.get('distribution_reason', '')}\n")
    L.append("## 적용 범위\n")
    L.append(note.get("scope_ko", "") + "\n")
    L.append("## 조항별 요구와 MINT 연결\n")
    L.append("| 조항 | 주제 | 요구 내용 | 대상 | 강도 | 기한·기간 | MINT 통제 | 정책 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for p in note["provisions"]:
        L.append(f"| {esc(p['ref'])} | {esc(p['topic_ko'])} | {esc(p['obligation_ko'])} | {esc(p['actor'])} | {STRENGTH_KO.get(p['strength'], p['strength'])} | {esc(p.get('timing_ko', '') or '—')} | {esc(p['gateway_control_ko'])} | {esc(', '.join(p['pol_ids']) or '—')} |")
    L.append("")
    if note.get("pitfalls_ko"):
        L.append("## 오독하기 쉬운 점\n")
        for x in note["pitfalls_ko"]:
            L.append(f"- {x}")
        L.append("")
    L.append("적용 항목은 개발 후보이며 이 자료를 읽었다는 사실이 정책의 구현·검수 완료나 법적 적합성을 뜻하지 않는다.\n")
    L.append("## 한계와 사용 조건\n")
    L.append(note["limitations_ko"] + "\n")
    L.append(f"라이선스·재사용: {note['license_notice']}\n")
    L.append("[요구사항 매트릭스](../analysis/compliance/README.md) · [자료 확보 규칙](../methodology/source-protocol.md)")
    return "\n".join(L) + "\n"


def record(note: dict, prov: dict, public: bool, rel: dict) -> dict:
    uses = []
    for p in note["provisions"]:
        if p["pol_ids"] and p["strength"] != "informative":
            uses.append(f"{p['ref']} → {', '.join(p['pol_ids'])}: {p['gateway_control_ko']}")
    pols = sorted({x for p in note["provisions"] for x in p["pol_ids"]})
    return {
        "id": note["id"], "title": note["title"], "kind": KIND.get(note["instrument_type"], "guide"), "url": note["official_page_url"],
        "verified_on": TODAY, "verification": "full_text_selected_sections_read", "publication_status": note["status"],
        "venue": note["issuer"], "year": int(re.search(r"(19|20)\d{2}", note.get("edition", "") + " " + note["key_dates"]).group(0)) if re.search(r"(19|20)\d{2}", note.get("edition", "") + " " + note["key_dates"]) else None,
        "authors": note["issuer"], "topic": "AI 규제·컴플라이언스 근거", "jurisdiction": note["jurisdiction"], "instrument_type": note["instrument_type"], "binding": note["binding"],
        "edition": note.get("edition", ""), "key_dates": note["key_dates"], "language": note["language"],
        "originals": [rel["original"]], "extracts": [rel["extract"]], "summary": note["summary_ko"],
        "engineering_use": uses[:6], "findings": [f"{p['ref']} {p['topic_ko']}: {p['obligation_ko']}" for p in note["provisions"][:5]],
        "limitations": note["limitations_ko"], "distribution": note["distribution"], "distribution_reason": note.get("distribution_reason", ""),
        "license_notice": note["license_notice"], "page": f"papers/{note['id']}.md", "provenance": rel["provenance"],
        "files": [{"path": rel["original"], "sha256": prov["sha256"]}], "summary_review": "full_text_selected_sections_read",
        "reading_scope": note.get("reading_scope_ko", ""), "note_json": f"analysis/compliance/notes/{note['id']}.json",
        "provision_count": len(note["provisions"]), "policy50_links": [{"policy_id": x} for x in pols],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", required=True)
    ap.add_argument("--ids", nargs="*")
    a = ap.parse_args()
    stage = Path(a.stage)
    ids = a.ids or sorted(p.name for p in stage.iterdir() if (p / "note.json").is_file())
    cat_path = ROOT / "catalogs/papers.json"
    catalog = json.loads(cat_path.read_text(encoding="utf-8"))
    by_id = {r["id"]: i for i, r in enumerate(catalog)}
    (ROOT / "analysis/compliance/notes").mkdir(parents=True, exist_ok=True)
    for did in ids:
        base = stage / did
        note = json.loads((base / "note.json").read_text(encoding="utf-8"))
        prov = json.loads((base / "provenance.json").read_text(encoding="utf-8"))
        public = note["distribution"] == "public-under-license"
        top = ROOT / ("sources/compliance" if public else "local-sources/compliance") / did
        (top / "originals").mkdir(parents=True, exist_ok=True)
        (top / "extracts").mkdir(parents=True, exist_ok=True)
        src_original = base / prov["original"]
        dst_original = top / "originals" / src_original.name
        shutil.copyfile(src_original, dst_original)
        shutil.copyfile(base / prov["extract"], top / "extracts" / f"{did}.md")
        assert sha256(dst_original) == prov["sha256"], did
        rel_root = ("sources/compliance" if public else "local-sources/compliance") + f"/{did}"
        rel = {"original": f"{rel_root}/originals/{src_original.name}", "extract": f"{rel_root}/extracts/{did}.md", "provenance": f"{rel_root}/provenance.json"}
        prov_out = dict(prov, original=f"originals/{src_original.name}", extract=f"extracts/{did}.md", distribution=note["distribution"])
        (top / "provenance.json").write_text(json.dumps(prov_out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        (ROOT / "analysis/compliance/notes" / f"{did}.json").write_text(json.dumps(note, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        (ROOT / "papers" / f"{did}.md").write_text(page(note, prov, public, rel), encoding="utf-8", newline="\n")
        rec = record(note, prov, public, rel)
        if did in by_id:
            catalog[by_id[did]] = rec
        else:
            by_id[did] = len(catalog)
            catalog.append(rec)
        print(did, "public" if public else "local", len(note["provisions"]), "provisions")
    cat_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
