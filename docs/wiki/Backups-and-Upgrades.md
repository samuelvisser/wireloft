# Backups and Upgrades

WireLoft is straightforward to back up when the two persistent Docker mounts are kept separate from the container itself.

## What to back up

### `/config` — essential

Back up the entire `/config` directory. It contains the application configuration and persistent state needed to reconstruct your WireLoft instance, including the SQLite database, `config.yml`, secret-key material, and Daily Wire authentication state.

Backing up the whole directory is safer than trying to maintain a hand-picked file list as WireLoft evolves.

### `/downloads` — according to your recovery needs

`/downloads` contains the media WireLoft downloaded. Whether you back it up depends on your storage strategy:

- back it up if downloaded media is expensive or inconvenient to recreate;
- omit it from backups if you deliberately treat downloads as reproducible cache/archive data and are comfortable fetching them again;
- remember that old premium media may not remain remotely available forever, so reproducibility is not guaranteed by WireLoft.

## Consistent database backups

WireLoft uses SQLite. For the cleanest snapshot, stop or quiesce the container while copying the database/config directory, or use a backup mechanism that understands SQLite snapshots.

A simple maintenance approach is:

```bash
docker compose stop wireloft
# back up ./config here
docker compose start wireloft
```

If your backup product already provides application-consistent filesystem snapshots, follow its SQLite guidance instead.

## Do not lose the secret key

The supplied Docker configuration keeps the generated application secret under `/config/wl_secret.key`. Preserve it with the rest of `/config`.

Restoring only the database but not the accompanying secret/authentication state can produce an incomplete restore.

## Upgrade the container

For a normal Compose deployment:

```bash
docker compose pull
docker compose up -d
```

Because `/config` and `/downloads` are bind-mounted outside the container, recreating the container does not remove those directories.

Before a major upgrade, take a fresh `/config` backup.

## Configuration upgrades

The default `config.yml` shipped with WireLoft is copied only when a configuration file does not already exist. An upgrade does **not** overwrite your existing file with a new full default.

That behavior is intentional: settings omitted from your YAML continue to receive their current application defaults, while values you explicitly customized remain yours.

The Settings UI likewise writes only changed fields instead of materializing every default into the file.

## Restore procedure

A typical restore is:

1. Stop WireLoft.
2. Restore the saved `/config` directory to the path mounted into the container.
3. Restore `/downloads` if it was part of the backup.
4. Confirm file ownership/permissions allow the container to read and write both mounts.
5. Start WireLoft.
6. Verify the Library, Settings, Daily Wire connection, and a known local download.
7. Test any private RSS feed from a podcast client.

If you intentionally restore to a different public hostname, edit RSS Stream Profile URLs so they point at the new reachable hostname. The secret token can remain the same unless you also want to rotate it.