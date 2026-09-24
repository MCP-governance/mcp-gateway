/* 합성 IdP 로그인. 토큰은 Agent Service가 발급하고 이 화면은 보관만 한다. */

const TOKEN_KEY = "mcp-console-token";

document.documentElement.dataset.theme = localStorage.getItem("mcp-console-theme")
  || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

const pick = document.querySelector("#pick");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const error = document.querySelector("#gate-error");
const button = document.querySelector("#gate-go");

pick.addEventListener("change", () => { email.value = pick.value; });

document.querySelector("#gate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  button.disabled = true;
  try {
    const response = await fetch("/auth/mock-login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: email.value.trim(), password: password.value }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      // 계정 상태(403)와 비밀번호 오류(401)를 한 문장으로 접지 않는다. 계정을 끈
      // 관리자조차 자기 조치가 먹혔는지 알 수 없게 된다.
      error.textContent = body.detail
        || (response.status === 429 ? "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
          : "합성 계정과 비밀번호를 확인해주세요.");
      return;
    }
    localStorage.setItem(TOKEN_KEY, body.access_token);
    location.href = "/workspace";
  } catch {
    error.textContent = "인증 서비스에 연결할 수 없습니다.";
  } finally {
    button.disabled = false;
  }
});
