# The employee's company LLM key (a LiteLLM virtual key) under the names each
# harness reads. Base URLs and models live in the managed config files; Gemini CLI
# takes its base URL only from the environment.
export ANTHROPIC_AUTH_TOKEN="${BOB_LLM_KEY:-}"
export GEMINI_API_KEY="${BOB_LLM_KEY:-}"
export GOOGLE_GEMINI_BASE_URL="${GOOGLE_GEMINI_BASE_URL:-http://llm-gateway:4000}"
