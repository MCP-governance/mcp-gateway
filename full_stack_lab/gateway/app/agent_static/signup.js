const form = document.querySelector("#signup-form");
const message = document.querySelector("#signup-message");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form));
    const response = await fetch("/auth/signup", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const result = await response.json();
    message.textContent = response.ok ? result.message : result.detail || "가입 신청에 실패했습니다.";
    if (response.ok) form.reset();
    message.focus();
  } catch {
    message.textContent = "인증 서비스에 연결할 수 없습니다.";
    message.focus();
  } finally {
    button.disabled = false;
  }
});
