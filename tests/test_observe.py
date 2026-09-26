import gzip
import json

import pytest

from mcp_gateway.observe import COPY_LIMIT, ResponseObserver, summarize_request


def rpc(method, id=None, **params):
    message = {"jsonrpc": "2.0", "method": method, "params": params}
    if id is not None:
        message["id"] = id
    return message


def test_tool_call_names_tool_and_keeps_arguments_only_when_asked():
    body = json.dumps(rpc("tools/call", 7, name="read_file", arguments={"path": "/etc/hosts"})).encode()
    summary = summarize_request(body)
    assert summary.parse == "ok"
    assert summary.methods == ["tools/call"]
    assert summary.tool == summary.target == "read_file"
    assert summary.ids == {"7"}
    assert summary.arguments is None
    assert json.loads(summarize_request(body, keep_arguments=True).arguments) == {"path": "/etc/hosts"}


def test_initialize_batch_notification_and_client_response():
    body = json.dumps([
        rpc("initialize", "a", protocolVersion="2025-11-25", clientInfo={"name": "claude-code", "version": "2.1"}),
        rpc("notifications/initialized"),
        {"jsonrpc": "2.0", "id": 5, "result": {}},
        rpc("resources/read", 1, uri="file:///notes.md"),
    ]).encode()
    summary = summarize_request(body)
    assert summary.methods == ["initialize", "notifications/initialized", "response", "resources/read"]
    assert summary.ids == {'"a"', "1"}
    assert (summary.client_name, summary.client_version, summary.protocol_version) == ("claude-code", "2.1", "2025-11-25")
    assert summary.target == "file:///notes.md"


@pytest.mark.parametrize("body,options,parse", [
    (b"", {}, "empty"), (b"not json", {}, "not_json"), (b"{}", {"truncated": True}, "truncated"),
    (b"\x1f\x8b", {"encoded": True}, "encoded"), (b"[1, 2]", {}, "ok"),
])
def test_request_parse_states(body, options, parse):
    summary = summarize_request(body, **options)
    assert summary.parse == parse
    assert summary.methods == []


def observe(content_type, chunks, ids=("1",), encoding=""):
    observer = ResponseObserver(content_type, encoding, set(ids))
    for chunk in chunks:
        observer.feed(chunk)
    return observer.finish()


def test_json_result_error_and_tool_error():
    assert observe("application/json", [b'{"jsonrpc":"2.0","id":1,"result":{"content":[]}}']).outcome == "ok"
    error = observe("application/json", [b'{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"bad params"}}'])
    assert (error.outcome, error.error_code, error.error_message) == ("rpc_error", -32602, "bad params")
    tool = observe("application/json; charset=utf-8",
                   [b'{"jsonrpc":"2.0","id":1,"result":{"isError":true,"content":[{"type":"text","text":"no such file"}]}}'])
    assert (tool.outcome, tool.error_message) == ("tool_error", "no such file")


def test_sse_split_across_chunks_with_crlf_and_server_messages():
    stream = (b'event: message\r\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\r\n\r\n'
              b'id: 9\r\ndata: {"jsonrpc":"2.0","id":1,\r\ndata: "result":{"content":[]}}\r\n\r\n')
    chunks = [stream[i:i + 7] for i in range(0, len(stream), 7)]
    summary = observe("text/event-stream", chunks)
    assert summary.outcome == "ok"
    assert summary.sse_events == 2
    assert summary.server_methods == ["notifications/progress"]


def test_stream_that_ends_before_the_answer_is_incomplete():
    summary = observe("text/event-stream", [b'data: {"jsonrpc":"2.0","method":"notifications/message"}\n\n'])
    assert summary.outcome == "incomplete"
    # A GET stream carries no request ids; nothing is owed, so nothing is incomplete.
    assert observe("text/event-stream", [b"data: {}\n\n"], ids=()).outcome is None


def test_gzip_copy_is_decoded_and_unknown_encoding_is_left_alone():
    payload = gzip.compress(b'{"jsonrpc":"2.0","id":1,"result":{}}')
    assert observe("application/json", [payload[:5], payload[5:]], encoding="gzip").outcome == "ok"
    assert observe("application/json", [b"\x00\x01"], encoding="br").parse == "encoded"


def test_oversized_copies_are_marked_not_guessed():
    big = b'{"jsonrpc":"2.0","id":1,"result":{"text":"' + b"x" * COPY_LIMIT + b'"}}'
    json_summary = observe("application/json", [big])
    assert (json_summary.parse, json_summary.outcome) == ("truncated", None)
    sse_summary = observe("text/event-stream", [b"data: " + big + b"\n\n"])
    assert sse_summary.parse == "truncated"
    assert sse_summary.sse_events == 1
