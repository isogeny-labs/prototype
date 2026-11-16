# Evidence Lab capability-check image (phase 4d): Debian 12's own build of OpenSSL 3.0.22, the known-incapable copy.
# Built only by: cd backend && .venv/bin/python -m app.prepare
# The base is the pinned Docker Official Image python:3.12-slim-bookworm, which carries Debian's libcrypto and its
# `openssl` program. Ours are only the test harness and the OpenSSL wrapper (shared with the openssl folder).
# Used only for the capability check: never a test subject, never in Retest. No step here needs the network.
ARG PYTHON_BASE
ARG LIBRARY_IMAGE
FROM ${LIBRARY_IMAGE}
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
