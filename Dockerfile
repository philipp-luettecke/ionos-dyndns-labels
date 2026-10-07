FROM python:slim

COPY requirements.txt /app/requirements.txt
RUN pip3 --no-cache-dir install -r /app/requirements.txt

COPY app/watcher.py /app/watcher.py

# Runs as root by default because it needs to read /var/run/docker.sock,
# which is normally only accessible to root or the host's "docker" group.
# See README for how to run it unprivileged instead.
ENTRYPOINT [ "python3", "/app/watcher.py" ]
