# Builds from the REPO ROOT (Azure Container Apps GitHub build context).
# Local: docker compose up --build (contexts point at the repo root).
FROM python:3.10-slim

WORKDIR /app

COPY dynamic_modules_service/requirements.txt /app/requirements.txt

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY dynamic_modules_service/ /app/

ENV PYTHONUTF8=1

# Hugging Face Spaces / Azure Container Apps set PORT; fallback 8002 for local dev
EXPOSE 8002
CMD python -X utf8 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8002}
