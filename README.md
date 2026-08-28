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
- Repackages downloaded video into `.mp4` instead of raw `.ts` (requires [ffmpeg](https://ffmpeg.org/) on PATH; controlled by the `downloadSettings.remuxVideoToMp4` / `downloadSettings.ffmpegPath` configuration fields, on by default)

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
backend-api run --debug
```

This starts the backend API at http://127.0.0.1:5001

Run the React UI (in ui/):

```bash
npm install
npm run dev
```

### Automated tests

The default backend suite is isolated from both the live Daily Wire API and
`data/wireloft.db`. Install the development dependency group and run it from
the repository root:

```bash
uv sync --group dev
uv run pytest
```

Network sockets are disabled during this suite. Requests in `tests/rest` are
manual integration aids and require an access token supplied through a private
JetBrains HTTP Client environment file.

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
- Default DB path: data/wireloft.db

#### Create and seed the database

Bash (repo root):
```bash
# Create database and tables
backend-api db init

# Seed database with demo data
backend-api db seed

# Use a custom database path
backend-api db init --db <DATA_DIR>/data/wireloft.db
backend-api db seed --db <DATA_DIR>/data/wireloft.db
```

#### Backend API commands

```bash
# Start backend server (development mode with auto-reload)
backend-api run --debug

# Start backend server (production mode)
backend-api run

# Start on custom host/port
backend-api run --host 0.0.0.0 --port 8000

# Stop all running backend processes
backend-api stop
```

Notes:
- Database seeding is idempotent: running it multiple times won't duplicate rows.


## Authentication and session persistence

When logging in, if you see a message like:

WL_SECRET_KEY not set; generating ephemeral key for this process. Tokens will not persist across restarts.

It means the application did not find a secret key to encrypt/decrypt your session cookies. A new, in-memory key was generated for that process only. If the process restarts, that key is lost and existing logins become invalid.

How to persist logins safely:

- Option A: Set WL_SECRET_KEY (recommended for non-Docker setups)
  - Generate a Fernet key once and keep it safe:
    - Python: python - <<'PY'\nfrom cryptography.fernet import Fernet\nprint(Fernet.generate_key().decode())\nPY
  - Put the printed value into your environment (or .env) as WL_SECRET_KEY=... and restart the app.

- Option B: Point to a key file with WL_SECRET_KEY_FILE (great for Docker/Kubernetes secrets)
  - Store the key string (from Option A) in a file readable by the app, and set WL_SECRET_KEY_FILE to that path.
  - Example .env:
    - WL_SECRET_KEY_FILE=./data/wl_secret.key

- Option C: Do nothing (auto-persist default)
  - If neither WL_SECRET_KEY nor WL_SECRET_KEY_FILE is set, WireLoft will now automatically create a persistent key file at data/wl_secret.key on first run and reuse it thereafter. Ensure your data/ directory is persisted across restarts (e.g., bind mounted as a Docker volume) so logins survive container restarts.

Security notes:
- Keep your secret key private. Anyone with this key can forge session cookies.
- Rotating the key will immediately invalidate all existing sessions. To rotate, replace the key (env or file) and restart the app.
- File permissions are set to 600 when possible.

Docker tip:
- Make sure the data directory is mapped to a persistent volume, so the auto-generated key and the database persist:
  - volumes:
    - ./data:/app/data
