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

You do **not** need Python, `uv`, or a local Postgres/Redis/MinIO. That is the
point: the backend toolchain lives entirely inside the container.

### What you need

| Tool | Minimum | Why | Check |
| --- | --- | --- | --- |
| Docker Desktop | 24+ | runs the backend and all infrastructure | `docker --version` |
| Docker Compose | v2 | `docker compose`, not `docker-compose` | `docker compose version` |
| Node.js | 20.9+ (LTS) | Next.js 16 requires it | `node --version` |
| npm | 10+ | ships with Node 20 | `npm --version` |
| Git | any recent | | `git --version` |
| Free disk | ~15 GB | images, volumes and build cache | `docker system df` |
| RAM | 8 GB, 16 GB comfortable | Postgres x2, Redis x2, MinIO, API | |

### Verify everything at once

Run this before you start. Every line should print a version, and the last line
should say the daemon is reachable.

```bash
docker --version
docker compose version
node --version
npm --version
git --version
docker info > /dev/null 2>&1 && echo "Docker daemon: OK" || echo "Docker daemon: NOT RUNNING"
```

If `node --version` prints below `v20.9.0`, or any line errors, fix that first —
the setup will fail in confusing ways otherwise.

### Windows: virtualization must be enabled

Docker Desktop on Windows runs through WSL2, which needs hardware
virtualization. This is the single most common thing that blocks a new machine.

**Check it:**

Open Task Manager → Performance → CPU and look for **Virtualization: Enabled**.
Or from PowerShell:

```powershell
systeminfo | Select-String "Hyper-V|Virtualization"
wsl --status
```

**If virtualization is disabled**, it is switched off in firmware, not in
Windows. Reboot into BIOS/UEFI (usually `F2`, `F10` or `Del` during startup) and
enable:

- Intel CPUs: **Intel VT-x** (sometimes "Intel Virtualization Technology")
- AMD CPUs: **AMD-V** or **SVM Mode**

Save, reboot, and re-check Task Manager.

**If WSL2 is missing or out of date:**

```powershell
wsl --install          # first-time install
wsl --update           # existing install
wsl --set-default-version 2
```

Then in Docker Desktop → Settings → General, confirm **Use the WSL 2 based
engine** is ticked.

### Docker Desktop resources

Settings → Resources. The stack runs six containers, two of them Postgres:

- Memory: **at least 4 GB**, 6–8 GB is better
- Disk image size: leave room for ~15 GB

Symptoms of too little memory are containers being killed mid-startup, or
Postgres exiting with code 137.

### Ports that must be free

The stack binds these on your machine. If one is taken the stack will not start.

| Port | Service |
| --- | --- |
| 2024 | backend API |
| 3000 | frontend (`npm run dev`) |
| 5433 | Postgres (application) |
| 5434 | Postgres (LangGraph) |
| 6379 | Redis (cache) |
| 6380 | Redis (LangGraph) |
| 9000, 9001 | MinIO and its console |

Check for conflicts:

```bash
# macOS / Linux
lsof -i :2024 -i :3000 -i :5433 -i :5434 -i :6379 -i :6380 -i :9000

# Windows PowerShell
Get-NetTCPConnection -LocalPort 2024,3000,5433,5434,6379,6380,9000 -ErrorAction SilentlyContinue
```

Nothing returned means you are clear. Ports 5433/5434/6380 were chosen
specifically so a Postgres or Redis already installed on your machine (on the
default 5432/6379) does not conflict.

### Network reachability

The first build downloads from several hosts. Some networks block a subset of
them, which shows up as a build that appears to hang rather than fail, because a
blocked host stalls until TCP times out.

```bash
for url in https://registry-1.docker.io/v2/ https://pypi.org/simple/ \
           https://files.pythonhosted.org https://deb.debian.org; do
  printf "%-45s " "$url"
  curl -s -o /dev/null -w "%{http_code}\n" --max-time 8 "$url" || echo "UNREACHABLE"
done
```

Any HTTP status is fine — `401` from the Docker registry and `200` from the
others are all healthy. Only `UNREACHABLE`, or a `000`, means blocked. Note
these blocks can be **intermittent**: a host that times out once may work
minutes later, so re-run the check before concluding anything is permanently
broken.

