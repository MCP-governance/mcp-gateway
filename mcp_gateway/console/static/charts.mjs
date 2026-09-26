// Charts on Apache ECharts (vendor/echarts.min.js, loaded as a classic script before
// this module). Ported from the governance console on main: colours come from the CSS
// tokens at mount time so a chart and a badge mean the same thing in both themes, and
// canvas rendering keeps the page inside `style-src 'self'`.
import { OUTCOMES, OUTCOME_LABEL, OUTCOME_TONE, nodeLabel } from "./console-state.mjs";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const outcomeColor = (outcome) => css(`--${OUTCOME_TONE[outcome] || "muted"}`);
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function base() {
  return {
    animation: !calm(),
    textStyle: { fontFamily: css("--sans"), fontSize: 14, color: css("--ink-2") },
    // richText: tooltips are drawn on the canvas. Principal and client names come from
    // requests (a client names itself), so nothing here may reach innerHTML.
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
const live = new Map();
const pending = new Map();

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

export function disposeAll() {
  for (const [el, { chart, observer }] of live) { observer.disconnect(); chart.dispose(); live.delete(el); }
  pending.clear();
}

export function redraw(id, build) {
  for (const [el, entry] of live) {
    if (el.id !== id) continue;
    entry.observer.disconnect(); entry.chart.dispose(); live.delete(el);
    draw(el, build);
    return;
  }
  pending.set(id, build);
}

export function redrawAll() {
  for (const [el, { chart, build, observer }] of live) {
    observer.disconnect(); chart.dispose(); live.delete(el);
    draw(el, build);
  }
}

// ── builders ─────────────────────────────────────────────────────────────
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

/** Stacked by outcome; only outcomes that occur get a legend entry. */
export function outcomeColumns(categories, rows, options = {}) {
  const present = OUTCOMES.filter((o) => rows.some((r) => r[o]));
  return stacked(categories, (present.length ? present : ["ok"]).map((o) => ({
    name: OUTCOME_LABEL[o], color: outcomeColor(o), data: rows.map((r) => r[o] || 0),
  })), options);
}

export function donut(items, { total = true, unit = "건" } = {}) {
  const sum = items.reduce((s, i) => s + (i.value || 0), 0);
  return {
    tooltip: { ...base().tooltip, trigger: "item", formatter: `{b} · {c}${unit} ({d}%)` },
    legend: { ...base().legend, type: "scroll", top: undefined, bottom: 0, left: "center", orient: "horizontal",
      textStyle: { ...base().legend.textStyle, width: 120, overflow: "truncate" } },
    title: total ? { text: String(sum), subtext: unit, left: "center", top: "33%",
      textStyle: { fontSize: 30, fontWeight: 700, color: css("--ink") }, subtextStyle: { color: css("--ink-3"), fontSize: 14 } } : undefined,
    series: [{
      type: "pie", radius: ["48%", "72%"], center: ["50%", "44%"], avoidLabelOverlap: true,
      label: { show: false }, itemStyle: { borderColor: css("--panel"), borderWidth: 2 },
      data: items.filter((i) => i.value).map((i) => ({ name: i.name, value: i.value, itemStyle: { color: i.color } })),
    }],
  };
}

export function bars(items, { unit = "건", tone = "--brand", onClick } = {}) {
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { ...base().grid, top: 8 },
    xAxis: axis({ type: "value", minInterval: 1 }),
    yAxis: axis({ type: "category", data: items.map((i) => i.name), inverse: true,
      axisLabel: { color: css("--ink-2"), fontSize: 14, width: 200, overflow: "truncate" } }),
    series: [{ type: "bar", barMaxWidth: 20, data: items.map((i) => ({ value: i.value, itemStyle: { color: i.color || css(tone) } })),
      label: { show: true, position: "right", color: css("--ink-2"), formatter: `{c}${unit}` } }],
    onClick,
  };
}

/** principal -> server -> outcome. Node ids carry their layer; labels show the name only. */
export function sankey({ nodes, links }) {
  const layerColor = [css("--brand"), css("--muted-series")];
  const byLabel = Object.fromEntries(OUTCOMES.map((o) => [OUTCOME_LABEL[o], outcomeColor(o)]));
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "item",
      formatter: (p) => (p.dataType === "edge" ? `${nodeLabel(p.data.source)} → ${nodeLabel(p.data.target)} · ${p.data.value}건` : nodeLabel(p.name)) },
    series: [{
      type: "sankey", left: 8, right: 130, top: 8, bottom: 8, nodeWidth: 14, nodeGap: 12, draggable: false,
      emphasis: { focus: "adjacency" },
      label: { color: css("--ink"), fontSize: 14, formatter: (p) => nodeLabel(p.name) },
      lineStyle: { color: "gradient", opacity: 0.35, curveness: 0.5 },
      data: nodes.map((n) => ({ name: n.name, itemStyle: { color: n.layer === 2 ? byLabel[n.label] : layerColor[n.layer] || css("--ink-3") } })),
      links,
    }],
  };
}

/** A small line (probe latency over time) for server tiles. */
export function spark(values, { tone = "--brand" } = {}) {
  return {
    legend: { show: false }, tooltip: { show: false }, animation: false,
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: "category", show: false, data: values.map((_, i) => i) },
    yAxis: { type: "value", show: false, min: 0 },
    series: [{ type: "line", data: values, showSymbol: false, smooth: true,
      lineStyle: { width: 2, color: css(tone) }, areaStyle: { color: css(tone), opacity: 0.12 } }],
  };
}

/** Latency per server: p50 and p95 side by side. */
export function latency(items) {
  return {
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: axis({ type: "category", data: items.map((i) => i.name), axisLabel: { color: css("--ink-2"), fontSize: 14, interval: 0 } }),
    yAxis: axis({ type: "value", axisLabel: { color: css("--ink-3"), fontSize: 13, formatter: "{value}ms" } }),
    series: [
      { name: "p50", type: "bar", barMaxWidth: 24, itemStyle: { color: css("--brand") }, data: items.map((i) => i.p50) },
      { name: "p95", type: "bar", barMaxWidth: 24, itemStyle: { color: css("--muted-series") }, data: items.map((i) => i.p95) },
    ],
  };
}
