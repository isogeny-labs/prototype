# Evidence Lab sandbox copy (JavaScript). Built only by the research command or the prepare command, never by the app.
# The library's own files, and its helper libraries, were fetched from the public registry, checked against the
# registry's fingerprints and unpacked as data before this build. Node is copied from the pinned Node image onto the
# pinned Python base (the test harness is Python). There is no RUN step, and no step needs the network.
ARG PYTHON_BASE
ARG NODE_IMAGE
FROM ${NODE_IMAGE} AS node
FROM ${PYTHON_BASE}
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/lib/libstdc++.so.6 /usr/lib/libstdc++.so.6
COPY --from=node /usr/lib/libgcc_s.so.1 /usr/lib/libgcc_s.so.1
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
