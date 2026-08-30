> Wireloft is currently in active development. It works and basic functionality is tested, but its very early days still.
> Absolutely use at your own risk, especially if you are using it behind a reverse proxy!

# WireLoft

## What it does
WireLoft is a self-hosted app for managing (premium) shows from The Daily Wire.  

It is built as the perfect solution for self-hosting nerds that do not want to settle for only being able to enjoy premium shows from The Daily Wire through their website. 
WireLoft allows you to download individual show episodes to your server, or just stream audio or video episodes straight to your RSS podcast client without first
having to download anything server-side. You can also automatically download audio for every item in a show, and download video only for full episodes. Or the other
way around. Whatever you want.  

Additionally, it supports downloading the premium version of shows behind the paywall, 
as long as you have a premium subscription with The Daily Wire. WireLoft is perfect for those who want to consume Daily Wire content 
through their media server (Plex, Jellyfin, Audiobookshelf) or who just want the content available locally.  

WireLoft is highly customizable to fit your exact needs. It is easy to install and use. Just launch the docker container, open the Web-UI and add any Daily Wire show. 
You can then choose to simply index that show, stream its contents straight from The Daily Wire server to your favorite podcast app, or download every single episode
(or, ofc, a subset). Anything is possible.  

This project was inspired by [Pinchflat](https://github.com/kieraneglin/pinchflat).
Pinchflat is an awesome project that allows you to automatically download videos from YouTube channels or playlists.
WireLoft takes that concept to The Daily Wire and expands on it greatly. Additionally, WireLoft allows downloading individual episodes and movies, 
making it truly a one-stop-shop for all things The Daily Wire.  

WireLoft is not meant to be used for consuming the content, it just downloads or streams it. For consuming the downloaded content 
use a self-hosted media server like Plex or Jellyfin for series, or Audiobookshelf for podcasts. Streaming should work with most podcast apps.  

## Features

- Fully-featured easy-to-use web UI for navigation and configuration
- Downloads series and podcasts with configurable parameters for each
- Download multiple versions of the same episode, automatically. For example, download both a video and audio version of the episode
- Download the premium version of episodes using your account credentials
- Supports audio-only mode for a podcast-like experience
- Intelligently helps you avoid downloading the countdown timer shown in live versions of show episodes
- Optionally automatically delete old show content from your server
- Open a private RSS feed for a show's downloaded episodes for use in any podcast app
- Download movies and trailers using Plex-friendly path templates and canonical release dates

## Planned

- Maybe: support for Bentkey - feasibility not yet known (if anyone knows how their API works, please let me know!)
- Maybe: support for browsing series- and movies not yet downloaded inside WireLoft (add them to WireLoft without a URL)

## Running with Docker

The best way to run WireLoft is using its Docker container. Everything is managed for you automatically within the container.

### Quick start: use the published image
Run this to get started immediately:
```bash
mkdir wireloft && cd wireloft
curl -O https://raw.githubusercontent.com/samuelvisser/wireloft/develop/.docker/docker-compose.yml
docker compose up -d
```
Then open http://localhost:5273. See Volumes and Useful environment
variables below for what to persist/configure; edit the compose file in
place for anything beyond the defaults.

### Or just create the compose file yourself
```yaml
services:
  wireloft:
    image: ghcr.io/samuelvisser/wireloft:latest
    restart: unless-stopped
    ports:
      - "5273:80"
    volumes:
      - ./config:/config
      - ./downloads:/downloads
    environment:
        # Set the timezone to your local timezone
      - TZ=UTC
```

### Setup

Volumes:
- `/config` -- app config (`config.yml`), the SQLite database, the session
  secret key, and your DailyWire login token. Persist this so settings, shows,
  and your login survive container restarts/upgrades.
- `/downloads` -- downloaded episodes/movies.

Useful environment variables:
- `TZ` -- container timezone (default `UTC`).
- `WL_ADMIN_AUTH__PASSWORD` -- set this to require a login to access the UI.
  Leave unset for open access on your local network. Always set this when running behind a reverse proxy.
- `WL_MOVIE_METADATA__TMDB_READ_ACCESS_TOKEN` -- TMDB API Read Access Token used
  once when a movie is first added to find and persist its canonical release
  date. Configure this before starting the first movie or trailer download.
- `API_URL` -- override the API base URL the UI is told to use (defaults to
  the relative `/api`, which works out of the box regardless of which host
  port you map).

The equivalent YAML setting is:

```yaml
movieMetadata:
  tmdbReadAccessToken: "your-tmdb-api-read-access-token"
```

WireLoft searches TMDB only while a movie is first persisted. It stores the
release date, source ID, lookup status, timestamp, and any matching error in the
local database, so later movie and trailer downloads do not repeat the lookup.
Movie Local Media Profiles can use `{year}`, `{date}`, and the other date/time
placeholders to create media-server-friendly paths such as
`Movie Title (2020)/Movie Title.mp4`.

This product uses the TMDB API but is not endorsed or certified by TMDB.

## Special thanks
While WireLoft is fully build from the ground up with original code, the open source [DailyWirePodcastProxy](https://github.com/fpnewton/DailyWirePodcastProxy) project has helped 
tremendously in figuring out how The Daily Wire API works. DailyWirePodcastProxy enables you to download premium versions of the shows 
directly from The Daily Wire to your podcast app. Definitely check it out if you’re interested!