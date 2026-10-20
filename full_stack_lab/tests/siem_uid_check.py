"""D-157 UID and attempt-log regressions without PostgreSQL or an MCP server."""
from __future__ import annotations

from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import ssl
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gateway"))
from app import siem
from siem_tls_receiver import receiver


def decision(**changes):
    return {"id": 7, "created_at": datetime(2026, 10, 20, tzinfo=timezone.utc),
            "decision": "Block", "policy_id": "MCP-CATALOG-001", "upstream_attempted": False,
            "upstream_executed": False, "entry_sha256": "a" * 64, **changes}


class UidChecks(unittest.TestCase):
    def test_chain_and_row_identity_ignore_session_timezone_and_attempt_state(self):
        row = decision()
        expected = "mint:decisions:7:" + "a" * 64
        self.assertEqual(siem.event("decisions", row)["metadata"]["uid"], expected)
        row.update(created_at=row["created_at"].astimezone(timezone(timedelta(hours=9))), attempts=99)
        self.assertEqual(siem.event("decisions", row)["metadata"]["uid"], expected)

    def test_row_id_and_chain_changes_are_distinct_events(self):
        uids = {siem.event("decisions", row)["metadata"]["uid"] for row in
                (decision(), decision(id=8), decision(entry_sha256="b" * 64))}
        self.assertEqual(len(uids), 3)

    def test_unchained_sources_use_utc_and_keep_the_legacy_utc_uid(self):
        row = decision(entry_sha256=None, kind="contract-reapprove", outcome="approved", synthetic=False)
        for source in siem.SOURCE_COLUMNS:
            with self.subTest(source=source):
                expected = f"mint:{source}:7:{siem.reference(row['created_at'].isoformat())}"
                shifted = {**row, "created_at": row["created_at"].astimezone(timezone(timedelta(hours=-7)))}
                self.assertEqual(siem.event(source, row)["metadata"]["uid"], expected)
                self.assertEqual(siem.event(source, shifted)["metadata"]["uid"], expected)

    def test_invalid_chain_is_not_silently_reidentified(self):
        for value in ("", "A" * 64, "private-credential", "a" * 63):
            with self.subTest(value=value), self.assertRaises(ValueError):
                siem.event("decisions", decision(entry_sha256=value))

    def test_uid_does_not_include_private_fields(self):
        a = siem.event("decisions", decision(user_token="private-token", reason="private-body"))
        b = siem.event("decisions", decision(user_token="different-token", reason="different-body"))
        self.assertEqual(a["metadata"]["uid"], b["metadata"]["uid"])


class AttemptLogChecks(unittest.IsolatedAsyncioTestCase):
    async def test_ack_then_commit_failure_keeps_two_uid_attempts_but_one_commit_log(self):
        row = decision()
        job = {"id": 1, "source": "decisions", "source_id": 7, "attempts": 0}
        execute = AsyncMock(side_effect=lambda query, *args: types.SimpleNamespace(
            fetchone=AsyncMock(return_value=job if query.startswith("SELECT *") else row)))
        fail_commit = True

        @asynccontextmanager
        async def transaction():
            yield types.SimpleNamespace(execute=execute)
            if fail_commit:
                raise OSError("private-database-error")

        fake_db = types.SimpleNamespace(transaction=transaction)
        uid = siem.event("decisions", row)["metadata"]["uid"]
        with patch.dict(sys.modules, {"app.db": fake_db}), patch.object(siem, "send", return_value=200), \
                self.assertLogs(siem.LOG, level="INFO") as logs:
            with self.assertRaises(OSError):
                await siem.deliver_one({})
            fail_commit = False
            await siem.deliver_one({})
        self.assertEqual(sum("SIEM attempt uid=" + uid in line for line in logs.output), 2)
        self.assertEqual(sum("SIEM response uid=" + uid in line for line in logs.output), 2)
        self.assertEqual(sum("SIEM queue committed uid=" + uid in line for line in logs.output), 1)
        self.assertNotIn("private", "\n".join(logs.output))


class TlsChecks(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("cryptography"), "gateway cryptography dependency required")
    def test_verified_ca_hostname_and_receiver_uid_deduplication(self):
        import sqlite3

        payload = siem.event("decisions", decision())
        with tempfile.TemporaryDirectory(prefix="siem-tls-") as name:
            with receiver(Path(name)) as (config, received, failures, store):
                for bad in ({**config, "ca_file": ""},
                            {**config, "url": config["url"].replace("localhost", "127.0.0.1")}):
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        siem.send(bad, payload)
                self.assertEqual(received, [])
                self.assertEqual([siem.send(config, payload) for _ in range(3)], [503, 200, 200])
                self.assertEqual({uid for uid, _, _ in received}, {payload["metadata"]["uid"]})
                self.assertEqual(failures, [])
                with closing(sqlite3.connect(store)) as sink:
                    self.assertEqual(sink.execute("SELECT count(*) FROM events").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
