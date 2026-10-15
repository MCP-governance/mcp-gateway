# Built by the runtime worker from the approved commit of the internal mirror. The base is pinned by digest.
FROM python:3.13-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
ENV DEBIAN_FRONTEND=noninteractive EXIFTOOL_PATH=/usr/bin/exiftool FFMPEG_PATH=/usr/bin/ffmpeg \
    ORT_DISABLE_TELEMETRY=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*
COPY . /src
RUN pip install --no-cache-dir "/src/packages/markitdown[all]" /src/packages/markitdown-mcp && rm -rf /src
WORKDIR /tmp
USER 65534:65534
ENTRYPOINT ["markitdown-mcp"]
