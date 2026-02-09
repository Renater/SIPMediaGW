FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd wget unzip net-tools sudo psmisc procps sngrep jq \
    v4l2loopback-utils libsdl2-2.0-0 libgl1-mesa-dri \
    curl \
    fluxbox xdotool unclutter wmctrl \
    gettext-base xz-utils \
    dbus-user-session \
    pulseaudio socat alsa-utils libspandsp2 \
    ffmpeg xvfb \
    python3 python3-pip python3-setuptools python3.11-venv \
    libnss3 openssl \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libvpx-dev libopus-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential cmake git \
    && git clone --branch v3.15.0_patch https://github.com/Renater/re.git && cd re \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone --branch v3.15.0_patch https://github.com/Renater/baresip.git && cd baresip \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && rm -r baresip re \
    && apt-get remove --purge -y \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libvpx-dev libopus-dev \
    libssl-dev \
    build-essential cmake git \
    && apt autoremove -y \
    && apt autoclean -y

#v=$(curl 'https://packages.debian.org/bookworm/amd64/chromium/download' | grep -o "chromium_.*.deb" | head -1 | cut -d "_" -f 2)
#https://snapshot.debian.org/archive/debian/20240930T202925Z/pool/main/c/chromium/
RUN v='144.0.7559.109-1~deb12u1' \
   && url='http://security.debian.org/debian-security/pool/updates/main/c/chromium/' \
   && wget $url'chromium_'$v'_amd64.deb' \
   && wget $url'chromium-common_'$v'_amd64.deb' \
   && wget $url'chromium-sandbox_'$v'_amd64.deb' \
   && wget $url'chromium-driver_'$v'_amd64.deb' \
   && apt install -y './chromium-sandbox_'$v'_amd64.deb' \
   && apt install -y './chromium-common_'$v'_amd64.deb' \
   && apt install -y './chromium_'$v'_amd64.deb' \
   && apt install -y './chromium-driver_'$v'_amd64.deb' \
   && rm *.deb

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir selenium requests pynetstring psutil

COPY entrypoint.sh /var/
COPY pulseaudio/init.sh /var/pulseaudio_init.sh
COPY src/logParse.py /usr/local/bin/logParse

COPY pulseaudio/daemon.conf /etc/pulse/
COPY alsa/asound.conf /etc/asound.conf
COPY fluxbox/init /root/.fluxbox/init

COPY baresip /var/baresip
COPY streaming /var/streaming
COPY recording /var/recording
COPY transcript /var/transcript
COPY browsing /var/browsing
COPY src /var/src

RUN mkdir /var/.baresip

RUN chmod +x /var/entrypoint.sh
RUN chmod +x /var/streaming/streaming.sh
RUN chmod +x /var/baresip/baresip.sh

RUN adduser root pulse-access

WORKDIR /var

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
