import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn


@pytest.fixture
def live_server():
    @contextmanager
    def start(app):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            app, log_level="warning", access_log=False, timeout_graceful_shutdown=2,
        ))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        try:
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started, "test HTTP server did not start"
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            listener.close()
            assert not thread.is_alive(), "test HTTP server did not stop"

    return start
