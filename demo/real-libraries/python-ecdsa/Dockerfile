# Evidence Lab real-library image: python-ecdsa 0.13.2 and 0.13.3. Built only by:
# cd backend && .venv/bin/python -m app.prepare
# The crypto is the library's own Python code, unpacked from its pinned, fingerprint-checked wheels onto the pinned
# Python base, so its source can be read in the image. Ours are only the test harness, the controls and the wrapper.
# No step here needs the network.
ARG PYTHON_BASE
FROM ${PYTHON_BASE}
COPY pkgs/ /tmp/pkgs/
RUN python -m zipfile -e /tmp/pkgs/ecdsa-0.13.2-py2.py3-none-any.whl /opt/evidence-lab/real/ecdsa-0.13.2/ \
 && python -m zipfile -e /tmp/pkgs/ecdsa-0.13.3-py2.py3-none-any.whl /opt/evidence-lab/real/ecdsa-0.13.3/ \
 && rm -rf /tmp/pkgs
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
