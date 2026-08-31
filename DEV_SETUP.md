→ These are some loose, very unorganized dev notes.

## Important information about the project.
1. dw_id's cannot be trusted to remain the same. They may change over time. Use slugs instead.


## Building it yourself
The included Docker setup builds the React UI and the FastAPI backend into a
single image. Normal development and Docker builds use Font Awesome Free and
do not require any private npm credentials.

```bash
docker compose up -d --build
```

Then open http://localhost:8080.

Or with plain `docker`:

```bash
docker build -t wireloft -f .docker/Dockerfile .
docker run -d \
  -p 8080:80 \
  -v $(pwd)/config:/config \
  -v $(pwd)/downloads:/downloads \
  -e TZ=Europe/Amsterdam \
  --name wireloft \
  wireloft
```

### Font Awesome Pro builds

The normal `npm run build` path deliberately uses Font Awesome Free. The same
build can be requested explicitly with `npm run build:free-icons`. The Free
Font Awesome packages are pinned to the same Font Awesome 6 generation as the
paid WireLoft kit, so icons available in both sets use matching artwork.

For a credential-free checkout, install UI dependencies from the public npm
registry:

```bash
npm --prefix ui ci --registry=https://registry.npmjs.org
```

The paid kit is an optional dependency, so unavailable private credentials do
not prevent the normal install. Other optional packages are still installed,
including platform-specific dependencies required by Vite and Rollup.

To validate the real paid icon set, create `ui/.npmrc` (never committed, see
`ui/.gitignore`) with your Font Awesome npm authentication, for example:

```
@awesome.me:registry=https://npm.fontawesome.com/
//npm.fontawesome.com/:_authToken=<your token>
```

Then install dependencies including the paid kit and run:

```bash
npm --prefix ui ci --include=optional
npm run build:pro-icons
```

A Docker image with Pro icons can be built explicitly with:

```bash
docker build -t wireloft -f .docker/Dockerfile . \
  --build-arg WIRELOFT_PRO_ICONS=true \
  --secret id=npmrc,src=ui/.npmrc
```

The npm credentials are mounted only into the dependency-install step and are
never copied into the image.

## Publishing a release image
`./deploy.sh [tag]` intentionally builds with Font Awesome Pro icons and pushes
the image to `ghcr.io/samuelvisser/wireloft`. Because releases use the paid
icon set, `ui/.npmrc` is required for this command. The image is tagged
`latest`, `develop`, or `test` according to the current branch unless an
explicit tag is supplied.

It needs a GitHub personal access token with `write:packages` scope to log
in to ghcr.io, picked up in order from: the `GHCR_TOKEN` env var, a local
token file (default `~/.config/wireloft/ghcr_token`, override with
`$GHCR_TOKEN_FILE`), or an interactive hidden prompt as a last resort --
which then offers to save it to that file (created with permissions
restricted to your user only) so later runs don't ask again. The token is
never passed as a CLI argument and never printed.

## Development
### UI (React 19, Vite + TypeScript)

A web UI is included for navigation and demonstration purposes. It now uses a proper build step so you can write JSX and TypeScript.

### Develop (recommended)
Bash:
```bash
npm --prefix ui ci --registry=https://registry.npmjs.org
cd <PROJECT_DIR>\wireloft\ui
npm run dev
```
Open the URL shown by Vite (usually http://localhost:5173/). Edits to `.tsx` and `.css` files hot‑reload. The normal dev server uses Font Awesome Free; use `npm run dev:pro-icons` when you specifically need to inspect the paid icon set.

### Build for production
```bash
cd <PROJECT_DIR>\wireloft\ui
npm run build
```

`npm run build` is the credential-free Font Awesome Free build. Use
`npm run build:free-icons` for the explicit equivalent or
`npm run build:pro-icons` with valid Font Awesome credentials to validate the
paid kit.

### Dev backend
A simple backend is included and reads its data from the SQLite database.
Run the backend (in repo root):

```bash
uv sync
backend-api run --debug
```

This starts the backend API at http://127.0.0.1:5001

Run the React UI after installing its dependencies as shown above:

```bash
cd ui
npm run dev
```

### Automated tests

The default backend suite is isolated from both the live Daily Wire API and
`config/wireloft.db`. Install the development dependency group and run it from
the repository root:

```bash
uv sync --group dev
uv run pytest
```

Network sockets are disabled during this suite. Requests in `tests/rest` are
manual integration aids and require an access token supplied through a private
JetBrains HTTP Client environment file.

### Dailywire API
#### DailyWire API CLI

You can list episodes for a DailyWire show using the dailywire-api helper.

Example (bash):
```bash
dailywire-api show list --slug the-ben-shapiro-show
```

Options:
- --all: include all episodes by following seasons and pagination
- --json: output JSON instead of plain lines
- --access-token <JWT>: optional bearer token for premium content
- --membership-plan <PLAN>: optional membership plan (e.g., AllAccess)

### Database (SQLite)

This project includes a required SQLite database for the backend.
- Default development DB path: config/wireloft.db
- Docker mounts the same project `config` directory at `/config` and uses `/config/wireloft.db`, so local development and Docker operate on the same database by default.

#### Create and seed the database

Bash (repo root):
```bash
# Create database and tables
backend-api db init

# Seed database with demo data
backend-api db seed

# Use a custom database path
backend-api db init --db <DATA_DIR>/wireloft.db
backend-api db seed --db <DATA_DIR>/wireloft.db
```

#### Backend API commands

```bash
# Start backend server (development mode with auto-reload)
backend-api run --debug

# Start backend server (production mode)
backend-api run

# Start on custom host
backend-api run --host 0.0.0.0 --port 8000

# Stop all running backend processes
backend-api stop
```

Notes:
- Database seeding is idempotent: running it multiple times won't duplicate rows.