The most reliable single test is simply:

```bash
docker pull hello-world
```

**If `registry-1.docker.io` is unreachable**, Docker Hub is blocked for you.
Pull the base images through Google's mirror and re-tag them locally, then build
as normal:

```bash
for pair in "library/python:3.11-slim|python:3.11-slim" \
            "pgvector/pgvector:pg17|pgvector/pgvector:pg17" \
            "library/redis:7-alpine|redis:7-alpine" \
            "minio/minio:latest|minio/minio:latest"; do
  src="mirror.gcr.io/${pair%%|*}"; dst="${pair##*|}"
  docker pull "$src" && docker tag "$src" "$dst"
done
```

Alternatively add `"registry-mirrors": ["https://mirror.gcr.io"]` under Docker
Desktop → Settings → Docker Engine, and restart Docker.

**If the Playwright CDN is blocked**, build with the browser download skipped:

```bash
docker compose -f docker-compose.dev.yml build --build-arg INSTALL_BROWSERS=0 api
```

Everything works except code that launches a real browser.

### If something is still wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| `docker: command not found` | Docker Desktop not installed or not on PATH | install it, then reopen your terminal |
| `Cannot connect to the Docker daemon` | Docker Desktop not started | launch it and wait for the whale icon to settle |
| `docker-compose: command not found` | using the old v1 syntax | use `docker compose` (space, not hyphen) |
| WSL2 errors on Windows | virtualization off, or WSL out of date | see the virtualization section above |
| Build hangs with no output | a download host is blocked | run the reachability check above |
| `port is already allocated` | something owns that port | free it, or change the left-hand side of the mapping in `docker-compose.dev.yml` |
| Postgres exits with code 137 | Docker was killed for memory | raise the memory limit in Docker Desktop |
| `no space left on device` | build cache filled the disk | `docker system prune -a` (removes unused images) |

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

**Local data is disposable.** The dev database is a Docker volume holding
throwaway data seeded by the migrations. It is not connected to staging or
production in any way, and nothing here can reach either.

---

## Optional: managed services instead of local containers

On a machine with 8 GB of RAM, running an IDE, a browser and six containers gets
tight. You can move the infrastructure into free managed services and keep only
the API local. Expect to free roughly **500–600 MB**.

This is entirely optional and nobody needs to do it. Read the trade-offs at the
bottom first — for most people, keeping everything local is still the better
experience.

### The one rule that makes this work

`docker-compose.dev.yml` sets the connection URLs in its `environment:` block,
and **that overrides `.env`**. So putting a Neon URL in `.env` alone does
nothing. For each service you move you must either:

- edit the value in `docker-compose.dev.yml`, **or**
- delete that line from the compose file so the value falls through from `.env`

The second is cleaner: the compose file stays shared, and each developer's
`.env` holds their own endpoints. All examples below use it.

### Postgres → Neon

