// Console state and data shaping, kept free of the DOM so it can be tested on its own.
// The server already scopes rows to the signed-in viewer; nothing here may widen that.
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

// ── control planes ───────────────────────────────────────────────────────────
// A status is never shown alone: it travels with how sure we are. Levels follow the
// evidence kind the server names: 4 endpoint heartbeat, 3 audit record, 2 manual
// vendor-console record, 1 self report, 0 none.
export const EVIDENCE = {
  kernel: { level: 4, label: "엔드포인트 점검", ttl: 180 },
  ledger: { level: 3, label: "감사 기록", ttl: null },
  manual: { level: 2, label: "수동 확인", ttl: 14 * 86400 },
  report: { level: 1, label: "자체 보고", ttl: 6 * 3600 },
  none: { level: 0, label: "기록 없음", ttl: null },
};
export const STATE_TONE = {
  gateway_enforced: "allow", endpoint_enforced: "allow", vendor_enforced: "restrict",
  observed_only: "alert", unknown_not_enrolled: "outline", bypass_possible: "block",
};

/** Seconds since an ISO time, or null. */
export function ageSeconds(iso, now = Date.now()) {
  const t = new Date(iso ?? NaN).getTime();
  return Number.isFinite(t) ? Math.max(0, Math.round((now - t) / 1000)) : null;
}

export function agoText(seconds) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds < 90) return `${seconds}초 전`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}분 전`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)}시간 전`;
  return `${Math.round(seconds / 86400)}일 전`;
}

/** {state, tone, level, evLabel, stale}. An enforced state without fresh evidence of
 * at least a ledger row is drawn neutral, so green always means "seen enforcing". */
export function statusView(item, now = Date.now()) {
  const kind = EVIDENCE[item?.evidence_kind] ? item.evidence_kind : "none";
  const ev = EVIDENCE[kind];
  const age = ageSeconds(item?.evidence_at, now);
  const stale = ev.ttl !== null && (age === null || age >= ev.ttl);
  let tone = STATE_TONE[item?.state] || "outline";
  if (tone === "allow" && (ev.level < 3 || stale)) tone = "outline";
  const ref = kind === "ledger" && item?.evidence_ref ? ` #${item.evidence_ref}` : "";
  const evLabel = kind === "none" ? (item?.state === "gateway_enforced" ? "경유 기록 없음" : ev.label)
    : `${ev.label}${ref}${age !== null ? ` · ${agoText(age)}` : ""}${stale ? " · 만료" : ""}`;
  return { state: item?.state || "unknown_not_enrolled", tone, level: stale ? Math.min(ev.level, 1) : ev.level, evLabel, stale };
}

/** One row per item_key; the PCs and owners that reported it are folded into a count. */
export function dedupeItems(items) {
  const groups = new Map();
  for (const item of items || []) {
    const key = item?.item_key || item?.key;
    if (!key) continue;
    const g = groups.get(key);
    if (!g) { groups.set(key, { ...item, key, pcs: 1, owners: [item.owner].filter(Boolean), devices: [item.device].filter(Boolean) }); continue; }
    g.pcs += 1;
    if (item.owner && !g.owners.includes(item.owner)) g.owners.push(item.owner);
    if (item.device && !g.devices.includes(item.device)) g.devices.push(item.device);
    // The worst state wins: one open PC makes the item bypassable.
    if (item.state === "bypass_possible") g.state = "bypass_possible";
    g.bypass = [...new Set([...(g.bypass || []), ...(item.bypass || [])])];
  }
  return [...groups.values()];
}

/** The five stops of one audit row: source, gateway, endpoint, upstream, response. */
export function pipelineOf(row) {
  const connection = row?.event_kind === "mcp-connection";
  const endpoint = (row?.planes || []).includes("endpoint");
  const upstream = row?.executed ? "executed" : row?.attempted ? "unknown" : "not_sent";
  return [
    { key: "source", state: row?.device_id ? "signed" : "reported" },
    { key: "gateway", state: connection ? "refused-connection" : "decided", decision: row?.decision, policy: row?.policy_id },
    { key: "endpoint", state: endpoint ? "bound" : "none" },
    { key: "upstream", state: upstream },
    { key: "response", state: row?.response || (upstream === "not_sent" ? "not_executed" : "unknown") },
  ];
}
