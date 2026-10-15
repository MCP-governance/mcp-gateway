"""Provenance digest, completeness and archive verification (unit level, no network, no database).

The worker hashes the tree it scanned; the Gateway hashes the archive of the copy employees get. The
two code paths live in different build contexts, so this file is what keeps them equal.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "gateway"))
from app import agent_service, provenance  # noqa: E402

spec = importlib.util.spec_from_file_location("worker_provenance", LAB / "supply_chain" / "provenance.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

FILES = {"README.md": b"# server\n", "src/main.py": b"print('hi')\n", "src/empty.txt": b"", "LICENSE": b"MIT\n"}


def archive(files: dict[str, bytes], top: str = "server", links: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        directory = tarfile.TarInfo(top + "/")
        directory.type = tarfile.DIRTYPE
        tar.addfile(directory)
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.type, info.linkname = tarfile.SYMTYPE, target
            tar.addfile(info)
    return buffer.getvalue()


def write_tree(root: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class DigestTest(unittest.TestCase):
    def test_worker_tree_and_gateway_archive_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_tree(root, FILES)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("not part of the artifact")
            from_tree = worker.tree_digest(root)
            self.assertEqual(from_tree, provenance.tree_digest(root))
        from_archive = provenance.archive_digest(io.BytesIO(archive(FILES)))
        self.assertEqual(from_tree, from_archive)
        self.assertEqual(from_tree["files"], 4)

    def test_symlink_counts_as_a_file_holding_its_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_tree(root, {**FILES, "link": b"README.md"})
            self.assertEqual(worker.tree_digest(root)["sha256"],
                             provenance.archive_digest(io.BytesIO(archive(FILES, links={"link": "README.md"})))["sha256"])

    def test_any_change_moves_the_digest(self):
        baseline = provenance.archive_digest(io.BytesIO(archive(FILES)))["sha256"]
        for changed in ({**FILES, "src/main.py": b"print('evil')\n"}, {**FILES, "extra.sh": b"curl x | sh"},
                        {k: v for k, v in FILES.items() if k != "LICENSE"}, {**{k.replace("README", "README2"): v for k, v in FILES.items()}}):
            self.assertNotEqual(provenance.archive_digest(io.BytesIO(archive(changed)))["sha256"], baseline)

    def test_path_escape_and_oversize_are_refused(self):
        with self.assertRaises(ValueError):
            provenance.archive_digest(io.BytesIO(archive({"../escape": b"x"})))
        with self.assertRaises(ValueError):
            provenance.archive_digest(io.BytesIO(archive({"big": b"x" * 100})), limit=10)


class CompletenessTest(unittest.TestCase):
    source = {"kind": "source", "source_url": "https://github.com/o/r", "version": "a" * 40,
              "license": {"spdx": "MIT"}, "artifact": {"applicable": True, "sha256": "b" * 64}}
    hosted = {"kind": "provider-hosted", "source_url": "https://mcp.example.com/mcp", "version": "2.1.0",
              "artifact": {"applicable": False, "reason": "해당 없음", "endpoint": "https://mcp.example.com/mcp"}}

    def test_complete_records(self):
        self.assertEqual(provenance.missing(self.source, intake_kind="repository", source_url="https://github.com/o/r"), [])
        self.assertEqual(provenance.missing(self.hosted, intake_kind="remote-endpoint", source_url="https://mcp.example.com/mcp"), [])

    def test_each_gap_is_named(self):
        cases = {
            "고정 커밋": {"version": "main"}, "라이선스": {"license": None}, "배포 파일 해시": {"artifact": {"sha256": "short"}},
            "공급 주소": {"source_url": ""},
        }
        for gap, change in cases.items():
            self.assertIn(gap, provenance.missing({**self.source, **change}, intake_kind="repository"))
        self.assertEqual(provenance.missing({}, intake_kind="repository"), ["출처 기록 없음"])
        self.assertEqual(provenance.missing(self.source, intake_kind="remote-endpoint"), ["출처 기록 없음"])

    def test_source_url_must_be_the_requested_one(self):
        self.assertIn("공급 주소", provenance.missing(self.source, intake_kind="repository", source_url="https://github.com/o/other"))

    def test_provider_hosted_never_carries_a_made_up_hash(self):
        faked = {**self.hosted, "artifact": {"applicable": False, "sha256": "c" * 64}}
        self.assertIn("배포 파일 구분", provenance.missing(faked, intake_kind="remote-endpoint"))
        applicable = {**self.hosted, "artifact": {"applicable": True}}
        self.assertIn("배포 파일 구분", provenance.missing(applicable, intake_kind="remote-endpoint"))


class InternalArchiveTest(unittest.TestCase):
    """The Gitea round trip, with an in-process transport standing in for the repository server."""

    def digest(self, handler):
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://gitea.test") as client:
                return await agent_service.internal_archive_digest(client, "/api/v1/repos/mcp/o-r", "a" * 40)
        return asyncio.run(run())

    def test_matching_archive(self):
        body = archive(FILES)
        seen = []

        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200, content=body)
        result = self.digest(handler)
        self.assertEqual(seen, ["/api/v1/repos/mcp/o-r/archive/" + "a" * 40 + ".tar.gz"])
        with tempfile.TemporaryDirectory() as temp:
            write_tree(Path(temp), FILES)
            self.assertEqual(result, worker.tree_digest(Path(temp)))

    def test_unreadable_or_failed_download_is_not_a_match(self):
        with self.assertRaises(agent_service.ProvenanceMismatch):
            self.digest(lambda request: httpx.Response(200, content=b"not a tar archive"))
        with self.assertRaises(agent_service.HTTPException):
            self.digest(lambda request: httpx.Response(404))

    def test_oversized_download_is_stopped(self):
        with patch.object(provenance, "MAX_ARCHIVE_BYTES", 8), self.assertRaises(agent_service.ProvenanceMismatch):
            self.digest(lambda request: httpx.Response(200, content=archive(FILES)))


class VulnDatabaseAgeTest(unittest.TestCase):
    def test_age(self):
        from datetime import UTC, datetime, timedelta
        now = datetime(2026, 10, 15, tzinfo=UTC)
        self.assertIsNone(provenance.vuln_db_age(None, now))
        self.assertEqual(provenance.vuln_db_age(now - timedelta(days=3), now), timedelta(days=3))
        self.assertEqual(provenance.VULN_DB_MAX_AGE, timedelta(days=7))


if __name__ == "__main__":
    unittest.main()
