# Local Development Setup

One setup, same on every machine. The **backend and its infrastructure run in
Docker** with hot reload; the **admin frontend runs natively** with `npm run dev`.

You edit exactly two files, ever:

| Repo | File | Holds |
| --- | --- | --- |
| `rext-backend` | `.env` | backend secrets and app config |
| `rext-admin` | `.env.local` | frontend keys and the backend URL |

Both are gitignored. Everything else — database URLs, Redis URLs, MinIO
credentials, ports — is set for you by `docker-compose.dev.yml`.

---

## Prerequisites

- Docker Desktop (running)
- Node.js 20+ and npm
- Git

You do **not** need Python, `uv`, or a local Postgres/Redis. That is the point:
the backend toolchain lives entirely inside the container.

---

## 1. Backend — runs in Docker

```bash
cd rext-backend
cp .env.example .env      # then fill in the secrets, see below
docker compose -f docker-compose.dev.yml up
```

First run builds the image and takes a few minutes. After that it starts in
seconds.

The API is on **http://localhost:2024**.

### What is running

| Service | Host port | Notes |
| --- | --- | --- |
| `api` | 2024 | the backend **and the LangGraph server**, with hot reload |
| `postgres` | 5433 | application data (pgvector/pg17); 5433 so it cannot clash with a locally installed Postgres |
| `langgraph-postgres` | 5434 | LangGraph checkpointer and store, its own database |
| `redis` | 6379 | app cache |
| `langgraph-redis` | 6380 | LangGraph queue, kept separate |
| `minio` | 9000, 9001 | object storage, console at http://localhost:9001 (`minioadmin` / `minioadmin`) |

### Where LangGraph runs

There is no separate LangGraph container, because there isn't one in production
either. The `api` service **is** the LangGraph server: `langgraph dev` reads
`langgraph.json`, serves the graph under `graphs.agent` (`main:graph`), and
mounts the FastAPI app from `http.app` (`src/api/server.py:app`) on the same
port. So `http://localhost:2024` serves both the REST routes the admin frontend
calls and the LangGraph endpoints. Its supporting services — `langgraph-redis`
and `langgraph-postgres` — are separate containers, matching production.

The image also installs Playwright, crawl4ai and Chromium, mirroring the
`dockerfile_lines` block in `langgraph.json`, so crawling code behaves the same
locally as it does in staging. That is most of the first build's duration.

If the Playwright CDN is unreachable from your network, the download is capped
at five minutes and the build continues with a warning rather than hanging — the
Python packages still install, so imports resolve and only actual browser
launches fail. To skip it outright:

```bash
docker compose -f docker-compose.dev.yml build --build-arg INSTALL_BROWSERS=0 api
```

One deliberate difference from production: `langgraph dev` runs the in-memory
runtime, while production runs `LANGGRAPH_RUNTIME_EDITION=postgres`. Graph state
is therefore not durable across restarts locally. Application data in `postgres`
**is** durable — only graph checkpoints are affected.

### Hot reload

The repo is bind-mounted into the container, so saving a `.py` file on your
machine reloads the server inside Docker. This is the `npm run dev` equivalent —
no rebuild, no restart.

You only need to rebuild when dependencies change:

```bash
docker compose -f docker-compose.dev.yml build api
```

### Filling in `.env`

Copy `.env.example` and set the real values for the keys you need. Only three
settings have no default and will stop the app booting: `SECRET_KEY` and
`REFRESH_SECRET_KEY` (both minimum 32 characters) and `POSTGRES_URI_CUSTOM`,
which the compose file already supplies. Add `OPENAI_API_KEY` for anything that
calls a model.

> **Check these two before your first `up`:**
>
> ```
> SUPER_ADMIN_EMAIL=admin@example.com
> SUPER_ADMIN_PASSWORD=replace_with_secure_admin_password
> ```
>
> The migration `6a35a3742a53_seed_super_admin_from_env` creates your admin
> login from these. `.env.example` ships working placeholders, so copying it
> unchanged gives you a usable local sign-in with exactly those credentials —
> change them now if you would rather they were yours.
>
> What you must not do is **blank them out**. If both are empty the migration
> prints a warning and skips, and because Alembic records the revision as
> applied it **never runs again**: you would have a working backend with no way
> to sign in, and re-running migrations would not fix it. Recovering means
> wiping the database with `db.py seed`.

