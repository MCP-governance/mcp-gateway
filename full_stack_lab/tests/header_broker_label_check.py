"""D-183 local policy/handler tests. No kernel or actual MCP execution evidence."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import socket
import socketserver
import struct
import threading
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / "endpoint-agent" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BINDING = load("broker_binding")
tree = ast.parse((ROOT / "endpoint-agent/enforce-linux.py").read_text(encoding="utf-8"))
namespace = {"Path": Path, "BASE": PurePosixPath("/usr/local/lib/mcpgw-enforcement")}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"profile", "bound_profile"}
         or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets)]
exec(compile(ast.Module(body=nodes, type_ignores=[]), "enforce-linux.py", "exec"), namespace)
ENFORCER = SimpleNamespace(**namespace)
CONFIG = {"username": "unit", "uid": 1234, "broker_binding": "enforce"}


class Peer:
    def __init__(self, label=b"mcpgw-unit-bound-codex (enforce)", uid=1234):
        self.label, self.uid, self.answer = label, uid, None

    def getsockopt(self, level, option, size):
        if option == getattr(socket, "SO_PEERCRED", 17):
            return struct.pack("3i", 456, self.uid, self.uid)
        if isinstance(self.label, Exception):
            raise self.label
        return self.label

    def sendall(self, data):
        self.answer = json.loads(data)


class HeaderBrokerLabel(unittest.TestCase):
    def setUp(self):
        source = (ROOT / "endpoint-agent/managed-linux.py").read_text(encoding="utf-8")
        serve = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "serve")
        handler = next(n for n in serve.body if isinstance(n, ast.ClassDef) and n.name == "Header")
        self.namespace = {"binding": BINDING, "socketserver": socketserver, "json": json,
                          "config": dict(CONFIG), "cache": {"token": "synthetic-secret", "until": 200},
                          "time": SimpleNamespace(monotonic=lambda: 100), "lock": threading.Lock()}
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "Header", "exec"), self.namespace)
        self.output = io.StringIO()
        self.addCleanup(patch.stopall)
        patch.object(socket, "SO_PEERCRED", 17, create=True).start()

    def handle(self, peer, kernel=""):
        with patch.object(BINDING, "kernel_ready", return_value=kernel), contextlib.redirect_stdout(self.output):
            self.namespace["Header"](peer, None, None)
        return peer.answer

    def test_pc_with_one_harness_needs_only_its_profiles(self):
        only = BINDING.enforcing_profiles("u", ("codex",))
        self.assertIn("mcpgw-u-bound-codex", only)
        self.assertFalse(any("claude" in p for p in only))
        self.assertEqual(BINDING.enforcing_profiles("u"), BINDING.enforcing_profiles("u", ("codex", "claude")))
        self.assertEqual(len(BINDING.enforcing_profiles("u")), 8)

    def test_exact_approved_labels_receive_active_token(self):
        for label in ("codex", "claude", "credential"):
            for mode in ("", " (enforce)"):
                with self.subTest(label=label, mode=mode):
                    self.assertEqual(self.handle(Peer(("mcpgw-unit-bound-" + label + mode).encode())),
                                     {"Authorization": "Bearer synthetic-secret"})

    def test_mismatch_complain_stack_prefix_and_other_user_denied(self):
        for label in ("unconfined", "mcpgw-unit-credential", "mcpgw-unit-bound-codex-tool",
                      "mcpgw-unit-bound-codex-extra", "mcpgw-unit-bound-codex (complain)",
                      "mcpgw-unit-bound-codex//child", "mcpgw-unit-bound-codex//&other"):
            with self.subTest(label=label):
                self.assertIn("error", self.handle(Peer(label.encode())))

    def test_uid_mismatch_is_denied_even_in_warning_mode(self):
        self.namespace["config"]["broker_binding"] = "warn"
        self.assertIn("error", self.handle(Peer(uid=9999)))

    def test_label_read_failure_unsupported_and_malformed_denied(self):
        for label in (OSError("not supported"), b"\xff", b"", b"mcpgw-unit-bound-codex\0junk"):
            with self.subTest(label=label):
                self.assertIn("error", self.handle(Peer(label)))

    def test_kernel_failures_deny_cached_token(self):
        for reason in ("apparmor-unavailable", "profiles-not-enforcing", "kernel-state-unreadable",
                       "unix-mediation-unavailable", "ptrace-mediation-unavailable"):
            with self.subTest(reason=reason):
                self.assertIn("error", self.handle(Peer(), kernel=reason))

    def test_warning_allows_and_records_failures_without_token_in_log(self):
        self.namespace["config"]["broker_binding"] = "warn"
        for peer, kernel in ((Peer(b"unconfined"), ""), (Peer(OSError("missing")), ""),
                             (Peer(), "apparmor-unavailable")):
            self.assertIn("Authorization", self.handle(peer, kernel))
        records = [json.loads(line) for line in self.output.getvalue().splitlines()]
        self.assertTrue(all(record["result"] == "warn" for record in records))
        self.assertNotIn("synthetic-secret", self.output.getvalue())

    def test_missing_mode_is_legacy_warning_invalid_mode_denies(self):
        self.namespace["config"].pop("broker_binding")
        self.assertIn("Authorization", self.handle(Peer(b"unconfined")))
        for mode in ("", "ENFORCE", None, "off"):
            self.namespace["config"]["broker_binding"] = mode
            self.assertIn("error", self.handle(Peer()))

    def test_expired_and_empty_cache_never_return_token(self):
        self.namespace["cache"]["until"] = 100
        self.assertIn("error", self.handle(Peer()))
        self.namespace["cache"].clear()
        self.assertIn("error", self.handle(Peer()))

    def test_credentials_failure_cannot_be_warning_allow(self):
        self.namespace["config"]["broker_binding"] = "warn"
        peer = Peer()
        peer.getsockopt = Mock(side_effect=OSError("closed"))
        self.assertIn("error", self.handle(peer))

    def test_so_peersec_is_used_without_proc_pid_lookup(self):
        peer = Peer()
        with patch.object(Path, "read_text", side_effect=AssertionError("no proc fallback")):
            self.assertEqual(BINDING.peer_label(peer), "mcpgw-unit-bound-codex")


class KernelReadiness(unittest.TestCase):
    def setUp(self):
        self.files = {
            "/sys/module/apparmor/parameters/enabled": "Y\n",
            "/sys/kernel/security/apparmor/profiles": "\n".join(
                p + " (enforce)" for p in BINDING.enforcing_profiles("unit")),
            "/sys/kernel/security/apparmor/features/network/af_unix": "yes\n",
            "/sys/kernel/security/apparmor/features/ptrace/mask": "read trace\n"}

    def status(self):
        def read(path, *args, **kwargs):
            value = self.files[path.as_posix()]
            if isinstance(value, Exception):
                raise value
            return value
        with patch.object(Path, "read_text", read):
            return BINDING.kernel_ready("unit")

    def test_loaded_enforcing_complete_policy(self):
        self.assertEqual(self.status(), "")

    def test_disabled_unreadable_and_removed_profile(self):
        for path, value, reason in (
            ("/sys/module/apparmor/parameters/enabled", "N", "apparmor-unavailable"),
            ("/sys/kernel/security/apparmor/profiles", OSError("denied"), "kernel-state-unreadable"),
            ("/sys/kernel/security/apparmor/profiles", "", "profiles-not-enforcing"),
            ("/sys/kernel/security/apparmor/features/network/af_unix", "no", "unix-mediation-unavailable"),
            ("/sys/kernel/security/apparmor/features/ptrace/mask", "trace", "ptrace-mediation-unavailable")):
            before = self.files[path]
            self.files[path] = value
            with self.subTest(path=path, value=value):
                self.assertEqual(self.status(), reason)
            self.files[path] = before

    def test_complain_instead_of_enforce_fails(self):
        path = "/sys/kernel/security/apparmor/profiles"
        self.files[path] = self.files[path].replace("-bound-codex (enforce)", "-bound-codex (complain)")
        self.assertEqual(self.status(), "profiles-not-enforcing")


class BoundProfiles(unittest.TestCase):
    def setUp(self):
        self.text = ENFORCER.profile("mcpgw-unit", PurePosixPath("/fixed/login-shell"), "/home/unit",
            {"codex": PurePosixPath("/opt/approved/codex"), "claude": PurePosixPath("/opt/approved/claude")}, True, True,
            {"codex": [PurePosixPath("/opt/approved/codex-code-mode-host")]}, "enforce")
        self.blocks = {part.split(" {", 1)[0].split(" ", 1)[0]: part.split(" {", 1)[1]
                       for part in self.text.split("profile ")[1:]}

    def test_every_shell_and_companion_leaves_harness(self):
        for key in ("codex", "claude"):
            harness = self.blocks["mcpgw-unit-bound-" + key]
            self.assertIn("{bash,dash,sh,", harness)
            self.assertIn("} px -> mcpgw-unit-bound-" + key + "-tool,", harness)
            self.assertNotIn(" ix,", harness)
        self.assertIn("/opt/approved/codex-code-mode-host mrpx -> mcpgw-unit-bound-codex-tool,", self.text)

    def test_only_harness_can_delegate_to_fixed_helper(self):
        for key in ("codex", "claude"):
            harness = self.blocks["mcpgw-unit-bound-" + key]
            tool = self.blocks["mcpgw-unit-bound-" + key + "-tool"]
            self.assertIn("header-helper px -> mcpgw-unit-bound-credential,", harness)
            self.assertIn("deny /usr/local/lib/mcpgw-enforcement/mcpgw-unit/header-helper x,", tool)
            self.assertNotIn("header-helper px", tool)
            self.assertIn("deny /run/mcpgw-unit.sock rw,", tool)
        self.assertIn('peer=(addr="/run/mcpgw-unit.sock", label=unconfined)', self.text)
        self.assertNotIn("network unix stream", self.text)
        self.assertNotIn("change_profile", self.text)

    def test_memory_access_denied_in_every_profile(self):
        for name, block in self.blocks.items():
            with self.subTest(name=name):
                self.assertIn("deny ptrace (trace, read, tracedby, readby),", block)
                self.assertIn("deny /proc/*/{mem,environ} r,", block)
                self.assertIn("deny capability sys_ptrace,", block)

    def test_default_warning_keeps_legacy_helper_path_and_shell_policy(self):
        args = ("mcpgw-unit", Path("/fixed/login-shell"), "/home/unit",
                {"codex": Path("/opt/approved/codex")}, True, True)
        self.assertEqual(ENFORCER.profile(*args), ENFORCER.profile(*args, binding_mode="warn"))
        self.assertIn("header-helper px -> mcpgw-unit-credential,", ENFORCER.profile(*args))
        self.assertNotIn("-bound-", ENFORCER.profile(*args))

    def test_nonmanaged_kit_cannot_claim_enforcement(self):
        with self.assertRaises(ValueError):
            ENFORCER.profile("mcpgw-unit", PurePosixPath("/fixed/login-shell"), "/home/unit",
                             {"codex": PurePosixPath("/opt/approved/codex")}, True, binding_mode="enforce")


class Integration(unittest.TestCase):
    def test_linux_download_contains_broker_module_and_installer_copies_it(self):
        source = (ROOT / "full_stack_lab/gateway/app/agent_service.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        files = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "KIT_FILES" for t in n.targets))
        self.assertIn("broker_binding.py", files["linux"])
        self.assertTrue(all((ROOT / "endpoint-agent" / name).is_file() for name in files["linux"]))
        tree = ast.parse((ROOT / "endpoint-agent/managed-linux.py").read_text(encoding="utf-8"))
        install = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "install")
        self.assertTrue(any(isinstance(n, ast.Tuple) and any(isinstance(e, ast.Constant)
                            and e.value == "broker_binding.py" for e in n.elts) for n in ast.walk(install)))

    def test_extracted_checks_need_no_new_namespace_and_follow_stage(self):
        source = (ROOT / "endpoint-agent/managed-linux.py").read_text(encoding="utf-8")
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "checks")
        person = SimpleNamespace(pw_name="unit", pw_uid=1234, pw_gid=1234,
            pw_shell="/usr/local/lib/mcpgw-enforcement/mcpgw-unit/login-shell")
        namespace = {"Path": PurePosixPath, "hashlib": hashlib, "json": json, "FILES": {}, "PRIVILEGED": set(),
                     "pwd": SimpleNamespace(getpwnam=lambda _: person), "os": SimpleNamespace(getgrouplist=lambda *a: []),
                     "subprocess": SimpleNamespace(run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}")),
                     "load_module": lambda *a: SimpleNamespace(user_command_settings=lambda _: (True, [])),
                     "__file__": str(ROOT / "endpoint-agent/managed-linux.py")}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "checks", "exec"), namespace)
        config = {**CONFIG, "nft_baseline": "/baseline"}
        profiles = "\n".join(p + " (enforce)" for p in BINDING.enforcing_profiles("unit"))
        # Path replacement supplies only the pre-existing checks dependencies.
        class ReadPath(PurePosixPath):
            def read_text(self):
                return profiles if str(self).endswith("/profiles") else "{}"
        namespace["Path"] = ReadPath
        self.assertTrue(namespace["checks"](config, {})[1]["apparmor_enforcing"])
        profiles = profiles.replace("-bound-codex-tool (enforce)", "-bound-codex-tool (complain)")
        self.assertFalse(namespace["checks"](config, {})[1]["apparmor_enforcing"])
        config.pop("broker_binding")
        profiles = "\n".join("mcpgw-unit" + s + " (enforce)" for s in ("", "-codex", "-claude", "-credential"))
        self.assertTrue(namespace["checks"](config, {})[1]["apparmor_enforcing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
