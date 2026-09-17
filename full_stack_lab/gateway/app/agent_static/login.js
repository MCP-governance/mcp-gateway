// 콘솔에서 고른 테마가 로그인 화면에도 이어져야 한다. 로그인할 때만 밝아지면
// 매번 눈이 한 번 튄다.
try {
  const stored = localStorage.getItem("bob_console_theme");
  if (stored === "light" || stored === "dark") document.documentElement.dataset.theme = stored;
} catch { /* 저장소를 못 읽어도 시스템 설정으로 동작한다 */ }

const TOKEN_KEY = "bob_mock_sso_token";

const form = document.querySelector("#login-form");
const emailInput = document.querySelector("#email");
const passwordInput = document.querySelector("#password");
const loginButton = document.querySelector("#login-button");
const errorMessage = document.querySelector("#login-error");
const togglePassword = document.querySelector("#toggle-password");
document.querySelector("#access-role").addEventListener("change", event => { emailInput.value = event.target.value; });

if (sessionStorage.getItem(TOKEN_KEY)) {
  window.location.replace("/workspace");
}

togglePassword.addEventListener("click", () => {
  const showing = passwordInput.type === "text";
  passwordInput.type = showing ? "password" : "text";
  togglePassword.textContent = showing ? "표시" : "숨김";
  togglePassword.setAttribute(
    "aria-label",
    showing ? "비밀번호 표시" : "비밀번호 숨김",
  );
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.textContent = "";

  if (!emailInput.value.trim() || !passwordInput.value) {
    errorMessage.textContent = "회사 이메일과 비밀번호를 입력해주세요.";
    return;
  }

  loginButton.disabled = true;
  loginButton.textContent = "인증 확인 중";

  try {
    const response = await fetch("/auth/mock-login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: emailInput.value.trim(),
        password: passwordInput.value,
      }),
    });

    const body = await response.json();

    if (!response.ok) {
      // 422의 detail은 객체 배열이다. 그대로 넣으면 [object Object]가 보인다.
      const detail = Array.isArray(body.detail)
        ? body.detail.map(item => item.msg).join(" / ")
        : body.detail;
      throw new Error(detail || "로그인에 실패했습니다.");
    }

    sessionStorage.setItem(TOKEN_KEY, body.access_token);
    window.location.assign("/workspace");
  } catch (error) {
    errorMessage.textContent = error.message;
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "계속";
  }
});
