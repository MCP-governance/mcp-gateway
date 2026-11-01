import "./i18n.mjs";

const TOKEN_KEY = "mcp-console-token";

document.documentElement.dataset.theme = localStorage.getItem("mcp-console-theme")
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

const email = document.querySelector("#email");
const password = document.querySelector("#password");
const error = document.querySelector("#gate-error");
const button = document.querySelector("#gate-go");
const params = new URLSearchParams(location.search);
async function configureLogin() {
  try {
    const config = await (await fetch("/auth/provider")).json();
    if (config.provider === "oidc") {
      document.querySelector("#sso-login").hidden = false;
      document.querySelector("#sso-button").hidden = !config.configured;
      if (config.label) document.querySelector("#sso-button").textContent = `${config.label} 로그인`;
      document.querySelector("#sso-error").textContent = {unbound: "연결되지 않은 SSO 계정입니다. 관리자에게 문의하세요.",
        invalid: "SSO 인증에 실패했습니다. 다시 로그인하세요.",
        refresh_unavailable: "인증 제공자가 세션 갱신을 지원하지 않아 로그인할 수 없습니다."}[params.get("sso_error")] || (!config.configured ? "SSO 설정이 완료되지 않았습니다." : "");
    } else document.querySelector("#gate-form").hidden = false;
    if (params.get("sso") === "complete") {
      const response = await fetch("/auth/oidc/session", {method: "POST"});
      const result = await response.json();
      if (!response.ok || !result.access_token) throw Error("SSO 인증을 완료하지 못했습니다. 다시 로그인하세요.");
      localStorage.setItem(TOKEN_KEY, result.access_token);
      location.replace("/workspace");
    }
  } catch (failure) {
    document.querySelector("#sso-login").hidden = false;
    document.querySelector("#sso-error").textContent = failure.message || "로그인 방식을 확인하지 못했습니다.";
  }
}
configureLogin();
const REASON = { account: { disabled: "사용이 중지된 계정입니다. 관리자에게 문의하세요.",
  locked: "잠긴 계정입니다. 관리자에게 문의하세요.", deleted: "삭제된 계정입니다. 관리자에게 복구를 요청하세요." },
session: { idle: "오래 사용하지 않아 로그아웃되었습니다.", maximum: "로그인 유지 시간이 지나 로그아웃되었습니다.",
  authentication: "로그인이 만료되었습니다." } };
error.textContent = Object.entries(REASON).map(([key, texts]) => Object.hasOwn(texts, params.get(key)) ? texts[params.get(key)] : "").find(Boolean) || "";

document.querySelector("#gate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled || !event.target.reportValidity()) return;
  error.textContent = "";
  button.disabled = true;
  button.textContent = "확인 중…";
  event.target.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/auth/mock-login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: email.value.trim(), password: password.value }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || !body.access_token) {
      error.textContent = body.detail
        || (response.status === 429 ? "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
          : "아이디와 비밀번호를 확인하세요.");
      error.focus();
      return;
    }
    localStorage.setItem(TOKEN_KEY, body.access_token);
    const next = new URLSearchParams(location.search).get("next") || "";
    location.href = /^\/git\/[^/\\]/.test(next) || next === "/git/" ? next : "/workspace";
  } catch {
    error.textContent = "인증 서비스에 연결할 수 없습니다. 잠시 후 다시 시도하세요.";
    error.focus();
  } finally {
    button.disabled = false;
    button.textContent = "로그인";
    event.target.setAttribute("aria-busy", "false");
  }
});
