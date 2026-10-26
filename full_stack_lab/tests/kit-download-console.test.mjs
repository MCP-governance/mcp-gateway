import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
const action = source.slice(source.indexOf('  async "pc-kit-download"(el) {'), source.indexOf('  async "device-activate"(el) {'));

function harness(fetch, os = "windows", isolated = false) {
  const elements = [], submissions = [], toasts = [];
  const document = {
    getElementById: (id) => elements.find((node) => node.id === id),
    createElement: (tag) => ({
      tag, children: [],
      append(node) { this.children.push(node); },
      remove() { elements.splice(elements.indexOf(this), 1); },
      submit() { submissions.push({ action: this.action, method: this.method, target: this.target,
        enctype: this.enctype, fields: this.children.map(({ name, value, type }) => ({ name, value, type })) }); },
    }),
    body: { append: (node) => elements.push(node) },
  };
  const run = runInNewContext(`({${action}})["pc-kit-download"]`, {
    fetch, document, token: "console-credential", detailText: (value) => value,
    toast: (message) => toasts.push(message),
  });
  const button = { dataset: { os }, textContent: "설치 파일 받기", disabled: false,
    closest: () => ({ querySelector: () => ({ checked: isolated }) }) };
  return { run: () => run(button), button, elements, submissions, toasts };
}

test("each platform uses a small authenticated ticket fetch then a native POST with only a body credential", async () => {
  for (const [os, query] of [["windows", "&packaging=oneclick"], ["macos", "&delivery=command"], ["linux", ""]]) {
    const calls = [];
    const h = harness(async (url, options) => {
      calls.push([url, options]);
      return { ok: true, json: async () => ({ ticket: "x".repeat(43) }), blob() { throw Error("binary fetch must not run"); } };
    }, os, true);
    await h.run();
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], `/api/pc-kit?platform=${os}${query}&isolated=true&issue_ticket=true`);
    assert.equal(calls[0][1].headers.authorization, "Bearer console-credential");
    assert.equal(calls[0][1].method, "POST");
    const form = h.submissions[0];
    assert.equal(form.action, `/api/pc-kit?platform=${os}${query}&isolated=true`);
    assert.equal(form.method, "POST");
    assert.equal(form.enctype, "application/x-www-form-urlencoded");
    assert.equal(form.target, "pc-kit-download-frame");
    assert.equal(JSON.stringify(form.fields), JSON.stringify([{ name: "ticket", value: "x".repeat(43), type: "hidden" }]));
    assert.equal(h.elements.length, 1, "the form and its ticket are removed after submitting");
    assert.equal(h.elements[0].tag, "iframe");
    assert.equal(h.elements[0].hidden, true);
    assert.equal(h.toasts[0], "다운로드를 시작했습니다. 브라우저 다운로드 목록을 확인하세요.");
    assert.equal(h.button.disabled, false);
    assert.equal(h.button.textContent, "설치 파일 받기");
  }
});

test("the button stays disabled with a preparation label until ticket issuance finishes", async () => {
  let finish;
  const h = harness(() => new Promise((resolve) => { finish = resolve; }));
  const pending = h.run();
  assert.equal(h.button.disabled, true);
  assert.equal(h.button.textContent, "준비 중…");
  assert.equal(h.submissions.length, 0);
  finish({ ok: true, json: async () => ({ ticket: "x".repeat(43) }) });
  await pending;
  assert.equal(h.button.disabled, false);
});

test("server errors retain their Korean detail and network or invalid JSON failures use Korean", async () => {
  for (const [fetch, message] of [
    [async () => ({ ok: false, json: async () => ({ detail: "다운로드 자격이 만료·사용됐습니다." }) }), "다운로드 자격이 만료·사용됐습니다."],
    [async () => { throw new TypeError("Failed to fetch"); }, "설치 파일을 받지 못했습니다."],
    [async () => ({ ok: true, json: async () => { throw new Error("Invalid JSON"); } }), "설치 파일을 받지 못했습니다."],
    [async () => ({ ok: true, json: async () => ({ ticket: '<script>bad</script>' }) }), "설치 파일을 받지 못했습니다."],
  ]) {
    const h = harness(fetch);
    await assert.rejects(h.run(), { message });
    assert.equal(h.submissions.length, 0);
    assert.equal(h.toasts.length, 0);
    assert.equal(h.button.disabled, false);
    assert.equal(h.button.textContent, "설치 파일 받기");
  }
});

test("repeated downloads reuse the hidden frame without retaining submitted ticket inputs", async () => {
  const h = harness(async () => ({ ok: true, json: async () => ({ ticket: "x".repeat(43) }) }));
  await h.run();
  await h.run();
  assert.equal(h.elements.length, 1);
  assert.equal(h.submissions.length, 2);
});
