FROM python:3.13-slim

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git \
      ffmpeg \
      cron \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Clone yt-dlp + PR #9920, install & add PyYAML
WORKDIR /opt
RUN git clone https://github.com/yt-dlp/yt-dlp.git && \
    cd yt-dlp && \
    git fetch origin pull/9920/head:pr-9920 && \
    git checkout pr-9920 && \
    pip install .

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
RUN cd /app && \
    poetry install
ENV DW_CONFIG_FILE="/config/config.yml"
ENV DW_COOKIES_FILE="/config/cookies.txt"
ENV DW_DOWNLOAD_DIR="/downloads"

# Copy remaining package files (we do this here to prevent poetry install from re- running for every change in the package
COPY ./dailywire_downloader/ /app/dailywire_downloader/

# Copy scripts to /usr/local/bin
COPY ./scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/*

# Copy the cron‐template
COPY ./cron.d /etc/cron.d
RUN chmod 0644 /etc/cron.d/*

# Ensure cron log exists
RUN touch /var/log/cron.log

# Volumes for user‑mounted config & outputs
VOLUME ["/config","/downloads"]

# Entrypoint sets up cron, then CMD runs it
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["sh", "-c", "cron -f & tail -f /var/log/cron.log"]