"""Check the embedded runtime without enrollment, host changes or network traffic."""
import ast
import importlib
import json
import sys
from pathlib import Path

FILES = ("agent.py", "install.py", "managed-windows.py", "os-observer-windows.py", "offline_buffer.py", "windows_status.py", "kit_screen.py")
# Linux-only branches are not imported on Windows; application modules have startup side effects. tomli·toml are the
# fallbacks for Pythons before 3.11 (D-232); the embedded 3.13 has tomllib, and requiring them failed every Windows
# install at 「실행 파일 준비」 (pj3 10-25).
NOT_IMPORTED = {"fcntl", "pwd", "grp", "termios", "tty", "agent", "windows_status", "tomli", "toml"}


def modules_of(root):
    modules = {"site", "ssl", "ctypes", "winreg", "msvcrt", "tomllib", "xml.etree.ElementTree"}
    for name in FILES:
        tree = ast.parse((root / name).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    return modules - NOT_IMPORTED


def check(root):
    modules = modules_of(root)
    for name in sorted(modules):
        importlib.import_module(name)
    assert sys.version_info[:3] == (3, 13, 16), sys.version
    assert sys.flags.isolated and sys.flags.no_site
    assert sys.flags.ignore_environment
    print(json.dumps({"modules": sorted(modules), "site_automatic": False}))


if __name__ == "__main__":
    check(Path(__file__).resolve().parent)
