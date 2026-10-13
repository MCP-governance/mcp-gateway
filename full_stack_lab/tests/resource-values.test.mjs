import assert from "node:assert/strict";
import test from "node:test";
import { resourceValues } from "../gateway/app/agent_static/console-state.mjs";

const now = Date.parse("2026-10-13T05:00:00Z");
const sample = () => ({
  measured_at: "2026-10-13T05:00:00Z",
  cpu: { percent: 0, scope: "linux_host", interval_seconds: 5 },
  memory: { total_bytes: 17179869184, used_bytes: 8589934592, percent: 50, scope: "linux_host" },
  network: { rtt_ms: 12.35, state: "ok", source: "console_gateway_tcp" },
});

test("resource values retain a real zero CPU and show measured memory and TCP latency", () => {
  assert.deepEqual(resourceValues(sample(), now), {
    cpu: "0.0%", memory: "8.0 / 16.0 GB · 50.0%", latency: "12.3 ms", measuredAt: now,
  });
});

test("missing, stale and invalid timestamps never become healthy zero values", () => {
  const missing = { cpu: "—", memory: "—", latency: "—", measuredAt: null };
  assert.deepEqual(resourceValues(null, now), missing);
  assert.deepEqual(resourceValues({ ...sample(), measured_at: "bad" }, now), missing);
  assert.deepEqual(resourceValues(sample(), now + 30001), missing);
  assert.deepEqual(resourceValues(sample(), now - 5001), missing);
});

test("failed network and unavailable CPU preserve independently valid memory", () => {
  const data = sample();
  data.cpu.percent = null;
  data.network.state = "unavailable";
  data.network.rtt_ms = null;
  const result = resourceValues(data, now);
  assert.equal(result.cpu, "—");
  assert.equal(result.latency, "—");
  assert.equal(result.memory, "8.0 / 16.0 GB · 50.0%");
});

test("unknown scopes, wrong types, negative or out-of-range values are not presented as measurements", () => {
  const data = sample();
  data.cpu.percent = "0";
  data.memory.used_bytes = data.memory.total_bytes + 1;
  data.network.rtt_ms = -2;
  let result = resourceValues(data, now);
  assert.equal(result.cpu, "—");
  assert.equal(result.memory, "—");
  assert.equal(result.latency, "—");
  result = resourceValues({ ...sample(), cpu: { percent: 30, scope: "container" },
    memory: { total_bytes: 0, used_bytes: 0, percent: 0, scope: "linux_host" },
    network: { rtt_ms: 10, state: "ok", source: "other" } }, now);
  assert.equal(result.cpu, "—");
  assert.equal(result.memory, "—");
  assert.equal(result.latency, "—");
});
