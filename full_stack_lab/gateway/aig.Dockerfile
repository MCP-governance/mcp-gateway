FROM zhuquelab/aig-server@sha256:0c2560d64ee48f3110a035c9ca385668fcb0723592db51a41b89687f1af7810a AS aig-web

FROM zhuquelab/aig-agent@sha256:7699c4004cd04c7b9c95766f07eb28d19b11d8d91ee4a38602acd74872734f7a
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=aig-web /app/ /aig-web/
WORKDIR /gateway
COPY requirements.txt .
RUN python -m venv /opt/gateway-venv \
    && /opt/gateway-venv/bin/pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser \
    && mkdir -p /runtime /reports \
    && chown -R appuser:appuser /gateway /runtime /reports
COPY --chown=appuser:appuser app ./app
COPY --chmod=755 start-with-aig.sh ./start-with-aig.sh
EXPOSE 8080 8088
ENTRYPOINT ["/gateway/start-with-aig.sh"]
