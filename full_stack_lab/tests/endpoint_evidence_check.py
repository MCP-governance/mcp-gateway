"""Endpoint evidence contracts: provenance hashes, origin, paging bounds, network quality, denial class.

Unit level. The receiver runs against a recording connection and the network probe talks to a
tiny stdlib HTTP listener on loopback; neither is a real Gateway, database or MCP server. The
PostgreSQL behaviour of the same functions is in endpoint_evidence_pg_check.py.
"""
import asyncio
import importlib.util
import json
import math
import sys
import tempfile
import threading
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "full_stack_lab" / "gateway"))
from app import endpoint_plane, main, mcp_facade  # noqa: E402


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = load("evidence_agent", "endpoint-agent/agent.py")
observer = load("evidence_observer", "endpoint-agent/os-observer.py")


class Cursor:
    def __init__(self, row=None, rows=(), rowcount=1):
        self.row, self.rows, self.rowcount = row, list(rows), rowcount

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return self.rows


class Recorder:
    """Records statements; answers just enough for the receivers to run."""

    def __init__(self):
        self.calls = []

    async def execute(self, query, params=None):
        self.calls.append((query, params))
        if "FROM endpoint_agents" in query:
            return Cursor(row={"endpoint_id": "ep-unit", "detail": {}})
        if "FROM mcp_servers" in query or "provenance->>'raw_sha256'" in query:
            return Cursor()
        return Cursor(rowcount=1)

    @asynccontextmanager
    async def transaction(self):
        yield self

    def inserted(self, table):
        return [params for query, params in self.calls if query.lstrip().startswith("INSERT INTO " + table)]


def stored(params, position):
    value = params[position]
    return getattr(value, "obj", value)


class OriginDefault(unittest.TestCase):
    def test_a_running_service_is_automatic_and_a_hand_run_is_manual(self):
        for argv, expected in ((["agent.py"], "automatic"), (["agent.py", "--once"], "manual")):
            with mock.patch.object(sys, "argv", argv), mock.patch.dict("os.environ", clear=False):
                self.assertEqual(load("origin_probe", "endpoint-agent/agent.py").ORIGIN, expected)
        for forced, expected in (("automatic", "automatic"), ("operator", "manual")):
            with mock.patch.object(sys, "argv", ["agent.py", "--once"]), mock.patch.dict("os.environ", {"ENDPOINT_ORIGIN": forced}):
                self.assertEqual(load("origin_probe", "endpoint-agent/agent.py").ORIGIN, expected)


class CanonicalHashes(unittest.TestCase):
    def test_agent_and_receiver_hash_the_same_bytes(self):
        for sample in ({"b": 1, "a": None, "c": "한글"}, {"details": {"x": "y", "n": 3}}, [], {"port": None}):
            self.assertEqual(agent.canonical_sha256(sample), endpoint_plane.canonical_sha256(sample))
        moment = datetime(2026, 10, 15, 1, 2, 3, 456789, tzinfo=UTC)
        self.assertEqual(agent.canonical_time(moment), endpoint_plane.canonical_time(moment))
        self.assertEqual(agent.canonical_time(moment), "2026-10-15T01:02:03.456789Z")
        zone = datetime(2026, 10, 15, 10, 2, 3, 456789, tzinfo=timezone_of(9))
        self.assertEqual(agent.canonical_time(zone), endpoint_plane.canonical_time(zone))


def timezone_of(hours):
    from datetime import timezone
    return timezone(timedelta(hours=hours))


