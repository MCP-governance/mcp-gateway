"""Synthetic fixtures for Windows event attribution and the OS-only supervisor wiring.

These tests do not inspect the host's Windows Event Logs or prove a real-device connection.
"""
from __future__ import annotations

import importlib.util
import ast
import base64
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("windows_os_observer", ROOT / "endpoint-agent/os-observer-windows.py")
observer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(observer)

AGENT_SPEC = importlib.util.spec_from_file_location("sealing_agent", ROOT / "endpoint-agent/agent.py")
SEALING_AGENT = importlib.util.module_from_spec(AGENT_SPEC)
AGENT_SPEC.loader.exec_module(SEALING_AGENT)

SID = "S-1-5-21-1-2-3-1001"
OTHER_SID = "S-1-5-21-1-2-3-1002"


def app_event(event_id: int = 8004, sid: str = SID, record_id: int = 31, path: str = r"C:\Users\synthetic\denied.exe") -> str:
    channel = "Microsoft-Windows-AppLocker/EXE and DLL"
    return (f'<Event xmlns="{observer.NS["e"]}"><System><Provider Name="Microsoft-Windows-AppLocker"/>'
            f'<EventID>{event_id}</EventID><TimeCreated SystemTime="2026-10-14T00:00:00.000Z"/>'
            f'<EventRecordID>{record_id}</EventRecordID><Channel>{channel}</Channel><Security UserID="{OTHER_SID}"/>'
            f'</System><UserData><RuleAndFileData xmlns="http://schemas.microsoft.com/schemas/event/Microsoft.Windows/1.0.0.0">'
            f'<TargetUser>{sid}</TargetUser><FilePath>{path}</FilePath></RuleAndFileData></UserData></Event>')


