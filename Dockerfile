# ---- Node build stage ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# ---- Python base stage ----
FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    docker.io-cli \
    && rm -rf /var/lib/apt/lists/*

# ---- Python build stage ----
FROM base AS builder
WORKDIR /app
COPY pyproject.toml README.md ./
COPY codepulse/ ./codepulse/
RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir -e .

# ---- Final stage ----
FROM base
WORKDIR /app

# Copy codepulse package
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/codepulse /usr/local/bin/codepulse
COPY codepulse.yaml.example /app/codepulse.yaml.example

# Copy built frontend
COPY --from=frontend-builder /app/web/dist /app/web/dist

# Default entry point
ENTRYPOINT ["codepulse"]
CMD ["--help"]
