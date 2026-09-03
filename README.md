# WireLoft

## What it does
WireLoft is a self-hosted app for managing (premium) media from The Daily Wire.  

It is built as the perfect solution for self-hosting nerds that do not want to be limited to only being able to enjoy premium shows from The Daily Wire website. 
WireLoft allows you to download individual show episodes to your server, or just stream audio or video episodes straight to your RSS podcast client without first
having to download anything server-side. You can also automatically download audio for every item in a show, and download video only for full episodes. Or the other
way around. Whatever you want. 

WireLoft works for movies hosted by The Daily Wire as well, download any that you have access to and enjoy them
with your local media server (Jellyfin, Plex, ect), or just enjoy the content locally.  

WireLoft is highly customizable to fit your exact needs. It is easy to install and use. Just launch the docker container, open the Web-UI, and add any Daily Wire show or movie. 
You can then choose to simply index that show, stream its contents straight from The Daily Wire server to your favorite podcast app, or download every single episode
(or a subset). Anything is possible.

This project was inspired by [Pinchflat](https://github.com/kieraneglin/pinchflat).
Pinchflat is an awesome project that allows you to automatically download videos from YouTube channels or playlists.
WireLoft takes that concept to The Daily Wire and expands on it greatly. Additionally, WireLoft allows downloading individual episodes and movies, 
making it truly a one-stop-shop for all things The Daily Wire.  

WireLoft is not meant to be used for consuming the content, it just downloads or streams it. For consuming the downloaded content 
use a self-hosted media server like Plex or Jellyfin for series, or Audiobookshelf for podcasts. Streaming should work with most podcast apps and
does not require a media server.

## Features

- Fully-featured easy-to-use web UI for navigation and configuration.
- Downloads series, podcasts, and movies with configurable parameters for each.
- Download multiple versions of the same episode, automatically. For example, download both a video and audio version of episodes.
- Download the premium version of episodes and movies using your The Daily Wire subscription.
- Supports audio-only mode for a podcast-like experience.
- Intelligently helps you avoid downloading the countdown timer shown in live versions of show episodes.
- Optionally automatically delete old show content from your server.
- Open a private RSS feed for a show's downloaded episodes for use in any podcast app.

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
- `API_URL` -- override the API base URL the UI is told to use (defaults to
  the relative `/api`, which works out of the box regardless of which host
  port you map).

## Special thanks
While WireLoft is fully build from the ground up with original code, the open source [DailyWirePodcastProxy](https://github.com/fpnewton/DailyWirePodcastProxy) project has helped 
tremendously in figuring out how The Daily Wire API works. DailyWirePodcastProxy enables you to download premium versions of the shows 
directly from The Daily Wire to your podcast app. Definitely check it out if you’re interested!
