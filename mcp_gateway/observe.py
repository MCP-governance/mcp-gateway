"""Read copies of MCP traffic for the record. The relayed bytes are never touched.

Everything here works on duplicates of chunks that have already been sent on, so a
parse failure can only make the record less detailed, never change the traffic.
"""
from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field

# A copy larger than this is not parsed; the record says so instead of guessing.
COPY_LIMIT = 256 * 1024
ARGUMENT_LIMIT = 4096
TEXT_LIMIT = 300
SERVER_METHOD_LIMIT = 20


def _id_key(value) -> str:
    # JSON-RPC ids may be strings or numbers; 1 and "1" are different requests.
    return json.dumps(value, sort_keys=True)


def _text(value, limit=TEXT_LIMIT) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit - 1] + "…"


@dataclass
class RequestSummary:
    parse: str = "empty"  # empty | ok | not_json | truncated | encoded
    methods: list[str] = field(default_factory=list)
    ids: set[str] = field(default_factory=set)
    tool: str | None = None
    target: str | None = None
    arguments: str | None = None
    client_name: str | None = None
    client_version: str | None = None
    protocol_version: str | None = None


def summarize_request(body: bytes, *, truncated: bool = False, encoded: bool = False,
                      keep_arguments: bool = False) -> RequestSummary:
    summary = RequestSummary()
    if encoded:
        summary.parse = "encoded"
        return summary
    if truncated:
        summary.parse = "truncated"
        return summary
    if not body.strip():
        return summary
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        summary.parse = "not_json"
        return summary
    summary.parse = "ok"
    for message in document if isinstance(document, list) else [document]:
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        if not isinstance(method, str):
            # The client answering a server request (sampling, elicitation, roots).
            summary.methods.append("response")
            continue
        summary.methods.append(method[:100])
        if "id" in message:
            summary.ids.add(_id_key(message["id"]))
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "tools/call" and summary.tool is None:
            summary.tool = _text(params.get("name"), 200)
            summary.target = summary.tool
            if keep_arguments and "arguments" in params:
                summary.arguments = _text(params["arguments"], ARGUMENT_LIMIT)
        elif method == "resources/read" and summary.target is None:
            summary.target = _text(params.get("uri"), 500)
        elif method == "prompts/get" and summary.target is None:
            summary.target = _text(params.get("name"), 200)
        elif method == "initialize":
            client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
            summary.client_name = _text(client.get("name"), 100)
            summary.client_version = _text(client.get("version"), 50)
            summary.protocol_version = _text(params.get("protocolVersion"), 30)
    return summary


class _Decoder:
    """Undo gzip/deflate on the copy. Other encodings are left unparsed."""

    def __init__(self, encoding: str):
        encoding = encoding.strip().lower()
        self.supported = encoding in ("", "identity", "gzip", "x-gzip", "deflate")
        wbits = 31 if "gzip" in encoding else zlib.MAX_WBITS
        self.inflate = zlib.decompressobj(wbits) if encoding not in ("", "identity") else None
        self.raw_deflate = encoding == "deflate"

    def feed(self, chunk: bytes) -> bytes:
        if self.inflate is None:
            return chunk
        try:
            return self.inflate.decompress(chunk)
        except zlib.error:
            if self.raw_deflate:
                # Some servers send raw deflate without the zlib header.
                self.inflate, self.raw_deflate = zlib.decompressobj(-zlib.MAX_WBITS), False
                return self.feed(chunk)
            self.supported = False
            return b""


@dataclass
class ResponseSummary:
    parse: str = "none"  # none | ok | not_json | truncated | encoded
    outcome: str | None = None  # ok | tool_error | rpc_error | incomplete
    error_code: int | None = None
    error_message: str | None = None
    sse_events: int = 0
    server_methods: list[str] = field(default_factory=list)


