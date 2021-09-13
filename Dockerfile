FROM debian:9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat wget unzip sudo \
    v4l2loopback-utils xdotool libsdl2-2.0-0 libgl1-mesa-dri \
    dbus-user-session \
    pulseaudio socat alsa-utils libspandsp2 \
    ffmpeg xvfb \
    python3 python3-pip \
    libnss3 openssl \
    libavcodec-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential \
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
    build-essential \
    && apt autoremove -y \
    && apt autoclean -y 

RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
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

RUN pip3 install selenium requests

COPY entrypoint.sh event_handler.py /var/

RUN mkdir /var/.baresip

RUN chmod +x /var/entrypoint.sh

RUN adduser root pulse-access

WORKDIR /var

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
