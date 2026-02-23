# Task 194: Add Rate Limiting on OpenAI Embedding API Calls

## Metadata
- **Task ID:** TASK-194
- **Source:** Backend Knowledge Base (Finding #3 under P0 Critical)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P0 Critical
- **Category:** security
- **Effort Estimate:** large (4+ hours)

---

## Description

The knowledge base module generates OpenAI embeddings for every piece of content added (files, text, web scrapes) via the `add_to_vector_store()` function in `src/utils/vector_store.py`, which calls `get_embedding()` from `src/utils/embedding.py`. This creates OpenAI API calls using the `text-embedding-3-small` model for every batch of document chunks. There is no rate limiting or cost control mechanism specifically governing these embedding API calls.

While the project has a general HTTP rate limiter (`RateLimiterMiddleware` in `src/api/server.py` with configurable `RATE_LIMIT_PER_MINUTE` from `src/api/config.py:68`) and a subscription-based quantity limiter (`check_knowledge_item_limit()` in `src/api/middleware/usage_limiter.py`), neither of these controls the **rate** or **volume** of OpenAI API calls. The quantity limiter only checks whether the user has reached their plan's maximum number of knowledge items — it does not prevent a user from uploading many items in rapid succession within their plan limit. A user on a high-tier plan could trigger hundreds of embedding requests per minute.

The `add_to_vector_store()` function processes documents in batches of 32 (line 48 of `vector_store.py`), and each batch call to `vector_store.add_documents()` triggers the OpenAI embedding API. A single large file could produce hundreds of chunks, each requiring an embedding API call. There is no queuing, no per-user embedding rate limit, no daily cost cap, and no circuit breaker if OpenAI returns 429 (rate limit exceeded) errors.

According to OpenAI's rate limits documentation, the `text-embedding-3-small` model has tier-based limits (e.g., Tier 1: 500 RPM, 1M TPM). If the application exceeds these limits, all users' embedding requests will fail until the rate limit resets. This creates a denial-of-service risk where one user's bulk upload degrades embedding quality for all users.

---

## Current Code

```python
# File: rext-backend/src/utils/vector_store.py
# Lines: 47-171 (add_to_vector_store function, key section)
def add_to_vector_store(
    batch_size: int = 32,
    blog_context: list[Document] = (),
    workspace_id: str = None,
    knowledge_id: str = None,
    knowledge_type: str = None,
    knowledge_base_id: str = None
) -> bool:
    # ... validation ...

    # No rate limiting before calling OpenAI embedding API
    test_embedding = get_embedding().embed_query("hello world")  # Immediate API call
    dimension = len(test_embedding)

    # ... FAISS setup ...

    for i in tqdm(range(0, len(documents_with_metadata), batch_size), desc="🔍 Embedding & Inserting", unit="batch"):
        try:
            batch_docs = documents_with_metadata[i:i+batch_size]
            batch_ids = uuids[i:i+batch_size]
            vector_store.add_documents(documents=batch_docs, ids=batch_ids)  # Each call triggers OpenAI API
        except Exception as e:
            logger.error(f"⚠️ Error during batch insertion: {str(e)}", exc_info=True)
            return False

    # ... save ...
    return True
```

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Lines: 146-156 (create_web_knowledge endpoint - has quantity limit but no rate limit)
@router.post("/web")
@db_transaction_handler("create web knowledge", "Web knowledge created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_web_knowledge(
    workspace_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: WebKnowledgeCreateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_knowledge_item_limit()),  # Only checks quantity, not rate
):
```

---

## Why This Matters (Context & Reasoning)

The knowledge base is a core feature of Rext AI — users upload documents, text, and web pages to build their content knowledge base for AI-powered content generation. Every knowledge item requires embedding generation via the OpenAI API, which has direct cost implications (billed per token). Without rate limiting:

1. **Financial Risk:** A single user could trigger thousands of API calls, generating significant unexpected costs. OpenAI bills per token for embeddings, and a large document could contain hundreds of thousands of tokens.
2. **Service Degradation:** Exceeding OpenAI's rate limits causes 429 errors for ALL users, not just the abusive one. This means one user's bulk upload can prevent all other users from adding knowledge.
3. **No Cost Visibility:** There's no tracking of embedding API usage per user or per workspace, making it impossible to attribute costs or detect abuse.
4. **Abuse Vector:** A malicious user could intentionally upload many large files to exhaust the application's OpenAI API budget.

---

## Impact

- **Severity:** Unbounded financial exposure via OpenAI API costs. Service-wide embedding failures when rate limits are hit. No per-user accountability for API usage.
- **Affected Users/Flows:** All knowledge creation flows (file upload, text creation, web scraping) across all workspaces. When rate limits are exceeded, all users are affected.
- **Blast Radius:** Global — affects all users and all workspaces because the OpenAI API key is shared across the entire application.

---

## Recommended Solution

Implement a multi-layered rate limiting strategy: (1) per-user embedding rate limit via Redis, (2) retry with exponential backoff for OpenAI 429 errors, and (3) a global embedding semaphore to control concurrency.

### Step 1: Add Per-User Embedding Rate Limiter

```python
# File: rext-backend/src/utils/embedding_rate_limiter.py
"""
Rate limiter for OpenAI embedding API calls.

Implements per-user and global rate limiting using Redis
to prevent cost overruns and API abuse.
"""

