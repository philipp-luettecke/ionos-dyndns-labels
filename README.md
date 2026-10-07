# ionos-dyndns-labels

Automatically creates and updates IONOS DNS records for your Docker services
based on a single label - **no manual browser confirmation**, unlike the
[Domain Connect](https://github.com/Domain-Connect/DomainConnectDDNS-Python)-based
[ionos-dyndns-docker](https://github.com/philipp-luettecke/ionos-dyndns-docker).

It talks directly to the [IONOS DNS API](https://api.hosting.ionos.com/dns/v1)
using an API key, watches the Docker socket for containers, and for every
container carrying `ionos.dyndns.hostname` it:

1. finds the matching zone in your IONOS account,
2. creates the DNS record if it doesn't exist yet,
3. keeps it updated whenever your public IP changes.

This only works for domains managed directly at IONOS (the classic
"Domains & Hosting" DNS, not IONOS Cloud DNS).

- **Source code, issues and releases:** https://github.com/philipp-luettecke/ionos-dyndns-labels
- **Supported architectures:** `linux/amd64`, `linux/arm64` (e.g. Raspberry Pi 4/5)

## Image tags

| Tag | Description |
| --- | --- |
| `latest` | Newest stable release |
| `1` | Newest release of major version 1 (no breaking changes) |
| `1.2` | Newest patch release of version 1.2 |
| `1.2.3` | Exact release, never changes |
| `dev` | Latest development build from the `main` branch, may be unstable |

For automatic updates without surprises use `1`. For fully reproducible setups pin an exact version like `1.2.3`.

## Why this exists

`domain-connect-dyndns` requires you to open a link and confirm access in
your browser once per hostname - that's inherent to the Domain Connect
protocol and can't be scripted around. This tool trades that one-time safety
confirmation for an IONOS API key, so adding a new service is just adding a
label - nothing to click.

## Getting an API key

Create one at the [IONOS API key manager](https://developer.hosting.ionos.com/)
(Developer Portal → DNS API). You'll get a **public prefix** and a **secret**.

## Quick start

```console
mkdir ionos-dyndns-labels && cd ionos-dyndns-labels
```

Create `docker-compose.yml`:

```yaml
services:
  ionos-dyndns-labels:
    image: philippluettecke/ionos-dyndns-labels:latest
    container_name: ionos-dyndns-labels
    restart: unless-stopped
    environment:
      - IONOS_API_PREFIX=your-prefix
      - IONOS_API_SECRET=your-secret
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

```console
docker compose up -d
```

Then, on any other service:

```yaml
services:
  whoami:
    image: traefik/whoami
    labels:
      - ionos.dyndns.hostname=whoami.example.com
```

`whoami.example.com` gets an A record pointing at this host's current public
IP automatically, and is kept in sync from then on - no `setup` command, no
browser step.

## Labels

| Label | Required | Default | Description |
| --- | --- | --- | --- |
| `ionos.dyndns.hostname` | yes | - | FQDN to manage, or a comma-separated list, e.g. `a.example.com,b.example.com` |
| `ionos.dyndns.type` | no | `A` | Comma-separated record types to maintain: `A`, `AAAA`, or both |
| `ionos.dyndns.ttl` | no | `60` | TTL in seconds for created/updated records |

Each label is read when the container **starts** (new containers are picked
up immediately via Docker events) and re-checked every `POLL_INTERVAL`
seconds for all currently running labeled containers, so an IP change is
also picked up without restarting anything.

## Settings (environment variables)

| Variable | Default | Description |
| --- | --- | --- |
| `IONOS_API_PREFIX` | - | **Required.** API key public prefix |
| `IONOS_API_SECRET` | - | **Required.** API key secret |
| `DEFAULT_TYPES` | `A` | Record type(s) used when a container has no `ionos.dyndns.type` label |
| `DEFAULT_TTL` | `60` | TTL used when a container has no `ionos.dyndns.ttl` label |
| `POLL_INTERVAL` | `300` | Seconds between full reconcile passes (catches IP changes) |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for per-check logging even when nothing changed |

## Running unprivileged

The container runs as root by default because `/var/run/docker.sock` is
normally only readable by root or the host's `docker` group. To run it as a
non-root user instead, find the GID of that group on the host
(`getent group docker`) and add it to the compose file:

```yaml
    user: "1000:1000"
    group_add:
      - "<docker-gid-on-host>"
```

## What it does *not* do

- It never deletes or removes records - stopping a labeled container just
  leaves its last known record in place.
- It only manages `A`/`AAAA` records for the exact hostname in the label,
  nothing else in the zone is touched.
- It does not create the zone/domain itself - the domain must already be
  added to your IONOS account.

## Security note

The API key in `IONOS_API_SECRET` can create and modify DNS records for
every domain in your IONOS account. Keep it out of version control (e.g. via
an `.env` file) the same way you would any other credential.

## Building the image yourself

```console
git clone https://github.com/philipp-luettecke/ionos-dyndns-labels.git
cd ionos-dyndns-labels
docker compose -f docker-compose.example.yml up -d --build
```
