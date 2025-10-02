# Backend Task Implementation Prompt - WREXT User Management System

**Last Updated:** 2025-10-02

---

## Context

This prompt is invoked by the universal task orchestrator (`@task-implementation-universal-prompt.md`) when a backend task is identified. You are executing a specific backend task from the user management implementation plan.

---

## Input from Universal Orchestrator

You receive:
- Task ID and description from `@user-management-backend-plan.md`
- Current phase and dependencies status
- Confirmation that all blockers are resolved

---

## Workflow

### 1. Discovery (Read-Only)

**CRITICAL: This step is READ-ONLY. Make NO changes.**

#### 1.1: Review Task Details
- Retrieve the task/subtask details from the backend plan
- Read task description, acceptance criteria, and dependencies
- Understand what problem this solves and why it's needed

#### 1.2: Examine Existing Code
Explore the exact files to be changed:
- **Routes**: Check `src/api/routes/` for existing endpoint patterns
- **Models**: Check `src/api/models/` for database models
- **Schemas**: Check `src/api/schemas/` for Pydantic validation schemas
- **Middleware**: Check `src/api/middleware/` for existing middleware
- **Migrations**: Check `alembic/versions/` for database migrations
- **Services**: Check `src/api/services/` for business logic

**Quote small snippets and line ranges where helpful.**

Example:
```
Reading src/api/routes/users/users_routes.py:415-450...
Found commented-out role assignment code at lines 136-147
```

#### 1.3: Analyze Existing Patterns
- **Error handling**: How are exceptions raised and handled? (`src/api/exceptions/`)
- **Response format**: What pattern is used for API responses? (`src/api/responses/`)
- **Database sessions**: How are DB sessions managed? (FastAPI Depends)
- **Validation**: What Pydantic patterns are used?
- **Logging**: What logging pattern is followed? (`src/utils/logger.py`)
- **Security**: How are auth and permissions handled? (`src/api/security/`)

#### 1.4: Check Database State
```bash
# Check current Alembic migration status
alembic current

# List recent migrations
ls -lt alembic/versions/ | head -5

# Check for pending migrations
alembic history
```

#### 1.5: Consult Latest Documentation
**Use WebSearch or WebFetch** to check latest docs for:
- **FastAPI**: Latest patterns, dependency injection, BackgroundTasks
- **Pydantic**: Validation schema patterns (v2 if applicable)
- **SQLAlchemy**: ORM patterns, relationships (2.0+ style)
- **Alembic**: Migration best practices
- **PostgreSQL**: Database optimization, indexes
- **JWT/Security**: Token management, password hashing

**Document which sources you consulted.**

#### 1.6: Verify Task Status
**Check if task is already done:**
```bash
# Search for related code
grep -r "keyword" src/api/

# Find similar implementations
find src/api -name "*pattern*.py"

# Check for TODO comments
grep -r "TODO" src/api/
```

---

### 2. Implementation Plan (For Approval)

**DO NOT implement anything until user approves this plan.**

Produce a concise, diff-oriented plan that includes:

#### 2.1: Overview
- **What** is being implemented (feature/fix/refactor)
- **Why** it's needed (tie to `@user-management-backend-plan.md`)
- **How** it fits into the overall system

#### 2.2: Impacted Files/Modules
**List absolute paths:**

**Create:**
- `/Users/mobeen/Work/Products/wrext/wrext-backend/path/to/new-file.py` - Purpose

**Modify:**
- `/Users/mobeen/Work/Products/wrext/wrext-backend/path/to/file.py:123-150` - Description of changes

**Database:**
- New migration: `alembic revision -m "description"`
- Tables affected: `users`, `roles`, etc.

#### 2.3: Exact Edits (Per File)
For each file, specify what to:
- **Add**: New functions, classes, imports
- **Remove**: Deprecated code, comments
- **Replace**: Updated logic, refactored code

**Include code snippets** showing before/after.

#### 2.4: Observability
- **Logging**: What log messages will be added?
  ```python
  logger.info(f"Operation started: {details}")
  logger.error(f"Operation failed: {error}")
  ```
- **Error handling**: What exceptions will be raised?
  ```python
  raise WrextValidationException(message="...", context={...})
  ```
