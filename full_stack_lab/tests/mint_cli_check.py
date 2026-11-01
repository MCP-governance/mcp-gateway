"""`mint` terminal commands against a fake service broker: every local-screen feature has a command (a server without
a desktop has only the terminal), and the console opens from the terminal without a text browser taking it over."""
import contextlib
import importlib.util
import io
import os
import unittest
from pathlib import Path
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[2] / "endpoint-agent"
spec = importlib.util.spec_from_file_location("kit_access_cli", KIT / "kit_access.py")
access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(access)

CONSOLE = "https://gateway.example/workspace"
SUMMARY = {
    "servers": [{"name": "Hugging Face", "path": "gateway", "available": True}],
    "calls": [{"called_at": "2026-11-01T03:00:00+00:00", "harness": "codex", "account": "pj3", "server": "hf", "server_name": "Hugging Face",
               "tool": "hub_repo_search", "path": "gateway", "failed": False, "input_bytes": 120, "output_bytes": 37000,
               "decision_id": 912, "decision": "Block", "policy_id": "P-CONSENT-001", "reason": "이용 동의 필요",
               "decided_at": "2026-11-01T02:59:59+00:00"},
              {"called_at": "2026-11-01T02:59:00+00:00", "harness": "claude", "server": "memory", "tool": "read_graph",
               "path": "local", "failed": False}],
    "requests": [{"name": "ghidra", "status": "OPEN", "created_at": "2026-11-01T01:00:00+00:00"}],
    "applications": [{"name": "Hugging Face", "status": "APPROVED", "registered_server_id": "hf", "created_at": "2026-10-31T01:00:00+00:00"},
                     {"name": "Fetch", "status": "HOLD", "registered_server_id": None, "created_at": "2026-10-31T02:00:00+00:00"}],
    "consents": [], "console_url": CONSOLE,
}
SOURCES = [{"server_id": "memory", "display_name": "Memory", "commit_sha": "a" * 40, "source_available": True},
           {"server_id": "hf", "display_name": "Hugging Face", "commit_sha": None, "source_available": False,
            "connection_url": "https://gateway.example/mcp/hf/"}]


def run(*argv, env=None):
    sent = []

    def receive(address, command, folder=None):
        sent.append((command, folder))
        if command["action"] == "self":
            return SUMMARY
        if command["action"] == "list":
            return SOURCES
        if command["action"] == "download":
            return str(Path(folder or "MINT") / "memory.zip")
        raise AssertionError(command)
    out = io.StringIO()
    with patch.object(access, "receive", receive), patch.dict(os.environ, env or {}, clear=env is not None), \
            patch("webbrowser.open") as opened, contextlib.redirect_stdout(out):
        code = access.mint_command(list(argv), "pipe", lambda: ["연결 상태: 연결됨"], lambda: [])
    return code, out.getvalue(), sent, opened


