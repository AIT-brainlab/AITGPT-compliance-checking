# =============================================================================
# PolicyChecker — Dockerfile (multi-stage: React build + Python API)
# =============================================================================

# ── Stage 1: Build React frontend ─────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci --silent
COPY web/frontend/ ./
RUN npm run build

# ── Stage 2: Python API server ────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy React build into frontend/dist (where app.py expects it)
COPY --from=frontend-build /build/dist /app/web/frontend/dist

# Seed the database on startup (idempotent), then run the web app
CMD ["sh", "-c", "python -m db.seed && python web/app.py"]
