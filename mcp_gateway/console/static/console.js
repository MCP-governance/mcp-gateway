/* MCP Proxy Console.
 *
 * Reads what the proxy recorded and manages the proxy's own client keys. It never
 * calls an MCP server (the same rule as the governance console on main): upstream
 * reachability comes from the proxy's HTTP probe, and tool names come from relayed
 * calls. The skeleton - safe html``, tabs, drawer, live feed, charts - is ported from
 * main's console (full_stack_lab/gateway/app/agent_static/console.js).
 */
import {
  OUTCOMES, OUTCOME_LABEL, OUTCOME_TONE, FAILED, mergeRows, searchRows, liveLabel, clientLabel,
  timeBuckets, bucketLabel, pivot, failureRate, sankeyData, formatMs, formatBytes, formatPercent,
} from "./console-state.mjs";
import * as charts from "./charts.mjs";

const TOKEN_KEY = "mcp-proxy-admin-token";
const THEME_KEY = "mcp-proxy-theme";
const token = sessionStorage.getItem(TOKEN_KEY);
if (!token) location.replace("/console/login");

const $ = (selector, root = document) => root.querySelector(selector);

// ── safe HTML ────────────────────────────────────────────────────────────────
// Everything interpolated into html`` is escaped unless it is itself html`` or raw().
// Recorded rows carry strings clients control (tool names, clientInfo, error text).
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
const raw = (s) => new Raw(String(s));
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);
const part = (v) => (v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join("")
  : v === null || v === undefined || v === false ? "" : esc(v));
