FROM debian:11.4-slim

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
    && git clone --branch v2.10.0_patch https://github.com/Renater/re.git \
    && cd re && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && wget https://github.com/baresip/rem/archive/v2.10.0.tar.gz && tar -xzf v2.10.0.tar.gz && rm v2.10.0.tar.gz \
    && cd rem-2.10.0 && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone --branch v2.10.0_patch https://github.com/Renater/baresip.git \
    && cd baresip && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone https://github.com/baresip/baresip-apps.git \
    && cd baresip-apps && git checkout a36b51fdbaa7dd26762bb3875259d671df1fd88e && cd .. \
    && cd baresip && cmake -B build -DAPP_MODULES_DIR=../baresip-apps/modules -DAPP_MODULES="auloop;vidloop" \
    && cmake --build build -j && cmake --install build && cd .. \
    && rm -r baresip-apps baresip re rem-2.10.0 \
    && apt-get remove --purge -y \
    libavcodec-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential wget \
    && apt autoremove -y \
    && apt autoclean -y 

WORKDIR /var

CMD ["baresip", "-f","/var/.baresip", "-v"]
