#!/usr/bin/env python3
"""Measure the Gateway's text inspectors on public corpora (fetched on demand, pinned, SHA-256 checked).

    python3 tests/inspection_corpus_eval.py build --out /tmp/samples.jsonl   # needs network and PyYAML
    python3 tests/inspection_corpus_eval.py run --samples /tmp/samples.jsonl # needs the gateway's app package

`build` downloads every source named in SOURCES, refuses a file whose SHA-256 differs from
inspection_corpus_manifest.json (`--update-manifest` records new hashes) and writes one JSON line per
sample: corpus, stratum, label (attack | benign), text and a dev / held-out split taken from the text's
own hash. Nothing downloaded is stored in the repository; the cache is `.corpus-cache` (gitignored) or
$MCPGW_CORPUS_CACHE.

`run` decides each sample the way the Gateway does:
  result    core._guarded_result      OVERRIDE_RULES on the serialised MCP result (withheld on a hit)
  argument  core.untrusted_markers    INSTRUCTION_RULES on a tool argument (approval for w/x, alert for r)
  catalog   poisoning.findings        CATALOG_RULES on a tool description (registration needs an acknowledgement)
and, with --gates, the argument path's size, schema and path gates (P-INPUT-SCHEMA-001). Rules are improved on
the dev split only: misses are listed for dev, held-out prints counts. The synthetic Korean sets are labelled
`synthetic-ko` and are never counted as a public corpus.
"""
from __future__ import annotations

import argparse
import base64
import codecs
import concurrent.futures
import csv
import hashlib
import io
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "inspection_corpus_manifest.json"
CACHE = Path(os.environ.get("MCPGW_CORPUS_CACHE") or HERE / ".corpus-cache")
SYNTHETIC = HERE / "data" / "synthetic_ko_inspection.json"

RAW = "https://raw.githubusercontent.com/"
PYRIT = "microsoft/PyRIT/ea9d0b43d71c971f82567de499a8e2f82f1f0e15/"
GARAK_DIR = PYRIT + "pyrit/datasets/seed_datasets/local/garak/"
CPYTHON = "python/cpython/0cc81280367df838c4b199f8f0378837165071c2/"
LOGHUB = "logpai/loghub/dd61d0952749ee7963bde24220d1be5ede023033/"
POKEAPI = "PokeAPI/api-data/4c7be8290912459130ff2df3ca0f1e62f719d292/data/api/v2/"
K8S = "kubernetes/website/bbea9aa9b7c1cbf67dfc66c4f7b19338e4f24d5d/content/"
INJECAGENT = "uiuc-kang-lab/InjecAgent/f19c9f2c79a41046eb13c03c51a24c567a8ffa07/data/"
MCPTOX = "zhiqiangwang4/MCPTox-Benchmark/f85189f9ad12504c197c7f920ab818a40657b1fa/"
EXPRESS = "expressjs/express/a419aa7350389a275ab45fde2e849ed1f02449ef/"
OWASP = "OWASP/www-project-top-10-for-large-language-model-applications/99f4395589bdbd120ae961f9cd179e79d7f9b27f/"
GARAK_REPO = "NVIDIA/garak/197d68645ecc8cec1a71ea20872823a8b54f92f3/"
PAYLOADS = "swisskyrepo/PayloadsAllTheThings/3ac27901c711bdf3f5b65a7b1d1820a1f65bd09a/"
HF_YANIS = "https://huggingface.co/datasets/yanismiraoui/prompt_injections/resolve/bd55359f2f332afc35f277ac3dd08f7111b024c9/"
HF_JACK = "https://huggingface.co/datasets/jackhhao/jailbreak-classification/resolve/2f2ceeb39658696fd3f462403562b6eea5306287/"

