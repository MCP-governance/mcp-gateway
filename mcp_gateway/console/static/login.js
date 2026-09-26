// The admin token lives in sessionStorage: it ends with the tab, and it is checked
// against the API before the console opens so a typo is reported here, not later.
const TOKEN_KEY = "mcp-proxy-admin-token";
const THEME_KEY = "mcp-proxy-theme";

try {
  const theme = localStorage.getItem(THEME_KEY);
  if (theme) document.documentElement.dataset.theme = theme;
} catch { /* storage may be blocked; the system theme applies */ }

const form = document.getElementById("login");
const error = document.getElementById("error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  const token = document.getElementById("token").value.trim();
  const response = await fetch("/admin/api/overview?hours=1", { headers: { authorization: `Bearer ${token}` } })
    .catch(() => null);
  if (!response) { error.textContent = "프록시에 연결하지 못했습니다."; return; }
  if (response.status === 401) { error.textContent = "토큰이 맞지 않습니다."; return; }
  if (!response.ok) { error.textContent = `확인하지 못했습니다 (${response.status}).`; return; }
  sessionStorage.setItem(TOKEN_KEY, token);
  location.replace("/console/");
});
