# An employee workstation: the AI assistant (office-agent) and the endpoint agent.
# It sits on the internal `office` network, so the only MCP endpoint it can reach
# is the Gateway, and the only model endpoint is LiteLLM.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 procps \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir mcp==2.2.0 httpx==0.28.1 httpx2==2.12.0
COPY workstation/office_agent.py workstation/provision_keys.py /opt/office/
COPY workstation/scenarios /opt/office/scenarios
COPY workstation/configs /opt/office/configs
COPY --from=endpoint agent.py /opt/office/endpoint_agent.py
COPY --chmod=0755 workstation/entrypoint.sh /usr/local/bin/workstation-entrypoint
RUN printf '#!/bin/sh\nexec python /opt/office/office_agent.py "$@"\n' > /usr/local/bin/office-agent \
 && chmod 0755 /usr/local/bin/office-agent \
 && useradd --uid 10020 --create-home --shell /bin/bash agent
USER agent
WORKDIR /home/agent
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/local/bin/workstation-entrypoint"]
