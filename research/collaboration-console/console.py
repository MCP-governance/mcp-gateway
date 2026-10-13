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
DEFAULT_LOG = ROOT / "runtime" / "events.jsonl"
AUTHORS = {"Codex", "Claude", "User", "System"}
KINDS = {"message", "task", "check"}
STATES = {"queued", "running", "waiting", "completed", "passed", "failed", "blocked", "cancelled"}
MAX_BODY = 48_000
MAX_LINE = MAX_BODY * 4 + 4096
MODEL = "claude-sonnet-5-5"
EFFORT = "xhigh"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact(value):
    """Suppress common credentials before either disk storage or HTTP output."""
    text = str(value)
    text = re.sub(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", text)
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One-byte OS lock serializes independent Codex/Claude recorder processes.
        with open(self.lock_path, "a+b") as lock:
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
                with open(self.path, "a+b") as stream:
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
        valid_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host", "") not in valid_hosts:
            self.respond(403, b'{"error":"Local host required"}')
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in valid_hosts}:
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
        elif url.path == "/health":
            self.respond(200, b'{"status":"ok","mode":"read-only","bind":"127.0.0.1"}')
        else:
            self.respond(404, b'{"error":"Not found"}')

    def do_POST(self):
        self.respond(405, b'{"error":"Read-only viewer; use the local emit CLI"}')


def make_server(port, log):
    server = ThreadingHTTPServer(("127.0.0.1", port), Viewer)
    server.event_log = log
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
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return native_session


