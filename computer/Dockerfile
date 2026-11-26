# Owner-only Nexora virtual computer — Render free web service (512 MB, no card).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXORA_VBOX_LOCAL=1 \
    NEXORA_VBOX_DIR=/tmp/nexora-vbox \
    NEXORA_VBOX_LOWMEM=1 \
    CHROME_BIN=/usr/bin/chromium \
    PORT=10000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        fonts-liberation \
        fonts-noto-core \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 app

WORKDIR /app
COPY computer/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY sglbot/__init__.py /app/sglbot/__init__.py
COPY sglbot/vbox.py /app/sglbot/vbox.py
COPY computer/server.py /app/server.py

RUN mkdir -p /tmp/nexora-vbox/workspace /tmp/nexora-vbox/tmp \
    && chown -R app:app /app /tmp/nexora-vbox

USER app
EXPOSE 10000
CMD ["python", "/app/server.py"]
