# Architecture: the Rext AI backend

A map of how this repository is put together, for whoever is about to change it. It describes the code on `stage` as it is (checked 2026-10-05); the audit behind it is `revnix/rext-control`'s `reports/app/02-rext-backend-audit.md`, and the pipeline step by step, with file and line, is that repository's `reports/part3/04-the-app.md`. Where this file and the code disagree, the code wins: say so and fix the file.

## Overview

A LangGraph server that mounts a FastAPI application as its HTTP app (`langgraph.json`: the graph `agent` is `main:graph`, the app is `src/api/server.py:app`). One process on port 2024 serves three things: the REST API under `/api/v1` (the spec at `/openapi.json`, the docs at `/docs`), the LangGraph server's own endpoints for threads, runs and the store, which the dashboard's generation routes call to start and resume runs, and the server-sent events the dashboard follows. `langgraph.json`'s `auth` entry (`src/api/security/auth.py`) requires the user's access token on those LangGraph routes, stamps every thread's `metadata.owner` and shows a user only their own threads; assistants are read-only. `server.py` at the root starts the API alone with uvicorn, without the graph.

- **Auth:** JWT, HS256, an access token of 30 minutes and a refresh token of 7 days by default (`src/api/security/token_utils.py`, `src/api/config.py`); `get_current_user` (`src/api/security/dependencies.py`) also checks the blacklist and that the session row is active. Roles and permissions are database rows, checked by `require_permissions` and `PermissionChecker` (`src/api/middleware/permissions.py`).
- **Data:** PostgreSQL with pgvector holds the application's tables (SQLAlchemy 2, Alembic under `alembic/versions`) and the LangGraph runtime's own tables (checkpoints, threads, runs, the store), which the runtime creates and migrates itself. Every component reads the address from `POSTGRES_URI_CUSTOM`. Redis serves the cache and the rate limiter; without it the cache is skipped and the rate limiter counts in memory.
- **Outside services:** OpenAI (writing, scoring, embeddings, the image), DataForSEO (SERP, keyword overview, backlinks), Tavily (research), Lemon Squeezy (billing and its webhooks), Resend (email, or a mock provider locally), MinIO or S3 (media), Sentry, LangSmith (optional tracing).
- **Start-up** (`src/api/server.py`, the lifespan): Sentry, the pending Alembic migrations (in the image only, below), the Redis cache, Lemon Squeezy's plan variant ids synced from the environment into `subscription_plans`, the APScheduler jobs (`src/tasks/scheduled_tasks.py`, `src/api/tasks/`: trials, grace periods, dunning, usage roll-ups, webhook reprocessing), the MinIO check, the vector store. Middleware: proxy headers, request ids, structlog, Sentry user context, the error handler, security headers, the rate limiter, CORS with explicit origins.

```text
main.py                     builds the graph (main:graph)
server.py                   the API alone, without the graph
langgraph.json              the graph, the HTTP app, the checkpointer's 3-day TTL, the store, the image's extra build lines
src/api/
  server.py                 the FastAPI app: lifespan, middleware, health endpoints
  registry/routes.py        registers every router under /api/v1
  routes/                   one router per area: users, workspaces, content, combine_user, integrations,
                            subscriptions, invitations, roles, permissions, security, audit, notifications,
                            events (SSE), email, shopify, admin, health
  schema/                   pydantic request and response models
  models/                   SQLAlchemy models
  security/                 JWT, the dependencies, the LangGraph auth handler (auth.py)
  middleware/               permissions, rate limits, plan limits (usage_limiter.py), security headers, errors
  database/                 the async and sync engines and sessions
  lib/                      logging (structlog), Sentry, error capture
  tasks/, cache/, tool/     scheduled jobs, the Redis cache, the free SEO tools' public endpoints
                            (tool/limits.py bounds them per visitor and per day)
src/flow/
  engines/rext.py           the top-level graph
  engines/serp, seo, content, router, competitors, agent      the stages and the gates
  states/                   the graph's state shapes
  prompts/                  the prompts
  model/                    the LLM manager and the structured outputs
  store/rext_store.py       the LangGraph store (pgvector)
  image_generation/         the featured image
src/services/               the business logic: subscriptions, trials, credits and usage, dunning and grace,
                            refunds, invitations, members, roles, brand voice and personas, the workspace pipeline,
                            notifications, email, SSE
src/providers/              payment (Lemon Squeezy) and email providers
src/web/                    the WordPress publisher and the Shopify connector and bridge
src/utils/credit_manager.py every billed stage and its cost; the only place credits are charged
scripts/                    db.py (reset, migrate, seed, status, store), check_imports.py, env_example.py (.env.example from the settings), audits and one-off fixes
tests/                      pytest; tests/conftest.py needs a real PostgreSQL; the coverage floor is 57 %
rext/                       the Shopify app (Node), built and deployed by the same workflows
```

## The pipeline

