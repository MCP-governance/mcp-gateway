import concurrent.futures
import csv
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SPEC = importlib.util.spec_from_file_location("console", Path(__file__).with_name("console.py"))
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)
import sheet_pull


class SheetSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "sheet-source.json"
        self.csv = self.root / "wbs.csv"
        self.snapshot = json.loads(console.WBS_SNAPSHOT.read_text(encoding="utf-8"))
        self.headers, self.rows = sheet_pull.parse_csv(
            (sheet_pull.WIKI / "sheet/tabs/02-wbs.csv").read_text(encoding="utf-8"), "wbs")
        self.write_csv()
        self.configure()
        self.source = sheet_pull.SheetSource(self.config)

    def write_csv(self, rows=None, headers=None):
        with self.csv.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers or self.headers)
            writer.writeheader()
            writer.writerows(self.rows if rows is None else rows)

    def configure(self, **values):
        self.config.write_text(json.dumps({"wbs_csv": self.csv.as_uri(),
                                          "sheet_url": "https://docs.google.com/spreadsheets/d/example/edit",
                                          **values}), encoding="utf-8")

    def test_overlay_by_header_and_id_preserves_evidence_and_adds_goals(self):
        row = self.rows[0]
        row.update({"구현": "0.5", "회귀": "", "배포": "1", "실기기": "0", "검수": "0",
                    "담당": "담당자", "진행 메모": "쉼표, 줄바꿈\n메모", "계획 일정": "10/20"})
        new = {**row, "ID": "G11.01", "목표": "G11", "목표명": "추가 목표", "작업": "추가 작업",
               "완료 조건": "완료 확인", "남은 일": "후속 확인"}
        self.write_csv([new, row], list(reversed(self.headers)))
        rows, meta = self.source.get("wbs")
        data, changed = sheet_pull.overlay_wbs(self.snapshot, rows)
        old = data["items"][0]
        self.assertEqual(old["id"], row["ID"])
        self.assertEqual(old["stage_scores"]["regression"], 0)
        self.assertEqual((old["progress"], old["status"]), (30, "일부 구현"))
        self.assertEqual((old["owner"], old["memo"], old["planned_schedule"]),
                         ("담당자", "쉼표, 줄바꿈\n메모", "10/20"))
        self.assertEqual(old["evidence"], self.snapshot["items"][0]["evidence"])
        self.assertNotIn("owner", self.snapshot["items"][0])
        self.assertEqual(data["items"][-1]["title"], "추가 작업")
        self.assertEqual(data["items"][-1]["completion_condition"], "완료 확인")
        self.assertEqual(data["items"][-1]["known_gap"], "후속 확인")
        self.assertEqual(data["goals"][-1]["title"], "추가 목표")
        self.assertEqual(data["summary"]["total"], len(self.snapshot["items"]) + 1)
        self.assertEqual(sum(data["summary"]["status_counts"].values()), data["summary"]["total"])
        self.assertIn(row["ID"], changed)
        self.assertEqual(meta["source"], "sheet")
        self.assertIsNone(meta["error"])
        self.assertIsNotNone(meta["fetched_at"])

    def test_all_status_rules_and_summary(self):
        rows = []
        for index, scores in enumerate(((0, 1, 1, 1, 1), (0.5, 0, 0, 0, 0),
                                        (1, 1, 1, 1, 1), (1, 0, 0, 0, 0))):
            row = {**self.rows[0], "ID": f"G01.0{index + 1}"}
            row.update(dict(zip(sheet_pull.STAGES, map(str, scores))))
            rows.append(row)
        data, _ = sheet_pull.overlay_wbs({"items": [], "goals": []}, rows)
        self.assertEqual([item["status"] for item in data["items"]], list(sheet_pull.STATUSES))
        self.assertEqual([item["progress"] for item in data["items"]], [80, 10, 100, 20])
        self.assertEqual(data["summary"]["progress"], 52.5)
        self.assertEqual(data["summary"]["complete"], 1)
        self.assertEqual(data["goals"][0]["progress"], 52.5)

    def test_cache_expiry_failure_stale_fallback_and_recovery(self):
        with patch.object(sheet_pull.time, "monotonic", return_value=1000):
            first, initial = self.source.get("wbs")
        self.csv.unlink()
        with patch.object(sheet_pull.time, "monotonic", return_value=1299):
            self.assertEqual(self.source.get("wbs"), (first, initial))
        with patch.object(sheet_pull.time, "monotonic", return_value=1300):
            stale, failed = self.source.get("wbs")
        self.assertEqual(stale, first)
        self.assertEqual(failed["source"], "sheet")
        self.assertEqual(failed["fetched_at"], initial["fetched_at"])
        self.assertTrue(failed["error"])
        self.rows[0]["담당"] = "변경"
        self.write_csv()
        with patch.object(sheet_pull.time, "monotonic", return_value=1599):
            self.assertEqual(self.source.get("wbs"), (stale, failed))
        with patch.object(sheet_pull.time, "monotonic", return_value=1600):
            fresh, meta = self.source.get("wbs")
        self.assertEqual(fresh[0]["담당"], "변경")
        self.assertIsNone(meta["error"])

    def test_disabled_bad_config_first_failure_and_changed_url(self):
        self.config.unlink()
        self.assertEqual(self.source.get("wbs")[1]["source"], "snapshot")
        self.assertIsNone(self.source.get("wbs")[1]["error"])
        self.configure(wbs_csv="")
        self.assertIsNone(self.source.get("wbs")[0])
        self.config.write_text("[]", encoding="utf-8")
        self.assertTrue(self.source.get("wbs")[1]["error"])
        self.configure()
        self.source.get("wbs")
        self.configure(wbs_csv=(self.root / "missing.csv").as_uri())
        rows, meta = self.source.get("wbs")
        self.assertIsNone(rows)
        self.assertEqual(meta["source"], "snapshot")
        self.assertIsNone(meta["fetched_at"])
        self.assertTrue(meta["error"])

    def test_invalid_csv_does_not_replace_cache(self):
        first, _ = self.source.get("wbs")
        for invalid in ("2", "NaN", "-0.5", "잘못된 값"):
            with self.subTest(invalid=invalid):
                self.rows[0]["구현"] = invalid
                self.write_csv()
                self.source.cache[("wbs", self.csv.as_uri())]["checked"] = 0
                rows, meta = self.source.get("wbs")
                self.assertEqual(rows, first)
                self.assertTrue(meta["error"])
        self.csv.write_text("<html>not CSV</html>", encoding="utf-8")
        source = sheet_pull.SheetSource(self.config)
        self.assertIsNone(source.get("wbs")[0])
        with self.assertRaises(ValueError):
            sheet_pull.parse_csv("ID,ID\nx,x", "wbs")
        with self.assertRaises(ValueError):
            sheet_pull.parse_csv(self.headers_text([self.rows[1], self.rows[1]]), "wbs")

    def headers_text(self, rows):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, self.headers)
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()

    def test_concurrent_requests_fetch_once_with_timeout(self):
        with patch.object(sheet_pull, "fetch_csv", wraps=sheet_pull.fetch_csv) as fetch:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: self.source.get("wbs"), range(16)))
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(all(result == results[0] for result in results))
        with patch.object(sheet_pull, "urlopen", side_effect=TimeoutError("timed out")) as fetch:
            source = sheet_pull.SheetSource(self.config)
            rows, meta = source.get("wbs")
            fetch.assert_called_once_with(self.csv.as_uri(), timeout=15)
            self.assertIsNone(rows)
            self.assertIn("timed out", meta["error"])

    def test_wbs_and_backlog_endpoints_with_snapshot_fallback(self):
        self.configure(backlog_csv=(sheet_pull.WIKI / "sheet/tabs/03-backlog.csv").as_uri())
        log = console.EventLog(self.root / "events.jsonl")
        server = console.make_server("127.0.0.1", 0, log)
        server.sheet_source = self.source
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/wbs") as response:
                data = json.load(response)
            self.assertEqual(data["sheet"]["source"], "sheet")
            self.assertEqual(data["items"][0]["stage_scores"], sheet_pull.scores_for(self.rows[0]))
            with urlopen(base + "/api/backlog") as response:
                backlog = json.load(response)
            self.assertEqual(backlog[0]["ID"], "WIKI-01")
            self.configure(wbs_csv=(self.root / "missing.csv").as_uri(), backlog_csv="")
            with urlopen(base + "/api/wbs") as response:
                data = json.load(response)
            self.assertEqual(data["items"], self.snapshot["items"])
            self.assertEqual(data["sheet"]["source"], "snapshot")
            self.assertTrue(data["sheet"]["error"])
            with urlopen(base + "/api/backlog") as response:
                self.assertEqual(json.load(response), backlog)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = console.EventLog(Path(self.tmp.name) / "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_gemini_recipient_and_reply_preserve_shared_thread(self):
        self.log.append("Codex", "message", "DEV-81", "running", "Review fixed commit", recipient="Gemini")
        self.log.append("Gemini", "message", "DEV-81", "completed", "ACK DEV-81; finding and evidence", recipient="Codex", reply_to=1)
        events = self.log.snapshot()["events"]
        self.assertEqual(events[0]["to"], "Gemini")
        self.assertEqual(events[1]["reply_to"], 1)
        self.assertEqual(events[1]["author"], "Gemini")
        with self.assertRaises(ValueError):
            self.log.append("Codex", "message", "DEV-81", "running", "bad recipient", recipient="external")
        with self.assertRaises(ValueError):
            self.log.append("Codex", "message", "DEV-81", "running", "bad reply", reply_to=True)

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
        server = console.make_server("127.0.0.1", 0, self.log)
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

    def test_allowed_hosts_trusts_localhost_and_the_bind_host_only(self):
        self.assertEqual(console.allowed_hosts_for("127.0.0.1", 1000), {"127.0.0.1:1000", "localhost:1000"})
        self.assertEqual(console.allowed_hosts_for("100.111.15.33", 1000),
                         {"127.0.0.1:1000", "localhost:1000", "100.111.15.33:1000"})

    def test_wbs_endpoint_serves_the_snapshot_file_fresh_each_request(self):
        snapshot = Path(self.tmp.name) / "snapshot.json"
        snapshot.write_text('{"items": [], "as_of": "v1"}', encoding="utf-8")
        previous = console.WBS_SNAPSHOT
        console.WBS_SNAPSHOT = snapshot
        try:
            server = console.make_server("127.0.0.1", 0, self.log)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/api/wbs") as response:
                    self.assertEqual(json.loads(response.read())["as_of"], "v1")
                snapshot.write_text('{"items": [], "as_of": "v2"}', encoding="utf-8")
                with urlopen(base + "/api/wbs") as response:
                    self.assertEqual(json.loads(response.read())["as_of"], "v2")
                snapshot.unlink()
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + "/api/wbs")
                self.assertEqual(error.exception.code, 503)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        finally:
            console.WBS_SNAPSHOT = previous


