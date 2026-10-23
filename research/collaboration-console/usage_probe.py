"""Bounded account usage reads; these commands never create an inference turn."""
import json
import math
import os
import queue
import re
import subprocess
import threading
import time
from datetime import datetime


MAX_OUTPUT = 1024 * 1024
MAX_LINE = 65536


def _observation(windows, source, now):
    if not windows:
        return None
    limiting = min(windows, key=lambda window: (window["remaining_percent"], -window["reset_at"]))
    remaining = limiting["remaining_percent"]
    return {"status": "exhausted" if remaining == 0 else "warning" if remaining <= 10 else "known",
            "remaining_percent": remaining, "reset_at": limiting["reset_at"],
            "observed_at": now, "source": source, "windows": windows}


def parse_codex(result, now=None):
    now = time.time() if now is None else now
    if not isinstance(result, dict):
        return None
    buckets = result.get("rateLimitsByLimitId")
    rates = buckets.get("codex") if isinstance(buckets, dict) else None
    if not isinstance(rates, dict):
        rates = result.get("rateLimits")
    if not isinstance(rates, dict):
        return None
    windows = []
    for name in ("primary", "secondary"):
        window = rates.get(name)
        if not isinstance(window, dict):
            continue
        used, reset = window.get("usedPercent"), window.get("resetsAt")
        if type(used) not in (int, float) or not math.isfinite(used) or not 0 <= used <= 100:
            continue
        if type(reset) not in (int, float) or not math.isfinite(reset) or reset <= now:
            continue
        clean = {"group": "codex", "window": name, "remaining_percent": round(100-used, 2), "reset_at": reset}
        minutes = window.get("windowDurationMins")
        if type(minutes) in (int, float) and math.isfinite(minutes) and 0 < minutes <= 525600:
            clean["window_minutes"] = minutes
        windows.append(clean)
    return _observation(windows, "Codex account/rateLimits/read", now)


def antigravity_group(model):
    """agy는 Gemini 모델 묶음과 Claude·GPT 모델 묶음의 주간 한도가 따로다(10-23 실측: 0% / 73%)."""
    return "Gemini Models" if str(model or "").startswith("gemini") else "Claude and GPT models"


def parse_antigravity(output, now=None, group="Gemini Models"):
    now = time.time() if now is None else now
    windows = []
    seen = set()
    for line in output.splitlines():
        columns = [value.strip() for value in line.split("\t")]
        if len(columns) != 4 or columns[0] != group:
            continue
        if columns[1] not in {"Weekly Limit Remaining", "Daily Limit Remaining", "Session Limit Remaining"}:
            continue
        if columns[1] in seen:
            continue
        percent = re.fullmatch(r"(\d{1,3}(?:\.\d{1,2})?)%", columns[2])
        if not percent:
            continue
        remaining = float(percent[1])
        try:
            reset_date = datetime.fromisoformat(columns[3].replace("Z", "+00:00"))
            reset = reset_date.timestamp() if reset_date.tzinfo else 0
        except (ValueError, OverflowError):
            continue
        if not 0 <= remaining <= 100 or reset <= now:
            continue
        windows.append({"group": group, "window": columns[1],
                        "remaining_percent": remaining, "reset_at": reset})
        seen.add(columns[1])
        if len(windows) == 3:
            break
    return _observation(windows, f"Antigravity /usage ({group})", now)


def _start(command):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    messages, stop = queue.Queue(maxsize=8), threading.Event()

    def read():
        total = 0
        try:
            while not stop.is_set():
                line = process.stdout.readline(MAX_LINE + 1)
                total += len(line)
                if len(line) > MAX_LINE or total > MAX_OUTPUT:
                    item = RuntimeError("Usage output limit exceeded")
                else:
                    item = line
                while not stop.is_set():
                    try:
                        messages.put(item, timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if not line or isinstance(item, Exception):
                    return
        except (OSError, ValueError):
            pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    return process, messages, stop, reader


def _line(messages, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Usage read timed out")
    try:
        line = messages.get(timeout=remaining)
    except queue.Empty as error:
        raise TimeoutError("Usage read timed out") from error
    if isinstance(line, Exception):
        raise line
    return line.decode("utf-8", errors="replace")


def _stop(process, messages, stop, reader):
    stop.set()
    if process.poll() is None:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=1, creationflags=subprocess.CREATE_NO_WINDOW)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    for stream in (process.stdin, process.stdout):
        try:
            stream.close()
        except OSError:
            pass
    reader.join(timeout=0.5)


def probe_codex(executable, timeout=12):
    process, messages, stop, reader = _start([executable, "--no-daemon", "app-server"])
    deadline = time.monotonic() + min(12, max(0.1, timeout))
    try:
        def send(message):
            process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
            process.stdin.flush()

        def receive(identifier):
            while True:
                line = _line(messages, deadline)
                if not line:
                    raise ValueError("Usage server ended")
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and type(event.get("id")) is int and event["id"] == identifier:
                    if "error" in event:
                        raise ValueError("Usage request rejected")
                    return event.get("result")

        send({"method": "initialize", "id": 0, "params": {"clientInfo": {"name": "mint_usage", "version": "1.0"}}})
        receive(0)
        send({"method": "initialized"})
        send({"method": "account/rateLimits/read", "id": 1})
        return parse_codex(receive(1))
    finally:
        _stop(process, messages, stop, reader)


def probe_antigravity(executable, timeout=12, group="Gemini Models"):
    process, messages, stop, reader = _start([executable, "--print", "/usage"])
    deadline = time.monotonic() + min(12, max(0.1, timeout))
    try:
        output = []
        while True:
            line = _line(messages, deadline)
            if not line:
                break
            output.append(line)
        if process.wait(timeout=max(0.1, deadline-time.monotonic())) != 0:
            return None
        raw="".join(output)
        result=parse_antigravity(raw,group=group)
        if result:
            result['groups']={name:parse_antigravity(raw,group=name) for name in ('Gemini Models','Claude and GPT models')}
        return result
    finally:
        _stop(process, messages, stop, reader)


def probe(provider, executable, model=None):
    try:
        if provider == "codex":
            return probe_codex(executable)
        if provider == "antigravity":
            return probe_antigravity(executable, group=antigravity_group(model))
    except (OSError, ValueError, RuntimeError, TimeoutError, queue.Empty, subprocess.SubprocessError):
        return None
    return None
