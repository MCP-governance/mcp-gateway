"""D-238 오프라인 검사: 통제 설정 변경은 차단·격리하고, 서버 목록 변경과 활성화는 장치를 끊지 않는다.

장치가 보고한 policy_hash는 control_hash와 설치 파일 해시의 결속값이라 게이트웨이가 기억 없이 다시 계산한다.
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
NAMES = {"managed_policy", "managed_platform", "json_document", "installed_hash", "legacy_hash", "policy_installed",
         "control_matches", "held_servers", "policy_accepted", "managed_failure", "heartbeat", "activate_managed",
         "managed_checks", "MANAGED_CHECKS", "MANAGED_CHECKS_BY_PLATFORM", "managed_mode", "SIMPLE_CHECKS",
         "endpoint_settings"}
OLD = "엔드포인트 정책이 최신 정책과 달라 연결을 중단했습니다."
NEW = "새로 승인된 서버입니다. PC가 새 정책을 적용하면 사용할 수 있습니다."
GONE = "사용할 수 없는 서버입니다."
PACKAGE = "gap_policy"


def load(path, names, namespace):
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    namespace = dict(namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class PolicySync(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.usable = ["docs", "git"]
        self.guidance = "# 조직 승인 MCP 도구\n"
        package = ModuleType(PACKAGE)
        package.pac = SimpleNamespace(servers_for=lambda owner: self.usable,
                                      harness_guidance=lambda owner, servers: self.guidance + ",".join(servers))
        self.updates = []

        async def execute(sql, params=None):
            self.updates.append((sql, params))
            return SimpleNamespace(rowcount=1, fetchone=AsyncMock(return_value={"managed_state": self.device["managed_state"]}))

        class Transaction:
            async def __aenter__(inner):
                return SimpleNamespace(execute=execute)

            async def __aexit__(inner, *args):
                return False

        def fetch_one(sql, *args):
            return ({"token": "o"} if "principals" in sql else {"last_value": 7} if "mcp_servers_version" in sql
                    else self.device)
        self.device = {"endpoint_id": "d", "owner_token": "o", "managed_state": "active", "status": "active",
                       "device_epoch": "e", "local_username": "u", "local_uid": 1, "detail": {},
                       "policy_hash": None, "configuration_hashes": {}, "heartbeat_at": datetime.now(timezone.utc)}
        db = SimpleNamespace(fetch_all=AsyncMock(return_value=[{"id": s} for s in ("docs", "git", "mail")]),
                             fetch_one=AsyncMock(side_effect=fetch_one), transaction=Transaction)
        self.plane = load(LAB / "gateway/app/endpoint_plane.py", NAMES,
                          {"__name__": PACKAGE + ".endpoint_plane", "__package__": PACKAGE, "os": os, "urlsplit": urlsplit,
                           "ipaddress": ipaddress, "hashlib": hashlib, "HEARTBEAT_INTERVAL": 60, "HEARTBEAT_SECONDS": 180,
                           "db": db, "datetime": datetime, "UTC": timezone.utc, "Jsonb": lambda v: v})
        package.endpoint_plane = self.plane
        self.jobs = load(LAB / "gateway/app/local_jobs.py", {"_same_control"}, {"__name__": PACKAGE + ".local_jobs",
                                                                               "__package__": PACKAGE})
        # MODEL_PROXY_PORT is cleared: a gateway image already sets it, which would make the change below no change.
        env = patch.dict(os.environ, {"IDP_ISSUER": "https://gateway.example", "ENDPOINT_GATEWAY_IPS": "100.64.0.2", "MODEL_PROXY_PORT": ""})
        env.start()
        self.addCleanup(env.stop)
        modules = patch.dict(sys.modules, {PACKAGE: package})
        modules.start()
        self.addCleanup(modules.stop)
        self.principal = {"token": "o", "managed_required": True}
        self.checks = dict.fromkeys(self.plane.managed_checks(self.device), True)

    async def beat(self, reported, hashes):
        """A heartbeat, with the row update applied to the device as the database would."""
        self.updates.clear()
        result = await self.plane.heartbeat(self.device, reported, hashes, self.checks)
        params = next(p for sql, p in self.updates if sql.lstrip().startswith("UPDATE endpoint_agents"))
        self.device.update(policy_hash=params[0], configuration_hashes=params[1],
                           detail={**{k: v for k, v in self.device["detail"].items() if k != "host"}, **params[3]})
        if not params[4]:
            self.device["managed_state"] = "quarantined"
        return result

    async def install(self, servers):
        """The kit's loop: fetch, install, heartbeat with the fetched hash and the installed files."""
        self.usable = servers
        policy = await self.plane.managed_policy(self.device)
        self.assertTrue((await self.beat(policy["policy_hash"], policy["configuration_hashes"]))["compliant"])
        return policy

    def claims(self, value):
        return {"device_id": "d", "device_epoch": "e", "scope": "mcp", "device_policy": value}

    async def failure(self, token, server=None, mint=False):
        return await self.plane.managed_failure(self.principal, self.claims(token), server=server, mint=mint)

    async def test_control_hash_leaves_out_servers_guidance_and_state(self):
        first = await self.plane.managed_policy(self.device)
        self.usable = ["git"]
        fewer = await self.plane.managed_policy(self.device)
        self.device["managed_state"] = "pending"
        waiting = await self.plane.managed_policy(self.device)
        self.assertEqual({first["control_hash"], fewer["control_hash"], waiting["control_hash"]}, {first["control_hash"]})
        self.assertEqual(len({first["policy_hash"], fewer["policy_hash"], waiting["policy_hash"]}), 3)
        self.assertIn("활성화를 기다리는", waiting["files"]["managed-settings.json"])
        self.assertIn(self.guidance.strip(), first["files"]["managed-settings.json"])
        self.assertEqual(first["servers_version"], 7)
        self.assertEqual(first["policy_hash"], self.plane.installed_hash(first["control_hash"], first["configuration_hashes"]))

    async def test_control_changes_stop_everything_and_quarantine(self):
        installed = await self.install(["git"])
        token = installed["control_hash"]
        for change in ({"ENDPOINT_GATEWAY_IPS": "100.64.0.9"},  # firewall allow-list
                       {"MODEL_PROXY_PORT": "3128"},            # protection setting
                       {"IDP_ISSUER": "https://other.example"}):  # gateway address
            with self.subTest(change=change), patch.dict(os.environ, change):
                self.assertEqual(await self.failure(token, "git"), OLD)
                self.assertEqual(await self.failure(token, mint=True), OLD)
                self.assertFalse(await self.plane.policy_accepted(self.device))
        self.device["local_username"] = "v"  # header helper path follows the account
        self.assertEqual(await self.failure(token, "git"), OLD)
        result = await self.beat(installed["policy_hash"], installed["configuration_hashes"])
        self.assertFalse(result["compliant"])
        self.assertEqual(self.device["managed_state"], "quarantined")

    async def test_tampered_or_incomplete_files_are_not_a_lagging_policy(self):
        installed = await self.install(["git"])
        edited = {**installed["configuration_hashes"], "managed-settings.json": "0" * 64}
        self.assertFalse((await self.beat(installed["policy_hash"], edited))["compliant"])
        missing = {k: v for k, v in installed["configuration_hashes"].items() if k != "requirements.toml"}
        self.assertFalse(self.plane.policy_installed(installed, self.plane.installed_hash(installed["control_hash"], missing), missing))

    async def test_added_server_keeps_held_servers_and_defers_new_one(self):
        installed = await self.install(["git"])
        self.usable = ["docs", "git"]  # the administrator approved docs; the device has not fetched yet
        for server, expected in (("git", None), (None, None), ("docs", NEW)):
            self.assertEqual(await self.failure(installed["control_hash"], server), expected)
        self.assertIsNone(await self.failure(installed["control_hash"], mint=True))
        result = await self.beat(installed["policy_hash"], installed["configuration_hashes"])
        self.assertTrue(result["compliant"])
        self.assertNotEqual(result["policy_hash"], installed["policy_hash"])  # the kit reinstalls on its next fetch
        await self.install(["docs", "git"])
        self.assertIsNone(await self.failure(installed["control_hash"], "docs"))

    async def test_removed_server_is_refused_per_call_only(self):
        installed = await self.install(["docs", "git"])
        self.usable = ["git"]  # docs revoked, or its upstream went to ERROR: git must keep working
        self.assertIsNone(await self.failure(installed["control_hash"], "git"))
        self.assertEqual(await self.failure(installed["control_hash"], "docs"), GONE)
        # The header helper mints a new token in this window; refusing it dropped every server of the harness (S4-08).
        self.assertIsNone(await self.failure(installed["control_hash"], mint=True))
        self.assertTrue((await self.beat(installed["policy_hash"], installed["configuration_hashes"]))["compliant"])
        self.assertEqual(self.device["managed_state"], "active")

    async def test_approvals_in_a_row_never_quarantine(self):
        # The device installed the middle policy; the next approval landed before its heartbeat (PJ1·pj3 10-23).
        await self.install(["git"])
        self.usable = ["docs", "git"]
        middle = await self.plane.managed_policy(self.device)
        self.usable = ["docs", "git", "mail"]
        self.assertTrue((await self.beat(middle["policy_hash"], middle["configuration_hashes"]))["compliant"])
        self.assertIsNone(await self.failure(middle["control_hash"], "git"))
        # docs waits for the latest list to be confirmed: fail-closed for the new server only, never for the PC.
        self.assertEqual(await self.failure(middle["control_hash"], "docs"), NEW)
        await self.install(["docs", "git", "mail"])
        self.assertIsNone(await self.failure(middle["control_hash"], "docs"))

    async def test_activation_does_not_move_the_reported_hash(self):
        self.device["managed_state"] = "pending"
        installed = await self.install(["git"])
        self.assertIn("활성화를 기다리는", installed["files"]["managed-settings.json"])
        await self.plane.activate_managed("d", "admin", installed["policy_hash"], "검토한 설치 증거로 활성화합니다.")
        self.device["managed_state"] = "active"
        active = await self.plane.managed_policy(self.device)
        self.assertEqual(active["control_hash"], installed["control_hash"])
        self.assertNotEqual(active["policy_hash"], installed["policy_hash"])  # new guidance is served next
        # The heartbeat racing the activation still carries the waiting rendering: compliant, not quarantined.
        self.assertTrue((await self.beat(installed["policy_hash"], installed["configuration_hashes"]))["compliant"])
        self.assertIsNone(await self.failure(installed["control_hash"], "git"))
        self.assertIsNone(await self.failure(installed["control_hash"], mint=True))

    async def test_activation_still_requires_the_reviewed_state(self):
        self.device["managed_state"] = "pending"
        installed = await self.install(["git"])
        with self.assertRaises(ValueError):
            await self.plane.activate_managed("d", "admin", "0" * 64, "검토한 설치 증거로 활성화합니다.")
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}), self.assertRaises(ValueError):
            await self.plane.activate_managed("d", "admin", installed["policy_hash"], "검토한 설치 증거로 활성화합니다.")

    async def test_tokens_bind_to_control(self):
        installed = await self.install(["git"])
        self.assertEqual(await self.failure("0" * 64, "git"), OLD)
        self.assertEqual(await self.failure(installed["policy_hash"], "git"), OLD)  # the rendering is not the control
        self.usable = ["docs", "git"]
        self.assertIsNone(await self.failure(installed["control_hash"], "git"))

    async def test_kit_installed_before_this_gateway_keeps_working(self):
        # Transition: the device row and its tokens carry the old full-policy hash until the kit's next fetch.
        policy = await self.install(["git"])
        legacy = self.plane.legacy_hash(policy)
        self.device["policy_hash"] = legacy
        self.assertTrue(await self.plane.policy_accepted(self.device))
        self.assertIsNone(await self.failure(legacy, "git"))
        self.assertTrue((await self.beat(legacy, policy["configuration_hashes"]))["compliant"])
        # The next fetch serves the new hash; the kit reinstalls the same files and reports it.
        self.assertTrue((await self.beat(policy["policy_hash"], policy["configuration_hashes"]))["compliant"])
        self.device["policy_hash"] = legacy
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):
            self.assertEqual(await self.failure(legacy, "git"), OLD)

    async def test_local_jobs_follow_control_not_servers(self):
        installed = await self.install(["docs", "git"])
        job = {"device_policy": installed["control_hash"]}
        self.usable = ["git"]  # removed elsewhere: a local job on this PC keeps running
        self.assertTrue(await self.jobs._same_control(job, self.device))
        with patch.dict(os.environ, {"ENDPOINT_GATEWAY_IPS": "100.64.0.9"}):
            self.assertFalse(await self.jobs._same_control(job, self.device))
        self.assertFalse(await self.jobs._same_control({"device_policy": "old"}, self.device))

    def test_no_served_policy_memory_remains(self):
        source = (LAB / "gateway/app/endpoint_plane.py").read_text(encoding="utf-8")
        for gone in ("served_policies", "record_served", "_held_policy", "SERVED_POLICIES"):
            self.assertNotIn(gone, source)
        self.assertNotIn("record_served", (LAB / "gateway/app/main.py").read_text(encoding="utf-8"))
        trigger = (LAB / "gateway/app/local_run_tables.sql").read_text(encoding="utf-8")
        self.assertNotIn("OLD.policy_hash", trigger)


if __name__ == "__main__":
    unittest.main(verbosity=2)
