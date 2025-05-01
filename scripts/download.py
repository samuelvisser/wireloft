#!/usr/bin/env python3
import os
import sys
import yaml
import subprocess
import time
import fcntl
import datetime
import re

# === Constants ===
DOWNLOAD_DIR = "/downloads"
TMP_DIR = "/tmp/yt-dlp-tmp"
ARCHIVE_FILE = f"{DOWNLOAD_DIR}/downloaded.txt"
COOKIES_FILE = os.environ.get("COOKIES_FILE", "/config/cookies.txt")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "/config/config.yml")
LOCKFILE = "/tmp/download.lock"

def log(message):
    """Print a timestamped log message."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp}: {message}")

def acquire_lock():
    """Prevent overlapping runs using file locking."""
    try:
        lock_fd = open(LOCKFILE, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except IOError:
        log("Another download.py is still running; exiting.")
        sys.exit(0)

def verify_prerequisites():
    """Verify that all required files and directories exist."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    
    # Create archive file if it doesn't exist
    if not os.path.exists(ARCHIVE_FILE):
        open(ARCHIVE_FILE, 'a').close()
    
    # Check for required files
    if not os.path.isfile(COOKIES_FILE):
        log(f"ERROR: Cookies file missing at {COOKIES_FILE}")
        sys.exit(1)
    
    if not os.path.isfile(CONFIG_FILE):
        log(f"ERROR: Config file missing at {CONFIG_FILE}")
        sys.exit(1)

def load_config():
    """Load configuration from YAML file."""
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def get_date_filter(config):
    """Get date filter arguments based on start_date in config."""
    start_date = config.get("start_date", "").strip()
    if start_date:
        clean_date = start_date.replace('-', '')
        return ["--dateafter", clean_date, "--break-match-filters", f"upload_date>={clean_date}"]
    return []

def get_audio_flags(config):
    """Get audio-related flags based on config."""
    audio_only = config.get("audio_only", False)
    audio_format = config.get("audio_format", "")
    
    if audio_only:
        flags = ["-x"]
        if audio_format:
            flags.extend(["--audio-format", audio_format])
        return flags
    return []

def get_nfo_flags(config):
    """Get NFO-related flags based on config."""
    save_nfo = config.get("save_nfo_file", False)
    
    if save_nfo:
        nfo_info_flag = ["--write-info-json", "--paths", f"infojson:{TMP_DIR}"]
        nfo_script_file = "/usr/local/bin/create_nfo.py"  # Updated to use Python script
        exec_flag = ["--exec", f"{nfo_script_file} %(filepath)q {TMP_DIR}"]
        return nfo_info_flag, exec_flag
    return [], []

def get_retry_flags(config):
    """Get retry-related flags based on config."""
    retry_download_all = config.get("retry_download_all", True)
    
    if not retry_download_all:
        return ["--break-on-existing"]
    return ["--sleep-requests", "0.75"]

def download_show(show_name, show_url, config, date_filter, audio_flags, nfo_info_flag, exec_flag, retry_flag):
    """Download a single show using yt-dlp."""
    log(f"Downloading '{show_name}' from {show_url}")
    
    output_template = config.get("output")
    if not output_template:
        log("ERROR: `output` key missing in config.yml")
        sys.exit(1)
    
    cmd = [
        "yt-dlp",
        "--cookies", COOKIES_FILE,
        "--download-archive", ARCHIVE_FILE,
        "--paths", f"temp:{TMP_DIR}",
        "--paths", f"home:{DOWNLOAD_DIR}",
        "--cache-dir", "/app/cache",
        "--no-part",
        "--windows-filenames",
        "--embed-metadata",
        "--parse-metadata", "description:(?s)(?P<meta_comment>.+)",
        "--parse-metadata", "title:(?P<meta_title>.+?)(?:\\s+\\[Member Exclusive\\])?$",
        "--parse-metadata", "title:(?:Ep\\.\\s+(?P<meta_movement>\\d+))?.*",
        "--parse-metadata", "title:(?:Ep\\.\\s+(?P<meta_track>\\d+))?.*",
        "--parse-metadata", "playlist_title:(?P<meta_album>.+)",
        "--parse-metadata", "playlist_title:(?P<meta_series>.+)",
        "--parse-metadata", "upload_date:(?P<meta_date>\\d{8})$",
        "--replace-in-metadata", "meta_date", "(.{4})(.{2})(.{2})", "\\1-\\2-\\3",
        "--parse-metadata", "upload_date:(?P<meta_year>.{4}).*",
        "--min-sleep-interval", "10",
        "--max-sleep-interval", "25",
        "--convert-thumbnails", "jpg",
        "--embed-thumbnail",
        "--match-title", "\\[Member Exclusive\\]",
        "-o", f"{show_name}/{output_template}",
        show_url
    ]
    
    # Add all the flag arrays
    cmd.extend(date_filter)
    cmd.extend(audio_flags)
    cmd.extend(nfo_info_flag)
    cmd.extend(exec_flag)
    cmd.extend(retry_flag)
    
    # Run the command
    subprocess.run(cmd)

def main():
    # Set umask to make all new dirs 777 and new files 666 by default
    os.umask(0)
    
    # Prevent overlapping runs
    lock_fd = acquire_lock()
    
    # Verify prerequisites
    verify_prerequisites()
    
    # Load configuration
    config = load_config()
    
    # Get flags based on configuration
    date_filter = get_date_filter(config)
    audio_flags = get_audio_flags(config)
    nfo_info_flag, exec_flag = get_nfo_flags(config)
    retry_flag = get_retry_flags(config)
    
    # Process each show
    for show in config.get("shows", []):
        show_name = show.get("name")
        show_url = show.get("url")
        
        if not (show_name and show_url):
            log("ERROR: each show needs `name` and `url`")
            sys.exit(1)
        
        download_show(show_name, show_url, config, date_filter, audio_flags, nfo_info_flag, exec_flag, retry_flag)
    
    # Release lock (will happen automatically when script exits, but being explicit)
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()

if __name__ == "__main__":
    main()