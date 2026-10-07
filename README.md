# ionos-dyndns-labels

Automatically creates and updates IONOS DNS records for your Docker services
based on a single label - **no manual browser confirmation**, unlike the
[Domain Connect](https://github.com/Domain-Connect/DomainConnectDDNS-Python)-based
[ionos-dyndns-docker](https://github.com/philipp-luettecke/ionos-dyndns-docker).

It talks directly to the [IONOS DNS API](https://api.hosting.ionos.com/dns/v1)
using an API key. It reacts immediately when a labeled container starts
(via Docker events), and additionally re-checks every running container on
a schedule (`CRON_SCHEDULE`, same as `ionos-dyndns-docker`) to catch public
IP changes. For each container carrying `ionos.dyndns.hostname` it:

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
      - CRON_SCHEDULE=*/15 * * * *
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    # Runs as user 1000:1000; it also needs the host's "docker" group to
    # read the socket. Find the GID with `getent group docker`.
    user: "1000:1000"
    group_add:
      - "<docker-gid-on-host>"
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

The moment this container starts, `whoami.example.com` gets an A record
pointing at this host's current public IP - no `setup` command, no browser
step - and is kept in sync from then on.

## Labels

| Label | Required | Default | Description |
| --- | --- | --- | --- |
| `ionos.dyndns.hostname` | yes | - | FQDN to manage, or a comma-separated list, e.g. `a.example.com,b.example.com` |
| `ionos.dyndns.type` | no | `A` | Comma-separated record types to maintain: `A`, `AAAA`, or both |
| `ionos.dyndns.ttl` | no | `60` | TTL in seconds for created/updated records |

Labels are picked up two ways:

- **Immediately** - a Docker event listener reconciles a container the
  moment it starts, so a newly labeled service gets its record within
  seconds, not at the next cron tick.
- **On schedule** - every `CRON_SCHEDULE` run (plus once when
  `ionos-dyndns-labels` itself starts) re-checks **all** currently running
  labeled containers, which is what catches a changed public IP for
  everyone, including services that haven't restarted.

## Settings (environment variables)

| Variable | Default | Description |
| --- | --- | --- |
| `IONOS_API_PREFIX` | - | **Required.** API key public prefix |
| `IONOS_API_SECRET` | - | **Required.** API key secret |
| `CRON_SCHEDULE` | `*/15 * * * *` | When to check labeled containers, in cron format (see below) |
| `DEFAULT_TYPES` | `A` | Record type(s) used when a container has no `ionos.dyndns.type` label |
| `DEFAULT_TTL` | `60` | TTL used when a container has no `ionos.dyndns.ttl` label |
| `TZ` | `UTC` | Your time zone, e.g. `Europe/Berlin`. Cron times are interpreted in this zone |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for per-check logging even when nothing changed |

### The update schedule (cron format)

`CRON_SCHEDULE` consists of five fields separated by spaces:

```
┌───────── minute (0-59)
│ ┌─────── hour (0-23)
│ │ ┌───── day of month (1-31)
│ │ │ ┌─── month (1-12)
│ │ │ │ ┌─ day of week (0-7, Sunday = 0 or 7)
│ │ │ │ │
* * * * *
```

`*` means "every", `*/15` means "every 15th". If the expression is invalid,
the container stops and prints an error in the log. All labeled containers
are additionally reconciled once every time the container starts.

Internally, the cron schedule and the Docker event listener run as two
separate processes in the same container. If either one dies unexpectedly,
the container exits so `restart: unless-stopped` brings both back up
cleanly.

## Running as user 1000:1000

Like `ionos-dyndns-docker`, this image runs as root unless you tell it
otherwise, but is designed to run as `1000:1000` instead (set via `user:` in
the compose file, as in the quick start above). Since
`/var/run/docker.sock` is normally only readable by root or the host's
`docker` group, that user also needs to be a member of the host's `docker`
group inside the container - find its GID with `getent group docker` on the
host and set it as `group_add`:

```yaml
    user: "1000:1000"
    group_add:
      - "<docker-gid-on-host>"
```

If you'd rather run it as root (skipping the `group_add` lookup), just drop
both `user:` and `group_add:` from the compose file.

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