function html(strings, ...values) {
  let out = strings[0];
  values.forEach((value, i) => { out += part(value) + strings[i + 1]; });
  return new Raw(out);
}
const short = (text, n = 120) => { const s = String(text ?? ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

// ── API ──────────────────────────────────────────────────────────────────────
async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    headers: { authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "content-type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    sessionStorage.removeItem(TOKEN_KEY);
    location.replace("/console/login");
    throw new Error("로그인이 필요합니다.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `요청이 거절되었습니다 (${response.status}).`);
  return data;
}

// ── vocabulary ───────────────────────────────────────────────────────────────
const chip = (tone, label) => html`<span class="chip ${tone}">${label}</span>`;
const outcomeChip = (o) => chip(OUTCOME_TONE[o] || "outline", OUTCOME_LABEL[o] || o || "—");
const HEALTH = { up: ["allow", "정상", "ok"], degraded: ["alert", "응답 이상", "warn"], down: ["block", "연결 안 됨", "bad"], unknown: ["outline", "확인 안 함", ""] };
const healthChip = (state) => chip(...(HEALTH[state] || HEALTH.unknown).slice(0, 2));
const AUTH = { none: "인증 없음", key: "프록시 키", litellm: "LiteLLM 키" };
const PARSE = { ok: "읽음", empty: "본문 없음", none: "본문 없음", not_json: "JSON 아님", truncated: "너무 커서 생략", encoded: "압축·인코딩" };
const pad = (n) => String(n).padStart(2, "0");
function when(value, { seconds = false } = {}) {
  if (!value) return "—";
  const d = new Date(typeof value === "number" ? value * 1000 : value);
  if (Number.isNaN(d.getTime())) return String(value);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}${seconds ? `:${pad(d.getSeconds())}` : ""}`;
  return d.toDateString() === new Date().toDateString() ? hm : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`;
}
function ago(epochSeconds) {
  if (!epochSeconds) return "—";
  const s = Math.round(Date.now() / 1000 - epochSeconds);
  if (s < 60) return "방금";
  if (s < 3600) return `${Math.floor(s / 60)}분 전`;
  if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
  return `${Math.floor(s / 86400)}일 전`;
}
const json = (v) => html`<pre class="json">${JSON.stringify(v, null, 2)}</pre>`;
const kv = (pairs) => html`<dl class="kv">${pairs.filter(([, v]) => v !== undefined && v !== null && v !== "")
  .map(([k, v]) => html`<dt>${k}</dt><dd>${v}</dd>`)}</dl>`;
const empty = (text) => html`<p class="empty">${text}</p>`;
const note = (text, tone = "") => html`<div class="note ${tone}">${text}</div>`;
const PALETTE = ["#1f4287", "#2c5bb8", "#4f7fd6", "#86a8ff", "#0a7f8a", "#9aa6b8", "#647085"];

// ── icons (Lucide, ISC licence) ──────────────────────────────────────────────
const ICON = {
  overview: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  activity: '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
  servers: '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  keys: '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5"/>',
  settings: '<path d="M14 17H5"/><path d="M19 7h-9"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
};
const icon = (name) => raw(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name] || ""}</svg>`);

// ── chrome: toast, drawer, dialog ────────────────────────────────────────────
let toastTimer;
function toast(message, bad = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = bad ? "toast bad" : "toast";
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, bad ? 8000 : 4000);
}

let drawerReturn = null;
function setDrawer(open) {
  const drawer = $("#drawer");
  drawer.classList.toggle("open", open);
  drawer.setAttribute("aria-hidden", String(!open));
  drawer.inert = !open;
  $("#scrim").classList.toggle("show", open);
}
function openDrawer(title, body, tabs = null) {
  if (!$("#drawer").classList.contains("open")) drawerReturn = document.activeElement;
  $("#drawer-title").textContent = title;
  $("#drawer-body").innerHTML = String(tabs ? html`${body}${tabBar(tabs, tabs[0].key, "d")}${tabs.map((t) => tabPanel(t.key, tabs[0].key, t.body, "d"))}` : body);
  setDrawer(true);
  $("#drawer .icon-btn").focus();
}
function closeDrawer() {
  const wasOpen = $("#drawer").classList.contains("open");
  setDrawer(false);
  if (wasOpen && drawerReturn?.isConnected) drawerReturn.focus();
  drawerReturn = null;
}

function ask({ title, body = "", fields = "", confirm = "확인", danger = false, cancel = "취소" }) {
  const dialog = $("#dialog");
  const form = $("#dialog-form");
  form.innerHTML = String(html`<h3>${title}</h3>${body ? html`<p>${body}</p>` : ""}${fields}
    <div class="row">${cancel ? html`<button class="btn" value="cancel" formnovalidate>${cancel}</button>` : ""}
    <button class="btn ${danger ? "danger solid" : "primary"}" value="ok">${confirm}</button></div>`);
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok" ? new FormData(form) : null), { once: true });
  });
}

// ── tabs and page pieces ─────────────────────────────────────────────────────
function tabBar(tabs, active, scope = "p") {
  return html`<div class="tabs" role="tablist">${tabs.map((t) => html`<button class="tab" role="tab" type="button"
    id="${scope}-tab-${t.key}" aria-controls="${scope}-panel-${t.key}" aria-selected="${String(t.key === active)}"
    tabindex="${t.key === active ? 0 : -1}" data-act="tab" data-tab="${t.key}">${t.label}${t.n !== undefined && t.n !== null
      ? html`<span class="n ${t.hot ? "hot" : ""}">${t.n}</span>` : ""}</button>`)}</div>`;
}
function tabPanel(key, active, body, scope = "p") {
  return html`<section class="tabpanel" role="tabpanel" id="${scope}-panel-${key}" aria-labelledby="${scope}-tab-${key}"
    data-panel="${key}" ${key === active ? "" : raw("hidden")}>${body}</section>`;
}
function page({ head, kpis = "", tabs, active }) {
  const current = tabs.some((t) => t.key === active) ? active : tabs[0].key;
  return html`${head}${kpis}${tabBar(tabs, current)}${tabs.map((t) => tabPanel(t.key, current, t.body))}`;
}
const head = (title, { status = "", actions = "" } = {}) => html`<div class="page-head">
  <h1>${title}</h1>${status ? html`<div class="status">${status}</div>` : ""}${actions ? html`<div class="actions">${actions}</div>` : ""}</div>`;
const kpiStrip = (items) => html`<div class="kpis">${items.map(([label, value, tone = "", href = ""]) => href
  ? html`<a class="kpi ${tone}" href="${href}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></a>`
  : html`<div class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value ?? 0}</div></div>`)}</div>`;
const panel = (title, body, { sub = "", tools = "", flush = false } = {}) => html`<section class="panel">
  <header><h2>${title}</h2>${sub ? html`<span class="sub">${sub}</span>` : ""}${tools ? html`<div class="tools">${tools}</div>` : ""}</header>
  <div class="body ${flush ? "flush" : ""}">${body}</div></section>`;
const chartBox = (id, label, size = "") => html`<div class="chart ${size}" id="${id}" role="img" aria-label="${label}"></div>`;
// Widths are set through the CSSOM after render: `style=` attributes are refused by the CSP.
const meter = (share, label, hot = false) => html`<div class="meter ${hot ? "hot" : ""}"><span class="bar-inline"><i data-width="${Math.round(Math.min(1, share) * 100)}"></i></span>${label}</div>`;
function applyWidths(root = document) {
  for (const el of root.querySelectorAll("[data-width]")) el.style.width = `${el.dataset.width}%`;
}

// ── routing ──────────────────────────────────────────────────────────────────
const PAGES = [
  { id: "overview", label: "개요", group: "운영" },
  { id: "activity", label: "활동 로그", group: "운영" },
  { id: "servers", label: "MCP 서버", group: "구성" },
  { id: "keys", label: "클라이언트 키", group: "구성" },
  { id: "settings", label: "설정", group: "구성" },
];
const ROUTES = {};
let routeSeq = 0;
let current = { page: "", arg: "", query: new URLSearchParams() };
let downCount = 0;

function renderNav(active) {
  const groups = new Map();
  for (const p of PAGES) {
    if (!groups.has(p.group)) groups.set(p.group, []);
    groups.get(p.group).push(p);
  }
  $("#nav").innerHTML = String(html`${[...groups].map(([group, pages]) => html`<div class="group">${group}</div>${pages.map((p) => html`
    <a href="#/${p.id}" ${active === p.id ? raw('aria-current="page"') : ""}>${icon(p.id)}<span>${p.label}</span>
      ${p.id === "servers" && downCount ? html`<span class="count">${downCount}</span>` : ""}</a>`)}`)}`);
}

function parseHash() {
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const [pageId = "", arg = ""] = path.split("/").map(decodeURIComponent);
  return { page: pageId, arg, query: new URLSearchParams(query) };
}

async function route() {
  stopLive();
  closeDrawer();
  charts.disposeAll();
  const at = parseHash();
  const id = PAGES.some((p) => p.id === at.page) ? at.page : "overview";
  if (id !== at.page) { location.replace(`#/${id}`); return; }
  current = at;
  renderNav(id);
  const seq = ++routeSeq;
  const view = $("#view");
  if (view.dataset.page !== id) view.innerHTML = '<p class="skeleton">불러오는 중…</p>';
  view.dataset.page = id;
  const moved = view.dataset.at !== `${id}/${at.arg}`;
  view.dataset.at = `${id}/${at.arg}`;
  try {
    const out = await ROUTES[id](at.arg, at.query.get("t") || "", at.query);
    if (seq !== routeSeq) return;
    view.innerHTML = String(out.html ?? out);
    applyWidths(view);
    charts.register(out.charts);
    charts.mountVisible(view);
    const h1 = $("h1", view);
    if (h1) {
      document.title = `${h1.textContent.trim()} · MCP Proxy`;
      if (moved) { h1.tabIndex = -1; h1.focus(); }
    }
    out.after?.();
  } catch (error) {
    if (seq === routeSeq) view.innerHTML = String(note(error.message, "bad"));
  }
}
const reload = () => route();

function rememberQuery(changes) {
  const q = new URLSearchParams(current.query);
  for (const [key, value] of Object.entries(changes)) {
    if (value === "" || value === null || value === undefined) q.delete(key); else q.set(key, value);
  }
  current.query = q;
  history.replaceState(null, "", `#/${current.page}${current.arg ? `/${encodeURIComponent(current.arg)}` : ""}${q.size ? `?${q}` : ""}`);
}