class InventoryProvenance(unittest.IsolatedAsyncioTestCase):
    async def ingest(self, entries, origin="automatic"):
        recorder = Recorder()
        with mock.patch.object(endpoint_plane.db, "transaction", recorder.transaction),              mock.patch.object(endpoint_plane, "_link_residue_to_cases", mock.AsyncMock()):
            await endpoint_plane.ingest("ep-unit", entries, complete=True, origin=origin)
        return recorder

    def collect(self, text, name="mcp.json"):
        folder = Path(tempfile.gettempdir()) / "endpoint-evidence-fixture"
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
        self.addCleanup(lambda: (folder / name).unlink(missing_ok=True))
        with mock.patch.object(agent, "SCAN_PATHS", [folder]):
            return agent.collect_configs()

    async def test_collected_entries_reach_the_server_as_a_match_without_secrets(self):
        config = json.dumps({"mcpServers": {
            "tool": {"command": "npx", "args": ["-y", "some-mcp"], "env": {"TOKEN": "fixture-secret-value"}},
            "remote": {"url": "https://user:fixture-pass@mcp.example/mcp?key=fixture-key"},
            "plain": {"url": "https://mcp.example/mcp", "headers": {"Authorization": "fixture-secret-value"}}}})
        entries = self.collect(config)
        recorder = await self.ingest(entries)
        rows = recorder.inserted("endpoint_inventory")
        self.assertEqual(len(rows), 3)
        for params in rows:
            provenance = stored(params, 10)
            self.assertEqual(provenance["state"], "match", provenance)
            self.assertEqual(provenance["collector"], "config-file")
            self.assertEqual(provenance["agent_projection_sha256"], provenance["server_projection_sha256"])
            self.assertEqual(params[9], "automatic")
        steps = {tuple(stored(params, 10)["transformations"]) for params in rows}
        self.assertIn(("drop_env_headers", "command_sha256"), steps)
        self.assertIn(("url_sha256",), steps)
        self.assertIn(("drop_env_headers",), steps)
        dump = json.dumps([stored(params, 10) for params in rows]) + json.dumps(entries)
        for secret in ("fixture-secret-value", "fixture-pass", "fixture-key"):
            self.assertNotIn(secret, dump)

    async def test_raw_hash_ignores_secret_values_and_changes_with_the_visible_record(self):
        def raw_hash(args, env):
            (entry,) = self.collect(json.dumps({"mcpServers": {"s": {"command": "npx", "args": args, "env": env}}}))
            return entry["provenance"]["raw_sha256"]
        self.assertEqual(raw_hash(["a"], {"K": "one"}), raw_hash(["a"], {"K": "two"}))
        self.assertNotEqual(raw_hash(["a"], {}), raw_hash(["b"], {}))

    async def test_a_changed_or_missing_agent_hash_is_flagged_or_unreported(self):
        (entry,) = self.collect(json.dumps({"mcpServers": {"s": {"url": "https://mcp.example/mcp"}}}))
        tampered = json.loads(json.dumps(entry))
        tampered["endpoint_ref"] = "https://elsewhere.example/mcp"
        legacy = {key: value for key, value in entry.items() if key != "provenance"}
        for item, expected in ((entry, "match"), (tampered, "mismatch"), (legacy, "unreported")):
            recorder = await self.ingest([item])
            self.assertEqual(stored(recorder.inserted("endpoint_inventory")[0], 10)["state"], expected)

    async def test_server_side_normalisation_is_recorded_and_flagged(self):
        entry = {"config_path": "/c.json", "server_label": "old", "transport": "stdio", "endpoint_ref": "npx some-server --token x"}
        legacy_projection = {key: entry[key] for key in agent.INVENTORY_FIELDS}
        entry["provenance"] = {"raw_sha256": "a" * 64, "projection_sha256": agent.canonical_sha256(legacy_projection),
                               "transformations": [], "collector": "config-file"}
        provenance = stored((await self.ingest([entry])).inserted("endpoint_inventory")[0], 10)
        self.assertEqual(provenance["state"], "mismatch")
        self.assertIn("server:command_sha256", provenance["transformations"])

    async def test_unknown_origin_is_refused(self):
        with self.assertRaises(ValueError):
            await self.ingest([], origin="operator")


class ListenerProvenance(unittest.IsolatedAsyncioTestCase):
    async def test_collector_findings_match_what_the_server_stores(self):
        row = {"address": "127.0.0.1", "port": 7311, "process_name": "ghidramcp", "command_line": "ghidramcp --token fixture-secret"}
        with mock.patch.object(agent, "local_listeners", return_value=[row]), \
             mock.patch.object(agent, "probe_mcp", return_value={"server_name": "ghidra", "server_version": "1.0", "protocol_version": "2025-06-18", "path": "/mcp"}):
            findings = agent.listener_findings({"probe_mcp": True})
        process = agent.sealed_listener({"source": "stdio-process", "address": "local-process", "port": None, "process_name": "x",
                                         "command_line": agent.command_digest("x --token fixture-secret"), "mcp_evidence": "suspected"},
                                        {"process_name": "x", "command_line": "x --token fixture-secret"}, "process-table")
        recorder = Recorder()
        with mock.patch.object(endpoint_plane.db, "transaction", recorder.transaction):
            await endpoint_plane.ingest_listeners("ep-unit", [*findings, process], complete=True,
                                                  sources=["local-socket", "stdio-process"], origin="automatic")
        rows = recorder.inserted("endpoint_listeners")
        self.assertEqual(len(rows), 2)
        for params in rows:
            provenance = stored(params, 15)
            self.assertEqual(provenance["state"], "match", provenance)
            self.assertEqual(params[14], "automatic")
        self.assertNotIn("fixture-secret", json.dumps([stored(params, 15) for params in rows]) + json.dumps([*findings, process]))


