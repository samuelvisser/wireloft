"""DailyWire show downloader module."""

import os
import sys
import yaml
import fcntl
import datetime
import time
import yt_dlp


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

    def get_show_config(self, show_name):
        """Get show-specific configuration based on show name."""
        show_config = {}
        for show in self.config.get("shows", []):
            if show.get("name") == show_name:
                show_config = show
                break
        return show_config

    def get_show_option(self, show_name, key, default=None):
        """Get show-specific configuration value based on show name."""
        show_config = self.get_show_config(show_name)
        if key in show_config:
            return show_config[key]

        # Fall back to global config
        return self.config.get(key, default)

    def get_date_filter_options(self, show_name):
        """Get date filter options based on start_date in config."""
        start_date = self.get_show_option(show_name, "start_date", "").strip()

        options = {}
        if start_date:
            clean_date = start_date.replace('-', '')
            options['match_filter'] = {'breaking_filters': ['upload_date>=' + clean_date]}
        return options

    def get_audio_options(self, show_name):
        """Get audio-related options based on config."""
        audio_only = self.get_show_option(show_name, "audio_only", False)
        audio_format = self.get_show_option(show_name, "audio_format", "")

        options = {}
        if audio_only:
            options = {
                'format': 'bestaudio/best',
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'nopostoverwrites': False,
                        'preferredcodec': 'best',
                        'preferredquality': '5'
                    }
                ]
            }

            if audio_format:
                options['final_ext'] = audio_format
                options['postprocessors'][0]['preferredcodec'] = audio_format

        return options

    def get_nfo_options(self, show_name):
        """Get NFO-related options based on config."""
        save_nfo = self.get_show_option(show_name, "save_nfo_file", False)

        options = {}
        if save_nfo:
            options['paths'] = {'infojson': self.tmp_dir}
            options['writeinfojson'] = True

            # Add nfo postprocessor hook
            from dailywire_downloader.nfo import create_nfo
            options['postprocessor_hooks'] = [
                lambda info, ctx: create_nfo(info['filepath'], self.tmp_dir)
            ]
        return options

    def get_retry_options(self, show_name):
        """Get retry-related options based on config."""
        retry_download_all = self.get_show_option(show_name, "retry_download_all", False)

        options = {}
        if not retry_download_all:
            options['break_on_existing'] = True
        else:
            # Add delay between HTTP requests to prevent rate limiting (HTTP 304 responses)
            options['sleep_interval_requests'] = 0.75
        return options

    def get_filter_options(self, show_name):
        """Get show-specific filter options."""
        show_config = self.get_show_config(show_name)
        filters = {}
        if "filters" in show_config:
            filters = show_config["filters"]
        if "filters" in self.config:
            self.update_dict(filters, self.config["filters"])

        options = {}
        if "matchtitle" in filters:
            options['matchtitle'] = filters['matchtitle']

        if "match_filters" in filters:
            options.setdefault('match_filter', {})['filters'] = filters['match_filters']

        if "breaking_filters" in filters:
            options.setdefault('match_filter', {})['breaking_filters'] = filters['breaking_filters']

        return options

    def download_show(self, show_name, show_url):
        """Download a single show using yt-dlp Python API."""
        self.log(f"Downloading '{show_name}' from {show_url}")

        output_template = self.get_show_option(show_name, "output")
        if not output_template:
            self.log("ERROR: `output` key missing in config.yml")
            sys.exit(1)

        # Base options for YoutubeDL
        # Options: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L220
        ydl_opts = {
            'cookiefile': self.cookies_file,
            'download_archive': self.archive_file,
            'paths': {
                'temp': self.tmp_dir,
                'home': self.download_dir
            },
            'cachedir': '/app/cache',
            'no_part': True,
            'windowsfilenames': True,
            'writethumbnail': True,
            'sleep_interval': 10.0,
            'max_sleep_interval': 25.0,
            'ignoreerrors': 'only_download',
            'outtmpl': {
                'default': f"{show_name}/{output_template}"
            },
            'match_filter': {
                'filters': ['!is_live']
            },
            'postprocessors': [
                {
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg',
                    'when': 'before_dl'
                },
                {
                    'key': 'EmbedThumbnail',
                    'already_have_thumbnail': False
                },
                {
                    'key': 'FFmpegMetadata',
                    'add_chapters': True,
                    'add_infojson': 'if_exists',
                    'add_metadata': True
                },
                {
                    'key': 'MetadataParser',
                    'when': 'pre_process',
                    'actions': [
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'description',
                         '(?s)(?P<meta_comment>.+)'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'title',
                         '(?P<meta_title>.+?)(?:\\s+\\[Member '
                         'Exclusive\\])?$'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'title',
                         '(?:Ep\\.\\s+(?P<meta_movement>\\d+))?.*'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'title',
                         '(?:Ep\\.\\s+(?P<meta_track>\\d+))?.*'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'playlist_title',
                         '(?P<meta_album>.+)'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'playlist_title',
                         '(?P<meta_series>.+)'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'upload_date',
                         '(?P<meta_date>\\d{8})$'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.replacer,
                         'meta_date',
                         '(.{4})(.{2})(.{2})',
                         '\\1-\\2-\\3'),
                        (yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
                         'upload_date',
                         '(?P<meta_year>.{4}).*')
                    ]
                }
            ],
            'verbose': False  # Reduce verbosity in API mode
        }

        # Merge all option dictionaries
        self.update_dict(ydl_opts, self.get_date_filter_options(show_name))
        self.update_dict(ydl_opts, self.get_audio_options(show_name), True)
        self.update_dict(ydl_opts, self.get_nfo_options(show_name))
        self.update_dict(ydl_opts, self.get_retry_options(show_name))
        self.update_dict(ydl_opts, self.get_filter_options(show_name))

        # Convert filters
        if 'match_filter' in ydl_opts:
            ydl_opts['match_filter'] = yt_dlp.utils.match_filter_func(ydl_opts['match_filter'].get('filters'), ydl_opts['match_filter'].get('breaking_filters'))

        # Use the Python API to download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([show_url])

    def update_dict(self, original, update, prepend_to_lists: bool = False):
        for key, value in update.items():

            # Add new key values
            if key not in original:
                original[key] = update[key]
                continue

            # Update the old key values with the new key values
            if key in original:
                if isinstance(value, dict):
                    self.update_dict(original[key], update[key])
                if isinstance(value, list):
                    if prepend_to_lists:
                        # Prepend instead of append to list
                        original[key] = update[key] + original[key]
                        continue
                    original[key].extend(update[key])
                if isinstance(value, (str, int, float)):
                    original[key] = update[key]
        return original

    def download_shows(self):
        """Main function to download all configured shows."""
        # Prevent overlapping runs
        self.acquire_lock()

        try:
            # Verify prerequisites
            self.verify_prerequisites()

            # Load configuration
            self.load_config()

            # Process each show
            for show in self.config.get("shows", []):
                show_name = show.get("name")
                show_url = show.get("url")

                if not (show_name and show_url):
                    self.log("ERROR: each show needs `name` and `url`")
                    sys.exit(1)

                try:
                    self.download_show(show_name, show_url)
                except Exception as e:
                    error_message = str(e)
                    if "--break-on-existing" in error_message:
                        self.log(f"Download for {show_name} stopped: All new videos have been downloaded.")
                    if " --" in error_message:
                        # The download stopped due to some setting (expected, no error)
                        self.log(f"Download for {show_name} stopped: {e}")
                    else:
                        raise e
                finally:
                    # Wait after download to avoid rate limiting (HTTP 304 responses)
                    # This intentionally will also wait after the last show, so that the
                    # next cron cycle cannot start sooner than 120 seconds after the last
                    self.log("Waiting 120 seconds after show download...")
                    time.sleep(120)
                    self.log("...done.")
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
