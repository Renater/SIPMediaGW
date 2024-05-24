FROM coturn/coturn

USER 0
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 wget
RUN wget https://github.com/sipcapture/heplify/releases/download/v1.66.2/heplify \
    && mv heplify /usr/local/bin/heplify && chmod +x /usr/local/bin/heplify
COPY heplify.sh /usr/local/bin/heplify.sh
COPY coturnRun.py /usr/local/bin/coturnRun
