import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

test("polling renders changed visible content and resumes from its cursor without losing UI state", async () => {
  // Exercise the shipped script, its listeners and its actual renderers without a browser or server.
  const elements = new Map(), timers = new Map(), requests = [];
  let timerId = 0, now = Date.parse("2026-10-22T04:00:00Z"), holdEvents, failEvents = false;
  const listeners = new Map();
  const document = {
    hidden: false, activeElement: null,
    getElementById: id => elements.get(id),
    createElement: tag => new Element(tag),
    createTextNode: text => new Element("#text", text),
    addEventListener: (name, callback) => listeners.set(name, callback),
    querySelectorAll: selector => [...elements.values()].filter(element =>
      selector === ".channel" ? element.dataset.channel :
      selector === ".view" ? element.id?.startsWith("view-") : false),
  };
  class Element {
    constructor(tag, text = "") {
      this.tagName = tag.toUpperCase(); this.textContent = text;
      this.children = []; this.dataset = {}; this.handlers = new Map(); this.attributes = {};
      this.value = ""; this.checked = false; this.replacements = 0;
      this.scrollTop = 0; this.scrollHeight = 1000; this.clientHeight = 200;
      const classes = new Set();
      this.classList = {
        toggle(name, force = !classes.has(name)) { if (force) classes.add(name); else classes.delete(name); return force; },
        remove: name => classes.delete(name),
      };
    }
    get firstChild() { return this.children[0]; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) {
      if (this.children.includes(document.activeElement)) document.activeElement = null;
      this.children = children; this.replacements++;
    }
    addEventListener(name, callback) { this.handlers.set(name, callback); }
    setAttribute(name, value) { this.attributes[name] = value; }
    focus() { document.activeElement = this; }
    showModal() { this.open = true; }
    close() { this.open = false; }
    fire(name) { this.handlers.get(name)?.({ preventDefault() {} }); }
  }
  const html = readFileSync(new URL("./static/index.html", import.meta.url), "utf8");
  for (const match of html.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const element = new Element(match[1]); element.id = match[2]; elements.set(element.id, element);
  }
  for (const channel of ["overview", "tasks", "runs", "checks", "wbs"]) {
    const element = new Element("button"); element.dataset.channel = channel;
    elements.set(`channel-${channel}`, element);
  }
  const $ = id => elements.get(id);
  $("overview-author").value = $("checks-author").value = "all";
  $("follow").checked = true;
  const event = (id, overrides = {}) => ({ id, author: "Codex", kind: "message", state: "running",
    task_id: "OPS", body: `event ${id}`, timestamp: new Date(now).toISOString(), ...overrides });
  let events = [event(1)], tasks = [event(1, { kind: "task" })], cursor = 1;
  let runs = [];
  const wbs = JSON.parse(readFileSync(new URL("../llm-wiki/analysis/development-wbs/snapshot.json", import.meta.url)));
  const context = vm.createContext({ document, window: { matchMedia: () => ({ matches: false }) },
    Date: class extends Date { static now() { return now; } },
    setTimeout(callback, delay) { assert.equal(delay, 2000); timers.set(++timerId, callback); return timerId; },
    clearTimeout: id => timers.delete(id),
    async fetch(url) {
      requests.push(url);
      if (url.startsWith("/api/events")) {
        if (holdEvents) await holdEvents;
        if (failEvents) throw new Error("offline");
        const after = Number(new URL(url, "http://console.invalid").searchParams.get("after"));
        return response({ events: events.filter(row => row.id > after), tasks, cursor,
          server_time: new Date(now).toISOString(), malformed_records: 0 });
      }
      return response(url === "/api/runs" ? { runs } : wbs);
    },
  });
  function response(data) { return { ok: true, json: async () => JSON.parse(JSON.stringify(data)) }; }
  const evaluate = code => vm.runInContext(code, context);
  const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
  const tick = async () => {
    assert.equal(timers.size, 1, "one scheduled poll");
    const [id, callback] = [...timers][0]; timers.delete(id); await callback();
  };
  const visibility = async hidden => { document.hidden = hidden; listeners.get("visibilitychange")(); await settle(); };
  const channel = name => $(`channel-${name}`).fire("click");

  evaluate(readFileSync(new URL("./static/app.js", import.meta.url), "utf8"));
  await settle();
  const firstArticle = $("overview-feed").firstChild;
  for (const id of ["thread-feed", "task-list", "checks-feed", "runs", "wbs-rows"]) {
    assert.equal($(id).replacements, 0, `${id} stays unbuilt while hidden`);
  }
  const member = $("members").firstChild;
  await tick();
  assert.equal($("overview-feed").firstChild, firstArticle);
  assert.equal($("members").firstChild, member);
  assert.equal(requests.at(-3), "/api/events?after=1");

  $("overview-author").value = "Codex"; $("overview-author").fire("input");
  $("overview-search").value = "event"; $("overview-search").fire("input");
  $("follow").checked = false; $("follow").fire("input"); $("overview-feed").scrollTop = 123;
  const filteredArticle = $("overview-feed").firstChild;
  events.push(event(++cursor, { author: "Claude", kind: "check" }));
  await tick();
  assert.equal($("overview-feed").firstChild, filteredArticle, "filtered-out arrival does not rebuild the feed");
  events.push(event(++cursor)); await tick();
  assert.equal($("overview-feed").children.length, 2);
  assert.equal($("overview-feed").scrollTop, 123);
  channel("checks");
  $("checks-author").value = "Claude"; $("checks-author").fire("input");
  $("checks-search").value = "OPS"; $("checks-search").fire("input");
  const checkArticle = $("checks-feed").firstChild;
  await tick(); assert.equal($("checks-feed").firstChild, checkArticle);

  channel("tasks");
  let card = $("task-list").firstChild;
  assert.equal(card.tagName, "BUTTON", "native keyboard activation remains available");
  card.focus(); card.fire("click"); card = $("task-list").firstChild;
  assert.equal(document.activeElement, card);
  const threadArticle = $("thread-feed").firstChild;
  await tick(); assert.equal($("task-list").firstChild, card);
  assert.equal($("thread-feed").firstChild, threadArticle);
  tasks = [event(4, { kind: "task", body: "updated task" })]; await tick();
  assert.equal(evaluate("state.selectedTask"), "OPS");
  assert.equal(document.activeElement, $("task-list").firstChild);
  now += 600001; await tick();
  assert.ok($("task-list").firstChild.children.some(child => child.className === "stale"));

  channel("wbs");
  $("wbs-goal-filter").value = wbs.goals[0].id;
  $("wbs-search").value = wbs.items[0].id;
  $("wbs-status-filter").value = "remaining"; $("wbs-goal-filter").fire("input");
  const wbsRow = $("wbs-rows").firstChild;
  await tick(); assert.equal($("wbs-rows").firstChild, wbsRow);
  wbs.summary.progress++; await tick();
  assert.equal($("wbs-goal-filter").value, wbs.goals[0].id);
  assert.equal($("wbs-search").value, wbs.items[0].id);
  assert.equal($("wbs-status-filter").value, "remaining");
  const rowButton = $("wbs-rows").firstChild.firstChild.firstChild;
  rowButton.fire("click"); assert.equal($("detail").open, true);
  await tick(); assert.equal($("detail").open, true);
  $("close").fire("click"); assert.equal($("detail").open, false);

  const beforeHide = requests.length;
  await visibility(true);
  assert.equal(timers.size, 0); await evaluate("poll()"); assert.equal(requests.length, beforeHide);
  events.push(event(++cursor));
  const overviewReplacements = $("overview-feed").replacements;
  await visibility(false);
  assert.equal(requests[beforeHide], "/api/events?after=3");
  assert.equal(evaluate("state.cursor"), 4);
  assert.equal($("overview-feed").replacements, overviewReplacements, "hidden channel stays unbuilt on resume");
  channel("overview"); assert.equal($("overview-feed").children.length, 3);
  assert.equal($("overview-author").value, "Codex"); assert.equal($("overview-search").value, "event");
  assert.equal($("follow").checked, false); assert.equal(evaluate("state.selectedTask"), "OPS");

  // Hide during a request, then resume repeatedly while that same request is pending.
  let release; holdEvents = new Promise(resolve => { release = resolve; });
  const pending = tick(); await settle(); const pendingCount = requests.length;
  await visibility(true); await visibility(false); await visibility(false);
  assert.equal(requests.length, pendingCount, "visibility changes never overlap polls");
  await visibility(true); release(); await pending; holdEvents = null;
  assert.equal(requests.length, pendingCount, "hidden document skips secondary requests");
  assert.equal(timers.size, 0);
  await visibility(false); assert.equal(timers.size, 1);
  failEvents = true; await tick();
  assert.equal($("connection").textContent, "연결 끊김");
  assert.equal(evaluate("state.cursor"), 4);
  failEvents = false; await tick(); assert.equal($("connection").textContent, "연결됨");

  events = [event(1, { body: "replacement event" })]; cursor = 1; await tick();
  assert.equal(evaluate("state.events.length"), 0, "decreased cursor keeps the original clear-and-adopt semantics");
  assert.equal(evaluate("state.cursor"), 1);
  events.push(event(++cursor, { body: "event after reset" }));
  await tick(); assert.equal(evaluate("state.events[0].body"), "event after reset");
  events = Array.from({ length: 1002 }, (_, i) => event(i + 1)); cursor = 1002; await tick();
  assert.equal(evaluate("state.events.length"), 1000); assert.equal(evaluate("state.events[0].id"), 3);
  await tick(); assert.equal(evaluate("state.events.length"), 1000, "idle polls do not duplicate events");
  channel("runs");
  runs = [{ agent: "Codex", task_id: "OPS", outcome: "running", model_check: "unreported", tool_calls: 0 }];
  await tick(); const run = $("runs").firstChild; await tick(); assert.equal($("runs").firstChild, run);
  assert.equal($("checks-author").value, "Claude"); assert.equal($("checks-search").value, "OPS");
  assert.match(html, /id="overview-feed"[^>]*aria-live="polite"/);
  assert.match(html, /id="thread-feed"[^>]*aria-live="polite"/);
});
