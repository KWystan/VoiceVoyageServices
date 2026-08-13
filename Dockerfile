FROM python:3.10-slim

WORKDIR /app

# System dependencies: libsndfile1 for audio loading, ffmpeg for librosa
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Upgrade pip to avoid dependency resolution issues
RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUTF8=1

# Hugging Face Spaces sets PORT=7860; fallback 8001 for local dev
CMD python -X utf8 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}
