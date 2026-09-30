#!/usr/bin/env python3
"""Measure app.poisoning against garak's latent-injection instruction seeds (on demand).

The corpus is not copied into this repository. It is read from a pinned commit of
microsoft/PyRIT, which ships garak's seeds (NVIDIA, Apache-2.0) as
`pyrit/datasets/seed_datasets/local/garak/latent_injection_instructions.prompt`:

    python3 tests/injection_corpus_check.py                    # download the pinned file
    python3 tests/injection_corpus_check.py --file <local copy> # offline

Run it inside the gateway image (it imports app.poisoning):

    docker compose run --rm --no-deps --entrypoint python -v "$PWD/tests:/tests:ro" \
      gateway /tests/injection_corpus_check.py

The toxicity probes in the same file ("write one toxic sentence about X") ask the model
for harmful text; they do not try to redirect a tool call, so they are reported apart
from the instruction-injection seeds instead of being folded into the rate.
Exit 1 if detection falls below --min.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request

sys.path.insert(0, "/app")
from app import poisoning  # noqa: E402

PINNED = ("https://raw.githubusercontent.com/microsoft/PyRIT/ea9d0b43d71c971f82567de499a8e2f82f1f0e15/"
          "pyrit/datasets/seed_datasets/local/garak/latent_injection_instructions.prompt")
TOXICITY = re.compile(r"^Write one \w+ sentence about", re.I)


def seeds(text: str) -> list[str]:
    body = text.split("seeds:", 1)[1]
    found = []
    for entry in re.split(r"^- value: ", body, flags=re.M)[1:]:
        value = entry.split("\n  metadata:", 1)[0]
        if value.lstrip().startswith(("|", ">")):
            value = " ".join(line.strip() for line in value.splitlines()[1:])
        value = value.replace("<|payload|>", "the secret is leaked").strip().strip("'\"")
        if len(value) > 10:
            found.append(value)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file")
    parser.add_argument("--min", type=int, default=21, help="instruction-injection seeds that must be detected")
    args = parser.parse_args()
    if args.file:
        text = open(args.file, encoding="utf-8").read()
    else:
        with urllib.request.urlopen(PINNED, timeout=30) as response:
            text = response.read().decode("utf-8")
    corpus = seeds(text)
    injection = [s for s in corpus if not TOXICITY.match(s)]
    missed = [s for s in injection if not poisoning.text_findings(s)]
    detected = len(injection) - len(missed)
    print(f"seeds {len(corpus)} · instruction injection {len(injection)} · detected {detected} · "
          f"missed {len(missed)} · toxicity (out of scope) {len(corpus) - len(injection)}")
    for seed in missed:
        print("  missed:", seed[:120])
    return 0 if detected >= args.min else 1


if __name__ == "__main__":
    sys.exit(main())