`START` → `library_router`, which checks the balance against a whole article's cost and sends a library keyword straight to `content_engine` (or ends at `insufficient_credits`) → `serp_engine` (the SERP and the competitors; `has_organic_results` ends the run at `no_serp_data`, an error the dashboard shows, when the search returned nothing) → `seo_engine` (the keyword overview and backlinks, `save_keyword_research` saving them to the keyword Library, then **gate 1**, the keyword, in `keyword_recommendation`) → `keyword_router`, which goes back to `serp_engine` if the keyword or country changed (or on to `no_serp_data`) → `content_engine`: `recommend_content_type`, `content_type` (**gate 2**), `generate_topics`, `topic_generation` (**gate 3**; new titles go back to `generate_topics`), keyword clustering, `generate_outline` and `review_outline` (**gate 4**, accept or reject with feedback), `generate_content`, `validate_content` and `repair_content`, `humanize_content`, `final_validate_content`, `review_content`, `persist_content` (the article is saved as a draft and a notification sent). Each gate is an `interrupt()`; the dashboard resumes the thread with the user's answer. LangGraph runs a node again from its start on resume, so a gate's node holds only its `interrupt()`: the model call or write it needs runs in the node before it and leaves its result in the state. The dashboard starts runs with `onDisconnect: "continue"`, so a run finishes after the user leaves; under `langgraph dev` the checkpointer is the in-memory runtime and runs vanish on restart.

## Credits and billing

`src/utils/credit_manager.py` holds the cost of each billed stage (`serp_seo` 1, `title_generation` 1, `generate_outline` 1 per call, `deep_research` 4, `content_drafting` 1, `featured_image` 1, `humanization` 5, `eeat_optimization` 1: 15 for an article) and is the only place credits are charged. Plans, trials, the grace period, dunning and refunds live in `src/services/` (`*subscription*`, `trial_service.py`, `usage_tracking_service.py`, `grace_period_service.py`, `dunning_service.py`, `refund_service.py`); Lemon Squeezy's webhooks arrive at `src/api/routes/subscriptions/` and are handled by `lemonsqueezy_webhook_service.py`. A new cost, plan or credit amount is a product decision, not a code change. The refund rule (within 14 days of a payment, the whole payment back if fewer than 100 credits were used since it; no partial refunds) is `credit_rule_refusal` and `create_request` in `refund_request_service.py`; its two numbers are in `refund_requests.py`, and the plan catalogue serves them (`refund`). An admin logging an emailed request (`enforce_policy=False`) reviews it instead.

