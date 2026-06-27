FROM python:3.11

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install -U pip setuptools
RUN pip install -r requirements.txt
RUN pip install git+https://github.com/osuAkatsuki/akatsuki-cli

COPY scripts /scripts
RUN chmod u+x /scripts/*

COPY . /srv/root
WORKDIR /srv/root

ENTRYPOINT ["/scripts/bootstrap.sh"]
