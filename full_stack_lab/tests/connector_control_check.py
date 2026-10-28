"""하네스 기본 커넥터 통제(10-23 PJ1 실측의 갭): 관리 단말의 수집·보고 경로, 장치 보고의 강제 상태, 비활성/사라짐 구분,
웹 검색 유효값. 입력 문자열은 PJ1에서 받은 실제 출력(claude plugin list, codex features list·config/read·
configRequirements/read·app/installed)이다. DB·소켓·setpriv는 대역이며 집행 증거가 아니다.
실행: python -B -X utf8 full_stack_lab/tests/connector_control_check.py (fastapi·psycopg 없이 AST로 함수만 꺼낸다)
"""
import ast
import asyncio
import importlib.util
import re
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "full_stack_lab"
APP = LAB / "gateway" / "app"
KIT = ROOT / "endpoint-agent"


def extract(path, names, namespace):
    nodes = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
             if getattr(n, "name", None) in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    found = {getattr(n, "name", None) or n.targets[0].id for n in nodes}
    assert found == set(names), set(names) - found
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return SimpleNamespace(**namespace)


PLUGIN_LIST = """Synced from claude.ai:

  ❯ productivity@synced
    Version: 1.3.1
    Path: /home/managed-pj1/.claude/plugins/synced/62ba_4579/productivity
    Status: ✔ loaded

  ❯ engineering@synced
    Version: 1.2.0
    Path: /home/managed-pj1/.claude/plugins/synced/62ba_4579/engineering~g2
    Status: ✔ loaded

  ❯ old@market
    Version: 0.1.0
    Status: ✘ disabled
"""
MCP_LIST = """Checking MCP server health…

claude.ai Notion: https://mcp.notion.com/mcp - ! Needs authentication
plugin:engineering:slack: https://mcp.slack.com/mcp (HTTP) - ! Needs authentication
plugin:pdf-viewer:pdf: npx -y @modelcontextprotocol/server-pdf --stdio - ✔ Connected
filesystem-aa0b61e3: https://gw.example:443/mcp/filesystem-aa0b61e3/ (HTTP) - ✔ Connected
"""
FEATURES = """apps                                     stable             false
browser_use                              stable             false
image_generation                         stable             true
memories                                 stable             false
web_search_cached                        deprecated         false
"""
APPS = [{"id": "asdk_app_69c18c28f1188191bf5b8445c4ab0a2e", "runtimeName": "Notion", "enabled": False, "callable": False},
        {"id": "connector_openai_hotline", "runtimeName": "Hotline", "enabled": False, "callable": False},
        {"id": "bad id!", "runtimeName": "X", "enabled": True}]
MANAGED = {"requirements": {"allowedWebSearchModes": ["disabled"], "featureRequirements": {"apps": False}}}


def linux_agent():
    names = {"origin", "parse_claude_servers", "parse_claude_plugins", "effective_web_search", "parse_codex",
             "collect_inventory", "read_versions", "report_inventory", "CLAUDE_LINE", "PLUGIN_HEAD", "CODEX_FEATURES", "APP_ID", "HARNESS_VERSIONS"}
    namespace = {"re": re, "json": __import__("json"), "urlsplit": __import__("urllib.parse").parse.urlsplit,
                 "subprocess": subprocess, "print": lambda *a, **k: None}
    return extract(KIT / "managed-linux.py", names, namespace)


