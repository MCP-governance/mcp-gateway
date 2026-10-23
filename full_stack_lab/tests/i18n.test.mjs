import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fragments, pieces } from "./i18n-extract.mjs";

const STATIC = new URL("../gateway/app/agent_static/", import.meta.url);
const HANGUL = /[가-힣]/;
const FILES = ["console.js", "console-state.mjs", "charts.mjs", "login.js", "signup.js", "console.html", "login.html", "signup.html"];
// Text no screen shows: liveLabel is only exercised by tests, "시" is the Korean-only branch of an hour label.
const NOT_SHOWN = new Set(["갱신 실패{}", "· 마지막 {}", "일시정지{}", "· 대기 {}건", "실시간 · {}", "실시간 · 연결 중", "시"]);

globalThis.localStorage = { getItem: () => "en", setItem() {} };
const { makeTranslator, translateTree, t, lang } = await import("../gateway/app/agent_static/i18n.mjs");
const { EN } = await import("../gateway/app/agent_static/i18n-en.mjs");
const translator = makeTranslator(EN);

test("every Korean text the console can show has an English entry", () => {
  const missing = [];
  for (const file of FILES) {
    for (const [fragment, line] of fragments(new URL(file, STATIC))) {
      if (NOT_SHOWN.has(fragment)) continue;
      const out = translator.translate(fragment.replaceAll("{}", "1"));
      if (HANGUL.test(out)) missing.push(`${file}:${line} ${fragment}`);
    }
  }
  assert.deepEqual(missing, [], `영어 사전에 없는 문구 ${missing.length}개`);
});

test("the labels the server sends are in the dictionary", () => {
  const outcomes = readFileSync(new URL("../gateway/app/outcomes.py", import.meta.url), "utf8");
  const words = [...outcomes.matchAll(/"([^"\n]*[가-힣][^"\n]*)"/g)].map((m) => m[1]);
  assert.ok(words.length >= 15);
  assert.deepEqual(words.filter((word) => HANGUL.test(translator.translate(word))), []);
  for (const word of ["관리자", "직원", "협력업체 직원", "읽기", "쓰기", "외부전송·실행", "공개", "내부", "중요"]) assert.ok(!HANGUL.test(translator.translate(word)), word);
});

