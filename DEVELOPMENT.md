# Development

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
