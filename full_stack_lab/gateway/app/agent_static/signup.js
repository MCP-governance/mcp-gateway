document.documentElement.dataset.theme = localStorage.getItem("mcp-console-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
const form = document.querySelector("#signup-form");
const message = document.querySelector("#signup-message");
const invitation = new URLSearchParams(location.hash.slice(1));
const invitationToken = invitation.get("invite") || "";
if (invitationToken) {
  form.elements.username.value = invitation.get("username") || "";
  form.elements.username.readOnly = true;
  document.querySelector(".brand b").textContent = "조직 초대 수락";
  document.querySelector(".gate-heading h2").textContent = "조직 초대 수락";
  document.querySelector(".gate-heading p").textContent = "이름과 비밀번호를 설정한 뒤 관리형 단말을 연결하세요.";
  document.querySelector(".brand span").textContent = "이름과 비밀번호를 설정하면 일반 사용자로 등록됩니다.";
  form.querySelector("button").textContent = "등록 완료";
  history.replaceState(null, "", "/signup");
}
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form));
    if (invitationToken) body.invitation_token = invitationToken;
    const response = await fetch("/auth/signup", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const result = await response.json();
    message.textContent = response.ok ? result.message : result.detail || "가입 신청에 실패했습니다.";
    if (response.ok) {
      form.reset();
      if (invitationToken) {
        form.querySelectorAll("label,button").forEach((element) => { element.hidden = true; });
      }
    }
    message.focus();
  } catch {
    message.textContent = "인증 서비스에 연결할 수 없습니다.";
    message.focus();
  } finally {
    button.disabled = false;
  }
});