class OSEventEvidence(unittest.IsolatedAsyncioTestCase):
    APPARMOR = ('apparmor="DENIED" operation="exec" class="file" profile="mcpgw-u" name="/usr/bin/{name}" '
                'pid=77 comm="{comm}" requested_mask="x" denied_mask="x" fsuid=1001 ouid=0')

    def record(self, message, cursor="c1"):
        return {"_BOOT_ID": "boot-0001-fixture", "__CURSOR": cursor, "__REALTIME_TIMESTAMP": "1760490123456789", "MESSAGE": message}

    def test_denial_class_comes_from_the_path_and_the_process_that_tried(self):
        cases = (("git", "claude", "harness_startup"), ("claude", "claude", "harness_startup"), ("codex", "codex", "harness_startup"),
                 ("git", "bash", "blocked_attempt"), ("curl", "claude", "blocked_attempt"), ("python3", "bash", "blocked_attempt"))
        for name, comm, expected in cases:
            found = observer.event(self.record(self.APPARMOR.format(name=name, comm=comm)), 1001, "mcpgw-u")
            self.assertEqual(found["denial_class"], expected, (name, comm))
            self.assertEqual(found["details"]["parent_executable"], comm)
            self.assertEqual(found["details"]["profile"], "mcpgw-u")
            self.assertEqual(found["details"]["executable"], name)
        self.assertEqual(observer.denial_class("exec", "/home/u/bin/git", "claude"), "blocked_attempt")
        self.assertEqual(observer.denial_class("exec", "/tmp/claude", "claude"), "blocked_attempt")
        self.assertEqual(observer.denial_class("file_inherit", "/tmp/out", "claude"), "unknown")
        without_process = self.APPARMOR.replace(' comm="{comm}"', "").format(name="git")
        self.assertEqual(observer.event(self.record(without_process), 1001, "mcpgw-u")["denial_class"], "unknown")
        network = observer.event(self.record("MCPGW_DENY uid=1001 SRC=10.0.0.2 DST=1.1.1.1 PROTO=TCP SPT=1 DPT=443"), 1001, "mcpgw-u")
        self.assertEqual((network["kind"], network["denial_class"]), ("network-denied", "unknown"))

    async def test_sealed_events_are_stored_as_a_match_with_their_class(self):
        events = [observer.event(self.record(self.APPARMOR.format(name="git", comm="claude"), "c1"), 1001, "mcpgw-u", "raw-line-1"),
                  observer.event(self.record("MCPGW_DENY uid=1001 SRC=10.0.0.2 DST=1.1.1.1 PROTO=TCP SPT=1 DPT=443", "c2"), 1001, "mcpgw-u", "raw-line-2")]
        accepted = [main.EndpointOSEvent.model_validate(item).model_dump() for item in events]
        recorder = Recorder()
        with mock.patch.object(endpoint_plane.db, "transaction", recorder.transaction):
            result = await endpoint_plane.ingest_os_events("ep-unit", accepted)
        self.assertEqual(result["received"], 2)
        rows = recorder.inserted("endpoint_os_events")
        self.assertEqual(len(rows), 2)
        for params in rows:
            self.assertEqual(stored(params, 6)["state"], "match")
        self.assertEqual([params[5] for params in rows], ["harness_startup", "unknown"])
        self.assertEqual(stored(rows[0], 6)["raw_sha256"], agent.hashlib.sha256(b"raw-line-1").hexdigest())

    async def test_a_changed_event_after_sealing_is_a_mismatch(self):
        event = observer.event(self.record(self.APPARMOR.format(name="curl", comm="bash")), 1001, "mcpgw-u", "raw")
        event["details"]["executable"] = "git"
        recorder = Recorder()
        with mock.patch.object(endpoint_plane.db, "transaction", recorder.transaction):
            await endpoint_plane.ingest_os_events("ep-unit", [main.EndpointOSEvent.model_validate(event).model_dump()])
        self.assertEqual(stored(recorder.inserted("endpoint_os_events")[0], 6)["state"], "mismatch")

    async def test_unknown_class_value_is_stored_as_unknown(self):
        event = main.EndpointOSEvent.model_validate({"event_id": "boot:cursor-x", "observed_at": "2026-10-15T00:00:00Z",
                                                     "kind": "execution-denied", "details": {"executable": "x"}}).model_dump()
        recorder = Recorder()
        with mock.patch.object(endpoint_plane.db, "transaction", recorder.transaction):
            await endpoint_plane.ingest_os_events("ep-unit", [event])
        row = recorder.inserted("endpoint_os_events")[0]
        self.assertEqual((row[5], stored(row, 6)["state"]), ("unknown", "unreported"))
        with self.assertRaises(ValueError):
            main.EndpointOSEvent.model_validate({**event, "denial_class": "harmless"})


