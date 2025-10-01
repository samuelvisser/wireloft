> This version of WireLoft is currently in active development. If you want to download Daily Wire shows, use the version in the master branch. 
> You can see a sneak peak of what is to come in the next version of WireLoft here, though!

# WireLoft

### What it does
WireLoft is a self-hosted app for downloading (premium) shows from The Daily Wire.
WireLoft is easy to install and use. Just launch the docker container, open the Web-UI and add any Daily Wire show. 
WireLoft will download as many episodes as is your preference and will download new episodes as soon as they are available. 
Once setup, WireLoft will handle it all for you. Additionally, it supports downloading the premium version of shows behind the paywall, 
as long as you have a Daily Wire premium subscription. WireLoft is perfect for those who want to consume Daily Wire content 
through their media server (Plex, Jellyfin, Audiobookshelf) or who just want the content available locally.<br>

WireLoft is also great if your goal is to listen to premium versions of the Daily Wire podcasts in your favorite Podcast app. 
We plan on supporting creating an RSS feed directly from WireLoft to consume in your podcast app. 
Currently, you will need a third party server like Audiobookshelf to generate an RSS feed from locally available files.<br>

This project was inspired by [Pinchflat](https://github.com/kieraneglin/pinchflat).
Pinchflat is an awesome project that allows you to automatically download videos from YouTube channels or playlists.
WireLoft takes that concept to The Daily Wire. Additionally, WireLoft allows downloading individual episodes and movies (coming soon!), 
making it truly a one-stop-shop for all things Daily Wire.<br>

The project uses a specific [pull request](https://github.com/yt-dlp/yt-dlp/pull/9920) to yt-dlp that adds support for downloading 
shows and movies from Daily Wire. We will implement an in-house downloader inside WireLoft in a future release, as the API this
pull requests uses seems to be deprecated: official Daily Wire apps moved on to a new Middleware API. WireLoft already uses that
Middleware API to get metadata: soon it will also use it to download episodes.<br>

WireLoft is not meant to be used for consuming the content, it just downloads it. For consuming the downloaded content 
use a self-hosted media server like Plex or Jellyfin for series, or Audiobookself for podcasts.

### Features

- Fully-featured easy-to-use web UI for navigation and configuration
- Downloads series and podcasts with configurable parameters for each
- Download multiple versions of the same episode, automatically. For example, download both a video and audio version of the episode
- Download the premium version of episodes using your account credentials
- Supports audio-only mode for a podcast-like experience
- Downloads video thumbnails and sets them as cover art in the media items
- Intelligently helps you avoid downloading the countdown timer shown in live versions of show episodes
- Optionally automatically delete old content

### Planned

- Support for downloading movies and standalone episodes (coming soon!)
- Maybe: support for Bentkey - feasibility not yet known (if anyone knows how their API works, please let me know!)
- Maybe: support for browsing series- and movies not yet downloaded inside WireLoft (add them to WireLoft without a URL)

### Building your own Docker image
If you want to build the image yourself:

```bash
docker build -t dailywire-downloader .

docker run -d \
  -v $(pwd)/config:/config:ro \
  -v $(pwd)/downloads:/downloads \
  --name dailywire-downloader \
  dailywire-downloader
```

### Special thanks
While WireLoft is fully build from the ground up with original code, the open source [DailyWirePodcastProxy](https://github.com/fpnewton/DailyWirePodcastProxy) project has helped 
tremendously in figuring out how the Daily Wire API works. DailyWirePodcastProxy enables you to download premium versions of the shows 
directly from The Daily Wire to your podcast app. Definitely check it out if you’re interested!

## Development
### UI (React 19, Vite + TypeScript)

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

### Dev backend
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

### Dailywire API
#### DailyWire API CLI

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

### Database (SQLite)

This project includes a required SQLite database for the backend.
- Default DB path: data\wireloft.db

#### Create and seed the database 

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
