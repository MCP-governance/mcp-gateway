import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const safeHTML = source.slice(source.indexOf("class Raw {"), source.indexOf("const short = "));
const route = source.slice(source.indexOf("const CONSENT_STATUS = "), source.indexOf("ROUTES.intake = "));
const handler = source.slice(source.indexOf('  async "consent-server"(el) {'), source.indexOf('  async "audit-event"(el) {'));
const panel = source.slice(source.indexOf("const panel = "), source.indexOf("const chartBox = "));

async function render(consents) {
  const calls = [];
  const context = vm.createContext({
    ROUTES: {}, badges: {}, api: async (...args) => { calls.push(args); return { consents }; },
    NONE: "—", DATA_CLASS: { public: "공개", nonimportant: "일반", important: "중요" },
    page: (value) => value, head: (value) => value, kpiStrip: (value) => value,
    when: (value) => value || "—", destinationText: (value) => (value || []).join(", "),
    reload: () => {}, refreshBadges: () => {}, toast: () => {},
  });
  vm.runInContext(`${safeHTML}\n${panel}\nconst chip = (tone, label) => html\`<span>\${label}</span>\`;
    const empty = (label) => html\`<div>\${label}</div>\`;
    ${route}\nglobalThis.actions = {${handler}};`, context);
  return { page: await context.ROUTES.consent(), context, calls };
}

const row = (id, server_id = "files", status = "PENDING") => ({
  id, server_id, tool_name: `tool${id}`, status, grade: "nonimportant", purpose: "문서 확인",
  terms: { destinations: ["docs.example.test"], inputs: ["path"] },
});

test("six tools produce one server group and one pair of bulk buttons", async () => {
  const { page, context } = await render(Array.from({ length: 6 }, (_, i) => row(i + 1)));
  const markup = String(page.tabs[0].body);
  assert.equal(context.badges.consent, 1);
  assert.equal(page.tabs[0].n, 1);
  assert.equal((markup.match(/data-act="consent-server"/g) || []).length, 2);
  assert.match(markup, /모두 허용/);
  assert.match(markup, /모두 거부/);
  assert.match(markup, /data-consents="1,2,3,4,5,6"/);
  assert.equal((markup.match(/<code>files\.tool/g) || []).length, 6);
  assert.match(markup, /docs.example.test/);
  assert.match(markup, /입력 path/);
  assert.doesNotMatch(markup, /data-act="consent"/);
});

test("server groups and history stay separate, even with a prototype-like server id", async () => {
  const { page, context } = await render([row(1), row(2, "other"), row(3, "__proto__"), row(4, "files", "GRANTED")]);
  assert.equal(context.badges.consent, 3);
  assert.equal(page.tabs[1].n, 1);
  assert.match(String(page.tabs[1].body), /data-act="consent" data-id="4" data-decision="revoke"/);
  assert.doesNotMatch(String(page.tabs[0].body), /data-consents="[^"<]*4/);
});

test("server, purpose, tools, destinations, and input fields are escaped", async () => {
  const payload = '"><img src=x onerror=alert(1)>';
  const c = row(1, payload);
  Object.assign(c, { tool_name: payload, purpose: payload, terms: { destinations: [payload], inputs: [payload] } });
  const { page } = await render([c]);
  const markup = String(page.tabs[0].body);
  assert.doesNotMatch(markup, /<img/);
  assert.match(markup, /&lt;img/);
  assert.doesNotMatch(markup, /style=|<script/);
});

test("bulk handler sends only displayed ids with an encoded server path", async () => {
  const { context, calls } = await render([row(1), row(2)]);
  await context.actions["consent-server"]({ dataset: { id: "files/a", consents: "1,2", decision: "grant" } });
  const [path, options] = calls[1];
  assert.equal(path, "/api/consents/server/files%2Fa");
  assert.deepEqual(JSON.parse(JSON.stringify(options)), { method: "POST", body: { decision: "grant", consent_ids: [1, 2] } });
});

test("unknown enum values use a dash and an empty list has no action", async () => {
  const c = { ...row(1, "files", "NEW_STATUS"), grade: "NEW_GRADE" };
  const { page, context } = await render([c]);
  assert.equal(context.badges.consent, 0);
  assert.doesNotMatch(String(page.tabs[1].body), /NEW_STATUS|NEW_GRADE|data-act/);
  assert.match(String(page.tabs[0].body), /확인할 요청 없음/);
});

test("a server with more than 200 requests includes every tool in the decision snapshot", async () => {
  const { page } = await render(Array.from({ length: 201 }, (_, i) => row(i + 1)));
  assert.match(String(page.tabs[0].body), /,199,200,201"/);
});
