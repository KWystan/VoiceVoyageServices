FROM python:3.10-slim

ARG HF_TOKEN=""
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PORT=8000 \
    HF_TOKEN=${HF_TOKEN}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download and cache Wav2Vec2 weights during image build for zero runtime delay
RUN python -c "from transformers import Wav2Vec2ForCTC, Wav2Vec2FeatureExtractor, Wav2Vec2PhonemeCTCTokenizer; m='facebook/wav2vec2-lv-60-espeak-cv-ft'; Wav2Vec2FeatureExtractor.from_pretrained(m); Wav2Vec2PhonemeCTCTokenizer.from_pretrained(m, do_phonemize=False); Wav2Vec2ForCTC.from_pretrained(m)"

COPY . .

EXPOSE 8000

CMD ["python", "-X", "utf8", "app.py"]

