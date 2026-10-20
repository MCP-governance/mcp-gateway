# 하네스 시험용 클라이언트: 직원 PC의 Claude Code·Codex와 같은 판본(PJ1 실측 2.1.288 / 0.160.0)을 공식 npm 패키지 그대로 쓴다.
# 관리형 설정이 없는 격리 컨테이너이며 LiteLLM 가상 키와 기본 URL만 환경으로 받는다.
FROM node:22-bookworm-slim
RUN npm install -g --no-fund --no-audit --omit=dev @anthropic-ai/claude-code@2.1.288 @openai/codex@0.160.0 \
 && npm cache clean --force
RUN useradd --uid 10030 --create-home agent
USER agent
WORKDIR /home/agent
ENV DISABLE_AUTOUPDATER=1 DISABLE_TELEMETRY=1 DISABLE_ERROR_REPORTING=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
