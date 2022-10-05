FROM kamailio/kamailio:5.5.0-stretch

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip cron \
    kamailio-sqlite-modules \
    && apt autoremove -y \
    && apt autoclean -y 

RUN pip3 install --upgrade pip
RUN pip3 install --upgrade setuptools
RUN pip3 install requests httplib2 pysqlite3

WORKDIR /etc/kamailio/

RUN mkdir /usr/local/etc/kamailio

EXPOSE 5060

COPY kamailioGetLogs.py /usr/local/bin/kamailioGetLogs
RUN (echo '* * * * * /usr/local/bin/kamailioGetLogs > /proc/1/fd/1 2>/proc/1/fd/2' > /etc/cron.d/logger)
RUN crontab /etc/cron.d/logger

