"""Runtime worker (DEV-38): recipes, container hardening flags and the egress allowlist, without a container engine."""
import re
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "runtime"), str(ROOT / "gateway" / "app")]
import worker  # noqa: E402

RUNTIME = {"id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
           "intake_id": uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"), "generation": 2}


class Recipes(unittest.TestCase):
    def test_shipped_recipe_is_pinned_and_hashed(self):
        recipes = worker.load_recipes(ROOT / "runtime" / "recipes")
        recipe = recipes["https://github.com/microsoft/markitdown"]
        self.assertEqual(recipe["id"], "markitdown-mcp")
        self.assertIn("@sha256:", recipe["base_image"])
        self.assertRegex(recipe["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(recipe["sha256"], worker.load_recipes(ROOT / "runtime" / "recipes")[recipe["repository"]]["sha256"])

    def test_unpinned_base_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "x.toml").write_text('[recipe]\nid="x"\nrepository="r"\ndockerfile="x.Dockerfile"\nport=1\npath="/mcp"\nargs=[]\n')
            Path(folder, "x.Dockerfile").write_text("FROM python:3.13-slim\n")
            with self.assertRaises(ValueError):
                worker.load_recipes(Path(folder))


class Containers(unittest.TestCase):
    def test_alias_follows_the_approval_and_names_follow_the_run(self):
        other = {**RUNTIME, "id": uuid.uuid4(), "generation": 3}
        self.assertEqual(worker.names(RUNTIME)["alias"], worker.names(other)["alias"])
        self.assertNotEqual(worker.names(RUNTIME)["container"], worker.names(other)["container"])
        recipe = {"port": 3001, "path": "/mcp"}
        self.assertEqual(worker.endpoint(recipe, RUNTIME), "http://mcpgw-mcp-aaaaaaaa:3001/mcp")
        self.assertNotIn(".", worker.names(RUNTIME)["alias"], "the gateway treats dotless hosts as internal")

    def test_mcp_container_is_confined(self):
        recipe = {"args": ["--http"], "user": "65534:65534"}
        args = worker.mcp_run_args(recipe, RUNTIME, "sha256:" + "0" * 64)
        joined = " ".join(args)
        for flag in ("--read-only", "--cap-drop ALL", "--security-opt no-new-privileges", "--user 65534:65534",
                     "--pids-limit", "--memory", f"--network {worker.names(RUNTIME)['network']}",
                     f"HTTPS_PROXY=http://{worker.names(RUNTIME)['egress']}:3128"):
            self.assertIn(flag, joined)
        self.assertFalse({"-p", "--publish", "--privileged", "-v", "--volume"} & set(args))
        self.assertEqual(args[-2:], ["sha256:" + "0" * 64, "--http"], "runs the exact image it built")


class FakeConnection:
    def __init__(self, row):
        self.row = row

    def execute(self, *_):
        return self

    def fetchone(self):
        return self.row


class Approval(unittest.TestCase):
    def test_every_reason_to_stop_a_build(self):
        recipes = worker.load_recipes(ROOT / "runtime" / "recipes")
        recipe = recipes["https://github.com/microsoft/markitdown"]
        job = {**RUNTIME, "source_commit": "c" * 40, "recipe_id": recipe["id"], "recipe_sha256": recipe["sha256"]}
        ok = {"status": "APPROVED", "intake_kind": "repository", "commit_sha": "c" * 40,
              "repository_url": recipe["repository"], "lifecycle": "OPERATING", "server_status": "READY"}
        self.assertIsNone(worker.approval_problem(FakeConnection(ok), job, recipes))
        for change in ({"status": "HOLD"}, {"commit_sha": "d" * 40}, {"lifecycle": "TERMINATING"},
                       {"server_status": "DISABLED"}, {"intake_kind": "remote-endpoint"}):
            self.assertTrue(worker.approval_problem(FakeConnection({**ok, **change}), job, recipes), change)
        self.assertTrue(worker.approval_problem(FakeConnection(None), job, recipes))
        moved = {**job, "recipe_sha256": "0" * 64}
        self.assertTrue(worker.approval_problem(FakeConnection(ok), moved, recipes), "a build follows the queued recipe")
        self.assertIsNone(worker.approval_problem(FakeConnection(ok), moved, recipes, recipe_fixed=False),
                          "a running image is not stopped because the recipe file changed")


class Egress(unittest.TestCase):
    def test_no_destination_lets_nothing_out(self):
        allow = worker.egress_filter([])
        self.assertEqual(allow, "^$")
        self.assertFalse(re.search(allow, "example.com"))

    def test_only_reviewed_hosts_exactly(self):
        allow = worker.egress_filter(["learn.microsoft.com", "raw.githubusercontent.com", "evil host", "x", "../etc"])
        patterns = allow.splitlines()
        self.assertEqual(patterns, [r"^learn\.microsoft\.com$", r"^raw\.githubusercontent\.com$"])
        matches = lambda host: any(re.search(p, host) for p in patterns)  # noqa: E731
        self.assertTrue(matches("learn.microsoft.com"))
        for host in ("learnxmicrosoft.com", "learn.microsoft.com.evil.net", "a.learn.microsoft.com", "169.254.169.254"):
            self.assertFalse(matches(host), host)
        self.assertIn("--label", worker.egress_run_args(RUNTIME, allow))


if __name__ == "__main__":
    unittest.main()
