"""A candidate policy must still stop every labelled attack and pass every normal case.

    python3 tests/replay_check.py reports/policy-replay.json

Reads the output of `python -m app.replay` (./console.sh replay or ./console.sh test).
The recorded-traffic comparison is reported, not judged: a change there is what a
policy change is supposed to show, and a person decides whether it is intended.
"""
import json
import sys


def check(report: dict) -> list[str]:
    corpus = report.get("frozen_corpus") or {}
    cases = corpus.get("cases") or []
    problems = [f"{c['id']}: {c['label']} 사례가 {c['candidate']['decision']}({c['candidate']['policy_id']})"
                for c in cases if not c.get("passed")]
    if not cases:
        problems.append("재생된 합성 사례가 없습니다")
    return problems


def main(path: str) -> int:
    with open(path, encoding="utf-8") as handle:
        report = json.load(handle)
    counts = report.get("counts") or {}
    print(f"기록 재생 {report.get('compared', 0)}건 — 동일 {counts.get('same', 0)} · 변경 {counts.get('changed', 0)} · "
          f"새로 실행 {counts.get('newly_executable', 0)} · 새로 미실행 {counts.get('newly_nonexecuting', 0)}")
    problems = check(report)
    corpus = report.get("frozen_corpus") or {}
    print(f"합성 사례 {len(corpus.get('cases') or [])}건: 공격 미탐 {corpus.get('missed_attacks')} · 정상 차단 {corpus.get('false_blocks')}"
          f" — {'PASS' if not problems else 'FAIL'}")
    for problem in problems:
        print(f"  - {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) == 2:
        sys.exit(main(sys.argv[1]))
    good = {"frozen_corpus": {"cases": [{"id": "a", "label": "attack", "passed": True,
                                         "candidate": {"decision": "Block", "policy_id": "X"}}]}}
    bad = {"frozen_corpus": {"cases": [{"id": "a", "label": "attack", "passed": False,
                                        "candidate": {"decision": "Allow", "policy_id": "P"}}]}}
    assert not check(good) and check(bad) and check({})
    print("self-check ok")