class Commands(unittest.TestCase):
    def test_every_command_is_dispatched_and_named_in_help(self):
        # managed-linux.py hands `mint <x>` to mint_command only when x is in SUBCOMMANDS.
        for name in access.SUBCOMMANDS:
            with self.assertRaises(SystemExit) as done, contextlib.redirect_stdout(io.StringIO()):
                access.mint_command([name, "-h"], "pipe", list, list)
            self.assertEqual(done.exception.code, 0, name)
            self.assertIn(name, access.HELP)
        with self.assertRaises(SystemExit) as done, contextlib.redirect_stderr(io.StringIO()):
            access.mint_command(["nothing"], "pipe", list, list)
        self.assertEqual(done.exception.code, 2)

    def test_logs_are_numbered_and_a_number_shows_the_gateway_decision(self):
        code, out, *_ = run("logs")
        self.assertEqual(code, 0)
        self.assertIn("번호", out)
        self.assertIn("Hugging Face · hub_repo_search", out)
        self.assertIn("mint logs <번호>", out)
        code, out, *_ = run("logs", "1")
        self.assertEqual(code, 0)
        for value in ("차단", "P-CONSENT-001", "이용 동의 필요", "36.1 KB", "120 B", "pj3", f"{CONSOLE}#/activity?d=912"):
            self.assertIn(value, out)
        self.assertIn("판정 시각", out)
        self.assertIn("호출 시각", out)
        code, out, *_ = run("logs", "2")
        self.assertIn("로컬", out)
        self.assertNotIn("#/activity", out)
        code, out, *_ = run("logs", "3")
        self.assertEqual((code, out.strip()), (1, "호출 번호 확인 필요 · 1~2"))

    def test_requests_shows_pc_requests_and_applications_in_console_words(self):
        code, out, *_ = run("requests")
        self.assertEqual(code, 0)
        self.assertIn("내 요청 · 1", out)
        self.assertIn("검토 대기", out)
        self.assertIn("도입 신청 · 2", out)
        self.assertIn("승인 · 게이트웨이 등록", out)
        self.assertNotIn("HOLD", out)

    def test_sources_lists_and_downloads_only_an_available_source(self):
        code, out, sent, _ = run("sources")
        self.assertEqual(code, 0)
        self.assertIn("받기 가능", out)
        self.assertIn("https://gateway.example/mcp/hf/", out)
        code, out, sent, _ = run("sources", "Memory", "--to", "inbox")
        self.assertEqual(code, 0)
        self.assertEqual(sent[-1], ({"action": "download", "server": "memory", "commit": "a" * 40}, "inbox"))
        code, out, sent, _ = run("sources", "hf")
        self.assertEqual(code, 1)
        self.assertFalse([c for c, _ in sent if c["action"] == "download"])

    def test_console_prints_the_page_and_opens_a_browser_only_on_a_desktop(self):
        code, out, _, opened = run("console", "consent", env={"DISPLAY": ":0"} if os.name != "nt" else {"SystemRoot": "C:\\Windows"})
        self.assertEqual((code, out.strip()), (0, f"{CONSOLE}#/consent"))
        opened.assert_called_once_with(f"{CONSOLE}#/consent")
        code, out, _, opened = run("console", env={"SSH_CONNECTION": "10.0.0.1 1 10.0.0.2 22", "DISPLAY": ":0"})
        self.assertEqual(out.strip(), CONSOLE)
        opened.assert_not_called()

    def test_headless_linux_never_opens_a_text_browser(self):
        with patch.object(access.os, "name", "posix"), patch("sys.platform", "linux"), patch.dict(os.environ, {}, clear=True):
            self.assertFalse(access.can_open_browser())
        with patch.object(access.os, "name", "posix"), patch("sys.platform", "linux"), patch.dict(os.environ, {"WAYLAND_DISPLAY": "w"}, clear=True):
            self.assertTrue(access.can_open_browser())

    def test_tables_align_by_terminal_columns_with_hangul(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            access.print_table("t", ("서버", "상태"), [("Hugging Face", "검토 대기"), ("메모리", "승인")])
        lines = out.getvalue().splitlines()[2:]
        # The second column starts at the same terminal column on every line.
        starts = {access.cells(line[:line.rindex("  ") + 2]) for line in lines}
        self.assertEqual(len(starts), 1, lines)
        code, out, *_ = run("logs", "1")
        with patch.dict(SUMMARY, calls=[]):
            code, out, *_ = run("logs", "1")
        self.assertEqual((code, out.strip()), (1, "MCP 호출 기록 없음"))

    def test_decision_and_tool_outcome_are_separate(self):
        cases = [({"decision": "Allow", "failed": False}, ("허용", "완료")), ({"decision": "Alert", "failed": False}, ("경보", "완료")),
                 ({"decision": "Alert", "failed": True}, ("경보", "실패")), ({"decision": "Block", "failed": False}, ("차단", "실행 안 함")),
                 ({"decision": "Allow", "failed": True}, ("허용", "실패")), ({"decision": None, "failed": False}, ("—", "완료"))]
        for call, expected in cases:
            self.assertEqual((access.call_verdict(call), access.call_outcome(call)), expected, call)
        code, out, *_ = run("logs")
        self.assertIn("판정", out)
        self.assertIn("실행 안 함", out)

    def test_narrow_terminal_prints_one_line_per_row(self):
        out = io.StringIO()
        with patch.object(access, "terminal_columns", lambda: 40), contextlib.redirect_stdout(out):
            access.print_table("MCP 호출", access.CALL_COLUMNS, [("2026-11-01 09:00:00", "Codex", "게이트웨이", "Hugging Face · hub_repo_search", "경보", "완료")])
        self.assertIn("  2026-11-01 09:00:00 · Codex · 게이트웨이 · Hugging Face · hub_repo_search · 경보 · 완료", out.getvalue())

    def test_json_output_for_scripts(self):
        import json
        code, out, *_ = run("logs", "--json", "-n", "1")
        self.assertEqual(code, 0)
        self.assertEqual([c["decision_id"] for c in json.loads(out)["calls"]], [912])
        code, out, *_ = run("requests", "--json")
        self.assertEqual(len(json.loads(out)["applications"]), 2)
        code, out, *_ = run("sources", "--json")
        self.assertEqual(json.loads(out)[0]["server_id"], "memory")

    def test_input_errors_read_in_korean(self):
        for argv, words in ((["logs", "abc"], "'abc' 확인 필요"), (["console", "bad"], "'bad' 없음 · 선택"), (["request"], "필요한 값: 서버")):
            err = io.StringIO()
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(err):
                access.mint_command(argv, "pipe", list, list)
            self.assertIn(words, err.getvalue())
            self.assertNotIn("error", err.getvalue())

    def test_console_without_address_is_a_label(self):
        with patch.dict(SUMMARY, console_url=""):
            code, out, *_ = run("console")
        self.assertEqual((code, out.strip()), (1, "콘솔 주소 확인 실패 · mint --check"))


if __name__ == "__main__":
    unittest.main()
