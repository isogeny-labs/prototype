# Isogeny Evidence Lab as one container, for hosting (21 November 2026). See docs/HOSTING.md.
#   docker compose up --build        (the app with PostgreSQL, Redis and MinIO; docker-compose.yml)
# The app runs in demo mode here: isolated mode starts containers of its own and needs Docker on the host.

# 1. The web pages.
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. The app.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# git: Connect demo code copies the bundled demo repository; openssl: the demo test certificate.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssl ca-certificates \
    && apt-get clean
RUN useradd --create-home --uid 10001 lab
WORKDIR /app
COPY backend/requirements.lock backend/requirements-infra.lock backend/
RUN python -m pip install --require-hashes -r backend/requirements.lock \
    && python -m pip install --require-hashes --no-deps -r backend/requirements-infra.lock
COPY backend/ backend/
COPY demo/ demo/
COPY knowledge/ knowledge/
COPY research/ research/
COPY --from=frontend /src/frontend/dist frontend/dist
RUN mkdir -p /data && chown lab:lab /data
USER lab
ENV EVIDENCE_LAB_DATA_DIR=/data EVIDENCE_LAB_MODE=demo EVIDENCE_LAB_BIND_HOST=0.0.0.0 EVIDENCE_LAB_PORT=8000
VOLUME ["/data"]
EXPOSE 8000
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["python", "-m", "app"]
