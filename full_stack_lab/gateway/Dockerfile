FROM zricethezav/gitleaks:v8.30.1 AS secrets
# Native engines are compiled here; the runtime image gets only the shared objects.
FROM golang:1.24.13-bookworm AS native-go
WORKDIR /src/gitleaks
COPY native/gitleaks/ ./
RUN CGO_ENABLED=1 go build -trimpath -buildmode=c-shared -o /out/libmcpgw_gitleaks.so .
FROM python:3.12-slim AS native-c
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*
COPY native/textscan/textscan.c /src/
# PCRE2 is linked statically, so the runtime image needs no extra package.
RUN mkdir /out && gcc -O2 -fPIC -shared -Wall -Wextra -Werror -Wno-unused-parameter -Wno-missing-field-initializers \
      $(python3-config --includes) /src/textscan.c -o /out/mcpgw_textscan$(python3-config --extension-suffix) \
      -Wl,-Bstatic -lpcre2-32 -Wl,-Bdynamic
FROM python:3.12-slim
COPY windows-python.json prepare-windows-python.py /tmp/windows-python/
RUN python /tmp/windows-python/prepare-windows-python.py /tmp/windows-python/windows-python.json /opt/windows-python \
    && rm -r /tmp/windows-python
COPY --from=secrets /usr/bin/gitleaks /usr/local/bin/gitleaks
COPY --from=native-go /out/libmcpgw_gitleaks.so /usr/local/lib/
COPY --from=native-c /out/ /usr/local/lib/python3.12/site-packages/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home appuser \
    && mkdir -p /runtime /reports /registry-runtime /disposal \
    && chown -R appuser:appuser /app /runtime /reports /registry-runtime /disposal
COPY --chown=appuser:appuser app ./app
ARG MCP_BUILD_REVISION=unknown
ENV MCP_BUILD_REVISION=$MCP_BUILD_REVISION
LABEL org.opencontainers.image.revision=$MCP_BUILD_REVISION
USER appuser
EXPOSE 8080 8081
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
