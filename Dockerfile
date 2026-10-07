FROM python:slim

ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.49

COPY requirements.txt /app/requirements.txt
RUN pip3 --no-cache-dir install -r /app/requirements.txt

# supercronic: cron daemon that runs without root (container runs as user 1000:1000)
ADD https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH} /usr/local/bin/supercronic
RUN chmod 0755 /usr/local/bin/supercronic

COPY app/watcher.py /app/watcher.py
COPY --chmod=0755 entrypoint.sh /run/entrypoint.sh

# Fallback default (every 15 minutes); override via CRON_SCHEDULE in docker-compose.yml
ENV CRON_SCHEDULE="*/15 * * * *"

ENTRYPOINT [ "/run/entrypoint.sh" ]
