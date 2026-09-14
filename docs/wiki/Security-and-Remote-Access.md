# Security and Remote Access

WireLoft has two separate kinds of access control:

1. **Administrator authentication** protects the WireLoft web interface and its protected API.
2. **RSS feed tokens** protect private podcast/video feeds without requiring a podcast app to sign in to the web interface.

A password on the WireLoft UI does not replace the RSS token, and an RSS token does not let someone sign in to the WireLoft UI.

## Protect the web interface

For Docker, the simplest way to enable the administrator login is:

```yaml
environment:
  - WL_ADMIN_AUTH__PASSWORD=choose-a-long-unique-password
```

Restart/recreate the container after changing deployment environment variables.

If no administrator password is configured, anyone who can reach the WireLoft interface can control the application. That can include starting downloads, changing configuration, and using the Daily Wire account connected to the instance.

A password is therefore strongly recommended whenever WireLoft is reachable outside a fully trusted network.

### Session lifetime

A signed-in browser stays authenticated for 30 days by default. You can change **Session lifetime** under **Settings → General**.

## Protect the Daily Wire connection

WireLoft does not store your Daily Wire password, but its persistent `/config` data contains the application state needed to keep the Daily Wire connection working.

Treat `/config` as private data:

- do not publish or share it;
- include it in secure backups;
- protect the host filesystem it lives on;
- keep the application secret key with the rest of the configuration when restoring a backup.

Anyone with full control of your WireLoft instance may be able to use media access available to the connected Daily Wire account.

## RSS feed URLs are credentials

A WireLoft feed URL contains a secret token, for example:

```text
https://wireloft.example.com/feeds/rss/<secret-token>/<show>.xml
```

The token allows podcast clients to use the feed without the WireLoft administrator login.

Treat the complete URL like an API key:

- do not post it publicly;
- redact it from screenshots, logs, and support reports;
- do not commit it to a repository;
- avoid sharing it with people who should not have feed access;
- use HTTPS whenever it travels over an untrusted network.

This is especially important for feeds that can use member-exclusive Daily Wire media through your WireLoft instance.

### If a feed URL leaks

Open its Stream Profile and click **Regenerate**. WireLoft creates a new token and rejects future requests using the old one.

Update your own podcast clients to the new URL afterwards.

Token rotation cannot delete media another client already downloaded.

## Remote-access options

You do not have to expose WireLoft directly to the public internet.

### LAN only

The simplest option. WireLoft and its feeds are available only on your home/local network.

### VPN or private overlay network

A good option when you want remote access without publishing WireLoft on the open internet. Your phone or laptop connects to the private network first and then uses WireLoft as if it were local.

### HTTPS reverse proxy

Useful when normal podcast applications must reach a feed from anywhere without a VPN.

When using Nginx, Caddy, Traefik, or another reverse proxy:

- use HTTPS;
- enable the WireLoft administrator password;
- forward the normal WireLoft web/API traffic;
- forward the entire `/feeds/rss/` path tree for podcast feeds and their media;
- make sure the hostname stored in each Stream Profile is actually reachable by the podcast client.

Do not place WireLoft's interactive administrator login in front of RSS paths unless the podcast app supports that extra login method. Normally, the RSS token itself is the feed credential.

## Podcast apps that fetch through the cloud

Some podcast applications fetch RSS feeds from the provider's servers rather than directly from your phone.

In that case, a LAN-only or VPN-only hostname may not work even while your phone itself can reach WireLoft. Use a client that fetches directly or provide an appropriately protected reachable HTTPS address.

## Keep the application key persistent

The supplied Docker configuration stores the generated application key under `/config` (normally `/config/wl_secret.key`). Keep `/config` persistent and include it in backups.

Changing or losing this key can invalidate protected application/authentication data.

## Configuration secrets

Environment variables take priority over `config.yml`. Sensitive deployment values such as the administrator password and optional TMDB token are often best supplied through your Docker/deployment secret mechanism rather than committed to a configuration repository.

See [[Settings]] for the full configuration reference and [[Podcast-RSS-Feeds]] for feed-specific security.