// ── overview ─────────────────────────────────────────────────────────────────
const WINDOWS = [[1, "1시간"], [6, "6시간"], [24, "24시간"], [168, "7일"]];
const windowSeg = (hours) => html`<div class="seg" role="group" aria-label="기간">${WINDOWS.map(([h, label]) => html`
  <button type="button" data-act="window" data-h="${h}" aria-pressed="${String(h === hours)}">${label}</button>`)}</div>`;

function recordOff() {
  return note(html`기록이 꺼져 있습니다. <code>proxy.toml</code>의 <code>[store] path</code>를 지정하면 호출 기록과 차트가 채워집니다.`, "warn");
}

function serverStates(servers) {
  const known = servers.filter((s) => s.health?.state && s.health.state !== "unknown");
  return { up: known.filter((s) => s.health.state === "up").length, known: known.length, total: servers.length };
}

ROUTES.overview = async (_, tab, query) => {
  const hours = Number(query.get("h")) || 24;
  const o = await api(`/admin/api/overview?hours=${hours}`);
  downCount = o.servers.filter((s) => s.health?.state === "down").length;
  renderNav("overview");
  const s = o.summary;
  const states = serverStates(o.servers);
  const status = html`${o.recorder.enabled ? chip("allow", "기록 중") : chip("outline", "기록 꺼짐")}
    ${chip("brand", o.auth.providers.length ? o.auth.providers.map((p) => ({ keys: "프록시 키", litellm: "LiteLLM 키" }[p])).join(" + ") : "인증 없음")}
    ${o.recorder.dropped ? chip("block", `기록 누락 ${o.recorder.dropped}건`) : ""}`;
  const pageHead = head("개요", { status, actions: windowSeg(hours) });
  if (!s) {
    return { html: html`${pageHead}${recordOff()}<div class="stack">${panel("서버 상태", serverTable(o.servers), { flush: true })}</div>`, after: () => applyWidths() };
  }
  const totals = s.totals;
  const all = OUTCOMES.reduce((sum, key) => sum + (totals[key] || 0), 0);
  const toolCalls = s.tools.reduce((sum, t) => sum + t.n, 0);
  const rate = failureRate(totals);
  const kpis = kpiStrip([
    ["요청", all, "", "#/activity"],
    ["성공률", rate === null ? "—" : formatPercent(1 - rate), rate !== null && rate > 0.1 ? "alert" : "allow"],
    ["도구 호출", toolCalls],
    ["거부", totals.denied || 0, totals.denied ? "block" : "", "#/activity?outcome=denied"],
    ["진행 중", o.active],
    ["서버 정상", states.known ? `${states.up}/${states.total}` : "—", states.known && states.up < states.total ? "block" : "", "#/servers"],
    ["응답 시작 p95", formatMs(s.latency.p95)],
  ]);
  const buckets = timeBuckets(s.series, { since: o.since, now: o.now, bucket: o.bucket_seconds });
  const byServer = pivot(s.servers, "server");
  const byPrincipal = pivot(s.principals, "principal");
  const outcomeItems = OUTCOMES.filter((key) => totals[key]).map((key) => ({ name: OUTCOME_LABEL[key], value: totals[key], color: charts.outcomeColor(key) }));
  const toolItems = s.tools.map((t) => ({ name: `${t.server} · ${t.tool}`, value: t.n, server: t.server, tool: t.tool }));
  const latencyItems = Object.entries(s.latency.servers).map(([name, v]) => ({ name, p50: v.p50, p95: v.p95 }));
  const tabs = [
    { key: "traffic", label: "트래픽", body: html`<div class="stack">
      ${panel("시간대별 요청", chartBox("c-traffic", "시간대별 요청 결과", "lg"), { sub: `${WINDOWS.find(([h]) => h === hours)?.[1] || `${hours}시간`} · 결과별` })}
      <div class="grid c2">
        ${panel("결과 비율", all ? chartBox("c-outcomes", "결과 비율") : empty("요청 없음"))}
        ${panel("많이 쓰인 MCP 메서드", s.methods.length ? chartBox("c-methods", "메서드별 요청") : empty("기록된 메서드 없음"))}
      </div></div>` },
    { key: "servers", label: "서버·도구", n: byServer.length, body: html`<div class="stack">
      ${panel("서버별 요청", byServer.length ? chartBox("c-servers", "서버별 요청 결과", "sm") : empty("요청 없음"), { sub: "막대를 누르면 활동 로그" })}
      <div class="grid c2">
        ${panel("많이 쓰인 도구", toolItems.length ? chartBox("c-tools", "도구별 호출") : empty("도구 호출 없음"), { sub: "막대를 누르면 활동 로그" })}
        ${panel("응답 시작 지연", latencyItems.length ? chartBox("c-latency", "서버별 응답 시작 지연") : empty("측정값 없음"), { sub: "p50 · p95" })}
      </div></div>` },
    { key: "people", label: "사용자·클라이언트", n: byPrincipal.length, body: html`<div class="stack">
      ${panel("사용자 → 서버 → 결과", s.flows.length ? chartBox("c-flow", "사용자에서 서버, 결과로 이어지는 흐름", "xl") : empty("요청 없음"))}
      <div class="grid c2">
        ${panel("사용자별 요청", byPrincipal.length ? chartBox("c-principals", "사용자별 요청 결과") : empty("요청 없음"))}
        ${panel("클라이언트", s.clients.length ? chartBox("c-clients", "클라이언트 비율") : empty("기록된 클라이언트 없음"), { sub: "initialize의 clientInfo" })}
      </div></div>` },
  ];
  return {
    html: page({ head: pageHead, kpis, tabs, active: tab }),
    charts: {
      "c-traffic": () => charts.outcomeColumns(buckets.keys.map((k) => bucketLabel(k, o.bucket_seconds)), buckets.rows),
      "c-outcomes": () => charts.donut(outcomeItems),
      "c-methods": () => charts.bars(s.methods.map((m) => ({ name: short(m.method, 40), value: m.n }))),
      "c-servers": () => charts.outcomeColumns(byServer.map((r) => r.name), byServer, {
        horizontal: true, onClick: (p) => { location.hash = `#/activity?server=${encodeURIComponent(p.name)}`; } }),
      "c-tools": () => charts.bars(toolItems, { onClick: (p) => {
        const item = toolItems[p.dataIndex];
        location.hash = `#/activity?server=${encodeURIComponent(item.server)}&tool=${encodeURIComponent(item.tool)}`;
      } }),
      "c-latency": () => charts.latency(latencyItems),
      "c-flow": () => charts.sankey(sankeyData(s.flows)),
      "c-principals": () => charts.outcomeColumns(byPrincipal.slice(0, 15).map((r) => r.name), byPrincipal.slice(0, 15), { horizontal: true }),
      "c-clients": () => charts.donut(s.clients.map((c, i) => ({ name: clientLabel(c.client), value: c.n, color: PALETTE[i % PALETTE.length] }))),
    },
  };
};

