"""DEV-35 loopback lab: runs inside a throwaway container (own netns) on the PJ1 kernel.
Renders the kit's nft_rules() for a managed UID, then checks who can reach whom on loopback,
with the current rules and with the proposed owner-initiated reply rule."""
import importlib.util, os, socket, subprocess, sys, time

spec = importlib.util.spec_from_file_location("enforce", "/lab/enforce-linux.py")
enforce = importlib.util.module_from_spec(spec); spec.loader.exec_module(enforce)

OWNER, MANAGED, FOREIGN = 1000, 1001, 1002
# One ct mark bit outside Tailscale's 0xff0000 connmark field (PJ1 ip mangle), set with OR.
MARK = "0x00000100"
PROPOSED = (f'oifname "lo" ct direction original ct state new meta skuid {OWNER} ct mark set ct mark or {MARK}\n'
            f'meta skuid {MANAGED} oifname "lo" ct direction reply ct mark and {MARK} == {MARK} accept\n')

def load(extra=""):
    text = enforce.nft_rules(MANAGED, ["192.0.2.10"], 443, 3128)
    if extra:  # proposed rules go before the managed accept/deny lines
        head, rest = text.split("policy accept;\n", 1)
        text = head + "policy accept;\n" + extra + rest
    open("/tmp/r.nft", "w").write(text)
    subprocess.run(["nft", "-f", "/tmp/r.nft"], check=True)
    return text

SERVER = r'''
import socket, sys, os
fam = socket.AF_INET6 if ":" in sys.argv[1] else socket.AF_INET
kind = socket.SOCK_DGRAM if sys.argv[3] == "udp" else socket.SOCK_STREAM
s = socket.socket(fam, kind); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((sys.argv[1], int(sys.argv[2])))
open("/tmp/ready-" + sys.argv[2], "w").close()
if kind == socket.SOCK_STREAM:
    s.listen(5); s.settimeout(6)
    try:
        c, _ = s.accept(); data = c.recv(100); c.sendall(b"pong:" + data); c.close()
    except Exception: pass
else:
    s.settimeout(6)
    try:
        data, peer = s.recvfrom(100); open("/tmp/udp-" + sys.argv[2], "wb").write(data)
    except Exception: pass
'''
CLIENT = r'''
import socket, sys
fam = socket.AF_INET6 if ":" in sys.argv[1] else socket.AF_INET
if sys.argv[3] == "udp":
    s = socket.socket(fam, socket.SOCK_DGRAM)
    try: s.sendto(b"ping", (sys.argv[1], int(sys.argv[2]))); print("sent")
    except Exception as e: print("ERR", type(e).__name__, e)
else:
    s = socket.socket(fam, socket.SOCK_STREAM); s.settimeout(4)
    try:
        s.connect((sys.argv[1], int(sys.argv[2]))); s.sendall(b"ping"); print(s.recv(100).decode())
    except Exception as e: print("ERR", type(e).__name__, e)
'''
open("/tmp/srv.py", "w").write(SERVER); open("/tmp/cli.py", "w").write(CLIENT)

def as_uid(uid, *args, **kw):
    return subprocess.Popen(["setpriv", f"--reuid={uid}", f"--regid={uid}", "--clear-groups", "python3", *args],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)

port = [20000]
def case(name, client, server, addr="127.0.0.1", proto="tcp"):
    port[0] += 1; p = port[0]
    srv = as_uid(server, "/tmp/srv.py", addr, str(p), proto)
    for _ in range(50):
        if os.path.exists(f"/tmp/ready-{p}"): break
        time.sleep(0.05)
    out = as_uid(client, "/tmp/cli.py", addr, str(p), proto).communicate(timeout=10)[0].strip()
    srv.wait(timeout=10)
    if proto == "udp":
        ok = os.path.exists(f"/tmp/udp-{p}")
    else:
        ok = out.startswith("pong:")
    print(f"  {'REACH ' if ok else 'BLOCK '} {name:<52} {addr:<10} {proto}  [{out[:60]}]")
    return ok

def run_all(label):
    print(f"== {label}")
    r = {}
    r["owner->managed"] = case("owner(1000) -> managed listener (login callback)", OWNER, MANAGED)
    r["owner->managed6"] = case("owner(1000) -> managed listener", OWNER, MANAGED, "::1")
    r["managed->managed"] = case("managed -> managed listener (Codex /cancel)", MANAGED, MANAGED)
    r["managed->owner"] = case("managed -> owner listener (E13 local MCP)", MANAGED, OWNER)
    r["managed->owner6"] = case("managed -> owner listener (E13 local MCP)", MANAGED, OWNER, "::1")
    r["managed->foreign"] = case("managed -> foreign(1002) listener (E13)", MANAGED, FOREIGN)
    r["managed->owner-udp"] = case("managed -> owner UDP listener (E13)", MANAGED, OWNER, proto="udp")
    r["foreign->managed"] = case("foreign(1002) -> managed listener", FOREIGN, MANAGED)
    r["owner->owner"] = case("owner -> owner listener (unmanaged control)", OWNER, OWNER)
    return r

load(); cur = run_all("current kit rules (enforce-linux.py nft_rules)")
subprocess.run(["sh", "-c", "dmesg 2>/dev/null | grep MCPGW_DENY | tail -3"])
text = load(PROPOSED); prop = run_all("proposed: owner-initiated reply on lo")
print(text)
# E13 invariant: managed UID never reaches a listener it does not own, before or after.
for k in ("managed->owner", "managed->owner6", "managed->foreign", "managed->owner-udp"):
    assert not cur[k] and not prop[k], k
assert prop["owner->managed"] and prop["owner->managed6"] and not cur["owner->managed"]
assert not prop["foreign->managed"] and prop["owner->owner"]
print("LAB OK")
