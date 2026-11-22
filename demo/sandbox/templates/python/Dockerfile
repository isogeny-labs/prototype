# Evidence Lab sandbox copy (Python). Built only by the research command or the prepare command, never by the app.
# The library's own files were fetched from its public registry, checked against the registry's fingerprint and
# unpacked as data before this build. Ours are the test harness, the controls and the asking program. There is no RUN
# step: nothing of the library runs while the image is built, and no step needs the network.
ARG PYTHON_BASE
FROM ${PYTHON_BASE}
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
