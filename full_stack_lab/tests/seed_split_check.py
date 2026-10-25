"""Lab accounts live in db/seed-lab.sql, loaded by the lab compose only; the release bundle starts without them.

The schema file used to insert seven named demo accounts, and deploy/compose.yaml loads that schema, so a customer
database began with them.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
INITDB = re.compile(r"^\s*-\s*(\S+):/docker-entrypoint-initdb\.d/(\S+?)(?::ro)?\s*$", re.M)


def initdb(compose: Path) -> dict[str, str]:
    return {target: Path(source).name for source, target in INITDB.findall(compose.read_text(encoding="utf-8"))}


class SeedSplit(unittest.TestCase):
    def test_schema_has_no_accounts_and_the_lab_seed_has_them(self):
        self.assertNotRegex((LAB / "db" / "init.sql").read_text(encoding="utf-8"), r"(?i)INSERT\s+INTO\s+principals")
        self.assertRegex((LAB / "db" / "seed-lab.sql").read_text(encoding="utf-8"), r"(?i)INSERT\s+INTO\s+principals")

    def test_lab_compose_loads_the_seed_after_the_schema(self):
        mounts = initdb(LAB / "compose.yaml")
        self.assertEqual(mounts.get("001-init.sql"), "init.sql")
        self.assertEqual(mounts.get("003-seed-lab.sql"), "seed-lab.sql")

    def test_release_bundle_loads_the_schema_but_never_the_seed(self):
        mounts = initdb(REPO / "deploy" / "compose.yaml")
        self.assertEqual(mounts.get("001-init.sql"), "init.sql")
        self.assertNotIn("seed-lab.sql", mounts.values())


if __name__ == "__main__":
    unittest.main()
