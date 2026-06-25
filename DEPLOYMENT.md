# Deployment Guide

This covers the most common ways to actually run the Streamlit dashboard
somewhere other than your own laptop. None of these require code changes
— the app reads its config from `configs/*.yaml` at startup and its
database connection from `HYDRAULIC_DB_*` environment variables, so the
same image/deployment works for any scenario set or environment.

**Since v2**: the app needs PostgreSQL with the **PostGIS** extension for
login/RBAC, audit logging, and the network map. The pure analysis modules
(`src/hydraulics/`, `src/simulation/`, `src/economics/`,
`src/machine_learning/`) have no database dependency and can be used as a
library without any of this — only the Streamlit dashboard and
`src/auth/`/`src/audit/`/`src/geospatial/` need it.

---

## Database setup

All options below need a reachable PostgreSQL instance with PostGIS
enabled, and these five environment variables pointing at it:

```
HYDRAULIC_DB_HOST=...
HYDRAULIC_DB_PORT=5432
HYDRAULIC_DB_NAME=hydraulic_analysis
HYDRAULIC_DB_USER=hydraulic_app
HYDRAULIC_DB_PASSWORD=...
```

(See `.env.example`.) The app calls `init_schema()` on first page load,
which runs `CREATE EXTENSION IF NOT EXISTS postgis;` and creates every
table if missing — idempotent, safe to leave in place permanently. It
also seeds the two demo accounts (`technician`/`engineer`) if the
`users` table is empty — **change or remove these before any real
deployment**, e.g. by calling `src.auth.service.create_user()` for real
accounts and not relying on `seed_demo_users()`.

Where to get a Postgres+PostGIS instance:

- **`docker-compose.yml`** (this repo) — provisions one automatically
  using the official `postgis/postgis` image. Best for local dev and
  Option 2 below.
- **Managed Postgres with PostGIS**: most providers support it —
  Supabase and Neon enable it via `CREATE EXTENSION postgis;` directly;
  AWS RDS for PostgreSQL, Google Cloud SQL, and Azure Database for
  PostgreSQL all support the PostGIS extension with a setting/flag. Check
  your provider's current docs, since exact steps change over time.
- **Self-hosted**: install `postgresql` + the matching
  `postgresql-<version>-postgis-3` package (apt/yum), or just run the
  `postgis/postgis` Docker image yourself.

---

## Option 1: Streamlit Community Cloud (easiest, free) + a managed Postgres

Best for: sharing this with others quickly, no servers to manage.

