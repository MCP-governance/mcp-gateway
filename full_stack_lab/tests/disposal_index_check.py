"""Verified disposal-index checks with throwaway signing keys and files only."""
import base64
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from termination_lab_support import isolated_disposal
except ModuleNotFoundError:
    serialization = None
    import ops_response_check as signing_support
    from ops_response_check import OPENSSL, OpenSSLKey

from app import disposal


class DisposalIndexChecks(unittest.TestCase):
    def setUp(self):
        if serialization is not None:
            self.store = isolated_disposal()
            self.store.__enter__()
            self.addCleanup(self.store.__exit__, None, None, None)
        else:
            if not OPENSSL:
                raise RuntimeError("cryptography or OpenSSL is required for real Ed25519 checks")
            self.store = signing_support.Disposal()
            self.store.setUp()
            self.addCleanup(self.store.doCleanups)
        self.addCleanup(disposal._INDEX.clear)
        disposal.remember("token", "old-jti", detail={"nested": {"value": "original"}})
        disposal.remember("refresh", "refresh-hash")
        disposal.remember("server", "server-subject", "server-id")
        disposal.remember("credential", "credential-subject")
        disposal.remember("credential", "credential-id", "credential-server")
        self.directory = disposal.DIRECTORY

    def read(self):
        return disposal.read()

    def assert_corrupt(self, name, mutate):
        self.assertTrue(disposal.blocked(jti="old-jti"))
        journal = self.directory / "journal.jsonl"
        head = self.directory / "head.json"
        before, before_head = journal.read_bytes(), head.read_bytes()
        mutate(journal, head)
        self.assertNotEqual((journal.read_bytes(), head.read_bytes()), (before, before_head), name)
        with self.assertRaises(disposal.IntegrityError, msg=name):
            disposal.blocked(jti="unrelated", raise_errors=True)
        self.assertNotIn(self.directory.resolve(), disposal._INDEX)
        self.assertTrue(disposal.blocked(jti="unrelated"), name)
        with self.assertRaises(disposal.IntegrityError, msg=name):
            self.read()

    def test_repeated_queries_skip_head_and_record_signatures(self):
        with patch.object(disposal, "verified", wraps=disposal.verified) as verified:
            self.assertTrue(disposal.blocked(jti="old-jti"))
            cold = verified.call_count
            records = self.read()
            self.assertEqual(cold, len(records) + 1)
            for _ in range(10):
                self.assertTrue(disposal.blocked(jti="old-jti"))
                self.assertFalse(disposal.blocked(jti="other"))
                self.assertEqual(self.read(), records)
            self.assertEqual(verified.call_count, cold)

    def test_same_size_and_mtime_tampering(self):
        def mutate(journal, head):
            stat = journal.stat()
            before = journal.read_bytes()
            after = before.replace(b"old-jti", b"bad-jti", 1)
            self.assertNotEqual(before, after)
            self.assertEqual(len(before), len(after))
            journal.write_bytes(after)
            os.utime(journal, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.assertEqual(journal.stat().st_size, stat.st_size)
            self.assertEqual(journal.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assert_corrupt("same size/mtime", mutate)

    def test_head_only_tampering(self):
        def mutate(journal, head):
            envelope = json.loads(head.read_bytes())
            envelope["signature"] = base64.b64encode(b"\0" * 64).decode()
            head.write_bytes(disposal.encoded(envelope))
        self.assert_corrupt("head signature", mutate)

    def test_truncated_journal(self):
        self.assert_corrupt("truncation", lambda journal, head: journal.write_bytes(journal.read_bytes()[:-1]))

    def test_unsigned_suffix(self):
        self.assert_corrupt("unsigned suffix", lambda journal, head: journal.write_bytes(
            journal.read_bytes() + b'{"kind":"token","subject":"unsigned"}\n'))

    def test_signed_head_cannot_hide_invalid_record_signature(self):
        def mutate(journal, head):
            journal.write_bytes(journal.read_bytes().replace(b"old-jti", b"bad-jti", 1))
            raw = journal.read_bytes()
            head.write_bytes(disposal.encoded(disposal.signed(
                {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})))
        self.assert_corrupt("invalid record under a newly signed head", mutate)

    def test_head_byte_change_forces_full_verification(self):
        self.assertTrue(disposal.blocked(jti="old-jti"))
        path = self.directory / "head.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with patch.object(disposal, "verified", wraps=disposal.verified) as verified:
            self.assertTrue(disposal.blocked(jti="old-jti"))
            self.assertEqual(verified.call_count, len(self.read()) + 1)

    def test_remember_is_immediately_visible(self):
        self.assertFalse(disposal.blocked(jti="new-jti"))
        disposal.remember("token", "new-jti")
        self.assertTrue(disposal.blocked(jti="new-jti"))
        self.assertFalse(disposal.blocked(jti="another-jti"))

    def test_cached_and_cold_results_match_100_random_queries(self):
        records = self.read()
        rng = random.Random(4)
        values = [None, "old-jti", "refresh-hash", "server-id", "server-subject",
                  "credential-subject", "credential-id", "credential-server", "unknown", "", 123]
        hits = 0
        for _ in range(100):
            query = {name: rng.choice(values) for name in ("jti", "refresh", "server_id")}
            expected = any(
                (query["jti"] is not None and r["kind"] == "token" and r["subject"] == str(query["jti"]))
                or (query["refresh"] is not None and r["kind"] == "refresh" and r["subject"] == query["refresh"])
                or (query["server_id"] is not None and r["kind"] in {"server", "credential"}
                    and (r["server_id"] or r["subject"]) == query["server_id"]) for r in records)
            cached = disposal.blocked(**query, raise_errors=True)
            disposal._INDEX.clear()
            cold = disposal.blocked(**query, raise_errors=True)
            self.assertEqual((cached, cold), (expected, expected), query)
            hits += expected
        self.assertGreater(hits, 0)
        self.assertLess(hits, 100)

    def test_read_mutations_cannot_poison_cached_records(self):
        records = self.read()
        records[1]["subject"] = "forged"
        records[1]["detail"]["nested"]["value"] = "forged"
        records.clear()
        self.assertTrue(disposal.blocked(jti="old-jti"))
        self.assertFalse(disposal.blocked(jti="forged"))
        self.assertEqual(self.read()[1]["detail"]["nested"]["value"], "original")

    def test_public_key_change_invalidates_cache(self):
        self.assertTrue(disposal.blocked(jti="old-jti"))
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            if serialization is not None:
                key = Ed25519PrivateKey.generate().public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw)
                stack.enter_context(patch.dict(os.environ, {"DISPOSAL_PUBLIC_KEY": base64.urlsafe_b64encode(key).decode()}))
            else:
                stack.enter_context(patch.object(disposal, "key", return_value=OpenSSLKey(Path(folder))))
                stack.enter_context(patch.dict(os.environ, {"DISPOSAL_PUBLIC_KEY": "changed"}))
            with self.assertRaises(disposal.IntegrityError):
                disposal.blocked(jti="other", raise_errors=True)
            self.assertTrue(disposal.blocked(jti="other"))
        self.assertFalse(disposal.blocked(jti="other"))

    def test_missing_files_discard_cache_and_fail_closed(self):
        for name in ("head.json", "journal.jsonl"):
            with self.subTest(name=name):
                self.assertFalse(disposal.blocked(jti="other"))
                path = self.directory / name
                raw = path.read_bytes()
                try:
                    path.unlink()
                    with self.assertRaises(disposal.IntegrityError):
                        disposal.blocked(jti="other", raise_errors=True)
                    self.assertNotIn(self.directory.resolve(), disposal._INDEX)
                    self.assertTrue(disposal.blocked(jti="other"))
                finally:
                    path.write_bytes(raw)


def benchmark(before_path):
    if serialization is None:
        raise RuntimeError("cryptography unavailable: OpenSSL subprocess timing is not production timing")
    spec = importlib.util.spec_from_file_location("disposal_before", before_path)
    before = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(before)
    with isolated_disposal():
        before.DIRECTORY = disposal.DIRECTORY
        with disposal.locked(disposal.DIRECTORY):
            records = disposal._read_index(disposal.DIRECTORY)["records"].copy()
            for number in range(499):
                disposal._append(disposal.DIRECTORY, records, {
                    "kind": "token", "subject": f"jti-{number}", "server_id": "", "detail": {}})
                records.append(None)
        assert len(disposal.read()) == 500
        timings = {}
        for name, module in (("before", before), ("after", disposal)):
            started = time.perf_counter()
            for number in range(1000):
                assert module.blocked(jti=f"jti-{number % 499}", raise_errors=True)
            timings[name] = time.perf_counter() - started
        print(json.dumps({"records": 500, "queries": 1000, "seconds": timings,
                          "speedup": timings["before"] / timings["after"]}))
    disposal._INDEX.clear()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--benchmark-before":
        benchmark(sys.argv[2])
    else:
        unittest.main(verbosity=2)
