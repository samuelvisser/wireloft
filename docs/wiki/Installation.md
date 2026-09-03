# Installation

Docker is the recommended way to run WireLoft. The published container includes the application and exposes the web UI and API through one HTTP port.

## Quick start

```bash
mkdir wireloft && cd wireloft
curl -O https://raw.githubusercontent.com/samuelvisser/wireloft/develop/.docker/docker-compose.yml
docker compose up -d
```

Open `http://localhost:5273`.

The supplied Compose file is equivalent to:

```yaml
services:
  wireloft:
    image: ghcr.io/samuelvisser/wireloft:latest
    container_name: wireloft
    restart: unless-stopped
    ports:
      - "5273:80"
    volumes:
      - ./config:/config
      - ./downloads:/downloads
    environment:
      - TZ=UTC
      # - WL_ADMIN_AUTH__PASSWORD=change-me
```

## Persistent volumes

### `/config`

Persist this directory. It contains WireLoft's application state, including `config.yml`, the SQLite database, the generated secret key, and Daily Wire authentication state.

A container that loses `/config` should be treated like a new installation. Back up the entire directory rather than selecting individual files unless you have a specific reason not to.

### `/downloads`

This is the default root for downloaded shows, podcasts, movies, and extras. Local Media Profile output templates begin with `/downloads/`; WireLoft maps that virtual prefix to the configured download root.

Mount the directory wherever you want the media to live on the host. Media servers such as Plex, Jellyfin, or Audiobookshelf can then be pointed at suitable subdirectories.

## Timezone

Set the standard `TZ` environment variable to an IANA timezone:

```yaml
environment:
  - TZ=Europe/Amsterdam
```

WireLoft deliberately uses `TZ` rather than `WL_TIMEZONE` for the application timezone. Scheduled jobs and date-sensitive behavior therefore use the same conventional container timezone setting.

## Administrator authentication

For a trusted LAN-only installation you can leave administrator authentication disabled, but anyone who can reach WireLoft can then control the application and access its stored Daily Wire session.

If WireLoft is reachable through a reverse proxy or from an untrusted network, set a long unique administrator password:

```yaml
environment:
  - WL_ADMIN_AUTH__PASSWORD=choose-a-long-unique-password
```

Restart the container after changing it. See [[Security-and-Remote-Access]].

## Configuration files and environment variables

WireLoft supports both `config.yml` and environment overrides. The default configuration file is seeded only once, when no `config.yml` exists yet. After that it is safe to edit in place, and changes made in the Settings UI are written to the same file.

Environment variables take precedence over `config.yml`. See [[Settings]] for the complete precedence rules and every supported key.

Two loader variables can move the configuration sources themselves:

| Variable | Purpose | Default |
| --- | --- | --- |
| `WL_CONFIG_FILE` | Path to the YAML configuration file | `<project>/config/config.yml` |
| `WL_ENV_FILE` | Path to the dotenv file | `<project>/.env` |

These are loader options rather than fields inside `config.yml`.

## UI API URL

The web UI normally talks to the relative `/api` path, which works through the bundled container regardless of the host port. `API_URL` can override that UI runtime value for unusual deployments. It is not part of WireLoft's `AppSettings` configuration model.

## Reverse proxy installations

When placing WireLoft behind a reverse proxy:

- use HTTPS if the service or RSS feeds are reachable over the internet;
- configure `WL_ADMIN_AUTH__PASSWORD` for the UI;
- ensure the hostname embedded in RSS feed URLs is reachable by the podcast client;
- do not accidentally require the WireLoft UI login on the tokenized `/feeds/rss/...` endpoints, because podcast clients access those using the secret feed token instead.

If the generated RSS hostname is wrong for your deployment, the feed URL can be edited from its Stream Profile. See [[Podcast-RSS-Feeds]].