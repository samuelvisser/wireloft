# Releasing WireLoft

WireLoft has one application version and independent versions for each Python workspace package.

- Application releases use Git tags such as `v1.0.0`.
- Python packages use scoped tags such as `backend-v0.1.0` and `dailywire-api-v0.1.0`.
- The root `pyproject.toml` is the single source of truth for the WireLoft application version. The backend settings API reads that value at runtime, so the API and UI always report the same application version.
- Package versions live in each package's `server/*/pyproject.toml`. If a package also exposes `__version__`, the release tool keeps it in sync.
- Release containers carry OCI `version`, `revision`, and `source` metadata in addition to their GHCR tags.

## Normal release

Start from a clean branch containing everything intended for the release, then run:

```bash
./release.py status
./release.py prepare
```

`prepare` fetches the latest tags and checks every `server/*` Python package independently. A package is only considered changed when files under that package changed since its latest scoped tag. For every changed package it prompts for a major, minor, or patch bump. Packages with no tag yet keep their current manifest version so their first release establishes a baseline.

WireLoft itself is prompted separately. You can choose major, minor, patch, or enter an exact semantic version. The command updates the root `pyproject.toml`, updates any changed package manifests and `__version__` constants, then runs `uv lock` once so the workspace lockfile stays consistent.

For automation or a known application version, use:

```bash
./release.py prepare --app-version 1.2.0
./release.py prepare --app-bump minor
./release.py prepare --dry-run
```

Review the resulting diff, run the normal tests/build, commit it, and merge it to `main`.

After the version-preparation commit is on `main`:

```bash
git switch main
git pull --ff-only
./release.py publish
```

`publish` refuses to run unless the worktree is clean and local `main` exactly matches `origin/main`. It then:

1. determines which Python packages need a tag;
2. builds the release container once and pushes `MAJOR.MINOR.PATCH`, `MAJOR.MINOR`, `MAJOR`, and `latest` aliases to GHCR;
3. creates annotated package tags for changed packages (or an initial baseline tag for packages that have never been tagged);
4. creates the application tag `vMAJOR.MINOR.PATCH`;
5. pushes all Git tags atomically.

The application tag triggers `.github/workflows/release.yml`, which verifies that the tag matches the version in the root `pyproject.toml` and creates the GitHub Release with generated release notes.

If the container has already been published separately, use:

```bash
./release.py publish --skip-container
```

For non-interactive publishing after you have reviewed the planned tags:

```bash
./release.py publish --yes
```

## WireLoft 1.0

WireLoft `1.0.0` is the first release under this scheme. Because no package tags existed before it, the first `publish` establishes these package baselines without changing their independent package versions. Future runs can then reliably detect package changes from those tags.
