// State and data shaping for the proxy console, without the DOM so `node --test`
// can check it (tests/console-state.test.mjs). Same split as the governance console on main.

export const FEED_LIMIT = 500;

// What happened to a relayed request. The order is the stacking order in charts.
export const OUTCOMES = ["ok", "tool_error", "rpc_error", "incomplete", "upstream_error", "proxy_error", "denied"];
export const OUTCOME_LABEL = {
  ok: "성공", tool_error: "도구 오류", rpc_error: "프로토콜 오류", incomplete: "미완료",
  upstream_error: "upstream 오류", proxy_error: "프록시 오류", denied: "거부",
};
export const OUTCOME_TONE = {
  ok: "allow", tool_error: "alert", rpc_error: "restrict", incomplete: "muted",
  upstream_error: "approval", proxy_error: "fault", denied: "block",
};
export const FAILED = new Set(["tool_error", "rpc_error", "incomplete", "upstream_error", "proxy_error", "denied"]);

/** Merge a polled page into the feed: newest first, no duplicates, bounded. */
export function mergeRows(current, incoming, limit = FEED_LIMIT) {
  const seen = new Map(current.map((row) => [row.id, row]));
  for (const row of incoming) seen.set(row.id, row);
  return [...seen.values()].sort((a, b) => b.id - a.id).slice(0, limit);
}

const SEARCHED = ["principal", "server", "tool", "target", "mcp_methods", "client_name", "error_message", "reason"];

/** Case-insensitive search over the visible text columns of the loaded rows. */
export function searchRows(rows, query = "") {
  const needle = query.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((row) => SEARCHED.some((key) => String(row[key] ?? "").toLowerCase().includes(needle)));
}

/** Live indicator text for the activity feed. */
export function liveLabel({ live, lastOk = 0, failing = false, pending = 0 }, now = Date.now()) {
  if (!live) return pending ? `일시정지 · 새 호출 ${pending}건` : "일시정지";
  if (failing) return "연결 끊김 · 재시도 중";
  const seconds = Math.max(0, Math.round((now - lastOk) / 1000));
  return lastOk ? `실시간 · ${seconds}초 전 갱신` : "실시간";
}

// Clients name themselves in initialize.clientInfo; these are the ones worth a friendly label.
const CLIENTS = {
  "claude-code": "Claude Code", "codex-mcp-client": "Codex CLI", "gemini-cli-mcp-client": "Gemini CLI",
  opencode: "OpenCode", "inspector-cli": "MCP Inspector", "mcp-inspector": "MCP Inspector",
  cursor: "Cursor", "Visual Studio Code": "VS Code", "claude-ai": "Claude Desktop", "mcp": "MCP SDK",
};
export const clientLabel = (name) => (name ? CLIENTS[name] || name : "알 수 없음");

/** Fill the gaps of a bucketed series so the time axis is continuous. */
export function timeBuckets(rows, { since, now, bucket }) {
  const start = Math.floor(since / bucket) * bucket;
  const keys = [];
  for (let t = start; t <= now; t += bucket) keys.push(t);
  const byKey = new Map(keys.map((t) => [t, Object.fromEntries(OUTCOMES.map((o) => [o, 0]))]));
  for (const row of rows) {
    const cell = byKey.get(row.bucket);
    if (cell && row.outcome in cell) cell[row.outcome] += row.n;
  }
  return { keys, rows: keys.map((t) => byKey.get(t)) };
}

/** Axis label for a bucket start (epoch seconds), short when the window is short. */
export function bucketLabel(epochSeconds, bucket) {
  const d = new Date(epochSeconds * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  if (bucket >= 86400) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** {key: {outcome: n}} from rows grouped by one column and outcome; totals sorted high to low. */
export function pivot(rows, key) {
  const out = new Map();
  for (const row of rows) {
    const name = row[key] ?? "";
    if (!out.has(name)) out.set(name, Object.fromEntries(OUTCOMES.map((o) => [o, 0])));
    if (row.outcome in out.get(name)) out.get(name)[row.outcome] += row.n;
  }
  const total = (cell) => OUTCOMES.reduce((sum, o) => sum + cell[o], 0);
  return [...out.entries()].map(([name, cell]) => ({ name, ...cell, total: total(cell) })).sort((a, b) => b.total - a.total);
}

/** Share of calls that did not succeed; null when there were none. */
export function failureRate(totals) {
  const all = OUTCOMES.reduce((sum, o) => sum + (totals[o] || 0), 0);
  if (!all) return null;
  const failed = OUTCOMES.filter((o) => FAILED.has(o)).reduce((sum, o) => sum + (totals[o] || 0), 0);
  return failed / all;
}

/**
 * principal -> server -> outcome. ECharts sankey needs unique node names, and a person
 * may share a name with a server, so every node is keyed by its layer; labels drop it.
 */
export function sankeyData(flows) {
  const nodes = new Map();
  const links = new Map();
  const node = (layer, name) => {
    const id = `${layer}\u0000${name}`;
    if (!nodes.has(id)) nodes.set(id, { name: id, label: name, layer });
    return id;
  };
  const add = (source, target, n) => links.set(`${source}\u0001${target}`, (links.get(`${source}\u0001${target}`) || 0) + n);
  for (const flow of flows) {
    const who = node(0, flow.principal || "익명");
    const server = node(1, flow.server || "?");
    const outcome = node(2, OUTCOME_LABEL[flow.outcome] || flow.outcome);
    add(who, server, flow.n);
    add(server, outcome, flow.n);
  }
  return {
    nodes: [...nodes.values()],
    links: [...links.entries()].map(([key, value]) => {
      const [source, target] = key.split("\u0001");
      return { source, target, value };
    }),
  };
}

export const nodeLabel = (id) => String(id).split("\u0000").slice(1).join("\u0000");

export function formatMs(value) {
  if (value === null || value === undefined) return "—";
  if (value < 1000) return `${Math.round(value)}ms`;
  if (value < 60000) return `${(value / 1000).toFixed(value < 10000 ? 2 : 1)}s`;
  return `${Math.floor(value / 60000)}m ${Math.round((value % 60000) / 1000)}s`;
}

export function formatBytes(value) {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value}B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)}KB`;
  return `${(value / 1024 / 1024).toFixed(1)}MB`;
}

export function formatPercent(share) {
  if (share === null || share === undefined) return "—";
  const percent = share * 100;
  return `${percent < 10 && percent > 0 ? percent.toFixed(1) : Math.round(percent)}%`;
}
