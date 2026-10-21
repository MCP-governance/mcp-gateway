"""Record public upstream identity and selected symbols without vendoring source."""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
COMMIT = "064c6b8c737f5b41d171fdda80bd9ef10ad06eb3"


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def main():
    records = []
    for path in ("codex-rs/rmcp-client/src/http_headers.rs", "LICENSE"):
        url = f"https://raw.githubusercontent.com/openai/codex/{COMMIT}/{path}"
        raw = fetch(url)
        lines = raw.decode("utf-8").splitlines()
        records.append({"url": url, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                        "anchors": [{"line": i, "text": line.strip()} for i, line in enumerate(lines, 1)
                                    if any(s in line for s in ('async fn run_helper(', 'let shell = "sh"',
                                        'Command::new(shell)', 'process.args(["-c", command])', 'Apache License', 'Version 2.0'))]})
    for repo in ("openai/codex", "openai/skills", "roddhjav/apparmor.d"):
        meta = json.loads(fetch("https://api.github.com/repos/" + repo))
        head = json.loads(fetch(f'https://api.github.com/repos/{repo}/commits/{meta["default_branch"]}'))
        records.append({"repo": repo, "head_commit": head["sha"], "pushed_at": meta["pushed_at"],
                        "archived": meta["archived"], "license": meta["license"],
                        "use": "Codex fixed release source inspection" if repo.endswith("codex") else
                        "discovery only; no skill/profile installed or copied"})
    tag = json.loads(fetch("https://api.github.com/repos/openai/codex/git/tags/54e1bd264b4122fe9471ee7d54c4d021a76bb8ff"))
    if tag["object"]["sha"] != COMMIT:
        raise ValueError("release tag commit mismatch")
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "release": "rust-v0.158.0",
              "commit": COMMIT, "tag_object": tag["sha"], "records": records,
              "limits": "source inspection only; not installed harness execution or upstream direct-exec support"}
    (HERE / "sources.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Recorded pinned Codex helper source, license, tag and three repository metadata records")


if __name__ == "__main__":
    main()
