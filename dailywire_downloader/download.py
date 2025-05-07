"""DailyWire show downloader module."""

import os
import sys
import yaml
import time
import fcntl
import datetime
import re
import yt_dlp

# === Constants ===
DOWNLOAD_DIR = "/downloads"
TMP_DIR = "/tmp/yt-dlp-tmp"
ARCHIVE_FILE = f"{DOWNLOAD_DIR}/downloaded.txt"
COOKIES_FILE = "/config/cookies.txt"
CONFIG_FILE = "/config/config.yml"
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
        log("Another download process is still running; exiting.")
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

def get_date_filter_options(config):
    """Get date filter options based on start_date in config."""
    start_date = config.get("start_date", "").strip()
    if start_date:
        clean_date = start_date.replace('-', '')
        return {
            'dateafter': clean_date,
            'break_match_filter': f"upload_date>={clean_date}"
        }
    return {}

def get_audio_options(config):
    """Get audio-related options based on config."""
    audio_only = config.get("audio_only", False)
    audio_format = config.get("audio_format", "")

    options = {}
    if audio_only:
        options['extractaudio'] = True
        if audio_format:
            options['audioformat'] = audio_format
    return options

def get_nfo_options(config):
    """Get NFO-related options based on config."""
    save_nfo = config.get("save_nfo_file", False)

    options = {}
    if save_nfo:
        options['writeinfojson'] = True
        options['paths'] = {'infojson': TMP_DIR}
        # Import and use the nfo module directly
        from dailywire_downloader.nfo import create_nfo
        # In the Python API, postprocessor_hooks is used instead of exec_cmd
        options['postprocessor_hooks'] = [
            lambda info, ctx: create_nfo(info['filepath'], TMP_DIR)
        ]
    return options

def get_retry_options(config):
    """Get retry-related options based on config."""
    retry_download_all = config.get("retry_download_all", True)

    options = {}
    if not retry_download_all:
        options['break_on_existing'] = True
    else:
        options['sleep_interval_requests'] = 0.75
    return options

def download_show(show_name, show_url, config, date_options, audio_options, nfo_options, retry_options):
    """Download a single show using yt-dlp Python API."""
    log(f"Downloading '{show_name}' from {show_url}")

    output_template = config.get("output")
    if not output_template:
        log("ERROR: `output` key missing in config.yml")
        sys.exit(1)

    # Base options for YoutubeDL
    ydl_opts = {
        'cookiefile': COOKIES_FILE,
        'download_archive': ARCHIVE_FILE,
        'paths': {
            'temp': TMP_DIR,
            'home': DOWNLOAD_DIR
        },
        'cachedir': '/app/cache',
        'noprogress': True,  # No progress bar in API mode
        'no_part': True,
        'windowsfilenames': True,
        'writethumbnail': True,
        'embedthumbnail': True,
        'embedmetadata': True,
        'parse_metadata': [
            'description:(?s)(?P<meta_comment>.+)',
            'title:(?P<meta_title>.+?)(?:\\s+\\[Member Exclusive\\])?$',
            'title:(?:Ep\\.\\s+(?P<meta_movement>\\d+))?.*',
            'title:(?:Ep\\.\\s+(?P<meta_track>\\d+))?.*',
            'playlist_title:(?P<meta_album>.+)',
            'playlist_title:(?P<meta_series>.+)',
            'upload_date:(?P<meta_date>\\d{8})$',
            'upload_date:(?P<meta_year>.{4}).*'
        ],
        'replace_in_metadata': [
            ('meta_date', '(.{4})(.{2})(.{2})', '\\1-\\2-\\3')
        ],
        'sleep_interval_requests': 0.75,
        'min_sleep_interval': 10,
        'max_sleep_interval': 25,
        'convertthumbnails': 'jpg',  # Convert thumbnails to jpg
        'match_filter': 'title~="\\[Member Exclusive\\]"',
        'outtmpl': {
            'default': f"{show_name}/{output_template}"
        },
        'verbose': False  # Reduce verbosity in API mode
    }

    # Merge all option dictionaries
    ydl_opts.update(date_options)
    ydl_opts.update(audio_options)
    ydl_opts.update(nfo_options)
    ydl_opts.update(retry_options)

    # Use the Python API to download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([show_url])

def download_shows(config_file: str, cookies_file: str, download_dir: str):
    """Main function to download all configured shows.

    Args:
        config_file: Path to the configuration file. If None, uses the CONFIG_FILE constant.
        cookies_file: Path to the cookies file. If None, uses the COOKIES_FILE constant.
    """
    # Set umask to make all new dirs 777 and new files 666 by default
    os.umask(0)

    # Override global constants
    global CONFIG_FILE, COOKIES_FILE
    CONFIG_FILE = config_file
    COOKIES_FILE = cookies_file

    # Prevent overlapping runs
    lock_fd = acquire_lock()

    # Verify prerequisites
    verify_prerequisites()

    # Load configuration
    config = load_config()

    # Get options based on configuration
    date_options = get_date_filter_options(config)
    audio_options = get_audio_options(config)
    nfo_options = get_nfo_options(config)
    retry_options = get_retry_options(config)

    # Process each show
    for show in config.get("shows", []):
        show_name = show.get("name")
        show_url = show.get("url")

        if not (show_name and show_url):
            log("ERROR: each show needs `name` and `url`")
            sys.exit(1)

        download_show(show_name, show_url, config, date_options, audio_options, nfo_options, retry_options)

    # Release lock (will happen automatically when script exits, but being explicit)
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()
