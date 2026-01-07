FROM debian:11.4-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl jq && ln -s /usr/bin/python3 /usr/bin/python

RUN pip3 install --upgrade pip
RUN pip3 install --upgrade setuptools
RUN pip3 install requests httplib2 web.py mysql-connector-python \
                 defusedxml fire xmltodict typing_extensions \
                 python-dateutil redis

COPY HTTPLauncher.py /var
COPY entrypoint.sh /var
WORKDIR /var

ENTRYPOINT ["/bin/bash", "/var/entrypoint.sh"]
