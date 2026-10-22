"""문서·코드·룰셋의 ID 정의와 참조를 추적하는 검사기. 표준 라이브러리만 쓴다(--export만 build_sheet_export를 빌린다).

python -B -X utf8 research/llm-wiki/tools/check_trace.py            # 검사(오류가 있으면 종료 코드 1, 경고는 통과)
python -B -X utf8 research/llm-wiki/tools/check_trace.py --next D   # 다음 빈 번호(main·열린 원격 브랜치까지)
python -B -X utf8 research/llm-wiki/tools/check_trace.py --export   # 추적표 CSV
python -B -X utf8 research/llm-wiki/tools/check_trace.py --self-test
규칙은 research/llm-wiki/trace/README.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WIKI = "research/llm-wiki"
SEP = " · "
EXPORT = f"{WIKI}/sheet/tabs/47-trace.csv"
HEADERS = ["ID", "계열", "제목", "정의 위치", "참조 수", "참조 위치", "관련 ID"]

# 키, 이름, 형식(정규식), 번호 폭, 정의 없는 참조를 오류로 볼지
FAMILIES = [
    ("D", "결정", r"D-\d+", 2, True),
    ("DEV", "백로그(개발)", r"DEV-\d{2,3}", 2, True),
    ("WIKI", "백로그(위키)", r"WIKI-\d{2}", 2, True),
    ("AIG", "백로그(AI 게이트웨이)", r"AIG-\d{2}", 2, True),
    ("RM", "백로그(방향 갱신)", r"RM-\d{2}", 2, True),
    ("OPS", "백로그(운영)", r"OPS-\d{2}", 2, True),
    ("RES", "백로그(옛 번호)", r"RES-\d{2}", 2, False),
    ("G", "WBS 작업", r"G\d{2}\.\d{2}", 2, True),
    ("F", "기능", r"F-\d{2}", 2, False),
    ("POL", "정책", r"POL-\d{2}", 2, True),
    ("E", "시험", r"E\d{2}", 2, False),
    ("CMP", "구성요소", r"CMP-\d{2}", 2, True),
    ("OSS", "OSS 재사용", r"OSS-\d{2}", 2, True),
    ("DEP", "배포", r"DEP-\d{2,}", 2, True),
    ("DOC", "자료", r"DOC-\d{3,}", 3, True),
    ("TH", "위협", r"TH-\d{2}", 2, True),
    ("LR", "로컬 도구 위험", r"LOCAL-RISK-\d{2}", 2, True),
    ("RT", "런타임 정책", r"(?:P|MCP|ENDPOINT)-(?:[A-Z][A-Z0-9]*-)+\d{3}|PAC-\d{2}(?:-[A-Z]+)*|P-CONTROL-FAIL-CLOSED|INPUT_CONTRACT|POLICY_BUNDLE", 3, True),
    ("PAC", "원본 PAC", r"PAC\d{2}", 2, True),
    ("CMT", "제품 기능 대조", r"CMP-\d{3}", 3, True),
]
LABEL = {k: n for k, n, *_ in FAMILIES}
STRICT = {k: re.compile(p) for k, _, p, *_ in FAMILIES}
ERROR_IF_UNDEFINED = {k for k, *_, e in FAMILIES if e}
NO_REFS_EXPECTED = {"DEP", "DOC"}  # 시트 번호표라 본문에서 부르지 않는다
TOKEN = {k: re.compile(r"(?<![A-Za-z0-9_.-])(?:" + p + r")(?![A-Za-z0-9_]|-\d|\.\d)") for k, _, p, *_ in FAMILIES}
# 접두어는 같은데 자릿수·형식이 다른 토큰(DEV-1, POL-100 …)을 형식 위반으로 잡는다
NEAR = re.compile(r"(?<![A-Za-z0-9_.-])((?:DEV|WIKI|AIG|RM|OPS|POL|CMP|OSS|DEP|DOC|TH)-\d+|D-0\d{2,}|D-00?)(?![A-Za-z0-9_]|\.\d)")
TAIL = re.compile(r"((?:[·~]\d+)+)")
RANGE_KEYS = {"D", "DEV", "WIKI", "AIG", "RM", "OPS", "POL"}

SCAN_EXT = {".md", ".py", ".rego", ".json", ".yaml", ".yml", ".sh", ".ps1", ".mjs", ".js", ".sql", ".toml", ".psv", ".csv", ".html", ".txt", ".drawio"}
SKIP_PREFIX = (f"{WIKI}/sources/", f"{WIKI}/threats/extracted/", f"{WIKI}/sheet/")  # 원문 사본·추출본·시트 생성물
SKIP_FILES = {f"{WIKI}/tools/check_trace.py",  # 시험용 가짜 ID
              f"{WIKI}/trace/README.md",  # 형식 설명
              f"{WIKI}/analysis/drive-curation/workbook-review.json",  # 엑셀 셀 주소(E20 …)
              "research/collaboration-console/test_console.py"}  # 시험용 가짜 작업 G11.01
RESERVED = f"{WIKI}/trace/reserved.md"
KEEP_PREFIX = (f"{WIKI}/sheet/seed/",)
# 시점 보존 문서: 당시 ID를 그대로 적었으므로 정의 없는 참조·형식 위반으로 보지 않는다
HISTORY = ("snapshot-before-", f"{WIKI}/status/history-", f"{WIKI}/status/reports/")
# 절 제목이 곧 그 절의 소유 ID인 문서: 절 안의 다른 ID가 소유 ID의 관련 ID가 된다
OWNED = {"docs/ai/DECISIONS.md": r"^## (D-\d+)\b", f"{WIKI}/threats/policies-50.md": r"^## (POL-\d{2})\b"}


def norm(fam, ident):
    """D-7과 D-07은 같은 결정이다(시트 규칙: 한 자리는 선행 0)."""
    if fam == "D":
        n = int(ident[2:])
        return f"D-{n:02d}" if n < 10 else f"D-{n}"
    return ident


def number(ident):
    return int(re.findall(r"\d+", ident)[-1])


def fmt(fam, n):
    width = next(w for k, _, _, w, _ in FAMILIES if k == fam)
    prefix = {"LR": "LOCAL-RISK-", "G": "G", "E": "E"}.get(fam, fam + "-")
    return f"{prefix}{n:0{width}d}" if fam != "D" else norm("D", f"D-{n}")


# ---------------------------------------------------------------- 정의

def json_ids(text, pattern, keys=("title", "name", "task", "feature")):
    """JSON 안 dict의 id 중 pattern에 맞는 것: [(id, 제목, 첫 행)]. id 줄이 곧 정의 위치."""
    first = {}
    for n, line in enumerate(text.splitlines(), 1):
        m = re.search(r'"id"\s*:\s*"([^"]+)"', line)
        if m:
            first.setdefault(m[1], n)
    found = {}

    def walk(node):
        if isinstance(node, dict):
            ident = node.get("id")
            if isinstance(ident, str) and re.fullmatch(pattern, ident):
                found.setdefault(ident, next((str(node[k]) for k in keys if node.get(k)), ""))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(json.loads(text))
    return [(i, t, first.get(i, 1)) for i, t in found.items()]


def collect_defs(read):
    """정의 정본에서 [(계열, ID, 제목, 경로, 행)]을 모은다. read(경로) → 본문 또는 None."""
    out = []

    def add(fam, ident, title, path, line):
        out.append((fam, norm(fam, ident), " ".join(str(title).split())[:120], path, line))

    def lines(path):
        return enumerate((read(path) or "").splitlines(), 1)

    def headings(path, pattern):
        for n, line in lines(path):
            m = re.match(pattern, line)
            if m:
                yield m, n

    for m, n in headings("docs/ai/DECISIONS.md", r"## (D-\d+)\s+(.+)$"):
        add("D", m[1], m[2], "docs/ai/DECISIONS.md", n)
    backlog = f"{WIKI}/status/backlog.md"
    for n, line in lines(backlog):
        m = re.match(r"\| ([A-Z]+)-(\d+) \| ([^|]*)\|", line)
        if m and m[1] in LABEL:
            add(m[1], f"{m[1]}-{m[2]}", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m[3]), backlog, n)
    for m, n in headings(f"{WIKI}/threats/policies-50.md", r"## (POL-\d{2})\s+(.+)$"):
        add("POL", m[1], m[2], f"{WIKI}/threats/policies-50.md", n)
    mapping = f"{WIKI}/analysis/drive-curation/policy-id-mapping.json"
    text = read(mapping)
    if text:  # 원본 PAC01~PAC{count}는 독스용 정책표 전체이고, 번호 대응 JSON의 systems가 개수를 고정한다
        data = json.loads(text)
        names = {l["id"]: r["name"] for r in data["mappings"] for l in r["links"] if l["system"] == "pac50-docs"}
        line = next((n for n, s in lines(mapping) if '"id": "pac50-docs"' in s), 1)
        for k in range(1, next(s["count"] for s in data["systems"] if s["id"] == "pac50-docs") + 1):
            add("PAC", f"PAC{k:02d}", names.get(f"PAC{k:02d}", "(빈 행)"), mapping, line)
    for path, pattern, fam in [(f"{WIKI}/analysis/development-wbs/snapshot.json", r"G\d{2}\.\d{2}", "G"),
                               (f"{WIKI}/catalogs/experiments.json", r"E\d{2}", "E"),
                               (f"{WIKI}/analysis/oss-reuse.json", r"OSS-\d{2}", "OSS"),
                               (f"{WIKI}/catalogs/threats.json", r"TH-\d{2}", "TH"),
                               (f"{WIKI}/catalogs/local-tool-risks.json", r"LOCAL-RISK-\d{2}", "LR"),
                               (f"{WIKI}/analysis/competitor-mapping.json", r"CMP-\d{3}", "CMT")]:
        text = read(path)
        for ident, title, n in (json_ids(text, pattern) if text else []):
            add(fam, ident, title, path, n)
    spec = f"{WIKI}/analysis/feature-spec-2026-10-17/feature-spec.json"
    seen_spec = 0  # 기능 ID는 원본 순서(F-01…)다
    for n, line in lines(spec):
        if re.match(r'\s*"wbs"\s*:', line):
            break
        m = re.match(r'   "feature"\s*:\s*"([^"]*)"', line)
        if m:
            seen_spec += 1
            add("F", f"F-{seen_spec:02d}", m[1], spec, n)
    components = "docs/ai/architecture/components.psv"
    for n, line in lines(components):
        m = re.match(r"(CMP-\d+)\|([^|]*)\|", line)
        if m:
            add("CMP", m[1], m[2], components, n)
    manifest = f"{WIKI}/sheet/manifest.json"
    text = read(manifest)
    if text:
        for n, line in lines(manifest):
            m = re.search(r'"([^"]+)"\s*:\s*"((?:DEP|DOC|WIKI)-\d+)"', line)
            if m:
                add(m[2].split("-")[0], m[2], m[1], manifest, n)
    for n, line in lines(RESERVED):  # 다른 브랜치·제안·폐기로 번호만 잡아 둔 것
        m = re.match(r"\| ([^| ]+) \| ([^|]*)\| ([^|]*)\| ([^|]*)\|", line)
        fam = next((k for k, rx in STRICT.items() if m and rx.fullmatch(m[1])), None)
        if fam:
            add(fam, m[1], f"[{m[2].strip()}] {m[4].strip()}", RESERVED, n)
    ledger = "full_stack_lab/opa/policy_ledger.json"
    text = read(ledger)
    if text:
        entries = json.loads(text)["policy_ledger"]
        for n, line in lines(ledger):
            m = re.match(r'    "([^"]+)": \{', line)
            if m and m[1] in entries:
                add("RT", m[1], entries[m[1]].get("name", ""), ledger, n)
    return out


# ---------------------------------------------------------------- 참조

def find_ids(line):
    """한 줄에서 [(계열, 정규화한 ID)]. DEV-66·67, D-12~15 같은 묶음 표기를 풀어 준다."""
    found = []
    for fam, rx in TOKEN.items():
        for m in rx.finditer(line):
            found.append((fam, norm(fam, m[0])))
            tail = TAIL.match(line, m.end()) if fam in RANGE_KEYS else None
            if tail:
                prefix, current = m[0].rsplit("-", 1)[0] + "-", int(m[0].rsplit("-", 1)[1])
                for sep, num in re.findall(r"([·~])(\d+)", tail[1]):
                    nxt = int(num)
                    span = range(current + 1, nxt + 1) if sep == "~" and 0 < nxt - current <= 100 else [nxt]
                    found.extend((fam, norm(fam, f"{prefix}{k:0{len(m[0]) - len(prefix)}d}")) for k in span)
                    current = nxt
    return found


def analyze(defs, texts):
    """defs와 {경로: 본문}으로 계열별 정의·참조·관련 ID·오류·경고를 만든다."""
    info = {}
    for fam, ident, title, path, line in defs:
        row = info.setdefault(ident, {"fam": fam, "title": title, "defs": [], "refs": [], "rel": Counter()})
        row["defs"].append((path, line))
    errors, warnings, format_errors = [], [], []
    for ident, row in info.items():
        if not STRICT[row["fam"]].fullmatch(ident):
            errors.append(f"형식 위반 정의: {ident} ({row['defs'][0][0]}:{row['defs'][0][1]})")
        if len(row["defs"]) > 1:
            errors.append(f"중복 정의 {ident}: " + ", ".join(f"{p}:{l}" for p, l in row["defs"]))
    for path, text in texts.items():
        history = any(h in path for h in HISTORY)
        owner_rx = re.compile(OWNED[path]) if path in OWNED else None
        owner = None
        for n, line in enumerate(text.splitlines(), 1):
            if owner_rx and (m := owner_rx.match(line)):
                owner = norm("D" if path.endswith("DECISIONS.md") else "POL", m[1])
            found = find_ids(line)
            for m in NEAR.finditer(line):
                fams = [f for f, rx in STRICT.items() if rx.fullmatch(m[1])]
                if not fams and not history:
                    format_errors.append(f"형식 위반 참조 {m[1]} ({path}:{n})")
            ids = sorted({i for _, i in found} | ({owner} if owner else set()))
            for fam, ident in found:
                row = info.setdefault(ident, {"fam": fam, "title": "", "defs": [], "refs": [], "rel": Counter()})
                row["refs"].append((path, n, history))
            for a in ids:
                if a in info:
                    for b in ids:
                        if a != b:
                            info[a]["rel"][b] += 1
    # 정의 줄 자신은 참조에서 뺀다
    for ident, row in info.items():
        own = set(row["defs"])
        row["refs"] = [(p, l, h) for p, l, h in row["refs"] if (p, l) not in own]
    errors += sorted(set(format_errors))
    undefined, unreferenced, history_only = defaultdict(list), defaultdict(list), []
    for ident, row in sorted(info.items(), key=lambda kv: (kv[1]["fam"], number(kv[0]) if re.search(r"\d", kv[0]) else 0, kv[0])):
        live = [r for r in row["refs"] if not r[2]]
        if not row["defs"] and live:
            undefined[row["fam"]].append((ident, live))
        elif not row["defs"] and row["refs"]:
            history_only.append(ident)
        elif row["defs"] and not row["refs"] and row["fam"] not in NO_REFS_EXPECTED and row["defs"][0][0] != RESERVED:
            unreferenced[row["fam"]].append(ident)
    for fam, items in undefined.items():
        for ident, live in items:
            msg = f"정의 없는 참조 {ident}: " + ", ".join(f"{p}:{l}" for p, l, _ in live[:3]) + (f" 외 {len(live) - 3}곳" if len(live) > 3 else "")
            (errors if fam in ERROR_IF_UNDEFINED else warnings).append(msg)
    if history_only:
        warnings.append(f"시점 보존 문서에만 있는 정의 없는 ID {len(history_only)}종: " + ", ".join(history_only[:8]) + (" …" if len(history_only) > 8 else ""))
    for fam, items in unreferenced.items():
        warnings.append(f"참조 0 ({LABEL[fam]}) {len(items)}건: " + ", ".join(items[:8]) + (" …" if len(items) > 8 else ""))
    return info, errors, warnings


def rows_of(info):
    """추적표 행. 계열 순서 → 번호 순서."""
    order = {k: i for i, (k, *_) in enumerate(FAMILIES)}
    rows = []
    for ident, row in sorted(info.items(), key=lambda kv: (order[kv[1]["fam"]], number(kv[0]) if re.search(r"\d", kv[0]) else 0, kv[0])):
        refs = sorted(row["refs"])
        files = list(dict.fromkeys(p for p, _, _ in refs))
        shown = [next(f"{p}:{l}" for p, l, _ in refs if p == f) for f in files[:5]]
        more = len(refs) - len(shown)
        rows.append({"ID": ident, "계열": LABEL[row["fam"]], "제목": row["title"] or ("" if row["defs"] else "(정의 없음)"),
                     "정의 위치": SEP.join(f"{p}:{l}" for p, l in row["defs"]), "참조 수": len(refs),
                     "참조 위치": SEP.join(shown) + (f" 외 {more}곳" if more > 0 and shown else ""),
                     "관련 ID": SEP.join(i for i, _ in sorted(row["rel"].items(), key=lambda kv: (-kv[1], kv[0]))[:10])})
    return rows


# ---------------------------------------------------------------- 저장소

def git(*args, check=True):
    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=check)
    return done.stdout.decode("utf-8", "replace")


def tree_read(path):
    try:
        return (ROOT / path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def batch_reader():
    """브랜치마다 git show를 띄우면 느리다. cat-file --batch 하나로 'ref:경로'를 연달아 읽는다."""
    proc = subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(spec):
        proc.stdin.write(spec.encode("utf-8") + b"\n")
        proc.stdin.flush()
        head = proc.stdout.readline().split()
        if head[-1] == b"missing":
            return None
        data = proc.stdout.read(int(head[2]) + 1)[:-1]
        return data.decode("utf-8-sig", "replace") if head[1] == b"blob" else None
    return read


def scan_texts():
    paths = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    texts = {}
    for path in paths:
        if not path or Path(path).suffix.lower() not in SCAN_EXT:
            continue
        if path in SKIP_FILES or (path.startswith(SKIP_PREFIX) and not path.startswith(KEEP_PREFIX)):
            continue
        text = tree_read(path)
        if text is not None:
            texts[path] = text
    return texts


def analyze_tree():
    return analyze(collect_defs(tree_read), scan_texts())


def next_id(family, fetch=True):
    """로컬 작업 트리·로컬 브랜치·origin 브랜치의 정의 중 가장 큰 번호 + 1."""
    goal = re.fullmatch(r"G(\d{2})", family)
    fam = "G" if goal else family
    if fam not in LABEL or fam in {"RT", "PAC", "RES"}:
        raise SystemExit("번호를 발급하는 계열: " + " ".join(k for k in LABEL if k not in {"RT", "PAC", "RES"}) + " G01~G10(목표별)")
    if fetch and subprocess.run(["git", "-C", str(ROOT), "fetch", "--prune", "-q", "origin"], capture_output=True).returncode:
        print("경고: git fetch 실패 — 마지막으로 받은 원격 상태로 계산한다", file=sys.stderr)
    tips = {}  # 같은 커밋을 가리키는 로컬·원격 브랜치는 한 번만 읽는다
    for line in git("for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads", "refs/remotes/origin").splitlines():
        sha, ref = line.split(" ", 1)
        if ref != "origin" and not ref.endswith("/HEAD"):
            tips.setdefault(sha, []).append(ref)
    batch = batch_reader()
    best = (0, "작업 트리")
    sources = [("작업 트리", tree_read)] + [(refs[0], (lambda path, r=refs[0]: batch(f"{r}:{path}"))) for refs in tips.values()]
    for source, read in sources:
        for f, ident, *_ in collect_defs(read):
            if f == fam and (not goal or ident.startswith(family + ".")) and (n := number(ident)) > best[0]:
                best = (n, source)
    new = f"{family}.{best[0] + 1:02d}" if goal else fmt(fam, best[0] + 1)
    print(f"최대 {best[0]} ({best[1]}), 확인한 곳: 작업 트리 + 브랜치 끝점 {len(tips)}개", file=sys.stderr)
    return new


def export(rows, path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_sheet_export as sheet  # 같은 CSV 규칙(UTF-8, LF, 인용, 수식 방지)을 쓰려고 빌린다. openpyxl 필요
    Path(path).write_bytes(sheet.csv_bytes(HEADERS, rows))


# ---------------------------------------------------------------- 시험

def self_test():
    files = {
        "docs/ai/DECISIONS.md": "# 결정\n## D-7 하나 (2026-10-01)\n본문 DEV-02\n## D-8 둘\n## D-8 둘 again\n## D-10 셋\n",
        f"{WIKI}/status/backlog.md": "| ID | 작업 |\n| --- | --- |\n| DEV-01 | 첫째 |\n| DEV-02 | 둘째 |\n| AIG-01 | 셋째 |\n",
        "code.py": "# D-07 와 D-999, DEV-1, DEV-66·67, D-9~10, DEV-01\nx = 'ND-12 D-8x'\n",
        f"{WIKI}/status/reports/old.md": "옛 보고 D-998\n",
    }
    defs = collect_defs(files.get)
    assert [(f, i) for f, i, *_ in defs] == [("D", "D-07"), ("D", "D-08"), ("D", "D-08"), ("D", "D-10"), ("DEV", "DEV-01"), ("DEV", "DEV-02"), ("AIG", "AIG-01")]
    info, errors, warnings = analyze(defs, files)
    text = "\n".join(errors)
    assert "중복 정의 D-08" in text, text
    assert "정의 없는 참조 D-999" in text and "D-998" not in text, text  # 시점 보존 문서는 제외
    assert "정의 없는 참조 DEV-66" in text and "DEV-67" in text, text  # 묶음 표기 풀이
    assert "정의 없는 참조 D-09" in text and "정의 없는 참조 D-12" not in text, text  # ND-12는 다른 토큰, D-9~10은 둘 다
    assert "형식 위반 참조 DEV-1 " in text, text
    assert "D-8x" not in text
    assert info["D-07"]["refs"], "D-7 정의에 D-07 참조가 붙어야 한다"
    assert "DEV-02" in info["D-07"]["rel"], "절 안 ID는 소유 결정의 관련 ID"
    assert any("참조 0" in w for w in warnings)
    row = next(r for r in rows_of(info) if r["ID"] == "DEV-01")
    assert row["참조 수"] == 1 and row["정의 위치"].endswith("backlog.md:3"), row
    assert fmt("E", 20) == "E20" and fmt("D", 9) == "D-09" and fmt("D", 191) == "D-191" and fmt("DEV", 100) == "DEV-100" and fmt("DOC", 7) == "DOC-007"
    print("self-test: PASS (정의·중복·정의 없는 참조·형식·묶음 표기·시점 보존·관련 ID)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--next", metavar="계열", help="다음 빈 번호: " + " ".join(k for k in LABEL if k not in {"RT", "PAC", "RES"}))
    parser.add_argument("--no-fetch", action="store_true", help="--next에서 git fetch를 생략")
    parser.add_argument("--export", nargs="?", const=EXPORT, metavar="경로", help="추적표 CSV (기본 " + EXPORT + ")")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true", help="경고를 모두 출력")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.next:
        print(next_id(args.next, not args.no_fetch))
        return 0
    info, errors, warnings = analyze_tree()
    if args.export:
        export(rows_of(info), ROOT / args.export)
        print(f"추적표 {len(info)}행 → {args.export}")
    count = Counter(r["fam"] for r in info.values() if r["defs"])
    print("정의 건수: " + ", ".join(f"{LABEL[k]} {count[k]}" for k, *_ in FAMILIES if count[k]))
    for text in errors:
        print("오류:", text)
    for text in warnings if args.verbose else warnings[:12]:
        print("경고:", text)
    if len(warnings) > 12 and not args.verbose:
        print(f"경고 {len(warnings) - 12}건 더(-v)")
    print(f"결과: 오류 {len(errors)}, 경고 {len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
