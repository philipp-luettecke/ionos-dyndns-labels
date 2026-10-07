#!/usr/bin/env python3
"""Checks containers for an ionos.dyndns.hostname label and keeps the
matching A/AAAA records at IONOS pointed at this host's current public IP -
fully unattended, no Domain Connect browser confirmation.

Two modes, both started by entrypoint.sh:
- no arguments: reconcile all currently running labeled containers once and
  exit. Triggered on a schedule by supercronic (catches IP changes).
- --listen: stay running and reconcile a container the moment it starts
  (catches newly added services immediately, without waiting for cron).
"""

import logging
import os
import sys
import time

import requests
import docker

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
)
log = logging.getLogger("ionos-dyndns-labels")

API_URL = "https://api.hosting.ionos.com/dns/v1/zones"

try:
    API_HEADERS = {
        "accept": "application/json",
        "X-API-Key": f"{os.environ['IONOS_API_PREFIX']}.{os.environ['IONOS_API_SECRET']}",
    }
except KeyError as exc:
    log.error("Missing required environment variable: %s", exc)
    sys.exit(1)

LABEL_HOSTNAME = "ionos.dyndns.hostname"
LABEL_TYPE = "ionos.dyndns.type"
LABEL_TTL = "ionos.dyndns.ttl"

DEFAULT_TYPES = os.environ.get("DEFAULT_TYPES", "A")
DEFAULT_TTL = int(os.environ.get("DEFAULT_TTL", "60"))

IP_LOOKUP_URL = {
    "A": "https://api4.ipify.org",
    "AAAA": "https://api6.ipify.org",
}

_zones = None
_ip_cache = {}


def get_zones(force=False):
    """All DNS zones in this IONOS account, cached for a minute."""
    global _zones
    if force or _zones is None:
        resp = requests.get(API_URL, headers=API_HEADERS, timeout=15)
        resp.raise_for_status()
        _zones = resp.json()
    return _zones


def find_zone_for_fqdn(fqdn):
    def best_match(zones):
        candidates = [z for z in zones if fqdn == z["name"] or fqdn.endswith("." + z["name"])]
        return max(candidates, key=lambda z: len(z["name"])) if candidates else None

    return best_match(get_zones()) or best_match(get_zones(force=True))


def get_public_ip(record_type):
    cached = _ip_cache.get(record_type)
    if cached and time.time() - cached[1] < 60:
        return cached[0]
    ip = requests.get(IP_LOOKUP_URL[record_type], timeout=10).text.strip()
    _ip_cache[record_type] = (ip, time.time())
    return ip


def parse_labels(labels):
    """Extract the hostnames/types/ttl this container wants managed, or None."""
    hostname_label = labels.get(LABEL_HOSTNAME)
    if not hostname_label:
        return []
    fqdns = [h.strip().lower() for h in hostname_label.split(",") if h.strip()]
    types = [t.strip().upper() for t in labels.get(LABEL_TYPE, DEFAULT_TYPES).split(",") if t.strip()]
    ttl = int(labels.get(LABEL_TTL, DEFAULT_TTL))
    return [(fqdn, types, ttl) for fqdn in fqdns]


def reconcile_hostname(fqdn, record_types, ttl):
    zone = find_zone_for_fqdn(fqdn)
    if not zone:
        log.error("%s: no matching zone in this IONOS account - is the domain added there?", fqdn)
        return

    zone_detail = requests.get(f"{API_URL}/{zone['id']}", headers=API_HEADERS, timeout=15).json()
    existing = [r for r in zone_detail["records"] if r["name"] == fqdn]

    to_create, to_update = [], []
    for record_type in record_types:
        if record_type not in IP_LOOKUP_URL:
            log.warning("%s: unsupported record type %s (use A or AAAA)", fqdn, record_type)
            continue
        ip = get_public_ip(record_type)
        match = next((r for r in existing if r["type"] == record_type), None)
        if match is None:
            log.info("%s %s: no record yet -> creating, pointing at %s", fqdn, record_type, ip)
            to_create.append({"name": fqdn, "type": record_type, "content": ip, "ttl": ttl})
        elif match["content"] != ip:
            log.info("%s %s: outdated (%s) -> updating to %s", fqdn, record_type, match["content"], ip)
            to_update.append({"name": fqdn, "type": record_type, "content": ip, "ttl": ttl})
        else:
            log.debug("%s %s: up to date (%s)", fqdn, record_type, ip)

    if to_create:
        resp = requests.post(f"{API_URL}/{zone['id']}/records", headers=API_HEADERS, json=to_create, timeout=15)
        resp.raise_for_status()
    if to_update:
        resp = requests.patch(f"{API_URL}/{zone['id']}", headers=API_HEADERS, json=to_update, timeout=15)
        resp.raise_for_status()


def reconcile_container(container):
    for fqdn, types, ttl in parse_labels(container.labels):
        try:
            reconcile_hostname(fqdn, types, ttl)
        except requests.HTTPError as exc:
            log.error("%s: IONOS API error: %s", fqdn, exc)
        except Exception:
            log.exception("%s: unexpected error while reconciling", fqdn)


def full_reconcile(client):
    containers = client.containers.list(filters={"status": "running"})
    labeled = [c for c in containers if LABEL_HOSTNAME in c.labels]
    log.info("Reconciling %d labeled container(s) out of %d running", len(labeled), len(containers))
    for container in labeled:
        reconcile_container(container)


def listen(client):
    """Reconcile a container the instant it starts, for immediate updates
    in between the regular cron-scheduled full_reconcile runs."""
    log.info("Listening for newly started containers")
    while True:
        try:
            for event in client.events(decode=True, filters={"type": "container", "event": "start"}):
                container_id = event.get("id") or event.get("Actor", {}).get("ID")
                if not container_id:
                    continue
                try:
                    container = client.containers.get(container_id)
                except docker.errors.NotFound:
                    continue
                if LABEL_HOSTNAME in container.labels:
                    log.info("Container %s started, reconciling its labels", container.name)
                    reconcile_container(container)
        except Exception:
            log.exception("Docker event stream interrupted, reconnecting in 5s")
            time.sleep(5)


def main():
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        log.error(
            "Cannot talk to the Docker socket (%s). Is it mounted, and can user %s read/write it "
            "(see the README section on running as user 1000:1000)?",
            exc, os.getuid(),
        )
        sys.exit(1)

    if "--listen" in sys.argv:
        listen(client)
    else:
        full_reconcile(client)


if __name__ == "__main__":
    main()
