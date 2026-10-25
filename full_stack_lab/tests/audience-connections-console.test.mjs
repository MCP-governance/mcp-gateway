// D-234 사용 대상과 D-235 「내 연결」: 설계된 정상 흐름이 화면에서 끊기지 않는지.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const cut = (from, to) => source.slice(source.indexOf(from), source.indexOf(to));
const safeHTML = cut("class Raw {", "const short = ");
const audience = cut("const AUDIENCE = ", "function validityChip(");
const connectionsRoute = cut("const CONNECTION_KIND = ", "ROUTES.intake = ");
const handlers = cut('  async "server-audience"(el) {', '  async "intake-accept-risk"(el) {')
  + cut("  async disconnect(el) {", '  async "connect-device"(el) {');
const connectForm = cut('  async "connect-token"(form) {', '  "sbom-impact"(form) {');

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
    const chip = (tone, label) => html\`<span class="chip \${tone}">\${label}</span>\`;
    const empty = (text) => html\`<p class="empty">\${text}</p>\`;
    const panel = (title, body, { sub = "", end = "" } = {}) => html\`<section><h2>\${title}</h2><p>\${sub}</p>\${end}\${body}</section>\`;
    ${audience}\n${connectionsRoute}
    globalThis.actions = {${handlers}};
    globalThis.forms = {${connectForm}};
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

const connection = (extra = {}) => ({ server_id: "git-1", name: "GitHub", service: "GitHub", token_url: "https://github.com/settings/personal-access-tokens/new",
  device: false, connected: false, expired: false, account: null, kind: null, connected_at: null, expires_at: null, last_used_at: null, ...extra });
async function renderConnections(connections, available = true) {
  const { context } = build({ api: async () => ({ connections, available }) });
  return String((await context.ROUTES.connections()).tabs[0].body);
}

test("내 연결: 연결 없음은 토큰 입력과 연결 버튼, 장치 인증 버튼은 사용할 수 있을 때만", async () => {
  const none = await renderConnections([connection()]);
  assert.match(none, /data-form="connect-token" data-id="git-1"/);
  assert.match(none, /type="password"/);
  assert.match(none, /연결 안 됨/);
  assert.doesNotMatch(none, /connect-device/);
  assert.equal(english(none), null);
  assert.match(await renderConnections([connection({ device: true })]), /data-act="connect-device"/);
});

test("내 연결: 연결됨은 계정·방식·시각과 해제 버튼, 값(토큰)은 어디에도 없다", async () => {
  const markup = await renderConnections([connection({ connected: true, account: "octo", kind: "token",
    connected_at: "2026-10-25T01:00:00Z", expires_at: null, last_used_at: null })]);
  assert.match(markup, /<b>octo<\/b>/);
  assert.match(markup, /개인 액세스 토큰/);
  assert.match(markup, /data-act="disconnect" data-id="git-1"/);
  assert.match(markup, /연결됨/);
  assert.match(markup, /마지막 사용<\/th><td><span class="muted">—<\/span>|마지막 사용<\/th><td>—/);
  assert.doesNotMatch(markup, /type="password"/);
  assert.equal(english(markup), null);
});

test("내 연결: 만료된 연결은 다시 연결하는 입력을 보여 준다", async () => {
  const markup = await renderConnections([connection({ connected: true, expired: true, account: "octo", kind: "token" })]);
  assert.match(markup, /만료/);
  assert.match(markup, /data-form="connect-token"/);
  assert.doesNotMatch(markup, /data-act="disconnect"/);
});

test("내 연결: 보관 키가 없으면 연결 불가, 서버가 없으면 빈 상태 문구", async () => {
  assert.match(await renderConnections([connection()], false), /연결 불가/);
  assert.match(await renderConnections([]), /연결할 계정 없음/);
});

test("연결·해제 후 목록이 다시 그려지고 안내는 한국어", async () => {
  let reloaded = 0;
  const { context, calls, toasts } = build({ api: async () => ({ account: "octo" }) });
  context.reload = () => { reloaded += 1; };
  const form = { dataset: { id: "git-1" }, reset() {} };
  const data = new FormData(); data.set("token", "  ghp_example1234  ");
  context.FormData = function () { return data; };
  await context.forms["connect-token"](form);
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), ["/api/my-connections/git-1/token", { method: "POST", body: { token: "ghp_example1234" } }]);
  assert.deepEqual(toasts[0], ["octo 계정을 연결했습니다.", false]);
  await context.actions.disconnect({ dataset: { id: "git-1" } });
  assert.equal(calls[1][0], "/api/my-connections/git-1");
  assert.equal(calls[1][1].method, "DELETE");
  assert.equal(toasts[1][0], "연결을 해제했습니다.");
  assert.equal(reloaded, 2);
});
