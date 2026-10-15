"""DEV-35 lab, rejected options: show the counterexample for each (throwaway container, own netns)."""
import os, subprocess, sys, time
sys.argv = ["lab"]
exec(open("/lab/lab.py").read().split("load(); cur = run_all")[0])  # reuse helpers, skip the main run

PORT = (f'meta skuid {MANAGED} oifname "lo" tcp dport {{ 1455, 1457 }} accept\n'
        f'meta skuid {MANAGED} oifname "lo" tcp sport {{ 1455, 1457 }} accept\n')
# Same-UID approximation: let the managed SYN out, then refuse replies that come from another UID.
SAME = (f'oifname "lo" ct direction original ct state new meta skuid {MANAGED} meta l4proto tcp ct mark set 0x4d475732\n'
        f'oifname "lo" ct direction reply ct mark 0x4d475732 meta skuid != {MANAGED} reject with tcp reset\n'
        f'meta skuid {MANAGED} oifname "lo" ct mark 0x4d475732 accept\n')

load(PORT)
print("== option C: allow managed loopback to/from 1455,1457")
case("managed -> managed listener on 1455 (Codex /cancel)", MANAGED, MANAGED, "127.0.0.1")  # port[0] not 1455
port[0] = 1454
c_hit = case("managed -> OWNER listener squatting 1455 (E13 hole)", MANAGED, OWNER)

load(SAME)
print("== option B': same-UID approximation via ct mark + reply owner check")
port[0] = 21000
b_same = case("managed -> managed listener", MANAGED, MANAGED)
b_owner = case("managed -> owner listener", MANAGED, OWNER)
# Does the refused SYN still land on the foreign listener? An unprivileged reader of /proc/net/tcp sees it.
p = 21555
srv = as_uid(OWNER, "-c", f"import socket,time;s=socket.socket();s.bind(('127.0.0.1',{p}));s.listen(5);open('/tmp/ready-{p}','w').close();time.sleep(4)")
while not os.path.exists(f"/tmp/ready-{p}"): time.sleep(0.05)
watcher = as_uid(OWNER, "-c", f"""
import time
seen=set()
for _ in range(60):
    for line in open('/proc/net/tcp').read().splitlines()[1:]:
        f=line.split(); local=int(f[1].split(':')[1],16); remote=int(f[2].split(':')[1],16)
        if local=={p} and f[3]=='03': seen.add(remote)
    time.sleep(0.05)
print('SYN_RECV from managed source ports:', sorted(seen))""")
time.sleep(0.2)
as_uid(MANAGED, "/tmp/cli.py", "127.0.0.1", str(p), "tcp").communicate(timeout=10)
leak = watcher.communicate(timeout=10)[0].strip(); srv.kill()
print("  ", leak)
assert c_hit, "port allowance should let managed reach an owner listener on 1455"
assert b_same and not b_owner
print("LAB2 OK")
