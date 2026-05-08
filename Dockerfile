# =============================================================================
# PolicyChecker — Dockerfile
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart python-dotenv

# Copy application code
COPY . .

# Seed the database on startup (idempotent), then run the web app
CMD ["sh", "-c", "python -m db.seed && python web/app.py"]
