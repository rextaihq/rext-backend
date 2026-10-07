# Development

## Running locally

`docker-compose.yml` is the deployed Coolify stack (an external `coolify` network, Traefik labels, the GHCR images, no published ports), not a development file. Locally the backend runs from the checkout with `uv`, against PostgreSQL and Redis in Docker. (The rework's sessions use the shared stack on the office laptop instead: `ARCHITECTURE.md`, "Running locally".)

1. **The data services.** PostgreSQL needs pgvector (the LangGraph store keeps embeddings, `src/flow/store/rext_store.py`), so use the image the stack uses:

   ```bash
   docker run -d --name rext-db -e POSTGRES_USER=rext -e POSTGRES_PASSWORD=rext -e POSTGRES_DB=rext_app \
     -p 5432:5432 pgvector/pgvector:pg17
   docker exec rext-db createdb -U rext rext_app_runtime          # the LangGraph runtime's database
   docker run -d --name rext-redis -p 6379:6379 redis:7-alpine --maxmemory 128mb
   ```

   MinIO is optional: without it the API serves, `/health` reports storage as unhealthy, and uploads and featured images fail. Set `REXT_STORAGE_SKIP_BUCKET_CHECK=1` to skip the bucket check at start.
2. **The environment.** Python 3.11 only (`.python-version`); `uv` installs it if it's missing. `uv sync --frozen` builds the environment from `uv.lock`. It is several GB, since crawl4ai brings torch, transformers and Playwright.
3. **`.env`.** Copy `.env.example`, fill in its top part (the database addresses, the two secrets, the OpenAI, Tavily and DataForSEO keys), and keep these for a local checkout:
   - `ENVIRONMENT=development`;
   - `REQUIRE_EMAIL_VERIFICATION=false`, so accounts log in without email;
   - `EMAIL_PROVIDER=mock`;
   - `LEMONSQUEEZY_SANDBOX_MODE=true`;
   - `SCHEDULER_ENABLED=false`, so the billing and trial jobs never act on accounts.

   Never commit `.env`. `.env.example` lists every name the code reads (`scripts/env_example.py` keeps it so).
4. **The database.** `uv run python scripts/db.py migrate` applies the migrations, sets up the store's tables and seeds what every database needs (below). `uv run python scripts/db.py status` shows the revision. `scripts/db.py reset` drops the application's data: never against a database you didn't create yourself.
5. **Run.** `uv run langgraph dev --no-browser --port 2024` serves the API and the graph (`langgraph.json` loads `.env`); `/ok` answers once it's up and `/docs` lists the endpoints. Under `langgraph dev` the runtime keeps runs in memory, so a restart loses them. `uv run python server.py` serves the API alone, without the graph.
6. **Optional:** the workspace crawler's browser fallback needs `uv run crawl4ai-setup` (`uv run crawl4ai-doctor` checks it).

A real generation run calls OpenAI, DataForSEO and Tavily, and each call costs money.

**Tests** write to the database `POSTGRES_URI_CUSTOM` names (falling back to `postgresql://localhost/mobeen`), so point it at a database of their own: `uv run pytest -q --no-cov -o addopts= tests/<area>`. About a quarter of the suite fails on `stage` today (`tests/quarantine.list`); a branch is judged by the tests that pass on the base and fail on it.

## Databases

Two kinds of data live on the PostgreSQL server:

| | Setting | What | Who creates the tables |
|---|---|---|---|
| The application | `POSTGRES_URI_CUSTOM` | everything in `src/api/models`, and the LangGraph store (the keyword library, `src/flow/store/rext_store.py`) | Alembic (`alembic/`) and `scripts/seed.py`; the store sets up its own tables |
| The LangGraph runtime | `DATABASE_URI` | threads, runs, checkpoints, crons, assistants | the LangGraph server, when it starts |

The application never reads the runtime's tables by SQL; the dashboard reaches them through the LangGraph API only. They can share one database (Alembic leaves the runtime's tables alone, `alembic/MIGRATION_CONVENTIONS.md`), but the recommended layout is a database of its own for the runtime on the same server (`<app database>_runtime`): neither side can touch the other, and a backup of customer data holds no transient runtime state.

### A new database

```bash
createdb rext_app && createdb rext_app_runtime          # or CREATE DATABASE … on the server
# .env: POSTGRES_URI_CUSTOM=…/rext_app   DATABASE_URI=…/rext_app_runtime
python scripts/db.py migrate                            # alembic upgrade head + the store's tables + scripts/seed.py
langgraph dev                                           # the server creates the runtime's tables in DATABASE_URI
```

`scripts/seed.py` inserts the plans, roles, permissions, email templates, the super admin named by `SUPER_ADMIN_EMAIL` (with `SUPER_ADMIN_PASSWORD`) and the API usage rollup's row, only where they are missing.

### Stage and live after the squash of 2026-10-05

Nothing to run. Both databases are at revision `3c9e1e5d5028`, which is the new baseline's id, so `alembic upgrade head` has nothing to do (`alembic current` prints `3c9e1e5d5028 (head)`). `python scripts/seed.py` may be run at any time; on these databases it inserts nothing, because every seeded row already exists.

### Moving the runtime to its own database (stage first, then live; one time)

Who: whoever manages the backend's environment in Coolify. It takes a few minutes per environment.

