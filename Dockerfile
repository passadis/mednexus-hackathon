# ── Python API ───────────────────────────────────────────────
FROM python:3.11-slim AS api

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY pyproject.toml .

# Install mednexus package so "import mednexus" works
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000
CMD ["uvicorn", "mednexus.api.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ── React UI (build stage) ──────────────────────────────────
FROM node:22-alpine AS ui-build

WORKDIR /app
COPY ui/package.json ui/package-lock.json* ./
RUN npm install

COPY ui/ .
RUN npm run build


# ── Combined production image ────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend
COPY src/ src/
COPY pyproject.toml .

# Install mednexus package so "import mednexus" works
RUN pip install --no-cache-dir --no-deps .

# Frontend assets (served by FastAPI static files in production)
COPY --from=ui-build /app/dist static/

# Data folders
RUN mkdir -p data/intake

EXPOSE 8000
ENV MEDNEXUS_LOG_LEVEL=INFO
CMD ["uvicorn", "mednexus.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--timeout-graceful-shutdown", "30"]