FIXTURES = Path(__file__).with_name("fixtures")
E13 = Path(__file__).resolve().parents[1] / "llm-wiki/analysis/pj1-local-mcp-e13/runs/e13-control-03/C1-stdio-direct.events.jsonl"
NATIVE = "fce4ba17-77ff-4039-b963-0a810e681142"


def fixture_lines(name):
    return [line for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if line.strip()]


class RunRecordTests(unittest.TestCase):
    """What the console shows per run comes from the CLI's own output: requested model and effort, the model the provider
    answered with, a turn error, a usage-limit error, a task failure, zero tool calls, and what the gateway holds.
    claude-auth-failure.jsonl and codex-model-rejected.jsonl are real CLI output (captured 2026-10-15; the first has its
    init record trimmed to four keys and the hook records dropped). The usage-limit streams and the Codex success
    streams are built from the field names of real records and say so."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.prompt = self.dir / "request.txt"
        self.prompt.write_text("Review the current code", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def fake_cli(self, lines, exit_code=0, name="cli"):
        script = self.dir / f"{name}.py"
        script.write_text("import json, sys\nsys.stdin.read()\nopen(%r, 'w').write(json.dumps(sys.argv[1:]))\n"
                          "for line in json.loads(%r):\n    print(line, flush=True)\nraise SystemExit(%d)\n"
                          % (str(self.dir / f"{name}.argv"), json.dumps(lines), exit_code), encoding="utf-8")
        prefix = self.dir / f"{name}.json"
        prefix.write_text(json.dumps([sys.executable, str(script)]), encoding="utf-8")
        return prefix

    def args(self, prefix, **extra):
        values = dict(log=str(self.dir / "events.jsonl"), prompt_file=str(self.prompt), prefix_file=str(prefix), executable=None,
                      task_id="run-check", resume=None, allowed_tools="Read,Grep,Glob", max_turns=15, permission_mode="plan",
                      cwd=self.tmp.name, model="gpt-test-model", effort="high", sandbox="read-only")
        values.update(extra)
        return SimpleNamespace(**values)

    def run_agent(self, runner, prefix, **extra):
        with redirect_stdout(io.StringIO()):
            code = runner(self.args(prefix, **extra))
        runs = console.RunLog(self.dir / "runs.jsonl").snapshot()["runs"]
        return code, runs[-1]

    def test_real_claude_authentication_failure_is_a_turn_error_without_a_model_or_tool_call(self):
        code, run = self.run_agent(console.run_claude, self.fake_cli(fixture_lines("claude-auth-failure.jsonl")))
        self.assertEqual(code, 1)
        self.assertEqual((run["outcome"], run["error"]["kind"], run["error"]["code"]), ("turn_error", "turn_error", "authentication_failed"))
        self.assertEqual(run["requested"], {"model": console.MODEL, "effort": console.EFFORT})
        self.assertEqual(run["observed"]["models"], [])
        self.assertEqual(run["model_check"], "unreported")
        self.assertEqual(run["cli_model"], "bogus-model-x")  # what the CLI echoed; never promoted to a provider answer
        self.assertEqual((run["tool_calls"], run["no_tool_call"]), (0, True))
        self.assertEqual(run["gateway"]["state"], "unverified")
        self.assertNotIn("제공자 응답 모델 확인", self.dir.joinpath("events.jsonl").read_text(encoding="utf-8"))

    def test_the_model_the_cli_echoes_at_init_is_not_a_provider_answer(self):
        lines = fixture_lines("claude-auth-failure.jsonl")
        lines[0] = json.dumps({"type": "system", "subtype": "init", "model": console.MODEL, "session_id": NATIVE})
        code, run = self.run_agent(console.run_claude, self.fake_cli(lines))
        self.assertEqual((run["cli_model"], run["model_check"], run["observed"]["models"]), (console.MODEL, "unreported", []))
        self.assertNotIn("제공자 응답 모델 확인", self.dir.joinpath("events.jsonl").read_text(encoding="utf-8"))

    def test_real_claude_success_log_confirms_the_model_from_the_provider_answer_and_counts_tool_calls(self):
        if not E13.exists():
            self.skipTest("real PJ1 log not in this checkout")
        run = console.Run("Claude", "t", "t:1", console.MODEL, console.EFFORT)
        for line in E13.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("{"):
                run.observe_claude(json.loads(line))
        run.finish(0)
        record = run.record("final")
        self.assertEqual((record["outcome"], record["model_check"]), ("completed", "confirmed"))
        self.assertIn(console.MODEL, record["observed"]["models"])
        self.assertEqual(record["observed"]["source"], "assistant.message.model")
        self.assertGreater(record["tool_calls"], 0)
        self.assertFalse(record["no_tool_call"])
        self.assertEqual(record["rate_limit"]["status"], "allowed_warning")  # a warning is not a limit error
        self.assertGreater(record["usage"]["output_tokens"], 0)

    def test_a_provider_answer_from_another_model_is_a_mismatch_not_a_confirmation(self):
        lines = [json.dumps({"type": "assistant", "message": {"id": "m1", "model": "claude-other-model", "content": [{"type": "text", "text": "hi"}]}})]
        code, run = self.run_agent(console.run_claude, self.fake_cli(lines))
        self.assertEqual((code, run["outcome"], run["model_check"]), (1, "model_mismatch", "mismatch"))
        self.assertEqual(run["observed"]["models"], ["claude-other-model"])

    def test_usage_limit_is_told_apart_from_other_turn_errors(self):
        notice = {"type": "assistant", "message": {"id": "m", "model": "<synthetic>", "content": [{"type": "text", "text": "You've hit your usage limit. Try again at 9:01 PM."}]},
                  "error": "rate_limit", "is_api_error_message": True}
        failed = {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 429, "terminal_reason": "api_error",
                  "result": "You've hit your usage limit. Try again at 9:01 PM.", "modelUsage": {}}
        cases = {
            "assistant error rate_limit": [notice, {**failed, "api_error_status": None}],
            "status 429 on the result": [{**notice, "error": "unknown"}, failed],
            "rejected rate-limit event": [{"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour"}},
                                          {**failed, "api_error_status": None, "result": "stopped"}],
        }
        for name, records in cases.items():
            with self.subTest(name):
                code, run = self.run_agent(console.run_claude, self.fake_cli([json.dumps(r) for r in records], name="limit"))
                self.assertEqual((code, run["outcome"], run["error"]["kind"]), (1, "usage_limit", "usage_limit"))
                self.assertEqual(run["model_check"], "unreported")
                self.assertTrue(run["no_tool_call"])

    def test_task_failure_means_the_process_failed_without_a_provider_error(self):
        code, run = self.run_agent(console.run_claude, self.fake_cli(["not json at all"], exit_code=3))
        self.assertEqual((code, run["outcome"], run["error"]["code"]), (3, "task_failed", "3"))
        missing = self.dir / "missing.json"
        missing.write_text(json.dumps([str(self.dir / "no-such-cli")]), encoding="utf-8")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(console.run_claude(self.args(missing)), 1)
        self.assertEqual(console.RunLog(self.dir / "runs.jsonl").snapshot()["runs"][-1]["outcome"], "task_failed")

    def test_real_codex_model_rejection_is_a_turn_error_and_reports_no_provider_model(self):
        code, run = self.run_agent(console.run_codex, self.fake_cli(fixture_lines("codex-model-rejected.jsonl"), exit_code=1, name="codex"))
        self.assertEqual(code, 1)
        self.assertEqual((run["outcome"], run["error"]["kind"], run["requested"]), ("turn_error", "turn_error", {"model": "gpt-test-model", "effort": "high"}))
        self.assertEqual((run["observed"]["models"], run["model_check"]), ([], "unreported"))
        self.assertTrue(any("Model metadata" in warning for warning in run["warnings"]))
        self.assertEqual((run["tool_calls"], run["no_tool_call"], run["native_session_id"]), (0, True, "01a13e37-caf3-7c20-a23d-28fb02f2e4b7"))
        argv = json.loads((self.dir / "codex.argv").read_text())
        self.assertEqual(argv[:3], ["exec", "--json", "--skip-git-repo-check"])
        self.assertEqual(argv[argv.index("-m") + 1], "gpt-test-model")
        self.assertEqual(argv[argv.index("-c") + 1], "model_reasoning_effort=high")
        self.assertEqual((argv[argv.index("-s") + 1], argv[-1]), ("read-only", "-"))

    def test_codex_passes_worktree_with_dash_c_and_resumes_a_native_thread(self):
        thread = "01a13e37-caf3-7c20-a23d-28fb02f2e4b7"
        code, run = self.run_agent(console.run_codex, self.fake_cli(fixture_lines("codex-model-rejected.jsonl"), exit_code=1, name="codex"),
                                   resume=thread)
        argv = json.loads((self.dir / "codex.argv").read_text())
        self.assertEqual(argv[:2], ["exec", "resume"])
        self.assertEqual(argv[2], thread)
        # codex exec resume rejects -s/-C; the worktree is the subprocess cwd instead.
        self.assertNotIn("-C", argv)
        self.assertNotIn("-s", argv)

    def test_codex_resume_rejects_a_value_that_is_not_a_native_thread_id(self):
        with self.assertRaises(ValueError):
            console.run_codex(self.args(self.fake_cli(["{}"], name="codex"), resume="not a thread id; rm -rf /"))

    def test_codex_without_resume_has_no_resume_argv(self):
        code, run = self.run_agent(console.run_codex, self.fake_cli(fixture_lines("codex-model-rejected.jsonl"), exit_code=1, name="codex"))
        argv = json.loads((self.dir / "codex.argv").read_text())
        self.assertNotIn("resume", argv)

    def test_find_codex_windows_executable_picks_the_most_recently_built_version(self):
        base = self.dir / "localappdata"
        older = base / "OpenAI/Codex/bin/0.157.0/codex.exe"
        newer = base / "OpenAI/Codex/bin/0.158.2/codex.exe"
        for path in (older, newer):
            path.parent.mkdir(parents=True)
            path.write_text("stub", encoding="utf-8")
        os.utime(older, (1000, 1000))
        os.utime(newer, (2000, 2000))
        previous = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(base)
        try:
            self.assertEqual(console.find_codex_windows_executable(), newer)
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_find_codex_windows_executable_is_none_without_localappdata_or_matches(self):
        previous = os.environ.pop("LOCALAPPDATA", None)
        try:
            self.assertIsNone(console.find_codex_windows_executable())
        finally:
            if previous is not None:
                os.environ["LOCALAPPDATA"] = previous
        os.environ["LOCALAPPDATA"] = str(self.dir)
        try:
            self.assertIsNone(console.find_codex_windows_executable())
        finally:
            os.environ.pop("LOCALAPPDATA", None)

    def test_codex_usage_limit_and_success_streams(self):
        failure = lambda info: [{"type": "thread.started", "thread_id": "01a13e37-0000-0000-0000-000000000001"}, {"type": "turn.started"},
                                {"type": "turn.failed", "error": {"message": "You've hit your usage limit. Try again at 9:01 PM.", **info}}]
        for info in ({"codex_error_info": "usage_limit_exceeded"}, {}):
            with self.subTest(info=info):
                code, run = self.run_agent(console.run_codex, self.fake_cli([json.dumps(r) for r in failure(info)], exit_code=1, name="codex"))
                self.assertEqual((run["outcome"], run["error"]["kind"]), ("usage_limit", "usage_limit"))
        item = lambda kind, identifier, **fields: {"type": "item.completed", "item": {"id": identifier, "type": kind, **fields}}
        done = {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 7}}
        with_tool = [{"type": "thread.started", "thread_id": "01a13e37-0000-0000-0000-000000000002"}, {"type": "turn.started"},
                     {"type": "item.started", "item": {"id": "item_1", "type": "command_execution"}},
                     item("command_execution", "item_1", command="echo hi", exit_code=0), item("agent_message", "item_2", text="done"), done]
        code, run = self.run_agent(console.run_codex, self.fake_cli([json.dumps(r) for r in with_tool], name="codex"))
        self.assertEqual((code, run["outcome"], run["tool_calls"], run["no_tool_call"], run["usage"]["output_tokens"]), (0, "completed", 1, False, 7))
        self.assertEqual((run["observed"]["models"], run["model_check"]), ([], "unreported"))  # exec --json never names a model
        no_tool = [with_tool[0], with_tool[1], item("agent_message", "item_0", text="nothing to run"), done]
        code, run = self.run_agent(console.run_codex, self.fake_cli([json.dumps(r) for r in no_tool], name="codex"))
        self.assertEqual((code, run["outcome"], run["tool_calls"], run["no_tool_call"]), (0, "completed", 0, True))

    def test_codex_applied_values_come_from_its_own_session_file_and_only_for_a_valid_thread(self):
        thread = "01a13e37-caf3-7c20-a23d-28fb02f2e4b7"
        sessions = self.dir / "sessions" / "2026" / "10" / "15"
        sessions.mkdir(parents=True)
        (sessions / f"rollout-2026-10-15T15-20-06-{thread}.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"id": thread}}) + "\n" +
            json.dumps({"type": "turn_context", "payload": {"model": "gpt-test-model", "effort": "high", "cwd": "C:/private/path"}}) + "\n", encoding="utf-8")
        previous = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.dir)
        try:
            self.assertEqual(console.codex_applied(thread), {"model": "gpt-test-model", "effort": "high"})  # no path, no content
            self.assertIsNone(console.codex_applied("00000000-0000-0000-0000-000000000000"))
            self.assertIsNone(console.codex_applied("../" * 8))
        finally:
            if previous is None:
                os.environ.pop("CODEX_HOME")
            else:
                os.environ["CODEX_HOME"] = previous

    def test_gateway_record_state_comes_only_from_a_counted_query(self):
        code, run = self.run_agent(console.run_claude, self.fake_cli(fixture_lines("claude-auth-failure.jsonl")))
        runs = console.RunLog(self.dir / "runs.jsonl")
        self.assertEqual(run["gateway"], {"state": "unverified", "count": None, "source": None})
        self.assertEqual(runs.set_gateway(run["run_id"], 0, "decisions id 801-805, window of the run")["gateway"]["state"], "none")
        self.assertEqual(runs.set_gateway(run["run_id"], 3, "decisions id 806-808")["gateway"], {"state": "recorded", "count": 3, "source": "decisions id 806-808"})
        for bad in (("no-such-run", 0), (run["run_id"], -1)):
            with self.assertRaises(ValueError):
                runs.set_gateway(bad[0], bad[1], "x")
        self.assertEqual(len(runs.snapshot()["runs"]), 1)  # updates replace the run's state, history stays in the file

    def test_raw_output_stays_private_and_run_records_are_redacted_on_the_way_out(self):
        lines = fixture_lines("claude-auth-failure.jsonl")
        code, run = self.run_agent(console.run_claude, self.fake_cli(lines))
        raw = list((self.dir / "raw").glob("*.jsonl"))
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0].read_text(encoding="utf-8").splitlines(), lines)
        log = console.EventLog(self.dir / "events.jsonl")
        record = console.Run("Claude", "t", "t:secret", console.MODEL, console.EFFORT)
        record.finish(1, failure="failure with TOKEN=very-secret-value")
        stored = record.record("final")
        stored["error"] = {**stored["error"], "message": "failure with TOKEN=very-secret-value"}
        console.RunLog(self.dir / "runs.jsonl").append(stored)
        server = console.make_server("127.0.0.1", 0, log)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/runs") as response:
                body = response.read().decode()
            self.assertNotIn("very-secret-value", body)
            self.assertEqual({item["agent"] for item in json.loads(body)["runs"]}, {"Claude"})
            for path in ("/runtime/raw/" + raw[0].name, "/raw/" + raw[0].name):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/runs", headers={"Host": "evil.example"}))
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