1. Pick a quiet moment. A generation in progress at the switch is lost (its thread stays behind in the old database; it would have expired within three days anyway).
2. On the same PostgreSQL server, as the user the backend connects with: `CREATE DATABASE <app database>_runtime;`.
3. In the backend service's environment, set `DATABASE_URI` to that database. Leave `POSTGRES_URI_CUSTOM` (and `DATABASE_URL`, which some scripts read as the application's database) as they are.
4. Restart the backend. The LangGraph server creates its tables in the new database on start; `/ok` answers once it is up.
5. Check: start a generation from the dashboard and see it reach the keyword step.
6. A week later, take a dump of the application database, then drop the runtime's old tables from it: the names in `src/api/database/langgraph_tables.py` except the store's four (`store`, `store_migrations`, `store_vectors`, `vector_migrations`), which stay with the application.

To undo before step 6: set `DATABASE_URI` back to the application database and restart.

## Deploys

A merge into `stage` deploys staging, and a push to `main` deploys production (`.github/workflows/stage.yaml`, `production.yaml`). The backend is a Coolify Service, and `/api/v1/deploy` only starts a Service with the images it already has. So both workflows restart it with `POST /api/v1/services/{uuid}/restart?latest=true`, which pulls the new image first. The job then waits until the running server reports the commit it built, and fails after 15 minutes.

- **Production** restarts the same way since #423. A restart with `latest=true` pulls every image in the Service, so `edoburu/pgbouncer` and `minio-mirror` are pinned by digest there (and in staging's), and only the backend's image changes. Pin any new image a Service gets, or the next deploy moves it.
- **What a server runs:** `curl -s https://staging-api.rext.ai/health/live` (or `https://api.rext.ai/health/live`). `commit` is the SHA the image was built from; `unknown` means an image built before this check, or outside CI.
- **A deploy that fails on "did not run <sha>":** the image is in GHCR, but the server didn't pick it up within 15 minutes. Look at the service in Coolify (its logs, whether the pull failed), then Restart it with "Pull latest images" ticked, and check `/health/live` again. Production's error says the same.
- **A run refused as stale:** a newer commit is already on the branch, so publishing this one would roll the server back. Re-run the newest run instead, or roll back on purpose. On `stage` each component counts on its own: the backend is left out only when a newer commit touches the backend's files, the Shopify app only when one touches `rext/`, and a run whose other component is still current deploys that one and then fails with "Not deployed by this run". A comparison of 300 or more files (GitHub's limit) refuses the whole run.
- **The Shopify app** keeps `/api/v1/deploy`. Its Coolify resource isn't visible to the workflows' token, so whether it's a Service or an Application is still to be confirmed. Production's step skips it with a warning while `COOLIFY_UUID_SHOPIFY` isn't set, since no resource exists yet (Shopify is postponed).


## Migrations and seeding

- Alembic, under `alembic/versions`. A new migration takes a standard 12-character hex id (`alembic/MIGRATION_CONVENTIONS.md`): `uv run alembic revision --autogenerate -m "…"`, then read what it generated before applying it.
- Never edit a migration once it has been applied anywhere. A change to applied schema is a new migration. Migrations hold schema only: a change to seeded rows on existing databases is a migration of its own, written for that change.
- `scripts/seed.py` (also run by `scripts/db.py migrate`) inserts the plans, roles, permissions, email templates, the super admin named by `SUPER_ADMIN_EMAIL` and the API usage rollup's row, only where they're missing, so a second run changes nothing. The data is in `scripts/seeds/`. Test data isn't kept in the repository.

## Images

CI builds the image (`langgraph build`, in `stage.yaml` and `production.yaml`) and writes the commit into it, so `/health/live` can prove what a server runs. `build_push_stage.sh` and `build_push_production.sh` are the manual fallback: the same build, pushed to the same GHCR tags. Use them only when CI can't build. An image pushed by hand reports its commit as `unknown`, and the next deploy from CI replaces it.

## Conventions

**Datetimes are timezone-aware, in UTC:**
- the current time is `datetime.now(timezone.utc)`, never `datetime.utcnow()`;
- columns are `DateTime(timezone=True)` with `default=lambda: datetime.now(timezone.utc)`;
- a parsed datetime without tzinfo is taken as UTC;
- `.isoformat()` keeps the offset.

## The Shopify app bridge

A Shopify store connects in app-bridge mode. The person gives the store's address (`monitod`, `monitod.myshopify.com` or a full URL). The backend normalises it to `https://{handle}.myshopify.com` and returns the app's launch URL, `https://admin.shopify.com/store/{store_handle}/apps/{app_slug}/app/blogpost`. The integration's config keeps:
- `connection_mode: app_bridge`;
- `app_slug`;
- `app_launch_url`;
- optionally `bridge_publish_url`.

**Publishing** goes to the app:
- **Endpoint:** a `POST` to `SHOPIFY_BRIDGE_BASE_URL` plus `SHOPIFY_BRIDGE_PUBLISH_ENDPOINT` (by default `/app/api/rext/publish`).
- **Body:** JSON with `storeUrl`, `storeHandle`, `title`, `body`, `published`, `tags`, `handle`, `featureImageUrl`, `contentId` and `workspaceId`.
- **Signature:** `X-Rext-Timestamp` and `X-Rext-Signature`, the hex HMAC-SHA256 of `timestamp.payload` with `SHOPIFY_BRIDGE_SHARED_SECRET`.

Shopify is postponed: the app in `rext/` builds, but production has no resource for it yet.