def kit_module():
    spec = importlib.util.spec_from_file_location("mcpgw_pc_under_test", LAB / "field" / "pc" / "mcpgw_pc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ManagedCollector(unittest.TestCase):
    def test_claude_lines_and_synced_plugins(self):
        agent = linux_agent()
        servers = agent.parse_claude_servers(MCP_LIST, "https://gw.example:443")
        self.assertEqual([(i["kind"], i["name"], i["target"]) for i in servers], [
            ("connector", "claude.ai Notion", "https://mcp.notion.com"),
            ("plugin", "plugin:engineering:slack", "https://mcp.slack.com"),
            ("plugin", "plugin:pdf-viewer:pdf", "stdio")])  # the Gateway's own server is not reported
        plugins = agent.parse_claude_plugins(PLUGIN_LIST)
        self.assertEqual([(i["name"], i["active"]) for i in plugins],
                         [("productivity@synced", True), ("engineering@synced", True), ("old@market", False)])
        self.assertTrue(all(i["kind"] == "plugin" and i["target"] == "stdio" for i in plugins))

    def test_codex_apps_features_and_effective_web_search(self):
        agent = linux_agent()
        self.assertEqual(agent.effective_web_search({"config": {"web_search": "disabled"}}, MANAGED), "disabled")
        # No key anywhere in the user's file: Codex defaults to cached, the managed list leaves only disabled.
        self.assertEqual(agent.effective_web_search({"config": {"web_search": None}}, MANAGED), "disabled")
        self.assertEqual(agent.effective_web_search({"config": {}}, {"requirements": {}}), "cached")
        self.assertEqual(agent.effective_web_search({"config": {"web_search": "live"}}, {"requirements": {"allowedWebSearchModes": ["cached"]}}), "cached")
        items = agent.parse_codex("https://gw.example:443", [], APPS, FEATURES, "disabled")
        self.assertEqual([(i["kind"], i["name"], i.get("active")) for i in items], [
            ("app", "Notion", False), ("app", "Hotline", False), ("feature", "image_generation", None)])
        self.assertIn("web_search", [i["name"] for i in agent.parse_codex("https://gw.example:443", [], [], "", "cached")])

    def test_matches_the_unmanaged_kit(self):
        """Two readers of the same output must agree, or the same item gets two keys."""
        agent, kit = linux_agent(), kit_module()
        with patch.object(kit, "claude_path", return_value="claude"), \
             patch.object(kit, "run", return_value=SimpleNamespace(returncode=0, stdout=MCP_LIST)):
            kit_items = kit.claude_items({"url": "https://gw.example:443"})
        self.assertEqual(kit_items, agent.parse_claude_servers(MCP_LIST, "https://gw.example:443"))
        for config in ({"config": {"web_search": "disabled"}}, {"config": {}}, None, {"config": {"web_search": "live"}}):
            for requirements in (MANAGED, {"requirements": {}}, None):
                self.assertEqual(kit.effective_web_search(config, requirements), agent.effective_web_search(config, requirements))

    def test_kit_reads_the_effective_web_search_not_the_user_file(self):
        """Before: a managed Codex with web_search disabled by requirements was reported as `cached`."""
        kit = kit_module()
        calls = {"config/read": {"config": {"web_search": None}}, "configRequirements/read": MANAGED}
        with patch.object(kit.shutil, "which", return_value="codex"), \
             patch.object(kit, "run", side_effect=lambda cmd, **k: SimpleNamespace(returncode=0, stdout="[]" if "mcp" in cmd else FEATURES)), \
             patch.object(kit, "codex_calls", return_value=calls), \
             patch.object(kit, "codex_rpc", return_value={"apps": []}), \
             patch.object(kit, "codex_config", return_value=Path("/nonexistent/config.toml")):
            names = [i["name"] for i in kit.codex_items({"url": "https://gw.example:443"})]
        self.assertNotIn("web_search", names)
        self.assertIn("image_generation", names)

    def test_a_failed_read_is_not_an_empty_report(self):
        """The Gateway marks every item of a reported harness absent; a harness that could not be read is left out."""
        agent = linux_agent()
        config = {"harnesses": ["claude", "codex"], "gateway_url": "https://gw.example:443"}
        outputs = {("claude", "mcp"): MCP_LIST, ("claude", "plugin"): PLUGIN_LIST, ("codex", "features"): FEATURES,
                   ("claude", "--version"): "2.1.282 (Claude Code)", ("codex", "--version"): "codex-cli 0.157.0"}

        def run_text(config, tool, arguments, timeout=120):
            if tool == "codex" and arguments[0] == "mcp":
                raise ValueError("codex mcp 실패")
            return outputs[(tool, arguments[0])]
        agent.collect_inventory.__globals__.update(
            run_text=run_text, codex_rpc=lambda config, calls: {"app/installed": {"apps": APPS}, "config/read": {"config": {}},
                                                               "configRequirements/read": MANAGED},
            subprocess=subprocess)
        found = agent.collect_inventory(config)
        self.assertEqual(sorted(found), ["claude"])  # codex failed: not reported, so nothing of codex is marked absent
        self.assertEqual(len(found["claude"]), 3 + 3)
        # The versions ride along to the heartbeat's host report (D-239), read as the account like the lists.
        self.assertEqual(agent.collect_inventory.__globals__["HARNESS_VERSIONS"], {"claude": "2.1.282", "codex": "0.157.0"})

        def nothing(config, tool, arguments, timeout=120):
            raise ValueError("실패")
        agent.collect_inventory.__globals__["run_text"] = nothing
        with self.assertRaises(ValueError):
            agent.report_inventory(config)

    def test_report_goes_out_under_the_device_credential_only(self):
        source = (KIT / "managed-linux.py").read_text(encoding="utf-8")
        body = source[source.index("def report_inventory"):source.index("def serve(")]
        self.assertIn('request(config, "/api/endpoint/harness-inventory"', body)
        self.assertNotIn("Authorization", body)
        self.assertNotIn("access_token", body)
        self.assertIn("threading.Thread(target=harness_inventory", source)
        self.assertIn("INVENTORY_EVERY = 6 * 3600", source)


class DeviceReports(unittest.TestCase):
    def test_route_needs_the_device_credential(self):
        tree = ast.parse((APP / "main.py").read_text(encoding="utf-8"))
        route = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and any(
            isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
            and d.args[0].value == "/api/endpoint/harness-inventory" for d in n.decorator_list))
        text = ast.unparse(route)
        self.assertIn("Depends(endpoint_device('inventory'))", text)
        self.assertNotIn("authenticated_user", text)

    def test_device_rows_cannot_be_forged_by_a_kit_report(self):
        connectors = (APP / "connectors.py").read_text(encoding="utf-8")
        self.assertRegex(connectors, r'DEVICE_PREFIX = "device:"')
        pattern = re.search(r'workstation: str = Field\(pattern=r"([^"]+)"\)', connectors).group(1)
        self.assertIsNone(re.match(pattern, "device:ep-1"))

    def test_ingest_stores_under_the_owner_and_the_device_workstation(self):
        recorded = []

        class Connection:
            async def execute(self, sql, params=()):
                recorded.append((" ".join(sql.split())[:40], params))

        class Transaction:
            async def __aenter__(self):
                return Connection()

            async def __aexit__(self, *args):
                return False

        item = SimpleNamespace(harness="claude", kind="plugin", name="productivity@synced", target="stdio", status="✔ loaded", active=True)
        other = SimpleNamespace(harness="codex", kind="feature", name="web_search", target="cached", status="cached", active=True)
        namespace = {"db": SimpleNamespace(transaction=lambda: Transaction()), "groups": AsyncMock(return_value=[]),
                     "policy": lambda g, h: {}, "HarnessItem": object, "gateway_host": lambda: "", "key_of": lambda *a: "k:" + a[2]}
        ingest = extract(APP / "connectors.py", {"ingest"}, namespace).ingest
        result = asyncio.run(ingest("emp-1", "device:ep-1", ["claude"], [item, other]))
        self.assertEqual(result["accepted"], 2)
        self.assertEqual(recorded[0][1], ("emp-1", "device:ep-1", ["claude"]))
        inserts = [r for r in recorded if r[0].startswith("INSERT")]
        self.assertEqual(len(inserts), 1, "an item of a harness the report does not cover is not stored")
        self.assertEqual(inserts[0][1][:3], ("emp-1", "device:ep-1", "claude"))


