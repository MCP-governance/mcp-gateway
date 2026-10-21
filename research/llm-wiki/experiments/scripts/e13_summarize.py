"""Summarize E13 runs: harness answer, Gateway decisions and endpoint OS events per run window.
usage: python e13_summarize.py RUN_DIR  -> prints a JSON line per run (also used for the wiki table)
"""
import collections, glob, json, os, re, sys

root = sys.argv[1]
for line in open(os.path.join(root, "index.jsonl"), encoding="utf-8"):
    run = json.loads(line)
    raw = open(os.path.join(root, run["label"] + ".out"), encoding="utf-8", errors="replace").read()
    answer, model, turns, limit = "", None, None, None
    m = re.search(r"\{.*\}", raw, re.S)
    if run["harness"] == "claude" and m:
        try:
            d = json.loads(m.group(0))
            answer, turns, model = d.get("result", ""), d.get("num_turns"), list(d.get("modelUsage") or {})
        except json.JSONDecodeError:
            answer = raw[-600:]
    else:
        text = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", raw)
        limit = "usage limit" in text
        answer = text[-900:]
    try:
        ev = json.load(open(os.path.join(root, run["label"] + ".appliance.json"), encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        ev = {"decisions": [], "os_events": [], "error": str(exc)}
    kinds = collections.Counter((e["kind"], e.get("denial_class"), e.get("executable") or e.get("daddr") or e.get("destination"))
                                for e in ev.get("os_events", []))
    print(json.dumps({**run, "model": model, "turns": turns, "usage_limit": limit,
                      "decisions": [(d["id"], d["server"], d["tool_name"], d["decision"], d["policy_id"], d["upstream_executed"])
                                    for d in ev.get("decisions", [])],
                      "os_events": [list(k) + [n] for k, n in kinds.most_common()],
                      "answer": answer.strip()[:700]}, ensure_ascii=False))
