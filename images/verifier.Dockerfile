FROM ghcr.io/eda-bench/eda-bench-agent:harbor-v1

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/eda-bench

COPY verifier/tasks /opt/eda-bench/tasks
COPY dataset /opt/eda-bench/dataset
COPY verifier/grader.py verifier/test.sh /tests/
RUN chmod +x /tests/test.sh

WORKDIR /workspace