class ItemState(unittest.TestCase):
    def setUp(self):
        self.ns = extract(APP / "integrations.py", {"endpoint_item_state", "harness_item_state"}, {})
        self.enforced = {"state": "endpoint_enforced", "account_state": "endpoint_enforced", "evidence": "엔드포인트 점검 정상 · 12초 전", "bypass": []}
        self.shared = {"state": "bypass_possible", "account_state": "endpoint_enforced", "evidence": "엔드포인트 점검 정상 · 12초 전",
                       "bypass": ["pj1(sudo) 통제 범위 밖"]}

    def test_a_device_report_is_enforced_as_far_as_its_device(self):
        state = self.ns.harness_item_state
        self.assertEqual(state(self.enforced, False, True, "✔ loaded")[0], "endpoint_enforced")
        self.assertEqual(state(self.shared, False, True, "loaded")[0], "bypass_possible")
        # Before: every harness item was computed with no device, so none could be enforced.
        self.assertEqual(state(None, False, True, "loaded")[0], "bypass_possible")
        self.assertEqual(state(None, True, True, "loaded")[0], "observed_only")

    def test_off_in_the_harness_is_not_vanished(self):
        state = self.ns.harness_item_state
        self.assertEqual(state(None, False, False, "disabled"), ("observed_only", "하네스에서 비활성 보고", ["관리형 엔드포인트 없음"]))
        off = state(self.enforced, False, False, "disabled")
        self.assertEqual(off[0], "endpoint_enforced")
        self.assertTrue(off[1].startswith("하네스에서 비활성 · "))
        for device in (None, self.enforced):
            self.assertEqual(state(device, False, False, "absent")[:2], ("observed_only", "마지막 보고에서 사라짐"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
