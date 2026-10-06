# Working on this repository

The Rext AI backend: FastAPI mounted as the HTTP app of a LangGraph server (`langgraph.json`), SQLAlchemy 2 (async) on PostgreSQL with Alembic migrations, Redis, the content-generation graph under `src/flow/`, the API under `src/api/`, the business logic under `src/services/`. Python 3.11 only; `uv` manages the environment. Its clients are the dashboard (`revnix/rext-admin`) and the Shopify app in `rext/`.

Codex and Claude Code both read this file (`CLAUDE.md` imports it). Keep it under 150 lines; procedures live in skills, the map of the code in `ARCHITECTURE.md`. The rework's plan, rules and tasks are in the private repository `revnix/rext-control`; a session working one of its tasks reads its `app/BRIEF.md` before anything else. Its clone sits beside this one, so from a rework worktree its scripts are `../rext-control/scripts/app/`.

## Branches

- **`main` is what production runs.** Never branch from it, target it or push to it: a push to `main` builds the `:latest` image and deploys production (`.github/workflows/production.yaml`).
- **`stage` is the base branch.** Every branch starts from `origin/stage` and every pull request targets `stage`. **A merge is a deploy:** a push to `stage` that touches the backend's paths builds the `:stage` image and deploys the staging server (`.github/workflows/stage.yaml`).
- One task, one branch, one pull request, kept small. Rework branches are named `app/<task>-<slug>`, each in a worktree of its own, and are merged by `../rext-control/scripts/app/merge.sh` (rebase and merge), never by hand.
- The team merges here daily. Rebase on `origin/stage` before your checks and before your merge, push your own branch with `--force-with-lease`, and never rewrite a commit that is not yours. A rework clone keeps no tracking ref for a task branch, so the bare flag is refused as stale: name the head you last pushed (the pull request shows it), `git push --force-with-lease=<branch>:<that sha> origin <branch>`.
- For Claude Code sessions, `.claude/settings.json` and the hooks in `.claude/hooks/` refuse reading an env file (every `.env` name and `.envrc` but `*.example`, through any tool or program; `test -s` and `grep -c` stay allowed), `docker push`, `gh workflow run`, a push to `main`, `staging` or `stage` or of every branch, and a forced push other than `--force-with-lease`.

## Secrets, data and money

- `.env` holds the database address, the signing secrets and the provider keys. Never commit, print or paste a value from it; `test -s .env` checks that it exists, and `.env.example` lists the names. `scripts/db.py seed` prints the super admin's password: never run it where its output is kept.
- Rework sessions use the local stack only: PostgreSQL at `127.0.0.1:5441`, Redis at `127.0.0.1:6381`, the shared backend at `127.0.0.1:2024`. `../rext-control/scripts/app/db.sh guard` fails unless `.env` points there; run it before a migration, a server or the tests.
- A migration is worked on a cloned database (`db.sh clone rext_app_<word>`), with a dump before and the row counts compared after (the `rext-app-db-safety` skill). Never run a migration against a database you did not clone or seed yourself, and never edit a migration once it has been applied anywhere.
- The tests use the database `POSTGRES_URI_CUSTOM` names (falling back to `postgresql://localhost/mobeen`) and write rows to it: point it at the test database, never at one with content. `tests/conftest.py` creates no tables (its `create_all` is commented out), so the database-backed tests need the schema there already.
- Lemon Squeezy stays in sandbox mode (`LEMONSQUEEZY_SANDBOX_MODE=true`). OpenAI, DataForSEO and Tavily cost money on every call: a real generation run only when the task is about the workflow, never a loop or a load test.
- No AI attribution anywhere: no co-author trailers, no "generated with" lines, no mention of AI tools in commits, pull requests, comments or code.

## Commands

Python 3.11 (`.python-version`) and uv (`uv.lock`).

