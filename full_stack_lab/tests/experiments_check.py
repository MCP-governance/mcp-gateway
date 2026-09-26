"""The paper experiments must keep showing what the paper claims.

    python3 tests/experiments_check.py reports/experiment-e1.json reports/experiment-e2.json reports/experiment-e3.json

`./console.sh test` runs the experiments against the live lab and then this check.
A finding flipping means either the lab changed or the claim no longer holds;
both need a person to look.
"""
import json
import sys

EXPECT = {
    # E1 · token revocation: 200 proves processing only; a stateless resource server
    # keeps accepting until expiry; the Gateway checks revocation and blocks at once.
    "E1": {"revocation_always_200": True, "introspection_inactive": True, "stateless_gap": True,
           "gateway_blocks_immediately": True, "refresh_survives_access_revocation": True},
    # E3 · server-held credential: upstream revocation does not reach it.
    "E3": {"upstream_revoked": True, "downstream_access_persisted": True,
           "blocked_only_after_provider_revocation": True},
}


def check(report: dict) -> list[str]:
    name = report.get("experiment", "?")
    findings = report.get("findings") or {}
    problems = [f"{name}.{key} = {findings.get(key)!r}, 논문 주장은 {want!r}"
                for key, want in EXPECT.get(name, {}).items() if findings.get(key) != want]
    if name == "E2":
        # E2 · session layer: most real servers issue no session at all, and every
        # round of a server must say the same thing.
        servers = report.get("servers") or {}
        stateless = findings.get("servers_without_sessions") or []
        if len(stateless) * 2 < len(servers):
            problems.append(f"E2: 세션을 발급하지 않는 서버가 절반 미만입니다 ({len(stateless)}/{len(servers)})")
        problems += [f"E2.{sid}: 반복 측정이 서로 다릅니다" for sid, s in servers.items() if not s.get("consistent")]
    return problems


def main(paths: list[str]) -> int:
    failed = False
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
        problems = check(report)
        print(f"{report.get('experiment', path)}: {'PASS' if not problems else 'FAIL'}")
        for problem in problems:
            print(f"  - {problem}")
        failed |= bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        # self-check: a report that contradicts the paper must fail
        assert check({"experiment": "E1", "findings": {**EXPECT["E1"], "stateless_gap": False}})
        assert not check({"experiment": "E3", "findings": EXPECT["E3"]})
        assert check({"experiment": "E2", "servers": {"a": {"consistent": True}, "b": {"consistent": False}},
                      "findings": {"servers_without_sessions": ["a"]}})
        print("self-check ok")
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