Credits on top of the month's are credit grants (`src/services/credit_grants.py`): a promotion's bonus, or credits a super admin added (`src/services/admin_credits.py`, behind `/api/v1/admin/users/{user_id}/credits`, which also deducts and resets the month's credits, every change audited with its reason). Every spend takes grants with an expiry first, soonest first, then the month's credits, then grants without an expiry. A refund forfeits only promotion grants, and only they count as used; an admin's deduction or reset of the month's credits is kept as the period's adjustment (`subscription_metadata.admin_credit_adjustment`), so the refund rule's "used" stays what was used.

A super admin can change a user's plan or move a trial's end later (`src/services/admin_plan_changes.py`, behind `/api/v1/admin/users/{user_id}/plan` and `/trial`). The plan change is the customer's own (`SubscriptionService.upgrade`) made by an admin: Lemon Squeezy takes the new variant first and the row changes only once it agreed, the plan changes at once, and the admin chooses the money: nothing now and the new price from the next renewal (the default, `disable_prorations`), or the prorated difference invoiced now (an upgrade only). A trial isn't moved to a paid plan there. Each change carries a reason and an audit entry (`admin.plan_changed`, `admin.trial_extended`).

## The workspace pipeline

`POST /api/v1/workspaces/` creates the rows, mints an `operation_id`, starts `run_workspace_pipeline` (`src/services/workspace_pipeline.py`) as an asyncio task inside the API process and answers at once. The dashboard follows `GET /api/v1/events/{operation_id}`, served from the in-memory `EventStreamManager` (`src/services/sse_service.py`), so the service runs as one replica. The pipeline scrapes the site (a fast scraper, with a crawl4ai browser as the fallback), embeds it, writes the brand voice, personas and competitors, and takes one to two minutes; a restart during it ends the run. Each run (at creation, on a brand-voice refresh or a retry) is recorded on the workspace's row (`pipeline_status`, `pipeline_operation_id`, `pipeline_started_at`). `GET /workspaces/{id}` and the slug and detail routes show it as `pipeline`: a row still marked running that started before the process did, or more than ten minutes ago, reads as `interrupted` (`pipeline_state` in `src/services/workspace_service.py`). `POST /workspaces/{id}/pipeline/retry` runs a failed or interrupted run again, and a refresh or retry is refused while a run is in progress.

Each step reports on the operation's stream: `<step>.started`, then `<step>.completed` with what it found (`scrape`: the page's title and word count; `brand_voice`: the drafted voice; `competitor_discovery`: the sites) or `<step>.failed`, and `pipeline.completed` at the end. Between those, progress events (status `progress`, the step's bare name) say what the run has found so far, for the screen that shows the workspace taking shape (revnix/rext-control#845): `scrape` with `pages` (each page read and what it is), `personas` with `people` (each person the moment the personas are saved, which is after `brand_voice.completed`), and `competitor_discovery` with `stage` (`searching` with the number of queries, then `checking` with the number of candidates). A progress event ends no step and is never worth the run: one that can't be sent is logged and passed over.

A workspace can also be made from its name alone (`POST /api/v1/workspaces/` with neither `url` nor `description`), so nobody is stopped at the create form: its rows are made, no brand voice is written and no run starts, the answer's `operation_id` is null and its `pipeline` reads `not_started`. It is set up later: a website saved with `PUT /workspaces/{id}` and read with the brand-voice refresh, or a description sent to `POST /workspaces/{id}/pipeline/retry` (`{description}`), which keeps it as the brand voice's `about` and runs the voice-only draft below.

A business with no website yet sends `description` in place of `url` (20 to 1,000 characters), and may send `brand_name`, what its owner calls it: that name is written as the brand voice's brand name, the draft is told it, and no draft replaces a name the brand voice already holds (the same field on the retry route). The description is written as the brand voice's `about` in the create request, word for word, and the run is then the brand-voice step alone, on the same operation and events: `_description_voice_generator` drafts the customer profile, selling position, audience, tone and content pillars from it and may use nothing else. No site is read, so there are no `scrape` or `competitor_discovery` events, no personas, no competitors and no favicon, and `workspace.url` stays null. A retry of such a run drafts again from the stored `about`; a brand-voice refresh is refused until the workspace has a website (`PUT /workspaces/{id}`), after which the refresh is the usual read of the site.

## Running locally

The rework's local stack runs on the office laptop: PostgreSQL with pgvector, Redis, MinIO and this service built from the `Dockerfile`, reached through SSH tunnels at `127.0.0.1:5441`, `6381`, `9000` and `2024`; the scripts in `../rext-control/scripts/app/` reach its containers through the `hp` Docker context. `run.sh` drives it, `db.sh` guards the addresses, and `run.sh backend --own` runs a checkout's own instance on another port. Outside the rework, `uv run langgraph dev --no-browser --port 2024` with a `.env` built from `.env.example` runs the API and the graph against your own PostgreSQL and Redis. Without MinIO the API serves and `/health` reports storage as unhealthy (it answers 503 for that only in production), and uploads fail.

## Traps

- The LangGraph runtime's and the store's tables are not Alembic's: `alembic/env.py` leaves them out of autogenerate (`src/api/database/langgraph_tables.py` names them). Never drop them, and a change to a state shape strands the generations in flight.
- The store (`src/flow/store/rext_store.py`) connects with psycopg directly and needs pgvector; it must not go through PgBouncer.
- The tests write to the database `POSTGRES_URI_CUSTOM` names, and `tests/conftest.py` creates no tables (its `create_all` is commented out): the schema must be migrated there first, and it must never be a database with content.
- `scripts/db.py seed` prints the super admin's password from `.env`.
- The image comes from `langgraph build`, which generates the Dockerfile from `langgraph.json` (its `dockerfile_lines` install the lock's runtime packages). The committed `Dockerfile` must equal what `langgraph.json` generates, and a test compares the two: change `langgraph.json` and regenerate it.
- A push to `stage` deploys staging and a push to `main` deploys production; nothing is pushed there directly. Both workflows write the commit to `src/api/build_commit.txt` before `langgraph build` (`/health/live` reports it, `src/api/build_info.py`), publish and deploy only from their own branch, and refuse a stale run (on `stage`, per component: the backend's paths and the Shopify app's `rext/`, as the changes filters list them). Both restart their Coolify Service with `latest=true` (`/api/v1/deploy` only starts a Service with the images it already has) and wait until `/health/live` reports the commit, failing after 15 minutes. `latest=true` pulls every image in a Service, so pgbouncer and minio-mirror are pinned by digest in both (#423).
- **A deploy migrates the database as it starts** (`src/api/database/migrate_on_start.py`, G32): the image sets `MIGRATE_ON_START=true`, so the server applies the pending migrations under a Postgres advisory lock before it serves, over the direct address when one names the app's database, and refuses to start if one fails. A checkout (tests, `langgraph dev`) never migrates. So a migration merged into `stage` runs on staging's database at that deploy, and one that can't run takes staging down until it's fixed: try it on a clone first. **Before the first deploy of this to `main`, live's database must already be at the baseline revision `3c9e1e5d5028` or later** (G23, rext-control#310): a database Alembic hasn't stamped would get the whole history replayed onto existing tables, fail, and the server wouldn't start.
- The repository has about 3,700 old ruff findings: new and changed files are clean, untouched files are not reformatted.
- `.githooks/pre-commit` runs only after `git config core.hooksPath .githooks`.
