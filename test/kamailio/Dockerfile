# To build from kamailio directory: docker build -t kamailio4sipmediagw -f Dockerfile ../..
FROM kamailio/kamailio:5.5.0-stretch

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip cron \
    kamailio-sqlite-modules \
    && rm /usr/bin/python && ln -s /usr/bin/python3 /usr/bin/python \
    && apt autoremove -y \
    && apt autoclean -y 

RUN pip3 install --upgrade pip
RUN pip3 install --upgrade setuptools
RUN pip3 install requests httplib2 pysqlite3

WORKDIR /etc/kamailio/

RUN mkdir /usr/local/etc/kamailio

EXPOSE 5060

COPY sipmediagw.cfg /etc/sipmediagw.cfg

VOLUME /etc/kamailio
COPY test/kamailio/config/* /etc/kamailio/
RUN kamdbctl create

COPY test/kamailio/kamailioRun.py /usr/local/bin/kamailioRun

COPY test/kamailio/kamailioGetLogs.py /usr/local/bin/kamailioGetLogs
RUN (echo '* * * * * /usr/local/bin/kamailioGetLogs > /proc/1/fd/1 2>/proc/1/fd/2' > /etc/cron.d/logger)
RUN crontab /etc/cron.d/logger