// ── activity ─────────────────────────────────────────────────────────────────
// One list, polled every 3 seconds with after_id. Paused, it keeps polling but holds
// new rows back and counts them, so the list stops moving without going stale.
const feed = { rows: [], pending: [], filters: { server: "", outcome: "", principal: "", tool: "" }, query: "",
  live: true, lastOk: 0, failing: false, gen: 0, servers: [] };
let liveTimer = null;
function stopLive() { clearInterval(liveTimer); liveTimer = null; feed.gen += 1; }
const feedQuery = (extra) => new URLSearchParams({ ...Object.fromEntries(Object.entries(feed.filters).filter(([, v]) => v)), ...extra });
const maxId = (rows) => rows.reduce((m, r) => Math.max(m, r.id), 0);

function minuteBuckets(rows) {
  if (!rows.length) return { labels: [], rows: [] };
  const times = rows.map((r) => r.ts * 1000);
  const [start, end] = [Math.min(...times), Math.max(...times)];
  const step = ([1, 5, 10, 30, 60, 180].find((m) => (end - start) / (m * 60e3) <= 30) || 360) * 60e3;
  const first = Math.floor(start / step) * step;
  const labels = [];
  const cells = [];
  for (let at = first; at <= end; at += step) {
    const d = new Date(at);
    labels.push(`${pad(d.getHours())}:${pad(d.getMinutes())}`);
    cells.push(Object.fromEntries(OUTCOMES.map((o) => [o, 0])));
  }
  for (const r of rows) {
    const cell = cells[Math.floor((r.ts * 1000 - first) / step)];
    if (cell && r.outcome in cell) cell[r.outcome] += 1;
  }
  return { labels, rows: cells };
}

const methodCell = (r) => (r.tool ? html`<code>${short(r.tool, 48)}</code>` : r.mcp_methods
  ? html`<span class="mono small">${short(r.mcp_methods, 48)}</span>` : html`<span class="muted">${r.http_method}</span>`);

function eventRow(r) {
  return html`<tr class="clickable" tabindex="0" data-act="event" data-id="${r.id}">
    <td class="t">${when(r.ts, { seconds: true })}</td>
    <td>${outcomeChip(r.outcome)}</td>
    <td class="who-cell"><b>${r.principal || "—"}</b><span class="sub">${AUTH[r.auth] || ""}</span></td>
    <td>${r.client_name ? chip("plain", clientLabel(r.client_name)) : html`<span class="muted">—</span>`}</td>
    <td><span class="chip outline mono">${r.server}</span></td>
    <td>${methodCell(r)}</td>
    <td class="clip"><span class="muted">${r.target && r.target !== r.tool ? short(r.target, 60) : r.reason ? short(r.reason, 60) : "—"}</span></td>
    <td class="num mono small">${r.status ?? "—"}</td>
    <td class="num small nowrap">${formatMs(r.ttfb_ms ?? r.duration_ms)}<span class="sub">${r.ttfb_ms !== null && r.ttfb_ms !== undefined ? formatMs(r.duration_ms) : ""}</span></td></tr>`;
}

function renderFeedStatus() {
  const status = $("#feed-status");
  if (!status) return;
  const shown = searchRows(feed.rows, feed.query).length;
  status.textContent = `${shown}/${feed.rows.length}건 · ${liveLabel({ ...feed, pending: feed.pending.length })}`;
  $("#feed-dot").className = `dot ${feed.failing ? "bad" : feed.live ? "on" : ""}`;
  const toggle = $("[data-act='live']");
  if (toggle) toggle.textContent = feed.live ? "일시정지" : `재개${feed.pending.length ? ` (${feed.pending.length})` : ""}`;
}

function renderFeed() {
  const body = $("#feed");
  if (!body) return;
  const focused = document.activeElement?.closest?.("#feed tr")?.dataset.id;
  const shown = searchRows(feed.rows, feed.query);
  body.innerHTML = String(html`${shown.map(eventRow)}`);
  if (focused) $(`#feed tr[data-id="${CSS.escape(focused)}"]`)?.focus();
  const hint = $("#feed-empty");
  hint.hidden = shown.length > 0;
  hint.innerHTML = String(feed.rows.length || feed.query || Object.values(feed.filters).some(Boolean)
    ? html`조건에 맞는 요청 없음 <button class="btn sm" type="button" data-act="feed-reset">조건 초기화</button>` : html`요청 없음`);
  const buckets = minuteBuckets(shown);
  // redraw() only queues a chart that is not on screen yet; mountVisible() draws it.
  charts.redraw("c-feed", () => charts.outcomeColumns(buckets.labels, buckets.rows));
  charts.mountVisible();
  renderFeedStatus();
}

function startLive() {
  stopLive();
  const gen = feed.gen;
  liveTimer = setInterval(async () => {
    try {
      const after = maxId([...feed.rows, ...feed.pending]);
      const data = await api(`/admin/api/events?${feedQuery({ after_id: after, limit: 200 })}`);
      if (gen !== feed.gen) return;
      feed.lastOk = Date.now();
      feed.failing = false;
      if (feed.live) feed.rows = mergeRows(feed.rows, data.events);
      else feed.pending = mergeRows(feed.pending, data.events);
      if (feed.live && data.events.length) renderFeed(); else renderFeedStatus();
    } catch {
      if (gen === feed.gen) { feed.failing = true; renderFeedStatus(); }
    }
  }, 3000);
}

