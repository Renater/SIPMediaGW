FROM coturn/coturn

USER 0
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3

COPY coturnRun.py /usr/local/bin/coturnRun
