# WireLoft Wiki

WireLoft is a self-hosted media manager for Daily Wire shows, podcasts, series, and movies. It can index your library, download media to local storage, or expose shows as private RSS feeds that stream downloaded files and/or media directly from Daily Wire.

This Wiki documents the current WireLoft 1.0-era `develop` implementation.

## Start here

- [[Installation]] — run WireLoft with Docker and persist the correct data.
- [[First-Run-Setup]] — connect Daily Wire, protect the UI, and add your first media.
- [[Daily-Wire-Integration]] — account authorization, membership access, catalog/API behavior, and live/publishing metadata.
- [[Shows-and-Library]] — browse, add, sync, and manage shows, seasons, episodes, and movies.
- [[Download-Profiles]] — control what WireLoft downloads and how long it keeps it.
- [[Local-Media-Profiles]] — choose formats and build output paths using Jinja templates.
- [[Downloads-and-File-Integrity]] — actual download files, FFmpeg remuxing, verification, and filesystem reconciliation.
- [[Podcast-RSS-Feeds]] — create private podcast feeds and choose local/downloaded versus Daily Wire streaming behavior.
- [[Settings]] — complete settings reference, including every `config.yml` key, environment-variable equivalent, default, and purpose.
- [[Automation-and-Background-Tasks]] — episode discovery, publication monitoring, retries, verification, and scheduling.
- [[Security-and-Remote-Access]] — administrator authentication, reverse proxies, and RSS feed security.
- [[Backups-and-Upgrades]] — what to persist and back up.
- [[Troubleshooting]] — common causes of missing media, failed downloads, RSS problems, and configuration surprises.

## How WireLoft fits together

WireLoft separates **what media you want**, **how it should be stored**, and **how it should be exposed**:

1. A **Show** or **Movie** represents Daily Wire content in your WireLoft library.
2. A **Local Media Profile** defines a local format and output path, such as 1080p video under a Plex-friendly directory or audio-only files under a podcast directory.
3. A **Download Profile** determines which episodes/seasons/types should automatically be downloaded using a Local Media Profile.
4. An **RSS Stream Profile** creates a private RSS feed and decides whether the feed serves local downloads, falls back to Daily Wire, or both.
5. Background workers discover new episodes, monitor live/publishing state, download eligible media, refresh metadata, and verify files on disk.

This separation is intentional: one show can have multiple download profiles and multiple local formats while an RSS feed independently decides which of those files to use.

## Premium content

WireLoft does not bypass Daily Wire membership checks. Premium content requires a Daily Wire account with access to that content. WireLoft uses Daily Wire's device authorization flow and does not ask for your Daily Wire password.

## Important RSS security note

A WireLoft RSS feed URL contains a secret token. **Treat the complete feed URL like a password or API key.** Anyone who has it can request that feed and the media exposed through it without logging into the WireLoft UI. See [[Podcast-RSS-Feeds]] and [[Security-and-Remote-Access]] before exposing feeds outside your LAN.