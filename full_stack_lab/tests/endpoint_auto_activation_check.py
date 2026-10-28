"""D-239 오프라인 검사: 간편 모드 새 PC는 설치 점검을 통과하면 게이트웨이가 활성화하고, 그 밖은 지금처럼 사람이 한다.

- 간편 모드 + 자동 활성화 켬 + 대기 중 + 점검 통과 → active, 원장 'activated'(처리 auto)
- 자동 활성화 끔, 격리 모드, 보류된 재설치(held_from), 격리된 장치, 점검 실패 → 자동 활성화 없음
- 간편 모드의 필수 점검은 보호된 관리형 설정 하나, 직원 명령 헬퍼는 기록만
DB는 대역이며 실제 PostgreSQL 동작의 증거가 아니다. 저장소 루트: python -B -X utf8 full_stack_lab/tests/endpoint_auto_activation_check.py
"""
import ast
import hashlib
import ipaddress
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

LAB = Path(__file__).resolve().parents[1]
NAMES = {"managed_policy", "managed_platform", "managed_mode", "json_document", "installed_hash", "legacy_hash",
         "policy_installed", "heartbeat", "managed_checks", "MANAGED_CHECKS", "MANAGED_CHECKS_BY_PLATFORM",
         "SIMPLE_CHECKS", "endpoint_settings"}
PACKAGE = "auto_activation"


