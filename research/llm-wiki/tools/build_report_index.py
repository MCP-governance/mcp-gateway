"""status/reports/*.md 색인(status/reports/README.md)을 만든다. 표준 라이브러리만 쓴다.

작업 ID(DEV-·WIKI-…)나 결정 번호로 보고서를 찾는 입구다. 보고서 본문은 읽지 않고 제목·첫 문장·언급 ID만 뽑는다.
  python research/llm-wiki/tools/build_report_index.py           # 다시 만든다
  python research/llm-wiki/tools/build_report_index.py --check   # 최신인지만 본다(낡았으면 종료 코드 1)
  python research/llm-wiki/tools/build_report_index.py --find DEV-89 D-197   # 그 ID를 언급한 보고서 목록
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "status/reports"
OUT = REPORTS / "README.md"
TASK = re.compile(r"\b(?:DEV|WIKI|AIG|OPS|RM|RES)-\d{2,3}\b")
DECISION = re.compile(r"\bD-\d{1,3}\b")
META = ("작업자", "코드 기준", "시작 근거", "해결할", "기준 commit", "기준 커밋", "작성")
NAME = re.compile(r"(\d{4}-\d{2}-\d{2})-(.+)\.md$")


def norm_decision(ident):
    n = int(ident[2:])
    return f"D-{n:02d}" if n < 10 else f"D-{n}"


def summary(text):
    """'## 결과' 아래 첫 문장, 없으면 제목 뒤 첫 일반 문단의 첫 문장."""
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("## 결과")), 1)
    for line in lines[start:]:
        plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).strip().lstrip("-*> ").replace("`", "").replace("**", "")
        if plain and not plain.startswith(("#", "|", "---", "```")) and len(plain) > 8 and not plain.startswith(META):
            sentence = re.split(r"(?<=[.。!?])\s", plain)[0]
            return sentence[:80] + ("…" if len(sentence) > 80 else "")
    return "—"


def records():
    out = []
    for path in sorted(REPORTS.glob("*.md")):
        m = NAME.match(path.name)
        if not m:
            continue
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
        tasks = Counter(TASK.findall(text))
        decisions = Counter(norm_decision(d) for d in DECISION.findall(text))
        out.append({"date": m[1], "file": path.name, "title": title, "summary": summary(text),
                    "tasks": [t for t, _ in tasks.most_common(4)],
                    "decisions": [d for d, _ in decisions.most_common(3)], "ids": set(tasks) | set(decisions)})
    return out


def cell(text):
    return text.replace("|", "/").replace("[", "(").replace("]", ")")


def render(recs):
    others = sorted(p.name for p in REPORTS.iterdir() if p.is_file() and p.suffix != ".md")
    out = ["# 작업 보고서 색인", "",
           "`build_report_index.py`가 만든 생성 파일이다. 직접 고치지 않는다. 작업 ID나 결정 번호는 이 파일에서 검색하거나 "
           "`build_report_index.py --find DEV-89`로 찾는다. 새 보고서를 쓴 뒤에는 도구를 다시 실행한다. "
           "「관련 ID」는 본문에서 많이 언급된 순이며 그 보고서가 정의한 ID라는 뜻은 아니다.", "",
           f"보고서 {len(recs)}개(최신순). 원본 증거 파일 {len(others)}개(JSON·JSONL·패치)는 같은 폴더에 있다.", "",
           "| 날짜 | 보고서 | 첫 문장 | 관련 ID |", "| --- | --- | --- | --- |"]
    for r in sorted(recs, key=lambda x: (x["date"], x["file"]), reverse=True):
        ids = " ".join(r["tasks"] + r["decisions"]) or "—"
        out.append(f"| {r['date']} | [{cell(r['title'])}]({r['file']}) | {cell(r['summary'])} | {ids} |")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--find", nargs="+", metavar="ID")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    recs = records()
    if args.find:
        wanted = {norm_decision(i) if i.upper().startswith("D-") else i.upper() for i in args.find}
        hits = [r for r in recs if wanted & r["ids"]]
        for r in sorted(hits, key=lambda x: x["date"], reverse=True):
            print(f"status/reports/{r['file']}  {r['title']}")
        return 0 if hits else 1
    text = render(recs)
    if args.check:
        current = OUT.read_text(encoding="utf-8").replace("\r\n", "\n") if OUT.exists() else ""
        if current != text:
            print("보고서 색인이 낡았다: build_report_index.py 로 다시 만든다")
            return 1
        print("보고서 색인 최신")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"{OUT.relative_to(ROOT.parents[1])} 갱신: 보고서 {len(recs)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