class ResponseObserver:
    """Follows a JSON or SSE response through copies of its raw chunks."""

    def __init__(self, content_type: str, content_encoding: str, request_ids: set[str]):
        media = content_type.split(";")[0].strip().lower()
        self.sse = media == "text/event-stream"
        self.json = media == "application/json" or media.endswith("+json")
        self.decoder = _Decoder(content_encoding)
        self.pending = set(request_ids)
        self.answered: set[str] = set()
        self.summary = ResponseSummary()
        self.buffer = bytearray()
        self.event: list[bytes] = []
        self.event_size = 0
        self.overflow = False

    def feed(self, chunk: bytes) -> None:
        if not (self.sse or self.json) or not self.decoder.supported:
            return
        data = self.decoder.feed(chunk)
        if self.json:
            if len(self.buffer) + len(data) > COPY_LIMIT:
                self.overflow = True
                self.buffer.clear()
            elif not self.overflow:
                self.buffer += data
            return
        self.buffer += data
        # SSE lines end with CRLF, LF or CR; a lone trailing CR may be half of CRLF.
        while True:
            ends = [i for i in (self.buffer.find(b"\n"), self.buffer.find(b"\r")) if i >= 0]
            cut = min(ends) if ends else -1
            if cut < 0 or (self.buffer[cut] == 13 and cut == len(self.buffer) - 1):
                break
            line = bytes(self.buffer[:cut])
            step = 2 if self.buffer[cut:cut + 2] == b"\r\n" else 1
            del self.buffer[:cut + step]
            self._line(line)
        if len(self.buffer) > COPY_LIMIT:
            self.buffer.clear()
            self.overflow = True

    def _line(self, line: bytes) -> None:
        if not line:
            if self.event:
                self.summary.sse_events += 1
                if self.event_size <= COPY_LIMIT:
                    self._message(b"\n".join(self.event))
                else:
                    self.overflow = True
            self.event, self.event_size = [], 0
            return
        if line.startswith(b"data:"):
            value = line[5:]
            value = value[1:] if value.startswith(b" ") else value
            self.event_size += len(value)
            if self.event_size <= COPY_LIMIT:
                self.event.append(value)
            else:
                self.event = [b""]

    def _message(self, payload: bytes) -> None:
        try:
            document = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            self.summary.parse = "not_json"
            return
        if self.summary.parse == "none":
            self.summary.parse = "ok"
        for message in document if isinstance(document, list) else [document]:
            if not isinstance(message, dict):
                continue
            method = message.get("method")
            if isinstance(method, str):
                # A server request or notification on the stream (progress, sampling, ...).
                if method not in self.summary.server_methods and len(self.summary.server_methods) < SERVER_METHOD_LIMIT:
                    self.summary.server_methods.append(method[:100])
                continue
            key = _id_key(message.get("id"))
            if key not in self.pending:
                continue
            self.pending.discard(key)
            self.answered.add(key)
            error = message.get("error")
            result = message.get("result")
            if isinstance(error, dict):
                self._worse("rpc_error")
                if self.summary.error_code is None:
                    code = error.get("code")
                    self.summary.error_code = code if isinstance(code, int) and not isinstance(code, bool) else None
                    self.summary.error_message = _text(error.get("message"))
            elif isinstance(result, dict) and result.get("isError") is True:
                self._worse("tool_error")
                if self.summary.error_message is None:
                    self.summary.error_message = _tool_error_text(result)
            else:
                self._worse("ok")

    def _worse(self, outcome: str) -> None:
        rank = {None: 0, "ok": 1, "tool_error": 2, "rpc_error": 3}
        if rank[outcome] > rank[self.summary.outcome]:
            self.summary.outcome = outcome

    def finish(self) -> ResponseSummary:
        if not self.decoder.supported:
            self.summary.parse = "encoded"
        elif self.json and not self.overflow and self.buffer:
            self._message(bytes(self.buffer))
        elif self.sse and self.event:
            # A stream cut mid-event still counts what it delivered.
            self._line(b"")
        if self.overflow and self.summary.parse in ("none", "ok"):
            self.summary.parse = "truncated"
        if self.pending and (self.answered or self.sse or self.json) and self.summary.parse != "truncated":
            self.summary.outcome = "incomplete" if self.summary.outcome in (None, "ok") else self.summary.outcome
        return self.summary


def _tool_error_text(result: dict) -> str | None:
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            return _text(item.get("text"))
    return None
