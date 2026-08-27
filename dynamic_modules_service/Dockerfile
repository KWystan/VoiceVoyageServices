# dynamic_modules_service — isolated Railway deployment (port 8002 / ${PORT})
# Build context MUST be this folder (Railway: Settings → Root Directory = dynamic_modules_service)
# If building from repo root: docker build -f dynamic_modules_service/Dockerfile -t modules VoiceVoyageServices/
# Local standalone: docker build -t modules dynamic_modules_service/ && docker run -p 8002:8002 -e ZEN_API_KEY=... modules
# Legacy root-context build (Azure/HF) still works if you pass repo root as context.

FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPYCACHEPREFIX=/app/.cache/pycache

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# App code (respect .dockerignore)
COPY . .

RUN useradd -m app && chown -R app:app /app && \
    mkdir -p /app/.cache/pycache && chown -R app:app /app/.cache
USER app

# Railway injects PORT=8080; fallback 8002 for local `docker run`
EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8002')+'/health', timeout=5)"

CMD ["sh", "-c", "python -X utf8 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8002}"]
