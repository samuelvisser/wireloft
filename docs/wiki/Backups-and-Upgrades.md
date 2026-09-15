# Backups and Upgrades

WireLoft is easy to back up when its persistent data is kept outside the container.

## What to back up

### `/config` — essential

Back up the entire `/config` directory. It contains the state needed to restore your WireLoft installation, including:

- the SQLite database;
- `config.yml`;
- the application secret key;
- Daily Wire authentication state;
- other persistent application data stored alongside the configuration.

Backing up the complete directory is safer than maintaining a hand-picked file list as WireLoft evolves.

### `/downloads` — optional, depending on your storage policy

`/downloads` contains the media WireLoft downloaded.

Back it up when those files are important or expensive to recreate. You may choose not to back it up when downloads are treated as replaceable media and you are comfortable fetching them again.

Remember that WireLoft cannot guarantee The Daily Wire will continue to make every old file available forever, especially member-exclusive media.

## Make a consistent database backup

WireLoft uses SQLite. The simplest reliable backup is to stop WireLoft while copying `/config`:

```bash
docker compose stop wireloft
# back up ./config here
docker compose start wireloft
```

If your storage/backup system supports application-consistent SQLite snapshots, you can use that instead.

Do not run two WireLoft backends against the same SQLite database at the same time. For example, avoid starting a local development backend and a Docker instance that both point to the same `wireloft.db`.

## Do not lose the application key

The normal Docker setup keeps WireLoft's generated application key under `/config`. Preserve it together with the database.

Restoring only `wireloft.db` while losing the accompanying key and authentication state can result in an incomplete restore.

## Upgrade WireLoft

Before an important upgrade, make a fresh `/config` backup.

Then update a normal Compose installation with:

```bash
docker compose pull
docker compose up -d
```

WireLoft applies required database migrations when the new container starts. Because `/config` and `/downloads` live outside the container, recreating the container does not remove those mounted directories.

## Configuration after an upgrade

WireLoft does not replace your existing `config.yml` with a newly shipped default file.

Settings you explicitly changed remain yours. Settings that are not present in your file use the defaults supplied by the new WireLoft version.

The Settings page also writes only values you actually change instead of filling `config.yml` with every possible default.

After a larger update, it is worth opening **Settings** and checking for new options that may be useful to your installation.

## Restore procedure

A typical restore is:

1. Stop WireLoft.
2. Restore the complete saved `/config` directory to the path mounted into the container.
3. Restore `/downloads` if it was included in the backup.
4. Confirm the container has permission to read and write the restored directories.
5. Start WireLoft.
6. Check Home and Library.
7. Verify the Daily Wire connection under Settings.
8. Open a known completed download and confirm the file is available.
9. Test any private RSS feeds you rely on.

If the restored installation uses a different hostname, edit the RSS Stream Profile URLs so podcast clients can reach the new address. You only need to regenerate the secret token if you intentionally want to revoke the old feed URL.

## Before experimenting with database or migration commands

Take a `/config` backup first. Database maintenance commands can be useful during development or recovery, but they are not a substitute for a known-good backup.

For ordinary upgrades, let the container apply its normal migrations automatically.