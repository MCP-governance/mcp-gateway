"""팀 정책 시트를 PaC 카탈로그로 옮긴다.

  extract  시트(.xlsm/.xlsx)의 「보안 정책」·「정책 실행 규칙」 두 탭을 source/sheet.json으로 뽑는다(openpyxl 필요).
  build    source/sheet.json + source/classification.json → pac/catalog.rego. --check는 다시 만든 결과가
           저장소의 catalog.rego와 같은지만 본다(CI).

시트가 정본이고 catalog.rego는 생성물이다. 손으로 고치지 않는다.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "source" / "sheet.json"
CLASSIFICATION = ROOT / "source" / "classification.json"
CATALOG = ROOT / "pac" / "catalog.rego"

POLICY_COLUMNS = ["id", "stage", "target", "condition", "content", "evidence", "requirement", "cia",
                  "impact", "likelihood", "risk_score", "risk_level", "prerequisite", "risk_points",
                  "priority_score", "priority"]
RULE_COLUMNS = ["id", "stage", "checkpoint", "inputs", "pass_condition", "block_condition", "exception", "risk_id"]


def _rows(sheet):
    for row in sheet.iter_rows(values_only=True):
        cells = ["" if v is None else str(v).strip() for v in row]
        if cells and cells[0].startswith("POL-"):
            yield cells


def extract(path):
    import openpyxl
    data = Path(path).read_bytes()
    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    policy_tab, rule_tab = book.worksheets[0], book.worksheets[1]
    policies, last_stage = {}, ""
    for cells in _rows(policy_tab):
        row = dict(zip(POLICY_COLUMNS, cells + [""] * len(POLICY_COLUMNS)))
        # 단계 열은 병합 셀이라 첫 행에만 값이 있다.
        last_stage = row["stage"] or last_stage
        row["stage"] = last_stage
        policies[row["id"]] = row
    for cells in _rows(rule_tab):
        rule = dict(zip(RULE_COLUMNS, cells + [""] * len(RULE_COLUMNS)))
        policies.setdefault(rule["id"], {"id": rule["id"]})["rule"] = {k: rule[k] for k in RULE_COLUMNS[2:]}
    out = {"source": Path(path).name, "sha256": hashlib.sha256(data).hexdigest(), "policies": policies}
    SHEET.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{SHEET.relative_to(ROOT)}: {len(policies)}개 정책")


def approver(text):
    # 시트 「예외」 열의 문장에서 최종 승인 주체를 읽는다. 「예외 심사 대상 아님」이면 예외 자체가 없다.
    # 이 값은 허용 목록·권한표 항목의 승인 주체 검사(lib.approved)에 쓰인다. 예외 문장의 나머지 뜻
    # (제한 허용·승인 기준 변경·재조회 절차)은 원문(exception)으로 함께 남긴다.
    if not text or "예외 심사 대상 아님" in text:
        return "none"
    if "자료 소유 부서" in text:
        return "data_owner"
    if "보안 관리자" in text:
        return "security_admin"
    return "unknown"


def rego_string(value):
    return json.dumps(value, ensure_ascii=False)


def render():
    sheet = json.loads(SHEET.read_text(encoding="utf-8"))
    classes = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))["policies"]
    missing = sorted(set(sheet["policies"]) ^ set(classes))
    if missing:
        sys.exit(f"시트와 분류표의 정책 ID가 다르다: {missing}")
    lines = [
        "# 생성 파일 — policy/tools/build_catalog.py build. 손으로 고치지 않는다.",
        f"# 원본: {sheet['source']} (SHA-256 {sheet['sha256']})",
        "# 분류: policy/source/classification.json",
        "package mcp.pol.catalog",
        "",
        "import rego.v1",
        "",
        "# 정책 ID → 시트의 정책·실행 규칙과 구현 분류. 규칙의 METADATA custom.pol_id가 이 키를 가리킨다.",
        "policies := {",
    ]
    for pol in sorted(sheet["policies"]):
        p, c = sheet["policies"][pol], classes[pol]
        rule = p.get("rule", {})
        entry = {
            "title": p.get("target", ""),
            "stage": p.get("stage", ""),
            "priority": p.get("priority", ""),
            "risk_id": rule.get("risk_id", ""),
            "content": p.get("content", ""),
            "checkpoint": rule.get("checkpoint", ""),
            "inputs": rule.get("inputs", ""),
            "pass_condition": rule.get("pass_condition", ""),
            "block_condition": rule.get("block_condition", ""),
            "exception": rule.get("exception", ""),
            "exception_approver": approver(rule.get("exception", "")),
            "category": c["category"],
            "enforced_by": c["enforced_by"],
            "note": c["note"],
        }
        body = ", ".join(f"{rego_string(k)}: {rego_string(v)}" for k, v in entry.items())
        lines.append(f"\t{rego_string(pol)}: {{{body}}},")
    lines += ["}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract").add_argument("sheet")
    sub.add_parser("build").add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.cmd == "extract":
        extract(args.sheet)
        return
    text = render()
    if args.check:
        if CATALOG.read_text(encoding="utf-8") != text:
            sys.exit("catalog.rego가 시트·분류표와 다르다: python policy/tools/build_catalog.py build")
        print("catalog.rego 최신")
        return
    CATALOG.write_text(text, encoding="utf-8", newline="\n")
    print(f"{CATALOG.relative_to(ROOT)} 생성")


if __name__ == "__main__":
    main()
