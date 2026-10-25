"""docs/ai/DECISIONS.md 색인·조회·번호대 분할. 표준 라이브러리만 쓴다.

  index [--check]   status/decisions-index.md 생성(분할 전후 모두 동작). --check는 최신인지만 본다.
  show D-199 ...    결정 본문만 출력한다(2,400줄을 열지 않고 한 건만 읽기).
  split [--write]   50개 단위 번호대 파일(docs/ai/decisions/)로 나누고 DECISIONS.md를 안내문으로 바꾼다.
                    --write 없이는 계획만 출력한다. 이미 나뉜 상태에서 다시 실행하면 번호대를 바로잡는다.
  check             분할 상태에서 결정이 제 번호대 파일에 있는지, 번호가 중복되지 않는지 본다.
"""
import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict

import decisions_layout as dl

INDEX = dl.REPO / "research/llm-wiki/status/decisions-index.md"
STUB_HEAD = """# 설계 결정 기록 (v2·v3)

> 형식: 결정 · 이유 · 대안과 버린 이유 · 되돌릴 조건. 번호는 다른 문서에서 `D-07`처럼 인용한다.
> 결정 본문은 번호대별 파일 `decisions/`에 있다. 새 결정은 가장 큰 번호대 파일 맨 아래에 `## D-번호 제목 (날짜)`로 추가하고
> (50개를 넘으면 `split_decisions.py split --write`가 새 파일을 만든다), 뒤집으면 원래 항목에 "→ D-xx로 대체"를 적는다(지우지 않는다).
> 추가·수정 뒤에는 `python research/llm-wiki/tools/split_decisions.py index`로 색인을 다시 만든다.

한 건만 읽으려면: `python research/llm-wiki/tools/split_decisions.py show D-199`.
전체 목록은 [결정 색인](../../research/llm-wiki/status/decisions-index.md).

| 번호대 | 파일 | 결정 수 |
| --- | --- | ---: |
"""


BAND, band_of, band_name = dl.BAND, dl.band_of, dl.band_name


def all_sections():
    return list(dl.sections())


def render_index(secs):
    by_band = defaultdict(list)
    for s in secs:
        by_band[band_of(s["num"])].append(s)
    nums = {s["num"] for s in secs}
    gaps = [n for n in range(1, max(nums) + 1) if n not in nums]
    out = ["# 결정 색인", "",
           "`split_decisions.py index`가 만든 생성 파일이다. 직접 고치지 않는다. 본문은 위치 칸의 파일에서 읽거나 "
           "`python research/llm-wiki/tools/split_decisions.py show D-번호`로 한 건만 출력한다.", "",
           f"결정 {len(secs)}개 · 최대 번호 {max(nums)} · 저장 형태: "
           f"{'번호대 분할(docs/ai/decisions/)' if dl.is_split() else '단일 파일(docs/ai/DECISIONS.md)'}", ""]
    for band in sorted(by_band):
        out += [f"## 번호 {band * BAND + 1}~{band * BAND + BAND}", "", "| 번호 | 결정 | 날짜 | 위치 |", "| --- | --- | --- | --- |"]
        for s in sorted(by_band[band], key=lambda x: x["num"]):
            link = f"[{s['path'].rsplit('/', 1)[-1]}:{s['line']}](../../../{s['path']})"
            out.append(f"| {s['id']} | {s['title'].replace('|', '/')} | {s['date'] or '—'} | {link} |")
        out.append("")
    out += ["## 비어 있는 번호", "",
            ("없음" if not gaps else ", ".join(str(n) for n in gaps)) +
            " — 예약했거나 쓰지 않은 번호다. 예약한 것은 [예약 번호](../trace/reserved.md) 표에 있다.", ""]
    return "\n".join(out)


def cmd_index(args):
    text = render_index(all_sections())
    if args.check:
        current = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"결정 색인이 낡았다: split_decisions.py index 로 다시 만든다 ({INDEX.relative_to(dl.REPO)})")
            return 1
        print("결정 색인 최신")
        return 0
    INDEX.write_text(text, encoding="utf-8", newline="\n")
    print(f"{INDEX.relative_to(dl.REPO)} 갱신")
    return 0


def cmd_show(args):
    found = {s["num"]: s for s in dl.sections()}
    missing = []
    for ident in args.ids:
        s = found.get(int(re.sub(r"\D", "", ident)))
        if s:
            print(f"<!-- {s['path']}:{s['line']} -->\n{s['text'].rstrip()}\n")
        else:
            missing.append(ident)
    if missing:
        print("없음: " + ", ".join(missing), file=sys.stderr)
    return 1 if missing else 0


