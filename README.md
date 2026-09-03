# WireLoft

## What it does

WireLoft is an easy-to-use, highly polished self-hosted app for managing (premium) media from The Daily Wire. 

It is built for self-hosting nerds who want to enjoy premium shows from The Daily Wire without being limited to its website or app. WireLoft allows you to download individual show episodes to your server, or stream audio and video episodes straight to your RSS podcast client without having to download anything server-side first.

WireLoft is highly customizable to fit your exact needs. You can automatically download audio for every item in a show while downloading video only for full episodes, do it the other way around, or configure something entirely different. You can simply index a show, stream its contents directly from The Daily Wire's servers to your favorite podcast app, download every episode, or download only the subset you are interested in. Whatever you want.

WireLoft works with movies hosted by The Daily Wire as well. Download any movie you have access to and enjoy it through your local media server, such as Jellyfin or Plex, or simply watch it locally. Despite all of these options, WireLoft is designed to remain easy to install and use: launch the Docker container, open the Web UI, and add any Daily Wire show or movie.

This project was inspired by [Pinchflat](https://github.com/kieraneglin/pinchflat), an awesome project that allows you to automatically download videos from YouTube channels and playlists. WireLoft takes that concept to The Daily Wire and expands on it greatly. In addition to automatically managing shows, WireLoft supports individual episodes and movies, making it a true one-stop shop for all things The Daily Wire.

WireLoft is not meant to be used for consuming the content itself; it downloads, organizes, or streams it for you. For downloaded content, use a self-hosted media server such as Plex or Jellyfin for video, or Audiobookshelf for podcasts and audio. Streaming works with most podcast apps and works inside WireLoft natively.

## Features

* Fully featured, easy-to-use Web UI for navigation and configuration.
* Download series, podcasts, and movies with configurable settings for each.
* Download multiple versions of the same episode automatically. For example, download both a video and an audio version of an episode.
* Download premium episodes and movies using your The Daily Wire subscription.
* Supports audio-only downloads for a podcast-like experience.
* Intelligently helps you avoid downloading the countdown timer shown before live show episodes begin.
* Optionally, delete old show content from your server automatically.
* Create a private RSS feed for a show's episodes for use in your favorite podcast app.

## Running with Docker

The best way to run WireLoft is using its Docker container. Everything is managed for you automatically within the container.

### Quick start: use the published image

Run the following to get started immediately:

```bash
mkdir wireloft && cd wireloft
curl -O https://raw.githubusercontent.com/samuelvisser/wireloft/develop/.docker/docker-compose.yml
docker compose up -d
```

Then open http://localhost:5273.

See **Volumes** and **Useful environment variables** below for persistence and configuration options. Edit the Compose file in place if you want to change anything beyond the defaults.

### Or create the Compose file yourself

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

#### Volumes

* `/config` -- App configuration (`config.yml`), the SQLite database, session secret key, and your Daily Wire login token. Persist this directory so your settings, shows, and login survive container restarts and upgrades.
* `/downloads` -- Downloaded episodes and movies.

#### Useful environment variables

* `TZ` -- Container timezone. Defaults to `UTC`.
* `WL_ADMIN_AUTH__PASSWORD` -- Set this to require a password to access the Web UI. Leave it unset for open access on your local network. Always set this when exposing WireLoft through a reverse proxy.
* `API_URL` -- Override the API base URL given to the Web UI. This defaults to the relative `/api`, which works out of the box regardless of which host port you map.

Literally every setting WireLoft provides can be managed by environment variables, too. However, I generally do not advise
using environment variables for anything but the above examples. Any setting configured by environment variable cannot be changed in the WireLoft UI.

Full documentation for all available settings is a work in progress. For now, just use the UI or check [settings](https://github.com/samuelvisser/wireloft/blob/main/server/config/src/config/settings/settings.py).

## Special thanks

While WireLoft is built entirely from the ground up with original code, the open-source [DailyWirePodcastProxy](https://github.com/fpnewton/DailyWirePodcastProxy) project has helped tremendously in figuring out how The Daily Wire API works. 
DailyWirePodcastProxy allows you to access premium versions of Daily Wire shows directly from your podcast app. Definitely check it out if you're interested!
