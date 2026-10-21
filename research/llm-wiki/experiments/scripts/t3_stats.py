"""T3 statistics: percentiles per (mode, path) from latency_ab.py CSV and gateway stage timings.

usage: python t3_stats.py RAW.csv [TIMINGS.jsonl]
Percentiles use the nearest-rank method on successful rows (no exception); failed rows are counted apart.
Gateway stages (core._Laps) are mapped to the P0~P11 pipeline of docs/ai/architecture (2026-10-18 review).
"""
import csv, json, math, random, sys
from collections import defaultdict

STAGE_TO_P = [  # lap name -> pipeline step
    ("identity", "P0~P1 토큰·주체·자원 확인"), ("reserve", "P2 호출 예약"), ("schema", "P3 입력 계약"),
    ("inspect_in", "P4 입력 검사"), ("context", "P5 정책 입력 조립"), ("policy", "P5~P6 OPA 판정·분기"),
    ("dispatch", "P6→P7 실행 준비"), ("connect", "P7 업스트림 연결"), ("list", "P7 tools/list 계약 대조"),
    ("recheck", "P7 직전 재검증"), ("intent", "P8 실행 의도 기록"), ("call", "P9 도구 실행"),
    ("close", "P9 세션 종료"), ("inspect_out", "P10 출력 검사"),
]


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    return round(s[max(0, math.ceil(q / 100 * len(s)) - 1)], 1)


def boot(values, q, other=None, rounds=2000, seed=20261020):
    """95% percentile-bootstrap CI of the q-th percentile (or of B-A when other=A values)."""
    rng = random.Random(seed)
    stats = []
    for _ in range(rounds):
        s = pct([rng.choice(values) for _ in values], q)
        if other is not None:
            s -= pct([rng.choice(other) for _ in other], q)
        stats.append(s)
    return [round(pct(stats, 2.5), 1), round(pct(stats, 97.5), 1)]


def summary(values, ci=True):
    out = {"n": len(values), "p50": pct(values, 50), "p95": pct(values, 95), "p99": pct(values, 99),
           "mean": round(sum(values) / len(values), 1) if values else None}
    if ci and len(values) >= 20:
        out.update({f"p{q}_ci95": boot(values, q) for q in (50, 95, 99)})
    return out


def main(raw, timings=None):
    groups, failed, errors = defaultdict(list), defaultdict(int), defaultdict(int)
    first = {}
    for row in csv.DictReader(open(raw)):
        key = (row["mode"], row["path"])
        if row.get("error"):
            failed[key] += 1; continue
        if row["is_error"] == "True":
            errors[key] += 1
        value = float(row["total_ms"])
        if row["mode"] == "warm" and row["i"] == "0":
            first[key] = value  # first call on a fresh long-lived session, reported apart
            continue
        groups[key].append(value)
        if row["mode"] == "cold":
            groups[("cold-init", row["path"])].append(float(row["init_ms"]))
            groups[("cold-call", row["path"])].append(float(row["call_ms"]))
            if row["path"] == "B" and float(row["token_ms"] or 0) > 0:
                groups[("token-helper", "B")].append(float(row["token_ms"]))
    out = {"percentiles": {f"{m}/{p}": summary(v) for (m, p), v in sorted(groups.items())},
           "failed_rows": {f"{m}/{p}": n for (m, p), n in failed.items()},
           "tool_isError_rows": {f"{m}/{p}": n for (m, p), n in errors.items()},
           "warm_first_call_ms": {f"{m}/{p}": v for (m, p), v in first.items()}}
    for mode in ("cold", "warm"):
        a, b = groups.get((mode, "A")), groups.get((mode, "B"))
        if a and b:
            out[f"{mode}_overhead_ms"] = {q: {"B-A": round(pct(b, q) - pct(a, q), 1), "ci95": boot(b, q, other=a)}
                                          for q in (50, 95, 99)}
    if timings:
        stages = defaultdict(list)
        for line in open(timings):
            t = json.loads(line).get("timings") or {}
            for name, _ in STAGE_TO_P:
                if name in t:
                    stages[name].append(float(t[name]))
            if "total" in t:
                stages["total"].append(float(t["total"]))
        out["gateway_stages"] = [{"stage": name, "pipeline": label, **summary(stages[name], ci=False)}
                                 for name, label in STAGE_TO_P + [("total", "게이트웨이 내부 합계")] if stages[name]]
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
