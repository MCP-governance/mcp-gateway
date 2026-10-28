"""Kit login and approved source transfer; device credentials stay in the service."""
import contextlib
import hashlib
import json
import os
import re
import socket
import tempfile
import threading
import urllib.request
import urllib.error
from pathlib import Path

MAX_BYTES = 128 << 20
SLOTS = threading.BoundedSemaphore(2)


class LoginError(ValueError):
    def __init__(self, reason):
        self.kit_reason = reason
        super().__init__(reason)


def login(bundle, request, inputs):
    address, username, password = inputs(bundle["gateway_url"])
    config = dict(bundle, gateway_url=address.strip().rstrip("/"))
    try:
        grant = request(config, "/auth/kit-enrollment", {"email": username, "password": password}, credential=False)
    except urllib.error.HTTPError as exc:
        reason = {401: "로그인: 아이디·비밀번호 확인 필요", 403: "로그인: 계정 잠김·승인 확인 필요",
                  429: "로그인: 시도 제한"}.get(exc.code, "로그인: 연결 실패")
        if exc.code == 403:
            try:
                if "승인" in json.loads(exc.read(8192)).get("detail", ""):
                    reason = "로그인: 관리자 승인 대기"
            except (ValueError, AttributeError):
                pass
        raise LoginError(reason) from None
    except OSError:
        raise LoginError("로그인: 네트워크 연결 실패") from None
    finally:
        password = None
    if not isinstance(grant, dict) or not isinstance(grant.get("enrollment_token"), str):
        raise ValueError("로그인 응답 확인 필요")
    return {**config, **{k: grant[k] for k in ("enrollment_token", "expires_at") if k in grant}}


def source_path(command):
    if not isinstance(command, dict):
        raise ValueError("소스 요청 확인 필요")
    if command == {"action": "list"}:
        return "/api/endpoint/approved-mcp"
    server, commit = command.get("server", ""), command.get("commit", "")
    if (command.get("action") != "download" or not isinstance(server, str) or not isinstance(commit, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", server)
            or not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ValueError("승인된 소스 확인 필요")
    return f"/api/endpoint/approved-mcp/{server}/source?commit={commit}"


def serve_source(config, command, transport, send):
    """Only approved list/archive paths, bounded and verified before crossing the local broker."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("주소 변경 거부")
    try:
        path = source_path(command)
        context = transport(config)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                            urllib.request.HTTPSHandler(context=context))
        request = urllib.request.Request(config["gateway_url"] + path,
            headers={"X-Endpoint-Key": config["device_key"], "Accept-Encoding": "identity"})
        with SLOTS, tempfile.SpooledTemporaryFile(max_size=4 << 20) as spool:
            with opener.open(request, timeout=130) as response:
                digest, size = hashlib.sha256(), 0
                limit = 1 << 20 if command["action"] == "list" else MAX_BYTES
                while block := response.read(64 << 10):
                    size += len(block)
                    if size > limit:
                        raise ValueError("소스 크기 상한 초과")
                    digest.update(block)
                    spool.write(block)
                sha = response.headers.get("X-Content-SHA256", "")
                if command["action"] == "download" and (not re.fullmatch(r"[0-9a-f]{64}", sha) or sha != digest.hexdigest()):
                    raise ValueError("소스 검증 실패")
            spool.seek(0)
            send((json.dumps({"size": size, "sha256": sha or digest.hexdigest()}) + "\n").encode())
            while block := spool.read(64 << 10):
                send(block)
    except (OSError, ValueError, KeyError, TypeError):
        send(b'{"error":"source unavailable"}\n')


@contextlib.contextmanager
def broker(address):
    if os.name == "nt":
        descriptor = os.open(address, os.O_RDWR | os.O_BINARY)
        with os.fdopen(descriptor, "r+b", buffering=0) as stream:
            yield stream
    else:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(140)
            connection.connect(address)
            with connection.makefile("rwb", buffering=0) as stream:
                yield stream


def receive(address, command, folder=None):
    source_path(command)
    with broker(address) as stream:
        payload = (json.dumps(command) + "\n").encode()
        # Raw named pipes and sockets may complete a write only partially.
        while payload:
            sent = stream.write(payload)
            if not sent:
                raise OSError("소스 연결 실패")
            payload = payload[sent:]
        header = json.loads(stream.readline(8192))
        size, sha = header.get("size"), header.get("sha256", "")
        if type(size) is not int or not 0 < size <= MAX_BYTES or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("승인된 MCP 확인 실패")
        if command["action"] == "list":
            if size > 1 << 20:
                raise ValueError("목록 크기 상한 초과")
            output = bytearray()
            while len(output) < size:
                block = stream.read(min(64 << 10, size - len(output)))
                if not block:
                    raise ValueError("목록 수신 실패")
                output.extend(block)
            if hashlib.sha256(output).hexdigest() != sha:
                raise ValueError("목록 검증 실패")
            return json.loads(output)["servers"]
        folder = Path(folder) if folder else Path.home() / "MINT" / "소스"
        folder.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".mint-", dir=folder)
        try:
            digest, remaining = hashlib.sha256(), size
            with os.fdopen(descriptor, "wb") as output:
                while remaining:
                    block = stream.read(min(64 << 10, remaining))
                    if not block:
                        raise ValueError("소스 수신 실패")
                    remaining -= len(block)
                    digest.update(block)
                    output.write(block)
            if digest.hexdigest() != sha:
                raise ValueError("소스 검증 실패")
            target = folder / f"{command['server']}-{command['commit'][:12]}.zip"
            os.replace(temporary, target)
            return str(target)
        finally:
            Path(temporary).unlink(missing_ok=True)
