"""The intake worker's evidence with the real scanners (Syft, Trivy, Semgrep, Gitleaks) on a synthetic checkout.

Run ONLY in the intake-worker image of a disposable lab, with no network, a copy of the Trivy cache
(TRIVY_CACHE_DIR) and this repository's supply_chain/ mounted at /app. The clone step is replaced by a
synthetic source tree (the real clone needs GitHub); everything after it is the worker's own code and the
real scanner binaries. Trivy runs with its database update skipped so the cached database is what is read.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, "/app")
import intake_worker as worker
from provenance import tree_digest

MIT = """MIT License

Copyright (c) 2026 Example Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
CLEAN = {"LICENSE": MIT, "README.md": "# notes server\n", "server.py": "print('serve')\n",
         "requirements.txt": "requests==2.19.0\nflask==0.12\n"}
CRITICAL = {**CLEAN, "requirements.txt": "PyYAML==5.3\nDjango==1.11.0\n"}
COMMIT = "c" * 40


class Connection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, args=None):
        self.calls.append((sql, args))

    def commit(self):
        pass


def scan(files: dict[str, str]) -> list:
    request_id = uuid4()
    connection = Connection()
    real_run = worker.run

    def run(command, timeout, cwd=None, extra_env=None):
        return real_run(command, timeout, cwd, {"TRIVY_SKIP_DB_UPDATE": "true", "TRIVY_SKIP_CHECK_UPDATE": "true", **(extra_env or {})})

    def clone(url, checkout):
        checkout.mkdir(parents=True)
        for name, text in files.items():
            (checkout / name).write_text(text)
        return COMMIT

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        worker.WORK_DIR, worker.REPORT_DIR = root / "work", root / "reports"
        worker.REPORT_DIR.mkdir()
        worker.clone, worker.run = clone, run
        worker.validate(connection, {"id": request_id, "repository_url": "https://github.com/example/notes", "display_name": "Notes", "requested_transport": "stdio"})
    return connection.calls


def main() -> int:
    metadata = json.loads((Path(os.environ["TRIVY_CACHE_DIR"]) / "db" / "metadata.json").read_text())
    with tempfile.TemporaryDirectory() as twin:
        for name, text in CLEAN.items():
            (Path(twin) / name).write_text(text)
        expected = tree_digest(Path(twin))

    calls = scan(CLEAN)
    provenance = [args for sql, args in calls if "SET provenance=%s" in sql][-1][0].obj
    assert provenance["kind"] == "source" and provenance["version"] == COMMIT and provenance["source_url"] == "https://github.com/example/notes", provenance
    assert provenance["artifact"]["sha256"] == expected["sha256"] and provenance["artifact"]["files"] == len(CLEAN), (provenance, expected)
    assert provenance["license"]["spdx"] == "MIT" and provenance["license"]["files"] == ["LICENSE"] and provenance["license"]["source"] == "trivy", provenance["license"]
    print("PASS real scanners: source, pinned commit, artifact digest and MIT licence recorded:", provenance["artifact"]["sha256"][:16], provenance["license"])

    stored = {args[0]: args for sql, args in calls if "INSERT INTO supply_chain_reports" in sql}
    assert set(stored) == {"Syft", "Trivy", "Semgrep", "Gitleaks"}, set(stored)
    versions = {name: args[1] for name, args in stored.items()}
    assert all(versions.values()), versions
    database = stored["Trivy"][-2]
    assert database == datetime.fromisoformat(metadata["UpdatedAt"]).astimezone(UTC), (database, metadata)
    assert all(stored[name][-2] is None for name in ("Syft", "Semgrep", "Gitleaks"))
    age = (datetime.now(UTC) - database).days
    print(f"PASS scanner versions {versions}; Trivy database built {database.isoformat()} ({age} days old; the gate's limit is 7)")

    counts = stored["Trivy"][5:8]
    final = [args for sql, args in calls if "SET status=%s" in sql][-1]
    assert counts[0] == 0 and final[0] in {"VALIDATED"}, (final[:2], counts)
    print("PASS no critical finding validates the request:", final[0], final[1], "critical/high/medium =", counts)

    calls = scan(CRITICAL)
    stored = {args[0]: args for sql, args in calls if "INSERT INTO supply_chain_reports" in sql}
    counts = stored["Trivy"][5:8]
    summary = stored["Trivy"][-1].obj
    final = [args for sql, args in calls if "SET status=%s" in sql][-1]
    ids = sorted({f["id"] for f in summary["findings"] if f["severity"] == "CRITICAL"})
    assert counts[0] > 0 and ids and final[0] == "HOLD" and final[1] == "CRITICAL", (final[:2], counts, ids)
    print("PASS a real critical finding holds the request:", final[0], final[1], "critical =", counts[0], ids[:3])
    return 0


if __name__ == "__main__":
    sys.exit(main())
