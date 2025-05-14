> This project was made primarily for personal use. Im sharing it publicly in the hopes it might be useful to some. If you run into issues, let me know, but I might not always respond very quickly 

# DailyWire Show Downloader

This is a simple Docker image made to download premium shows from the DailyWire website.<br>
Specifically, it is made to be used together with other tools to create a private RSS feed for premium DailyWire Shows.<br>
In no way does this project help pirate premium shows, as it requires an active premium DailyWire account to work.

## Features

- Downloads premium DailyWire shows using your account credentials (via cookies)
- Supports audio-only mode for podcast-like experience
- Downloads video thumbnails and sets them as cover art
- Can extract video descriptions and save them as .nfo files for Audiobookshelf compatibility
- Ensures filenames only use ASCII characters for maximum compatibility
- Configurable download schedule via cron
- Displays cron job logs in the console for easy monitoring

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
- `save_nfo_file`: If true, save video descriptions and other metadata as .nfo files for Audiobookshelf
- `retry_download_all`: If false, stop downloading when an already downloaded video is encountered
- `shows`: List of shows to download with their names and URLs

### Audiobookshelf Integration

When `save_nfo_file` is enabled, the tool will:
1. Extract video descriptions and metadata using yt-dlp
2. Extract episode titles directly from the video metadata
3. Convert them to .nfo files in XML format with both episode title and description
4. Place the .nfo files alongside the media files

Audiobookshelf will automatically read these .nfo files and include both the titles and descriptions in its RSS feed.

### Command-line Arguments and Environment Variables

The downloader supports the following command-line arguments:

- `--config`: Path to the configuration file (default: `/config/config.yml` or `$DW_CONFIG_FILE` env var)
- `--cookies`: Path to the cookies file (default: `/config/cookies.txt` or `$DW_COOKIES_FILE` env var)
- `--download-dir`: Path to the download directory (default: `/downloads` or `$DW_DOWNLOAD_DIR` env var)

You can also set these paths using environment variables:

- `DW_CONFIG_FILE`: Path to the configuration file
- `DW_COOKIES_FILE`: Path to the cookies file
- `DW_DOWNLOAD_DIR`: Path to the download directory

## Development

This project uses [Poetry](https://python-poetry.org/) for dependency management.

### Setup for Development

1. Install Poetry:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Run the downloader:
   Run simply like so. Make sure config.yml and cookies.txt are available at $(pwd)/config/
   ```bash
   dailywire-downloader
   ```

   Additionally, you can specify custom paths for the configuration and cookies files:
   ```bash
   dailywire-downloader --config /path/to/config.yml --cookies /path/to/cookies.txt --download-dir /path/to/download_dir
   ```

## Build Docker image

```bash
docker build -t dailywire-downloader .

docker run -d \
  -v ./config:/config:ro \
  -v ./downloads:/downloads \
  dailywire-downloader
```

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
```bash
docker build -t dailywire-downloader .

echo ACCESS_TOKEN | docker login ghcr.io -u samuelvisser --password-stdin

docker tag dailywire-downloader ghcr.io/samuelvisser/dailywire-downloader:latest

docker push ghcr.io/samuelvisser/dailywire-downloader:latest
```


    --min-sleep-interval 10 --max-sleep-interval 25 

    --parse-metadata "description:(?s)(?P<meta_comment>.+)" --parse-metadata "title:(?P<meta_title>.+?)(?:\s+\[Member Exclusive\])?$" --parse-metadata "title:(?:Ep\.\s+(?P<meta_movement>\d+))?.*" --parse-metadata "title:(?:Ep\.\s+(?P<meta_track>\d+))?.*" --parse-metadata "playlist_title:(?P<meta_album>.+)" --parse-metadata "playlist_title:(?P<meta_series>.+)" --parse-metadata "upload_date:(?P<meta_date>\d{8})$" --replace-in-metadata "meta_date" "(.{4})(.{2})(.{2})" "\1-\2-\3" --parse-metadata "upload_date:(?P<meta_year>.{4}).*" 
