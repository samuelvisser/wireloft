→ These are some loose, very unorganized dev notes.

## Important information about the project.
1. dw_id's cannot be trusted to remain the same. They may change over time. Use slugs instead.


## Building it yourself
The included Docker setup builds the React UI and the FastAPI backend into a
single image.

Building the UI needs your own Font Awesome Pro credentials: create
`ui/.npmrc` (never committed, see `ui/.gitignore`) with the same npm auth
token you use for local development, e.g.:

```
@awesome.me:registry=https://npm.fontawesome.com/
//npm.fontawesome.com/:_authToken=<your token>
```

The build reads it as a [BuildKit secret](https://docs.docker.com/build/building/secrets/)
mounted only into the `npm ci` step -- it's never copied into the build
context or baked into any image layer, so the published image stays safe to
make public.

Using Docker Compose (recommended -- already wired to `ui/.npmrc` as a
build secret):

```bash
docker compose up -d --build
```

Then open http://localhost:8080.

Or with plain `docker`:

```bash
docker build -t wireloft -f .docker/Dockerfile . \
  --secret id=npmrc,src=ui/.npmrc

docker run -d \
  -p 8080:80 \
  -v $(pwd)/config:/config \
  -v $(pwd)/downloads:/downloads \
  -e TZ=Europe/Amsterdam \
  --name wireloft \
  wireloft
```

## Publishing a release image
`./deploy.sh [tag]` builds the image (same as above, `ui/.npmrc` required)
and pushes it to `ghcr.io/samuelvisser/wireloft`, tagged `latest` by default
or with `tag` (e.g. `./deploy.sh v1.2.0`) plus `latest`.

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
cd <PROJECT_DIR>\wireloft\ui
npm install
npm run dev
```
Open the URL shown by Vite (usually http://localhost:5173/). Edits to `.tsx` and `.css` files hot‑reload.

### Build for production
```bash
cd <PROJECT_DIR>\wireloft\ui
npm run build
```

### Dev backend
A simple backend is included and reads its data from the SQLite database.
Run the backend (in repo root):

```bash
uv sync
backend-api run --debug
```

This starts the backend API at http://127.0.0.1:5001

Run the React UI (in ui/):

```bash
npm install
npm run dev
```

### Automated tests

The default backend suite is isolated from both the live Daily Wire API and
`data/wireloft.db`. Install the development dependency group and run it from
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
- Default DB path: data/wireloft.db

#### Create and seed the database

Bash (repo root):
```bash
# Create database and tables
backend-api db init

# Seed database with demo data
backend-api db seed

# Use a custom database path
backend-api db init --db <DATA_DIR>/data/wireloft.db
backend-api db seed --db <DATA_DIR>/data/wireloft.db
```

#### Backend API commands

```bash
# Start backend server (development mode with auto-reload)
backend-api run --debug

# Start backend server (production mode)
backend-api run

# Start on custom host/port
backend-api run --host 0.0.0.0 --port 8000

# Stop all running backend processes
backend-api stop
```

Notes:
- Database seeding is idempotent: running it multiple times won't duplicate rows.
