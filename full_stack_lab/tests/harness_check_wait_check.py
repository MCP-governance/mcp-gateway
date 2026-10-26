"""harness-check의 응답 대기(converse): 응답이 오면 바로 끝나고, 침묵하면 상한에서 실패하며,
명령이 없거나 응답 없이 죽으면 실패로 돌아오는지 가짜 서버로 확인한다."""
import importlib.machinery
import importlib.util
import os
import pathlib
import sys
import time

BIN = pathlib.Path(__file__).resolve().parents[1] / "workstation" / "bin" / "harness-check"

os.environ.setdefault("WORKSTATION_ID", "ws-test")
_read = pathlib.Path.read_text
pathlib.Path.read_text = lambda self, *a, **k: "a b" if str(self).replace("\\", "/") == "/etc/bob/servers" else _read(self, *a, **k)
loader = importlib.machinery.SourceFileLoader("harness_check", str(BIN))
mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("harness_check", loader))
loader.exec_module(mod)
pathlib.Path.read_text = _read

PY = sys.executable
REPLY = 'import sys,time;sys.stdin.readline();print(\'{"id":2,"result":{"data":[]}}\',flush=True);%s'


def timed(command, limit):
    start = time.monotonic()
    message, out = mod.converse(command, ['{"id":2}'], 2, limit)
    return message, out, time.monotonic() - start


# 응답이 오면 서버가 stdin을 닫지 않고 계속 살아 있어도 바로 끝난다.
message, _, took = timed([PY, "-c", REPLY % "time.sleep(30)"], 20)
assert message and message["id"] == 2 and took < 10, (message, took)

# 다른 id만 오면 상한까지 기다린 뒤 실패.
message, out, took = timed([PY, "-c", 'import time;print(\'{"id":1}\',flush=True);time.sleep(30)'], 1.5)
assert message is None and 1.4 <= took < 10 and '"id":1' in out, (message, out, took)

# 침묵하는 서버도 상한에서 실패.
message, _, took = timed([PY, "-c", "import time;time.sleep(30)"], 1.5)
assert message is None and 1.4 <= took < 10, (message, took)

# 응답 없이 종료하면 상한을 기다리지 않고 실패.
message, _, took = timed([PY, "-c", "pass"], 20)
assert message is None and took < 10, (message, took)

# 실행 파일이 없으면 실패로 돌아온다(예외로 죽지 않음).
message, out, took = timed(["/nonexistent/codex-app-server"], 20)
assert message is None and out.startswith("error:"), (message, out)

# 파싱 안 되는 줄이 섞여도 id 2 응답을 찾는다.
message, _, _ = timed([PY, "-c", "import sys;sys.stdin.readline();print('log noise',flush=True);print('{\"id\":2}',flush=True)"], 20)
assert message == {"id": 2}, message

print("harness_check_wait_check: ok")