class Paging(unittest.TestCase):
    def test_cursor_and_limit_are_bounded(self):
        self.assertEqual(endpoint_plane._bounds(500, None), (200, None))
        self.assertEqual(endpoint_plane._bounds(0, "42"), (1, 42))
        for bad in ("-1", "1; DROP TABLE x", "abc", "9" * 19):
            with self.assertRaises(ValueError):
                endpoint_plane._bounds(10, bad)
        self.assertEqual(endpoint_plane._classes("shadow,retired-residue"), ["shadow", "retired-residue"])
        self.assertIsNone(endpoint_plane._classes(""))
        with self.assertRaises(ValueError):
            endpoint_plane._classes("shadow,other")

    def test_window_reports_the_cursor_only_when_more_rows_exist(self):
        rows = [{"id": n} for n in (9, 8, 7)]
        self.assertEqual(endpoint_plane._window(rows, 2), ([{"id": 9}, {"id": 8}], "8"))
        self.assertEqual(endpoint_plane._window(rows, 3), (rows, None))


class NetworkQualityContract(unittest.TestCase):
    def sample(self, **changes):
        return {"measured_at": datetime.now(UTC).isoformat(), "rtt_p50_ms": 12.0, "rtt_p95_ms": 20.5,
                "jitter_ms": 1.2, "failure_pct": 0.0, "probes": 6, **changes}

    def test_valid_sample_is_accepted(self):
        self.assertEqual(main.NetworkQuality.model_validate(self.sample()).probes, 6)
        self.assertIsNone(main.NetworkQuality.model_validate(self.sample(rtt_p50_ms=None, rtt_p95_ms=None, jitter_ms=None, failure_pct=100)).rtt_p50_ms)

    def test_nan_negative_absurd_and_incoherent_values_are_rejected(self):
        old = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        for changes in ({"rtt_p50_ms": float("nan")}, {"rtt_p95_ms": float("inf")}, {"jitter_ms": -0.1}, {"rtt_p50_ms": -1},
                        {"rtt_p95_ms": 60001}, {"failure_pct": 100.5}, {"failure_pct": -1}, {"probes": 0}, {"probes": 33},
                        {"rtt_p50_ms": 30.0, "rtt_p95_ms": 20.0}, {"rtt_p95_ms": None}, {"measured_at": old}, {"measured_at": future},
                        {"measured_at": "2026-10-15T00:00:00"}, {"extra": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                main.NetworkQuality.model_validate(self.sample(**changes))

    def test_the_json_nan_literal_is_not_accepted(self):
        body = json.loads('{"measured_at": "%s", "rtt_p50_ms": NaN, "rtt_p95_ms": 1, "failure_pct": 0, "probes": 6}' % datetime.now(UTC).isoformat())
        with self.assertRaises(ValueError):
            main.NetworkQuality.model_validate(body)

    def test_summary_uses_nearest_rank_and_successive_differences(self):
        result = agent.summarise_samples([10.0, 14.0, 12.0, 30.0, 11.0], failed=1, probes=6)
        self.assertEqual((result["rtt_p50_ms"], result["rtt_p95_ms"]), (12.0, 30.0))
        self.assertEqual(result["jitter_ms"], round((4 + 2 + 18 + 19) / 4, 1))
        self.assertEqual((result["failure_pct"], result["probes"]), (16.7, 6))
        none = agent.summarise_samples([], failed=6, probes=6)
        self.assertEqual((none["rtt_p50_ms"], none["jitter_ms"], none["failure_pct"]), (None, None, 100.0))
        self.assertEqual(agent.summarise_samples([5.0], 0, 6)["jitter_ms"], 0.0)
        for value in agent.summarise_samples([1.0, 2.0], 0, 6).values():
            self.assertFalse(isinstance(value, float) and not math.isfinite(value))


class Health(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args):
        pass


class GatewayProbe(unittest.TestCase):
    """measure_gateway against a loopback stand-in for the health endpoint (not a Gateway)."""

    def serve(self, status):
        handler = type("Handler", (Health,), {"status": status})
        server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def test_five_connects_and_one_http_round_trip(self):
        result = agent.measure_gateway(self.serve(200))
        self.assertEqual((result["probes"], result["failure_pct"]), (6, 0.0))
        self.assertTrue(0 <= result["rtt_p50_ms"] <= result["rtt_p95_ms"] < 2000)
        main.NetworkQuality.model_validate(result)

    def test_server_errors_count_as_probe_failures(self):
        result = agent.measure_gateway(self.serve(503))
        self.assertEqual(result["failure_pct"], round(100 / 6, 1))
        self.assertIsNotNone(result["rtt_p50_ms"])

    def test_unreachable_gateway_is_total_failure_with_no_latency(self):
        server = HTTPServer(("127.0.0.1", 0), Health)
        port = server.server_port
        server.server_close()
        result = agent.measure_gateway(f"http://127.0.0.1:{port}", timeout=0.3)
        self.assertEqual((result["failure_pct"], result["rtt_p50_ms"], result["rtt_p95_ms"]), (100.0, None, None))
        main.NetworkQuality.model_validate(result)


class HeartbeatHandler(unittest.IsolatedAsyncioTestCase):
    request = dict(policy_hash="a" * 64, configuration_hashes={}, checks={})

    async def beat(self, quality):
        seen = {}

        async def heartbeat(device, policy_hash, hashes, checks, host, stored_quality):
            seen["quality"] = stored_quality
            return {"state": "active", "compliant": True, "policy_hash": policy_hash}

        with mock.patch.object(endpoint_plane, "heartbeat", heartbeat):
            reply = await main.endpoint_heartbeat(main.ManagedHeartbeat(**self.request, network_quality=quality), {"endpoint_id": "ep"})
        return reply, seen["quality"]

    async def test_bad_measurement_is_dropped_without_failing_the_heartbeat(self):
        good = {"measured_at": datetime.now(UTC).isoformat(), "rtt_p50_ms": 5.0, "rtt_p95_ms": 6.0, "jitter_ms": 0.5, "failure_pct": 0.0, "probes": 6}
        reply, quality = await self.beat(good)
        self.assertEqual((reply["network_quality"], quality["probes"]), ("stored", 6))
        reply, quality = await self.beat({**good, "rtt_p50_ms": -3})
        self.assertEqual((reply["network_quality"], quality, reply["state"]), ("rejected", None, "active"))
        reply, quality = await self.beat(None)
        self.assertEqual((reply["network_quality"], quality), ("absent", None))


class TraceContext(unittest.TestCase):
    def test_only_a_well_formed_traceparent_is_recorded(self):
        good = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        self.assertEqual(mcp_facade._traceparent({"traceparent": good}), good)
        self.assertEqual(mcp_facade._traceparent({"traceparent": good.upper()}), good)
        for bad in ("", "garbage", "00-" + "0" * 32 + "-00f067aa0ba902b7-01", "00-4bf92f3577b34da6a3ce929d0e0e4736-" + "0" * 16 + "-01",
                    good + "-extra", "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"):
            self.assertIsNone(mcp_facade._traceparent({"traceparent": bad}), bad)
        self.assertIsNone(mcp_facade._traceparent({}))


class CorrelationArguments(unittest.TestCase):
    def test_a_decision_or_a_record_but_not_both_or_neither(self):
        for query in ({}, {"decision_id": 1, "kind": "os-event", "record_id": 2}, {"kind": "os-event"}, {"record_id": 3}):
            with self.assertRaises(main.HTTPException) as caught:
                asyncio.run(main.endpoint_correlation(user={}, window_seconds=300, **{"decision_id": None, "kind": None, "record_id": None, **query}))
            self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
