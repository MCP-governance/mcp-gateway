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
  loginButton.firstElementChild.textContent = "인증 확인 중";

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
      throw new Error(body.detail || "로그인에 실패했습니다.");
    }

    sessionStorage.setItem(TOKEN_KEY, body.access_token);
    window.location.assign("/workspace");
  } catch (error) {
    errorMessage.textContent = error.message;
  } finally {
    loginButton.disabled = false;
    loginButton.firstElementChild.textContent = "계속";
  }
});