ROUTES.activity = async (_, tab, query) => {
  for (const key of Object.keys(feed.filters)) feed.filters[key] = query.get(key) || "";
  const [data, o] = await Promise.all([
    api(`/admin/api/events?${feedQuery({ limit: 300 })}`).catch((error) => ({ error })),
    api("/admin/api/overview?hours=1"),
  ]);
  if (data.error) return html`${head("활동 로그")}${recordOff()}`;
  feed.rows = mergeRows([], data.events);
  feed.pending = [];
  feed.lastOk = Date.now();
  feed.failing = false;
  feed.servers = o.servers.map((s) => s.name);
  const select = (name, label, options) => html`<select data-filter="${name}" aria-label="${label}">
    <option value="">${label} 전체</option>${options.map(([value, text]) => html`<option value="${value}" ${feed.filters[name] === value ? raw("selected") : ""}>${text}</option>`)}</select>`;
  const filters = html`<div class="filters">
    ${select("server", "서버", feed.servers.map((s) => [s, s]))}
    ${select("outcome", "결과", OUTCOMES.map((key) => [key, OUTCOME_LABEL[key]]))}
    <input data-filter="principal" placeholder="사용자" aria-label="사용자" value="${feed.filters.principal}" />
    ${feed.filters.tool ? html`<span class="chip brand">도구 ${feed.filters.tool} <button class="icon-btn" type="button" data-act="clear-tool" aria-label="도구 조건 지우기">✕</button></span>` : ""}
    <input class="grow" type="search" data-feed-search placeholder="불러온 요청에서 찾기 (도구·대상·오류…)" aria-label="찾기" value="${feed.query}" />
    <span class="live"><span id="feed-dot" class="dot on"></span><span id="feed-status"></span></span></div>`;
  const tableHead = html`<table class="data"><thead><tr><th>시각</th><th>결과</th><th>사용자</th><th>클라이언트</th><th>서버</th>
    <th>메서드·도구</th><th>대상·사유</th><th class="num">HTTP</th><th class="num">응답 시작·전체</th></tr></thead><tbody id="feed"></tbody></table>`;
  return {
    html: html`${head("활동 로그", { actions: html`<button class="btn" type="button" data-act="live">일시정지</button>` })}
      <div class="stack">
        ${panel("불러온 요청의 시간 분포", chartBox("c-feed", "불러온 요청의 시간 분포", "sm"))}
        <section class="panel">${filters}<div class="body flush">${tableHead}<p class="empty" id="feed-empty" hidden></p></div></section>
      </div>`,
    after: () => { renderFeed(); startLive(); },
  };
};

async function showEvent(id) {
  const r = await api(`/admin/api/events/${id}`);
  const summary = kv([
    ["결과", outcomeChip(r.outcome)], ["시각", when(r.ts, { seconds: true })],
    ["사용자", html`${r.principal || "—"} <span class="muted small">${AUTH[r.auth] || ""}</span>`],
    ["키", r.key_id ? html`<code>${r.key_id}</code>` : null], ["서버", html`<code>${r.server}</code>`],
    ["클라이언트", r.client_name ? `${clientLabel(r.client_name)} ${r.client_version || ""}` : null],
    ["사유", r.reason], ["IP", r.client_ip],
  ]);
  const request = kv([
    ["HTTP", `${r.http_method}`], ["MCP 메서드", r.mcp_methods ? html`<code>${r.mcp_methods}</code>` : null],
    ["도구", r.tool ? html`<code>${r.tool}</code>` : null], ["대상", r.target && r.target !== r.tool ? r.target : null],
    ["프로토콜 버전", r.protocol_version], ["세션", r.session ? html`<code>${r.session}</code> <span class="muted small">해시</span>` : null],
    ["본문", `${formatBytes(r.bytes_in)} · ${PARSE[r.request_parse] || r.request_parse || "—"}`],
    ["User-Agent", r.user_agent],
  ]);
  const response = kv([
    ["HTTP 상태", r.status], ["출처", r.source === "proxy" ? "프록시가 응답" : "upstream이 응답"],
    ["오류 코드", r.error_code], ["오류", r.error_message],
    ["서버 메시지", r.server_methods ? html`<code>${r.server_methods}</code>` : null],
    ["SSE 이벤트", r.sse_events || null],
    ["본문", r.source === "upstream" ? `${formatBytes(r.bytes_out)} · ${PARSE[r.response_parse] || r.response_parse || "—"}` : null],
    ["응답 시작", formatMs(r.ttfb_ms)], ["전체", formatMs(r.duration_ms)],
  ]);
  openDrawer(`요청 #${r.id}`, html`<div class="row-actions">${outcomeChip(r.outcome)}<span class="chip outline mono">${r.server}</span>${r.tool ? html`<code>${r.tool}</code>` : ""}</div>`, [
    { key: "summary", label: "요약", body: summary },
    { key: "request", label: "요청", body: html`${request}${r.arguments ? html`<h3>인자</h3>${json(safeParse(r.arguments))}` : ""}` },
    { key: "response", label: "응답", body: response },
    { key: "raw", label: "원본", body: json(r) },
  ]);
}
function safeParse(text) { try { return JSON.parse(text); } catch { return text; } }

// ── servers ──────────────────────────────────────────────────────────────────
function serverStats(o) {
  const byServer = Object.fromEntries(pivot(o.summary?.servers || [], "server").map((r) => [r.name, r]));
  return (name) => {
    const r = byServer[name];
    const total = r?.total || 0;
    const failed = r ? OUTCOMES.filter((x) => FAILED.has(x)).reduce((sum, x) => sum + r[x], 0) : 0;
    return { total, failed, rate: total ? failed / total : null, p95: o.summary?.latency.servers[name]?.p95 };
  };
}

