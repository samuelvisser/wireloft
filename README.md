# DailyWire Show Downloader

This is a simple Docker image that is made to download premium shows from the DailyWire website.<br>
Specifically, it is made to be used together with other tools to create a private RSS feed for premium DailyWire Shows.<br>
In no way does this project help pirate premium shows, as it requires an active premium DailyWire account to work.

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