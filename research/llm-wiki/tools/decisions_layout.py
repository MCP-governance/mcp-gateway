"""docs/ai 결정 기록을 한 파일(DECISIONS.md)이든 번호대별 파일(decisions/)이든 같은 방식으로 읽는다."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOC = REPO / "docs/ai"
SINGLE = DOC / "DECISIONS.md"
SPLIT_DIR = DOC / "decisions"
HEADING = re.compile(r"^## (D-\d+)\s+(.+)$", re.M)
DATE = re.compile(r"20\d{2}-\d{2}-\d{2}")
BAND = 50


def band_of(num):
    return (num - 1) // BAND


def band_name(band):
    return f"D-{band * BAND + 1:03d}-{band * BAND + BAND:03d}.md"


def repo_paths():
    """다른 브랜치·판본에서 읽을 때 쓰는 후보 경로(없는 것은 호출한 쪽이 건너뛴다)."""
    return ["docs/ai/DECISIONS.md"] + [f"docs/ai/decisions/{band_name(b)}" for b in range(40)]


def read(path):
    return Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def is_split():
    return SPLIT_DIR.is_dir() and any(SPLIT_DIR.glob("D-*.md"))


def files():
    """결정 본문이 들어 있는 파일(번호대 순). 분할 전에는 DECISIONS.md 하나."""
    return sorted(SPLIT_DIR.glob("D-*.md")) if is_split() else [SINGLE]


def rel(path):
    return Path(path).resolve().relative_to(REPO).as_posix()


def sections(paths=None):
    """파일 안 등장 순서대로 {id, num, title, date, path, line, text}를 낸다."""
    for path in paths or files():
        text = read(path)
        found = list(HEADING.finditer(text))
        for i, m in enumerate(found):
            end = found[i + 1].start() if i + 1 < len(found) else len(text)
            date = DATE.search(m[2])
            yield {"id": m[1], "num": int(m[1][2:]), "title": m[2].strip(), "date": date[0] if date else "",
                   "path": rel(path), "line": text.count("\n", 0, m.start()) + 1, "text": text[m.start():end]}


def preface(path=SINGLE):
    text = read(path)
    m = HEADING.search(text)
    return text[:m.start()] if m else text
