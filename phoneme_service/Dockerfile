# phoneme_service — isolated Railway deployment (port 8001 / ${PORT})
# Build context MUST be this folder (Railway: Settings → Root Directory = phoneme_service)
# If building from repo root: docker build -f phoneme_service/Dockerfile -t phoneme VoiceVoyageServices/

FROM python:3.10-slim

# Dedicated phoneme env vars — set in Railway Dashboard → Variables (not baked)
# HF_TOKEN: Hugging Face read token (high rate-limits, required for reliable 1.4GB download) — MUST be runtime Variable, not ARG/ENV bake (hadolint SecretsUsedInArgOrEnv)
# VV_FP16: 1 = float16 ~600MB peak (free tier), 0 = float32 + INT8 ~1.2GB peak
# PHONEME_PRELOAD: 1 = background Wav2Vec2 preload (fast first request), 0 = lazy (saves RAM idle)
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch \
    PYTHONPYCACHEPREFIX=/app/.cache/pycache \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    TRANSFORMERS_VERBOSITY=error \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    VV_FP16=0 \
    PHONEME_PRELOAD=1

WORKDIR /app

# System deps: ffmpeg (librosa/soundfile), libsndfile1 (soundfile), git (hf_hub)
# git is kept for hf_transfer but `fatal: not a git repository` warning is silenced via ENV above
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/.cache/huggingface /app/.cache/torch /app/.cache/pycache \
    && git config --global --add safe.directory /app

# Python deps — CPU-only torch to cut image ~2 GB vs CUDA
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt

# App code (respect .dockerignore)
COPY . .

# Non-root (Railway runs as root by default, but good practice)
RUN useradd -m app && chown -R app:app /app
USER app

# Railway injects PORT=8080; Azure injects WEBSITES_PORT=8001; fallback 8001 for local `docker run`
EXPOSE 8001

# Health probe — start-period 120s tolerates cold Wav2Vec2 download + INT8 quant
# Azure App Service ignores Docker HEALTHCHECK (uses its own Health check blade), but keep for local/Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT', os.environ.get('WEBSITES_PORT','8001'))+'/health', timeout=5)"

# Exec-form via shell to expand ${PORT} while preserving SIGTERM; handles both Railway (PORT) and Azure (WEBSITES_PORT)
CMD ["sh", "-c", "python -X utf8 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-${WEBSITES_PORT:-8001}}"]
