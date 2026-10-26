import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const STATIC = new URL("../gateway/app/agent_static/", import.meta.url);
const source = readFileSync(new URL("console.js", STATIC), "utf8");
const css = readFileSync(new URL("console.css", STATIC), "utf8");
const safeHTML = source.slice(source.indexOf("class Raw {"), source.indexOf("const short = "));
const kitSource = source.slice(source.indexOf("const PLATFORM_KIT ="), source.indexOf("const EXIT_TERMS = {"));
const toolSource = source.slice(source.indexOf("function requestedToolList("), source.indexOf("// ── intake ──"));

function sandbox(platform) {
  const context = vm.createContext({ navigator: { platform }, URL });
  vm.runInContext(`${safeHTML}
    const chip = (tone, label) => html\`<span class="chip">\${label}</span>\`;
    const kv = (pairs) => html\`<dl>\${pairs.map(([k, v]) => html\`<dt>\${k}</dt><dd>\${v}</dd>\`)}</dl>\`;
    ${kitSource}
    ${toolSource}
    globalThis.kit = (os) => String(kitView({ platforms: ["linux", "macos", "windows"], servers: "git,docs" }, os));
    globalThis.preferred = preferredKitPlatform;
    globalThis.tools = (list) => String(requestedToolList(list));`, context);
  return context;
}

test("도구 불러오기: 체크박스와 도구 이름·설명이 한 행에서 구분되고 값은 이스케이프된다", () => {
  const out = sandbox("Linux x86_64").tools([
    { name: "ask_wiki_question", description: "Ask a question about a repository" },
    { name: "read_wiki_contents", description: "<img src=x onerror=1>" },
    { name: "read_wiki_structure", description: "" }]);
  assert.equal((out.match(/type="checkbox" name="requested_tool"/g) || []).length, 3);
  assert.match(out, /<b class="mono">ask_wiki_question<\/b><span class="sub">Ask a question/);
  assert.ok(out.includes("&lt;img"));
  assert.ok(!out.includes("<img"));
  assert.ok(!/read_wiki_structure<\/b><span class="sub">/.test(out), "빈 설명은 칸을 만들지 않는다");
});

test("체크박스에는 입력칸용 전체 너비·높이 규칙이 걸리지 않고 목록 행은 보통 크기다", () => {
  for (const rule of css.match(/\.form input[^{]*\{[^}]*\}/g)) {
    if (/width:100%/.test(rule)) assert.match(rule, /not\(\[type="checkbox"\]\)/, rule);
  }
  assert.match(css, /\.tool-list input\[type="checkbox"\]\{[^}]*width:16px;height:16px/);
  assert.match(css, /\.tool-list \.sub\{[^}]*color:var\(--ink-3\)/);
});

test("내 PC 연결: 운영체제 버튼은 선택만 하고 받기는 별도 버튼 하나다", () => {
  const context = sandbox("Linux x86_64");
  for (const os of ["linux", "macos", "windows"]) {
    const out = context.kit(os);
    assert.equal((out.match(/data-act="pc-kit-os"/g) || []).length, 3);
    assert.equal((out.match(/data-act="pc-kit-download"/g) || []).length, 1);
    assert.match(out, new RegExp(`data-act="pc-kit-download" data-os="${os}">설치 파일 받기`));
    assert.match(out, new RegExp(`class="btn sm primary" type="button" aria-pressed="true" data-act="pc-kit-os" data-os="${os}"`));
    assert.equal((out.match(/aria-pressed="true"/g) || []).length, 1);
  }
});

test("내 PC 연결: 선택한 운영체제의 절차만 보인다", () => {
  const context = sandbox("Linux x86_64");
  const linux = context.kit("linux");
  assert.ok(linux.includes("unzip ~/Downloads/mcp-managed-kit-linux.zip -d ~/mcp-managed-kit && ~/mcp-managed-kit/install.sh"));
  assert.ok(linux.includes("sudo ~/mcp-managed-kit/install.sh --remove"));
  assert.ok(!linux.includes("mint-"));
  assert.ok(!linux.includes("mcp-connect-macos") && !linux.includes(".cmd"));
  const mac = context.kit("macos");
  assert.ok(mac.includes("mcp-connect-macos.command") && !mac.includes("sudo"));
  const windows = context.kit("windows");
  assert.ok(windows.includes(".cmd") && !windows.includes("sudo") && !windows.includes("mcp-connect-macos"));
});

test("내 PC 연결: 기본 선택은 Windows(주 대상)", () => {
  for (const platform of ["MacIntel", "Win32", "Linux x86_64"]) assert.equal(sandbox(platform).preferred(), "windows");
  const out = sandbox("Linux x86_64").kit("windows");
  assert.ok(out.indexOf('data-os="windows"') < out.indexOf('data-os="linux"'), "Windows 버튼이 맨 앞");
});

test("내 PC 연결: 자동 활성화면 바로 사용, 끄면 관리자 활성화, 격리 계정은 고급 선택", () => {
  const context = sandbox("Win32");
  context.kitWith = (kit, os) => String(vm.runInContext("kitView", context)({ platforms: ["windows", "macos", "linux"], servers: "git", ...kit }, os));
  assert.ok(context.kitWith({ auto_activate: true }, "windows").includes("설치가 끝나면 바로 사용"));
  assert.ok(context.kitWith({ auto_activate: false }, "windows").includes("관리자 활성화 뒤 사용"));
  const windows = context.kitWith({}, "windows");
  assert.ok(windows.includes("지금 계정 그대로") && windows.includes('name="kit-isolated"') && windows.includes("고급: 격리 계정"));
  assert.ok(!context.kitWith({}, "macos").includes('name="kit-isolated"'));
});

test("내 PC 연결: 내려받는 파일 이름은 서버가 주는 값을 쓴다", () => {
  const download = source.slice(source.indexOf('  async "pc-kit-download"(el) {'), source.indexOf('  async "device-activate"(el) {'));
  assert.match(download, /form\.submit\(\)/);
  assert.doesNotMatch(download, /\.blob\(|\.download\s*=/);
  const service = readFileSync(new URL("../gateway/app/agent_service.py", import.meta.url), "utf8");
  for (const filename of ["mcp-managed-setup-windows.cmd", "mcp-connect-macos.command", "mcp-managed-kit-{platform}.zip"]) {
    assert.ok(service.includes(`attachment; filename="${filename}"`), filename);
  }
});

test("삭제된 사용자: 목록 탭과 복구 동작이 있다", () => {
  assert.match(source, /api\("\/api\/accounts\/deleted"\)/);
  assert.match(source, /key: "deleted", label: "삭제된 사용자"/);
  assert.match(source, /data-act="account-restore" data-id="\$\{a\.user_id\}"/);
  assert.match(source, /async "account-restore"\(el\)[\s\S]*?\/restore`, \{ method: "POST" \}/);
});
