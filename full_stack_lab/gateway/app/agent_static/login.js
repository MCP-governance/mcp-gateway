/* 합성 IdP 로그인. 토큰은 Agent Service가 발급하고 이 화면은 보관만 한다. */

const TOKEN_KEY = "mcp-console-token";

const saved = localStorage.getItem("mcp-console-theme");
if (saved) document.documentElement.dataset.theme = saved;

const pick = document.querySelector("#pick");
const email = document.querySelector("#email");
const password = document.querySelector("#password");
const error = document.querySelector("#gate-error");
const button = document.querySelector("#gate-go");

pick.addEventListener("change", () => { email.value = pick.value; });

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
          : "합성 계정과 비밀번호를 확인해주세요.");
      error.focus();
      return;
    }
    localStorage.setItem(TOKEN_KEY, body.access_token);
    location.href = "/workspace";
  } catch {
    error.textContent = "인증 서비스에 연결할 수 없습니다. 잠시 후 다시 시도하세요.";
    error.focus();
  } finally {
    button.disabled = false;
    button.textContent = "작업 공간 열기 →";
    event.target.setAttribute("aria-busy", "false");
  }
});
