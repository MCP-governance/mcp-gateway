"""Check the embedded runtime without enrollment, host changes or network traffic."""
import ast
import importlib
import json
import sys
from pathlib import Path


def check(root):
    modules = {"site", "ssl", "ctypes", "winreg", "msvcrt", "tomllib", "xml.etree.ElementTree"}
    files = ("agent.py", "install.py", "managed-windows.py", "os-observer-windows.py", "offline_buffer.py", "windows_status.py")
    for name in files:
        tree = ast.parse((root / name).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    # Linux-only branches are not imported on Windows; application modules have startup side effects.
    modules -= {"fcntl", "pwd", "grp", "agent", "windows_status"}
    for name in sorted(modules):
        importlib.import_module(name)
    assert sys.version_info[:3] == (3, 13, 16), sys.version
    assert sys.flags.isolated and sys.flags.no_site
    assert sys.flags.ignore_environment
    print(json.dumps({"modules": sorted(modules), "site_automatic": False}))


if __name__ == "__main__":
    check(Path(__file__).resolve().parent)