function serverTable(servers) {
  return html`<table class="data"><thead><tr><th>서버</th><th>상태</th><th>URL</th><th class="num">확인 지연</th><th>연결</th></tr></thead>
    <tbody>${servers.map((s) => html`<tr class="clickable" tabindex="0" data-act="server" data-name="${s.name}">
      <td><b>${s.name}</b></td><td>${healthChip(s.health?.state)}</td><td class="mono small clip">${s.url}</td>
      <td class="num small">${formatMs(s.health?.latency_ms)}</td>
      <td>${meter(s.active / s.max_connections, `${s.active}/${s.max_connections}`, s.active / s.max_connections > 0.8)}</td></tr>`)}</tbody></table>`;
}

function serverTile(s, stats) {
  const [, , dot] = HEALTH[s.health?.state] || HEALTH.unknown;
  const st = stats(s.name);
  return html`<div class="tile" role="button" tabindex="0" data-act="server" data-name="${s.name}">
    <div class="top"><span class="dot ${dot}"></span><b>${s.name}</b>${healthChip(s.health?.state)}</div>
    <div class="url">${s.url}</div>
    <div class="stats"><span><b>${st.total}</b>요청 24h</span><span><b>${formatPercent(st.rate)}</b>실패</span>
      <span><b>${formatMs(st.p95)}</b>p95</span></div>
    ${meter(s.active / s.max_connections, `연결 ${s.active}/${s.max_connections}`, s.active / s.max_connections > 0.8)}
    ${s.history?.length ? chartBox(`spark-${s.name}`, `${s.name} 확인 지연 추이`, "spark") : ""}</div>`;
}

ROUTES.servers = async () => {
  const o = await api("/admin/api/overview?hours=24");
  downCount = o.servers.filter((s) => s.health?.state === "down").length;
  renderNav("servers");
  const stats = serverStats(o);
  const states = serverStates(o.servers);
  const kpis = kpiStrip([
    ["서버", o.servers.length], ["정상", states.known ? states.up : "—", "allow"],
    ["연결 안 됨", downCount, downCount ? "block" : ""],
    ["진행 중", o.active],
  ]);
  const sparks = Object.fromEntries(o.servers.filter((s) => s.history?.length).map((s) => [
    `spark-${s.name}`, () => charts.spark(s.history.map((h) => h.latency_ms ?? 0), { tone: s.health?.state === "down" ? "--block" : "--brand" })]));
  return {
    html: html`${head("MCP 서버", { actions: html`<button class="btn" type="button" data-act="check-all">모두 확인</button>` })}${kpis}
      ${states.known ? "" : note(html`도달 확인이 꺼져 있습니다. <code>[health] interval_seconds</code>를 지정하거나 서버마다 확인을 누르세요.`)}
      <div class="tiles">${o.servers.map((s) => serverTile(s, stats))}</div>`,
    charts: sparks,
    after: () => { const name = current.query.get("name"); if (name) showServer(name, o); },
  };
};

async function showServer(name, o = null) {
  o = o || await api("/admin/api/overview?hours=24");
  const s = o.servers.find((x) => x.name === name);
  if (!s) return;
  const st = serverStats(o)(name);
  const tools = (o.summary?.tools || []).filter((t) => t.server === name);
  const failures = o.summary ? (await api(`/admin/api/events?server=${encodeURIComponent(name)}&limit=200`)).events.filter((e) => FAILED.has(e.outcome)).slice(0, 30) : [];
  const h = s.health || {};
  openDrawer(name, html`<div class="row-actions">${healthChip(h.state)}<button class="btn sm" type="button" data-act="check" data-name="${name}">지금 확인</button>
    <a class="btn sm" href="#/activity?server=${encodeURIComponent(name)}">활동 로그</a></div>`, [
    { key: "info", label: "개요", body: kv([
      ["URL", html`<code>${s.url}</code>`], ["upstream 헤더", s.headers.length ? s.headers.join(", ") : "없음"],
      ["마지막 확인", h.checked_at ? `${when(h.checked_at, { seconds: true })} (${ago(h.checked_at)})` : "—"],
      ["확인 결과", h.status ? `HTTP ${h.status}` : h.error], ["확인 지연", formatMs(h.latency_ms)],
      ["연결", `${s.active}/${s.max_connections}`], ["요청 24h", st.total], ["실패율", formatPercent(st.rate)], ["응답 시작 p95", formatMs(st.p95)],
    ]) },
    { key: "tools", label: "도구", n: tools.length, body: tools.length ? html`<table class="data"><thead><tr><th>도구</th><th class="num">호출</th><th class="num">실패</th></tr></thead>
      <tbody>${tools.map((t) => html`<tr><td><code>${t.tool}</code></td><td class="num">${t.n}</td><td class="num">${t.failed || 0}</td></tr>`)}</tbody></table>`
      : empty("기록된 도구 호출 없음") },
    { key: "errors", label: "최근 실패", n: failures.length, hot: failures.length > 0, body: failures.length
      ? html`<table class="data"><tbody>${failures.map((e) => html`<tr class="clickable" tabindex="0" data-act="event" data-id="${e.id}">
        <td class="t">${when(e.ts, { seconds: true })}</td><td>${outcomeChip(e.outcome)}</td><td class="clip">${short(e.error_message || e.reason || e.tool || "", 60)}</td></tr>`)}</tbody></table>`
      : empty("실패 없음") },
  ]);
}

// ── keys ─────────────────────────────────────────────────────────────────────
function keyState(k) {
  const now = Date.now() / 1000;
  if (k.disabled_at) return ["block", "사용 중지"];
  if (k.expires_at && k.expires_at <= now) return ["outline", "만료"];
  return ["allow", "사용 중"];
}

