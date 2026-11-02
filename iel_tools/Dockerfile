# Customer-side runner container harness. UNTESTED in the environment used to build this MVP (no Docker daemon).
FROM python:3.13-slim
RUN pip install --no-cache-dir cryptography dilithium-py
WORKDIR /app
COPY iel_tools /app/iel_tools
COPY backend/fixtures /app/iel_tools/fixtures
ENTRYPOINT ["python", "-m", "iel_tools.runner"]
