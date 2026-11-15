# Evidence Lab real-library image: elliptic 6.5.6 and 6.5.7 (npm). Built only by: cd backend && .venv/bin/python -m app.prepare
# The crypto is elliptic's own JavaScript, unpacked from its pinned, fingerprint-checked npm files (with its seven
# dependencies, one tree per version) and run by Node, copied from the pinned Node image onto the pinned Python base.
# Ours are only the test harness, the controls and the wrapper. No step here needs the network.
ARG PYTHON_BASE
ARG NODE_IMAGE
FROM ${NODE_IMAGE} AS node
FROM ${PYTHON_BASE}
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/lib/libstdc++.so.6 /usr/lib/libstdc++.so.6
COPY --from=node /usr/lib/libgcc_s.so.1 /usr/lib/libgcc_s.so.1
COPY pkgs/ /tmp/pkgs/
RUN set -e; \
 for v in 6.5.6 6.5.7; do \
  for p in bn.js-4.12.5 brorand-1.1.0 hash.js-1.1.7 hmac-drbg-1.0.1 inherits-2.0.4 minimalistic-assert-1.0.1 minimalistic-crypto-utils-1.0.1 elliptic-$v; do \
   d=/opt/evidence-lab/real/elliptic-$v/node_modules/${p%-*}; mkdir -p $d; tar -xzf /tmp/pkgs/$p.tgz --strip-components=1 -C $d; \
  done; \
 done; rm -rf /tmp/pkgs
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
