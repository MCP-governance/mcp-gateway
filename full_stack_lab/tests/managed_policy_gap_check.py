"""D-198 오프라인 검사: 서버 추가만 있는 정책 변경은 장치가 가진 서버를 막지 않고, 통제 변경은 즉시 막는다.

DB·MCP 서버는 대역이며 집행 증거가 아니다. 저장소 루트: python -B -X utf8 full_stack_lab/tests/managed_policy_gap_check.py
"""
import ast
import hashlib
import ipaddress
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
import sys

LAB = Path(__file__).resolve().parents[1]
NAMES = {"managed_policy", "managed_platform", "json_document", "_held_policy", "managed_failure", "heartbeat", "policy_accepted",
         "managed_checks", "MANAGED_CHECKS", "MANAGED_CHECKS_BY_PLATFORM"}
OLD = "엔드포인트 정책이 최신 정책과 달라 연결을 중단했습니다."
NEW = "새로 승인된 서버입니다. PC가 새 정책을 적용하면 사용할 수 있습니다."


def load(namespace):
    path = LAB / "gateway/app/endpoint_plane.py"
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in NAMES
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in NAMES for t in n.targets)]
    namespace = dict(namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class PolicyGap(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.usable = ["docs", "git"]
        package = ModuleType("gap_policy")
        package.pac = SimpleNamespace(servers_for=lambda owner: self.usable, harness_guidance=lambda owner, servers: "")
        connection = SimpleNamespace(execute=AsyncMock())
        connection.execute.return_value = SimpleNamespace(fetchone=AsyncMock(return_value={"managed_state": "active"}))

        class Transaction:
            async def __aenter__(inner):
                return connection

            async def __aexit__(inner, *args):
                return False
        self.device = {"endpoint_id": "d", "owner_token": "o", "managed_state": "active", "status": "active",
                       "device_epoch": "e", "local_username": "u", "local_uid": 1, "detail": {},
                       "heartbeat_at": datetime.now(timezone.utc)}
        self.db = SimpleNamespace(
            fetch_all=AsyncMock(return_value=[{"id": s} for s in ("docs", "git", "mail")]),
            fetch_one=AsyncMock(side_effect=lambda sql, *a: {"token": "o"} if "principals" in sql else self.device),
            transaction=Transaction)
        self.plane = load({"__name__": "gap_under_test", "__package__": package.__name__, "os": os, "urlsplit": urlsplit,
                           "ipaddress": ipaddress, "hashlib": hashlib, "HEARTBEAT_INTERVAL": 60, "HEARTBEAT_SECONDS": 180,
                           "db": self.db, "datetime": datetime, "UTC": timezone.utc, "Jsonb": lambda v: v})
        # MODEL_PROXY_PORT is cleared: a gateway image already sets it, which would make the change below no change.
        env = patch.dict(os.environ, {"IDP_ISSUER": "https://gateway.example", "ENDPOINT_GATEWAY_IPS": "100.64.0.2", "MODEL_PROXY_PORT": ""})
        env.start()
        self.addCleanup(env.stop)
        modules = patch.dict(sys.modules, {package.__name__: package})
        modules.start()
        self.addCleanup(modules.stop)
        self.principal = {"token": "o", "managed_required": True}

    async def install(self, servers):
        """The device holds the policy rendered for these servers (as a heartbeat would have recorded it)."""
        self.usable = servers
        held = await self.plane.managed_policy(self.device)
        self.device.update(policy_hash=held["policy_hash"], detail={"policy_servers": held["servers"]})
        return held["policy_hash"]

    def claims(self, hash_):
        return {"device_id": "d", "device_epoch": "e", "scope": "mcp", "device_policy": hash_}

    async def test_added_server_keeps_held_servers_and_defers_new_one(self):
        installed = await self.install(["git"])
        self.usable = ["docs", "git"]  # the administrator approved docs
        for server, expected in (("git", None), (None, None), ("docs", NEW)):
            self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server=server), expected)

    async def test_control_changes_stop_everything(self):
        installed = await self.install(["git"])
        self.usable = ["docs", "git"]
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):  # firewall allow-list
            self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"), OLD)
        with patch.dict(os.environ, {"MODEL_PROXY_PORT": "3128"}):  # protection setting
            self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"), OLD)
        self.device["local_username"] = "v"  # header helper path follows the account
        self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"), OLD)

    async def test_removed_server_unknown_record_and_stale_token_stop(self):
        installed = await self.install(["docs", "git"])
        self.usable = ["git"]  # docs removed: git keeps working, docs is refused (an upstream in ERROR must not cut the PC off)
        self.assertIsNone(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"))
        self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server="docs"), "사용할 수 없는 서버입니다.")
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):  # removal plus a control change still stops
            self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"), OLD)
        self.usable = ["docs", "git"]
        self.assertIsNone(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"))
        installed = await self.install(["git"])
        self.usable = ["docs", "git"]
        self.assertEqual(await self.plane.managed_failure(self.principal, self.claims("0" * 64), server="git"), OLD)
        self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), mint=True), OLD)
        self.device["detail"] = {}  # nothing recorded yet: strict, as before D-198
        self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(installed), server="git"), OLD)

    async def test_local_jobs_accept_a_policy_one_server_list_behind(self):
        await self.install(["docs", "git"])
        self.usable = ["git"]  # removed elsewhere: a local job on this PC keeps running
        self.assertTrue(await self.plane.policy_accepted(self.device))
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):
            self.assertFalse(await self.plane.policy_accepted(self.device))

    async def test_a_served_but_unconfirmed_policy_is_behind_not_tampered(self):
        # Two approvals in a row: the device installed the middle policy before any heartbeat confirmed it.
        await self.install(["git"])                       # confirmed: policy_servers = [git]
        self.usable = ["docs", "git"]
        middle = await self.plane.managed_policy(self.device)
        self.device["detail"]["served_policies"] = {middle["policy_hash"]: middle["servers"]}
        self.device["policy_hash"] = middle["policy_hash"]
        self.usable = ["docs", "git", "mail"]           # the next approval landed before the heartbeat
        self.assertIsNone(await self.plane.managed_failure(self.principal, self.claims(middle["policy_hash"]), server="docs"))
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):  # a control change still stops
            self.assertEqual(await self.plane.managed_failure(self.principal, self.claims(middle["policy_hash"]), server="docs"), OLD)

    async def test_heartbeat_with_older_server_set_is_compliant_but_control_drift_is_not(self):
        installed = await self.install(["git"])
        self.usable = ["docs", "git"]
        held = await self.plane.managed_policy(self.device, servers=["git"])
        checks = dict.fromkeys(self.plane.managed_checks(self.device), True)
        result = await self.plane.heartbeat(self.device, installed, held["configuration_hashes"], checks)
        self.assertTrue(result["compliant"])
        self.assertNotEqual(result["policy_hash"], installed)
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):
            self.assertFalse((await self.plane.heartbeat(self.device, installed, held["configuration_hashes"], checks))["compliant"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
