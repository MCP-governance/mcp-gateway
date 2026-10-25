"""작업 ID 또는 결정 번호 하나로 백로그 행·결정·보고서를 한 번에 찾는다. 표준 라이브러리만 쓴다.

  python research/llm-wiki/tools/lookup.py DEV-89          # 백로그 행 + 그 ID를 언급한 결정·보고서
  python research/llm-wiki/tools/lookup.py D-197 --full    # 결정 본문 전체 + 언급한 보고서
큰 문서를 열지 않고 내 작업의 근거 위치만 얻는 용도다. 본문 판단은 가리킨 파일을 읽고 한다.
"""
import argparse
import re
import sys

import build_report_index as reports
import decisions_layout as dl

BACKLOG = reports.ROOT / "status/backlog.md"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--full", action="store_true", help="잘라내지 않고 전부 출력")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    backlog = BACKLOG.read_text(encoding="utf-8-sig").splitlines()
    secs = list(dl.sections())
    recs = reports.records()
    found = 0
    for raw in args.ids:
        ident = raw.upper()
        is_decision = re.fullmatch(r"D-\d+", ident)
        if is_decision:
            ident = reports.norm_decision(ident)
        print(f"== {ident}")
        for n, line in enumerate(backlog, 1):
            if line.startswith(f"| {ident} |"):
                found += 1
                print(f"백로그 status/backlog.md:{n}\n  " + (line if args.full else line[:700] + ("…" if len(line) > 700 else "")))
        for s in secs:
            if is_decision and reports.norm_decision(s["id"]) == ident:
                found += 1
                print(f"결정 {s['path']}:{s['line']}")
                body = s["text"].rstrip().splitlines()
                print("\n".join("  " + l for l in (body if args.full else body[:12])))
                if not args.full and len(body) > 12:
                    print(f"  … ({len(body) - 12}줄 더, --full 또는 split_decisions.py show {s['id']})")
            elif not is_decision and re.search(rf"\b{re.escape(ident)}\b", s["text"]):
                print(f"결정이 언급 {s['id']} {s['title'][:70]} ({s['path']}:{s['line']})")
        hits = [r for r in recs if ident in r["ids"]]
        for r in sorted(hits, key=lambda x: x["date"], reverse=True):
            found += 1
            print(f"보고서 status/reports/{r['file']}  {r['title'][:70]}")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
