"""DEV-73 (D-175) manifest rules, signature and the runner's container command. No engine, no network."""
import base64
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import pwd
except ImportError:  # Windows still runs the platform-independent manifest checks.
    pwd = None

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "full_stack_lab" / "gateway"))
from app import local_jobs  # noqa: E402

spec = importlib.util.spec_from_file_location("local_runner", ROOT / "endpoint-agent" / "local-runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

IMAGE = "docker.io/mcp/filesystem@sha256:" + "b" * 64


def manifest(**change):
    base = {"server_id": "fs-local", "image": IMAGE, "command": ["/workspace/work"],
            "mounts": [{"path": "work", "mode": "ro"}], "env": {"LOG_LEVEL": "info"},
            "reason": {"kind": "local_file", "text": "사내 문서 폴더를 읽어 요약해야 한다"}}
    return {**base, **change}


class ManifestRules(unittest.TestCase):
    def test_valid_manifest(self):
        self.assertEqual(local_jobs.manifest_errors(manifest(), "fs-local"), [])

    def test_refusals(self):
        for change in ({"image": "mcp/filesystem:latest"}, {"server_id": "other"},
                       {"mounts": [{"path": "", "mode": "ro"}]}, {"mounts": [{"path": ".ssh", "mode": "ro"}]},
                       {"mounts": [{"path": "work/.config", "mode": "ro"}]}, {"mounts": [{"path": "/etc", "mode": "ro"}]},
                       {"mounts": [{"path": "work/../..", "mode": "ro"}]}, {"mounts": [{"path": "work", "mode": "rwx"}]},
                       {"env": {"LD_PRELOAD": "/x.so"}}, {"env": {"NODE_OPTIONS": "--require x"}}, {"env": {"PATH": "/x"}},
                       {"reason": {"kind": "remote_api", "text": "원격 API를 감싸는 서버입니다"}},
                       {"reason": {"kind": "local_file", "text": "짧음"}}, {"command": "sh -c x"}):
            with self.subTest(change=change):
                self.assertNotEqual(local_jobs.manifest_errors(manifest(**change), "fs-local"), [])
        self.assertNotEqual(local_jobs.manifest_errors({**manifest(), "privileged": True}, "fs-local"), [])

    def test_signature_with_gateway_and_runner(self):
        key = Ed25519PrivateKey.generate()
        pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        body = manifest()
        signature = base64.b64encode(key.sign(local_jobs.canonical(body))).decode()
        with patch.dict(os.environ, {"LOCAL_MANIFEST_PUBKEY": pem.replace("\n", "\\n")}):
            self.assertTrue(local_jobs.verify(body, signature))
            self.assertFalse(local_jobs.verify(manifest(command=["/"]), signature))
            block = local_jobs.local_block(body, signature, "dev-1", "fs-local")
        self.assertEqual(len(block["manifest_sha256"]), 64)
        self.assertEqual(runner.canonical(body), local_jobs.canonical(body))
        if shutil.which("openssl"):
            self.assertTrue(runner.signed(body, signature, pem))
            self.assertFalse(runner.signed(manifest(env={}), signature, pem))
            other = Ed25519PrivateKey.generate().public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
            self.assertFalse(runner.signed(body, signature, other))
        self.assertFalse(runner.signed(body, signature, ""))


@unittest.skipUnless(sys.platform.startswith("linux") and pwd is not None, "POSIX 경로 규칙")
class RunnerCommand(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)
        os.mkdir(os.path.join(self.home, "work"))
        self.account = pwd.struct_passwd(("u", "x", 2001, 2001, "", self.home, "/bin/sh"))
        self.pinned = runner.PinnedMounts(manifest(), self.home)
        self.addCleanup(self.pinned.close)

    def test_fixed_isolation_options(self):
        name, command = runner.container_command("/usr/bin/docker", {**manifest(), "command": ["serve"]}, self.account,
                                                 mount_options=self.pinned.options,
                                                 host_paths=[str(path) for path, *_ in self.pinned.paths])
        for flag in ("--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pull=never", "--rm", "-i"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--user") + 1], "2001:2001")
        # docker는 홈 경로를 계정 이름과 무관한 컨테이너 경로 /workspace/<상대경로>에 바인드한다.
        self.assertIn(f"{self.home}/work:/workspace/work:ro", command)
        self.assertNotIn(f"{self.home}/work:{self.home}/work:ro", command)
        self.assertEqual(command[-2:], [IMAGE, "serve"])
        self.assertNotIn("--privileged", command)
        self.assertEqual(name, "mcpgw-local-fs-local-2001")

    def test_symlink_and_missing_mounts_refused(self):
        os.symlink("/etc", os.path.join(self.home, "link"))
        for path in ("link", "missing"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.PinnedMounts(manifest(mounts=[{"path": path, "mode": "ro"}]), self.home)
        # 첫 설치 PC: 승인된 폴더가 없으면 소유자를 받은 러너가 그 계정 소유 0700으로 만든다. 링크는 여전히 거부.
        owner = (os.getuid(), os.getgid())
        made = runner.PinnedMounts(manifest(mounts=[{"path": "fresh/docs", "mode": "ro"}]), self.home, owner)
        self.addCleanup(made.close)
        self.assertEqual(os.stat(os.path.join(self.home, "fresh", "docs")).st_mode & 0o777, 0o700)
        with self.assertRaises(ValueError):
            runner.PinnedMounts(manifest(mounts=[{"path": "link", "mode": "ro"}]), self.home, owner)
        # 별도 관리 계정: 읽기 전용 폴더는 직원 홈(직원이 문서를 넣는 곳)에서, 쓰기 폴더는 관리 계정 홈에 둔다(D-224).
        employee = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, employee)
        split = runner.PinnedMounts(manifest(mounts=[{"path": "docs", "mode": "ro"}, {"path": "state", "mode": "rw"}]),
                                    self.home, owner, (employee, *owner))
        self.addCleanup(split.close)
        self.assertEqual([str(p).startswith(employee) for p, *_ in split.paths], [True, False])
        self.assertEqual(os.stat(os.path.join(employee, "docs")).st_mode & 0o777, 0o755)
        with self.assertRaises(ValueError):
            runner.container_command("docker", manifest(image="mcp/filesystem:latest"), self.account,
                                     mount_options=self.pinned.options)
        with self.assertRaises(ValueError):
            runner.container_command("docker", manifest(env={"LD_PRELOAD": "x"}), self.account,
                                     mount_options=self.pinned.options)


if __name__ == "__main__":
    unittest.main()
