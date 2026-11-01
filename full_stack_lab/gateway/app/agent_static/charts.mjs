import { DECISIONS } from "./console-state.mjs";
import { t } from "./i18n.mjs";

const TOKENS = { Allow: "--allow", Alert: "--alert", Restrict: "--restrict", Approval: "--approval", Block: "--block" };
export const DECISION_LABEL = { Allow: "허용", Alert: "경보", Restrict: "제한", Approval: "승인 대기", Block: "차단" };

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const color = (decision) => css(TOKENS[decision] || "--muted-series");
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function base() {
  return {
    animation: !calm(),
    textStyle: { fontFamily: css("--sans"), fontSize: 13.5, color: css("--ink-2") },
    tooltip: {
      renderMode: "richText", backgroundColor: css("--panel"), borderColor: css("--line-2"), borderWidth: 1,
      textStyle: { color: css("--ink"), fontSize: 13.5 }, confine: true,
    },
    legend: { type: "scroll", pageIconColor: css("--ink-2"), pageTextStyle: { color: css("--ink-2") }, top: 0, left: 0, icon: "circle", itemWidth: 10, itemHeight: 10, itemGap: 18,
      textStyle: { color: css("--ink-2"), fontSize: 13.5 } },
    grid: { left: 4, right: 20, top: 44, bottom: 4, containLabel: true },
  };
}
const axis = (extra = {}) => ({
  axisLine: { lineStyle: { color: css("--line-2") } }, axisTick: { show: false },
  axisLabel: { color: css("--ink-3"), fontSize: 13.5 }, splitLine: { lineStyle: { color: css("--line") } }, ...extra,
});

const live = new Map();
const pending = new Map();
export function register(builders) {
  for (const [id, build] of Object.entries(builders || {})) pending.set(id, build);
}

export function mountVisible(root = document) {
  for (const [id, build] of pending) {
    const el = root.querySelector(`#${CSS.escape(id)}`);
    if (!el || el.closest("[hidden], details:not([open])")) continue;
    pending.delete(id);
    draw(el, build);
  }
}

const values = (option) => (option.series || []).flatMap((s) => [...(s.data || []), ...(s.links || [])])
  .map((d) => (Array.isArray(d) ? d.at(-1) : d && typeof d === "object" ? d.value : d));

export const localize = (v) => (typeof v === "string" ? t(v) : Array.isArray(v) ? v.map(localize)
  : v && Object.getPrototypeOf(v) === Object.prototype ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, localize(x)])) : v);

function chartOption(build) {
  const { onClick, ...built } = build();
  const option = localize(built);
  if (option.series) option.series = option.series.map((series) => ({ ...series, cursor: onClick ? "pointer" : "default" }));
  return { onClick, option };
}

function draw(el, build) {
  const echarts = globalThis.echarts;
  if (!echarts) { el.textContent = "차트를 불러오지 못했습니다."; return; }
  const { onClick, option } = chartOption(build);
  el.classList.toggle("chart-interactive", Boolean(onClick));
  if (!values(option).some((v) => Number(v) > 0)) {
    el.classList.add("is-empty");
    el.replaceChildren(Object.assign(document.createElement("p"), { className: "empty", textContent: "표시할 데이터가 없습니다." }));
    live.set(el, { chart: null, build, observer: null });
    return;
  }
  el.classList.remove("is-empty");
  el.replaceChildren();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  chart.setOption({ ...base(), ...option });
  if (onClick) chart.on("click", onClick);
  const observer = new ResizeObserver(() => chart.resize());
  observer.observe(el);
  live.set(el, { chart, build, observer });
}
export function disposeAll() {
  for (const [el, { chart, observer }] of live) { observer?.disconnect(); chart?.dispose(); live.delete(el); }
  pending.clear();
}
export function redraw(id, build) {
  for (const [el, entry] of live) {
    if (el.id !== id) continue;
    entry.observer?.disconnect(); entry.chart?.dispose(); live.delete(el);
    draw(el, build);
    return;
  }
  pending.set(id, build);
}
export function redrawAll() {
  for (const [el, { chart, build, observer }] of [...live]) {
    observer?.disconnect(); chart?.dispose(); live.delete(el);
    draw(el, build);
  }
}

export function stacked(categories, series, { horizontal = false, onClick, grouped = false, unit = "" } = {}) {
  const cat = axis({ type: "category", data: categories,
    axisLabel: { color: css("--ink-2"), fontSize: 13.5, ...(horizontal ? { width: 160, overflow: "truncate" } : {}) } });
  const val = axis({ type: "value", minInterval: 1 });
  const valueFormatter = unit ? (v) => (v == null ? "—" : `${Math.round(v * 10) / 10} ${unit}`) : undefined;
  return {
    tooltip: { ...base().tooltip, trigger: "axis", axisPointer: { type: "shadow" }, ...(valueFormatter ? { valueFormatter } : {}) },
    xAxis: horizontal ? val : cat,
    yAxis: horizontal ? { ...cat, inverse: true } : val,
    series: series.map((s) => ({
      name: s.name, type: "bar", ...(grouped ? {} : { stack: "s" }), barMaxWidth: horizontal ? 22 : 28,
      itemStyle: { color: s.color }, emphasis: { focus: "series" }, data: s.data,
    })),
    onClick,
  };
}
export function decisionColumns(categories, rows, options = {}) {
  return stacked(categories, DECISIONS.map((d) => ({ name: DECISION_LABEL[d], color: color(d), data: rows.map((r) => r[d] || 0) })), options);
}
export function donut(items, { total = true } = {}) {
  const sum = items.reduce((s, i) => s + (i.value || 0), 0);
  return {
    tooltip: { ...base().tooltip, trigger: "item", formatter: "{b} · {c}건 ({d}%)" },
    legend: { ...base().legend, type: "scroll", top: undefined, bottom: 0, left: "center", orient: "horizontal",
      textStyle: { ...base().legend.textStyle, width: 120, overflow: "truncate" } },
    title: total ? { text: String(sum), subtext: "건", left: "center", top: "33%",
      textStyle: { fontSize: 34.2, fontWeight: 700, color: css("--ink") }, subtextStyle: { color: css("--ink-3"), fontSize: 13.5 } } : undefined,
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
      axisLabel: { color: css("--ink-2"), fontSize: 13.5, width: 180, overflow: "truncate" } }),
    series: [{ type: "bar", barMaxWidth: 20, data: items.map((i) => ({ value: i.value, itemStyle: { color: i.color || css(tone) } })),
      label: { show: true, position: "right", color: css("--ink-2"), formatter: `{c}${unit}` } }],
    onClick,
  };
}
export function sankey({ nodes, links }) {
  const layerColor = [css("--brand"), css("--muted-series")];
  const decisionColor = Object.fromEntries(DECISIONS.map((d) => [DECISION_LABEL[d], color(d)]));
  return {
    legend: { show: false },
    tooltip: { ...base().tooltip, trigger: "item" },
    series: [{
      type: "sankey", left: 8, right: 110, top: 8, bottom: 8, nodeWidth: 14, nodeGap: 12, draggable: false, nodeAlign: "left",
      emphasis: { focus: "adjacency" },
      label: { color: css("--ink"), fontSize: 13.5 },
      lineStyle: { color: "gradient", opacity: 0.35, curveness: 0.5 },
      data: nodes.map((n) => ({ name: n.name, itemStyle: { color: decisionColor[n.name] || layerColor[n.layer] || css("--ink-3") } })),
      links,
    }],
  };
}
