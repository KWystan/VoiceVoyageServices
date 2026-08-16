# Railway deployment — self-contained Dockerfile.
# Railway sets this service's ROOT DIRECTORY to `dynamic_modules_service/`, so
# the build context is THIS folder and paths are relative to it.
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/

ENV PYTHONUTF8=1

# Railway injects PORT; fallback 8002 for local dev.
# ZEN_API_KEY is provided by Railway variables — never baked into the image.
EXPOSE 8002
CMD python -X utf8 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8002}
