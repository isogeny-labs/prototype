# Evidence Lab real-library image: OpenSSL 3.5.9. Built only by: cd backend && .venv/bin/python -m app.prepare
# The crypto is OpenSSL's own library file (libcrypto), copied from the pinned OpenSSL image onto the pinned
# Python base. Ours are only the test harness, the controls and the wrapper. No step here needs the network.
ARG PYTHON_BASE
ARG LIBRARY_IMAGE
FROM ${LIBRARY_IMAGE} AS library
FROM ${PYTHON_BASE}
COPY --from=library /usr/lib/libcrypto.so.3 /usr/lib/libcrypto.so.3
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
