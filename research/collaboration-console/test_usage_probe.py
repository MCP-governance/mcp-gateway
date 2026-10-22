import json
import queue
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import usage_probe


class ParseChecks(unittest.TestCase):
    def test_codex_uses_limiting_window_and_its_reset(self):
        value = usage_probe.parse_codex({"rateLimits": {
            "primary": {"usedPercent": 15, "resetsAt": 200, "windowDurationMins": 300},
            "secondary": {"usedPercent": 93, "resetsAt": 900, "windowDurationMins": 10080},
        }}, now=100)
        self.assertEqual(value["remaining_percent"], 7)
        self.assertEqual(value["reset_at"], 900)
        self.assertEqual(value["status"], "warning")
        self.assertEqual(len(value["windows"]), 2)
        self.assertEqual(value["windows"][0]["window_minutes"], 300)

    def test_codex_selects_codex_bucket_without_using_other_groups(self):
        value = usage_probe.parse_codex({"rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 10, "resetsAt": 200}},
            "another_product": {"primary": {"usedPercent": 100, "resetsAt": 900}},
        }}, now=100)
        self.assertEqual(value["remaining_percent"], 90)
        self.assertEqual(value["reset_at"], 200)

    def test_two_exhausted_windows_wait_until_both_can_reset(self):
        value = usage_probe.parse_codex({"rateLimits": {
            "primary": {"usedPercent": 100, "resetsAt": 200},
            "secondary": {"usedPercent": 100, "resetsAt": 900},
        }}, now=100)
        self.assertEqual(value["remaining_percent"], 0)
        self.assertEqual(value["status"], "exhausted")
        self.assertEqual(value["reset_at"], 900)

    def test_invalid_or_expired_codex_values_are_unknown(self):
        for used in (True, "20", -1, 101, float("nan"), float("inf"), None):
            with self.subTest(used=used):
                self.assertIsNone(usage_probe.parse_codex({"rateLimits": {
                    "primary": {"usedPercent": used, "resetsAt": 200}}}, now=100))
        for reset in (True, "200", 100, -1, float("nan"), float("inf"), None):
            with self.subTest(reset=reset):
                self.assertIsNone(usage_probe.parse_codex({"rateLimits": {
                    "primary": {"usedPercent": 20, "resetsAt": reset}}}, now=100))
        for malformed in (None, [], {"rateLimits": []}, {"rateLimits": {"primary": "no"}}):
            self.assertIsNone(usage_probe.parse_codex(malformed, now=100))

    def test_antigravity_never_combines_gemini_with_claude_gpt_quota(self):
        text = ("Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-10-29T05:14:59Z\n"
                "Gemini Models\tWeekly Limit Remaining\t31%\t2026-10-28T11:22:12Z\n"
                "Gemini Models\tDaily Limit Remaining\t8%\t2026-10-23T11:22:12Z\n")
        value = usage_probe.parse_antigravity(text, now=100)
        self.assertEqual(value["remaining_percent"], 8)
        self.assertEqual(value["status"], "warning")
        self.assertEqual(value["reset_at"], value["windows"][1]["reset_at"])
        self.assertEqual({window["group"] for window in value["windows"]}, {"Gemini Models"})
        self.assertEqual(len(value["windows"]), 2)
        self.assertIsNone(usage_probe.parse_antigravity(text.splitlines()[0], now=100))

    def test_antigravity_rejects_malformed_expired_and_duplicate_windows(self):
        valid = "Gemini Models\tWeekly Limit Remaining\t0%\t2026-10-28T11:22:12Z"
        invalid = [valid.replace("0%", "101%"), valid.replace("0%", "nan%"),
                   valid.replace("2026-10-28T11:22:12Z", "1970-01-01T00:00:01Z"),
                   valid.replace("2026-10-28T11:22:12Z", "2026-10-28T11:22:12"),
                   valid.replace("Weekly Limit Remaining", "Tokens remaining"), "not TSV"]
        for text in invalid:
            self.assertIsNone(usage_probe.parse_antigravity(text, now=100))
        value = usage_probe.parse_antigravity("\n".join([valid] * 10), now=100)
        self.assertEqual(value["status"], "exhausted")
        self.assertEqual(len(value["windows"]), 1)