import asyncio
import time
from typing import Optional

import redis.asyncio as aioredis

from src.api.config import get_settings
from src.utils.logger import logger

settings = get_settings()


class EmbeddingRateLimiter:
    """
    Redis-based rate limiter for embedding API calls.

    Uses a sliding window counter pattern to enforce:
    - Per-user limits: Max embedding requests per minute per user
    - Global limits: Max total embedding requests per minute across all users
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        user_rpm: int = 10,
        global_rpm: int = 200,
    ):
        """
        Args:
            redis_url: Redis connection URL. Defaults to settings.REDIS_URL.
            user_rpm: Maximum embedding requests per minute per user.
            global_rpm: Maximum embedding requests per minute globally.
        """
        self.redis_url = redis_url or settings.REDIS_URL
        self.user_rpm = user_rpm
        self.global_rpm = global_rpm
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def check_rate_limit(self, user_id: str) -> bool:
        """
        Check if the user is within rate limits.

        Args:
            user_id: The user identifier.

        Returns:
            True if the request is allowed, False if rate limited.
        """
        r = await self._get_redis()
        now = time.time()
        window_start = now - 60  # 1-minute window

        pipe = r.pipeline()

        # Per-user rate limit
        user_key = f"embedding_rate:{user_id}"
        pipe.zremrangebyscore(user_key, 0, window_start)
        pipe.zcard(user_key)

        # Global rate limit
        global_key = "embedding_rate:global"
        pipe.zremrangebyscore(global_key, 0, window_start)
        pipe.zcard(global_key)

        results = await pipe.execute()
        user_count = results[1]
        global_count = results[3]

        if user_count >= self.user_rpm:
            logger.warning(
                f"User {user_id} exceeded embedding rate limit: {user_count}/{self.user_rpm} RPM"
            )
            return False

        if global_count >= self.global_rpm:
            logger.warning(
                f"Global embedding rate limit exceeded: {global_count}/{self.global_rpm} RPM"
            )
            return False

        return True

    async def record_request(self, user_id: str) -> None:
        """Record an embedding request for rate limiting."""
        r = await self._get_redis()
        now = time.time()

        pipe = r.pipeline()

        user_key = f"embedding_rate:{user_id}"
        pipe.zadd(user_key, {f"{now}": now})
        pipe.expire(user_key, 120)

        global_key = "embedding_rate:global"
        pipe.zadd(global_key, {f"{user_id}:{now}": now})
        pipe.expire(global_key, 120)

        await pipe.execute()


# Singleton instance
_rate_limiter: Optional[EmbeddingRateLimiter] = None


def get_embedding_rate_limiter() -> EmbeddingRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = EmbeddingRateLimiter()
    return _rate_limiter
```

### Step 2: Add Rate Limit Check as FastAPI Dependency

```python
# File: rext-backend/src/api/middleware/usage_limiter.py
# Add this function after the existing check_knowledge_item_limit:

from src.utils.embedding_rate_limiter import get_embedding_rate_limiter

def check_embedding_rate_limit():
    """
    FastAPI dependency that checks per-user embedding rate limits.

    Usage:
        @router.post("/knowledge/web")
        async def create_web_knowledge(
            ...,
            _rate: None = Depends(check_embedding_rate_limit()),
        ):
    """
    async def _check(
        request: Request,
        current_user: dict = Depends(get_current_user),
    ) -> None:
        user_id = str(current_user.get("identity", ""))
        limiter = get_embedding_rate_limiter()

        allowed = await limiter.check_rate_limit(user_id)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Embedding rate limit exceeded. Please wait before adding more knowledge items.",
            )

        await limiter.record_request(user_id)

    return _check
```

### Step 3: Add Retry with Backoff to Vector Store

```python
# File: rext-backend/src/utils/vector_store.py
# Add import at top:
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Wrap the batch insertion loop with retry logic.
# Replace the for loop (lines 157-164) with:

    for i in tqdm(range(0, len(documents_with_metadata), batch_size), desc="Embedding & Inserting", unit="batch"):
        try:
            batch_docs = documents_with_metadata[i:i+batch_size]
            batch_ids = uuids[i:i+batch_size]
            _add_batch_with_retry(vector_store, batch_docs, batch_ids)
        except Exception as e:
            logger.error(f"Error during batch insertion after retries: {str(e)}", exc_info=True)
            return False


# Add this new function before add_to_vector_store:
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying embedding batch (attempt {retry_state.attempt_number})"
    ),
)
def _add_batch_with_retry(vector_store, batch_docs, batch_ids):
    """Add a batch of documents to the vector store with retry on failure."""
    vector_store.add_documents(documents=batch_docs, ids=batch_ids)
```

### Step 4: Apply Rate Limit Dependency to Knowledge Routes

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Add import:
from src.api.middleware.usage_limiter import check_embedding_rate_limit

# Add the dependency to create_web_knowledge (line 149):
@router.post("/web")
@db_transaction_handler("create web knowledge", "Web knowledge created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_web_knowledge(
    workspace_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: WebKnowledgeCreateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_knowledge_item_limit()),
    _rate: None = Depends(check_embedding_rate_limit()),  # ADD THIS
):

# Also add to create_file_knowledge and create_text_knowledge endpoints similarly.
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `348` | `add_file_knowledge` — needs rate limit dependency |
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `536` | `add_text_knowledge` — needs rate limit dependency |
| `rext-backend/src/api/tasks/knowledge_task.py` | `38-43` | Calls `add_to_vector_store` in background task — needs rate awareness |
| `rext-backend/src/services/workspace_pipeline.py` | `507` | Calls `web_page_scraper` → embeddings — consider rate limiting |
| `rext-backend/src/services/workspace_service.py` | `1042` | Calls `web_page_scraper` → embeddings — consider rate limiting |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a workspace and obtain auth tokens for two test users
2. As User A, rapidly create 20+ text knowledge items in quick succession via API
3. Observe that all requests succeed with no throttling — each triggers OpenAI API calls
4. If the OpenAI account has low rate limits, observe 429 errors from OpenAI on later requests

### After Fix (Verify the Solution):
1. Set `user_rpm=5` for testing (lower limit)
2. As User A, rapidly create 6+ text knowledge items
3. The 6th request should return HTTP 429 with message "Embedding rate limit exceeded"
4. Wait 60 seconds and retry — should succeed
5. As User B, create items during User A's cooldown — should succeed (per-user limits)

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "knowledge" --no-header
```

---

## Acceptance Criteria

- [ ] Per-user embedding rate limit is enforced via Redis (configurable RPM)
- [ ] Global embedding rate limit prevents total API exhaustion
- [ ] Rate limit exceeded returns HTTP 429 with a clear message
- [ ] Retry with exponential backoff handles transient OpenAI 429 errors
- [ ] Rate limit dependency is applied to all three knowledge creation endpoints (web, file, text)
- [ ] Redis-based rate limiter uses sliding window pattern for accurate limiting
- [ ] Rate limit values are configurable (not hardcoded)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OpenAI Rate Limits Guide](https://platform.openai.com/docs/guides/rate-limits)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [OpenAI Cookbook — How to Handle Rate Limits](https://cookbook.openai.com/examples/how_to_handle_rate_limits)
- **Related Issues/PRs:** [OpenAI Best Practices for Managing Rate Limits](https://help.openai.com/en/articles/6891753-what-are-the-best-practices-for-managing-my-rate-limits-in-the-api)

---

## Dependencies & Related Tasks

- **Depends on:** None (Redis is already a project dependency per `pyproject.toml`: `redis[hiredis]>=5.0.0`)
- **Blocks:** None
- **Related:** TASK-128 (B5 — No Rate Limiting on License Endpoints), TASK-065 (B3 — No Rate Limiting on OAuth Endpoints)
