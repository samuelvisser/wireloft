# WireLoft

WireLoft is a self-hosted app for downloading shows from The Daily Wire website.
Its designed to be easy to use. You just add a Daily Wire show, and it'll make sure you always have the 
latest episodes locally available. Additionally, it supports downloading the premium version of shows behind the paywall, 
as long as you have a Daily Wire premium subscription.
WireLoft is perfect for those who want to consume Daily Wire content through their media server (Plex, Jellyfin, Audiobookshelf)
or who just want the content available locally.<br>

This project was inspired by [Pinchflat](https://github.com/kieraneglin/pinchflat).
Pinchflat is an awesome project that allows you to automatically download videos from YouTube channels or playlists.
WireLoft takes that concept to The Daily Wire. Additionally, WireLoft also allows downloading individual episodes and
movies, making it truly a one-stop-shop for all things Daily Wire.<br>

The project has also taken inspiration from [DailyWirePodcastProxy](https://github.com/fpnewton/DailyWirePodcastProxy).
This is another great project that allows you to stream Daily Wire premium shows directly to your podcast client.
With WireLoft, this same result can be achieved by downloading audio-only versions of a show to a media
server like Audiobookshelf and making it generate an RSS feed for you. In some situations this leads to a more stable
experience as the audio files are not being streamed from the Daily Wire directly, but from a local server.
This is actually the main use-case WireLoft was originally designed for. Support for generating an RSS feed
directly from WireLoft, like Pinchflat also does, is planned for a future release.

The project uses a specific [pull request](https://github.com/yt-dlp/yt-dlp/pull/9920) to yt-dlp that adds support for downloading 
shows and movies from Daily Wire. We will implement an in-house downloader inside WireLoft in a future release, as the API this
pull requests uses seems to be deprecated: official Daily Wire apps moved on to a new Middleware API. WireLoft already uses that
Middleware API to get metadata: soon it will also use it to download episodes.

## Features

- Fully-featured easy to use web UI for navigation and configuration
- Downloads series and podcasts with configurable parameters for each
- Downloads the premium version of episodes using your account credentials
- Supports audio-only mode for a podcast-like experience
- Downloads video thumbnails and sets them as cover art

## Planned

- Support for downloading movies and standalone episodes
- Possible support for Bentkey: feasibility not yet known

## Building your own Docker image
If you want to build the image yourself:

```bash
docker build -t dailywire-downloader .

docker run -d \
  -v $(pwd)/config:/config:ro \
  -v $(pwd)/downloads:/downloads \
  --name dailywire-downloader \
  dailywire-downloader
```

## Development
## UI (React 19, Vite + TypeScript)

A web UI is included for navigation and demonstration purposes. It now uses a proper build step so you can write JSX and TypeScript.

### Develop (recommended)
Bash:
```bash
cd <PROJECT_DIR>\wireloft\ui
npm install
npm run dev
```
Open the URL shown by Vite (usually http://localhost:5173/). Edits to `.tsx` and `.css` files hot‑reload.

### Build for production
```bash
cd <PROJECT_DIR>\wireloft\ui
npm run build
```

# Dev backend
A simple backend is included and reads its data from the SQLite database.
Run the backend (in repo root):

```bash
uv sync
backend-api --debug
```

This starts Flask at http://127.0.0.1:5001

Run the React UI (in ui/):

```bash
npm install
npm run dev
```

# Dailywire API
## DailyWire API CLI

You can list episodes for a DailyWire show using the dailywire-api helper.

Example (bash):
```bash
dailywire-api show list --slug the-ben-shapiro-show
```

Options:
- --all: include all episodes by following seasons and pagination
- --json: output JSON instead of plain lines
- --access-token <JWT>: optional bearer token for premium content
- --membership-plan <PLAN>: optional membership plan (e.g., AllAccess)

# Database (SQLite)

This project includes a required SQLite database for the backend.
- Default DB path: data\wireloft.db

### Create and seed the database 

Bash (repo root):
```bash
# Create database and tables
backend-api --init-db

# Seed database with the same demo data currently hardcoded in the backend
backend-api --seed-db

# Use a custom database path
backend-api --init-db --db <DATA_DIR>\data\wireloft.db
backend-api --seed-db --db <DATA_DIR>\data\wireloft.db
```

Notes:
- Seeding is idempotent: running it multiple times won’t duplicate rows.