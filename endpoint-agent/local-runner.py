"""Run approved local MCP servers for the managed account (DEV-73, D-175). Linux, root.

managed-linux.py serve starts this in a thread. It asks the gateway for this device's jobs over
the device's outbound HTTPS, so nothing listens here, and it starts only manifests signed with
the key pinned at install - never one the gateway merely lists. The container runs as the
managed account's UID with no network, read-only root, no capabilities and only the approved
folders under that account's home.
"""
import base64
import hashlib
import json
import os
import pwd
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/:-]{0,200}@sha256:[0-9a-f]{64}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ENV_DENIED = re.compile(r"^(LD_|DYLD_|PYTHON|NODE_OPTIONS$|BASH_ENV$|ENV$|PATH$|HOME$)")
PROTOCOL = "2025-06-18"


def canonical(manifest):
    # Same bytes as gateway/app/local_jobs.canonical and field/sign-local-manifest.py.
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def signed(manifest, signature, public_pem):
    """openssl, not a Python crypto package: the root service keeps to the standard library."""
    if not public_pem:
        return False
    with tempfile.TemporaryDirectory() as folder:
        files = {"pub": public_pem.encode(), "body": canonical(manifest), "sig": base64.b64decode(signature, validate=True)}
        for name, content in files.items():
            Path(folder, name).write_bytes(content)
        result = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", f"{folder}/pub", "-rawin",
                                 "-in", f"{folder}/body", "-sigfile", f"{folder}/sig"], capture_output=True, timeout=10)
    return result.returncode == 0


def mounts(manifest, home):
    """Each approved folder, resolved now; a symlink anywhere on the path is refused."""
    options = []
    for item in manifest["mounts"]:
        path, mode = item["path"], item["mode"]
        parts = path.split("/")
        if (mode not in {"ro", "rw"} or path.startswith("/") or os.path.normpath(path) != path
                or any(p in {"", ".", ".."} or p.startswith(".") for p in parts)):
            raise ValueError("허용하지 않는 마운트 경로")
        target = os.path.join(home, path)
        if os.path.realpath(target) != target or not os.path.exists(target):
            raise ValueError("마운트 경로가 없거나 링크를 거칩니다")
        options += ["-v", f"{target}:{target}:{mode}"]
    return options


def container_command(engine, manifest, account):
    if not IMAGE.fullmatch(manifest["image"]):
        raise ValueError("digest로 고정하지 않은 이미지")
    env = manifest["env"]
    if not all(ENV_NAME.fullmatch(k) and not ENV_DENIED.match(k) for k in env):
        raise ValueError("허용하지 않는 환경 변수")
    name = f"mcpgw-local-{manifest['server_id']}-{account.pw_uid}"
    return name, [engine, "run", "--rm", "-i", "--name", name, "--label", "mcpgw.local=1", "--pull=never",
                  "--network=none", "--read-only", "--tmpfs", "/tmp:rw,size=64m", "--cap-drop=ALL",
                  "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=512m",
                  "--user", f"{account.pw_uid}:{account.pw_gid}",
                  *[x for k, v in sorted(env.items()) for x in ("-e", f"{k}={v}")],
                  *mounts(manifest, account.pw_dir), manifest["image"], *manifest["command"]]


class Session:
    """One stdio MCP session to one container; newline-delimited JSON-RPC (MCP stdio transport)."""

    def __init__(self, engine, manifest, account):
        self.engine = engine
        self.name, command = container_command(engine, manifest, account)
        if subprocess.run([engine, "image", "inspect", manifest["image"]], capture_output=True).returncode:
            subprocess.run([engine, "pull", manifest["image"]], capture_output=True, check=True, timeout=600)
        subprocess.run([engine, "rm", "-f", self.name], capture_output=True)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.lines, self.next_id, self.used = queue.Queue(), 0, time.monotonic()
        threading.Thread(target=self._read, daemon=True).start()
        self.hello = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                                  "clientInfo": {"name": "mint-local-runner", "version": "1"}}, 60)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params, timeout):
        self.next_id += 1
        ident = self.next_id
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        end = time.monotonic() + timeout
        while True:
            line = self.lines.get(timeout=max(0.1, end - time.monotonic()))
            if line is None:
                raise OSError("로컬 MCP 프로세스가 종료됐습니다")
            try:
                message = json.loads(line)
            except ValueError:
                continue  # a stray non-protocol line is not an answer
            if message.get("id") == ident and "method" not in message:
                if "error" in message:
                    raise RuntimeError(str(message["error"].get("message", "오류"))[:300])
                return message["result"]
            if "method" in message and "id" in message:
                # Sampling, roots or elicitation would reach past the gateway's decision: refuse them.
                self._send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "not supported"}})

    def alive(self):
        return self.process.poll() is None

    def stop(self):
        subprocess.run([self.engine, "rm", "-f", self.name], capture_output=True, timeout=30)
        self.process.kill()


