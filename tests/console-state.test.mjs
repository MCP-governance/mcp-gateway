// node --test tests/console-state.test.mjs — the console's data shaping, without a browser.
import test from "node:test";
import assert from "node:assert/strict";
import {
  OUTCOMES, mergeRows, searchRows, liveLabel, clientLabel, timeBuckets, bucketLabel, pivot,
  failureRate, sankeyData, nodeLabel, formatMs, formatBytes, formatPercent,
} from "../mcp_gateway/console/static/console-state.mjs";

test("mergeRows keeps newest first, drops duplicates and caps the feed", () => {
  const merged = mergeRows([{ id: 2 }, { id: 1 }], [{ id: 3 }, { id: 2, changed: true }], 2);
  assert.deepEqual(merged, [{ id: 3 }, { id: 2, changed: true }]);
});

test("searchRows matches visible text case-insensitively", () => {
  const rows = [{ tool: "read_text_file", principal: "ysg" }, { tool: "send_email", error_message: "Quota" }];
  assert.equal(searchRows(rows, "QUOTA").length, 1);
  assert.equal(searchRows(rows, "  ").length, 2);
});

test("liveLabel tells paused, failing and fresh apart", () => {
  assert.equal(liveLabel({ live: false, pending: 3 }), "일시정지 · 새 호출 3건");
  assert.equal(liveLabel({ live: true, failing: true }), "연결 끊김 · 재시도 중");
  assert.equal(liveLabel({ live: true, lastOk: 10_000 }, 13_000), "실시간 · 3초 전 갱신");
});

test("timeBuckets fills gaps so the time axis is continuous", () => {
  const out = timeBuckets([{ bucket: 3600, outcome: "ok", n: 2 }, { bucket: 10800, outcome: "denied", n: 1 }],
    { since: 3600, now: 10900, bucket: 3600 });
  assert.deepEqual(out.keys, [3600, 7200, 10800]);
  assert.equal(out.rows[1].ok, 0);
  assert.equal(out.rows[2].denied, 1);
  assert.deepEqual(Object.keys(out.rows[0]), OUTCOMES);
  assert.match(bucketLabel(3600, 3600), /^\d\d:\d\d$/);
  assert.match(bucketLabel(3600, 86400), /^\d\d-\d\d$/);
});

test("pivot totals by key, highest first", () => {
  const rows = pivot([{ server: "a", outcome: "ok", n: 1 }, { server: "b", outcome: "ok", n: 5 }, { server: "a", outcome: "denied", n: 2 }], "server");
  assert.deepEqual(rows.map((r) => [r.name, r.total, r.denied]), [["b", 5, 0], ["a", 3, 2]]);
});

test("failureRate counts every outcome but ok as a failure", () => {
  assert.equal(failureRate({}), null);
  assert.equal(failureRate({ ok: 3, tool_error: 1 }), 0.25);
});

test("sankeyData keeps a person and a server with the same name apart", () => {
  const { nodes, links } = sankeyData([{ principal: "demo", server: "demo", outcome: "ok", n: 2 }]);
  assert.equal(nodes.length, 3);
  assert.deepEqual(nodes.map((n) => nodeLabel(n.name)), ["demo", "demo", "성공"]);
  assert.deepEqual(links.map((l) => l.value), [2, 2]);
});

test("formatters", () => {
  assert.equal(formatMs(12.4), "12ms");
  assert.equal(formatMs(1500), "1.50s");
  assert.equal(formatMs(null), "—");
  assert.equal(formatBytes(2048), "2.0KB");
  assert.equal(formatPercent(0.05), "5.0%");
  assert.equal(formatPercent(0.5), "50%");
  assert.equal(clientLabel("claude-code"), "Claude Code");
  assert.equal(clientLabel(null), "알 수 없음");
});