1. Provision a small managed Postgres with PostGIS enabled (see above —
   Supabase's free tier is a reasonable choice for a demo).
2. Push this repository to GitHub (public or private).
3. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, click **New app**, and set:
   - **Main file path**: `streamlit_app/app.py`
   - **Python version**: 3.10 (matches `pyproject.toml`)
4. In the app's **Settings → Secrets**, add your `HYDRAULIC_DB_*` values
   (Community Cloud injects secrets as environment variables, which
   `src/db.py` reads directly — no code changes needed):
   ```toml
   HYDRAULIC_DB_HOST = "your-host"
   HYDRAULIC_DB_PORT = "5432"
   HYDRAULIC_DB_NAME = "hydraulic_analysis"
   HYDRAULIC_DB_USER = "hydraulic_app"
   HYDRAULIC_DB_PASSWORD = "your-real-password"
   ```
5. Deploy. Community Cloud installs `requirements.txt` and picks up
   `.streamlit/config.toml` from the repo root automatically.

**Limitations**: free tier apps sleep after inactivity and have modest
resource limits — fine for this app's calculations, but not for heavy
Monte Carlo batches with very large `n_samples`. The Config Editor page
writes directly to `configs/*.yaml` on disk; Community Cloud's
filesystem is ephemeral, so **those edits won't survive a redeploy** —
commit config changes to the repo instead for anything that needs to
persist (this limitation doesn't apply to Option 2, where the volume
mount makes edits durable).

---

## Option 2: Docker / docker-compose (any cloud VM, or local)

Use this for: full control, no third-party platform lock-in, persistent
config edits, or testing exactly what production will run before
deploying it. This is the option the app was primarily built against —
both services (app + database) are already wired together correctly.

### Local

```bash
docker compose up --build
```

This starts both the `db` (Postgres+PostGIS) and `dashboard` services,
wires them together via the `HYDRAULIC_DB_HOST=db` environment variable,
waits for the database's health check before starting the app, and
persists database data in a named volume (`postgres_data`) across
restarts. Visit `http://localhost:8501`.

The compose file also volume-mounts `configs/` from your host, so edits
via the Config Editor page (or directly editing the YAML) persist and
don't require a rebuild. Remove that mount in `docker-compose.yml` for a
fully immutable production image.

### Build and run the app image manually (bring your own Postgres)

```bash
docker build -t hydraulic-dashboard -f streamlit_app/Dockerfile .
docker run -p 8501:8501 \
  -e HYDRAULIC_DB_HOST=your-postgres-host \
  -e HYDRAULIC_DB_PASSWORD=your-real-password \
  hydraulic-dashboard
```

### Deploy to a cloud VM

Push the image to a registry and run it on any host that can run Docker,
pointed at your managed Postgres (or a Postgres container on the same
host/network):

```bash
docker tag hydraulic-dashboard your-registry/hydraulic-dashboard:latest
docker push your-registry/hydraulic-dashboard:latest
# on the server:
docker run -d -p 8501:8501 --restart unless-stopped \
  -e HYDRAULIC_DB_HOST=... -e HYDRAULIC_DB_PASSWORD=... \
  your-registry/hydraulic-dashboard:latest
```

Put a reverse proxy (nginx, Caddy, Traefik) in front for TLS/HTTPS —
Streamlit itself serves plain HTTP.

**Verification status**: `.github/workflows/ci.yml` runs `docker compose
up --build` (the full two-service stack) and smoke-tests the health
endpoint on every push — check that job's status before trusting a given
commit for production. One real bug was caught and fixed this way during
development (a missing `curl` install that made the Dockerfile's
`HEALTHCHECK` always report unhealthy).

---

## Option 3: Container-platform-as-a-service (Render, Railway, Fly.io, etc.)

Use this for: Docker's control without managing servers yourself. Most of
these platforms can provision a Postgres add-on directly (check whether
their managed Postgres supports enabling PostGIS — if not, point the app
at an external managed Postgres instead).

General steps (specifics vary by platform):

1. Provision a Postgres database through the platform (or use an
   external one) and confirm PostGIS can be enabled on it.
2. Connect your GitHub repo to the platform.
3. Set the Dockerfile path to `streamlit_app/Dockerfile` and the build
   context to the repo root (not the `streamlit_app/` subfolder — the
   Dockerfile's `COPY` commands assume the root context).
4. Set the exposed port to `8501`.
5. Set the `HYDRAULIC_DB_*` environment variables in the platform's
   dashboard, pointing at the Postgres from step 1.
6. Deploy.

Most of these platforms auto-detect the `HEALTHCHECK` in the Dockerfile;
some want it configured separately in their dashboard (path:
`/_stcore/health`, port `8501`).

---

## Health checks

The app exposes Streamlit's built-in health endpoint at
`/_stcore/health` (used by the Dockerfile's `HEALTHCHECK` and
`docker-compose.yml`). Note this only confirms the Streamlit *server* is
responding — it does not confirm the database is reachable. A database
outage shows as a clear in-app error message (each page's
`_ensure_db_ready()` check) rather than a failed health check; monitor
both if database uptime matters to you.

## Configuration & secrets in production

- `configs/*.yaml` drives every scenario, cost assumption, and Monte
  Carlo/sensitivity setting.
- `HYDRAULIC_DB_*` environment variables hold database credentials —
  **never** commit real values (only `.env.example` belongs in version
  control; `.gitignore`/`.dockerignore` already exclude `.env`).
- `.streamlit/config.toml` disables Streamlit's usage-stats collection
  and sets a basic theme.
- RBAC/login is handled entirely by this app's own `src/auth/` (bcrypt
  password hashing, roles stored in Postgres) — it does not use
  Streamlit's own auth features. If you later want SSO/OAuth instead,
  see [Streamlit's auth docs](https://docs.streamlit.io/develop/concepts/multipage-apps/authentication)
  for current options, since that surface changes over time.

## CI/CD

`.github/workflows/ci.yml`:
- **`build`** job: lints, runs the full pytest suite (with a
  `postgis/postgis` service container, so the auth/audit/geospatial/RBAC
  tests actually run, not just skip) across Python 3.10/3.11, generates
  the PDF report, and uploads it as a build artifact.
- **`docker`** job: runs `docker compose up --build` (the real two-service
  stack) and smoke-tests the health endpoint.

Extend it with a deploy step if you want push-to-deploy — the exact step
depends on which option above you pick (e.g. `docker/build-push-action`
for Option 2/3, or nothing extra needed for Option 1, which deploys
automatically from GitHub on its own).
