"""T4 tier 2 replay: pass real MCP results/catalogs captured on PJ1 through the gateway's own inspection code.

Runs in the gateway container (`app.core`, `app.poisoning`, live Presidio/secret engines). This is NOT the
end-to-end gateway path (local stdio servers cannot be routed yet, DEV-73): it measures the P10 output
inspection and the registration-time description check on real server output. Each item runs --reps times.
usage: python t4_replay.py capture.jsonl [catalog_extra.jsonl ...] --reps 3
Prints one JSON line per (item, rep): verdict withheld|masked|clean, reasons, ms.
"""
import asyncio, json, sys, time
from app import core, poisoning, contract

PROTOCOL = "2025-11-25"


async def inspect_result(payload):
    payload = {"content": payload.get("content", []), "isError": payload.get("isError", False)}
    try:
        guarded = await asyncio.to_thread(core._guarded_result, payload, PROTOCOL, None)
    except core.ResultRejected as exc:
        return "withheld", str(exc)[:200]
    try:
        _, kinds = await core._inspected_result(guarded)
    except core.ResultRejected as exc:
        return "withheld", str(exc)[:200]
    except Exception as exc:  # inspection unavailable counts as a failure, never a pass
        return "error", f"{type(exc).__name__}: {exc}"[:200]
    return ("masked", ",".join(sorted(kinds))) if kinds else ("clean", "")


async def main(paths, reps):
    items = [json.loads(line) for p in paths for line in open(p, encoding="utf-8")]
    for rep in range(reps):
        for item in items:
            t = time.perf_counter()
            if item["kind"] == "result":
                verdict, why = await inspect_result(item["payload"])
                row = {"case": item["case"], "label": item["label"], "server": item["server"], "tool": item["tool"]}
            elif item["kind"] == "catalog":
                flagged = {tool["name"]: poisoning.findings(tool) for tool in item["tools"]}
                flagged = {k: v for k, v in flagged.items() if v}
                verdict, why = ("flagged" if flagged else "clean"), json.dumps(flagged, ensure_ascii=False)[:300]
                row = {"case": f"CAT-{item['server']}", "label": item.get("label", "normal"), "server": item["server"],
                       "tools": len(item["tools"]), "catalog_sha256": contract.canonical_hash(item["tools"])}
            else:
                continue
            row.update(rep=rep, verdict=verdict, why=why, ms=round((time.perf_counter() - t) * 1000, 1))
            print(json.dumps(row, ensure_ascii=False), flush=True)

args = [a for a in sys.argv[1:] if not a.startswith("--")]
reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 3
args = [a for a in args if a != str(reps)]
asyncio.run(main(args, reps))