class ProcessChecks(unittest.TestCase):
    def setUp(self):
        self.children = []
        self.real_start = usage_probe._start

    def start_script(self, script):
        def start(command):
            self.command = command
            child = self.real_start([sys.executable, "-u", "-c", script])
            self.children.append(child)
            return child
        return patch.object(usage_probe, "_start", side_effect=start)

    def tearDown(self):
        for process, messages, stop, reader in self.children:
            try:
                self.assertIsNotNone(process.poll(), "usage child must be reaped on every path")
                self.assertFalse(reader.is_alive(), "usage reader must not remain blocked")
                self.assertTrue(process.stdin.closed)
                self.assertTrue(process.stdout.closed)
            finally:
                usage_probe._stop(process, messages, stop, reader)

    def test_codex_only_initializes_and_reads_usage_without_starting_a_turn(self):
        script = """
import json, sys, time
first = json.loads(sys.stdin.readline())
assert first['method'] == 'initialize' and first['id'] == 0
print(json.dumps({'id': 0, 'result': {}}), flush=True)
assert json.loads(sys.stdin.readline()) == {'method': 'initialized'}
assert json.loads(sys.stdin.readline()) == {'method': 'account/rateLimits/read', 'id': 1}
print(json.dumps({'method': 'account/updated', 'params': {}}), flush=True)
print(json.dumps({'id': 1, 'result': {'rateLimits': {'primary': {
    'usedPercent': 25, 'resetsAt': time.time() + 600}}}}), flush=True)
assert sys.stdin.readline() == ''
"""
        with self.start_script(script):
            value = usage_probe.probe_codex("vendor-codex", timeout=2)
        self.assertEqual(value["remaining_percent"], 75)
        self.assertEqual(self.command, ["vendor-codex", "--no-daemon", "app-server"])

    def test_antigravity_only_invokes_native_usage_command(self):
        script = "print('Gemini Models\\tWeekly Limit Remaining\\t31%\\t2099-10-28T11:22:12Z')"
        with self.start_script(script):
            value = usage_probe.probe_antigravity("vendor-agy", timeout=2)
        self.assertEqual(value["remaining_percent"], 31)
        self.assertEqual(self.command, ["vendor-agy", "--print", "/usage"])

    def test_silent_child_times_out_and_is_reaped(self):
        started = time.monotonic()
        with self.start_script("import time; time.sleep(30)"):
            with self.assertRaises(TimeoutError):
                usage_probe.probe_codex("vendor-codex", timeout=0.1)
        self.assertLess(time.monotonic() - started, 5)

    def test_oversized_output_is_stopped_before_unbounded_buffering(self):
        script = "import sys, time; sys.stdout.write('x' * 2000000); sys.stdout.flush(); time.sleep(30)"
        started = time.monotonic()
        with self.start_script(script):
            with self.assertRaisesRegex(RuntimeError, "output limit"):
                usage_probe.probe_antigravity("vendor-agy", timeout=2)
        self.assertLess(time.monotonic() - started, 5)
        self.assertLessEqual(self.children[0][1].qsize(), 8)

    def test_many_small_lines_cannot_exceed_total_output_budget(self):
        script = "import sys, time; sys.stdout.write(('x' * 50000 + '\\n') * 40); sys.stdout.flush(); time.sleep(30)"
        with self.start_script(script):
            with self.assertRaisesRegex(RuntimeError, "output limit"):
                usage_probe.probe_antigravity("vendor-agy", timeout=2)

    def test_saturated_queue_cleanup_does_not_leave_process_or_reader(self):
        child = self.real_start([sys.executable, "-u", "-c",
                                 "import sys; sys.stdout.write('x\\n' * 2000000); sys.stdout.flush()"])
        self.children.append(child)
        process, messages, stop, reader = child
        deadline = time.monotonic() + 2
        while messages.qsize() < 8 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(messages.qsize(), 8)
        started = time.monotonic()
        usage_probe._stop(process, messages, stop, reader)
        self.assertLess(time.monotonic() - started, 5)

    def test_rejected_request_is_unknown_and_child_is_reaped(self):
        script = "import json, sys; sys.stdin.readline(); print(json.dumps({'id': 0, 'error': {'message': 'rejected'}}), flush=True)"
        with self.start_script(script):
            self.assertIsNone(usage_probe.probe("codex", "vendor-codex"))

    def test_spawn_hides_console_and_discards_stderr(self):
        import io
        fake = unittest.mock.Mock()
        fake.stdout = io.BytesIO()
        with patch.object(usage_probe.subprocess, "Popen", return_value=fake) as popen:
            _, messages, stop, reader = usage_probe._start(["vendor-cli"])
            reader.join(timeout=1)
            stop.set()
        arguments = popen.call_args.kwargs
        self.assertEqual(arguments["stderr"], subprocess.DEVNULL)
        self.assertEqual(arguments["creationflags"], subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        self.assertEqual(messages.get_nowait(), b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
