#!/usr/bin/env python3
"""OPA 정책 번들의 적용 전후 판정을 같은 입력으로 비교한다."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OPA_IMAGE = "openpolicyagent/opa:1.20.2-static"
OPA_URL = "/v1/data/mcp/authz/decision"
DECISIONS = {"Allow", "Alert", "Restrict", "Approval", "Block"}
EXECUTABLE = {"Allow", "Alert", "Restrict"}


def merge_objects(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """중첩 객체는 병합하고 나머지 값과 배열은 사례 값으로 바꾼다."""
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_objects(merged[key], value)
        else:
            merged[key] = value
    return merged


def convert_replay_cases(document: dict[str, Any]) -> dict[str, Any]:
    """기존 base+patch 재생 사례를 독립 입력 사례 형식으로 바꾼다."""
    converted = []
    for item in document["cases"]:
        attack = item["label"] == "attack"
        converted.append({
            "id": item["id"],
            "label": "attack" if attack else "benign",
            "category": (
                "공격: " + item["id"].removeprefix("attack-").replace("-", " ")
                if attack else
                "정상 업무: " + item["id"].removeprefix("normal-").replace("-", " ")
            ),
            "expect": {"decision": "Block" if attack else "Allow"},
            "input": merge_objects(document["base"], item.get("patch", {})),
        })
    return {"cases": converted}


def is_blocked(decision: str) -> bool:
    return decision not in EXECUTABLE


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def percentile(values: list[float], percentile_value: float) -> float | None:
    """선형 보간 방식의 백분위수. 입력은 ms이며 결과는 3자리로 고정한다."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile_value
    lower = math.floor(rank)
    upper = math.ceil(rank)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
    return round(value, 3)


def calculate_metrics(cases: list[dict[str, Any]], results: list[dict[str, Any]],
                      latencies: list[float]) -> dict[str, Any]:
    """고정된 사례 결과에서 여섯 평가지표를 계산한다."""
    by_id = {result["id"]: result for result in results}
    attacks = [case for case in cases if case["label"] == "attack"]
    benign = [case for case in cases if case["label"] == "benign"]
    blocked_attacks = [case for case in attacks if is_blocked(by_id[case["id"]]["decision"])]
    blocked_benign = [case for case in benign if is_blocked(by_id[case["id"]]["decision"])]
    blocked_total = blocked_attacks + blocked_benign
    expected = [case for case in attacks if case.get("expect", {}).get("policy_id")
                and is_blocked(by_id[case["id"]]["decision"])]
    matched = sum(by_id[case["id"]].get("policy_id") == case["expect"]["policy_id"]
                  for case in expected)
    return {
        "attack_block_rate": ratio(len(blocked_attacks), len(attacks)),
        "benign_allow_rate": ratio(len(benign) - len(blocked_benign), len(benign)),
        "false_positive_rate": ratio(len(blocked_benign), len(benign)),
        "precision": ratio(len(blocked_attacks), len(blocked_total)),
        "block_reason_match_rate": ratio(matched, len(expected)),
        "latency_ms": {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95)},
    }


def self_test() -> None:
    cases = [
        {"id": "a1", "label": "attack", "expect": {"policy_id": "P1"}},
        {"id": "a2", "label": "attack", "expect": {}},
        {"id": "b1", "label": "benign", "expect": {}},
        {"id": "b2", "label": "benign", "expect": {}},
    ]
    results = [
        {"id": "a1", "decision": "Block", "policy_id": "P1"},
        {"id": "a2", "decision": "Allow", "policy_id": None},
        {"id": "b1", "decision": "Approval", "policy_id": "P2"},
        {"id": "b2", "decision": "Restrict", "policy_id": "P3"},
    ]
    metrics = calculate_metrics(cases, results, [1, 2, 3, 4, 5])
    assert metrics == {
        "attack_block_rate": 0.5,
        "benign_allow_rate": 0.5,
        "false_positive_rate": 0.5,
        "precision": 0.5,
        "block_reason_match_rate": 1.0,
        "latency_ms": {"p50": 3.0, "p95": 4.8},
    }
    assert calculate_metrics([], [], []) == {
        "attack_block_rate": None, "benign_allow_rate": None,
        "false_positive_rate": None, "precision": None,
        "block_reason_match_rate": None, "latency_ms": {"p50": None, "p95": None},
    }
    legacy = {"base": {"nested": {"a": 1}, "items": [1]}, "cases": [
        {"id": "normal-x", "label": "normal", "patch": {"nested": {"b": 2}, "items": [2]}}
    ]}
    converted = convert_replay_cases(legacy)["cases"][0]
    assert converted["input"] == {"nested": {"a": 1, "b": 2}, "items": [2]}
    assert converted["label"] == "benign" and converted["expect"]["decision"] == "Allow"


