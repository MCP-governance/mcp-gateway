"""D-142: shingle length and match threshold for P-FLOW-001, measured on this repository's own documents.

Run from the repository root: python research/llm-wiki/analysis/flow-fingerprint-1020/threshold_experiment.py
The documents change with the repository, so the numbers belong to the commit in the report. The
normalisation is the Gateway's (full_stack_lab/gateway/app/flow_fingerprint.py squash).

  false matches  a 1500-character slice of one document against another document it does not copy
  kept matches   a 500-character passage copied with a change, against the original
"""
import base64
import random
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WIKI = ROOT / "research" / "llm-wiki"
sys.stdout.reconfigure(encoding="utf-8")


def squash(text):
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def hangul(text):
    flat = squash(text)
    return sum("가" <= ch <= "힣" for ch in flat) / max(1, len(flat))


def load(patterns, keep, minimum=5000):
    found = []
    for pattern in patterns:
        for path in sorted(WIKI.glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if len(text) >= minimum and keep(text):
                found.append(text)
    return found


def grams(flat, k):
    return {flat[i:i + k] for i in range(len(flat) - k + 1)}


def pairs(first, second, rng, count=1000):
    out = []
    while len(out) < count:
        a, b = rng.choice(first), rng.choice(second)
        if a is b:
            continue
        flat_b = squash(b)
        start = rng.randrange(0, max(1, len(flat_b) - 1500))
        out.append((squash(a), flat_b[start:start + 1500]))
    return out


def replace_words(text, every):
    return " ".join("zzqx" if i % every == every - 1 else w for i, w in enumerate(text.split(" ")))


def sentences(text):
    return " ".join(re.split(r"(?<=[.!?。])\s+", text)[::2])


def insert_letters(text, every=10):
    flat = squash(text)
    return "".join(flat[i:i + every] + "q" for i in range(0, len(flat), every))


VARIANTS = {
    "공백·대소문자 변경": lambda t: re.sub(r"\s+", "  ", t).upper(),
    "단어 5개마다 1개 교체": lambda t: replace_words(t, 5),
    "문장 하나씩 건너뜀": sentences,
    "글자 10개마다 1글자 삽입": insert_letters,
    "base64 인코딩": lambda t: base64.b64encode(t.encode()).decode(),
    "역순": lambda t: t[::-1],
}


def main():
    rng = random.Random(11)
    korean = load(["status/reports/*.md", "analysis/**/*.md"], lambda t: hangul(t) > 0.4)
    english = load(["sources/compliance/*/extracts/*.md", "sources/policy/**/*.md", "solutions/**/*.md"],
                   lambda t: hangul(t) < 0.05)
    print(f"문서: 한국어 중심 {len(korean)}건, 영어 {len(english)}건")
    shingle_lengths, thresholds = (10, 12, 16, 20), (1, 2, 3, 5)
    for name, a, b in (("한국어×영어(무관한 쌍)", korean, english), ("한국어×한국어(같은 프로젝트 문서)", korean, korean)):
        sample = pairs(a, b, rng)
        print(f"\n거짓 일치율: {name}, {len(sample)}쌍")
        for k in shingle_lengths:
            shared = [len(grams(x, k) & grams(y, k)) for x, y in sample]
            print(f"  길이 {k:2d}: " + "  ".join(
                f"공유 {t}개 이상 {sum(s >= t for s in shared) / len(shared) * 100:5.1f}%" for t in thresholds))
    for name, pool in (("한국어", korean), ("영어", english)):
        passages = []
        for _ in range(60):
            doc = rng.choice(pool)
            start = rng.randrange(0, len(doc) - 500)
            passages.append(doc[start:start + 500])
        print(f"\n변형 뒤에도 일치로 잡히는 비율: {name} 구절 {len(passages)}개, 공유 3개 이상")
        for label, change in VARIANTS.items():
            row = []
            for k in (12, 16, 20):
                hit = sum(len(grams(squash(p), k) & grams(squash(change(p)), k)) >= 3 for p in passages)
                row.append(f"길이 {k}: {hit / len(passages) * 100:4.0f}%")
            print(f"  {label:18s} " + "  ".join(row))


main()
