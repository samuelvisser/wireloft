> This project was made primarily for personal use. Im sharing it publicly in the hopes it might be useful to some. If you run into issues, let me know, but I might not always respond very quickly 

# WireLoft

This is a project made to download premium shows and movies from The Daily Wire website using browser cookies.<br>
For this to work, an active premium subscription to The Daily Wire is required.

My main personal use for this is to download the episodes to a directory read by my Audiobookshelf instance, which I then use to create a private RSS feed from the episodes.

The project uses a specific [pull request](https://github.com/yt-dlp/yt-dlp/pull/9920) to yt-dlp that adds support for downloading premium episodes and entire shows at once. This project is a wrapper around that pull request to yt-dlp and adds some convenient features.

## Features

Currently, this project is made only to download episodes from DailyWire podcasts and is therefore only really useful
for people who have a DailyWire premium subscription, as downloading free versions of the episodes is already straightforward with
any RSS app. Where this project shines is in the ability to download premium versions of the shows and consume those in your RSS app.<br><br>

I am planning to add support for downloading other shows and movies as well. 
Anything that is free on DailyWire is downloadable using this project even without a subscription, so in the future this project
will also be useful for users without a DailyWire subscription.

- Fully-featured web UI for navigation and configuration
- Downloads premium DailyWire shows using your account credentials
- Supports audio-only mode for podcast-like experience
- Downloads video thumbnails and sets them as cover art
- Configurable download schedule via cron

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
### Push new update to github registry (dev only)
```bash
docker build -t dailywire-downloader .

echo ACCESS_TOKEN | docker login ghcr.io -u samuelvisser --password-stdin

docker tag dailywire-downloader ghcr.io/samuelvisser/dailywire-downloader:latest

docker push ghcr.io/samuelvisser/dailywire-downloader:latest
```

## UI (React 19, Vite + TypeScript)

A web UI is included for navigation and demonstration purposes. It now uses a proper build step so you can write JSX and TypeScript.

### Develop (recommended)
PowerShell:
```powershell
cd C:\Users\samuv\PycharmProjects\wireloft\ui
npm install
npm run dev
```
Open the URL shown by Vite (usually http://localhost:5173/). Edits to `.tsx` and `.css` files hot‑reload.

### Build for production
```powershell
cd C:\Users\samuv\PycharmProjects\wireloft\ui
npm run build
```
The static site will be in `ui\dist`. You can preview it locally:
```powershell
npm run preview
```

### Formatting
Run Prettier across the UI project:
```powershell
cd C:\Users\samuv\PycharmProjects\wireloft\ui
npm run format
```

# Dev backend (Flask) + UI
A simple Flask backend is included and reads its data from the required SQLite database.
Run the backend (in repo root):

```
uv sync
backend-api
```

This starts Flask at http://127.0.0.1:5000 with endpoints:
- GET /api/media-profiles
- GET /api/shows
- GET /api/shows/<slug>
- GET /api/shows/<slug>/episodes
- GET /api/shows/<slug>/episodes/<episode_slug>
- GET /api/health

Run the React UI (in ui/):

```
npm install
npm run dev
```

The UI will fetch media profiles from http://localhost:5000/api/media-profiles.

# Dailywire API
## DailyWire API CLI

You can list episodes for a DailyWire show using the dailywire-api helper.

Example (PowerShell):
- dailywire-api show list --slug the-ben-shapiro-show

Options:
- --all: include all episodes by following seasons and pagination
- --json: output JSON instead of plain lines
- --access-token <JWT>: optional bearer token for premium content
- --membership-plan <PLAN>: optional membership plan (e.g., AllAccess)

## Database (SQLite)

This project includes a required SQLite database for the backend.

- Default DB path: data\wireloft.db

### Create and seed the database 
These scripts only run when you call them explicitly. They do nothing during normal server start.

PowerShell (repo root):

```powershell
# Create database and tables
backend-api --init-db

# Seed database with the same demo data currently hardcoded in the backend
backend-api --seed-db

# Use a custom database path
backend-api --init-db --db C:\Users\samuv\PycharmProjects\wireloft\data\wireloft.db
backend-api --seed-db --db C:\Users\samuv\PycharmProjects\wireloft\data\wireloft.db
```

Notes:
- Seeding is idempotent: running it multiple times won’t duplicate rows.
