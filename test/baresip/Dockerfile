FROM debian:9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget build-essential  ca-certificates \
    libsdl2-2.0-0 libgl1-mesa-dri xvfb \
    socat libspandsp2 \
    libnss3 openssl \
    libavcodec57 libavcodec-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev libsndfile1-dev\
    libssl-dev \
    && wget https://github.com/baresip/re/archive/v1.1.0.tar.gz && tar -xzf v1.1.0.tar.gz && rm v1.1.0.tar.gz \
    && cd re-1.1.0 && make && make install && cd .. \
    && wget https://github.com/creytiv/rem/archive/v0.6.0.tar.gz && tar -xzf v0.6.0.tar.gz && rm v0.6.0.tar.gz \
    && cd rem-0.6.0 && make && make install && cd .. \
    && wget https://github.com/baresip/baresip/archive/v1.0.0.tar.gz && tar -xzf v1.0.0.tar.gz && rm v1.0.0.tar.gz \
    && cd baresip-1.0.0 && make RELEASE=1 && make install && cd .. \
    && rm -r baresip-1.0.0 re-1.1.0 rem-0.6.0 \
    && apt-get remove --purge -y \
    libavcodec-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential wget \
    && apt autoremove -y \
    && apt autoclean -y 

WORKDIR /var

CMD ["baresip", "-f","/var/.baresip", "-v"]
