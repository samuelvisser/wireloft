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

## Quick Start

### Using Docker

1. Create configuration directory and files:
   ```bash
   mkdir -p config downloads
   cp /path/to/repo/config/config.yml.default config/config.yml
   cp /path/to/repo/config/cookies.txt.default config/cookies.txt
   ```

2. Edit the configuration files with your settings and cookies

3. Run the Docker container:
   ```bash
   docker run -d \
     -v $(pwd)/config:/config:ro \
     -v $(pwd)/downloads:/downloads \
     ghcr.io/samuelvisser/dailywire-downloader:latest
   ```

### Using Python Package

0. Install Poetry if not already installed:
   ```bash
   # Linux, macOS
   curl -sSL https://install.python-poetry.org | python3 -
   
   # Windows
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
   ```

1. Install the package:
   ```bash
   cd /path/to/repo
   poetry install
   ```

2. Set up your configuration files:
   ```bash
   mkdir -p config
   cp /path/to/repo/config/config.yml.default config/config.yml
   cp /path/to/repo/config/cookies.txt.default config/cookies.txt
   ```

3. Edit the configuration files with your settings and cookies

4. Run the downloader:
   ```bash
   dailywire-downloader
   ```
   By default, it will try to get the config and cookies files at `$(pwd)/config/`

You can specify custom paths for the configuration, cookies, and download directory:
```bash
dailywire-downloader --config /path/to/config.yml --cookies /path/to/cookies.txt --download-dir /path/to/download_dir
```

## Configuration

Copy the default configuration files and customize them:

```bash
cp config/config.yml.default config/config.yml
cp config/cookies.txt.default config/cookies.txt
```

### Configuration Options

In `config.yml`, you can set the following options:

- `schedule`: Cron schedule for automated downloads
- `start_date`: Only download episodes published on or after this date (YYYY-MM-DD)
- `output`: Output template for file naming. See [here](https://github.com/yt-dlp/yt-dlp/tree/311bb3b?tab=readme-ov-file#output-template) for possible values
- `audio_only`: If true, extract audio instead of video
- `audio_format`: Format to encode extracted audio into (e.g., "mp3"). Ignored if `audio_only` is false
- `save_nfo_file`: If true, save video descriptions and other metadata as .nfo files for Media Servers to read (e.g. Audiobookshelf, Jellyfin, ect). Note: metadata is additionally embedded in the media file, making the nfo file in most cases redundant
- `retry_download_all`: If false, stop downloading when an already downloaded video is encountered. If true, it will attempt to re-download every episode which is useful if some older episodes where not correctly downloaded on an earlier run
- `shows`: List of shows to download with their names and URLs. Additionally, you can add any setting except the schedule for a specific show, allowing granular control over how exactly shows are downloaded

#### Filters
Further, you can also set various filters either globally or per show
```yaml
    filters:
      matchtitle: '\[Member Exclusive\]'
      rejecttitle: 'Sunday Special'
      filters: []
      breaking_filters: []
```
- `matchtitle`: regex to filter all episode titles by. In above example, only episodes that contain "[Member Exclusive]"" in their title will be downloaded
- `rejecttitle`: regex to filter all episode titles by. In above example, only episodes that DO NOT contain "Sunday Special" in their title will be downloaded
- `filters`: array of filters to apply. Any "OUTPUT TEMPLATE" field can be compared with a number or a string. For options, see [here](https://github.com/yt-dlp/yt-dlp/tree/311bb3b?tab=readme-ov-file#video-selection) and look for `--match-filters`
- `breaking_filters`: array of breaking filters to apply. These filters will stop the show download if they match. For options, see [here](https://github.com/yt-dlp/yt-dlp/tree/311bb3b?tab=readme-ov-file#video-selection) and look for `--break-match-filters`

#### Cookies
To download premium DailyWire shows, you will need to export your browser cookies for `dailywire.com`

* Install in your browser an extension to extract cookies:
  * [Firefox](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)
  * [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
* Extract the cookies you need with the extension and rename the file `cookies.txt`
* Drop the file in the folder you configured
* Restart the container

### Command-line Arguments and Environment Variables

The downloader supports the following command-line arguments:

- `--config`: Path to the configuration file (default: `/config/config.yml` or `$DW_CONFIG_FILE` env var)
- `--cookies`: Path to the cookies file (default: `/config/cookies.txt` or `$DW_COOKIES_FILE` env var)
- `--download-dir`: Path to the download directory (default: `/downloads` or `$DW_DOWNLOAD_DIR` env var)

You can also set these paths using environment variables:

- `DW_CONFIG_FILE`: Path to the configuration file
- `DW_COOKIES_FILE`: Path to the cookies file
- `DW_DOWNLOAD_DIR`: Path to the download directory

## Docker Usage Details

### Using the pre-built image
The easiest way to get started is to use the pre-built image from GitHub Container Registry:

```bash
docker pull ghcr.io/samuelvisser/dailywire-downloader:latest

docker run -d \
  -v $(pwd)/config:/config:ro \
  -v $(pwd)/downloads:/downloads \
  --name dailywire-downloader \
  ghcr.io/samuelvisser/dailywire-downloader:latest
```

### How the Docker container works
When the container starts:
1. It immediately runs a download job for all configured shows
2. It sets up a cron job based on the schedule in your config.yml
3. The cron job will run the downloader according to your schedule

### Viewing logs
To view the logs from the Docker container:
```bash
docker logs -f dailywire-downloader
```

### Running a manual download
To trigger a download manually:
```bash
docker exec dailywire-downloader dailywire-downloader
```

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

## Development

This project uses [Poetry](https://python-poetry.org/) for dependency management.

### Setup for Development

1. Clone the repository:
   ```bash
   git clone https://github.com/samuelvisser/dailywire-show-download.git
   cd dailywire-show-download
   ```

2. Install Poetry:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. Install dependencies:
   ```bash
   poetry install
   ```

4. Set up your configuration files:
   ```bash
   cp config/config.yml.default config/config.yml
   cp config/cookies.txt.default config/cookies.txt
   ```

5. Edit the configuration files with your settings and cookies

### Running the Downloader in Development Mode

Run the downloader using Poetry:
```bash
poetry run dailywire-downloader
```

Or activate the Poetry virtual environment and run directly:
```bash
poetry shell
dailywire-downloader
```

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





# Backend for playlist


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