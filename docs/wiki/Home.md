# WireLoft 1.1 Wiki

WireLoft is a self-hosted media manager for Daily Wire shows, podcasts, series, and movies. It can keep a local library of Daily Wire content, download media to your own storage, and expose shows through private RSS feeds.

This wiki documents **WireLoft 1.1**. It focuses on what features do, how to configure them, and how to solve common problems.

## What you can do with WireLoft

- Browse The Daily Wire shows and movies and add them to your own Library.
- Keep show seasons and episodes synchronized automatically.
- Download episodes in audio, 720p, 1080p, or 4K where available.
- Download movies and movie extras using separate movie storage rules.
- Keep only the latest episodes, a date window, selected seasons, or everything.
- Organize files with customizable Local Media Profiles and Jinja output templates.
- Subscribe to private RSS feeds that use downloaded files, Daily Wire streaming, or both.
- Track active, queued, failed, missing, and corrupted downloads from one place.

## Main areas of the interface

### Home

The Home page is WireLoft's status dashboard. It shows active and queued downloads, recent completions, and items that need attention such as failed downloads or movie metadata problems.

### Browse

Browse is the Daily Wire catalog. Use it to find shows and movies that are not yet in your Library.

### Library

The Library contains the shows and movies WireLoft manages for you. Adding something to the Library does **not** automatically mean it must be downloaded.

For shows, WireLoft can manage seasons, episodes, automatic downloads, and RSS feeds. Movies are downloaded manually and can include extras such as trailers or featurettes when The Daily Wire provides them.

### Downloads

The Downloads page is the central history and queue for actual media files. It shows progress, format, size, status, and available actions such as cancel, retry, prioritize, and viewing the download log.

### Profiles

WireLoft separates three decisions so they can be changed independently:

1. A **Local Media Profile** defines the format, download behavior, and output path for a local file.
2. A **Download Profile** decides which show episodes should be downloaded automatically with a Local Media Profile.
3. An **RSS Stream Profile** decides which episodes appear in a private feed and whether media should come from local downloads, Daily Wire, or both.

This makes it possible, for example, to keep every episode as audio, retain only the latest five episodes as 1080p video, and expose both through one RSS feed.

### Settings

The Settings page covers normal application, download, automation, Daily Wire, and advanced settings. Most users can configure WireLoft entirely from this page; environment variables are mainly useful when a deployment needs to enforce a value.

## Start here

- [[Installation]] — install WireLoft with Docker and persist the correct directories.
- [[First-Run-Setup]] — connect Daily Wire, secure WireLoft, and add your first media.
- [[Shows-and-Library]] — understand Home, Browse, Library, shows, movies, seasons, and episodes.
- [[Local-Media-Profiles]] — choose formats, download behavior, and output paths.
- [[Download-Profiles]] — configure automatic show downloads and retention.
- [[Downloads-and-File-Integrity]] — use the download queue and understand missing/corrupted file handling.
- [[Podcast-RSS-Feeds]] — create private podcast/video feeds.
- [[Automation-and-Background-Tasks]] — understand what WireLoft keeps updated automatically.
- [[Settings]] — complete user-facing settings reference.
- [[Security-and-Remote-Access]] — protect the UI and private feeds.
- [[Backups-and-Upgrades]] — back up and update your installation safely.
- [[Troubleshooting]] — symptom-based help for common problems.

## The Daily Wire access

WireLoft does not bypass The Daily Wire membership checks. Public content can be used without connecting an account. Member-exclusive content requires a Daily Wire account that already has access to it.

WireLoft uses Daily Wire's device authorization flow, so you authorize WireLoft through The Daily Wire rather than giving WireLoft your Daily Wire password. See [[Daily-Wire-Integration]].

## Keep RSS URLs private

A WireLoft RSS feed URL contains a secret token. Treat the complete URL like a password or API key. Anyone who has it can use that feed without signing in to the WireLoft web interface.

If a feed URL is exposed, regenerate it from the Stream Profile. See [[Podcast-RSS-Feeds]] and [[Security-and-Remote-Access]].