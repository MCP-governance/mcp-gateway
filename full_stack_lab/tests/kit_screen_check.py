"""Offline shared-screen checks; no enrollment, model, host settings or network."""
import ctypes
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from contextlib import redirect_stdout

KIT = Path(__file__).resolve().parents[2] / "endpoint-agent"
spec = importlib.util.spec_from_file_location("kit_screen_test", KIT / "kit_screen.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class TTY(io.StringIO):
    def isatty(self):
        return True


def example():
    now = 1800000000
    return {"updated": now, "connected": True, "state": "active", "mode": "simple", "servers": ["learn", "deepwiki"],
            "harnesses": {"claude": "2.1.10", "codex": "0.115.0"}, "protected_configs": True,
            "blocks": [{"at": datetime.fromtimestamp(now - i * 10, timezone.utc).isoformat(), "id": "private-event"}
                       for i in range(5, 0, -1)], "device_key": "super-secret-token-never-print"}


class Frame(unittest.TestCase):
    def test_same_frame_has_steps_three_cells_korean_badge_and_five_blocks(self):
        text = kit.frame(example(), [("연결 등록", 0, 4, "✓"), ("설치 확인", 0, 8, "✓")],
                         kit.check_cells({"model": {"ok": True, "seconds": 2.1},
                                          "connection": {"initialized": ["learn"], "tools": 12}}),
                         columns=90, lines=40, now=1800000000)
        for label in ("MINT 엔드포인트", "차단 발생", "연결 등록  완료 · 4초", "하네스 응답",
                      "게이트웨이 MCP 목록", "관리 설정 적용  완료", "승인 MCP 서버  2개", "codex 0.115.0", kit.KEYS):
            self.assertIn(label, text)
        self.assertEqual(text.count("엔드포인트에서 차단"), 5)
        for hidden in ("active", "simple", "device_key", "super-secret", "private-event"):
            self.assertNotIn(hidden, text)

    def test_stale_future_and_unknown_states_do_not_claim_a_connection(self):
        for updated in (0, 1800000001):
            text = kit.frame({**example(), "updated": updated, "state": "new-enum"}, now=1800000000)
            self.assertIn("연결 끊김", text)
            self.assertNotIn("new-enum", text)
        text = kit.frame({"connected": True, "updated": 1800000000}, now=1800000000)
        self.assertIn("관리 설정 적용  —", text)

    def test_probe_errors_and_credentials_never_leave_the_projection(self):
        cells = kit.check_cells({"model": {"ok": False, "detail": "Bearer private-token"},
                                 "connection": {"failed": {"learn": "authorization=abc"}}})
        text = kit.frame(example(), cells=cells + [("서버 연결", "실패 · Bearer abc")], now=1800000000)
        self.assertIn("실패", text)
        for hidden in ("Bearer", "authorization", "private-token"):
            self.assertNotIn(hidden, text)
        self.assertEqual(kit.clean("\x1b[2J\nhello\r"), "[2Jhello")

    def test_korean_width_combining_characters_and_tiny_terminal(self):
        self.assertEqual(kit.width("한글a"), 5)
        self.assertEqual(kit.clip("한글a", 3), "한")
        self.assertEqual(kit.clip("한글a", 4), "한글")
        self.assertEqual(kit.width("e\u0301"), 1)
        self.assertEqual(kit.clip("e\u0301한", 1), "e\u0301")
        for columns, lines in ((1, 1), (10, 4), (40, 10), (80, 24)):
            text = kit.frame(example(), columns=columns, lines=lines, now=1800000000)
            self.assertLessEqual(len(text.splitlines()), max(0, lines - 1))
            self.assertTrue(all(kit.width(line) < columns for line in text.splitlines()))


class Terminal(unittest.TestCase):
    def screen(self, vt=True):
        output = TTY()
        with mock.patch.object(kit, "enable_vt", return_value=(lambda: None) if vt else None), \
                mock.patch.object(kit.os, "name", "nt"), mock.patch.dict(os.environ, {"MCPGW_PLAIN": ""}):
            return kit.Screen(output=output, input=TTY()), output

    def test_vt_failure_uses_lines_and_never_writes_escape_sequences(self):
        screen, output = self.screen(vt=False)
        screen.step("연결 등록")
        screen.close_step()
        screen.result([("하네스 응답", "완료")], "하네스 실행")
        screen.stop()
        self.assertIn("[연결 등록]", output.getvalue())
        self.assertIn("하네스 응답: 완료", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

    def test_quit_exception_and_signal_restore_cursor_and_buffer(self):
        screen, output = self.screen()
        with mock.patch.object(screen, "read_key", return_value="q"):
            kit.live(example, screen=screen)
        self.assertTrue(output.getvalue().startswith(kit.ENTER))
        self.assertTrue(output.getvalue().endswith(kit.LEAVE))
        old = output.getvalue()
        screen.stop()
        self.assertEqual(output.getvalue(), old)
        screen, output = self.screen()
        with self.assertRaises(RuntimeError):
            kit.live(lambda: (_ for _ in ()).throw(RuntimeError("failure")), screen=screen)
        self.assertTrue(output.getvalue().endswith(kit.LEAVE))
        previous = signal.getsignal(signal.SIGTERM)
        screen, output = self.screen()
        with self.assertRaises(SystemExit):
            screen._signal(signal.SIGTERM, None)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
        self.assertTrue(output.getvalue().endswith(kit.LEAVE))

    def test_pause_resume_and_finish_leave_a_plain_summary(self):
        screen, output = self.screen()
        screen.step("설치 확인")
        screen.close_step()
        screen.pause()
        self.assertIsNone(screen.window)
        with mock.patch.object(kit, "enable_vt", return_value=lambda: None), mock.patch.object(kit.os, "name", "nt"), \
                mock.patch.dict(os.environ, {"MCPGW_PLAIN": ""}):
            screen.resume()
        with mock.patch.object(screen, "read_key", return_value=""):
            screen.finish(0)
        self.assertEqual(output.getvalue().count(kit.ENTER), 2)
        self.assertEqual(output.getvalue().count(kit.LEAVE), 2)
        self.assertIn("MINT 엔드포인트", output.getvalue().split(kit.LEAVE)[-1])

    def test_c_checks_r_rereads_and_q_exits(self):
        screen, _ = self.screen()
        read, check = mock.Mock(side_effect=example), mock.Mock(return_value=[("하네스 응답", "완료")])
        immediate = lambda **kw: SimpleNamespace(start=lambda: kw["target"](*kw["args"]))
        with mock.patch.object(screen, "read_key", side_effect=["c", "r", "q"]), \
                mock.patch.object(kit.threading, "Thread", side_effect=immediate):
            kit.live(read, check, screen)
        self.assertEqual(read.call_count, 3)
        check.assert_called_once()
        self.assertEqual(screen.cells, [("하네스 응답", "완료")])

    def test_windows_console_mode_is_enabled_and_restored(self):
        kernel = SimpleNamespace(GetConsoleMode=mock.Mock(), SetConsoleMode=mock.Mock(return_value=1))
        def get_mode(handle, pointer):
            pointer._obj.value = 1
            return 1
        kernel.GetConsoleMode.side_effect = get_mode
        with mock.patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
                mock.patch.object(kit.os, "name", "nt"), \
                mock.patch.dict(sys.modules, {"msvcrt": SimpleNamespace(get_osfhandle=lambda fd: 123)}):
            restore = kit.enable_vt(SimpleNamespace(fileno=lambda: 1))
            kernel.SetConsoleMode.assert_called_with(123, 5)
            restore()
            kernel.SetConsoleMode.assert_called_with(123, 1)
            kernel.SetConsoleMode.return_value = 0
            self.assertIsNone(kit.enable_vt(SimpleNamespace(fileno=lambda: 1)))

    def test_posix_input_is_nonblocking_and_termios_is_restored(self):
        terminal = SimpleNamespace(tcgetattr=mock.Mock(return_value=[1, 2, 3]),
                                   tcsetattr=mock.Mock(), TCSADRAIN=1)
        keyboard = TTY()
        keyboard.fileno = lambda: 10
        with mock.patch.object(kit, "enable_vt", return_value=lambda: None), \
                mock.patch.object(kit.os, "name", "posix"), mock.patch.dict(os.environ, {"MCPGW_PLAIN": ""}), \
                mock.patch.dict(sys.modules, {"termios": terminal, "tty": SimpleNamespace(setcbreak=mock.Mock()),
                                             "select": SimpleNamespace(select=lambda *args: ([keyboard], [], []))}), \
                mock.patch.object(kit.os, "read", return_value=b"c"):
            screen = kit.Screen(output=TTY(), input=keyboard)
            self.assertEqual(screen.read_key(0), "c")
            screen.stop()
        terminal.tcsetattr.assert_called_once_with(10, 1, [1, 2, 3])

    def test_windows_input_is_nonblocking(self):
        screen, _ = self.screen()
        keyboard = SimpleNamespace(kbhit=lambda: True, getwch=lambda: "R")
        try:
            with mock.patch.object(kit.os, "name", "nt"), mock.patch.dict(sys.modules, {"msvcrt": keyboard}):
                self.assertEqual(screen.read_key(0), "r")
        finally:
            screen.stop()

    def test_windows_redirect_preserves_existing_text_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            path.write_text(json.dumps(example()), encoding="utf-8")
            done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-I", "-S", str(KIT / "windows_status.py"), str(path)],
                                  capture_output=True, text=True, encoding="utf-8", check=True)
        self.assertIn("연결 상태:", done.stdout)
        self.assertNotIn("\x1b", done.stdout)


class LinuxObservation(unittest.TestCase):
    def test_existing_observer_emits_only_five_timestamps_and_ids_for_the_screen(self):
        observer_spec = importlib.util.spec_from_file_location("screen_observer_test", KIT / "os-observer.py")
        observer = importlib.util.module_from_spec(observer_spec)
        observer_spec.loader.exec_module(observer)
        agent_spec = importlib.util.spec_from_file_location("screen_agent_test", KIT / "agent.py")
        agent = importlib.util.module_from_spec(agent_spec)
        agent_spec.loader.exec_module(agent)

        class RootOwnedPath(type(Path())):
            def stat(self, *, follow_symlinks=True):
                actual = os.stat(self, follow_symlinks=follow_symlinks)
                mode = 0o40700 if stat.S_ISDIR(actual.st_mode) else 0o100600
                return os.stat_result((mode, actual.st_ino, actual.st_dev, actual.st_nlink, 0, 0, actual.st_size,
                                       int(actual.st_atime), int(actual.st_mtime), int(actual.st_ctime)))

            def exists(self):
                return os.path.exists(self)

        records = [{"_BOOT_ID": "boot", "__CURSOR": f"c{i}", "__REALTIME_TIMESTAMP": str(1800000000000000 + i),
                    "MESSAGE": 'apparmor="DENIED" operation="exec" profile="mcpgw-u" name="/usr/bin/tool" '
                               'comm="bash" fsuid=1001 ouid=0'} for i in range(7)]
        fake_agent = SimpleNamespace(validate_gateway=lambda: None, endpoint_id=lambda: "fixture",
                                     call=mock.Mock(), report_status=mock.Mock(), seal_os_event=agent.seal_os_event)
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "observer.json"
            config.write_text("{}", encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(observer, "_AGENT", fake_agent), mock.patch.object(observer, "Path", RootOwnedPath), \
                    mock.patch.object(observer.os, "geteuid", return_value=0, create=True), \
                    mock.patch.object(observer.subprocess, "run", return_value=SimpleNamespace(
                        stdout="\n".join(json.dumps(record) for record in records))), \
                    mock.patch.object(sys, "argv", ["os-observer.py", "--config", str(config), "--uid", "1001",
                                                   "--profile", "mcpgw-u"]), redirect_stdout(out):
                observer.main()
        blocks = json.loads(out.getvalue())["recent_blocks"]
        self.assertEqual([row["id"] for row in blocks], [f"boot:c{i}" for i in range(2, 7)])
        self.assertTrue(all(set(row) == {"id", "at"} for row in blocks))
        self.assertNotIn("MESSAGE", out.getvalue())
        self.assertNotIn("/usr/bin", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
