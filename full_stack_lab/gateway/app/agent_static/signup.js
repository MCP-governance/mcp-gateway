document.documentElement.dataset.theme = localStorage.getItem("mcp-console-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
const form = document.querySelector("#signup-form");
const message = document.querySelector("#signup-message");
const invitation = new URLSearchParams(location.hash.slice(1));
const invitationToken = invitation.get("invite") || "";
if (invitationToken) {
  form.elements.username.value = invitation.get("username") || "";
  form.elements.username.readOnly = true;
  document.querySelector("#signup-title").textContent = "초대 수락";
  document.title = "초대 수락 · MCP Governance";
  form.querySelector("button").textContent = "등록";
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
    message.textContent = response.ok ? result.message : result.detail || "가입 요청에 실패했습니다.";
    message.classList.toggle("ok", response.ok);
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
