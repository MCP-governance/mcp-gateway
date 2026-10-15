"""Offline regression for managed heartbeat checks; no OS rules are changed."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "endpoint-agent" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManagedChecks(unittest.TestCase):
    def setUp(self):
        self.windows = load("managed-windows")
        self.linux = load("managed-linux")
        self.temporary = tempfile.TemporaryDirectory(prefix="mcpgw-heartbeat-check-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.target = self.folder / "managed-settings.json"
        self.target.write_text("{}")
        self.config = {"username": "unit", "uid": 1234, "sid": "S-1-5-21-1-2-3-1234", "profile": str(self.folder),
                       "firewall_baseline": str(self.folder / "firewall.json"), "nft_baseline": str(self.folder / "nft.json")}
        self.good_rules = {"profiles": [True, True, True], "rules": [
            {"Name": "MCPGW-unit-" + name, "Enabled": "True", "Direction": "Outbound", "Action": "Block",
             "Profile": "Any", "LocalUser": "D:(A;;CC;;;" + self.config["sid"] + ")"}
            for name in self.windows.RULES]}

    def windows_health(self, state, baseline=None):
        Path(self.config["firewall_baseline"]).write_text(json.dumps(baseline or state))
        account = {"sid": self.config["sid"], "profile": self.config["profile"], "admin": False}
        with mock.patch.object(self.windows, "FILES", {"managed-settings.json": self.target}), \
             mock.patch.object(self.windows, "protected", return_value=True), \
             mock.patch.object(self.windows, "account", return_value=account), \
             mock.patch.object(self.windows, "rule_state", return_value=state):
            return self.windows.checks(self.config, {})[1]["firewall_enforcing"]

    def test_windows_healthy(self):
        self.assertTrue(self.windows_health(self.good_rules))

    def test_windows_empty_profiles_fail_closed(self):
        state = copy.deepcopy(self.good_rules)
        state["profiles"] = []
        self.assertFalse(self.windows_health(state))

    def test_windows_unknown_profile_values_fail_closed(self):
        state = copy.deepcopy(self.good_rules)
        state["profiles"] = ["True"] * 3
        self.assertFalse(self.windows_health(state))

    def test_windows_missing_rules_even_in_baseline_fail_closed(self):
        state = copy.deepcopy(self.good_rules)
        state["rules"] = []
        self.assertFalse(self.windows_health(state))

    def test_windows_disabled_rule_even_in_baseline_fail_closed(self):
        state = copy.deepcopy(self.good_rules)
        state["rules"][0]["Enabled"] = "False"
        self.assertFalse(self.windows_health(state))

    def test_windows_foreign_account_rule_fail_closed(self):
        state = copy.deepcopy(self.good_rules)
        state["rules"][0]["LocalUser"] = "D:(A;;CC;;;S-1-5-18)"
        self.assertFalse(self.windows_health(state))

    def linux_health(self, profiles):
        Path(self.config["nft_baseline"]).write_text("{}")
        read_text = Path.read_text

        def text(path, *args, **kwargs):
            return profiles if str(path) == "/sys/kernel/security/apparmor/profiles" else read_text(path, *args, **kwargs)

        person = SimpleNamespace(pw_name="unit", pw_uid=1234, pw_gid=1234,
                                 pw_shell="/usr/local/lib/mcpgw-enforcement/mcpgw-unit/login-shell")
        result = SimpleNamespace(returncode=0, stdout="{}")
        with mock.patch.object(self.linux, "FILES", {"managed-settings.json": self.target}), \
             mock.patch.object(self.linux, "protected", return_value=True), \
             mock.patch.object(self.linux.pwd, "getpwnam", return_value=person), \
             mock.patch.object(self.linux.os, "getgrouplist", return_value=[]), \
             mock.patch.object(self.linux.subprocess, "run", return_value=result), \
             mock.patch.object(Path, "read_text", text):
            self.target.chmod(0o644)
            return self.linux.checks(self.config, {})[1]["apparmor_enforcing"]

    def test_linux_exact_enforcing_profiles(self):
        profiles = "\n".join("mcpgw-unit" + suffix + " (enforce)" for suffix in ("", "-codex", "-claude", "-credential"))
        self.assertTrue(self.linux_health(profiles))

    def test_linux_different_profiles_cannot_impersonate_account(self):
        profiles = "\n".join("other-mcpgw-unit" + suffix + " (enforce)" for suffix in ("", "-codex", "-claude", "-credential"))
        self.assertFalse(self.linux_health(profiles))

    def test_linux_complain_profile_fails_closed(self):
        profiles = "\n".join("mcpgw-unit" + suffix + " (enforce)" for suffix in ("", "-codex", "-claude", "-credential"))
        self.assertFalse(self.linux_health(profiles.replace("mcpgw-unit-codex (enforce)", "mcpgw-unit-codex (complain)")))


class StaleSignIn(unittest.TestCase):
    """A reinstall clears the harness's needs-sign-in marks without following links."""

    def test_mark_removed_and_links_not_followed(self):
        linux = load("managed-linux")
        with tempfile.TemporaryDirectory(prefix="mcpgw-signin-") as raw:
            home = Path(raw) / "home"
            (home / ".claude").mkdir(parents=True)
            mark = home / ".claude" / "mcp-needs-auth-cache.json"
            mark.write_text("{}")
            linux.forget_stale_sign_in(str(home))
            self.assertFalse(mark.exists())
            linux.forget_stale_sign_in(str(home))  # already gone: nothing to do
            outside = Path(raw) / "outside"
            outside.mkdir()
            (outside / "mcp-needs-auth-cache.json").write_text("keep")
            other = Path(raw) / "other"
            other.mkdir()
            try:
                (other / ".claude").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symbolic links are not available here")
            with self.assertRaises(OSError):
                linux.forget_stale_sign_in(str(other))
            self.assertTrue((outside / "mcp-needs-auth-cache.json").exists())
            # A link higher up the home path is not followed either.
            (outside / ".claude").mkdir()
            (outside / ".claude" / "mcp-needs-auth-cache.json").write_text("keep")
            (Path(raw) / "parent").symlink_to(Path(raw), target_is_directory=True)
            with self.assertRaises(OSError):
                linux.forget_stale_sign_in(str(Path(raw) / "parent" / "outside"))
            self.assertTrue((outside / ".claude" / "mcp-needs-auth-cache.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