ROUTES.keys = async () => {
  const data = await api("/admin/api/keys").catch((error) => ({ error }));
  if (data.error) return html`${head("클라이언트 키")}${recordOff()}`;
  const active = data.keys.filter((k) => keyState(k)[1] === "사용 중").length;
  const calls = data.keys.reduce((sum, k) => sum + k.usage_24h.calls, 0);
  const kpis = kpiStrip([["키", data.keys.length], ["사용 중", active, "allow"], ["중지·만료", data.keys.length - active], ["요청 24h", calls]]);
  const rows = data.keys.map((k) => html`<tr>
    <td><b>${k.name}</b><span class="sub mono">${k.prefix}…</span></td>
    <td>${chip(...keyState(k))}</td>
    <td><div class="pill-list">${k.servers.map((s) => chip("outline", s === "*" ? "모든 서버" : s))}</div></td>
    <td class="num">${k.rate_per_minute || "무제한"}</td>
    <td class="num">${k.usage_24h.calls}${k.usage_24h.denied ? html`<span class="sub">거부 ${k.usage_24h.denied}</span>` : ""}</td>
    <td class="small">${ago(k.last_used_at)}</td>
    <td class="small">${k.expires_at ? when(k.expires_at) : "없음"}</td>
    <td><div class="row-actions">
      <button class="btn sm" type="button" data-act="key-edit" data-id="${k.id}">권한</button>
      <button class="btn sm ${k.disabled_at ? "" : "danger"}" type="button" data-act="key-toggle" data-id="${k.id}" data-disabled="${k.disabled_at ? "1" : ""}">${k.disabled_at ? "다시 사용" : "사용 중지"}</button>
    </div></td></tr>`);
  keysCache = data;
  return html`${head("클라이언트 키", { actions: html`<button class="btn primary" type="button" data-act="key-new">새 키</button>` })}${kpis}
    ${data.enabled ? "" : note(html`<code>[auth] providers</code>에 <code>"keys"</code>가 없어 이 키로는 아직 인증하지 않습니다.`, "warn")}
    ${panel("키", data.keys.length ? html`<table class="data"><thead><tr><th>이름</th><th>상태</th><th>서버</th><th class="num">분당 한도</th>
      <th class="num">요청 24h</th><th>마지막 사용</th><th>만료</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : empty("키 없음"), { flush: true })}`;
};
let keysCache = null;

const serverChecks = (selected) => html`<fieldset><legend>서버</legend><div class="checks">
  <label class="check"><input type="checkbox" name="servers" value="*" ${selected.includes("*") ? raw("checked") : ""} /> 모든 서버</label>
  ${keysCache.servers.map((s) => html`<label class="check"><input type="checkbox" name="servers" value="${s}" ${selected.includes(s) ? raw("checked") : ""} /> ${s}</label>`)}
