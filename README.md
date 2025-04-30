# DailyWire Show Downloader

This is a simple Docker image that is made to download premium shows from the DailyWire website.<br>
Specifically, it is made to be used together with other tools to create a private RSS feed for premium DailyWire Shows.<br>
In no way does this project help pirate premium shows, as it requires an active premium DailyWire account to work.

## Features

- Downloads premium DailyWire shows using your account credentials (via cookies)
- Supports audio-only mode for podcast-like experience
- Downloads video thumbnails and sets them as cover art
- Can extract video descriptions and save them as .nfo files for Audiobookshelf compatibility
- Ensures filenames only use ASCII characters for maximum compatibility
- Configurable download schedule via cron

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
- `output`: Output template for file naming
- `audio_only`: If true, extract audio instead of video
- `audio_format`: Format to encode extracted audio into (e.g., "mp3")
- `save_nfo_file`: If true, save video descriptions as .nfo files for Audiobookshelf
- `shows`: List of shows to download with their names and URLs

### Audiobookshelf Integration

When `save_nfo_file` is enabled, the tool will:
1. Extract video descriptions and metadata using yt-dlp
2. Extract episode titles directly from the video metadata
3. Convert them to .nfo files in XML format with both episode title and description
4. Place the .nfo files alongside the media files

Audiobookshelf will automatically read these .nfo files and include both the titles and descriptions in its RSS feed.

## Build Docker image
docker build -t dailywire-downloader-cron .

docker run -d \
  -v ./config:/config:ro \
  -v ./downloads:/downloads \
  dailywire-downloader-cron

## Using the pre-built image
You can pull the pre-built image from GitHub Container Registry:

```bash
docker pull ghcr.io/samuelvisser/dailywire-downloader:latest

docker run -d \
  -v ./config:/config:ro \
  -v ./downloads:/downloads \
  ghcr.io/samuelvisser/dailywire-downloader:latest
```

### Push new update to github registry (dev only)
echo ACCESS_TOKEN | docker login ghcr.io -u samuelvisser --password-stdin

docker tag dailywire-downloader ghcr.io/samuelvisser/dailywire-downloader:latest

docker push ghcr.io/samuelvisser/dailywire-downloader:latest
