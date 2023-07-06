FROM debian:11.4-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat wget unzip net-tools sudo psmisc procps \
    v4l2loopback-utils libsdl2-2.0-0 libgl1-mesa-dri \
    fluxbox xdotool unclutter \
    dbus-user-session \
    pulseaudio socat alsa-utils libspandsp2 \
    ffmpeg xvfb \
    python3 python3-pip python3-setuptools \
    libnss3 openssl \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential cmake git \
    && git clone --branch bfcp https://github.com/Renater/re.git \
    && cd re && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && wget https://github.com/baresip/rem/archive/v2.10.0.tar.gz && tar -xzf v2.10.0.tar.gz && rm v2.10.0.tar.gz \
    && cd rem-2.10.0 && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && git clone --branch bfcp https://github.com/Renater/baresip.git \
    && cd baresip && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j && cmake --install build && cd .. \
    && rm -r baresip re rem-2.10.0 \
    && git clone https://github.com/Renater/JitsiMeetUIHelper.git /var/UIHelper \
    && cd /var/UIHelper && git checkout b91c106f80d73bac5ac9d2c4d2c16ec2efb67c56 \
    && apt-get remove --purge -y \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev \
    libv4l-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential cmake git \
    && apt autoremove -y \
    && apt autoclean -y

RUN wget https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_110.0.5481.77-1_amd64.deb \
    && apt install -y ./google-chrome-stable_110.0.5481.77-1_amd64.deb \
    && rm google-chrome-stable_110.0.5481.77-1_amd64.deb \
    && CHROME_STRING=$(google-chrome --version) \
    && CHROME_VERSION_STRING=$(echo "${CHROME_STRING}" | grep -oP "\d+\.\d+\.\d+\.\d+") \
    && CHROME_MAJOR_VERSION=$(echo "${CHROME_VERSION_STRING%%.*}") \
    && wget --no-verbose -O /tmp/LATEST_RELEASE "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR_VERSION}" \
    && CHROME_DRIVER_VERSION=$(cat "/tmp/LATEST_RELEASE") \
    && wget https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip && sudo mv chromedriver /usr/bin/chromedriver && chmod +x /usr/bin/chromedriver \
    && rm chromedriver_linux64.zip \
    && apt autoremove -y \
    && apt autoclean -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip
RUN pip3 install selenium requests

RUN pip3 install gTTS pydub \
    && python3 /var/UIHelper/scripts/generate_tts_files.py -i /var/UIHelper/src/assets/lang/ -o /var/UIHelper/src/assets/lang/files/ \
    && pip3 uninstall -y gTTS pydub

COPY entrypoint.sh /var/
COPY pulseaudio/init.sh /var/pulseaudio_init.sh
COPY src/logParse.py /usr/local/bin/logParse

COPY pulseaudio/daemon.conf /etc/pulse/
COPY alsa/asound.conf /etc/asound.conf
COPY fluxbox/init /root/.fluxbox/init

COPY baresip /var/baresip
COPY browsing /var/browsing
COPY src /var/src

RUN mkdir /var/.baresip

RUN chmod +x /var/entrypoint.sh

RUN adduser root pulse-access

WORKDIR /var

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
