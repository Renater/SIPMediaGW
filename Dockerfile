FROM debian:12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd wget unzip net-tools sudo psmisc procps sngrep\
    v4l2loopback-utils libsdl2-2.0-0 libgl1-mesa-dri \
    fluxbox xdotool unclutter \
    dbus-user-session \
    pulseaudio socat alsa-utils libspandsp2 \
    ffmpeg xvfb \
    python3 python3-pip python3-setuptools python3.11-venv\
    libnss3 openssl \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential cmake git \
    && git clone --branch bfcp https://github.com/Renater/re.git \
    && cd re && git checkout 9e879ba5a9e8944dfac2514311016866d133d334 \
    && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && wget https://github.com/baresip/rem/archive/v2.10.0.tar.gz && tar -xzf v2.10.0.tar.gz && rm v2.10.0.tar.gz \
    && cd rem-2.10.0 && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone --branch bfcp https://github.com/Renater/baresip.git \
    && cd baresip && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && rm -r baresip re rem-2.10.0 \
    && git clone https://github.com/Renater/JitsiMeetUIHelper.git /var/UIHelper \
    && cd /var/UIHelper && git checkout a18a3527fab43fcdc423e1cd8d16e87f0c59fc61 \
    && apt-get remove --purge -y \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential cmake git \
    && apt autoremove -y \
    && apt autoclean -y

RUN wget http://security.debian.org/debian-security/pool/updates/main/c/chromium/chromium_128.0.6613.113-1~deb12u1_amd64.deb \
   && wget http://security.debian.org/debian-security/pool/updates/main/c/chromium/chromium-sandbox_128.0.6613.113-1~deb12u1_amd64.deb \
   && wget http://security.debian.org/debian-security/pool/updates/main/c/chromium/chromium-driver_128.0.6613.113-1~deb12u1_amd64.deb \
   && apt install -y ./chromium-sandbox_128.0.6613.113-1~deb12u1_amd64.deb \
   && apt install -y ./chromium_128.0.6613.113-1~deb12u1_amd64.deb \
   && apt install -y ./chromium-driver_128.0.6613.113-1~deb12u1_amd64.deb \
   && rm *.deb

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --no-cache-dir --upgrade pip
RUN pip3 install --no-cache-dir selenium requests pynetstring

RUN pip3 install --no-cache-dir gTTS pydub \
    && python3 /var/UIHelper/scripts/generate_tts_files.py -i /var/UIHelper/src/assets/lang/ -o /var/UIHelper/src/assets/lang/files/ \
    && pip3 uninstall -y gTTS pydub

COPY entrypoint.sh /var/
COPY pulseaudio/init.sh /var/pulseaudio_init.sh
COPY src/logParse.py /usr/local/bin/logParse

COPY pulseaudio/daemon.conf /etc/pulse/
COPY alsa/asound.conf /etc/asound.conf
COPY fluxbox/init /root/.fluxbox/init

COPY baresip /var/baresip
COPY streaming /var/streaming
COPY browsing /var/browsing
COPY src /var/src

RUN mkdir /var/.baresip

RUN chmod +x /var/entrypoint.sh
RUN chmod +x /var/streaming/streaming.sh
RUN chmod +x /var/baresip/baresip.sh

RUN adduser root pulse-access

WORKDIR /var

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
