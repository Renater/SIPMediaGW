FROM debian:9-slim

RUN apt-get update && apt-get install -y htop nano netcat wget unzip pulseaudio v4l2loopback-utils socat alsa-utils xdotool libasound2-dev libavcodec-dev libx11-dev libxext-dev ffmpeg xvfb sudo python3 python3-pip libnss3 openssl libssl-dev libspandsp-dev libsdl2-dev 
RUN pip3 install selenium requests

RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt install -y ./google-chrome-stable_current_amd64.deb
RUN  wget https://chromedriver.storage.googleapis.com/2.41/chromedriver_linux64.zip \
     && unzip chromedriver_linux64.zip && sudo mv chromedriver /usr/bin/chromedriver && chmod +x /usr/bin/chromedriver

COPY entrypoint.sh /var/
RUN mkdir /var/.baresip

RUN chmod +x /var/entrypoint.sh

RUN adduser root pulse-access

WORKDIR /var

RUN wget https://github.com/baresip/re/archive/v1.1.0.tar.gz && tar -xzf v1.1.0.tar.gz && rm v1.1.0.tar.gz \
    && cd re-1.1.0 && make && make install && cd .. \
    && wget https://github.com/creytiv/rem/archive/v0.6.0.tar.gz && tar -xzf v0.6.0.tar.gz && rm v0.6.0.tar.gz \
    && cd rem-0.6.0 && make && make install && cd .. \
    && wget https://github.com/baresip/baresip/archive/v1.0.0.tar.gz && tar -xzf v1.0.0.tar.gz && rm v1.0.0.tar.gz \
    && cd baresip-1.0.0 && make RELEASE=1 && make install && cd .. 
    
RUN rm -r baresip-1.0.0 re-1.1.0 rem-0.6.0
RUN apt-get remove -y libasound2-dev libavcodec-dev libx11-dev libssl-dev libxext-dev libspandsp-dev

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