test("dictionary entries are well formed", () => {
  for (const [key, value] of Object.entries(EN)) {
    assert.ok(HANGUL.test(key.replace(/^\[\w+\] /, "")) || /^\[/.test(key), `key without Korean: ${key}`);
    assert.ok(!HANGUL.test(value), `value still has Korean: ${key}`);
    const captures = (key.match(/\{n?\}/g) || []).length;
    for (const [, index] of value.matchAll(/\{(\d+)[}?]/g)) assert.ok(Number(index) >= 1 && Number(index) <= captures, `bad capture {${index}} in: ${key}`);
    if (captures) assert.ok(key.replace(/\{n?\}/g, "").replace(/[^가-힣]/g, "").length >= 1, `pattern needs Korean text: ${key}`);
  }
  assert.ok(translator.size > 1000);
});

test("known phrases, patterns, plurals and runtime joins", () => {
  assert.equal(t("대시보드"), "Dashboard");
  assert.equal(t("  차단된 요청 "), "  Blocked requests ");
  assert.equal(t("요청 1건"), "1 request");
  assert.equal(t("요청 3건"), "3 requests");
  assert.equal(t("5분 전"), "5 min ago");
  assert.equal(t("1–50 / 전체 120건"), "1–50 of 120");
  assert.equal(t("읽기 · 내부"), "Read · Internal");
  assert.equal(t("예상 T1 종료"), "Expected T1 Terminated");
  assert.equal(t("T2 부분 종료"), "T2 Partially terminated");
  assert.equal(t("사용자 2명, 엔드포인트 1대"), "2 users, 1 endpoint");
  assert.equal(t("홍길동 · MCP 이용 중지"), "홍길동 · Suspend MCP usage");
  assert.equal(t("유휴 시간이 1분 30초 후 만료됩니다."), "Idle time will expire in 1 min 30 s.");
  assert.equal(t("14시"), "14:00");
  assert.equal(t("Oct 23 14:05까지"), "Until Oct 23 14:05");
  assert.equal(t("관리자, 직원"), "Administrator, Employee");
});

test("chart text is translated through the same dictionary", async () => {
  const { localize } = await import("../gateway/app/agent_static/charts.mjs");
  const option = localize({ legend: { data: ["허용", "차단"] }, series: [{ name: "승인 대기", data: [{ name: "경보", value: 3 }], links: [{ source: "files ·", target: "허용", value: 1 }] }],
    tooltip: { formatter: "{b} · {c}건 ({d}%)" }, xAxis: { data: ["14시", "15시"] }, valueFormatter: () => "kept" });
  assert.deepEqual(option.legend.data, ["Allow", "Block"]);
  assert.equal(option.series[0].name, "Pending approval");
  assert.equal(option.series[0].data[0].name, "Alert");
  assert.equal(option.series[0].links[0].target, "Allow");
  assert.equal(option.tooltip.formatter, "{b} · {c} calls ({d}%)");
  assert.deepEqual(option.xAxis.data, ["14:00", "15:00"]);
  assert.equal(option.valueFormatter(), "kept");
});

test("a sentence from the server is left alone, never half translated", () => {
  const sentence = "알 수 없는 사유로 호출이 거부되었습니다.";
  assert.equal(t(sentence), sentence);
  assert.equal(t("승인 대기 중인 홍길동 요청"), "승인 대기 중인 홍길동 요청");
  assert.equal(t("쓰기 호출 승인"), "쓰기 호출 승인");  // a policy name from the server: known words, still not ours to gloss
});

// A small DOM: enough for the walker (elements, text, attributes, closest, classList).
function parse(markup) {
  const root = element("div", {});
  let node = root;
  for (const token of markup.match(/<[^>]+>|[^<]+/g) || []) {
    if (token.startsWith("</")) node = node.parentNode;
    else if (token.startsWith("<")) {
      const name = /^<(\w+)/.exec(token)[1];
      const attrs = Object.fromEntries([...token.matchAll(/([\w-]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
      const child = element(name, attrs, node);
      node.childNodes.push(child);
      if (!/\/>$/.test(token)) node = child;
    } else node.childNodes.push({ nodeType: 3, data: token, parentNode: node });
  }
  return root;
}
function element(name, attrs, parentNode = null) {
  const el = { nodeType: 1, tagName: name.toUpperCase(), attrs, parentNode, childNodes: [],
    getAttribute: (key) => el.attrs[key] ?? null, setAttribute: (key, value) => { el.attrs[key] = value; },
    classList: { contains: (name) => (el.attrs.class || "").split(" ").includes(name) },
    closest(selector) {
      const test = selector === "#dialog" ? (e) => e.attrs?.id === "dialog" : (e) => selector.startsWith("[data-i18n-ctx]") && e.attrs?.["data-i18n-ctx"] !== undefined;
      for (let e = el; e && e.nodeType === 1; e = e.parentNode) if (test(e)) return e;
      return null;
    } };
  return el;
}
const textOf = (node) => (node.nodeType === 3 ? [node.data.trim()] : node.childNodes.flatMap(textOf)).filter(Boolean);

test("the page walker translates text and attributes, and tells a verb from a status", () => {
  const dom = parse(`<td><span class="chip">승인</span> <button class="btn">승인</button> <button class="tab">기록<span>3</span></button>
    <input placeholder="이름 또는 계정" /><button aria-label="메뉴 접기" title="메뉴 접기">x</button><label>종료<input /></label>
    <pre>차단</pre><span>종료</span><a href="#/x" class="btn">케이스</a><h1 data-i18n-ctx="button">가입 요청</h1>
    <h2>사용자</h2><nav><a data-i18n-ctx="nav" title="승인 대기"><span>승인 대기</span></a></nav><div class="group" data-i18n-ctx="group">운영</div><button class="tab">승인</button></td>`);
  translateTree(dom);
  assert.deepEqual(textOf(dom), ["Approved", "Approve", "Record", "3", "x", "End", "차단", "Terminated", "Case", "Request sign-up", "Users", "Approvals", "Operations", "Approval"]);
  const input = dom.childNodes[0].childNodes.find((n) => n.tagName === "INPUT");
  assert.equal(input.attrs.placeholder, "Name or account");
});

test("a dialog's pre-filled reason is written in English", () => {
  const dom = parse(`<form id="dialog"><input name="reason" value="관리자 수동 중지" /></form><input value="관리자 수동 중지" />`);
  dom.childNodes[0].attrs.id = "dialog";
  translateTree(dom);
  assert.equal(dom.childNodes[0].childNodes[0].attrs.value, "Suspended manually by administrator");
  assert.equal(dom.childNodes[1].attrs.value, "관리자 수동 중지");
});

// English render of real pages: the consent page, which is also tested in Korean.
const source = readFileSync(new URL("consent-per-server-console.test.mjs", import.meta.url), "utf8");
test("the consent page renders in English with no Korean left", async () => {
  const code = readFileSync(new URL("../gateway/app/agent_static/console.js", import.meta.url), "utf8");
  const safeHTML = code.slice(code.indexOf("class Raw {"), code.indexOf("const short = "));
  const panel = code.slice(code.indexOf("const panel = "), code.indexOf("const chartBox = "));
  const route = code.slice(code.indexOf("const CONSENT_STATUS = "), code.indexOf("ROUTES.intake = "));
  assert.ok(source.includes("CONSENT_STATUS"));
  const context = vm.createContext({ ROUTES: {}, badges: {}, api: async () => ({ consents: [
    { id: 1, server_id: "files", tool_name: "read", status: "PENDING", grade: "nonimportant", purpose: "", terms: { destinations: [], inputs: ["path"] } },
    { id: 2, server_id: "files", tool_name: "send", status: "GRANTED", grade: "important", purpose: "", terms: { destinations: ["docs.example.test"] } }] }),
  NONE: "—", DATA_CLASS: { public: "공개", nonimportant: "내부", important: "중요" }, page: (v) => v, head: (v) => v, kpiStrip: (v) => v,
  when: (v) => v || "—", destinationText: (v) => (v || []).join(", ") || "없음", reload() {}, refreshBadges() {}, toast() {} });
  vm.runInContext(`${safeHTML}\n${panel}\nconst chip = (tone, label) => html\`<span class="chip \${tone}">\${label}</span>\`;
    const empty = (label) => html\`<div>\${label}</div>\`;\n${route}`, context);
  const page = await context.ROUTES.consent();
  const markup = page.tabs.map((tab) => `<h2>${tab.label}</h2>${tab.body}`).join("");
  const english = pieces(String(markup)).map((piece) => translator.translate(piece));
  assert.ok(english.includes("Allow all") && english.includes("Reject all"), english.join("|"));
  assert.ok(english.includes("1 request"));
  assert.ok(english.includes("External destinations None · Input path"), english.join("|"));
  assert.deepEqual(english.filter((piece) => HANGUL.test(piece)), []);
  assert.equal(lang(), "en");
});
