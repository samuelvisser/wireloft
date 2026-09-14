# Installation

Docker is the recommended way to run WireLoft. The published container includes the backend, web interface, FFmpeg, and the web server used to expose them through one HTTP port.

## Quick start

```bash
mkdir wireloft && cd wireloft
curl -O https://raw.githubusercontent.com/samuelvisser/wireloft/main/.docker/docker-compose.yml
docker compose up -d
```

Open:

```text
http://localhost:5273
```

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

After WireLoft opens, continue with [[First-Run-Setup]]. For the supplied Docker layout, also confirm **Settings → Downloads → Download root** is set to `/downloads` so downloaded media uses the persistent media mount.

## Persistent storage

WireLoft keeps the application itself inside the container and stores persistent data in mounted directories. Recreating or upgrading the container is therefore safe as long as these mounts are preserved.

### `/config` — required

Persist the entire `/config` directory. It contains WireLoft's database, configuration, secret-key material, and Daily Wire authentication state.

If `/config` is lost, WireLoft should be treated as a new installation.

### `/downloads` — your media library

The supplied Compose file maps `./downloads` on the host to `/downloads` in the container. Set **Download root** to `/downloads` when using this layout.

Local Media Profiles use paths beginning with `/downloads/`. WireLoft resolves that virtual prefix from the configured Download root. See [[Local-Media-Profiles]] and [[Settings#downloads]].

You can point Plex, Jellyfin, Audiobookshelf, or another media application at the appropriate folders inside the host's download directory.

If you enable temporary download mode, also review **Temporary download folder**. It can remain on container-local storage when you only need a staging area, or you can point it at another suitable disk/mount.

## Set your timezone

Change `TZ` to your local IANA timezone, for example:

```yaml
environment:
  - TZ=Europe/Amsterdam
```

The timezone affects scheduled jobs and how WireLoft displays and interprets time-based behavior.

## Protect the web interface

On a trusted LAN you can run WireLoft without its own administrator password. If other people can reach the service, or if you expose it through a reverse proxy, configure one:

```yaml
environment:
  - WL_ADMIN_AUTH__PASSWORD=choose-a-long-unique-password
```

Restart the container after changing deployment environment variables:

```bash
docker compose up -d
```

This password protects the WireLoft web interface. Private RSS feeds use their own secret URLs instead. See [[Security-and-Remote-Access]].

## Configuration

For normal use, configure WireLoft from **Settings** in the web interface. Changes are saved to the persistent `config.yml` under `/config`.

Environment variables can override settings when you need deployment-level control. If a setting is controlled by an environment variable, the Settings page shows that override and does not pretend a saved UI value can replace it.

See [[Settings]] for the full reference.

## Reverse proxy and remote access

If WireLoft will be available outside your trusted local network:

- use HTTPS;
- enable the WireLoft administrator password;
- make sure the hostname stored in RSS Stream Profiles is reachable by your podcast clients;
- forward both the normal WireLoft application and `/feeds/rss/` paths;
- keep RSS feed URLs private, because the token in the URL is the feed credential.

A VPN or private overlay network is also a good option when you do not want to expose WireLoft publicly. See [[Security-and-Remote-Access]].

## Updating WireLoft

For a normal Compose installation:

```bash
docker compose pull
docker compose up -d
```

WireLoft applies database migrations when the container starts. Back up `/config` before important upgrades. See [[Backups-and-Upgrades]].