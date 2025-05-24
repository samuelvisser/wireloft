FROM python:3.13-slim

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git \
      ffmpeg \
      cron \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"
ENV PATH="/app/.venv/bin:$PATH"

# Create directories
RUN mkdir -p /downloads /config /usr/local/bin /app/cache /tmp/yt-dlp-tmp \
    && chmod a+rwX /tmp/yt-dlp-tmp /app/cache

# Install the package
COPY pyproject.toml poetry.lock poetry.toml /app/
COPY dailywire_downloader/__init__.py /app/dailywire_downloader/__init__.py
COPY wireloft_web/__init__.py /app/wireloft_web/__init__.py
RUN cd /app && \
    poetry install
ENV DW_CONFIG_FILE="/config/config.yml"
ENV DW_COOKIES_FILE="/config/cookies.txt"
ENV DW_DOWNLOAD_DIR="/downloads"

# Copy remaining package files (we do this here to prevent poetry install from re- running for every change in the package
COPY ./dailywire_downloader/ /app/dailywire_downloader/
COPY ./wireloft_web/ /app/wireloft_web/
COPY ./frontend/ /app/frontend/

# Copy scripts to /usr/local/bin
COPY ./scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*

# Copy the cron‐template
COPY ./cron.d /etc/cron.d
RUN chmod 0644 /etc/cron.d/*

# Ensure cron log exists
RUN touch /var/log/cron.log

# Docker setup
VOLUME ["/config","/downloads"]
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