class WindowsOSEventTests(unittest.TestCase):
    def test_service_records_partial_snapshot_without_called_process_error(self):
        source = ast.parse((ROOT / 'endpoint-agent/managed-windows.py').read_text(encoding='utf-8'))
        observe = next(node for node in ast.walk(source) if isinstance(node, ast.FunctionDef) and node.name == 'observe')
        class StopRound(Exception):
            pass
        cases = []
        for state in ('success', 'partial'):
            observation = {'inventory': {'state': 'success'}, 'process': {'state': state}, 'network': {'state': 'disabled'}}
            cases.append((SimpleNamespace(stdout=json.dumps({'observation': observation})), state))
        cases += [(SimpleNamespace(stdout='not json'), 'JSONDecodeError'),
                  (SimpleNamespace(stdout='{"observation":{}}'), 'KeyError'),
                  (subprocess.CalledProcessError(1, 'collector'), 'CalledProcessError'),
                  (subprocess.TimeoutExpired('collector', 40), 'TimeoutExpired')]
        for output, expected in cases:
            latest = {}
            run = mock.Mock(side_effect=[output,
                                        SimpleNamespace(stdout='{"channel":"os","state":"disabled"}')])
            namespace = {'json': json, 'sys': SimpleNamespace(executable='python'), 'PROGRAMS': ROOT,
                         'observer_config': ROOT / 'unused-fixture.json', 'subprocess': SimpleNamespace(
                             run=run, SubprocessError=subprocess.SubprocessError), 'latest': latest,
                         'lock': threading.Lock(), 'time': SimpleNamespace(sleep=mock.Mock(side_effect=StopRound))}
            exec(compile(ast.Module(body=[observe], type_ignores=[]), '<service-observe>', 'exec'), namespace)
            with self.assertRaises(StopRound):
                namespace['observe']()
            self.assertEqual(latest['inventory'], expected)
            self.assertEqual(latest['os']['state'], 'disabled')
            self.assertTrue(run.call_args_list[0].kwargs['check'])

    def test_exact_managed_sid_yields_safe_event_contract(self):
        row, issue = observer.parse_event(app_event(), observer.CHANNELS[1][0], "applocker", SID)
        self.assertIsNone(issue)
        self.assertEqual(row["kind"], "execution-denied")
        self.assertEqual(row["event_id"], f"windows:{observer.CHANNELS[1][0]}:31")
        self.assertEqual(row["details"]["application"], "denied.exe")
        self.assertNotIn(SID, str(row))
        self.assertNotIn("synthetic", str(row))
        self.assertLessEqual(len(row["details"]), 12)

    def test_foreign_sid_and_group_like_other_sid_are_excluded(self):
        row, issue = observer.parse_event(app_event(sid=OTHER_SID), observer.CHANNELS[1][0], "applocker", SID)
        self.assertIsNone(row)
        self.assertIsNone(issue)

    def test_wfp_without_explicit_subject_sid_is_not_attributed_by_pid(self):
        xml = (f'<Event xmlns="{observer.NS["e"]}"><System><Provider Name="{observer.PROVIDER_SECURITY}"/>'
               '<EventID>5157</EventID><TimeCreated SystemTime="2026-10-14T00:00:00Z"/>'
               '<EventRecordID>32</EventRecordID><Channel>Security</Channel></System><EventData>'
               '<Data Name="ProcessID">4212</Data><Data Name="Application">C:\\synthetic\\x.exe</Data>'
               '<Data Name="DestAddress">127.0.0.1</Data></EventData></Event>')
        row, issue = observer.parse_event(xml, "Security", "wfp", SID)
        self.assertIsNone(row)
        self.assertEqual(issue, "sid_unavailable")

    def test_wrong_provider_channel_or_malformed_xml_is_rejected(self):
        row, issue = observer.parse_event(app_event().replace("Microsoft-Windows-AppLocker", "OtherProvider"),
                                           observer.CHANNELS[1][0], "applocker", SID)
        self.assertIsNone(row)
        self.assertEqual(issue, "query_failed")
        row, issue = observer.parse_event("<Event>", observer.CHANNELS[1][0], "applocker", SID)
        self.assertIsNone(row)
        self.assertEqual(issue, "query_failed")

    def test_collection_uses_read_only_event_queries_and_separate_status(self):
        self.assertIn("Get-WinEvent", observer.POWERSHELL_QUERY)
        self.assertNotRegex(observer.POWERSHELL_QUERY, r"(?i)Auditpol\\s+/set|Set-.*Audit|Enable.*Audit")
        self.assertIn("/api/endpoint/os-events", (ROOT / "endpoint-agent/os-observer-windows.py").read_text())
        managed = (ROOT / "endpoint-agent/managed-windows.py").read_text(encoding="utf-8")
        self.assertIn('"os_observer": os_observer', managed)
        self.assertIn('"config_inventory": inventory_status', managed)
        self.assertIn('"ENDPOINT_PROCESS_SID": config["sid"]', managed)
        self.assertIn('"ENDPOINT_PROCESS_SCAN": "1"', managed)

    @unittest.skipUnless(os.name == "nt", "PowerShell parser check requires Windows")
    def test_powershell_is_syntactically_valid_without_executing_it(self):
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        if not executable.is_file():
            self.skipTest("Windows PowerShell is unavailable")
        encoded = base64.b64encode(observer.POWERSHELL_QUERY.encode("utf-8")).decode("ascii")
        check = ("$src=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')); "
                 "$t=$null; $e=$null; "
                 "[System.Management.Automation.Language.Parser]::ParseInput($src,[ref]$t,[ref]$e) | Out-Null; "
                 "if($e.Count){$e | ForEach-Object { Write-Error $_.Message }; exit 1}")
        done = subprocess.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", check],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_failed_event_batch_does_not_advance_channel_cursor(self):
        class FakeAgent:
            def __init__(self, fail):
                self.fail = fail
                self.event_calls = 0
                self.status = []

            def validate_gateway(self):
                return None

            def seal_os_event(self, *args):
                return SEALING_AGENT.seal_os_event(*args)

            def endpoint_id(self):
                return "endpoint-synthetic"

            def call(self, method, path, body):
                if path.endswith("/os-events"):
                    self.event_calls += 1
                    if self.fail:
                        raise OSError("synthetic delivery failure")
                if path.endswith("/observation-status"):
                    self.status.append(body)
                return {"accepted": len(body.get("events", []))}

        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "observer.json"
            config_path.write_text(json.dumps({"ENDPOINT_MANAGED_SID": SID}), encoding="utf-8")
            target_channel = observer.CHANNELS[1][0]

            def query(config, channel, ids, cursor):
                if cursor is None:
                    return {"state": "success", "newest": 10, "oldest": 1, "events": []}
                if channel == target_channel:
                    return {"state": "success", "newest": 11, "oldest": 1,
                            "events": [app_event(record_id=11)]}
                return {"state": "success", "newest": 10, "oldest": 1, "events": []}

            failing = FakeAgent(fail=True)
            with mock.patch.object(observer, "_load_agent", return_value=failing), \
                 mock.patch.object(observer, "_powershell", side_effect=query):
                observer.collect(config_path)  # first run establishes a live-only baseline
                result = observer.collect(config_path)
            self.assertEqual(result["state"], "partial")
            cursor_path = config_path.with_suffix(".os-cursor.json")
            cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
            self.assertEqual(cursor[target_channel]["record_id"], 10)
            self.assertEqual(failing.status[-1]["error_code"], "delivery_failed")

            succeeding = FakeAgent(fail=False)
            with mock.patch.object(observer, "_load_agent", return_value=succeeding), \
                 mock.patch.object(observer, "_powershell", side_effect=query):
                observer.collect(config_path)
            cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
            self.assertEqual(cursor[target_channel]["record_id"], 11)
            self.assertEqual(succeeding.event_calls, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
