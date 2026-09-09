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
    && git clone --branch v3.15.0_patchv3 https://github.com/Renater/re.git && cd re \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone --branch v3.15.0_patchv3 https://github.com/Renater/baresip.git && cd baresip \
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
# Debian keeps only the current Chromium in the security pool and rotates it
# about every week, so a pinned version stops resolving without warning. The
# build tries the pin, falls back to the newest available version, and records
# what it installed: two images from the same commit may then differ, and
# /etc/chromium.version says how. The pool also carries Debian 13 packages,
# hence the ~deb12u filter: the base image here is debian:12-slim.
ARG CHROMIUM_VERSION=150.0.7871.124-1~deb12u1
RUN set -eu \
   && url='http://security.debian.org/debian-security/pool/updates/main/c/chromium/' \
   && v="$CHROMIUM_VERSION" \
   && if ! wget -q --spider $url'chromium_'$v'_amd64.deb'; then \
        echo '=============================================================='; \
        echo "WARNING: Chromium $v is gone from the Debian security pool."; \
        v=$(wget -qO- $url \
            | grep -o 'chromium_[0-9][^"]*~deb12u[0-9]*_amd64\.deb' \
            | sed 's/chromium_//;s/_amd64\.deb//' | sort -V | tail -1); \
        [ -n "$v" ] || { echo 'No Debian 12 build found in the pool.'; exit 1; }; \
        echo "Falling back to $v. This build is NOT reproducible;"; \
        echo 'see /etc/chromium.version in the resulting image.'; \
        echo '=============================================================='; \
      fi \
   && for pkg in chromium chromium-common chromium-sandbox chromium-driver; do \
        wget $url$pkg'_'$v'_amd64.deb'; \
      done \
   && apt install -y './chromium-sandbox_'$v'_amd64.deb' \
   && apt install -y './chromium-common_'$v'_amd64.deb' \
   && apt install -y './chromium_'$v'_amd64.deb' \
   && apt install -y './chromium-driver_'$v'_amd64.deb' \
   && rm *.deb \
   && echo "$v" > /etc/chromium.version \
   && echo "Chromium installed: $v"

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir selenium requests pynetstring psutil qrcode pillow

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
