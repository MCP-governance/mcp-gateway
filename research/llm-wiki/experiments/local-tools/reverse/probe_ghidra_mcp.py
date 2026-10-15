#!/usr/bin/env python3
"""Create a harmless synthetic ELF and exercise a pinned Ghidra MCP over stdio."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path


def write_synthetic_elf(path: Path) -> str:
    # ELF64 ET_EXEC for x86-64, one RX PT_LOAD, and `mov eax,42; ret` at entry.
    code = bytes.fromhex("b82a000000c3")
    offset = 64 + 56
    base = 0x400000
    entry = base + offset
    ident = b"\x7fELF" + bytes((2, 1, 1, 0, 0)) + bytes(7)
    header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        ident,
        2,
        62,
        1,
        entry,
        64,
        0,
        0,
        64,
        56,
        1,
        0,
        0,
        0,
    )
    program_header = struct.pack(
        "<IIQQQQQQ",
        1,
        5,
        0,
        base,
        base,
        offset + len(code),
        offset + len(code),
        0x1000,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + program_header + code)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True, help="task-local venv python.exe")
    parser.add_argument("--ghidra-install-dir", type=Path, required=True)
    parser.add_argument("--extension-jar", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, help="optional persistent Ghidra project directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    work = args.work_dir
    binary = work / "synthetic_return_42.elf"
    binary_sha256 = write_synthetic_elf(binary)
    env = os.environ.copy()
    env["GHIDRA_INSTALL_DIR"] = str(args.ghidra_install_dir)
    env["JAVA_HOME"] = str(args.java_home)
    env["PATH"] = str(args.java_home / "bin") + os.pathsep + env.get("PATH", "")
    env["JAVA_TOOL_OPTIONS"] = "-Dfile.encoding=UTF-8 -Duser.home=" + str(work / "java-home")
    (work / "java-home").mkdir(parents=True, exist_ok=True)
    command = [
        str(args.python),
        "-m",
        "ghidra_mcp",
        "--headless",
        "--binary",
        str(binary),
        "--ghidra-install-dir",
        str(args.ghidra_install_dir),
        "--extension-jar",
        str(args.extension_jar),
    ]
    if args.project_dir:
        command.extend(["--project", str(args.project_dir), "--project-name", "synthetic-reverse-probe"])
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    lines: queue.Queue[str | None] = queue.Queue()
    errors: list[str] = []

    def read_stdout() -> None:
        assert process.stdout
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    def read_stderr() -> None:
        assert process.stderr
        for line in process.stderr:
            errors.append(line.rstrip())

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    assert process.stdin
    messages: list[dict] = []

    def request(method: str, params: dict, request_id: int, timeout: int = 240) -> dict:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if line is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                time.sleep(0.1)
                break
            response = json.loads(line)
            messages.append(response)
            if response.get("id") == request_id:
                return response
        raise RuntimeError(
            f"No response for {method}; exit={process.poll()}; stderr={' | '.join(errors[-30:])}"
        )

    evidence: dict = {
        "command": command,
        "binary": str(binary),
        "binary_sha256": binary_sha256,
        "messages": messages,
    }
    try:
        evidence["initialize"] = request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "local-reverse-probe", "version": "1.0"},
            },
            1,
        )
        process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        process.stdin.flush()
        evidence["tools_list"] = request("tools/list", {}, 2)
        evidence["read_call"] = request(
            "tools/call", {"name": "get_program_info", "arguments": {}}, 3
        )
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            process.stdin.close()
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        except OSError:
            process.kill()
        time.sleep(0.2)
        for thread in threading.enumerate():
            if thread.name in {"Thread-1 (read_stdout)", "Thread-2 (read_stderr)"}:
                thread.join(timeout=1)
    evidence["stderr"] = errors
    evidence["exit_code_after_terminate"] = process.returncode
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "binary_sha256": binary_sha256,
        "tool_count": len(evidence.get("tools_list", {}).get("result", {}).get("tools", [])),
        "read_call": evidence.get("read_call"),
        "stderr_tail": errors[-20:],
    }, ensure_ascii=False, indent=2))
    return 1 if "error" in evidence else 0


if __name__ == "__main__":
    raise SystemExit(main())
