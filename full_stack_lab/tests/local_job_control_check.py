"""S4-07: a local job is bound to its own server's control, and a job refused before /start never ran.

10-25 field test: a registration elsewhere and an automatic approval renewal rewrote servers.json, the global
catalog hash in control_generation() moved, and every running local job on the PC was refused (409). The retry
of a write-classified tool was then held by P-RATE-003 although the refused job had never started.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import local_jobs, pac, registry

TOOLS = {"sequentialthinking": "w"}


def spec(**extra):
    return {"display_name": "think", "endpoint": "local://think", "intake_id": "i-1", "tools": TOOLS,
            "tool_reviews": {"sequentialthinking": {"reviewed_at": "2026-10-25T00:00:00+00:00"}},
            "valid_until": "2026-10-26T00:00:00+00:00", "allowed_principals": ["*"], **extra}


class LocalJobControl(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "catalog.toml").write_text("[servers]\n", encoding="utf-8")
        (self.root / "capabilities.json").write_text("{}", encoding="utf-8")
        for name, path in (("REGISTRY_DIR", self.root), ("CATALOG_PATH", self.root / "catalog.toml"),
                           ("RUNTIME_PATH", self.root / "servers.json")):
            patcher = patch.object(registry, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        pac._capabilities.update(key=None, document=None)
        registry._cache.update(mtime=None, catalog=None, runtime=None)

    def save(self, servers, history=()):
        (self.root / "servers.json").write_text(json.dumps({"servers": servers, "history": list(history)}), encoding="utf-8")

    def generation(self):
        return local_jobs.control_generation("think")

    def test_registration_and_renewal_elsewhere_keep_the_job(self):
        self.save({"think": spec()})
        before = self.generation()
        self.save({"think": spec(), "docs": {**spec(display_name="docs"), "intake_id": "i-2"}},
                  [{"type": "server-register", "server_id": "docs"}])
        self.assertEqual(self.generation(), before)
        self.save({"think": spec(valid_until="2026-10-27T00:00:00+00:00", approval_days=1)},
                  [{"type": "approval-renewed", "server_id": "think"}])
        self.assertEqual(self.generation(), before)

    def test_this_servers_scope_or_reviewed_catalog_change_stops_the_job(self):
        self.save({"think": spec()})
        before = self.generation()
        self.save({"think": spec(tools={"sequentialthinking": "x"})})
        self.assertNotEqual(self.generation(), before)
        self.save({"think": spec()})
        (self.root / "catalog.toml").write_text("[servers]\n# reviewed change\n", encoding="utf-8")
        self.assertNotEqual(self.generation(), before)

    def test_job_refused_before_start_is_not_an_attempt(self):
        row = {"id": "j", "request_id": "r", "device_id": "d", "server_id": "think", "method": "tools/call",
               "manifest_sha256": "m", "claimed_at": "t1", "started_at": None, "finished_at": "t2", "stopped_at": "t2",
               "state": "done", "result_sha256": None}
        event = {"upstream_attempted": True}
        local_jobs.remember(row, event)
        self.assertFalse(event["upstream_attempted"])
        local_jobs.remember({**row, "started_at": "t1.5"}, event)
        self.assertTrue(event["upstream_attempted"])


if __name__ == "__main__":
    unittest.main()
