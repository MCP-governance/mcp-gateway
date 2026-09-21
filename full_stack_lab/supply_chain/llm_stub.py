"""OpenAI 호환 스트리밍 stub. 배선 확인 전용이며 보안 판단을 하지 않는다.

mcp-scan은 `chat.completions.create(stream=True)`로 모델과 대화하므로, endpoint
설정·작업 큐·SARIF 파싱·결과 화면이 실제로 이어지는지 확인하려면 최소한 그
프로토콜을 말하는 상대가 필요하다. 이 stub은 고정 문장 하나를 흘려보낼 뿐이며
취약점을 찾지 않는다. 결과 화면이 모델 이름과 endpoint를 항상 함께 보여주는
이유가 이것이다. `llm-stub` profile로만 뜨고 기본 기동에는 포함되지 않는다.
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.getenv("LLM_STUB_PORT", "4010"))
def reply() -> str:
    path = os.getenv("LLM_STUB_REPLY_FILE", "").strip()
    if path:
        return Path(path).read_text(encoding="utf-8")
    return os.getenv(
        "LLM_STUB_REPLY",
        "This is a wiring stub, not a security review. No findings were produced.",
    )


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 요청 로그는 stdout 하나로 충분하다
        print("[llm-stub] " + fmt % args, flush=True)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [{"id": "wire-stub", "object": "model"}]})
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            request = {}
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json({"error": "not found"}, 404)
            return
        model = request.get("model") or "wire-stub"
        if not request.get("stream"):
            self._json({
                "id": "stub", "object": "chat.completion", "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply()}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def chunk(delta: dict, finish=None, usage=None) -> None:
            payload = {
                "id": "stub", "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if usage is not None:
                payload["usage"] = usage
            self.wfile.write(b"data: " + json.dumps(payload).encode() + b"\n\n")
            self.wfile.flush()

        chunk({"role": "assistant"})
        chunk({"content": reply()})
        chunk({}, finish="stop", usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    print(f"[llm-stub] listening on :{PORT} (wiring only, not a model)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