- **Monitoring**: How will success/failure be detected?

#### 2.5: Acceptance Criteria
**Binary, verifiable checks:**
- [ ] Endpoint returns 200 OK for valid input
- [ ] Endpoint returns 400 for invalid input
- [ ] Database record created successfully
- [ ] Migration runs without errors
- [ ] All tests pass

#### 2.6: Pre-Implementation Checklist
Answer these questions:
- **Is this must-have or nice-to-have?** Must-have - blocks Phase X
- **Which files/modules/folders are impacted?** `src/api/routes/users/`, `src/api/schemas/`
- **When should this be done (now vs later) and why?** Now - dependency for Task X.Y
- **What are this task's dependencies?** Task X.Y-1 must be complete
- **Is this task already done or not?** No - verified in discovery
- **What existing patterns must be followed?** Using Pydantic BaseModel, FastAPI Depends
- **What documentation did I consult?** FastAPI docs (BackgroundTasks), existing routes

---

### 3. Implementation (After Approval)

**Only proceed after user approves the plan.**

#### 3.1: Follow Tech Stack Guardrails

**Must Follow:**
- ✅ Python 3.11+ everywhere
- ✅ FastAPI framework
- ✅ Models in `src/api/models/` folder
- ✅ Schemas in `src/api/schemas/` folder
- ✅ Routes in `src/api/routes/` folder
- ✅ Use Pydantic for request/response validation
- ✅ Use SQLAlchemy for database operations
- ✅ Use Alembic for database migrations
- ✅ Follow existing error handling patterns using custom exceptions
- ✅ Use type hints everywhere
- ✅ Follow existing logging patterns using logger utility

#### 3.2: Code Quality Standards

**All code must:**
- ✅ Follow existing code patterns
- ✅ Include proper error handling
- ✅ Include logging for important operations
- ✅ Use Python type hints
- ✅ Be well-commented for complex logic
- ✅ Handle edge cases
- ✅ Validate inputs with Pydantic
- ✅ Use environment variables for configuration
- ✅ Follow security best practices

**Backend-specific:**
- ✅ Use dependency injection (FastAPI Depends)
- ✅ Validate with Pydantic schemas
- ✅ Return standardized responses (`success()`, `error()`)
- ✅ Use proper HTTP status codes
- ✅ Add database transaction handling
- ✅ Include SQL migration if schema changes

#### 3.3: Apply Edits Per Plan
- Create/modify files according to approved plan
- Make one logical change at a time
- Add proper logging at each step
- Handle errors gracefully

**Example error handling:**
```python
try:
    result = operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise WrextValidationException(
        message="User-friendly error message",
        context={"details": str(e)}
    )
```

#### 3.4: Database Migrations (If Applicable)
If schema changes:
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Review generated migration
cat alembic/versions/<revision>.py

# Test upgrade
alembic upgrade head

# Test downgrade
alembic downgrade -1
```

---

### 4. Completion

#### 4.1: Run Linting (If Configured)
```bash
# Check pyproject.toml for lint commands
cat pyproject.toml | grep -A 10 "lint"

# Run if available (e.g., black, ruff, pylint)
# black src/
# ruff check src/
```

#### 4.2: Test Implementation
**Manual testing:**
```bash
# Start server
PYTHONPATH=. python src/api/server.py

# Test endpoint
curl -X POST http://localhost:8000/api/v1/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

**Automated tests (if available):**
```bash
pytest tests/
```

#### 4.3: Verify Acceptance Criteria
Go through each criterion:
- [ ] All criteria met?
- [ ] Edge cases handled?
- [ ] Error states tested?
- [ ] Performance acceptable?

#### 4.4: Document Implementation
Mark the subtask as done and append implementation notes to the backend plan:

