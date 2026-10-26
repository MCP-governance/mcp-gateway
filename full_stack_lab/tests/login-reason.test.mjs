import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gateway/app/agent_static/login.js", import.meta.url), "utf8").replace(/^import .*$/m, "");

function shown(search) {
  const error = { textContent: "" };
  const element = { hidden: false, addEventListener() {}, dataset: {}, querySelector() { return element; }, textContent: "" };
  const context = vm.createContext({
    URLSearchParams, localStorage: { getItem: () => "light" }, matchMedia: () => ({ matches: false }),
    location: { search }, fetch: () => new Promise(() => {}),
    document: { documentElement: { dataset: {} }, querySelector: (selector) => (selector === "#gate-error" ? error : element) },
  });
  vm.runInContext(source, context);
  return error.textContent;
}

test("세션 종료 사유를 한국어 한 줄로 보인다", () => {
  assert.equal(shown("?session=idle"), "오래 사용하지 않아 로그아웃되었습니다.");
  assert.equal(shown("?session=maximum"), "로그인 유지 시간이 지나 로그아웃되었습니다.");
  assert.equal(shown("?session=authentication"), "로그인이 만료되었습니다.");
});

test("계정 상태가 먼저고 알 수 없는 값은 무시한다", () => {
  assert.match(shown("?account=deleted&session=idle"), /삭제된 계정/);
  for (const search of ["", "?session=x", "?session=toString", "?account=constructor"]) assert.equal(shown(search), "", search);
});
