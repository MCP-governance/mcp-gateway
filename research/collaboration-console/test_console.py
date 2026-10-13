import concurrent.futures
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SPEC = importlib.util.spec_from_file_location("console", Path(__file__).with_name("console.py"))
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = console.EventLog(Path(self.tmp.name) / "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_concurrent_producers_preserves_jsonl_and_redacts(self):
        def append(number):
            self.log.append("Codex", "message", "audit", "running", f"record {number}: API_KEY=abc-secret-value")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(append, range(32)))
        snapshot = self.log.snapshot()
        self.assertEqual(len(snapshot["events"]), 32)
        self.assertEqual(snapshot["malformed_records"], 0)
        self.assertNotIn("abc-secret-value", self.log.path.read_text())
        self.assertEqual(len(self.log.snapshot(after=31)["events"]), 1)

    def test_reject_invalid_and_skip_malformed_records(self):
        with self.assertRaises(ValueError):
            self.log.append("attacker", "message", "audit", "running", "invalid")
        self.log.append("Codex", "task", "audit", "running", "Analyzing")
        with open(self.log.path, "ab") as stream:
            stream.write(b'not-json\n{"incomplete":')
        snapshot = self.log.snapshot()
        self.assertEqual(snapshot["malformed_records"], 1)
        self.assertEqual(snapshot["cursor"], 2)
        self.assertEqual(snapshot["tasks"][0]["state"], "running")
        self.log.append("Claude", "task", "claude-audit", "running", "New append after partial record")
        self.assertEqual(self.log.snapshot()["malformed_records"], 2)
        self.assertEqual(len(self.log.snapshot()["events"]), 2)

    def test_credentials_and_hidden_thinking_never_recorded(self):
        seen = set()
        console.visible_claude_event({"type": "assistant", "message": {"id": "m1", "content": [
            {"type": "thinking", "thinking": "private thoughts"},
            {"type": "text", "text": "Bearer abcdefg TOKEN=secret"},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"password": "tool-secret"}}
        ]}}, self.log, "claude-audit", seen, "session1")
        stored = self.log.path.read_text()
        self.assertNotIn("private thoughts", stored)
        self.assertNotIn("tool-secret", stored)
        self.assertNotIn("abcdefg", stored)
        self.assertNotIn("TOKEN=secret", stored)
        self.assertIn("Read", stored)
        self.assertEqual(console.redact("https://name:password@host/?access_token=secret"), "https://[REDACTED]@host/?access_token=[REDACTED]")
        self.assertEqual(console.redact('"api_key": "example-secret"'), '"api_key": [REDACTED]')

    def test_shared_task_preserves_both_agent_owners(self):
        self.log.append("Codex", "task", "shared-audit", "running", "Implementation review")
        self.log.append("Claude", "task", "shared-audit", "running", "Independent review")
        self.log.append("Claude", "task", "shared-audit", "completed", "Review complete")
        tasks = self.log.snapshot()["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertEqual({task["author"]: task["state"] for task in tasks}, {"Codex": "running", "Claude": "completed"})

    def test_claude_resume_preserves_native_uuid_and_reports_turn_limit(self):
        native_id = "fce4ba17-77ff-4039-b963-0a810e681142"
        fake = Path(self.tmp.name) / "test_cli.py"
        fake.write_text("import json, sys\nrequest=sys.stdin.read()\n"
                        "print(json.dumps({'type':'system','subtype':'init','model':'claude-sonnet-5-5','session_id':" + repr(native_id) + "}), flush=True)\n"
                        "print(json.dumps({'type':'system','subtype':'status','model':'claude-sonnet-5-5','session_id':" + repr(native_id) + "}), flush=True)\n"
                        "print(json.dumps({'type':'result','subtype':'error_max_turns','is_error':True,'session_id':" + repr(native_id) + ", 'errors':['Maximum turns exceeded'], 'result':json.dumps(sys.argv[1:])}), flush=True)\n", encoding="utf-8")
        prefix = Path(self.tmp.name) / "prefix.json"
        prefix.write_text(json.dumps([sys.executable, str(fake)]), encoding="utf-8")
        prompt = Path(self.tmp.name) / "request.txt"
        prompt.write_text("Continue the same code review", encoding="utf-8")
        args = SimpleNamespace(log=str(self.log.path), prompt_file=str(prompt), prefix_file=str(prefix),
                               executable=None, task_id="test-audit", resume=native_id, allowed_tools="Read,Grep,Glob",
                               max_turns=15, permission_mode="plan", cwd=self.tmp.name)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(console.run_claude(args), 1)
        self.assertEqual(output.getvalue().count("CLAUDE_NATIVE_SESSION="), 1)
        events = self.log.snapshot()["events"]
        failure = events[-1]
        self.assertEqual(failure["state"], "failed")
        self.assertIn("error_max_turns", failure["body"])
        self.assertNotIn("완료 결과 레코드 없음", failure["body"])
        cli_args = json.loads(next(event["body"] for event in events if event["kind"] == "message" and event["author"] == "Claude"))
        self.assertEqual(cli_args[cli_args.index("--resume") + 1], native_id)
        self.assertEqual(cli_args[cli_args.index("--tools") + 1], "Read,Grep,Glob")
        metadata = json.loads((Path(self.tmp.name) / "test-audit.session.json").read_text())
        self.assertEqual(metadata["native_session_id"], native_id)
        self.assertNotEqual(metadata["run_session_id"], native_id)
        self.assertEqual(metadata["state"], "failed")
        self.assertEqual(metadata["result_subtype"], "error_max_turns")

    def test_runtime_synthetic_message_is_visible_but_real_alternate_model_stops(self):
        native_id = "fce4ba17-77ff-4039-b963-0a810e681142"
        prompt = Path(self.tmp.name) / "request.txt"
        prompt.write_text("Review current code", encoding="utf-8")
        for message_model, expected_code in (("<synthetic>", 0), ("claude-opus-5-5", 1)):
            fake = Path(self.tmp.name) / "model_cli.py"
            records = [{"type": "system", "subtype": "init", "model": console.MODEL, "session_id": native_id},
                       {"type": "assistant", "message": {"id": "runtime1", "model": message_model,
                         "content": [{"type": "text", "text": "Runtime notice: Write permission unavailable"}]}},
                       {"type": "result", "subtype": "success", "is_error": False, "session_id": native_id}]
            fake.write_text("import sys\nsys.stdin.read()\n" + "\n".join("print(" + repr(json.dumps(record)) + ", flush=True)" for record in records), encoding="utf-8")
            prefix = Path(self.tmp.name) / "prefix.json"
            prefix.write_text(json.dumps([sys.executable, str(fake)]), encoding="utf-8")
            path = Path(self.tmp.name) / ("synthetic.jsonl" if expected_code == 0 else "wrong-model.jsonl")
            args = SimpleNamespace(log=str(path), prompt_file=str(prompt), prefix_file=str(prefix),
                                   executable=None, task_id="model-check", resume=None, allowed_tools="Read,Grep,Glob",
                                   max_turns=15, permission_mode="plan", cwd=self.tmp.name)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(console.run_claude(args), expected_code)
            events = console.EventLog(path).snapshot()["events"]
            if expected_code == 0:
                self.assertTrue(any("Write permission unavailable" in event["body"] for event in events))
                self.assertFalse(any("모델 불일치" in event["body"] for event in events))
            else:
                self.assertEqual(events[-1]["state"], "failed")
                self.assertTrue(any("claude-opus-5-5" in event["body"] and "모델 불일치" in event["body"] for event in events))

    def test_http_read_only_fixed_assets_local_host_and_redacted_data(self):
        attack = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
        self.log.append("Claude", "message", "audit", "running", attack)
        server = console.make_server(0, self.log)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/events") as response:
                data = json.loads(response.read())
                self.assertEqual(data["events"][0]["body"], attack)
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            for path, status in (("/../../console.py", 404), ("/runtime/events.jsonl", 404), ("/api/events?after=-1", 400)):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, status)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/", headers={"Host": "evil.example"}))
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/events", headers={"Origin": "https://evil.example"}))
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/events", data=b'{}', method="POST"))
            self.assertEqual(error.exception.code, 405)
            with urlopen(base + "/app.js") as response:
                source = response.read().decode()
                self.assertNotIn("innerHTML", source)
                self.assertIn("element.textContent = text", source)
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
