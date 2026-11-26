# Nexora AI web app — works on Render (free web service), Hugging Face Spaces, Fly, any Docker host.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860 DATA_DIR=/app/data
RUN useradd -m -u 1000 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app sglbot ./sglbot
COPY --chown=app:app static ./static
COPY --chown=app:app server.py .
RUN mkdir -p /app/data/media && chown -R app:app /app/data
USER app
EXPOSE 7860
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
