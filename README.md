> This project was made primarily for personal use. Im sharing it publicly in the hopes it might be useful to some. If you run into issues, let me know, but I might not always respond very quickly 

# WireLoft

This is a project made to download premium shows and movies from The Daily Wire website using browser cookies.<br>
For this to work, an active premium subscription to The Daily Wire is required.

My main personal use for this is to download the episodes to a directory read by my Audiobookshelf instance, which I then use to create a private RSS feed from the episodes.

The project uses a specific [pull request](https://github.com/yt-dlp/yt-dlp/pull/9920) to yt-dlp that adds support for downloading premium episodes and entire shows at once. This project is a wrapper around that pull request to yt-dlp and adds some convenient features.

## Features

- Downloads premium DailyWire shows using your account credentials (via cookies)
- Supports audio-only mode for podcast-like experience
- Downloads video thumbnails and sets them as cover art
- Can extract video descriptions and save them as .nfo files for Media Servers
- Ensures filenames only use ASCII characters for maximum compatibility
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

- Location: `ui` (Vite project)
- Entry HTML: `ui\index.html` (Vite-style, loads `/src/main.tsx`)
- Source: `ui\src\**/*` (TypeScript + JSX)
- Features:
  - Sidebar with: Home, Media Profiles, and Settings
  - Sidebar footer branding: WireLoft

### Prerequisites
- Node.js 18+ and npm

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

### Notes
- Legacy buildless files have been removed; the UI now exclusively uses the Vite + TypeScript setup.
- The UI is still standalone and does not currently interact with the Python backend. It’s intended as a foundation you can extend.

# Dev backend (Flask) + UI

A simple Flask backend is included to serve the UI with hardcoded media profiles.

Run the backend (in repo root):

```
poetry install
poetry run backend-api
```

This starts Flask at http://127.0.0.1:5000 with endpoints:
- GET /api/health
- GET /api/media-profiles

Run the React UI (in ui/):

```
npm install
npm run dev
```

The UI will fetch media profiles from http://localhost:5000/api/media-profiles.





# Dailywire API
python -m dailywire_api --help







--lazy-playlist
Immediately receive playlist items

--skip-download
 Do not download the video but write all related files

--simulate
 Do not download the video and do not write anything to disk

--ignore-no-formats-error
Ignore "No video formats" error. Useful for extracting metadata even if the videos are not actually available for download

--print
Field name or output template to print to screen, optionally prefixed with when to print it, separated by a ":". 
Supported values of "WHEN" are the same as that of --use-postprocessor (default: video). 
Implies --quiet. Implies --simulate unless --no-simulate or later stages of WHEN are used. This option can be used multiple times

--progress                      
Show progress bar, even if in quiet mode


--print title
--print upload_date
--print live_status




yt-dlp --lazy-playlist --simulate --ignore-no-formats-error --sleep-requests 2 https://www.dailywire.com/show/the-ben-shapiro-show



yt-dlp --simulate --progress --ignore-no-formats-error --sleep-requests 2 --print title --print upload_date --print live_status https://www.dailywire.com/show/the-ben-shapiro-show



yt-dlp --simulate --progress --ignore-no-formats-error --sleep-requests 2 https://www.dailywire.com/show/the-ben-shapiro-show


## DailyWire API CLI

You can list episodes for a DailyWire show using the dailywire-api helper.

Examples (PowerShell):

- dailywire-api show list --slug the-ben-shapiro-show
- python -m dailywire_api show list --slug the-ben-shapiro-show

Options:
- --all: include all episodes by following seasons and pagination
- --json: output JSON instead of plain lines
- --access-token <JWT>: optional bearer token for premium content
- --membership-plan <PLAN>: optional membership plan (e.g., AllAccess)

Backward compatibility (deprecated):
- python -m dailywire_api --show the-ben-shapiro-show
