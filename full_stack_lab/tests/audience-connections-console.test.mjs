// 사용 대상 설정의 화면과 요청 처리를 확인한다.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const cut = (from, to) => source.slice(source.indexOf(from), source.indexOf(to));
const safeHTML = cut("class Raw {", "const short = ");
const audience = cut("const AUDIENCE = ", "function validityChip(");
const handlers = cut('  async "server-audience"(el) {', '  async "intake-accept-risk"(el) {');

function build(overrides = {}) {
  const calls = [], toasts = [];
  const context = vm.createContext({
    FormData, encodeURIComponent, ROUTES: {}, NONE: "—", calls, toasts,
    registry: { registrations: { "git-1": { allowed_principals: ["*"] } }, servers: [{ id: "git-1", display_name: "GitHub" }] },
    api: async (...args) => { calls.push(args); return overrides.api ? overrides.api(...args) : {}; },
    gw: async (...args) => { calls.push(args); return {}; },
    ask: async () => overrides.form || null,
    page: (value) => value, head: (value) => value,
    when: (value) => `시각:${value}`, reload: () => {}, closeDrawer: () => {},
    toast: (message, error = false) => toasts.push([message, error]),
  });
  vm.runInContext(`${safeHTML}
    ${cut("const kv = ", "const empty = ")}
    const chip = (tone, label) => html\`<span class="chip \${tone}">\${label}</span>\`;
    const empty = (text) => html\`<p class="empty">\${text}</p>\`;
    const panel = (title, body, { sub = "", end = "" } = {}) => html\`<section><h2>\${title}</h2><p>\${sub}</p>\${end}\${body}</section>\`;
    ${audience}
    globalThis.actions = {${handlers}};
    globalThis.fields = audienceFields; globalThis.body = audienceBody; globalThis.text = audienceText;`, context);
  return { context, calls, toasts };
}
const plain = (markup) => String(markup).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
const english = (markup) => plain(markup).replace(/GitHub|MINT|octo/g, "").match(/[A-Za-z]{4,}/g);

test("사용 대상은 기본이 전체 직원이고 지정 직원 칸은 숨겨져 있다", () => {
  const { context } = build();
  const markup = String(context.fields("all"));
  assert.match(markup, /<option value="all" selected>전체 직원<\/option>/);
  assert.match(markup, /<option value="requester" >신청자만/);
  assert.match(markup, /<option value="selected" >지정 직원/);
  assert.match(markup, /data-audience-users hidden/);
  assert.match(String(context.fields("selected")), /data-audience-users >/);
  assert.equal(english(markup), null);
});

test("사용 대상 본문: 지정 직원일 때만 아이디를 보내고, 나머지는 빈 목록", () => {
  const { context } = build();
  const fd = (audience, users) => { const f = new FormData(); f.set("audience", audience); f.set("audience_users", users); return f; };
  const json = (value) => JSON.parse(JSON.stringify(value));
  assert.deepEqual(json(context.body(fd("all", "kim"))), { audience: "all", audience_users: [] });
  assert.deepEqual(json(context.body(fd("requester", "kim"))), { audience: "requester", audience_users: [] });
  const picked = context.body(fd("selected", " kim, lee ,,"));
  assert.equal(picked.audience, "selected");
  assert.deepEqual([...picked.audience_users], ["kim", "lee"]);
  assert.equal(context.text(["*"]), "전체 직원");
  assert.equal(context.text(["emp-kim", "emp-lee"]), "emp-kim, emp-lee");
});

test("서버 상세의 사용 대상 변경이 변경 API를 부른다", async () => {
  const form = new FormData(); form.set("audience", "selected"); form.set("audience_users", "kim, lee");
  const { context, calls, toasts } = build({ form });
  await context.actions["server-audience"]({ dataset: { id: "git-1" } });
  assert.equal(calls[0][0], "registry/servers/git-1/audience");
  assert.equal(calls[0][1].method, "POST");
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1].body)), { audience: "selected", users: ["kim", "lee"] });
  assert.deepEqual(toasts[0], ["사용 대상을 변경했습니다.", false]);
  const cancelled = build();
  await cancelled.context.actions["server-audience"]({ dataset: { id: "git-1" } });
  assert.equal(cancelled.calls.length, 0);
});
