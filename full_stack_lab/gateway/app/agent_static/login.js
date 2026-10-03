/* 합성 IdP 로그인. 토큰은 Agent Service가 발급하고 이 화면은 보관만 한다. */

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
      document.querySelector("#sso-login a").hidden = !config.configured;
      document.querySelector("#sso-label").textContent = `${config.label} 계정으로 로그인합니다.`;
      document.querySelector("#sso-error").textContent = {unbound: "조직 사용자와 연결되지 않은 SSO 계정입니다. 관리자에게 신원 연결을 요청하세요.",
        invalid: "SSO 인증을 확인하지 못했습니다. 다시 로그인하세요."}[params.get("sso_error")] || (!config.configured ? "조직 SSO 설정이 완료되지 않았습니다." : "");
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
// The Console sends a session here when an admin switched the account off.
error.textContent = { disabled: "사용이 중지된 계정이에요. 관리자에게 문의하세요.",
  locked: "잠긴 계정이에요. 관리자에게 문의하세요.", deleted: "삭제된 계정이에요." }[new URLSearchParams(location.search).get("account")] || "";

document.querySelector("#gate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled || !event.target.reportValidity()) return;
  error.textContent = "";
  button.disabled = true;
  button.textContent = "로그인 확인 중…";
  event.target.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/auth/mock-login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: email.value.trim(), password: password.value }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || !body.access_token) {
      // 계정 상태(403)와 비밀번호 오류(401)를 한 문장으로 접지 않는다. 계정을 끈
      // 관리자조차 자기 조치가 먹혔는지 알 수 없게 된다.
      error.textContent = body.detail
        || (response.status === 429 ? "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
          : "아이디와 비밀번호를 확인해주세요.");
      error.focus();
      return;
    }
    localStorage.setItem(TOKEN_KEY, body.access_token);
    // 내부 Git에서 로그인하러 온 경우만 그리로 돌려보낸다. 다른 주소로 보내는 열린 리다이렉트를 만들지 않는다.
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
