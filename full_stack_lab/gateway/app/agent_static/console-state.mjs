// Console state and data shaping, kept free of the DOM so it can be tested on its own.
// The server already scopes rows to the signed-in viewer; nothing here may widen that.
export const FEED_LIMIT = 500;
export const DECISIONS = ["Allow", "Alert", "Restrict", "Approval", "Block"];

export function resourceValues(sample, now = Date.now()) {
  const missing = { cpu: "—", memory: "—", latency: "—", measuredAt: null };
  const timestamp = Date.parse(sample?.measured_at);
  if (!Number.isFinite(timestamp) || now - timestamp > 30000 || timestamp - now > 5000) return missing;
  const finite = (v) => typeof v === "number" && Number.isFinite(v);
  const percent = (v) => finite(v) && v >= 0 && v <= 100 ? `${v.toFixed(1)}%` : "—";
  const mem = sample.memory || {};
  const bytesValid = finite(mem.total_bytes) && mem.total_bytes > 0 && finite(mem.used_bytes)
    && mem.used_bytes >= 0 && mem.used_bytes <= mem.total_bytes;
  const gib = (n) => (n / 1073741824).toFixed(1);
  return {
    cpu: sample.cpu?.scope === "linux_host" ? percent(sample.cpu.percent) : "—",
    memory: mem.scope === "linux_host" && bytesValid && percent(mem.percent) !== "—"
      ? `${gib(mem.used_bytes)} / ${gib(mem.total_bytes)} GB · ${percent(mem.percent)}` : "—",
    latency: sample.network?.source === "console_gateway_tcp" && sample.network.state === "ok"
      && finite(sample.network.rtt_ms) && sample.network.rtt_ms >= 0
      ? `${sample.network.rtt_ms.toFixed(1)} ms` : "—",
    measuredAt: timestamp,
  };
}

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

const OBSERVATION_CHANNELS = { inventory: "설정", process: "프로세스", network: "네트워크", os: "운영체제" };
const OBSERVATION_STATE = {
  success: ["보고됨", "plain"], partial: ["일부 보고", "alert"], failed: ["실패", "block"],
  disabled: ["중지", "outline"], unauthorized: ["권한 없음", "block"],
  unsupported: ["지원 안 함", "outline"], unknown: ["확인 불가", "outline"],
};
const FRESHNESS_LABEL = { fresh: "최근 보고", stale: "오래됨", unknown: "확인 불가" };

/** Render only bounded observation metadata; never pass the agent's detail object to the page. */
export function observationRows(agents, now = Date.now()) {
  return (agents || []).flatMap((agent) => Object.entries(OBSERVATION_CHANNELS).map(([key, label]) => {
    const report = agent?.detail?.observation?.[key] || {};
    const state = Object.hasOwn(OBSERVATION_STATE, report.state) ? report.state : "unknown";
    const reportedAt = Date.parse(report.reported_at || "");
    const future = Number.isFinite(reportedAt) && reportedAt - now > 5000;
    const age = Number.isFinite(reportedAt) ? (now - reportedAt) / 1000 : null;
    const freshness = future || age === null ? "unknown" : age > 180 ? "stale" : "fresh";
    return {
      endpointId: agent?.endpoint_id || "—", channel: key, channelLabel: label,
      state, stateLabel: OBSERVATION_STATE[state][0], tone: OBSERVATION_STATE[state][1], freshness,
      freshnessLabel: FRESHNESS_LABEL[freshness], reportedAt: report.reported_at || null,
      lastSuccessAt: report.last_success_at || null,
      acceptedCount: Number.isSafeInteger(report.accepted_count) && report.accepted_count >= 0 ? report.accepted_count : null,
      hasError: Boolean(report.error_code),
    };
  }));
}

const LISTENER_SOURCE = { "local-socket": "로컬 소켓", network: "네트워크", "stdio-process": "표준입출력 프로세스" };
const LISTENER_CLASS = { registered: "등록", shadow: "미등록", "retired-residue": "폐기 잔존" };
const MCP_EVIDENCE = { confirmed: "MCP 응답 확인", suspected: "MCP로 추정", unknown: "MCP 여부 미확인" };
const SCAN_STATE = { success: "보고됨", partial: "일부 보고", failed: "실패", disabled: "중지",
  unauthorized: "권한 없음", unsupported: "지원 안 함", unknown: "확인 불가" };

