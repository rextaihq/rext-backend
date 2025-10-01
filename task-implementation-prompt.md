Review the @alembic-integration-plan.md file and based on the plan, work on the next task in the plan.

Make sure to work on one subtask at a time. While working on a subtask, make sure to update the phase, task and that subtask's status to "in-progress" and "done" after completion.

Always keep the plan updated for the progress so that it can be used for future reference.

Write your learnings/observations/updates/lesson learned etc in a new section along the way. Before making the plan of a subtask, make sure to visit that section and update the plan with the new information accordingly.

Authoritative references

- Codebase: `wrext-backend/**`
- Latest official docs (read before each implementation): FastAPI, Pydantic, SQLAlchemy, Alembic, LangGraph, LangChain, PostgreSQL

Project guardrails (must follow)

- Python 3.11+ everywhere; FastAPI framework
- Always add models in "src/api/models/" folder
- Always add schemas in "src/api/schema/" folder
- Always add routes in "src/api/routes/" folder
- Always use Pydantic for request/response validation
- Always use SQLAlchemy for database operations
- Always use Alembic for database migrations
- Follow existing error handling patterns using custom exceptions
- Use type hints everywhere
- Follow existing logging patterns using the logger utility

Workflow

1. Discovery (read-only)
   - Retrieve the task/subtask details from Taskmaster and read any linked context.
   - Explore the exact files to be changed (APIs, routes, models, schemas, db migrations, middleware, services). Quote small snippets and line ranges where helpful.
   - Consult latest docs (FastAPI, Pydantic, SQLAlchemy, Alembic, LangGraph, LangChain, PostgreSQL) to validate patterns and APIs you will use.

2. Implementation plan (for approval)
   Produce a concise, diff-oriented plan that includes:
   - Overview: what is being implemented and why (tie to plan file(s))
   - Impacted files/modules (absolute paths)
   - Exact edits (per file): what to add/remove/replace;
   - Observability: key logs and error handling approach
   - Acceptance criteria: binary, verifiable checks
   - Make sure to check if the task is already done or not.
   - Answers to these questions:
     - Is this must-have or nice-to-have?
     - Which files/modules/folders are impacted?
     - When should this be done (now vs later) and why?
     - What are this task's dependencies?
     - Is this task already done or not?

3. Implementation (after approval)
   - Apply edits per plan;

4. Completion
   - Run linting if configured: Check pyproject.toml for lint commands
   - If tests pass, mark the subtask as done and append implementation notes summarizing:
     - What changed (files/classes/functions)
     - Any follow-ups or risks
   - Commit changes to git with a descriptive commit message (standard format without Claude attribution)

Notes & tips
- Always analyze the latest codebase, previous tasks done and latest docs of any libraries/packages involved to have the most accurate and up to date information before making the plan.