**Do not put database or Redis URLs in `.env`.** `docker-compose.dev.yml` sets
`POSTGRES_URI_CUSTOM`, `REDIS_URL`, `REDIS_URI`, `CACHE_URL` and the MinIO
settings itself, and those override `.env`. This is deliberate: inside a
container `localhost` means *that container*, not your machine, so a hostname
that works on your host would break in Docker. Leaving them out of `.env` keeps
one file working for everyone.

### Database migrations — automatic

**You do not run migrations by hand.** A one-shot `migrate` service runs on every
`up`, applies anything pending via `scripts/db.py migrate` (which also sets up
the LangGraph store tables), and exits. The API waits for it to finish
successfully before starting, so it can never come up against an out-of-date
schema.

That means after `git pull` brings in a new migration, a plain
`docker compose -f docker-compose.dev.yml up` applies it. Alembic is idempotent,
so when there is nothing pending the step is a fast no-op.

To watch it:

```bash
docker compose -f docker-compose.dev.yml logs migrate
```

To run one yourself anyway:

```bash
docker compose -f docker-compose.dev.yml run --rm migrate
```

**`db.py seed` is deliberately not automated** — it is *reset + migrate* and
drops every row. Run it only when you deliberately want a clean database:

```bash
docker compose -f docker-compose.dev.yml run --rm api python scripts/db.py seed
```

Other useful commands:

```bash
docker compose -f docker-compose.dev.yml exec api python scripts/db.py status  # migration status
docker compose -f docker-compose.dev.yml exec api sh                # shell in the container
docker compose -f docker-compose.dev.yml logs -f api                # follow logs
```

### Connecting a DB client

Host `localhost`, port **5433**, user `rext`, password `rext`, database `rext`.

---

## 2. Frontend — runs natively

```bash
cd rext-admin
cp .env.local.example .env.local    # then add your keys
npm install
npm run dev
```

The app is on **http://localhost:3000** and talks to the backend on 2024.

`.env.local.example` already points at the right place:

```
BACKEND_API_URL=http://127.0.0.1:2024
```

Because the backend publishes port 2024 to your host, the frontend reaches it at
`127.0.0.1` exactly as if it were running natively. Nothing about the frontend
changes just because the backend moved into Docker.

---

## Daily workflow

```bash
# terminal 1
cd rext-backend && docker compose -f docker-compose.dev.yml up

# terminal 2
cd rext-admin && npm run dev
```

Edit backend Python or frontend TypeScript — both reload automatically.

Stopping:

```bash
docker compose -f docker-compose.dev.yml stop   # keeps data
docker compose -f docker-compose.dev.yml down   # removes containers, keeps volumes
docker compose -f docker-compose.dev.yml down -v # DELETES the local database too
```

---

## Notes and gotchas

**`docker-compose.yml` vs `docker-compose.dev.yml`.** The plain
`docker-compose.yml` in this repo is the Coolify/production file. It pulls a
prebuilt image from ghcr.io and joins Coolify's external network, so it will not
work on your laptop. Always pass `-f docker-compose.dev.yml` locally.

**Port 2024 already in use.** Something else is bound to it — often a previously
running `langgraph dev`. Stop it, or change the left-hand side of `'2024:2024'`
in `docker-compose.dev.yml`.

**Changed dependencies and imports fail.** Rebuild the image; `uv.lock` is baked
in at build time, not read from the mount.

**Windows file watching.** If hot reload does not fire, keep the repo on the
native filesystem (`C:\...`) rather than a network or WSL-crossed path.

**Local data is disposable.** The dev database is a Docker volume with seed-free
throwaway data. It is not connected to staging or production in any way, and
nothing here can reach either.
