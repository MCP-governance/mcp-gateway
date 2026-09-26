# The employee's company LLM key (a LiteLLM virtual key) under the names each
# harness reads. Base URLs and models live in the managed config files; Gemini CLI
# takes its base URL only from the environment.
export ANTHROPIC_AUTH_TOKEN="${BOB_LLM_KEY:-}"
export GEMINI_API_KEY="${BOB_LLM_KEY:-}"
export GOOGLE_GEMINI_BASE_URL="${GOOGLE_GEMINI_BASE_URL:-http://llm-gateway:4000}"

# Codex, Gemini CLI and OpenCode read the MCP bearer token from the environment once
# per run; a fresh one each time the person starts them (Claude Code asks bob-sso itself
# through headersHelper).
codex()    { BOB_SSO_TOKEN="$(bob-sso token)" command codex "$@"; }
gemini()   { BOB_SSO_TOKEN="$(bob-sso token)" command gemini "$@"; }
opencode() { BOB_SSO_TOKEN="$(bob-sso token)" command opencode "$@"; }
