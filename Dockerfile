# ══════════════════════════════════════════════════════════════
# Surveillance-IA Dockerfile
# Multi-stage build for production deployment
# ══════════════════════════════════════════════════════════════

# ── Stage 1: Base ────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies for OpenCV + libGL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 2: Dependencies ───────────────────────────────────
FROM base AS dependencies

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: Surveillance API (FastAPI + WebSockets) ─────────
FROM dependencies AS surv-api

COPY src/ ./src/
COPY api/ ./api/
COPY database/ ./database/

RUN mkdir -p data/splits models/finetuned reports

EXPOSE 8000

ENV MODEL_PATH="models/finetuned/best.pt" \
    DATABASE_URL="postgresql://surv_user:surv_pass@surv-db:5432/surveillance_db" \
    SECRET_KEY="surveillance-ia-secret-key-change-me"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Stage 4: Surveillance Dashboard (Streamlit) ─────────
FROM dependencies AS surv-dashboard

COPY src/ ./src/
COPY app/ ./app/

EXPOSE 8501

ENV API_URL="http://surv-api:8000"

CMD ["streamlit", "run", "app/dashboard.py", "--server.port", "8501", "--server.address", "0.0.0.0"]

# ── Stage 5: Surveillance GPU (CUDA + YOLO v8) ──────────────
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS surv-gpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip python3.12-venv \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.12 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY api/ ./api/
COPY database/ ./database/

RUN mkdir -p data/splits models/finetuned reports

EXPOSE 8000

ENV MODEL_PATH="models/finetuned/best.pt" \
    DATABASE_URL="postgresql://surv_user:surv_pass@surv-db:5432/surveillance_db" \
    SECRET_KEY="surveillance-ia-secret-key-change-me" \
    DEVICE="cuda"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