def load_cases(paths: list[Path]) -> tuple[list[dict[str, Any]], str]:
    all_cases = []
    hashes = []
    for path in paths:
        raw = path.read_bytes()
        hashes.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        document = json.loads(raw.decode("utf-8"))
        document = document.get("pac15_replay", document)  # opa/replay_cases_pac15.json 그대로
        if "base" in document and "cases" in document:
            document = convert_replay_cases(document)
        all_cases.extend(document["cases"])
    all_cases.sort(key=lambda case: case["id"])
    ids = [case["id"] for case in all_cases]
    if len(set(ids)) != len(ids):
        raise ValueError("사례 id는 모든 입력 파일에서 고유해야 합니다")
    for case in all_cases:
        if case.get("label") not in {"attack", "benign"}:
            raise ValueError(f"{case.get('id')}: label은 attack 또는 benign이어야 합니다")
        if case.get("expect", {}).get("decision") not in DECISIONS:
            raise ValueError(f"{case.get('id')}: expect.decision이 없거나 잘못되었습니다")
        if not isinstance(case.get("input"), dict):
            raise ValueError(f"{case.get('id')}: input은 객체여야 합니다")
    return all_cases, json.dumps(hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def bundle_sha256(bundle: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in bundle.rglob("*") if item.is_file()):
        digest.update(path.relative_to(bundle).as_posix().encode("utf-8"))
        digest.update(bytes([0]))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def bundle_for(reference: str, temp_root: Path) -> tuple[Path, str, str]:
    bundle = temp_root / "policy"
    bundle.mkdir(parents=True)
    if reference == "worktree":
        source = ROOT / "full_stack_lab" / "opa"
        shutil.copytree(source, bundle, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*_test.rego"))
        commit = git_output("rev-parse", "HEAD")
    else:
        commit = git_output("rev-parse", f"{reference}^{{commit}}")
        archive = subprocess.check_output(
            ["git", "archive", reference, "full_stack_lab/opa"], cwd=ROOT
        )
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            for member in tar.getmembers():
                if member.name.endswith("_test.rego"):
                    continue
                parts = Path(member.name).parts[2:]
                if not parts:
                    continue
                target = bundle.joinpath(*parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source_file = tar.extractfile(member)
                    if source_file is not None:
                        target.write_bytes(source_file.read())
    return bundle, commit, bundle_sha256(bundle)


def docker_digest() -> str:
    output = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", OPA_IMAGE],
        text=True,
    ).strip()
    digests = json.loads(output)
    if not digests:
        raise RuntimeError(f"{OPA_IMAGE} 이미지에 RepoDigest가 없습니다")
    return sorted(digests)[0]


def evaluate_opa(bundle: Path, cases: list[dict[str, Any]], repeat: int
                 ) -> tuple[list[dict[str, Any]], list[float]]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    container = subprocess.check_output([
        "docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{port}:8181",
        "-v", f"{bundle.resolve()}:/policy:ro", OPA_IMAGE,
        "run", "--server", "--addr", "0.0.0.0:8181", "/policy",
    ], text=True).strip()
    endpoint = f"http://127.0.0.1:{port}{OPA_URL}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                request = urllib.request.Request(endpoint, data=b'{"input":{}}',
                                                 headers={"Content-Type": "application/json"},
                                                 method="POST")
                with urllib.request.urlopen(request, timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:  # 기동 중 연결 거부·끊김·시간 초과
                if time.monotonic() >= deadline:
                    raise RuntimeError("OPA 서버가 30초 안에 준비되지 않았습니다")
                time.sleep(0.2)
        results, latencies = [], []
        for case in cases:
            samples = []
            verdict = None
            for _ in range(repeat):
                body = json.dumps({"input": case["input"]}, ensure_ascii=False,
                                  separators=(",", ":")).encode("utf-8")
                request = urllib.request.Request(endpoint, data=body,
                                                 headers={"Content-Type": "application/json"},
                                                 method="POST")
                started = time.perf_counter_ns()
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                samples.append(round((time.perf_counter_ns() - started) / 1_000_000, 3))
                verdict = payload["result"]
                if verdict.get("decision") not in DECISIONS:
                    raise RuntimeError(f"{case['id']}: 알 수 없는 OPA 판정 {verdict.get('decision')!r}")
            latencies.extend(samples)
            results.append({
                "id": case["id"], "decision": verdict["decision"],
                "policy_id": verdict.get("policy_id"),
                "latency_ms": samples,
            })
        return results, latencies
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def evaluate_none(cases: list[dict[str, Any]], repeat: int) -> tuple[list[dict[str, Any]], list[float]]:
    return ([{"id": case["id"], "decision": "Allow", "policy_id": None,
              "latency_ms": [0.0] * repeat} for case in cases], [0.0] * len(cases) * repeat)


def metric_rows(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("공격 차단율", metrics["attack_block_rate"]),
        ("정상 허용률", metrics["benign_allow_rate"]),
        ("오탐률", metrics["false_positive_rate"]),
        ("정밀도", metrics["precision"]),
        ("차단 사유 일치율", metrics["block_reason_match_rate"]),
        ("판정 지연 p50 / p95 (ms)", metrics["latency_ms"]),
    ]


def render_report(cases: list[dict[str, Any]], before: dict[str, Any],
                  after: dict[str, Any]) -> str:
    def show(value: Any) -> str:
        if isinstance(value, dict):
            return f"{value['p50']} / {value['p95']}"
        return "—" if value is None else f"{value:.6f}"

    lines = ["# 통제 적용 전후 효과 비교", "", "| 지표 | 적용 전 | 적용 후 |", "| --- | ---: | ---: |"]
    for (name, before_value), (_, after_value) in zip(metric_rows(before["metrics"]),
                                                       metric_rows(after["metrics"])):
        lines.append(f"| {name} | {show(before_value)} | {show(after_value)} |")
    bmap = {result["id"]: result for result in before["cases"]}
    amap = {result["id"]: result for result in after["cases"]}
    changed = [case for case in cases if
               (bmap[case["id"]]["decision"], bmap[case["id"]]["policy_id"]) !=
               (amap[case["id"]]["decision"], amap[case["id"]]["policy_id"])]
    lines.extend(["", "## 판정이 바뀐 사례", ""])
    if changed:
        lines.extend(["| 사례 | 구분 | 적용 전 | 적용 후 |", "| --- | --- | --- | --- |"])
        for case in changed:
            old, new = bmap[case["id"]], amap[case["id"]]
            lines.append(f"| {case['id']} | {case['label']} | {old['decision']} ({old['policy_id'] or '—'}) | {new['decision']} ({new['policy_id'] or '—'}) |")
    else:
        lines.append("판정 변화 없음.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", type=Path, help="사례 JSON 파일(여러 개 가능)")
    parser.add_argument("--before", default="none", help="적용 전 Git ref 또는 none")
    parser.add_argument("--after", default="worktree", help="적용 후 Git ref 또는 worktree")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--out", type=Path, help="결과 출력 폴더")
    parser.add_argument("--self-test", action="store_true", help="순수 지표 계산 자체 검사")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test 통과")
        return 0
    if not args.cases or not args.out:
        parser.error("--cases와 --out이 필요합니다")
    if args.repeat < 1:
        parser.error("--repeat는 1 이상이어야 합니다")

    cases, cases_sha = load_cases(args.cases)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    before_ref = args.before
    after_ref = args.after
    before_commit = None if before_ref == "none" else git_output("rev-parse", f"{before_ref}^{{commit}}")
    after_commit = git_output("rev-parse", "HEAD") if after_ref == "worktree" else git_output("rev-parse", f"{after_ref}^{{commit}}")
    digest = docker_digest()

    with tempfile.TemporaryDirectory(prefix="mint-eval-") as temporary:
        temp_root = Path(temporary)
        before_bundle = None if before_ref == "none" else bundle_for(before_ref, temp_root / "before")
        after_bundle = bundle_for(after_ref, temp_root / "after")
        if before_ref == "none":
            before_cases, before_latencies = evaluate_none(cases, args.repeat)
            before_bundle_hash = None
        else:
            before_cases, before_latencies = evaluate_opa(before_bundle[0], cases, args.repeat)
            before_bundle_hash = before_bundle[2]
        after_cases, after_latencies = evaluate_opa(after_bundle[0], cases, args.repeat)

    before = {"ref": before_ref, "commit": before_commit,
              "policy_bundle_sha256": before_bundle_hash,
              "cases": before_cases,
              "metrics": calculate_metrics(cases, before_cases, before_latencies)}
    after = {"ref": after_ref, "commit": after_commit,
             "policy_bundle_sha256": after_bundle[2],
             "cases": after_cases,
             "metrics": calculate_metrics(cases, after_cases, after_latencies)}
    result = {
        "run": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "image": OPA_IMAGE, "image_digest": digest,
        "cases_sha256": json.loads(cases_sha), "repeat": args.repeat,
        "before": before, "after": after,
    }
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                 sort_keys=True) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_report(cases, before, after), encoding="utf-8")
    print(f"결과: {out / 'result.json'}")
    print(f"보고서: {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