def load(path, names, namespace):
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    namespace = dict(namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


class AutoActivation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        package = ModuleType(PACKAGE)
        package.pac = SimpleNamespace(servers_for=lambda owner: ["learn"], harness_guidance=lambda owner, servers: "g")
        open_controls = {"claude_tools_denied": [], "claude_connectors": True, "claude_servers_denied": [],
                         "codex_features_off": [], "codex_apps": True, "codex_apps_disabled": []}
        package.connectors = SimpleNamespace(managed_controls=AsyncMock(return_value=open_controls))
        package.registry = SimpleNamespace(server=lambda server: {})
        self.auto = True
        self.events = []

        async def execute(sql, params=None):
            if sql.lstrip().startswith("UPDATE endpoint_agents"):
                # The CASE the statement carries, applied to the row the way PostgreSQL would.
                compliant, automatic, state = params[4], params[5], self.device["managed_state"]
                state = "quarantined" if not compliant else "active" if automatic and state == "pending" else state
                self.stored = state  # the row changes; the caller's snapshot of it does not
                return SimpleNamespace(fetchone=AsyncMock(return_value={"managed_state": state}))
            if "endpoint_managed_events" in sql:
                self.events.append((sql.split("VALUES")[1], params))
            return SimpleNamespace(fetchone=AsyncMock(return_value=None))

        class Transaction:
            async def __aenter__(inner):
                return SimpleNamespace(execute=execute)

            async def __aexit__(inner, *args):
                return False

        def fetch_one(sql, *args, connection=None):
            if "endpoint_settings" in sql:
                return {"auto_activate": self.auto, "updated_by": None, "updated_at": None}
            return {"token": "o"} if "principals" in sql else {"last_value": 3}
        db = SimpleNamespace(fetch_all=AsyncMock(return_value=[{"id": "learn"}]), fetch_one=AsyncMock(side_effect=fetch_one),
                             transaction=Transaction)
        self.plane = load(LAB / "gateway/app/endpoint_plane.py", NAMES,
                          {"__name__": PACKAGE + ".endpoint_plane", "__package__": PACKAGE, "os": os, "urlsplit": urlsplit,
                           "ipaddress": ipaddress, "hashlib": hashlib, "HEARTBEAT_INTERVAL": 60, "HEARTBEAT_SECONDS": 180,
                           "db": db, "datetime": datetime, "UTC": timezone.utc, "Jsonb": lambda v: v, "re": __import__("re")})
        env = patch.dict(os.environ, {"IDP_ISSUER": "https://gateway.example", "ENDPOINT_GATEWAY_IPS": "100.64.0.2",
                                      "MODEL_PROXY_PORT": ""})
        env.start()
        self.addCleanup(env.stop)
        modules = patch.dict(sys.modules, {PACKAGE: package})
        modules.start()
        self.addCleanup(modules.stop)

    def pc(self, mode="simple", state="pending", **detail):
        self.device = {"endpoint_id": "d", "owner_token": "o", "managed_state": state, "status": "active",
                       "device_epoch": "e", "local_username": "emp", "local_uid": 1000, "detail": {"mode": mode, **detail}}
        return self.device

    async def beat(self, checks=None, findings=None):
        policy = await self.plane.managed_policy(self.device)
        checks = checks if checks is not None else dict.fromkeys(self.plane.managed_checks(self.device), True)
        self.events.clear()
        report = await self.plane.heartbeat(self.device, policy["policy_hash"], policy["configuration_hashes"], checks,
                                            user_command_settings=findings)
        self.device = {**self.device, "managed_state": self.stored}
        return report

    def activated(self):
        return [params[2] for values, params in self.events if "'activated'" in values]

    async def test_a_new_simple_pc_that_passes_is_activated_by_the_gateway(self):
        self.pc()
        self.assertEqual(self.plane.managed_checks(self.device), {"protected_configs"})
        report = await self.beat()
        self.assertEqual((report["state"], report["compliant"]), ("active", True))
        self.assertEqual(self.activated(), [{"actor": "auto", "note": "설치 점검 통과로 자동 활성화",
                                             "policy_hash": report["policy_hash"]}])
        self.assertFalse([e for e in self.events if "'quarantined'" in e[0]], "an activation is not logged as quarantine")
        again = await self.beat()  # already active: nothing more is recorded
        self.assertEqual((again["state"], self.activated()), ("active", []))

    async def test_an_employee_command_helper_is_recorded_not_a_quarantine_in_simple_mode(self):
        self.pc()
        report = await self.beat(findings=[{"file": ".claude/settings.json", "keys": ["apiKeyHelper"]}])
        self.assertEqual((report["state"], report["compliant"]), ("active", True))

    async def test_everything_else_waits_for_a_person(self):
        self.auto = False
        self.pc()
        self.assertEqual((await self.beat())["state"], "pending")  # the organization turned it off
        self.auto = True
        self.pc(held_from="old")
        self.assertEqual((await self.beat())["state"], "pending")  # a reinstall of a held PC
        self.pc(mode="isolated")
        self.assertIn("apparmor_enforcing", self.plane.managed_checks(self.device))
        self.assertEqual((await self.beat())["state"], "pending")  # isolated installs keep the administrator's check
        self.pc(state="quarantined")
        self.assertEqual((await self.beat())["state"], "quarantined")  # a passing heartbeat never lifts a quarantine
        self.pc()
        report = await self.beat({"protected_configs": False})
        self.assertEqual((report["state"], report["compliant"]), ("quarantined", False))
        self.assertEqual(self.activated(), [])
        self.pc()
        self.device["detail"].pop("mode")  # a kit before D-239: isolated
        self.assertEqual(self.plane.managed_mode(self.device), "isolated")

    async def test_simple_claude_gets_the_ca_from_the_managed_settings_in_field_mode(self):
        # pj2 10-25: a terminal opened before the install has no CA variable; the managed settings carry it for Claude.
        import json
        def env(**detail):
            return json.loads(policy["files"]["managed-settings.json"]).get("env", {})
        with patch.dict(os.environ, {"MCP_FIELD_MODE": "1"}):
            self.pc()
            policy = await self.plane.managed_policy(self.device)
            self.assertEqual(env(), {"NODE_EXTRA_CA_CERTS": "/usr/local/lib/mcpgw-managed/ca-1000.crt"})
            self.pc(mode="isolated")
            policy = await self.plane.managed_policy(self.device)
            self.assertNotIn("env", json.loads(policy["files"]["managed-settings.json"]))  # its launchers carry the CA
            sid = "S-1-5-21-1-2-3-1001"
            self.pc(local_sid=sid, helper_command='"C:\\Program Files\\MCPGatewayManaged\\python\\python.exe" -I -S '
                                                 '"C:\\Program Files\\MCPGatewayManaged\\managed-windows.py" header')
            policy = await self.plane.managed_policy(self.device)
            self.assertEqual(env(), {"NODE_EXTRA_CA_CERTS": f"C:\\Program Files\\MCPGatewayManaged\\launchers\\{sid}\\root.crt"})
        self.pc()
        self.assertNotIn("env", json.loads((await self.plane.managed_policy(self.device))["files"]["managed-settings.json"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
