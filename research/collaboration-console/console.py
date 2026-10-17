"""Local, read-only viewer and append-only recorder for visible agent collaboration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from uuid import UUID
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
DEFAULT_LOG = ROOT / "runtime" / "events.jsonl"
WBS_SNAPSHOT = REPO_ROOT / "research" / "llm-wiki" / "analysis" / "development-wbs" / "snapshot.json"
AUTHORS = {"Codex", "Claude", "User", "System"}
KINDS = {"message", "task", "check"}
STATES = {"queued", "running", "waiting", "completed", "passed", "failed", "blocked", "cancelled"}
MAX_BODY = 48_000
MAX_LINE = MAX_BODY * 4 + 4096
MODEL = "claude-sonnet-5-5"
EFFORT = "xhigh"
DEFAULT_PORT = 1000
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact(value):
    """Suppress common credentials before either disk storage or HTTP output."""
    text = str(value)
    text = re.sub(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(authorization\s*:\s*)\S.*", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,})\b", "[REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED]", text)
    text = re.sub(r"(?is)-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----", "[REDACTED PRIVATE KEY]", text)
    text = re.sub(r"(?i)([\"']?(?:[A-Z_]*API_KEY|[A-Z_]*TOKEN|[A-Z_]*PASSWORD|CLIENT_SECRET|SECRET_KEY)[\"']?\s*[:=]\s*)[\"']?[^\s\"',;}]+[\"']?", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(https?://)[^\s/:@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)([?&](?:access_token|token|api_key|password|secret)=)[^&#\s]+", r"\1[REDACTED]", text)
    return text


def validate(event):
    if not isinstance(event, dict):
        raise ValueError("Event must be an object")
    for key, choices in (("author", AUTHORS), ("kind", KINDS), ("state", STATES)):
        if event.get(key) not in choices:
            raise ValueError(f"Invalid {key}")
    task_id = event.get("task_id")
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}", task_id):
        raise ValueError("task_id must be a short stable identifier")
    if not isinstance(event.get("body"), str) or not event["body"].strip():
        raise ValueError("body must be nonempty text")
    if len(event["body"]) > MAX_BODY:
        raise ValueError("Event body too long")
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, str):
        raise ValueError("Missing timestamp")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    result = {key: event[key] for key in ("timestamp", "author", "kind", "task_id", "state")}
    result["body"] = redact(event["body"])
    if event.get("session_id"):
        session_id = event["session_id"]
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", session_id):
            raise ValueError("Invalid session_id")
        result["session_id"] = session_id
    return result


def append_line(path, lock_path, payload):
    """One whole line appended under a one-byte OS lock, so independent recorder processes never interleave."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock:
        if lock.seek(0, os.SEEK_END) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            with open(path, "a+b") as stream:
                if stream.seek(0, os.SEEK_END):
                    stream.seek(-1, os.SEEK_END)
                    if stream.read(1) != b"\n":
                        # Preserve a crashed producer's partial record; isolate the next valid append.
                        stream.write(b"\n")
                stream.write(payload)
                stream.flush()
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class EventLog:
    def __init__(self, path=DEFAULT_LOG):
        self.path = Path(path).resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def append(self, author, kind, task_id, state, body, session_id=None):
        event = validate({"timestamp": utc_now(), "author": author, "kind": kind,
                          "task_id": task_id, "state": state, "body": body, "session_id": session_id})
        payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(payload) > MAX_LINE:
            raise ValueError("Encoded event too long")
        append_line(self.path, self.lock_path, payload)
        return event

    def snapshot(self, after=0):
        events, tasks, malformed, total = [], {}, 0, 0
        if self.path.exists():
            with open(self.path, "rb") as stream:
                for total, line in enumerate(stream, 1):
                    if not line.endswith(b"\n"):
                        # Readers can race the final append; retry this incomplete line next poll.
                        total -= 1
                        break
                    try:
                        if len(line) > MAX_LINE:
                            raise ValueError("Oversized record")
                        event = validate(json.loads(line))
                    except (ValueError, UnicodeError):
                        malformed += 1
                        continue
                    event["id"] = total
                    if event["kind"] == "task":
                        tasks[(event["task_id"], event["author"])] = event
                    if total > after:
                        events.append(event)
        # shortcut: keep the newest 1,000 visible records; add pagination when sessions need archival browsing.
        return {"events": events[-1000:], "tasks": list(tasks.values()), "cursor": total,
                "malformed_records": malformed, "server_time": utc_now(), "empty": total == 0,
                "truncated": len(events) > 1000, "model_request": {"model": MODEL, "effort": EFFORT}}


