/* 합성 IdP 로그인. 토큰은 Agent Service가 발급하고 이 화면은 보관만 한다. */

const TOKEN_KEY = "mcp-console-token";

document.documentElement.dataset.theme = localStorage.getItem("mcp-console-theme")
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

const email = document.querySelector("#email");
const password = document.querySelector("#password");
const error = document.querySelector("#gate-error");
const button = document.querySelector("#gate-go");
// The Console sends a session here when an admin switched the account off.
error.textContent = { disabled: "사용이 중지된 계정이에요. 관리자에게 문의하세요.",
  locked: "잠긴 계정이에요. 관리자에게 문의하세요." }[new URLSearchParams(location.search).get("account")] || "";

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
