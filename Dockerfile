FROM debian:9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat wget unzip net-tools sudo psmisc \
    v4l2loopback-utils xdotool libsdl2-2.0-0 libgl1-mesa-dri \
    dbus-user-session \
    socat alsa-utils libspandsp2 \
    ffmpeg xvfb \
    python3 python3-pip python3-setuptools \
    libnss3 openssl \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential git \
    && wget https://github.com/baresip/re/archive/v2.5.0.tar.gz && tar -xzf v2.5.0.tar.gz && rm v2.5.0.tar.gz \
    && cd re-2.5.0 && make && make install && cd .. \
    && wget https://github.com/baresip/rem/archive/v2.5.0.tar.gz && tar -xzf v2.5.0.tar.gz && rm v2.5.0.tar.gz \
    && cd rem-2.5.0 && make && make install && cd .. \
    && git clone --branch v2.5.0_x11grab https://github.com/Renater/baresip.git \
    && cd baresip && make RELEASE=1 && make install && cd .. \
    && rm -r baresip re-2.5.0 rem-2.5.0 \
    && apt-get remove --purge -y \
    libavcodec-dev libavformat-dev libavutil-dev libavdevice-dev libx11-dev libxext-dev libspandsp-dev libasound2-dev libsdl2-dev \
    libssl-dev \
    build-essential git \
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

RUN pip3 install --upgrade pip
RUN pip3 install selenium requests opencv-python pillow

COPY entrypoint.sh /var/

COPY baresip /var/baresip
COPY browsing /var/browsing
COPY ivr /var/ivr

COPY src /var/src

RUN mkdir /var/.baresip

RUN chmod +x /var/entrypoint.sh

WORKDIR /var

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
