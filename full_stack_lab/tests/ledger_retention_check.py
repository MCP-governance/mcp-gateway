"""DEV-67 / D-141: retention floors and the sealed audit-chain prefix.

The pure parts (floors, signed seal journal, chain walk) run anywhere with jsonschema and
cryptography; the verify_audit_chain wiring needs the gateway image (psycopg).
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import base64
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import contract, disposal, retention

try:
    from app import core
except ImportError:  # psycopg and friends only exist in the gateway image
    core = None


def keys():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"DISPOSAL_PRIVATE_KEY": base64.urlsafe_b64encode(raw).decode(),
            "DISPOSAL_PUBLIC_KEY": base64.urlsafe_b64encode(public).decode()}


def chain(count, start=datetime(2025, 1, 1, tzinfo=UTC)):
    rows, previous = [], contract.GENESIS
    for number in range(1, count + 1):
        row = dict.fromkeys(contract.AUDIT_COLUMNS)
        row.update(id=number, request_id=f"r{number}", decision="Allow", policy_id="P-ALLOW",
                   upstream_executed=True, created_at=start + timedelta(days=number),
                   chain_version=contract.CHAIN_VERSION, prev_sha256=previous)
        previous = hashlib.sha256((previous + contract.audit_fingerprint(row)).encode()).hexdigest()
        row["entry_sha256"] = previous
        rows.append(row)
    return rows, {"head_sha256": previous, "entries": count}


def seal_detail(rows, last_id, **overrides):
    row = rows[last_id - 1]
    return {"last_id": last_id, "last_sha256": row["entry_sha256"], "last_created_at": row["created_at"].isoformat(),
            "retention_days": 366, "jurisdictions": ["EU"], "reason": "보존 기간 만료 구간 폐기",
            "requested_by": "admin-a", "approved_by": "admin-b", **overrides}


class Floors(unittest.TestCase):
    def test_below_floor_is_refused_and_the_longest_floor_wins(self):
        with self.assertRaises(ValueError):
            retention.check(183, ["EU"])
        self.assertEqual(retention.check(184, ["EU"]), 184)
        self.assertEqual(retention.check(366, ["EU", "US-FED"]), 366)
        with self.assertRaises(ValueError):
            retention.check(400, ["EU", "KR-CREDIT"])
        self.assertEqual(retention.check(1096, ["CN", "KR-CREDIT"]), 1096)

    def test_no_pack_falls_back_to_twelve_months_and_bad_input_is_refused(self):
        with self.assertRaises(ValueError):
            retention.check(365, [])
        self.assertEqual(retention.check(366, []), retention.DEFAULT_DAYS)
        for days, packs in ((400, ["XX"]), (True, []), ("400", []), (None, ["EU"])):
            with self.subTest(days=days, packs=packs), self.assertRaises(ValueError):
                retention.check(days, packs)


class SealedChain(unittest.TestCase):
    def setUp(self):
        self.rows, self.head = chain(10)
        self.directory = Path(tempfile.mkdtemp())
        self.env = patch.dict(os.environ, keys())
        self.env.start()
        self.addCleanup(self.env.stop)
        disposal.initialize(self.directory)

    def seal(self, last_id, **overrides):
        disposal.remember("ledger", f"decisions:{last_id}", detail=seal_detail(self.rows, last_id, **overrides),
                          directory=self.directory)
        return retention.current_seal(self.directory)

    def test_purged_prefix_verifies_from_the_seal_and_later_rows_continue(self):
        seal = self.seal(6)
        self.assertEqual(seal["last_id"], 6)
        result = contract.walk_chain(self.rows[6:], self.head, seal)
        self.assertTrue(result["intact"], result)
        self.assertEqual((result["checked"], result["sealed_through"]), (4, 6))
        # Everything sealed and nothing appended since: the head is the seal hash itself.
        everything = self.seal(10)
        self.assertTrue(contract.walk_chain([], self.head, everything)["intact"])

    def test_restored_backup_brings_sealed_rows_back_and_is_flagged(self):
        seal = self.seal(6)
        for restored in (self.rows, self.rows[3:]):
            result = contract.walk_chain(restored, self.head, seal)
            self.assertFalse(result["intact"])
            self.assertEqual(result["broken_at"], restored[0]["id"])
            self.assertIn("되살아났", result["reason"])

    def test_purge_without_a_readable_seal_breaks_the_chain(self):
        self.seal(6)
        result = contract.walk_chain(self.rows[6:], self.head, None)
        self.assertEqual((result["intact"], result["broken_at"]), (False, 7))

    def test_rows_deleted_beyond_the_seal_are_caught(self):
        seal = self.seal(6)
        result = contract.walk_chain(self.rows[8:], self.head, seal)
        self.assertEqual((result["intact"], result["broken_at"]), (False, 9))

    def test_signed_seal_with_another_hash_does_not_cover_the_gap(self):
        seal = self.seal(6, last_sha256="f" * 64)
        result = contract.walk_chain(self.rows[6:], self.head, seal)
        self.assertEqual((result["intact"], result["broken_at"]), (False, 7))

    def test_edited_journal_drops_the_seal(self):
        self.seal(6)
        journal = self.directory / "journal.jsonl"
        lines = journal.read_bytes().splitlines()
        envelope = json.loads(lines[-1])
        envelope["payload"]["detail"]["last_id"] = 8
        journal.write_bytes(b"\n".join([*lines[:-1], disposal.encoded(envelope)]) + b"\n")
        self.assertIsNone(retention.current_seal(self.directory))

    def test_seals_that_break_the_rules_are_corruption(self):
        cases = {"one person": {"approved_by": "admin-a"},
                 "inside retention": {"last_created_at": datetime.now(UTC).isoformat()},
                 "below floor": {"retention_days": 100},
                 "unknown pack": {"jurisdictions": ["XX"]},
                 "no reason": {"reason": ""}}
        for name, override in cases.items():
            with self.subTest(name):
                directory = Path(tempfile.mkdtemp())
                disposal.initialize(directory)
                disposal.remember("ledger", "decisions:6", detail=seal_detail(self.rows, 6, **override),
                                  directory=directory)
                self.assertIsNone(retention.current_seal(directory))

    def test_seals_only_move_forward(self):
        self.seal(6)
        self.seal(4)
        self.assertIsNone(retention.current_seal(self.directory))

    def test_ledger_seal_is_not_a_server_tombstone(self):
        self.seal(6)
        with patch.object(disposal, "DIRECTORY", self.directory):
            self.assertFalse(disposal.blocked(server_id="decisions:6"))
            self.assertFalse(disposal.blocked(server_id=""))


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return self.rows


class Snapshot:
    def __init__(self, rows, head):
        self.rows, self.head = rows, head

    async def execute(self, query, params=None):
        if "FROM decisions ORDER BY id" in query:
            return Cursor(self.rows)
        if "FROM audit_chain" in query:
            return Cursor([self.head])
        raise AssertionError(query)


@unittest.skipIf(core is None, "gateway image only")
class GatewayVerify(unittest.IsolatedAsyncioTestCase):
    async def test_verify_reads_the_journal_seal(self):
        rows, head = chain(10)
        seal = seal_detail(rows, 6)
        purged = Snapshot(rows[6:], head)
        with patch.object(retention, "current_seal", return_value=seal):
            self.assertTrue((await core.verify_audit_chain(purged))["intact"])
            restored = await core.verify_audit_chain(Snapshot(rows, head))
            self.assertEqual((restored["intact"], restored["broken_at"]), (False, 1))
        with patch.object(retention, "current_seal", return_value=None):
            self.assertEqual((await core.verify_audit_chain(purged))["broken_at"], 7)
            self.assertTrue((await core.verify_audit_chain(Snapshot(rows, head)))["intact"])


if __name__ == "__main__":
    unittest.main()
