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
Add a Stream Profile to any show and WireLoft generates a private RSS feed URL you can paste straight into your podcast app -
no third-party server needed to turn locally downloaded files into a feed.<br>

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
- Open a private RSS feed of a show's downloaded episodes for use in any podcast app, via Stream Profiles (see below)

### Planned

- Support for downloading movies and standalone episodes (coming soon!)
- Maybe: support for Bentkey - feasibility not yet known (if anyone knows how their API works, please let me know!)
- Maybe: support for browsing series- and movies not yet downloaded inside WireLoft (add them to WireLoft without a URL)

### Running with Docker
The included Docker setup builds the React UI and the FastAPI backend into a
single image. One container serves the web UI, the API, and the background
scheduler/downloader -- everything starts automatically, and the SQLite
database is created (and migrated) on first boot if it doesn't already exist.

Building the UI needs your own Font Awesome Pro credentials: create
`ui/.npmrc` (never committed, see `ui/.gitignore`) with the same npm auth
token you use for local development, e.g.:

```
@awesome.me:registry=https://npm.fontawesome.com/
//npm.fontawesome.com/:_authToken=<your token>
```

The build reads it as a [BuildKit secret](https://docs.docker.com/build/building/secrets/)
mounted only into the `npm ci` step -- it's never copied into the build
context or baked into any image layer, so the published image stays safe to
make public.

Using Docker Compose (recommended -- already wired to `ui/.npmrc` as a
build secret):

```bash
docker compose up -d --build
```

Then open http://localhost:8080.

Or with plain `docker`:

```bash
docker build -t wireloft -f .docker/Dockerfile . \
  --secret id=npmrc,src=ui/.npmrc

docker run -d \
  -p 8080:80 \
  -v $(pwd)/config:/config \
  -v $(pwd)/downloads:/downloads \
  -e TZ=Europe/Amsterdam \
  --name wireloft \
  wireloft
```

Volumes:
- `/config` -- app config (`config.yml`), the SQLite database, the session
  secret key, and your DailyWire login token. Persist this so settings, shows,
  and your login survive container restarts/upgrades.
- `/downloads` -- downloaded episodes/movies.

Useful environment variables:
- `TZ` -- container timezone (default `UTC`).
- `WL_ADMIN_AUTH__PASSWORD` -- set this to require a login to access the UI.
  Leave unset for open access on your local network.
- `API_URL` -- override the API base URL the UI is told to use (defaults to
  the relative `/api`, which works out of the box regardless of which host
  port you map).

### Publishing a release image
`./deploy.sh [tag]` builds the image (same as above, `ui/.npmrc` required)
and pushes it to `ghcr.io/samuelvisser/wireloft`, tagged `latest` by default
or with `tag` (e.g. `./deploy.sh v1.2.0`) plus `latest`.

It needs a GitHub personal access token with `write:packages` scope to log
in to ghcr.io, picked up in order from: the `GHCR_TOKEN` env var, a local
token file (default `~/.config/wireloft/ghcr_token`, override with
`$GHCR_TOKEN_FILE`), or an interactive hidden prompt as a last resort --
which then offers to save it to that file (created with permissions
restricted to your user only) so later runs don't ask again. The token is
never passed as a CLI argument and never printed.

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


## Podcast RSS feeds

Add a Stream Profile (of type RSS) to a show and WireLoft generates a feed URL for you automatically -
paste it into your podcast app and go. The URL can be freely edited afterwards (e.g. if you access WireLoft
through a different hostname than the one WireLoft guessed), and can be regenerated at any time from the
profile's edit page, which immediately invalidates the old URL.

The feed only lists episodes for which a matching downloaded file exists (per the profile's preferred format
and "require exact match" setting); streaming episodes straight from Daily Wire when no download exists yet is
planned but not implemented yet.

Feed URLs (and the media files they link to) are served without going through WireLoft's own login: each
profile's URL contains a long, unguessable secret token, so the feed keeps working for your podcast app even
when local authentication is enabled for the web UI - similar to how [Pinchflat handles this](https://github.com/kieraneglin/pinchflat/wiki/Podcast-RSS-Feeds).
Treat a feed URL like a password: anyone who has it can stream (and see the titles/descriptions of) that
show's downloaded episodes.

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
- The provided image already persists this for you: the auto-generated key
  and the database both live under `/config`, which `docker-compose.yml` maps
  to `./config` on the host. Nothing extra to configure.
