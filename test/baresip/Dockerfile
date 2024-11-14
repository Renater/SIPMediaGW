FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget build-essential  ca-certificates \
    libsdl2-2.0-0 libgl1-mesa-dri xvfb \
    ffmpeg \
    socat libspandsp2 alsa-utils \
    libnss3 openssl \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential cmake git \
    && git clone --branch v3.15.0_patch https://github.com/Renater/re.git && cd re \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone --branch v3.15.0_patch https://github.com/Renater/baresip.git && cd baresip \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && rm -r baresip re \
    && apt-get remove --purge -y \
    libavcodec-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential wget cmake git \
    && apt autoremove -y \
    && apt autoclean -y 

WORKDIR /var

CMD ["baresip", "-f","/var/.baresip", "-v"]
