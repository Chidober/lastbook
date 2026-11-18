# Library server only (not the desktop GUI). Ubuntu-friendly Python image.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LASTBOOK_DATA=/data/LastbookData \
    PORT=8890 \
    MODEL_PROXY_PORT=19443 \
    SURVIVAL_MODEL_BASE=http://127.0.0.1:19443 \
    SURVIVAL_REASONING_EFFORT=none

# libzim wheel needs ICU/xz/zstd at runtime; ca-certificates for setup downloads.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      libglib2.0-0 \
      libicu72 \
      libzstd1 \
      liblzma5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY packaging/linux/requirements_linux.txt /tmp/requirements_linux.txt
RUN pip install --no-cache-dir -r /tmp/requirements_linux.txt

COPY . /app
RUN chmod +x /app/docker/entrypoint.sh \
 && python3 -c "import libzim, numpy, bs4, pypdfium2; print('deps ok')"

# Do not VOLUME /data/LastbookData. Setup renames that directory after unpacking
# LastbookData.setup. A volume mount point cannot be renamed, so the switch fails
# and the host folder stays the empty stub.
EXPOSE 8890

ENTRYPOINT ["/app/docker/entrypoint.sh"]
