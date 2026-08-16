# Railway deployment — self-contained Dockerfile.
# Railway sets this service's ROOT DIRECTORY to `phoneme_service/`, so the
# build context is THIS folder and paths are relative to it.
FROM python:3.10-slim

WORKDIR /app

# System dependencies: libsndfile1 for audio loading, ffmpeg for librosa
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

# Upgrade pip to avoid dependency resolution issues
RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

ENV PYTHONUTF8=1

# Railway injects PORT; fallback 8001 for local dev
EXPOSE 8001
CMD python -X utf8 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}