def run(config, current_policy, request, log):
    """current_policy() returns the latest managed policy the serve loop fetched."""
    engine = shutil.which("podman") or shutil.which("docker")
    account = pwd.getpwnam(config["username"])
    sessions, verified = {}, set()
    while True:
        try:
            policy = current_policy() or {}
            approved = {item["server_id"]: item for item in policy.get("local_servers", [])}
            for item in approved.values():
                digest = hashlib.sha256(canonical(item["manifest"])).hexdigest()
                if (item["server_id"], digest) not in verified and engine and signed(
                        item["manifest"], item["signature"], config.get("manifest_pubkey", "")):
                    verified.add((item["server_id"], digest))
                    # Pull before the first call so a call's deadline is not spent downloading.
                    image = item["manifest"]["image"]
                    if IMAGE.fullmatch(image) and subprocess.run([engine, "image", "inspect", image], capture_output=True).returncode:
                        subprocess.run([engine, "pull", image], capture_output=True, timeout=600)
            # Withdrawn or changed; an observation of a server not yet registered lives one idle minute.
            for key in [k for k, v in sessions.items()
                        if (k[0] in approved and hashlib.sha256(canonical(approved[k[0]]["manifest"])).hexdigest() != k[1])
                        or (k[0] not in approved and time.monotonic() - v.used > 60)]:
                sessions.pop(key).stop()  # withdrawn or changed: the container goes with it
                log({"local_runner": "stopped", "server_id": key[0]})
            job = request(config, "/api/endpoint/local-jobs?wait=10").get("job")
            if not job:
                continue
            answer = {"error": "실행하지 않았습니다"}
            try:
                manifest, digest = job["manifest"], hashlib.sha256(canonical(job["manifest"])).hexdigest()
                if not engine:
                    raise ValueError("컨테이너 엔진이 없습니다")
                # The signature is the approval; the gateway only carries it. A first observation runs
                # before the server is in the policy, so the policy list is not the gate here.
                if digest != job["manifest_sha256"] or manifest.get("server_id") != job["server_id"]:
                    raise ValueError("서명된 승인 매니페스트가 아닙니다")
                if (job["server_id"], digest) not in verified:
                    if not signed(manifest, job["signature"], config.get("manifest_pubkey", "")):
                        raise ValueError("서명된 승인 매니페스트가 아닙니다")
                    verified.add((job["server_id"], digest))
                limit = max(1.0, datetime.fromisoformat(job["deadline"]).timestamp() - time.time())
                key = (job["server_id"], digest)
                if key not in sessions or not sessions[key].alive():
                    sessions[key] = Session(engine, manifest, account)
                session, params = sessions[key], job["params"] or {}
                session.used = time.monotonic()
                if job["method"] == "initialize":
                    answer = {"result": session.hello}
                elif job["method"] == "tools/list" and set(params) <= {"cursor"}:
                    answer = {"result": session.request("tools/list", params, limit)}
                elif job["method"] == "tools/call" and set(params) == {"name", "arguments"}:
                    answer = {"result": session.request("tools/call", params, limit)}
                else:
                    raise ValueError("허용하지 않는 요청")
            except (OSError, ValueError, RuntimeError, KeyError, queue.Empty, subprocess.SubprocessError) as exc:
                answer = {"error": str(exc)[:300] or type(exc).__name__}
            request(config, f"/api/endpoint/local-jobs/{job['id']}", answer)
        except (OSError, ValueError, KeyError) as exc:
            log({"local_runner": "error", "error": type(exc).__name__, "reason": str(exc)[:200]})
            time.sleep(5)
