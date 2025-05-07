"""DailyWire show downloader module."""

import os
import sys
import yaml
import time
import fcntl
import datetime
import re
import yt_dlp
from yt_dlp.devscripts.cli_to_api import cli_to_api


class DailyWireDownloader:
    """Class for downloading DailyWire shows."""

    def __init__(self, config_file, cookies_file, download_dir):
        """Initialize the downloader with configuration.

        Args:
            config_file: Path to the configuration file.
            cookies_file: Path to the cookies file.
            download_dir: Path to the download directory.
        """
        # Paths
        self.download_dir = download_dir
        self.tmp_dir = "/tmp/yt-dlp-tmp"
        self.config_file = config_file
        self.cookies_file = cookies_file
        self.lockfile = "/tmp/download.lock"
        self.archive_file = f"{self.download_dir}/downloaded.txt"

        # Set umask to make all new dirs 777 and new files 666 by default
        os.umask(0)

        # Initialize lock file descriptor
        self.lock_fd = None

        # Configuration
        self.config = None

    def log(self, message):
        """Print a timestamped log message."""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"{timestamp}: {message}")

    def acquire_lock(self):
        """Prevent overlapping runs using file locking."""
        try:
            self.lock_fd = open(self.lockfile, 'w')
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self.lock_fd
        except IOError:
            self.log("Another download process is still running; exiting.")
            sys.exit(0)

    def release_lock(self):
        """Release the lock file."""
        if self.lock_fd:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            self.lock_fd.close()
            self.lock_fd = None

    def verify_prerequisites(self):
        """Verify that all required files and directories exist."""
        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.tmp_dir, exist_ok=True)

        # Create archive file if it doesn't exist
        if not os.path.exists(self.archive_file):
            open(self.archive_file, 'a').close()

        # Check for required files
        if not os.path.isfile(self.cookies_file):
            self.log(f"ERROR: Cookies file missing at {self.cookies_file}")
            sys.exit(1)

        if not os.path.isfile(self.config_file):
            self.log(f"ERROR: Config file missing at {self.config_file}")
            sys.exit(1)

    def load_config(self):
        """Load configuration from YAML file."""
        with open(self.config_file, 'r') as f:
            self.config = yaml.safe_load(f)
            return self.config

    def get_date_filter_options(self):
        """Get date filter options based on start_date in config."""
        start_date = self.config.get("start_date", "").strip()
        if start_date:
            clean_date = start_date.replace('-', '')
            return {
                'dateafter': clean_date,
                'break_match_filter': f"upload_date>={clean_date}"
            }
        return {}

    def get_audio_options(self):
        """Get audio-related options based on config."""
        audio_only = self.config.get("audio_only", False)
        audio_format = self.config.get("audio_format", "")

        options = {}
        if audio_only:
            options['extractaudio'] = True
            if audio_format:
                options['audioformat'] = audio_format
        return options

    def get_nfo_options(self):
        """Get NFO-related options based on config."""
        save_nfo = self.config.get("save_nfo_file", False)

        options = {}
        if save_nfo:
            options['writeinfojson'] = True
            options['paths'] = {'infojson': self.tmp_dir}
            # Import and use the nfo module directly

            from dailywire_downloader.nfo import create_nfo
            # Call the create_nfo function
            options['postprocessor_hooks'] = [
                lambda info, ctx: create_nfo(info['filepath'], self.tmp_dir)
            ]
        return options

    def get_retry_options(self):
        """Get retry-related options based on config."""
        retry_download_all = self.config.get("retry_download_all", True)

        options = {}
        if not retry_download_all:
            options['break_on_existing'] = True
        else:
            ## TODO there needs to be some mitigation here against http 304 responses when too many requests are made
            ## options['sleep_interval_requests'] = 0.75
            ...
        return options

    def download_show(self, show_name, show_url, date_options, audio_options, nfo_options, retry_options):
        """Download a single show using yt-dlp CLI-style options."""
        self.log(f"Downloading '{show_name}' from {show_url}")

        output_template = self.config.get("output")
        if not output_template:
            self.log("ERROR: `output` key missing in config.yml")
            sys.exit(1)

        # Build CLI-style options
        cli_opts = [
            # Basic options
            '--cookies', self.cookies_file,
            '--download-archive', self.archive_file,
            '--paths', f'temp:{self.tmp_dir}',
            '--paths', f'home:{self.download_dir}',
            '--cache-dir', '/app/cache',
            '--no-progress',
            '--no-part',
            '--windows-filenames',
            '--convert-thumbnails', 'jpg',
            '--embed-thumbnail',
            '--embed-metadata',
            '--parse-metadata', 'description:(?s)(?P<meta_comment>.+)',
            '--parse-metadata', 'title:(?P<meta_title>.+?)(?:\\s+\\[Member Exclusive\\])?$',
            '--parse-metadata', 'title:(?:Ep\\.\\s+(?P<meta_movement>\\d+))?.*',
            '--parse-metadata', 'title:(?:Ep\\.\\s+(?P<meta_track>\\d+))?.*',
            '--parse-metadata', 'playlist_title:(?P<meta_album>.+)',
            '--parse-metadata', 'playlist_title:(?P<meta_series>.+)',
            '--parse-metadata', 'upload_date:(?P<meta_date>\\d{8})$',
            '--parse-metadata', 'upload_date:(?P<meta_year>.{4}).*',
            '--replace-in-metadata', 'meta_date', '(.{4})(.{2})(.{2})', '\\1-\\2-\\3',
            '--min-sleep-interval', '10',
            '--max-sleep-interval', '25',
            '--match-filter', 'title~="\\[Member Exclusive\\]"',
            '--output', f"{show_name}/{output_template}",
            '--quiet'  # Equivalent to verbose=False
        ]

        # Add date options
        if 'dateafter' in date_options:
            cli_opts.extend(['--dateafter', date_options['dateafter']])
        if 'break_match_filter' in date_options:
            cli_opts.extend(['--break-match-filter', date_options['break_match_filter']])

        # Add audio options
        if audio_options.get('extractaudio', False):
            cli_opts.append('--extract-audio')
            if 'audioformat' in audio_options:
                cli_opts.extend(['--audio-format', audio_options['audioformat']])

        # Add NFO options
        if nfo_options.get('writeinfojson', False):
            cli_opts.append('--write-info-json')
            # Note: postprocessor_hooks can't be directly translated to CLI options
            # We'll handle this separately

        # Add retry options
        if retry_options.get('break_on_existing', False):
            cli_opts.append('--break-on-existing')

        # Convert CLI options to API parameters
        ydl_opts = cli_to_api(cli_opts)

        # Add options that can't be directly translated to CLI
        if 'postprocessor_hooks' in nfo_options:
            ydl_opts['postprocessor_hooks'] = nfo_options['postprocessor_hooks']

        # Use the Python API to download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([show_url])

    def download_shows(self):
        """Main function to download all configured shows."""
        # Prevent overlapping runs
        self.acquire_lock()

        try:
            # Verify prerequisites
            self.verify_prerequisites()

            # Load configuration
            self.load_config()

            # Get options based on configuration
            date_options = self.get_date_filter_options()
            audio_options = self.get_audio_options()
            nfo_options = self.get_nfo_options()
            retry_options = self.get_retry_options()

            # Process each show
            for show in self.config.get("shows", []):
                show_name = show.get("name")
                show_url = show.get("url")

                if not (show_name and show_url):
                    self.log("ERROR: each show needs `name` and `url`")
                    sys.exit(1)

                self.download_show(show_name, show_url, date_options, audio_options, nfo_options, retry_options)
        finally:
            # Release lock (will happen automatically when script exits, but being explicit)
            self.release_lock()


def download_shows(config_file: str, cookies_file: str, download_dir: str):
    """Main function to download all configured shows.

    Args:
        config_file: Path to the configuration file.
        cookies_file: Path to the cookies file.
        download_dir: Path to the download directory where shows will be saved.
    """
    downloader = DailyWireDownloader(config_file, cookies_file, download_dir)
    downloader.download_shows()