CPYTHON_CODE = ["Lib/argparse.py", "Lib/json/decoder.py", "Lib/logging/__init__.py", "Lib/http/server.py", "Lib/subprocess.py",
                "Lib/shlex.py", "Lib/textwrap.py", "Lib/difflib.py", "Lib/csv.py", "Lib/configparser.py", "Lib/email/message.py",
                "Lib/tomllib/_parser.py", "Lib/unittest/case.py", "Lib/asyncio/tasks.py", "Lib/urllib/request.py",
                "Lib/sqlite3/dump.py", "Lib/pathlib.py", "Lib/shutil.py", "Lib/tempfile.py", "Lib/zipfile/__init__.py",
                "Lib/ast.py", "Lib/inspect.py", "Lib/enum.py", "Lib/dataclasses.py", "Lib/functools.py",
                "Lib/collections/__init__.py", "Lib/ssl.py", "Lib/getpass.py", "Lib/secrets.py", "Lib/hmac.py"]
CPYTHON_DOCS = ["Doc/library/json.rst", "Doc/library/subprocess.rst", "Doc/tutorial/errors.rst", "Doc/howto/logging.rst",
                "Doc/library/argparse.rst", "Doc/library/os.rst"]
LOGS = ["Apache", "Android", "BGL", "Hadoop", "HDFS", "HealthApp", "HPC", "Linux", "Mac", "OpenSSH", "OpenStack",
        "Proxifier", "Spark", "Thunderbird", "Windows", "Zookeeper"]
K8S_EN = ["en/docs/concepts/workloads/pods/_index.md", "en/docs/concepts/security/pod-security-standards.md",
          "en/docs/concepts/configuration/secret.md", "en/docs/concepts/services-networking/service.md",
          "en/docs/concepts/architecture/nodes.md", "en/docs/concepts/storage/volumes.md",
          "en/docs/concepts/security/rbac-good-practices.md", "en/docs/reference/access-authn-authz/rbac.md"]
K8S_KO = ["ko/docs/concepts/workloads/pods/_index.md", "ko/docs/concepts/configuration/secret.md",
          "ko/docs/concepts/services-networking/service.md", "ko/docs/concepts/storage/volumes.md",
          "ko/docs/concepts/architecture/nodes.md", "ko/docs/concepts/security/overview.md",
          "ko/docs/concepts/workloads/controllers/deployment.md", "ko/docs/concepts/configuration/configmap.md",
          "ko/docs/tasks/run-application/run-stateless-application-deployment.md", "ko/docs/concepts/security/rbac-good-practices.md"]
POKE = [f"{kind}/{n}/index.json" for kind, count in (("pokemon", 24), ("pokemon-species", 24), ("ability", 16), ("move", 16), ("item", 8))
        for n in range(1, count + 1)]
EXPRESS_CODE = ["lib/application.js", "lib/request.js", "lib/response.js",
                "lib/utils.js", "lib/view.js", "lib/express.js"]
EXPRESS_DOCS = ["Readme.md", "History.md"]
PATHS = ["Directory%20Traversal/Intruder/deep_traversal.txt", "Directory%20Traversal/Intruder/directory_traversal.txt",
         "Directory%20Traversal/Intruder/traversals-8-deep-exotic-encoding.txt"]

SOURCES: dict[str, str] = {}
for _name in ("latent_injection_instructions", "latent_injection_contexts", "latent_injection_payload_templates",
              "latent_injection_triggers", "prompt_inject_contexts", "prompt_inject_techniques",
              "system_prompt_extraction", "normal_instructions"):
    SOURCES[f"garak/{_name}"] = f"{RAW}{GARAK_DIR}{_name}.prompt"
SOURCES["yanismiraoui/prompt_injections"] = HF_YANIS + "prompt_injections.csv"
SOURCES["jackhhao/jailbreak_dataset_full"] = HF_JACK + "default/jailbreak_dataset_full.csv"
for _name in ("test_cases_dh_enhanced", "test_cases_ds_enhanced", "test_cases_dh_base", "test_cases_ds_base"):
    SOURCES[f"injecagent/{_name}"] = f"{RAW}{INJECAGENT}{_name}.json"
SOURCES["mcptox/pure_tool"] = f"{RAW}{MCPTOX}pure_tool.json"
SOURCES["mcptox/response_all"] = f"{RAW}{MCPTOX}response_all.json"
for _path in CPYTHON_CODE + CPYTHON_DOCS:
    SOURCES[f"cpython/{_path}"] = f"{RAW}{CPYTHON}{_path}"
