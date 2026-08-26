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

COPY . .

EXPOSE 8000

CMD ["python", "-X", "utf8", "app.py"]


