# Evidence Lab real-library image: Java (OpenJDK 17.0.2 and 17.0.3, Temurin builds). Built only by:
# cd backend && .venv/bin/python -m app.prepare
# The crypto is each JDK's own, copied from the pinned Temurin images onto the pinned Python base. Ours are only
# the test harness, the controls and the wrapper, compiled by each JDK's own javac. No step here needs the network.
ARG PYTHON_BASE
ARG JDK_AFFECTED
ARG JDK_FIXED
FROM ${JDK_AFFECTED} AS jdk-affected
COPY real/EcdsaAdapter.java /src/EcdsaAdapter.java
RUN javac -d /opt/classes /src/EcdsaAdapter.java
FROM ${JDK_FIXED} AS jdk-fixed
COPY real/EcdsaAdapter.java /src/EcdsaAdapter.java
RUN javac -d /opt/classes /src/EcdsaAdapter.java
FROM ${PYTHON_BASE}
COPY --from=jdk-affected /opt/java/openjdk /opt/java/17.0.2
COPY --from=jdk-fixed /opt/java/openjdk /opt/java/17.0.3
COPY --from=jdk-affected /opt/classes /opt/evidence-lab/real/classes-17.0.2
COPY --from=jdk-fixed /opt/classes /opt/evidence-lab/real/classes-17.0.3
COPY components/ /opt/evidence-lab/components/
COPY real/ /opt/evidence-lab/real/
USER 65534:65534
