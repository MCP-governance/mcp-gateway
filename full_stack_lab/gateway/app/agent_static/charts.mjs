// Charts on Apache ECharts (vendor/echarts.min.js, loaded as a classic script before
// this module). Colours come from the CSS tokens at mount time, so the decision
// colours in a chart are the same ones the badges use, in both themes. Canvas
// rendering keeps the page inside `style-src 'self'`.
import { DECISIONS } from "./console-state.mjs";

const TOKENS = { Allow: "--allow", Alert: "--alert", Restrict: "--restrict", Approval: "--approval", Block: "--block" };
export const DECISION_LABEL = { Allow: "허용", Alert: "경보", Restrict: "제한", Approval: "승인 대기", Block: "차단" };

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const color = (decision) => css(TOKENS[decision] || "--muted-series");
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function base() {
  return {
    animation: !calm(),
    textStyle: { fontFamily: css("--sans"), fontSize: 14, color: css("--ink-2") },
    // richText: the tooltip is drawn on the canvas, not built as HTML. Series names come
    // from the audit log (a harness names itself), so nothing here may reach innerHTML;
    // HTML tooltips would also need inline style attributes, which the CSP refuses.
    tooltip: {
      renderMode: "richText", backgroundColor: css("--panel"), borderColor: css("--line-2"), borderWidth: 1,
      textStyle: { color: css("--ink"), fontSize: 14 }, confine: true,
    },
    legend: { top: 0, left: 0, icon: "circle", itemWidth: 10, itemHeight: 10, itemGap: 18,
      textStyle: { color: css("--ink-2"), fontSize: 14 } },
    grid: { left: 4, right: 20, top: 44, bottom: 4, containLabel: true },
  };
}
const axis = (extra = {}) => ({
  axisLine: { lineStyle: { color: css("--line-2") } }, axisTick: { show: false },
  axisLabel: { color: css("--ink-3"), fontSize: 13 }, splitLine: { lineStyle: { color: css("--line") } }, ...extra,
});

// ── mounting ─────────────────────────────────────────────────────────────
const live = new Map();          // element -> {chart, option, observer}
const pending = new Map();       // element id -> option builder (mounted when visible)

/** Register charts for the page; mountVisible() draws the ones whose panel is shown. */
export function register(builders) {
  for (const [id, build] of Object.entries(builders || {})) pending.set(id, build);
}

export function mountVisible(root = document) {
  for (const [id, build] of pending) {
    const el = root.querySelector(`#${CSS.escape(id)}`);
    if (!el || el.closest("[hidden]")) continue;
    pending.delete(id);
    draw(el, build);
  }
}

function draw(el, build) {
  const echarts = globalThis.echarts;
  if (!echarts) { el.textContent = "차트를 불러오지 못했습니다."; return; }
  const { onClick, ...option } = build();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  chart.setOption({ ...base(), ...option });
  if (onClick) chart.on("click", onClick);
  const observer = new ResizeObserver(() => chart.resize());
  observer.observe(el);
  live.set(el, { chart, build, observer });
}

/** Drop every chart (route change). */
export function disposeAll() {
  for (const [el, { chart, observer }] of live) { observer.disconnect(); chart.dispose(); live.delete(el); }
  pending.clear();
}

/** Live data changed: rebuild one chart if it is on screen, else keep it for later. */
export function redraw(id, build) {
  for (const [el, entry] of live) {
    if (el.id !== id) continue;
    entry.observer.disconnect(); entry.chart.dispose(); live.delete(el);
    draw(el, build);
    return;
  }
  pending.set(id, build);
}

/** Theme switch: rebuild with the new tokens. */
export function redrawAll() {
  for (const [el, { chart, build, observer }] of live) {
    observer.disconnect(); chart.dispose(); live.delete(el);
    draw(el, build);
  }
}

// ── builders ─────────────────────────────────────────────────────────────
/** Stacked columns (or bars) per category: [{name, color, data}]. */
export function stacked(categories, series, { horizontal = false, onClick } = {}) {
  const cat = axis({ type: "category", data: categories,
    axisLabel: { color: css("--ink-2"), fontSize: 13, ...(horizontal ? { width: 160, overflow: "truncate" } : {}) } });
  const val = axis({ type: "value", minInterval: 1 });
  return {
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: horizontal ? val : cat,
    yAxis: horizontal ? { ...cat, inverse: true } : val,
    series: series.map((s) => ({
      name: s.name, type: "bar", stack: "s", barMaxWidth: horizontal ? 22 : 28,
      itemStyle: { color: s.color }, emphasis: { focus: "series" }, data: s.data,
    })),
    onClick,
  };
}

/** Stacked by decision: traffic over time, calls per server or per person. */
export function decisionColumns(categories, rows, options = {}) {
  return stacked(categories, DECISIONS.map((d) => ({ name: DECISION_LABEL[d], color: color(d), data: rows.map((r) => r[d] || 0) })), options);
}

