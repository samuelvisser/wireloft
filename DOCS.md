## Podcast RSS feeds

Add a Stream Profile (of type RSS) to a show and WireLoft generates a feed URL for you automatically -
paste it into your podcast app and go. The URL can be freely edited afterwards (e.g. if you access WireLoft
through a different hostname than the one WireLoft guessed), and can be regenerated at any time from the
profile's edit page, which immediately invalidates the old URL.

The feed can serve matching downloaded files (per the profile's preferred format and "require exact match"
setting), stream episodes directly from Daily Wire, or use both sources. When both are enabled, a matching
download is preferred and Daily Wire is used as the fallback.

Feed URLs (and the media files they link to) are served without going through WireLoft's own login: each
profile's URL contains a long, unguessable secret token, so the feed keeps working for your podcast app even
when local authentication is enabled for the web UI - similar to how [Pinchflat handles this](https://github.com/kieraneglin/pinchflat/wiki/Podcast-RSS-Feeds).
Treat a feed URL like a password: anyone who has it can stream (and see the titles/descriptions of) that
show's downloaded episodes.

## Authentication and session persistence

When logging in, if you see a message like:

WL_SECRET_KEY not set; generating ephemeral key for this process. Tokens will not persist across restarts.

It means the application did not find a secret key to encrypt/decrypt your session cookies. A new, in-memory key was generated for that process only. If the process restarts, that key is lost and existing logins become invalid.

How to persist logins safely:

- Option A: Set WL_SECRET_KEY (recommended for non-Docker setups)
  - Generate a Fernet key once and keep it safe:
    - Python: python - <<'PY'\nfrom cryptography.fernet import Fernet\nprint(Fernet.generate_key().decode())\nPY
  - Put the printed value into your environment (or .env) as WL_SECRET_KEY=... and restart the app.

- Option B: Point to a key file with WL_SECRET_KEY_FILE (great for Docker/Kubernetes secrets)
  - Store the key string (from Option A) in a file readable by the app, and set WL_SECRET_KEY_FILE to that path.
  - Example .env:
    - WL_SECRET_KEY_FILE=./data/wl_secret.key

- Option C: Do nothing (auto-persist default)
  - If neither WL_SECRET_KEY nor WL_SECRET_KEY_FILE is set, WireLoft will now automatically create a persistent key file at data/wl_secret.key on first run and reuse it thereafter. Ensure your data/ directory is persisted across restarts (e.g., bind mounted as a Docker volume) so logins survive container restarts.

Security notes:
- Keep your secret key private. Anyone with this key can forge session cookies.
- Rotating the key will immediately invalidate all existing sessions. To rotate, replace the key (env or file) and restart the app.
- File permissions are set to 600 when possible.

Docker tip:
- The provided image already persists this for you: the auto-generated key
  and the database both live under `/config`, which `docker-compose.yml` maps
  to `./config` on the host. Nothing extra to configure.