1. Create a project at [neon.tech](https://neon.tech). Give each developer their
   own **branch** so you are not sharing one database.
2. In the Neon SQL editor, enable pgvector once per branch:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. In `docker-compose.dev.yml`, delete this line from the `api` **and**
   `migrate` `environment:` blocks (it is a YAML anchor, so remove it once from
   `api`, which `migrate` inherits):
   ```yaml
   POSTGRES_URI_CUSTOM: 'postgresql://rext:rext@postgres:5432/rext'
   ```
4. Comment out the whole `postgres:` service, its `pgdata` volume, and the
   `postgres:` entry under `migrate.depends_on`.
5. Put your Neon URL in `.env`:
   ```
   POSTGRES_URI_CUSTOM=postgresql://USER:PASSWORD@ep-xxx.region.aws.neon.tech/neondb?ssl=require
   ```

> **Use `?ssl=require`, not Neon's copy-paste `?sslmode=require&channel_binding=require`.**
> Alembic strips those two parameters itself (`alembic/env.py` pops `sslmode`
> and `channel_binding`), so migrations would work — but the app's engine in
> `src/api/database/async_database.py` only rewrites the scheme and passes the
> rest through to asyncpg, which does not accept `sslmode` and will fail at
> runtime. `ssl=require` is the asyncpg spelling and works in both paths.

### langgraph-postgres → Neon

Same steps, a second Neon branch or database. Remove this line from the `api`
`environment:` block:

```yaml
DATABASE_URI: 'postgresql://rext:rext@langgraph-postgres:5432/langgraph'
```

Comment out the `langgraph-postgres:` service, the `langgraphdata` volume, and
its entry in `migrate.depends_on`. Then in `.env`:

```
DATABASE_URI=postgresql://USER:PASSWORD@ep-yyy.region.aws.neon.tech/langgraph?ssl=require
```

Keep this separate from the application database — LangGraph creates and
migrates its own tables, and mixing them makes a reset messy.

### redis + langgraph-redis → Upstash

1. Create two databases at [upstash.com](https://upstash.com) (one for cache,
   one for the LangGraph queue). Copy the **TCP** endpoint, not the REST URL.
2. Remove these three lines from the `api` `environment:` block:
   ```yaml
   REDIS_URL: 'redis://redis:6379/0'
   CACHE_URL: 'redis://redis:6379/0'
   REDIS_URI: 'redis://langgraph-redis:6379'
   ```
3. Comment out the `redis:` and `langgraph-redis:` services, the `redisdata`
   volume, and their entries under `api.depends_on`.
4. In `.env` — note `rediss://` with two s's, Upstash is TLS-only:
   ```
   REDIS_URL=rediss://default:PASSWORD@xxx.upstash.io:6379
   CACHE_URL=rediss://default:PASSWORD@xxx.upstash.io:6379
   REDIS_URI=rediss://default:PASSWORD@yyy.upstash.io:6379
   ```

> Upstash's free tier allows **10,000 commands per day**. The LangGraph queue
> polls continuously, so watch your usage for the first day before relying on
> it — this is the service most likely to hit a free limit.

### minio → Cloudflare R2

1. In the Cloudflare dashboard create an R2 bucket named `rext-media`, and an
   API token with **Object Read & Write**.
2. **Create the bucket yourself before starting the app.** On boot
   `src/utils/storage.py` calls `_ensure_bucket_exists()`, which tries to create
   the bucket and apply a policy — behaviour R2 does not fully support.
3. Remove these from the `api` `environment:` block:
   ```yaml
   MINIO_ENDPOINT: 'minio:9000'
   MINIO_ACCESS_KEY: minioadmin
   MINIO_SECRET_KEY: minioadmin
   MINIO_USE_SSL: 'false'
   ```
4. Comment out the `minio:` service, the `miniodata` volume, and its
   `api.depends_on` entry.
5. In `.env` — the endpoint is a bare host, no `https://` prefix, because the
   code builds the scheme from `MINIO_USE_SSL`:
   ```
   MINIO_ENDPOINT=<ACCOUNT_ID>.r2.cloudflarestorage.com
   MINIO_ACCESS_KEY=<R2 access key id>
   MINIO_SECRET_KEY=<R2 secret access key>
   MINIO_BUCKET=rext-media
   MINIO_USE_SSL=true
   ```

> `src/utils/storage.py` hardcodes `region_name='us-east-1'` and path-style
> addressing. R2 normally tolerates this, but if you get
> `SignatureDoesNotMatch` or a 401, that region is why — R2's own region is
> `auto`, and changing it means a code change, not an env var.

### Trade-offs

**Latency.** Every query and cache hit becomes an internet round trip. On a slow
or unreliable connection the app will feel noticeably worse than local
containers.

**No offline development.** With everything local you can work on a plane. With
managed services, no internet means no backend.

**Shared state.** One Neon database shared across the team means people
overwrite each other's data. Neon branches solve this, but each developer needs
their own.

**Free-tier ceilings.** Neon suspends idle databases, so the first request after
a pause is slow. Upstash's daily command cap is the one to watch.

**A cheaper alternative.** If the goal is purely memory, merging `postgres` and
`langgraph-postgres` into a single container with two databases saves a
container and about 150 MB, costs nothing, and keeps every advantage of running
locally. Capping Docker Desktop at 4 GB (Settings → Resources) also stops it
starving your IDE.