class Viewer(BaseHTTPRequestHandler):
    server_version = "CollaborationConsole/1"

    def log_message(self, *_):
        pass

    def respond(self, status, payload, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        # Reject DNS rebinding and cross-origin requests even though no HTTP mutations exist.
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            self.respond(403, b'{"error":"Allowed host required"}')
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in self.server.allowed_hosts}:
            self.respond(403, b'{"error":"Same origin required"}')
            return
        url = urlsplit(self.path)
        if url.path in STATIC:
            name, mime = STATIC[url.path]
            self.respond(200, (ROOT / "static" / name).read_bytes(), mime)
        elif url.path == "/api/events":
            try:
                after = int(parse_qs(url.query).get("after", ["0"])[0])
                if after < 0:
                    raise ValueError("Invalid cursor")
                result = self.server.event_log.snapshot(after)
                self.respond(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except ValueError:
                self.respond(400, b'{"error":"Invalid cursor"}')
            except OSError:
                self.respond(503, b'{"error":"Event log unavailable"}')
        elif url.path == "/api/runs":
            try:
                self.respond(200, json.dumps(self.server.run_log.snapshot(), ensure_ascii=False).encode("utf-8"))
            except OSError:
                self.respond(503, b'{"error":"Run log unavailable"}')
        elif url.path == "/api/wbs":
            try:
                self.respond(200, WBS_SNAPSHOT.read_bytes())
            except OSError:
                self.respond(503, b'{"error":"WBS snapshot unavailable"}')
        elif url.path == "/health":
            self.respond(200, b'{"status":"ok","mode":"read-only"}')
        else:
            self.respond(404, b'{"error":"Not found"}')

    def do_POST(self):
        self.respond(405, b'{"error":"Read-only viewer; use the local emit CLI"}')


def allowed_hosts_for(host, port):
    """127.0.0.1/localhost are always trusted for local testing; the bind host is added so teammates reading over Tailscale pass the Host check."""
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if host not in ("127.0.0.1", "localhost"):
        hosts.add(f"{host}:{port}")
    return hosts


def make_server(host, port, log):
    server = ThreadingHTTPServer((host, port), Viewer)
    server.event_log = log
    server.run_log = RunLog(log.path.parent / "runs.jsonl")
    server.allowed_hosts = allowed_hosts_for(host, server.server_port)
    server.daemon_threads = True
    return server


def visible_claude_event(record, log, task_id, seen, session_id):
    """Record only assistant text/tool names; never record thinking or tool inputs/results."""
    if record.get("type") == "assistant":
        message = record.get("message", {})
        if not isinstance(message, dict) or not isinstance(message.get("content", []), list):
            return None
        message_id = message.get("id", "")
        for index, block in enumerate(message.get("content", [])):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                key = (message_id, index, text)
                if text and key not in seen:
                    log.append("Claude", "message", task_id, "running", text[:MAX_BODY], session_id)
                    seen.add(key)
            elif block.get("type") == "tool_use":
                name = block.get("name", "tool")
                key = ("tool", block.get("id", ""), name)
                if key not in seen:
                    summary = f"도구 호출: {name}"
                    tool_input = block.get("input", {})
                    if name in {"Read", "Grep", "Glob"} and isinstance(tool_input, dict):
                        target = tool_input.get("file_path") or tool_input.get("path")
                        if isinstance(target, str) and not re.search(r"[\x00-\x1f]", target):
                            summary += f" · 대상 {target[:240]}"
                    log.append("Claude", "message", task_id, "running", summary, session_id)
                    seen.add(key)
    elif record.get("type") == "result":
        result = record.get("result")
        if isinstance(result, str) and result.strip():
            if not any(len(key) == 3 and key[-1] == result for key in seen):
                log.append("Claude", "message", task_id, "failed" if claude_failed(record) else "completed", result[:MAX_BODY], session_id)
        if claude_failed(record):
            errors = record.get("errors", [])
            if errors:
                log.append("Claude", "check", task_id, "failed", redact(json.dumps(errors, ensure_ascii=False))[:MAX_BODY], session_id)
        return record
    return None


def claude_failed(record):
    return bool(record.get("is_error")) or str(record.get("subtype", "")).startswith("error")


def save_native_session(record, log, task_id, run_session_id):
    if record.get("type") not in {"system", "result"} or not record.get("session_id"):
        return None
    if record.get("type") == "system" and record.get("subtype") != "init":
        return None
    try:
        native_session = str(UUID(record["session_id"]))
    except (ValueError, TypeError, AttributeError):
        return None
    metadata = {"native_session_id": native_session, "run_session_id": run_session_id,
                "task_id": task_id, "updated_at": utc_now(), "requested_model": MODEL,
                "requested_effort": EFFORT,
                "state": "failed" if record.get("type") == "result" and claude_failed(record)
                else "completed" if record.get("type") == "result" else "running"}
    if record.get("subtype"):
        metadata["result_subtype"] = str(record["subtype"])[:96]
    log.path.parent.mkdir(parents=True, exist_ok=True)
    path = log.path.parent / f"{task_id}.session.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)
    return native_session


RUNS_LOG = ROOT / "runtime" / "runs.jsonl"
# Claude Code's marker for its own local notices ("Failed to authenticate", a limit message). They are not a provider answer.
SYNTHETIC_MODEL = "<synthetic>"
OUTCOMES = {"running", "completed", "turn_error", "usage_limit", "task_failed", "model_mismatch", "cancelled"}
GATEWAY_STATES = {"unverified", "none", "recorded"}
MODEL_CHECKS = {"confirmed", "mismatch", "unreported"}
LIMIT_TEXT = re.compile(r"usage[ _]limit|hit your .{0,16}limit|limit reached|rate.?limit|quota", re.I)
CODEX_TOOL_ITEMS = {"command_execution", "mcp_tool_call", "file_change", "web_search"}
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}")
EFFORT_NAME = re.compile(r"[a-z]{3,10}")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


