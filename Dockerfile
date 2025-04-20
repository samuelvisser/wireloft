FROM python:3.10-slim

# 1. System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      git \
      ffmpeg \
      cron \
    && rm -rf /var/lib/apt/lists/*

# 2. Clone yt-dlp + PR #9920, install & add PyYAML
WORKDIR /opt
RUN git clone https://github.com/yt-dlp/yt-dlp.git && \
    cd yt-dlp && \
    git fetch origin pull/9920/head:pr-9920 && \
    git checkout pr-9920 && \
    pip install . && \
    pip install pyyaml

# 3. Create directories
RUN mkdir -p /downloads /config /usr/local/bin

# 4. Copy in our scripts
COPY ./scripts/ /usr/local/bin/
RUN chmod +x /usr/local/bin/download.sh /usr/local/bin/entrypoint.sh

# 5. Copy the cron‐template
COPY dailywire.cron.template /etc/cron.d/dailywire.cron.template
RUN chmod 0644 /etc/cron.d/dailywire.cron.template

# 6. Ensure cron log exists
RUN touch /var/log/cron.log

# 7. Volumes for user‑mounted config & outputs
VOLUME ["/config","/downloads"]

# 8. Entrypoint sets up cron, then CMD runs it
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["cron", "-f"]