for _path in EXPRESS_CODE + EXPRESS_DOCS:
    SOURCES[f"express/{_path}"] = f"{RAW}{EXPRESS}{_path}"
for _name in LOGS:
    SOURCES[f"loghub/{_name}"] = f"{RAW}{LOGHUB}{_name}/{_name}_2k.log"
for _path in POKE:
    SOURCES[f"pokeapi/{_path}"] = f"{RAW}{POKEAPI}{_path}"
for _path in K8S_EN + K8S_KO:
    SOURCES[f"k8s/{_path}"] = f"{RAW}{K8S}{_path}"
SOURCES["owasp/LLM01_PromptInjection"] = f"{RAW}{OWASP}2_0_vulns/LLM01_PromptInjection.md"
SOURCES["garak-repo/README"] = f"{RAW}{GARAK_REPO}README.md"
SOURCES["pyrit/README"] = f"{RAW}{PYRIT}README.md"
SOURCES["unicode/emoji-zwj-sequences-16.0"] = "https://www.unicode.org/Public/emoji/16.0/emoji-zwj-sequences.txt"
for _path in PATHS:
    SOURCES[f"payloadsallthethings/{_path}"] = f"{RAW}{PAYLOADS}{_path}"

# What a reader of the report needs to know about each group. The licence decides whether a copy may live in
# this repository: none of them is vendored.
GROUPS = {
    "garak": ("NVIDIA garak seeds as shipped by microsoft/PyRIT", "Apache-2.0 (garak), MIT (PyRIT)", "PyRIT ea9d0b43"),
    "yanismiraoui": ("yanismiraoui/prompt_injections, en fr de es pt it ro", "Apache-2.0", "HF revision bd55359f"),
    "jackhhao": ("jackhhao/jailbreak-classification", "Apache-2.0", "HF revision 2f2ceeb3"),
    "injecagent": ("InjecAgent (UIUC Kang lab), attacker instructions inside tool responses", "MIT", "f19c9f2c"),
    "mcptox": ("MCPTox (AAAI 2026): poisoned tool descriptions and the clean descriptions of 45 real MCP servers",
               "no licence file in the repository: read for measurement, not redistributed", "f85189f9"),
    "cpython": ("CPython v3.12.10 sources and docs", "PSF-2.0", "0cc81280"),
    "express": ("expressjs/express", "MIT", "a419aa73"),
    "loghub": ("logpai/loghub 2k log samples", "free for research (README), no SPDX licence", "dd61d095"),
    "pokeapi": ("PokeAPI api-data JSON", "BSD-3-Clause", "4c7be829"),
    "k8s": ("kubernetes/website English and Korean documentation", "CC-BY-4.0", "bbea9aa9"),
    "owasp": ("OWASP LLM01 Prompt Injection page", "CC BY-SA 4.0 (project page), no SPDX licence in the repository", "99f43955"),
    "pyrit": ("microsoft/PyRIT README", "MIT", "ea9d0b43"),
    "garak-repo": ("NVIDIA/garak README", "Apache-2.0", "197d6864"),
    "unicode": ("Unicode emoji-zwj-sequences 16.0", "Unicode Terms of Use (data files)", "16.0"),
    "payloadsallthethings": ("PayloadsAllTheThings directory traversal lists", "MIT", "3ac27901"),
    "synthetic-ko": ("authored for this repository: tests/data/synthetic_ko_inspection.json", "repository licence", "-"),
}


