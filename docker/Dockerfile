# Library server only (not the desktop GUI). Ubuntu-friendly Python image.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LASTBOOK_DATA=/data/LastbookData \
    PORT=8890 \
    MODEL_PROXY_PORT=19443 \
    SURVIVAL_MODEL_BASE=http://127.0.0.1:19443 \
    SURVIVAL_REASONING_EFFORT=none

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Same dependency set as the Linux package (keyword search; no onnxruntime).
COPY packaging/linux/requirements_linux.txt /tmp/requirements_linux.txt
RUN pip install --no-cache-dir -r /tmp/requirements_linux.txt

COPY . /app
RUN chmod +x /app/docker/entrypoint.sh

VOLUME ["/data/LastbookData"]
EXPOSE 8890

ENTRYPOINT ["/app/docker/entrypoint.sh"]
