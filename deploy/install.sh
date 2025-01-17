#!/bin/bash

apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd wget unzip net-tools sudo psmisc procps sngrep \
    v4l2loopback-utils libsdl2-2.0-0 libgl1-mesa-dri \
    fluxbox xdotool unclutter \
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
    && git clone https://github.com/Renater/JitsiMeetUIHelper.git /var/UIHelper \
    && cd /var/UIHelper && git checkout dc50c19eac4113976fea37ae02838693996a2bf5 \
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
v='131.0.6778.85-1~deb12u1' \
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

python3 -m venv /opt/venv
export PATH="/opt/venv/bin:$PATH"
pip3 install --no-cache-dir --upgrade pip
pip3 install --no-cache-dir selenium requests pynetstring

pip3 install --no-cache-dir gTTS pydub \
    && python3 /var/UIHelper/scripts/generate_tts_files.py -i /var/UIHelper/src/assets/lang/ -o /var/UIHelper/src/assets/lang/files/ \
    && pip3 uninstall -y gTTS pydub

cp /sipmediagw/entrypoint.sh /var/
cp /sipmediagw/pulseaudio/init.sh /var/pulseaudio_init.sh
cp /sipmediagw/src/logParse.py /usr/local/bin/logParse

cp /sipmediagw/pulseaudio/daemon.conf /etc/pulse/
cp /sipmediagw/alsa/asound.conf /etc/asound.conf
mkdir /root/.fluxbox
cp /sipmediagw/fluxbox/init /root/.fluxbox/init

cp -r /sipmediagw/baresip /var/baresip
cp -r /sipmediagw/streaming /var/streaming
cp -r /sipmediagw/browsing /var/browsing
cp -r /sipmediagw/src /var/src

mkdir /var/.baresip

chmod +x /var/entrypoint.sh
chmod +x /var/streaming/streaming.sh
chmod +x /var/baresip/baresip.sh