```markdown
### Task X.Y: [Task Name] - COMPLETED ✅

**Completed:** 2025-XX-XX

**Implementation Summary:**
- Created: `src/api/schemas/auth_schemas.py`
- Modified: `src/api/routes/users/users_routes.py:415-450`
- Migration: `alembic/versions/abc123_fix_password_reset.py`

**Key Changes:**
- Added `ForgotPasswordRequest` Pydantic schema
- Injected `BackgroundTasks` via FastAPI dependency
- Used environment variable for frontend URL
- Added proper error handling and logging

**Observations/Learnings:**
- FastAPI BackgroundTasks must be injected, not called directly
- Environment variables should always have defaults
- Email sending should be in background to avoid blocking

**Follow-ups:**
- None - task complete

**Testing:**
- ✅ Manual testing passed
- ✅ Email sent successfully
- ✅ Error handling verified
```

#### 4.5: Update Master Plan
After updating the backend plan, also update `@user-management-master-plan.md`:
- Mark task as ✅ complete
- Update phase progress percentage
- Note any blockers or risks discovered

#### 4.6: Commit Changes
```bash
git add .
git commit -m "<type>: <short summary>

- <change 1>
- <change 2>
- <change 3>

Closes: Backend Phase X, Task X.Y"
```

**Commit types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `docs`: Documentation changes
- `test`: Test additions/changes
- `chore`: Maintenance tasks

**Example:**
```bash
git commit -m "fix: implement password reset endpoint with proper typing

- Add ForgotPasswordRequest schema for validation
- Inject BackgroundTasks via FastAPI dependency
- Use environment variable for frontend URL
- Add proper error handling and logging

Closes: Backend Phase 0, Task 0.1"
```

---

## Authoritative References

**Codebase:** `wrext-backend/**`

**Latest Official Docs (consult before implementation):**
- FastAPI: https://fastapi.tiangolo.com/
- Pydantic: https://docs.pydantic.dev/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/
- PostgreSQL: https://www.postgresql.org/docs/

---

## Common Patterns

### Error Handling
```python
from src.api.exceptions import WrextValidationException, WrextAuthenticationException

# Validation error
raise WrextValidationException(
    message="Invalid email address",
    context={"email": email}
)

# Authentication error
raise WrextAuthenticationException(
    message="Invalid credentials"
)
```

### Logging
```python
from src.utils.logger import logger

logger.info(f"User {user_id} registered successfully")
logger.warning(f"Failed login attempt for {email}")
logger.error(f"Database error: {str(e)}")
```

### Response Format
```python
from src.api.responses import success, error

# Success response
return success(
    data={"user": user.to_dict()},
    request=request,
    message="User created successfully"
)

# Error response
return error(
    message="User not found",
    request=request,
    status_code=404
)
```

### Database Session
```python
from fastapi import Depends
from sqlalchemy.orm import Session
from src.api.database.database import get_db

@router.post("/endpoint")
def my_endpoint(
    data: MySchema,
    db: Session = Depends(get_db)
):
    # Use db session
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
```

---

## Quality Checklist

Before marking complete:
- [ ] Code follows existing patterns
- [ ] Proper error handling implemented
- [ ] Logging added for key operations
- [ ] Python type hints used everywhere
- [ ] Edge cases handled
- [ ] Input validation with Pydantic
- [ ] Environment variables used (no hardcoded values)
- [ ] Security best practices followed
- [ ] Database migration tested (if applicable)
- [ ] Manual/automated tests passing
- [ ] Backend plan updated with learnings
- [ ] Master plan updated with progress
- [ ] Changes committed to git

---

## Notes & Tips

- Always analyze the **latest codebase** before planning
- Check **previous tasks** done to understand context
- Consult **latest docs** of libraries/packages involved
- Have the **most accurate and up-to-date information** before making the plan
- When in doubt, **ask the user** rather than guessing
- **Document learnings** for future reference

---

## Special Scenarios

### Task Already Done
If you discover the task is already implemented:
1. Verify it meets all acceptance criteria
2. Update backend plan to mark complete
3. Document what was found
4. Update master plan
5. Inform user and move to next task

### Dependencies Not Met
If dependencies aren't satisfied:
1. Identify the blocking task
2. Ask user: start blocker first, skip to another task, or wait?
3. Update plans with blocker status

### Conflicting Information
Resolution order:
1. Actual codebase = ultimate source of truth
2. Backend plan = source of truth for implementation details
3. Master plan = source of truth for priorities
4. When in doubt, ask the user

---

**Ready to implement? Wait for user approval of your implementation plan before proceeding.**