/** Share of a whole; the total sits in the hole. */
export function donut(items, { total = true } = {}) {
  const sum = items.reduce((s, i) => s + (i.value || 0), 0);
  return {
    tooltip: { ...base().tooltip, trigger: "item", formatter: "{b} · {c}건 ({d}%)" },
    // Legend below, one scrolling row: it fits a narrow panel as well as a wide one. Long
    // names (a harness names itself) are cut with an ellipsis; the tooltip has the full name.
    legend: { ...base().legend, type: "scroll", top: undefined, bottom: 0, left: "center", orient: "horizontal",
      textStyle: { ...base().legend.textStyle, width: 120, overflow: "truncate" } },
    title: total ? { text: String(sum), subtext: "건", left: "center", top: "33%",
      textStyle: { fontSize: 30, fontWeight: 700, color: css("--ink") }, subtextStyle: { color: css("--ink-3"), fontSize: 14 } } : undefined,
    series: [{
      type: "pie", radius: ["48%", "72%"], center: ["50%", "44%"], avoidLabelOverlap: true,
      label: { show: false }, itemStyle: { borderColor: css("--panel"), borderWidth: 2 },
      data: items.filter((i) => i.value).map((i) => ({ name: i.name, value: i.value, itemStyle: { color: i.color } })),
    }],
  };
}

/** Plain horizontal bars (top-N lists). */
export function bars(items, { unit = "건", tone = "--brand", onClick } = {}) {
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { ...base().grid, top: 8 },
    xAxis: axis({ type: "value", minInterval: 1 }),
    yAxis: axis({ type: "category", data: items.map((i) => i.name), inverse: true,
      axisLabel: { color: css("--ink-2"), fontSize: 14, width: 180, overflow: "truncate" } }),
    series: [{ type: "bar", barMaxWidth: 20, data: items.map((i) => ({ value: i.value, itemStyle: { color: i.color || css(tone) } })),
      label: { show: true, position: "right", color: css("--ink-2"), formatter: `{c}${unit}` } }],
    onClick,
  };
}

/** Harness -> server -> decision flows. */
export function sankey({ nodes, links }) {
  const layerColor = [css("--brand"), css("--muted-series")];
  const decisionColor = Object.fromEntries(DECISIONS.map((d) => [DECISION_LABEL[d], color(d)]));
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "item" },
    series: [{
      type: "sankey", left: 8, right: 110, top: 8, bottom: 8, nodeWidth: 14, nodeGap: 12, draggable: false,
      emphasis: { focus: "adjacency" },
      label: { color: css("--ink"), fontSize: 14 },
      lineStyle: { color: "gradient", opacity: 0.35, curveness: 0.5 },
      data: nodes.map((n) => ({ name: n.name, itemStyle: { color: decisionColor[n.name] || layerColor[n.layer] || css("--ink-3") } })),
      links,
    }],
  };
}

/** Role x (data class, action) grid coloured by the decision OPA returned. */
export function decisionGrid(rows, cols, cells) {
  const index = Object.fromEntries(DECISIONS.map((d, i) => [d, i]));
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "item", formatter: (p) => `${rows[p.value[1]]} · ${cols[p.value[0]]}\n${p.data.label}` },
    grid: { left: 4, right: 12, top: 8, bottom: 8, containLabel: true },
    xAxis: axis({ type: "category", data: cols, position: "top", splitArea: { show: false },
      axisLabel: { color: css("--ink-2"), fontSize: 14, interval: 0 } }),
    yAxis: axis({ type: "category", data: rows, inverse: true, axisLabel: { color: css("--ink"), fontSize: 15, fontWeight: 600 } }),
    visualMap: { show: false, type: "piecewise", dimension: 2,
      pieces: DECISIONS.map((d, i) => ({ value: i, color: color(d) })) },
    series: [{
      type: "heatmap", itemStyle: { borderColor: css("--panel"), borderWidth: 4, borderRadius: 6 },
      label: { show: true, color: "#fff", fontSize: 14, fontWeight: 600, formatter: (p) => p.data.label },
      data: cells.map((c) => ({ value: [c.x, c.y, index[c.decision] ?? 0], label: DECISION_LABEL[c.decision] || c.decision })),
    }],
  };
}

/** Columns by category without a decision split (e.g. requests per status). */
export function columns(items, { tone = "--brand" } = {}) {
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { ...base().grid, top: 16 },
    xAxis: axis({ type: "category", data: items.map((i) => i.name), axisLabel: { color: css("--ink-2"), fontSize: 14, interval: 0 } }),
    yAxis: axis({ type: "value", minInterval: 1 }),
    series: [{ type: "bar", barMaxWidth: 36, data: items.map((i) => ({ value: i.value, itemStyle: { color: i.color || css(tone) } })),
      label: { show: true, position: "top", color: css("--ink-2") } }],
  };
}