</div></fieldset>`;

// ── settings ─────────────────────────────────────────────────────────────────
ROUTES.settings = async () => {
  const c = await api("/admin/api/config");
  const list = (items) => (items.length ? items.join(", ") : "없음");
  return html`${head("설정", { status: chip("outline", `v${c.version}`) })}
    <div class="grid c2">
      ${panel("중계", kv([
        ["연결 제한 시간", `${c.proxy.connect_timeout_seconds}초`], ["읽기 제한 시간", c.proxy.read_timeout_seconds ? `${c.proxy.read_timeout_seconds}초` : "없음 (SSE 유지)"],
        ["쓰기 제한 시간", `${c.proxy.write_timeout_seconds}초`], ["종료 대기", `${c.proxy.shutdown_timeout_seconds}초`],
        ["서버별 연결 한도", c.proxy.max_connections_per_server], ["허용 Origin", list(c.proxy.allowed_origins)],
      ]))}
      ${panel("인증", kv([
        ["방식", c.auth.providers.length ? c.auth.providers.join(" + ") : "없음 (loopback 전용)"],
        ["LiteLLM", c.auth.litellm_url], ["LiteLLM 캐시", c.auth.providers.includes("litellm") ? `${c.auth.litellm_cache_seconds}초` : null],
        ["LiteLLM 키 기본 서버", c.auth.providers.includes("litellm") ? list(c.auth.litellm_default_servers) : null],
        ["LiteLLM 키 서버 지정", c.auth.providers.includes("litellm") ? html`<code>metadata.mcp_proxy_servers</code>` : null],
        ["기본 분당 한도", c.auth.default_rate_per_minute || "무제한"],
      ]))}
      ${panel("기록", kv([
        ["저장 위치", c.store.path ? html`<code>${c.store.path}</code>` : "꺼짐"], ["보관", c.store.path ? `${c.store.retention_days}일` : null],
        ["도구 인자 기록", c.store.path ? (c.store.record_arguments ? "기록함" : "기록 안 함") : null],
        ["기록 건수", c.store.events], ["파일 크기", c.store.bytes !== undefined ? formatBytes(c.store.bytes) : null],
      ]))}
      ${panel("도달 확인", kv([
        ["주기", c.health.interval_seconds ? `${c.health.interval_seconds}초` : "꺼짐"], ["제한 시간", `${c.health.timeout_seconds}초`],
        ["지표", html`<code>/admin/metrics</code> <span class="muted small">Prometheus · 관리자 토큰</span>`],
      ]))}
    </div>
    <div class="stack">${panel("서버", html`<table class="data"><thead><tr><th>이름</th><th>URL</th><th>upstream 헤더</th></tr></thead>
      <tbody>${c.servers.map((s) => html`<tr><td><b>${s.name}</b></td><td class="mono small">${s.url}</td><td class="small">${list(s.headers)}</td></tr>`)}</tbody></table>`,
      { flush: true, sub: "proxy.toml · 바꾸면 재시작" })}</div>`;
};

// ── actions ──────────────────────────────────────────────────────────────────
const ACTIONS = {
  theme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch { /* per-tab theme then */ }
    charts.redrawAll();
  },
  logout() {
    sessionStorage.removeItem(TOKEN_KEY);
    location.replace("/console/login");
  },
  skip() { $("#view").focus(); },
  "close-drawer": closeDrawer,
  tab(el) {
    const key = el.dataset.tab;
    const bar = el.closest(".tabs");
    const scope = bar.parentElement;
    for (const b of bar.querySelectorAll(".tab")) {
      const on = b.dataset.tab === key;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    }
    for (const p of scope.querySelectorAll(":scope > .tabpanel")) p.hidden = p.dataset.panel !== key;
    if (!el.closest(".drawer")) rememberQuery({ t: key });
    charts.mountVisible(scope);
  },
  window(el) { rememberQuery({ h: el.dataset.h }); reload(); },
  event: (el) => showEvent(el.dataset.id),
  server: (el) => showServer(el.dataset.name),
  async check(el) {
    const r = await api(`/admin/api/servers/${encodeURIComponent(el.dataset.name)}/check`, { method: "POST" });
    toast(`${el.dataset.name}: ${(HEALTH[r.state] || HEALTH.unknown)[1]}${r.status ? ` · HTTP ${r.status}` : r.error ? ` · ${r.error}` : ""} · ${formatMs(r.latency_ms)}`, r.state === "down");
    if (current.page === "servers") { rememberQuery({ name: el.dataset.name }); reload(); }
  },
  async "check-all"() {
    const { servers } = await api("/admin/api/servers");
    await Promise.all(servers.map((s) => api(`/admin/api/servers/${encodeURIComponent(s.name)}/check`, { method: "POST" })));
    reload();
  },
  live() {
    feed.live = !feed.live;
    if (feed.live && feed.pending.length) { feed.rows = mergeRows(feed.rows, feed.pending); feed.pending = []; renderFeed(); }
    renderFeedStatus();
  },
  "feed-reset"() { feed.query = ""; location.hash = "#/activity"; },
  "clear-tool"() { rememberQuery({ tool: "" }); reload(); },
  async "key-new"() {
    const form = await ask({
      title: "새 클라이언트 키", confirm: "만들기",
      fields: html`<label>이름<input name="name" required maxlength="100" placeholder="예: 정원재 노트북" /></label>
        ${serverChecks([])}
        <label>분당 한도 (0 = 무제한)<input name="rate" type="number" min="0" max="100000" value="0" /></label>
        <label>만료 (일, 비우면 없음)<input name="days" type="number" min="1" max="3650" /></label>`,
    });
    if (!form) return;
    const servers = form.getAll("servers");
    if (!servers.length) throw new Error("서버를 하나 이상 고르세요.");
    const days = String(form.get("days") || "").trim();
    const created = await api("/admin/api/keys", { method: "POST", body: {
      name: String(form.get("name")).trim(), servers: servers.includes("*") ? ["*"] : servers,
      rate_per_minute: Number(form.get("rate") || 0), expires_days: days ? Number(days) : null,
    } });
    await ask({
      title: "키가 만들어졌습니다", confirm: "닫기", cancel: "",
      body: "이 화면을 닫으면 다시 볼 수 없습니다.",
      fields: html`<div class="secret"><code id="secret">${created.secret}</code><button class="btn sm" type="button" data-act="copy-secret">복사</button></div>`,
    });
    reload();
  },
  async "copy-secret"() {
    const text = $("#secret")?.textContent || "";
    try { await navigator.clipboard.writeText(text); toast("복사했습니다."); } catch { getSelection().selectAllChildren($("#secret")); }
  },
  async "key-edit"(el) {
    const key = keysCache.keys.find((k) => k.id === el.dataset.id);
    const form = await ask({
      title: `${key.name} · 권한`, confirm: "저장",
      fields: html`${serverChecks(key.servers)}
        <label>분당 한도 (0 = 무제한)<input name="rate" type="number" min="0" max="100000" value="${key.rate_per_minute}" /></label>`,
    });
    if (!form) return;
    const servers = form.getAll("servers");
    if (!servers.length) throw new Error("서버를 하나 이상 고르세요.");
    await api(`/admin/api/keys/${encodeURIComponent(key.id)}`, { method: "PATCH", body: {
      servers: servers.includes("*") ? ["*"] : servers, rate_per_minute: Number(form.get("rate") || 0) } });
    toast("저장했습니다.");
    reload();
  },
  async "key-toggle"(el) {
    const disabling = !el.dataset.disabled;
    if (disabling && !await ask({ title: "키 사용 중지", body: "이 키의 요청은 즉시 거부됩니다.", confirm: "사용 중지", danger: true })) return;
    await api(`/admin/api/keys/${encodeURIComponent(el.dataset.id)}`, { method: "PATCH", body: { disabled: disabling } });
    reload();
  },
};

// ── wiring ───────────────────────────────────────────────────────────────────
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-act]");
  if (!el) return;
  const inner = event.target.closest("a[href], button, summary, input, select, textarea, label");
  if (inner && inner !== el && el.contains(inner)) return;
  const fn = ACTIONS[el.dataset.act];
  if (!fn) return;
  event.preventDefault();
  const busy = el.tagName === "BUTTON" && el.dataset.act !== "tab";
  if (busy) el.disabled = true;
  Promise.resolve(fn(el)).catch((error) => toast(error.message, true)).finally(() => { if (busy && el.isConnected) el.disabled = false; });
});
document.addEventListener("change", (event) => {
  const filter = event.target.closest("[data-filter]");
  if (!filter) return;
  rememberQuery({ [filter.dataset.filter]: filter.value.trim() });
  reload();
});
document.addEventListener("input", (event) => {
  if (!event.target.matches("[data-feed-search]")) return;
  feed.query = event.target.value;
  renderFeed();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  if (event.key === "Enter" && !event.isComposing && event.target.matches("tr[data-act], .tile[data-act]")) event.target.click();
  if (event.target.matches('[role="tab"]') && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    const tabs = [...event.target.closest(".tabs").querySelectorAll('[role="tab"]')];
    const i = tabs.indexOf(event.target);
    const next = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: tabs.length - 1 }[event.key];
    const target = tabs[(next + tabs.length) % tabs.length];
    event.preventDefault();
    target.focus();
    target.click();
  }
});

(function applyTheme() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch { /* blocked storage: follow the system */ }
  document.documentElement.dataset.theme = saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
})();

async function boot() {
  const o = await api("/admin/api/overview?hours=1");
  $("#version").textContent = `v${o.version}`;
  $("#who").innerHTML = String(html`<b>관리자</b>${o.servers.length}개 서버`);
  window.addEventListener("hashchange", route);
  await route();
}
boot().catch((error) => { $("#view").innerHTML = String(note(error.message, "bad")); });