def run_claude(args):
    log = EventLog(args.log)
    prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig") if args.prompt_file else sys.stdin.read()
    if not prompt.strip():
        raise ValueError("Claude request stdin/prompt file must be nonempty")
    if len(prompt) > MAX_BODY:
        raise ValueError("Request too long for a visible collaboration record")
    if args.prefix_file:
        prefix = json.loads(Path(args.prefix_file).read_text(encoding="utf-8-sig"))
        if not isinstance(prefix, list) or not prefix or not all(isinstance(item, str) and item for item in prefix):
            raise ValueError("Prefix file must be a nonempty JSON argument array")
    else:
        executable = args.executable or shutil.which("claude") or shutil.which("claude.cmd")
        if not executable:
            raise ValueError("Claude CLI not found; pass --executable or --prefix-file")
        prefix = [executable]
    command = prefix + ["-p", "--model", MODEL, "--effort", EFFORT,
                        "--output-format", "stream-json", "--verbose"]
    if args.resume:
        try:
            resume_id = str(UUID(args.resume))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("--resume must be the native Claude session UUID") from exc
        command += ["--resume", resume_id]
    if args.allowed_tools:
        command += ["--tools", args.allowed_tools, "--allowedTools", args.allowed_tools]
    if args.max_turns:
        command += ["--max-turns", str(args.max_turns)]
    if args.permission_mode:
        command += ["--permission-mode", args.permission_mode]
    session_id = args.task_id + ":" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log.append("Codex", "message", args.task_id, "queued", prompt, session_id)
    log.append("Claude", "task", args.task_id, "running", f"Claude CLI 요청 시작 · {MODEL} · effort {EFFORT}. 모델 사용 확인은 CLI 응답으로 별도 판정합니다.", session_id)
    print(f"CLAUDE_SESSION={session_id}", flush=True)
    stderr_lines, stopped = [], threading.Event()
    result, parse_errors, confirmed_model, last_native_session = None, 0, False, None
    process = None
    try:
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
                log.append("Claude", "task", args.task_id, "running", "Claude CLI 프로세스 실행 중 · 공개 출력 대기", session_id)

        errors_thread = threading.Thread(target=read_errors, daemon=True)
        errors_thread.start()
        threading.Thread(target=heartbeat, daemon=True).start()
        process.stdin.write(prompt)
        process.stdin.close()
        seen = set()
        for line in process.stdout:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("Non-object output")
            except ValueError:
                parse_errors += 1
                continue
            native_session = save_native_session(record, log, args.task_id, session_id)
            if native_session and native_session != last_native_session:
                print(f"CLAUDE_NATIVE_SESSION={native_session}", flush=True)
                last_native_session = native_session
            message = record.get("message", {})
            actual_model = record.get("model") if record.get("type") == "system" else message.get("model") if isinstance(message, dict) else None
            # Claude Code uses this literal sentinel for local runtime messages, not provider output.
            if actual_model and actual_model != "<synthetic>":
                if actual_model != MODEL:
                    log.append("Claude", "check", args.task_id, "failed", f"요청 모델 불일치: 요청 {MODEL}, CLI 응답 {actual_model}. 자동 대체를 허용하지 않아 세션을 중단합니다.", session_id)
                    process.terminate()
                    raise RuntimeError("Claude returned a different model; no fallback allowed")
                if not confirmed_model:
                    confirmed_model = True
                    log.append("Claude", "check", args.task_id, "passed", f"CLI 모델 응답 확인: {actual_model}. effort {EFFORT}는 요청 인자이며 서버 적용 여부는 이 출력으로 독립 확인할 수 없습니다.", session_id)
            final = visible_claude_event(record, log, args.task_id, seen, session_id)
            if final is not None:
                result = final
        returncode = process.wait()
        stopped.set()
        errors_thread.join(timeout=2)
        if returncode != 0 or result is None or claude_failed(result):
            if result is not None:
                details = f"CLI 결과 유형: {result.get('subtype', 'error')}"
                if result.get("subtype") == "error_max_turns":
                    details += f" · 최대 턴 제한 도달 ({args.max_turns}턴). 네이티브 세션 UUID로 대화를 재개할 수 있습니다."
                if result.get("errors"):
                    details += "\n" + redact(json.dumps(result["errors"], ensure_ascii=False))
                if isinstance(result.get("result"), str) and result["result"].strip():
                    details += "\n" + redact(result["result"])
            else:
                details = f"stream-json 파싱 실패 {parse_errors}건" if parse_errors else "완료 결과 레코드 없음"
            if stderr_lines:
                details += "\n" + "\n".join(stderr_lines)
            log.append("Claude", "task", args.task_id, "failed", f"Claude CLI 실패 · 종료 코드 {returncode}\n{details}"[:MAX_BODY], session_id)
            return returncode or 1
        log.append("Claude", "task", args.task_id, "completed", "Claude CLI 완료 · 모델 응답 확인" if confirmed_model else "Claude CLI 완료 · 모델 응답 필드는 제공되지 않아 실제 모델은 미확인", session_id)
        print("CLAUDE_RESULT=" + redact(str(result.get("result", ""))), flush=True)
        return 0
    except (OSError, RuntimeError) as exc:
        log.append("Claude", "task", args.task_id, "failed", f"Claude CLI 실행 실패: {redact(exc)}", session_id)
        print(redact(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        log.append("Claude", "task", args.task_id, "cancelled", "CLI 실행 중 사용자/호출자의 중단 신호 수신", session_id)
        return 130
    finally:
        stopped.set()
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start localhost read-only viewer")
    serve.add_argument("--port", type=int, default=18766)
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
    args = parser.parse_args()
    try:
        if args.command == "serve":
            server = make_server(args.port, EventLog(args.log))
            print(f"COLLABORATION_CONSOLE=http://127.0.0.1:{server.server_port}", flush=True)
            server.serve_forever(poll_interval=0.5)
        elif args.command == "emit":
            text = Path(args.body_file).read_text(encoding="utf-8-sig") if args.body_file else sys.stdin.read() if args.stdin else args.body
            event = EventLog(args.log).append(args.author, args.kind, args.task_id, args.state, text, args.session_id)
            print(json.dumps(event, ensure_ascii=False))
        elif args.command == "claude":
            return run_claude(args)
    except (OSError, ValueError) as exc:
        print(redact(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