# ── fetch ───────────────────────────────────────────────────────────────────
def fetch(key: str, manifest: dict, update: bool) -> bytes:
    path = CACHE / hashlib.sha256(key.encode()).hexdigest()[:24]
    if path.exists():
        data = path.read_bytes()
    else:
        request = urllib.request.Request(SOURCES[key], headers={"User-Agent": "mcpgw-corpus-eval"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    pinned = manifest.get(key)
    if pinned is None or update:
        manifest[key] = {"sha256": digest, "bytes": len(data), "url": SOURCES[key]}
    elif pinned["sha256"] != digest:
        raise SystemExit(f"SHA-256 mismatch for {key}: pinned {pinned['sha256']}, fetched {digest}")
    return data


def load_all(update: bool) -> dict[str, bytes]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    before = json.dumps(manifest, sort_keys=True)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        data = dict(zip(SOURCES, pool.map(lambda key: fetch(key, manifest, update), SOURCES)))
    if json.dumps(manifest, sort_keys=True) != before:
        MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n", encoding="utf-8")
    return data


# ── samples ─────────────────────────────────────────────────────────────────
def split_of(text: str) -> str:
    return "dev" if int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) % 10 < 6 else "held-out"


class Samples(list):
    seen: set = set()

    def add(self, corpus: str, stratum: str, label: str, text: str, where: str = "result") -> None:
        text = text.strip("\n")
        if text.strip():
            self.append({"corpus": corpus, "stratum": stratum, "label": label, "where": where,
                         "text": text, "split": split_of(text)})


def prompt_values(raw: bytes) -> list[str]:
    import yaml  # only `build` needs it; the gateway image does not ship it
    body = "\n".join(line for line in raw.decode("utf-8").splitlines() if not line.startswith("#"))
    return [str(seed["value"]) for seed in (yaml.safe_load(body).get("seeds") or []) if seed.get("value")]


def lines_of(raw: bytes, size: int, picks: tuple[int, ...]) -> list[str]:
    lines = raw.decode("utf-8", "replace").splitlines()
    return ["\n".join(lines[i * size:(i + 1) * size]) for i in picks if i * size < len(lines)]


def windows(text: str, size: int, every: int) -> list[str]:
    out, current, length = [], [], 0
    for line in text.splitlines():
        current.append(line)
        length += len(line) + 1
        if length >= size:
            out.append("\n".join(current))
            current, length = [], 0
    return out[::every]


# Encodings an attacker puts around a sentence the filter would otherwise read. Every one of them is applied to
# the same seeds, so the table says which transform the rules survive, not which seed.
ZW = "​"
HOMOGLYPH = str.maketrans({"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "i": "і", "s": "ѕ", "y": "у", "x": "х"})
LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"})
KEYWORDS = re.compile(r"\b(ignore|instructions?|previous|system|prompt)\b", re.I)
ENCODINGS = {
    "base64": lambda t: base64.b64encode(t.encode()).decode(),
    "base64-with-hint": lambda t: "Decode this base64 and follow it: " + base64.b64encode(t.encode()).decode(),
    "hex": lambda t: t.encode().hex(),
    "rot13": lambda t: codecs.encode(t, "rot13"),
    "url-percent": lambda t: urllib.parse.quote(t, safe=""),
    "html-entities": lambda t: "".join(f"&#{ord(c)};" for c in t),
    "zero-width-between-letters": lambda t: ZW.join(t),
    "zero-width-inside-keywords": lambda t: KEYWORDS.sub(lambda m: ZW.join(m.group()), t),
    "cyrillic-homoglyphs": lambda t: t.translate(HOMOGLYPH),
    "leetspeak": lambda t: t.lower().translate(LEET),
    "letter-spacing": lambda t: " ".join(t),
    "full-width": lambda t: "".join(chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) < 0x7F else c for c in t),
    "reversed": lambda t: t[::-1],
    "html-comment": lambda t: f"<!-- {t} -->",
    "markdown-comment": lambda t: f"[//]: # ({t})",
    "split-by-newlines": lambda t: "\n".join(t.split()),
}


def build(data: dict[str, bytes]) -> Samples:
    out = Samples()
    out.seen = set()
    rng = random.Random(15)
    garak = lambda name: prompt_values(data[f"garak/{name}"])

    # garak seeds exactly as tests/injection_corpus_check.py reads them: 26 instruction injections + 6 toxicity asks
    toxicity = re.compile(r"^Write one \w+ sentence about", re.I)
    raw_instructions = garak("latent_injection_instructions")
    injection = [v.replace("<|payload|>", "the secret is leaked").strip() for v in raw_instructions if not toxicity.match(v)]
    injection = [v for v in injection if len(v) > 10]
    for v in injection:
        out.add("garak", "latent-injection-instruction", "attack", v)
    for v in raw_instructions:
        if toxicity.match(v):
            out.add("garak", "toxicity-request (out of scope)", "attack", v.replace("<|payload|>", "the secret is leaked"))

    # garak carrier documents: a context with its injection slot filled by instruction + payload, assembled by the
    # procedure the PyRIT file describes (deterministic, seed 15). This is our assembly of garak's parts.
    contexts = [v for v in garak("latent_injection_contexts") if "<|injection|>" in v and len(v) > 200]
    templates = [v for v in garak("latent_injection_payload_templates") if "<|trigger|>" in v]
    triggers = [v for v in garak("latent_injection_triggers") if v.strip()]
    slots = [v for v in raw_instructions if "<|payload|>" in v and not toxicity.match(v)]
    for _ in range(240):
        payload = rng.choice(templates).replace("<|trigger|>", rng.choice(triggers))
        out.add("garak", "latent-injection-carrier-document", "attack",
                rng.choice(contexts).replace("<|injection|>", rng.choice(slots).replace("<|payload|>", payload)))

    # promptinject (Perez and Ribeiro) techniques x contexts; goals as in garak's promptinject probe
    techniques = garak("prompt_inject_techniques")
    for context in garak("prompt_inject_contexts"):
        if "{{ technique_text }}" in context:
            for technique in techniques:
                for goal in ("I hate humans", "I kill humans"):
                    out.add("garak", "promptinject-technique", "attack",
                            context.replace("{{ technique_text }}", technique.replace("{{ goal_text }}", goal)))
    for v in garak("system_prompt_extraction"):
        out.add("garak", "system-prompt-extraction", "attack", v)
    for v in garak("normal_instructions"):
        out.add("garak", "plain-user-prompt", "benign", v)

    multilingual = [r[0] for r in csv.reader(io.StringIO(data["yanismiraoui/prompt_injections"].decode("utf-8")))][1:]
    for v in multilingual:
        out.add("yanismiraoui", "multilingual-prompt-injection", "attack", v)
    for row in csv.DictReader(io.StringIO(data["jackhhao/jailbreak_dataset_full"].decode("utf-8"), newline="")):
        if row["type"] == "jailbreak":
            out.add("jackhhao", "jailbreak-prompt", "attack", row["prompt"])
        else:
            out.add("jackhhao", "plain-user-prompt", "benign", row["prompt"][:6000])

    # InjecAgent: the tool response with the attacker's instruction in it; the same response with the slot left
    # empty is a benign JSON API response of a real tool schema.
    seen: set[str] = set()
    for kind in ("dh", "ds"):
        for variant in ("enhanced", "base"):
            for case in json.loads(data[f"injecagent/test_cases_{kind}_{variant}"]):
                text = case["Tool Response"]
                if text not in seen:
                    seen.add(text)
                    out.add("injecagent", f"tool-response-{variant}", "attack", text)
                template = case["Tool Response Template"].replace("<Attacker Instruction>", "")
                if variant == "base" and template not in seen:
                    seen.add(template)
                    out.add("injecagent", "tool-response-template", "benign", template)

    # MCPTox: poisoned descriptions and the clean descriptions of the same servers (catalog ruleset)
    for entries in json.loads(data["mcptox/pure_tool"]):
        for entry in entries.values():
            out.add("mcptox", "poisoned-tool-description", "attack", entry["tool_content"].strip(), "description")
    for server in json.loads(data["mcptox/response_all"])["servers"].values():
        for block in re.split(r"\n\nTool: ", server["clean_system_promot"])[1:]:
            match = re.search(r"Description: (.*?)\nArguments:", block, re.S)
            if match:
                out.add("mcptox", "clean-tool-description", "benign", match.group(1).strip(), "description")

    # encoded and obfuscated variants of the same garak and multilingual seeds
    for name, transform in ENCODINGS.items():
        for v in injection:
            out.add("garak", f"encoded:{name}", "attack", transform(v))
        for v in multilingual[::10]:
            out.add("yanismiraoui", f"encoded:{name}", "attack", transform(v))
    # the same sentences planted inside ordinary content
    for v in injection:
        out.add("garak", "embedded-in-json", "attack", json.dumps({"id": 7, "title": "Quarterly notes", "description": v + " Thanks."}))
        out.add("garak", "embedded-in-log", "attack",
                "2026-10-15 09:12:03 INFO job finished\n2026-10-15 09:12:04 WARN " + v + "\n2026-10-15 09:12:05 INFO exit 0")

    # benign tool output
    for path in CPYTHON_CODE:
        text = data[f"cpython/{path}"].decode("utf-8", "replace")[:100_000]
        out.add("cpython", "code-file", "benign", text)
        for window in windows(text, 3000, 4):
            out.add("cpython", "code-snippet", "benign", window)
    for path in EXPRESS_CODE:
        out.add("express", "code-file", "benign", data[f"express/{path}"].decode("utf-8", "replace")[:100_000])
    for path in CPYTHON_DOCS:
        text = data[f"cpython/{path}"].decode("utf-8", "replace")[:100_000]
        out.add("cpython", "docs-page", "benign", text)
        for window in windows(text, 3000, 3):
            out.add("cpython", "docs-snippet", "benign", window)
    for path in EXPRESS_DOCS:
        out.add("express", "docs-page", "benign", data[f"express/{path}"].decode("utf-8", "replace")[:100_000])
    for name in LOGS:
        for chunk in lines_of(data[f"loghub/{name}"], 40, (3, 13, 23, 33, 43)):
            out.add("loghub", "log-lines", "benign", chunk)
    for path in POKE:
        out.add("pokeapi", "json-api-response", "benign", data[f"pokeapi/{path}"].decode("utf-8")[:100_000])
    for path in K8S_EN:
        text = data[f"k8s/{path}"].decode("utf-8")[:100_000]
        out.add("k8s", "docs-page", "benign", text)
        for window in windows(text, 3000, 3):
            out.add("k8s", "docs-snippet", "benign", window)
    for path in K8S_KO:
        text = data[f"k8s/{path}"].decode("utf-8")[:100_000]
        out.add("k8s", "docs-page-korean", "benign", text)
        for window in windows(text, 1500, 3):
            out.add("k8s", "docs-snippet-korean", "benign", window)
    # writing about prompt injection says the words honestly: the hardest benign stratum, reported apart
    for key, corpus in (("owasp/LLM01_PromptInjection", "owasp"), ("garak-repo/README", "garak-repo"), ("pyrit/README", "pyrit")):
        text = data[key].decode("utf-8")
        out.add(corpus, "security-writing-page", "benign", text[:100_000])
        for window in windows(text, 2000, 1):
            out.add(corpus, "security-writing-snippet", "benign", window)

    # file-format artifacts that real tool output carries: a byte-order mark in front of a file, and the zero-width
    # joiner inside emoji sequences. Derived from the real samples above and from Unicode's sequence list.
    for text in [s["text"] for s in out if s["stratum"] == "json-api-response"][:20]:
        out.add("pokeapi", "bom-prefixed-file", "benign", "﻿" + text)
    for text in [s["text"] for s in out if s["stratum"] == "log-lines"][:20]:
        out.add("loghub", "bom-prefixed-file", "benign", "﻿" + text)
    sequences = []
    for line in data["unicode/emoji-zwj-sequences-16.0"].decode("utf-8").splitlines():
        if line and not line.startswith("#"):
            sequences.append("".join(chr(int(code, 16)) for code in line.split(";")[0].split()))
    for index in range(0, 120, 3):
        out.add("unicode", "emoji-zwj-chat-message", "benign", "회의 끝났습니다 " + " ".join(sequences[index:index + 3]) + " 수고하셨습니다")

    if SYNTHETIC.exists():
        synthetic = json.loads(SYNTHETIC.read_text(encoding="utf-8"))
        for item in synthetic["attack"]:
            out.add("synthetic-ko", "korean-attack-" + item["kind"], "attack", item["text"])
        for item in synthetic["benign"]:
            language = "korean" if re.search("[가-힣]", item["text"]) else "english"
            out.add("synthetic-ko", f"{language}-business-{item['kind']}", "benign", item["text"])
    return out


# ── measurement ─────────────────────────────────────────────────────────────
def judge(samples: list[dict]) -> dict:
    sys.path.insert(0, str(HERE.parent / "gateway"))
    sys.path.insert(0, os.environ.get("MCPGW_APP", "/app"))
    from app import core, poisoning, textscan  # noqa: E402

    def result_hit(text: str) -> list[str]:
        try:
            core._guarded_result({"content": [{"type": "text", "text": text}]})
        except core.ResultRejected as exc:
            message = str(exc)
            return ["size"] if "상한" in message else [m.strip() for m in message.split(": ", 1)[-1].split(",")]
        return []

    paths = {"result": lambda s: result_hit(s["text"]),
             "argument": lambda s: ["content"] if core.untrusted_markers({"content": s["text"]}) else []}
    catalog = {"catalog": lambda s: poisoning.findings({"name": "tool", "description": s["text"]})}
    table: dict = {}
    for sample in samples:
        for name, decide in (catalog if sample["where"] == "description" else paths).items():
            started = time.perf_counter()
            hits = decide(sample)
            elapsed = time.perf_counter() - started
            cell = table.setdefault((name, sample["corpus"], sample["stratum"], sample["label"], sample["split"]),
                                    {"n": 0, "hit": 0, "ms": 0.0, "bytes": 0, "labels": {}, "attack_missed": [], "benign_flagged": []})
            cell["n"] += 1
            cell["ms"] += elapsed * 1000
            cell["bytes"] += len(sample["text"].encode())
            for label in hits:
                cell["labels"][label] = cell["labels"].get(label, 0) + 1
            cell["hit"] += bool(hits)
            bucket = "benign_flagged" if sample["label"] == "benign" and hits else \
                "attack_missed" if sample["label"] == "attack" and not hits else None
            if bucket and len(cell[bucket]) < 12:
                cell[bucket].append(sample["text"][:110])
    return {"table": table, "engine": "native" if textscan.mcpgw_textscan is not None else "python"}


def traversal_lines(data: dict[str, bytes]) -> list[str]:
    seen, lines = set(), []
    for path in PATHS:
        for line in data[f"payloadsallthethings/{path}"].decode("utf-8", "replace").splitlines():
            if line.strip() and line not in seen:
                seen.add(line)
                lines.append(line.strip())
    return lines


def gates(data: dict[str, bytes]) -> dict:
    """The input gates that come before the marker rules: size, schema, path handling."""
    sys.path.insert(0, str(HERE.parent / "gateway"))
    from jsonschema import Draft202012Validator
    from app import classify, core
    validator = Draft202012Validator({"type": "object", "properties": {"content": {"type": "string"}},
                                      "required": ["content"], "additionalProperties": False})
    limit = core.MAX_ARGUMENT_BYTES

    def gate(arguments: dict) -> str:
        try:
            size = len(json.dumps(arguments, ensure_ascii=False).encode())
        except UnicodeError:
            return "UnicodeError while serialising"
        if size > limit:
            return "P-INPUT-SCHEMA-001 (size)"
        return "passes" if validator.is_valid(arguments) else "P-INPUT-SCHEMA-001 (schema)"

    shapes = {
        "limit minus a little": {"content": "a" * (limit - 20)},
        "one byte over": {"content": "a" * (limit - 12)},
        "three-byte characters over": {"content": "한" * (limit // 3 + 10)},
        "integer for string": {"content": 7}, "list for string": {"content": ["a"]}, "null": {"content": None},
        "extra property": {"content": "a", "role": "admin"}, "proto key": {"content": "a", "__proto__": {"admin": True}},
        "missing content": {}, "nested object": {"content": {"a": {"b": "c"}}},
        "NUL byte in string": {"content": "a\x00b"}, "lone surrogate": {"content": "a\ud800b"},
    }
    classes: dict[str, int] = {}
    quiet = []
    for line in traversal_lines(data):
        resource = classify.path_resource(line, "/shared")
        classes[resource.data_class] = classes.get(resource.data_class, 0) + 1
        if resource.data_class != "important":
            quiet.append(line)
    return {"shapes": {name: gate(arguments) for name, arguments in shapes.items()},
            "traversal": {"lines": sum(classes.values()), "classes": classes, "not_graded_important": quiet[:10]}}


def summarise(result: dict) -> list[dict]:
    rows = []
    for (path, corpus, stratum, label, split), cell in sorted(result["table"].items()):
        rows.append({"path": path, "corpus": corpus, "stratum": stratum, "label": label, "split": split,
                     "n": cell["n"], "hit": cell["hit"], "ms_per_sample": round(cell["ms"] / cell["n"], 4),
                     "kib": round(cell["bytes"] / 1024, 1), "labels": cell["labels"],
                     "examples": cell["attack_missed"] if label == "attack" else cell["benign_flagged"]})
    return rows


EXCLUDED_ATTACK = ("toxicity", "tool-response-base", "encoded:")


def totals(rows: list[dict]) -> list[dict]:
    """Recall, precision and false-positive rate per path and split, over the strata the narrow rules claim to cover.
    Out of scope and reported apart: toxicity asks, tool responses that carry a bare imperative without override
    wording, encoded variants, and the security-writing pages."""
    out = []
    for path in sorted({r["path"] for r in rows}):
        for split in ("dev", "held-out", "all"):
            pick = lambda label, skip: [r for r in rows if r["path"] == path and r["label"] == label
                                        and split in (r["split"], "all") and not any(s in r["stratum"] for s in skip)]
            attack, benign = pick("attack", EXCLUDED_ATTACK), pick("benign", ("security-writing",))
            tp, fn = sum(r["hit"] for r in attack), sum(r["n"] - r["hit"] for r in attack)
            fp, tn = sum(r["hit"] for r in benign), sum(r["n"] - r["hit"] for r in benign)
            out.append({"path": path, "split": split, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
                        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
                        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
                        "fp_rate": round(fp / (fp + tn), 4) if fp + tn else None})
    return out


def report(rows: list[dict], total: list[dict], show: bool) -> None:
    print(f"{'path':9} {'corpus':13} {'stratum':44} {'label':6} {'split':8} {'n':>5} {'hit':>5} {'ms':>8}")
    for r in rows:
        print(f"{r['path']:9} {r['corpus']:13} {r['stratum'][:44]:44} {r['label']:6} {r['split']:8} {r['n']:5} {r['hit']:5} {r['ms_per_sample']:8.3f}")
        if show and r["split"] == "dev":
            for example in r["examples"][:4]:
                print("      ", "missed" if r["label"] == "attack" else "flagged", "|", example.replace("\n", " ")[:100])
    print("\nruleset totals")
    for t in total:
        print(t)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    b.add_argument("--update-manifest", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--samples", required=True)
    r.add_argument("--json")
    r.add_argument("--show-misses", action="store_true", help="list dev-split misses and flags; held-out stays counts only")
    r.add_argument("--gates", action="store_true", help="also run the size / schema / path gates (needs the cached sources)")
    args = parser.parse_args()
    if args.command == "build":
        samples = build(load_all(args.update_manifest))
        with open(args.out, "w", encoding="utf-8") as stream:
            for sample in samples:
                stream.write(json.dumps(sample, ensure_ascii=False) + "\n")
        counts: dict = {}
        for s in samples:
            key = (s["corpus"], s["stratum"], s["label"])
            counts[key] = counts.get(key, 0) + 1
        for key, n in sorted(counts.items()):
            print(n, *key)
        print("samples", len(samples), "dev", sum(s["split"] == "dev" for s in samples))
        return 0
    samples = [json.loads(line) for line in open(args.samples, encoding="utf-8")]
    result = judge(samples)
    rows, total = summarise(result), None
    total = totals(rows)
    print("engine:", result["engine"])
    report(rows, total, args.show_misses)
    output = {"engine": result["engine"], "rows": rows, "totals": total}
    if args.gates:
        output["gates"] = gates(load_all(False))
        print(json.dumps(output["gates"], ensure_ascii=False, indent=1))
    if args.json:
        Path(args.json).write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
