"""시트 정책 ↔ Rego 규칙 ↔ 시험을 잇는 추적표(policy/TRACE.md)를 만들고, 빠진 연결을 검사한다.

  python policy/tools/trace.py           TRACE.md를 다시 쓴다
  python policy/tools/trace.py --check   다시 만든 표가 저장소와 같고 아래 조건을 모두 지키는지 본다(CI)

검사 조건
  - 분류가 「이미 구현」·「구현 가능(PaC)」이고 Rego가 판정하는 정책은 그 정책을 내는 판정 줄이 있다.
  - 판정 줄이 있는 정책은 METADATA custom.pol_id에도 적혀 있다(주석과 코드가 같은 정책을 가리킨다).
  - 그 정책마다 통과 시험(test_pol_NNN_pass_*)과 차단 시험(test_pol_NNN_block_*)이 하나 이상씩 있다.
  - 규칙·시험이 가리키는 정책 ID는 시트에 있다.
  - 솔루션 기능·제외로 분류한 정책은 사유가 있다.
opa 없이 Rego 파일을 직접 읽는다(CI의 정적 단계에서 돌리기 위해서다). 시험의 실행·통과는 opa test가 본다.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAC = ROOT / "pac"
TRACE = ROOT / "TRACE.md"

CATEGORY = {"implemented": "이미 구현", "pac": "구현 가능(PaC)", "solution": "솔루션 기능으로 커버", "excluded": "구현 불가·제외"}
ENFORCED = {"rego": "Rego", "rego+sensor": "Rego + 센서", "solution": "솔루션"}
# 판정 줄: findings의 lib.finding("POL-…") 또는 ops violations의 "policy_id": "POL-…".
DECISION_LINE = re.compile(r'lib\.finding\("(POL-\d{3})"|"policy_id": "(POL-\d{3})"')


def load_policies():
    sheet = json.loads((ROOT / "source" / "sheet.json").read_text(encoding="utf-8"))
    classes = json.loads((ROOT / "source" / "classification.json").read_text(encoding="utf-8"))["policies"]
    return sheet, {pol: {**sheet["policies"][pol], **classes[pol]} for pol in sheet["policies"]}


def rule_sources():
    """정책 ID → 그 정책을 내는 판정 줄(파일:행) 목록, 그리고 METADATA pol_id에 적힌 정책 집합."""
    decisions, annotated = defaultdict(list), set()
    for path in sorted(PAC.glob("*.rego")):
        if path.name.endswith("_test.rego"):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"#\s+pol_id:\s*(.+)$", line)
            if m:
                annotated.update(re.findall(r"POL-\d{3}", m.group(1)))
            for a, b in DECISION_LINE.findall(line):
                decisions[a or b].append(f"{path.name}:{i}")
    return decisions, annotated


def test_counts():
    counts = defaultdict(lambda: {"pass": 0, "block": 0, "adv": 0})
    for path in sorted(PAC.glob("*_test.rego")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^test_pol_(\d{3})_(pass|block)_\w+", text, re.M):
            counts[f"POL-{m.group(1)}"][m.group(2)] += 1
        for m in re.finditer(r"^test_adv_pol_(\d{3})_\w+", text, re.M):
            counts[f"POL-{m.group(1)}"]["adv"] += 1
    return counts


def expects_rego(p):
    return p["category"] in {"implemented", "pac"} and p["enforced_by"] in {"rego", "rego+sensor"}


def cell(text):
    return str(text).replace("|", "／").replace("\n", " ")


def render(sheet, policies, decisions, tests):
    rows = []
    for pol in sorted(policies):
        p = policies[pol]
        t = tests.get(pol, {"pass": 0, "block": 0, "adv": 0})
        where = ", ".join(decisions.get(pol, [])) or "—"
        if decisions.get(pol):
            state = "Rego 규칙·시험" if t["pass"] and t["block"] else "시험 부족"
        elif expects_rego(p):
            state = "규칙 없음"
        else:
            state = "Rego 대상 아님"
        note = cell(p.get("note", "")) if p["category"] in {"solution", "excluded"} else ""
        rows.append(f"| {pol} | {p.get('stage', '')} | {p.get('priority', '')} | {cell(p.get('target', ''))} | "
                    f"{CATEGORY[p['category']]} | {ENFORCED[p['enforced_by']]} | {where} | {t['pass']}/{t['block']} | {t['adv']} | {state} | {note} |")
    per_cat = defaultdict(int)
    for p in policies.values():
        per_cat[CATEGORY[p["category"]]] += 1
    with_rules = sum(1 for pol in policies if decisions.get(pol))
    named = sum(t["pass"] + t["block"] for t in tests.values())
    adversarial = sum(t["adv"] for t in tests.values())
    summary = " · ".join(f"{k} {per_cat[k]}" for k in CATEGORY.values())
    return "\n".join([
        "# 정책 추적표",
        "",
        "생성 파일 — `python policy/tools/trace.py`. 손으로 고치지 않는다.",
        f"원본 시트: `{sheet['source']}` (SHA-256 `{sheet['sha256'][:16]}…`).",
        "",
        f"분류: {summary}. Rego 판정이 있는 정책 {with_rules}개, 정책 번호가 붙은 시험 {named}건, 독립 반례 시험 {adversarial}건.",
        "",
        "- 「판정 위치」는 그 정책의 결과를 내는 줄(findings·violations)이다. 정책 하나가 여러 줄·여러 패키지에 걸칠 수 있다.",
        "- 「시험」은 통과/차단 시험 수, 「반례」는 규칙 작성자의 시험을 보지 않고 시트만으로 쓴 시험 수다.",
        "- 이 표는 코드·시험의 연결이다. 게이트웨이 판정 경로 연결과 실기기 집행은 따로 확인한다(README 「게이트웨이 연결」).",
        "",
        "| 정책 | 단계 | 우선순위 | 통제 대상 | 분류 | 판정 | 판정 위치 | 시험 | 반례 | 상태 | 사유(솔루션·제외) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
    ])


def problems(policies, decisions, annotated, tests):
    out = []
    for pol, p in sorted(policies.items()):
        t = tests.get(pol, {"pass": 0, "block": 0, "adv": 0})
        if expects_rego(p) and not decisions.get(pol):
            out.append(f"{pol}: Rego 판정 대상인데 이 정책을 내는 판정 줄이 없다")
        if decisions.get(pol) and pol not in annotated:
            out.append(f"{pol}: 판정 줄은 있는데 METADATA custom.pol_id에 없다")
        if decisions.get(pol) and not (t["pass"] and t["block"]):
            out.append(f"{pol}: 통과 시험 {t['pass']}건·차단 시험 {t['block']}건 — 둘 다 있어야 한다")
        if p["category"] in {"solution", "excluded"} and not p.get("note"):
            out.append(f"{pol}: 솔루션·제외 분류인데 사유가 없다")
    for pol in sorted((set(decisions) | annotated) - set(policies)):
        out.append(f"{pol}: 규칙이 시트에 없는 정책 ID를 가리킨다")
    for pol in sorted(annotated - set(decisions)):
        out.append(f"{pol}: METADATA에는 있는데 그 정책을 내는 판정 줄이 없다")
    for pol in sorted(set(tests) - set(policies)):
        out.append(f"{pol}: 시험이 시트에 없는 정책 ID를 가리킨다")
    return out


def main():
    sheet, policies = load_policies()
    (decisions, annotated), tests = rule_sources(), test_counts()
    text = render(sheet, policies, decisions, tests)
    issues = problems(policies, decisions, annotated, tests)
    if "--check" in sys.argv:
        if TRACE.read_text(encoding="utf-8") != text:
            issues.append("TRACE.md가 최신이 아니다: python policy/tools/trace.py")
        if issues:
            sys.exit("\n".join(issues))
        print(f"추적 검사 통과: 정책 {len(policies)}개, 판정 있는 정책 {sum(1 for p in policies if decisions.get(p))}개")
        return
    TRACE.write_text(text, encoding="utf-8", newline="\n")
    print(f"{TRACE.relative_to(ROOT)} 생성")
    for issue in issues:
        print("경고:", issue)


if __name__ == "__main__":
    main()