/** Keep listener-only endpoints in the coverage view and expose only display-safe fields. */
export function listenerCoverage(listeners, now = Date.now()) {
  const rows = (listeners || []).filter((item) => item?.classification !== "registered").map((item) => {
    const observedAt = item?.observed_at || null;
    const age = ageSeconds(observedAt, now);
    const future = Number.isFinite(Date.parse(observedAt || "")) && Date.parse(observedAt) - now > 5000;
    const reportedFreshness = item?.freshness;
    const freshness = ["fresh", "stale", "unknown"].includes(reportedFreshness)
      ? reportedFreshness : future || age === null ? "unknown" : age > 180 ? "stale" : "fresh";
    const scanStatus = item?.scan_source_status;
    const scanState = typeof scanStatus === "string" ? scanStatus : scanStatus?.state;
    return {
      id: item?.id ?? null, origin: originLabel(item?.origin), provenance: item?.provenance_state,
      endpointId: item?.endpoint_id || "—", hostname: item?.hostname || "—",
      source: LISTENER_SOURCE[item?.source] || "확인 불가",
      address: item?.address || "—", port: Number.isInteger(item?.port) ? item.port : null,
      processName: item?.process_name || "—", serverName: item?.server_name || item?.registry_name || "—",
      evidence: MCP_EVIDENCE[item?.mcp_evidence] || MCP_EVIDENCE.unknown,
      classification: LISTENER_CLASS[item?.classification] || "확인 불가",
      observedAt, freshness, freshnessLabel: FRESHNESS_LABEL[freshness],
      scanStatusLabel: scanStatus == null ? "" : SCAN_STATE[scanState] || SCAN_STATE.unknown,
    };
  });
  const counts = new Map();
  for (const row of rows) counts.set(row.endpointId, (counts.get(row.endpointId) || 0) + 1);
  return { rows, total: rows.length, byEndpoint: [...counts].map(([endpointId, count]) => ({ endpointId, count })) };
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

const isMs = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0;

/** "4.2 ms", "38 ms", "1.6 s"; "—" for a value that was not measured. */
export function msText(value) {
  if (!isMs(value)) return "—";
  if (value >= 10000) return `${(value / 1000).toFixed(1)} s`;
  return value < 10 ? `${value.toFixed(1)} ms` : `${Math.round(value)} ms`;
}

export function pctText(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100
    ? `${value < 10 && value % 1 ? value.toFixed(1) : Math.round(value)}%` : "—";
}

export const LATENCY_STAGE = {
  identity: "신원 확인", reserve: "호출 예약", schema: "입력 형식", inspect_in: "입력 검사", context: "정책 입력",
  policy: "정책 판정", dispatch: "전송 준비", connect: "서버 연결", list: "계약 재확인", recheck: "실행 전 재판정",
  intent: "실행 기록", call: "도구 실행", close: "세션 종료", inspect_out: "출력 검사",
};

/** One call's stages in path order with their share of the total; unknown keys are dropped. */
export function timingRows(timings) {
  const total = isMs(timings?.total) ? timings.total : null;
  const rows = Object.keys(LATENCY_STAGE).filter((key) => isMs(timings?.[key]))
    .map((key) => ({ key, label: LATENCY_STAGE[key], ms: timings[key],
      share: total ? Math.min(100, Math.round((timings[key] / total) * 100)) : null }));
  return { rows, total };
}

const ORIGIN = { automatic: "자동 수집", manual: "수동 보고", os_event: "운영체제 이벤트" };
export const originLabel = (origin) => ORIGIN[origin] || "—";

const DENIAL_CLASS = { harness_startup: ["outline", "하네스 기동"], blocked_attempt: ["block", "차단된 시도"], unknown: ["outline", "확인 불가"] };
export const denialClass = (value) => DENIAL_CLASS[value] || DENIAL_CLASS.unknown;

const HEX64 = /^[a-f0-9]{64}$/;
export const hashPrefix = (hash) => (HEX64.test(hash || "") ? hash.slice(0, 12) : "—");

export function provenanceView(provenance) {
  const state = provenance?.state === "match" || provenance?.state === "mismatch" ? provenance.state : "unreported";
  return {
    state, label: { match: "일치", mismatch: "불일치", unreported: "—" }[state],
    tone: { match: "allow", mismatch: "block", unreported: "outline" }[state],
    raw: hashPrefix(provenance?.raw_sha256), agent: hashPrefix(provenance?.agent_projection_sha256),
    server: hashPrefix(provenance?.server_projection_sha256),
    steps: Array.isArray(provenance?.transformations) ? provenance.transformations : [],
  };
}

export function countView(page, shown) {
  const total = Number.isSafeInteger(page?.total) && page.total >= 0 ? page.total : shown;
  return { total, shown, truncated: total > shown, label: `전체 ${total.toLocaleString("ko-KR")}건` };
}

export function pager(state, page) {
  const limit = Number.isSafeInteger(page?.limit) && page.limit > 0 ? page.limit : 1;
  const total = Number.isSafeInteger(page?.total) && page.total >= 0 ? page.total : 0;
  return {
    number: state.index + 1, count: Math.max(1, Math.ceil(total / limit)),
    hasPrev: state.index > 0, hasNext: Boolean(page?.next_cursor),
  };
}

const finite = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0;
const trimmed = (v) => (v >= 10 ? String(Math.round(v)) : String(Number(v.toFixed(1))));

export function networkCells(sample) {
  const fresh = sample?.state === "fresh";
  return {
    latency: fresh && finite(sample.rtt_p50_ms) ? `${trimmed(sample.rtt_p50_ms)} ms` : "—",
    failure: fresh && finite(sample.failure_pct) ? `${Number(sample.failure_pct.toFixed(1))}%` : "—",
  };
}

export function denialCount(device) {
  const state = device?.kernel_denials_state;
  if (state === "fresh") return `${Number(device.kernel_denials_24h) || 0}건`;
  return state === "failed" || state === "stale" ? "수집 중단" : null;
}