```sh
git config core.hooksPath .githooks                  # once per clone: the import check and ruff on staged files at every commit
uv sync --frozen                                     # the environment from uv.lock (rework worktrees come synced)
uv run ruff check <files> && uv run ruff format --check <files>   # the files you changed; the tree has about 3,700 old findings
uv run python scripts/check_imports.py --tracked     # import integrity, as CI runs it
export POSTGRES_URI_CUSTOM="$(../rext-control/scripts/app/db.sh test-url --raw)"   # the test database; never echo it
uv run pytest -q --no-cov -o addopts= tests/<area>   # the tests of the area you changed; `uv run pytest -q` is the whole suite with the 57 % floor
uv run python scripts/db.py status                   # migration status; db.py migrate, seed, reset and store act on .env's database
uv run langgraph dev --no-browser --port <port>      # the API and the graph from this checkout (rework: run.sh backend --own)
```

- About a quarter of the suite fails on `stage` today, many of those because the test database holds no application tables yet (task 0.5, rext-control#200, sets it up and triages the rest). A branch is judged by the tests that pass on the base and fail on the branch, which is what `check.sh` compares.
- Never reformat files you did not change: `ruff format` on the whole tree rewrites hundreds of them.

## Code

Read `ARCHITECTURE.md` before your first change: the server, the graph and its gates, credits and billing, the workspace pipeline, the local run and the traps.

- **The graph** (`src/flow/engines/rext.py`, registered as `agent` in `langgraph.json`): `library_router` → `serp_engine` → `seo_engine` → `content_engine`, with four human gates as `interrupt()` calls (keyword, content type, topic, outline). A gate's payload, the state shapes in `src/flow/states/` and the stream events are a contract with the dashboard: a change names the dashboard task that consumes it, and must not strand runs in flight.
- **Credits** (`src/utils/credit_manager.py`): every billed stage and its cost, 15 credits per article. Credits are charged only there; a new or changed cost is the founder's decision.
- **Routes** (`src/api/routes/`, registered in `src/api/registry/routes.py`, all under `/api/v1`): one router per area, request and response models in `src/api/schema/`. A new endpoint gets the auth dependency (`get_current_user`, `src/api/security/dependencies.py`), a permission check (`require_permissions`, `src/api/middleware/permissions.py`), a response model and a test.
- **Database:** models in `src/api/models/`; sessions in `src/api/database/` (async for routes, sync for graph nodes). The LangGraph runtime's own tables are not Alembic's (`src/api/database/langgraph_tables.py`).
- **Prompts** (`src/flow/prompts/`): reviewed like code; no prompt names AI detectors or promises to get past them.
- **Logging:** structlog (`src/api/lib/logging_config.py`); no personal data and no secret in a log line.
- Match the code around your change: its naming, its structure, how much it comments; `ruff format` decides the rest.

## Before a pull request

1. The branch holds the current `origin/stage`, and `../rext-control/scripts/app/check.sh` passes (ruff on the changed files, the import check, no test that passes on `stage` failing here); `--full` before merging a migration or a billing change. Outside the rework, run the commands above.
2. A migration's pull request shows the row counts before and after, on the clone.
3. On GitHub, `PR_CHECKS` also runs `🧪 Tests` on a fresh PostgreSQL: one migration head, valid migration ids and migrations that apply to an empty database are required; the test suite's result is reported in the job summary and does not block yet.
4. The pull request body says what changed, why, how it was checked and what is not in it, and names the task.

## Code Review Rules

For the reviewer (Codex reads this section). Flag, in the lines a pull request adds or changes:

- an endpoint without the auth dependency, or a permission check that runs after the work it guards;
- a query that trusts a user, workspace or role id from the request without checking it against the caller;
- raw SQL built with string interpolation;
- a blocking call (synchronous HTTP, file or database I/O) in an async path;
- a change to a LangGraph state, an `interrupt()` payload or a stream event without the dashboard task that consumes it;
- a credit charged or refunded outside `src/utils/credit_manager.py`, or a price, plan or credit amount changed;
- a migration that edits one already applied, or drops data without a step that keeps it;
- personal data or a secret in a log line;
- a prompt that names AI detectors;
- a change that would push or deploy to `main`.

Do not repeat what ruff already enforces.