def plan_split(secs):
    bands = defaultdict(list)
    for s in secs:
        bands[band_of(s["num"])].append(s)
    return bands


ANCHOR_LINK = re.compile(r"(\]\([^)#\s]*?)DECISIONS\.md#d-(\d+)")


def relink():
    """`DECISIONS.md#d-61-…` 앵커 링크를 그 결정이 있는 번호대 파일로 돌린다(git이 추적하는 Markdown만)."""
    tracked = subprocess.run(["git", "-C", str(dl.REPO), "ls-files", "-z", "*.md"], capture_output=True).stdout.decode("utf-8")
    count = 0
    for name in filter(None, tracked.split("\0")):
        if name.startswith(("research/llm-wiki/sources/", "research/llm-wiki/papers/")):
            continue
        path = dl.REPO / name
        text = path.read_bytes().decode("utf-8")
        new, n = ANCHOR_LINK.subn(lambda m: f"{m[1]}decisions/{band_name(band_of(int(m[2])))}#d-{m[2]}", text)
        if n:
            path.write_bytes(new.encode("utf-8"))
            count += n
    return count


def cmd_split(args):
    secs = all_sections()
    ids = Counter(s["id"] for s in secs)
    dup = [i for i, n in ids.items() if n > 1]
    if dup:
        print("중복 번호가 있어 중단: " + ", ".join(dup), file=sys.stderr)
        return 1
    bands = plan_split(secs)
    for band in sorted(bands):
        print(f"{band_name(band)}: {len(bands[band])}개 (번호 {min(s['num'] for s in bands[band])}~{max(s['num'] for s in bands[band])})")
    if not args.write:
        print("계획만 출력했다. 실행: split --write (이후 index 실행, 아래 「분할 뒤 할 일」은 보고서 참조)")
        return 0
    before = {s["id"]: s["text"] for s in secs}
    dl.SPLIT_DIR.mkdir(exist_ok=True)
    stale = {p for p in dl.SPLIT_DIR.glob("D-*.md")}
    written = set()
    for band, items in bands.items():
        path = dl.SPLIT_DIR / band_name(band)
        head = f"# 설계 결정 번호 {band * BAND + 1}~{band * BAND + BAND}\n\n"
        path.write_text(head + "".join(s["text"] if s["text"].endswith("\n") else s["text"] + "\n" for s in items),
                        encoding="utf-8", newline="\n")
        written.add(path)
    for path in stale - written:
        path.unlink()
    table = "".join(f"| {b * BAND + 1}~{b * BAND + BAND} | [decisions/{band_name(b)}](decisions/{band_name(b)}) | {len(bands[b])} |\n"
                    for b in sorted(bands))
    dl.SINGLE.write_text(STUB_HEAD + table, encoding="utf-8", newline="\n")
    after = {s["id"]: s["text"] for s in dl.sections()}
    if {k: v.strip() for k, v in before.items()} != {k: v.strip() for k, v in after.items()}:
        print("분할 뒤 본문이 원본과 다르다 — git checkout으로 되돌릴 것", file=sys.stderr)
        return 1
    INDEX.write_text(render_index(list(dl.sections())), encoding="utf-8", newline="\n")
    relinked = relink()
    print(f"분할 완료: {len(written)}개 파일, 본문 {len(after)}건 일치 확인, 색인 갱신, 앵커 링크 {relinked}개 고침")
    return 0


def cmd_check(_):
    if not dl.is_split():
        print("분할 전(단일 파일) — 검사할 번호대 없음")
        return 0
    bad = []
    for s in dl.sections():
        if s["path"].rsplit("/", 1)[-1] != band_name(band_of(s["num"])):
            bad.append(f"{s['id']}는 {s['path']}에 있으나 {band_name(band_of(s['num']))}여야 한다")
    ids = Counter(s["id"] for s in dl.sections())
    bad += [f"{i} 중복" for i, n in ids.items() if n > 1]
    for line in bad:
        print(line)
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index"); p.add_argument("--check", action="store_true"); p.set_defaults(fn=cmd_index)
    p = sub.add_parser("show"); p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("split"); p.add_argument("--write", action="store_true"); p.set_defaults(fn=cmd_split)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