class Run:
    """What one CLI run did, taken from the CLI's own output.

    `requested` is what we asked for. `observed.models` holds a model name only when a provider answer carried it
    (Claude: assistant.message.model and result.modelUsage; Codex `exec --json` carries none, so it stays empty).
    The model Claude Code echoes in system.init is the request as the CLI resolved it, kept apart as `cli_model`,
    and the <synthetic> sentinel of its local notices is never a model.
    """

    def __init__(self, agent, task_id, run_id, model, effort):
        self.agent, self.task_id, self.run_id = agent, task_id, run_id
        self.requested = {"model": model, "effort": effort}
        self.started_at, self.ended_at = utc_now(), None
        self.cli_model, self.applied = None, None
        self.models, self.usage_models, self.model_source = [], [], None
        self.tool_ids, self.tool_calls = set(), 0
        self.api_error, self.notice, self.error_text = None, "", ""
        self.limit_rejected, self.rate_limit = False, None
        self.mismatch, self.warnings = None, []
        self.result, self.usage, self.exit_code, self.native_session = None, None, None, None
        self.finished, self.outcome, self.error = False, "running", None
        self.gateway = {"state": "unverified", "count": None, "source": None}

    # ── observation ──
    def provider_model(self, model, source):
        if not isinstance(model, str) or not model or model == SYNTHETIC_MODEL:
            return False
        if model not in self.models:
            self.models.append(model)
        self.model_source = self.model_source or source
        if model != self.requested["model"] and not self.mismatch:
            self.mismatch = model
        return True

    def tool_call(self, identifier):
        if identifier not in self.tool_ids:
            self.tool_ids.add(identifier)
            self.tool_calls += 1

    def observe_claude(self, record):
        kind = record.get("type")
        if kind == "system" and record.get("subtype") == "init":
            self.cli_model = record.get("model") if isinstance(record.get("model"), str) else None
        elif kind == "assistant":
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            self.provider_model(message.get("model"), "assistant.message.model")
            if isinstance(record.get("error"), str):
                self.api_error = record["error"][:64]
            blocks = message.get("content") if isinstance(message.get("content"), list) else []
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self.tool_call(block.get("id") or f"tool-{self.tool_calls}")
                elif isinstance(block, dict) and block.get("type") == "text" and (message.get("model") == SYNTHETIC_MODEL or record.get("error")):
                    self.notice = redact(block.get("text", ""))[:300]
        elif kind == "rate_limit_event":
            info = record.get("rate_limit_info") if isinstance(record.get("rate_limit_info"), dict) else {}
            self.rate_limit = {key: info.get(key) for key in ("status", "rateLimitType", "utilization", "resetsAt") if key in info}
            self.limit_rejected = self.limit_rejected or info.get("status") == "rejected"
        elif kind == "result":
            self.result = record
            usage_models = record.get("modelUsage") if isinstance(record.get("modelUsage"), dict) else {}
            self.usage_models = [name for name in usage_models if isinstance(name, str)]
            if self.usage_models and not self.model_source:
                self.model_source = "result.modelUsage"
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            self.usage = {key: usage[key] for key in ("input_tokens", "output_tokens") if isinstance(usage.get(key), int)} or None
            if isinstance(record.get("result"), str):
                self.error_text = redact(record["result"])[:300]

    def observe_codex(self, record):
        kind = record.get("type")
        if kind == "thread.started" and isinstance(record.get("thread_id"), str):
            self.native_session = record["thread_id"]
        elif kind in {"item.started", "item.updated", "item.completed"}:
            item = record.get("item") if isinstance(record.get("item"), dict) else {}
            if item.get("type") in CODEX_TOOL_ITEMS:
                self.tool_call(item.get("id") or f"item-{self.tool_calls}")
            elif item.get("type") == "error" and isinstance(item.get("message"), str):
                self.warnings.append(redact(item["message"])[:200])
        elif kind == "turn.completed":
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            self.usage = {key: usage[key] for key in ("input_tokens", "output_tokens") if isinstance(usage.get(key), int)} or None
            self.result = record
        elif kind in {"turn.failed", "error"}:
            payload = record.get("error") if isinstance(record.get("error"), dict) else record
            self.api_error = self.api_error or "turn_failed"
            self.error_text = redact(payload.get("message", ""))[:300] if isinstance(payload.get("message"), str) else self.error_text
            self.result = self.result or record
            info = payload.get("codex_error_info")
            if isinstance(info, str):
                self.api_error = info[:64]
            self.api_status = self.error_status(self.error_text)

    @staticmethod
    def error_status(text):
        """Codex wraps the provider error as JSON text: {"type":"error","status":400,"error":{...}}."""
        try:
            wrapped = json.loads(text)
        except ValueError:
            return None
        return wrapped.get("status") if isinstance(wrapped, dict) and isinstance(wrapped.get("status"), int) else None

    # ── classification ──
    def finish(self, exit_code=None, cancelled=False, failure=None):
        self.finished, self.exit_code, self.ended_at = True, exit_code, utc_now()
        result = self.result or {}
        failed_result = self.agent == "Claude" and claude_failed(result) if result else False
        limit_text = self.notice or self.error_text
        status = result.get("api_error_status") if self.agent == "Claude" else getattr(self, "api_status", None)
        is_limit = (self.limit_rejected or status == 429 or self.api_error in {"rate_limit", "usage_limit_exceeded"}
                    or bool(self.api_error and LIMIT_TEXT.search(limit_text)) or bool(failed_result and LIMIT_TEXT.search(limit_text)))
        if cancelled:
            self.outcome = "cancelled"
        elif self.mismatch and self.mismatch != self.requested["model"]:
            self.outcome, self.error = "model_mismatch", {"kind": "model_mismatch", "code": None,
                                                           "message": f"요청 {self.requested['model']}, 응답 {self.mismatch}"}
        elif is_limit:
            self.outcome, self.error = "usage_limit", {"kind": "usage_limit", "code": self.api_error or (str(status) if status else None),
                                                       "message": limit_text}
        elif self.api_error or failed_result or (self.agent == "Codex" and result.get("type") in {"turn.failed", "error"}):
            code = self.api_error or str(result.get("subtype") or result.get("terminal_reason") or "")
            self.outcome, self.error = "turn_error", {"kind": "turn_error", "code": code or None, "message": limit_text or code}
        elif failure or exit_code or not result:
            self.outcome, self.error = "task_failed", {"kind": "task_failed", "code": str(exit_code) if exit_code is not None else None,
                                                       "message": redact(failure or "완료 결과 레코드 없음")[:300]}
        else:
            self.outcome = "completed"

    def model_check(self):
        if self.mismatch and self.mismatch != self.requested["model"]:
            return "mismatch"
        return "confirmed" if self.requested["model"] in {*self.models, *self.usage_models} else "unreported"

    def record(self, phase):
        return {"run_id": self.run_id, "agent": self.agent, "task_id": self.task_id, "phase": phase, "updated_at": utc_now(),
                "started_at": self.started_at, "ended_at": self.ended_at, "requested": self.requested,
                "cli_model": self.cli_model, "applied": self.applied,
                "observed": {"models": self.models, "usage_models": self.usage_models, "source": self.model_source},
                "model_check": self.model_check(), "outcome": self.outcome, "error": self.error,
                "tool_calls": self.tool_calls, "no_tool_call": self.finished and self.tool_calls == 0,
                "rate_limit": self.rate_limit, "usage": self.usage, "exit_code": self.exit_code,
                "native_session_id": self.native_session, "warnings": self.warnings[:5], "gateway": self.gateway}

    def fingerprint(self):
        return (len(self.models), len(self.usage_models), self.api_error, self.limit_rejected, self.tool_calls // 5, self.finished)


def redact_deep(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_deep(item) for key, item in value.items()}
    return value


def validate_run(record):
    if not isinstance(record, dict):
        raise ValueError("Run must be an object")
    if record.get("agent") not in {"Claude", "Codex"} or record.get("outcome") not in OUTCOMES:
        raise ValueError("Invalid run agent or outcome")
    if record.get("model_check") not in MODEL_CHECKS or record.get("gateway", {}).get("state") not in GATEWAY_STATES:
        raise ValueError("Invalid run model check or gateway state")
    if not isinstance(record.get("run_id"), str) or not RUN_ID.fullmatch(record["run_id"]):
        raise ValueError("Invalid run id")
    if not isinstance(record.get("tool_calls"), int) or record["tool_calls"] < 0:
        raise ValueError("Invalid tool call count")
    return record


class RunLog:
    """Append-only run records; the last record of a run is its current state."""

    def __init__(self, path=RUNS_LOG):
        self.path = Path(path).resolve()
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def append(self, record):
        validate_run(record)
        payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(payload) > MAX_LINE:
            raise ValueError("Encoded run too long")
        append_line(self.path, self.lock_path, payload)
        return record

    def snapshot(self):
        runs, malformed = {}, 0
        if self.path.exists():
            with open(self.path, "rb") as stream:
                for line in stream:
                    if not line.endswith(b"\n"):
                        break
                    try:
                        record = validate_run(json.loads(line))
                    except (ValueError, UnicodeError):
                        malformed += 1
                        continue
                    runs[record["run_id"]] = redact_deep(record)
        ordered = sorted(runs.values(), key=lambda run: run.get("started_at") or "")
        return {"runs": ordered[-200:], "malformed_records": malformed, "server_time": utc_now()}

    def set_gateway(self, run_id, records, source):
        """The caller queried the gateway's own decision records for this run's window and passes what it found."""
        current = self.snapshot()["runs"]
        latest = next((run for run in reversed(current) if run["run_id"] == run_id), None)
        if latest is None:
            raise ValueError("Unknown run id")
        if records < 0:
            raise ValueError("records must be 0 or more")
        latest = {**latest, "phase": "gateway", "updated_at": utc_now(),
                  "gateway": {"state": "recorded" if records else "none", "count": records, "source": redact(source)[:200]}}
        return self.append(latest)


def codex_applied(thread_id):
    """The model and effort Codex put in the turn, from its own session file (the request as sent, not the answer)."""
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    if not isinstance(thread_id, str) or not re.fullmatch(r"[0-9a-f-]{20,64}", thread_id):
        return None
    for path in (home / "sessions").glob(f"**/rollout-*-{thread_id}.jsonl"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if '"turn_context"' not in line:
                        continue
                    payload = json.loads(line).get("payload") or {}
                    return {key: payload[key] for key in ("model", "effort") if isinstance(payload.get(key), str)} or None
        except (OSError, ValueError):
            return None
    return None


def private_raw(log, run_id):
    """Raw CLI output for audit. It stays under runtime/ (ignored by Git, never served by the viewer) and is not redacted."""
    directory = log.path.parent / "raw"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (re.sub(r"[^A-Za-z0-9_.-]", "_", run_id) + ".jsonl")
    stream = open(path, "a", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return stream


def find_codex_windows_executable():
    """The Windows Codex CLI installs each release under its own version directory; pick the one built most recently."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    candidates = list(Path(base).glob("OpenAI/Codex/bin/*/codex.exe"))
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def build_prefix(args):
    if args.prefix_file:
        prefix = json.loads(Path(args.prefix_file).read_text(encoding="utf-8-sig"))
        if not isinstance(prefix, list) or not prefix or not all(isinstance(item, str) and item for item in prefix):
            raise ValueError("Prefix file must be a nonempty JSON argument array")
        return prefix
    executable = args.executable or shutil.which(args.agent_cli) or shutil.which(args.agent_cli + ".cmd")
    if not executable and args.agent_cli == "codex":
        found = find_codex_windows_executable()
        executable = str(found) if found else None
    if not executable:
        raise ValueError(f"{args.agent_cli} CLI not found; pass --executable or --prefix-file")
    return [executable]


def run_cli(args, agent, command, prompt, requested_by):
    """Start one CLI run, record its events and its run record from the CLI's own output, return the exit code."""
    log = EventLog(args.log)
    runs = RunLog(Path(args.log).resolve().parent / "runs.jsonl")
    session_id = args.task_id + ":" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    model = MODEL if agent == "Claude" else args.model
    effort = EFFORT if agent == "Claude" else args.effort
    run = Run(agent, args.task_id, session_id, model, effort)
    log.append(requested_by, "message", args.task_id, "queued", prompt, session_id)
    log.append(agent, "task", args.task_id, "running", f"{agent} CLI 요청 시작 · 요청 {model} · 강도 {effort}. 응답 모델은 CLI 출력으로 별도 판정합니다.", session_id)
    runs.append(run.record("start"))
    print(f"{agent.upper()}_SESSION={session_id}", flush=True)
    stderr_lines, stopped = [], threading.Event()
    parse_errors, announced, last_native = 0, False, None
    process, raw = None, None
    seen, fingerprint = set(), run.fingerprint()
    try:
        raw = private_raw(log, session_id)
        process = subprocess.Popen(command, cwd=args.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                   shell=False, bufsize=1)

        def read_errors():
            for line in process.stderr:
                stderr_lines.append(redact(line.strip()))
                if len(stderr_lines) > 30:
                    stderr_lines.pop(0)

        def heartbeat():
            while not stopped.wait(20):
                if process.poll() is not None:
                    return
                log.append(agent, "task", args.task_id, "running", f"{agent} CLI 프로세스 실행 중 · 공개 출력 대기", session_id)

        errors_thread = threading.Thread(target=read_errors, daemon=True)
        errors_thread.start()
        threading.Thread(target=heartbeat, daemon=True).start()
        process.stdin.write(prompt)
        process.stdin.close()
        for line in process.stdout:
            raw.write(line)
            raw.flush()
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("Non-object output")
            except ValueError:
                parse_errors += 1
                continue
            if agent == "Claude":
                run.observe_claude(record)
                native = save_native_session(record, log, args.task_id, session_id)
                final = None
                if run.mismatch and run.mismatch != MODEL:
                    log.append("Claude", "check", args.task_id, "failed", f"요청 모델 불일치: 요청 {MODEL}, CLI 응답 {run.mismatch}. 자동 대체를 허용하지 않아 세션을 중단합니다.", session_id)
                    process.terminate()
                    raise RuntimeError("Claude returned a different model; no fallback allowed")
                if not announced and run.model_check() == "confirmed":
                    announced = True
                    log.append("Claude", "check", args.task_id, "passed", f"제공자 응답 모델 확인: {', '.join(run.models or run.usage_models)} ({run.model_source}). 강도 {EFFORT}는 요청 인자이며 서버 적용 여부는 이 출력으로 독립 확인할 수 없습니다.", session_id)
                final = visible_claude_event(record, log, args.task_id, seen, session_id)
                if final is not None:
                    run.result = final
            else:
                run.observe_codex(record)
                native = run.native_session
                codex_visible(record, log, args.task_id, seen, session_id)
            if native and native != last_native:
                print(f"{agent.upper()}_NATIVE_SESSION={native}", flush=True)
                last_native = native
            if run.fingerprint() != fingerprint:
                fingerprint = run.fingerprint()
                runs.append(run.record("update"))
        returncode = process.wait()
        stopped.set()
        errors_thread.join(timeout=2)
        if agent == "Codex":
            run.applied = codex_applied(run.native_session)
        failure = None
        if returncode != 0 and not run.result:
            failure = f"종료 코드 {returncode}" + (f" · stream-json 파싱 실패 {parse_errors}건" if parse_errors else "")
        run.finish(returncode, failure=failure)
        runs.append(run.record("final"))
        if run.outcome != "completed":
            label = {"usage_limit": "사용량 한도 오류", "turn_error": "턴 오류", "task_failed": "작업 실패"}.get(run.outcome, run.outcome)
            details = f"{label} · 종료 코드 {returncode}"
            if agent == "Claude" and run.result:
                details += f"\nCLI 결과 유형: {run.result.get('subtype', 'error')}"
                if run.result.get("subtype") == "error_max_turns":
                    details += f" · 최대 턴 제한 도달 ({getattr(args, 'max_turns', None)}턴). 네이티브 세션 UUID로 대화를 재개할 수 있습니다."
                if run.result.get("errors"):
                    details += "\n" + redact(json.dumps(run.result["errors"], ensure_ascii=False))
            if run.error and run.error.get("message"):
                details += "\n" + run.error["message"]
            if stderr_lines:
                details += "\n" + "\n".join(stderr_lines)
            raw_ref = f"runtime/raw/{Path(raw.name).name}" if raw else "없음"
            log.append(agent, "task", args.task_id, "failed", f"{agent} CLI 실패 · {details}\n원본 로그 {raw_ref}"[:MAX_BODY], session_id)
            return returncode or 1
        if run.tool_calls == 0:
            log.append(agent, "check", args.task_id, "failed", "도구 호출 0건: CLI 출력에 도구 호출 기록이 없습니다.", session_id)
        verdict = "제공자 응답 모델 확인" if run.model_check() == "confirmed" else "응답 모델 필드는 제공되지 않아 실제 모델은 미확인"
        raw_ref = f"runtime/raw/{Path(raw.name).name}" if raw else "없음"
        log.append(agent, "task", args.task_id, "completed", f"{agent} CLI 완료 · {verdict} · 도구 호출 {run.tool_calls}건 · 원본 로그 {raw_ref}", session_id)
        print(f"{agent.upper()}_RESULT=" + redact(str((run.result or {}).get("result", ""))), flush=True)
        return 0
    except (OSError, RuntimeError) as exc:
        run.finish(1, failure=str(exc))
        if run.mismatch and run.mismatch != run.requested["model"]:
            run.outcome = "model_mismatch"
        runs.append(run.record("final"))
        log.append(agent, "task", args.task_id, "failed", f"{agent} CLI 실행 실패: {redact(exc)}", session_id)
        print(redact(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        run.finish(130, cancelled=True)
        runs.append(run.record("final"))
        log.append(agent, "task", args.task_id, "cancelled", "CLI 실행 중 사용자/호출자의 중단 신호 수신", session_id)
        return 130
    finally:
        stopped.set()
        if raw:
            raw.close()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()


def codex_visible(record, log, task_id, seen, session_id):
    """Public Codex output only: the agent's message text and the kind of each tool call, never commands or results."""
    if record.get("type") != "item.completed" or not isinstance(record.get("item"), dict):
        return
    item = record["item"]
    key = (item.get("id"), item.get("type"))
    if key in seen:
        return
    seen.add(key)
    if item.get("type") == "agent_message" and isinstance(item.get("text"), str) and item["text"].strip():
        log.append("Codex", "message", task_id, "running", item["text"].strip()[:MAX_BODY], session_id)
    elif item.get("type") in CODEX_TOOL_ITEMS:
        log.append("Codex", "message", task_id, "running", f"도구 호출: {item['type']}", session_id)


def read_prompt(args):
    prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig") if args.prompt_file else sys.stdin.read()
    if not prompt.strip():
        raise ValueError("request stdin/prompt file must be nonempty")
    if len(prompt) > MAX_BODY:
        raise ValueError("Request too long for a visible collaboration record")
    return prompt


def run_claude(args):
    prompt = read_prompt(args)
    args.agent_cli = "claude"
    command = build_prefix(args) + ["-p", "--model", MODEL, "--effort", EFFORT, "--output-format", "stream-json", "--verbose"]
    if args.resume:
        try:
            command += ["--resume", str(UUID(args.resume))]
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("--resume must be the native Claude session UUID") from exc
    if args.allowed_tools:
        command += ["--tools", args.allowed_tools, "--allowedTools", args.allowed_tools]
    if args.max_turns:
        command += ["--max-turns", str(args.max_turns)]
    if args.permission_mode:
        command += ["--permission-mode", args.permission_mode]
    return run_cli(args, "Claude", command, prompt, getattr(args, "requested_by", None) or "Codex")


def run_codex(args):
    if not MODEL_NAME.fullmatch(args.model or "") or not EFFORT_NAME.fullmatch(args.effort or ""):
        raise ValueError("--model and --effort are required (a model name and a reasoning effort such as high)")
    prompt = read_prompt(args)
    args.agent_cli = "codex"
    resume = getattr(args, "resume", None)
    if resume and not re.fullmatch(r"[0-9a-f-]{20,64}", resume):
        raise ValueError("--resume must be the native Codex thread id (CODEX_NATIVE_SESSION)")
    command = build_prefix(args) + ["exec"] + (["resume", resume] if resume else [])
    command += ["--json", "--skip-git-repo-check", "-s", args.sandbox, "-m", args.model,
               "-c", f"model_reasoning_effort={args.effort}", "-C", args.cwd, "-"]
    return run_cli(args, "Codex", command, prompt, getattr(args, "requested_by", None) or "Claude")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the read-only viewer (collaboration log + WBS board)")
    serve.add_argument("--host", default="127.0.0.1", help="bind address; use the Tailscale IP to let teammates read it")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--log", default=str(DEFAULT_LOG))
    emit = sub.add_parser("emit", help="Append a visible message/task/check locally")
    emit.add_argument("--log", default=str(DEFAULT_LOG))
    emit.add_argument("--author", choices=sorted(AUTHORS), required=True)
    emit.add_argument("--kind", choices=sorted(KINDS), required=True)
    emit.add_argument("--task-id", required=True)
    emit.add_argument("--state", choices=sorted(STATES), required=True)
    body = emit.add_mutually_exclusive_group(required=True)
    body.add_argument("--body")
    body.add_argument("--body-file")
    body.add_argument("--stdin", action="store_true")
    emit.add_argument("--session-id")
    claude = sub.add_parser("claude", help="Run the explicitly requested Claude CLI and record its visible output")
    claude.add_argument("--log", default=str(DEFAULT_LOG))
    claude.add_argument("--task-id", required=True)
    claude.add_argument("--prompt-file")
    executable = claude.add_mutually_exclusive_group()
    executable.add_argument("--executable")
    executable.add_argument("--prefix-file", help="JSON argv array, for example WSL distribution + claude path")
    claude.add_argument("--cwd", default=str(ROOT.parents[1]))
    claude.add_argument("--allowed-tools")
    claude.add_argument("--max-turns", type=int)
    claude.add_argument("--resume", help="Resume the exact native Claude session UUID; not the run correlation ID")
    claude.add_argument("--permission-mode", choices=["default", "acceptEdits", "plan", "dontAsk"])
    claude.add_argument("--requested-by", choices=sorted(AUTHORS), default="Codex")
    codex = sub.add_parser("codex", help="Run the explicitly requested Codex CLI (exec --json) and record its visible output")
    codex.add_argument("--log", default=str(DEFAULT_LOG))
    codex.add_argument("--task-id", required=True)
    codex.add_argument("--prompt-file")
    codex.add_argument("--model", required=True, help="requested model name, passed to codex -m and recorded as requested")
    codex.add_argument("--effort", required=True, help="requested reasoning effort, passed as model_reasoning_effort")
    codex.add_argument("--sandbox", choices=["read-only", "workspace-write"], default="read-only")
    codex_executable = codex.add_mutually_exclusive_group()
    codex_executable.add_argument("--executable")
    codex_executable.add_argument("--prefix-file", help="JSON argv array, for example WSL distribution + codex path")
    codex.add_argument("-C", "--cwd", default=str(ROOT.parents[1]), help="worktree passed as codex's own -C/--cd and as the subprocess cwd")
    codex.add_argument("--resume", help="Resume the native Codex thread id printed as CODEX_NATIVE_SESSION")
    codex.add_argument("--requested-by", choices=sorted(AUTHORS), default="Claude")
    gateway = sub.add_parser("gateway-records", help="Attach what the gateway's own decision records show for a run")
    gateway.add_argument("--log", default=str(DEFAULT_LOG))
    gateway.add_argument("--run-id", required=True)
    gateway.add_argument("--count", type=int, required=True, help="decision records the gateway holds for this run's window (0 = none)")
    gateway.add_argument("--source", required=True, help="where the count came from, e.g. the decisions id range that was queried")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            if args.host in ("0.0.0.0", "::"):
                print(f"경고: {args.host}은 모든 네트워크 인터페이스에 공개합니다. Tailscale IP처럼 특정 주소에 바인딩하세요.", file=sys.stderr)
            server = make_server(args.host, args.port, EventLog(args.log))
            print(f"COLLABORATION_CONSOLE=http://{args.host}:{server.server_port}", flush=True)
            server.serve_forever(poll_interval=0.5)
        elif args.command == "emit":
            text = Path(args.body_file).read_text(encoding="utf-8-sig") if args.body_file else sys.stdin.read() if args.stdin else args.body
            event = EventLog(args.log).append(args.author, args.kind, args.task_id, args.state, text, args.session_id)
            print(json.dumps(event, ensure_ascii=False))
        elif args.command == "claude":
            return run_claude(args)
        elif args.command == "codex":
            return run_codex(args)
        elif args.command == "gateway-records":
            print(json.dumps(RunLog(Path(args.log).resolve().parent / "runs.jsonl").set_gateway(args.run_id, args.count, args.source), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        print(redact(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
