// Console state and data shaping, kept free of the DOM so `node --test` can check it
// (full_stack_lab/tests/console-state.test.mjs). The server already scopes rows to
// the signed-in viewer; nothing here may widen that.
export const FEED_LIMIT = 500;
export const DECISIONS = ["Allow", "Alert", "Restrict", "Approval", "Block"];

/** Newest first, one row per numeric id. A poll that overlaps a page load must not
 * show a call twice, and a malformed row must not push a real decision out. */
export function mergeRows(current, incoming, limit = FEED_LIMIT) {
  const rows = new Map();
  for (const row of [...(current || []), ...(incoming || [])]) {
    const id = Number(row?.id);
    if (Number.isSafeInteger(id) && id > 0) rows.set(id, row);
  }
  return [...rows.values()].sort((a, b) => Number(b.id) - Number(a.id)).slice(0, limit);
}

const SEARCHED = ["who", "department", "workstation", "harness", "server", "tool", "target", "policy_id", "trace_id", "reason"];

/** Search over what is already loaded: person, PC, harness, tool, target, policy or trace id. */
export function searchRows(rows, query = "") {
  const term = String(query).trim().toLocaleLowerCase();
  if (!term) return rows;
  return rows.filter((row) => SEARCHED.some((key) => String(row?.[key] ?? "").toLocaleLowerCase().includes(term))
    || `${row?.server}.${row?.tool}`.toLocaleLowerCase().includes(term));
}

const pad = (n) => String(n).padStart(2, "0");
const clock = (t) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };

/** One status phrase. It never calls a view fresh after a failed poll. */
export function liveLabel({ live, lastOk = 0, failing = false, pending = 0 }) {
  if (failing) return `갱신 실패${lastOk ? ` · 마지막 ${clock(lastOk)}` : ""}`;
  if (!live) return `일시정지${pending ? ` · 대기 ${pending}건` : ""}`;
  return lastOk ? `실시간 · ${clock(lastOk)}` : "실시간 · 연결 중";
}

// MCP clients as they name themselves in `initialize` (clientInfo.name).
const HARNESS = {
  "claude-code": "Claude Code", "codex-mcp-client": "Codex CLI", "gemini-cli-mcp-client": "Gemini CLI",
  opencode: "OpenCode", "inspector-cli": "MCP Inspector", "termination-probe": "종료 점검", mcp: "Python SDK",
};
export const harnessLabel = (name) => HARNESS[name] || name || "알 수 없음";

/** The last 24 hours as 24 hourly buckets, oldest first, with a count per decision.
 * `series` rows are {hour, decision, n} from /api/overview; hours without calls are 0. */
export function hourBuckets(series, now = Date.now()) {
  const HOUR = 3600e3;
  const end = Math.floor(now / HOUR) * HOUR;
  const buckets = Array.from({ length: 24 }, (_, i) => {
    const hour = end - (23 - i) * HOUR;
    return { hour, label: `${pad(new Date(hour).getHours())}시`, total: 0, ...Object.fromEntries(DECISIONS.map((d) => [d, 0])) };
  });
  for (const row of series || []) {
    const index = 23 - Math.round((end - Math.floor(new Date(row.hour).getTime() / HOUR) * HOUR) / HOUR);
    const bucket = buckets[index];
    if (!bucket || !DECISIONS.includes(row.decision)) continue;
    bucket[row.decision] += Number(row.n) || 0;
    bucket.total += Number(row.n) || 0;
  }
  return buckets;
}

/** Count rows by `key`, with a split by decision: [{key, total, Allow, ..., Block}], largest first. */
export function splitBy(rows, key, weight = () => 1) {
  const groups = new Map();
  for (const row of rows || []) {
    const name = typeof key === "function" ? key(row) : row?.[key];
    if (name === undefined || name === null || name === "") continue;
    const g = groups.get(name) || { key: name, total: 0, ...Object.fromEntries(DECISIONS.map((d) => [d, 0])) };
    const n = weight(row);
    if (DECISIONS.includes(row.decision)) g[row.decision] += n;
    g.total += n;
    groups.set(name, g);
  }
  return [...groups.values()].sort((a, b) => b.total - a.total || String(a.key).localeCompare(String(b.key)));
}

/** harness -> server -> decision flows for a Sankey. Layers are kept apart by name so
 * a server called "fetch" never merges with a harness of the same name. */
export function sankeyData(flows, decisionLabel = (d) => d) {
  const nodes = new Map();
  const links = new Map();
  const node = (name, layer) => { if (!nodes.has(name)) nodes.set(name, { name, layer }); return name; };
  const link = (source, target, value) => {
    const k = `${source}\u0000${target}`;
    links.set(k, { source, target, value: (links.get(k)?.value || 0) + value });
  };
  for (const f of flows || []) {
    const n = Number(f.n) || 0;
    if (!n) continue;
    const h = node(harnessLabel(f.harness), 0);
    const s = node(`${f.server} ·`, 1);
    const d = node(decisionLabel(f.decision), 2);
    link(h, s, n);
    link(s, d, n);
  }
  return { nodes: [...nodes.values()], links: [...links.values()] };
}
