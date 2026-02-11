# Task 196: Fix Weak API Key Handling — Missing Import and Silent Failure

## Metadata
- **Task ID:** TASK-196
- **Source:** Backend Knowledge Base (Finding #2 under P0 Critical)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `get_embedding()` function in `src/utils/embedding.py` has two critical bugs that compound into a complete failure of the embedding subsystem:

**Bug 1: Missing `import os` (NameError).** The function calls `os.getenv("OPENAI_API_KEY")` on line 16, but `os` is never imported in the file. The only imports are `from langchain_openai import OpenAIEmbeddings` and `from src.utils.logger import logger`. This means the very first call to `get_embedding()` will raise a `NameError: name 'os' is not defined`. Due to the global `_embedding_model` caching pattern (lines 5, 11-13), the error occurs on the first call and then the except block on line 25 attempts the same `os.getenv()` call in the fallback, causing another `NameError` that propagates unhandled.

**Bug 2: Silent continuation with `api_key=None`.** Even if `import os` were present, when `OPENAI_API_KEY` is not set in the environment, the code only logs a warning (`logger.warning("OPENAI_API_KEY not found in environment")` on line 18) and then proceeds to create the `OpenAIEmbeddings` model with `api_key=None`. This will cause a cryptic `AuthenticationError` from the OpenAI SDK when the first actual embedding request is made, far removed from the root cause. According to the 12-Factor App methodology and OpenAI's own best practices, required configuration should be validated at startup, and the application should fail fast with a clear error message.

The embedding model is used by `vector_store.py` (imported on line 2), which is called during every knowledge creation operation (file upload, text creation, web scraping). This means **all knowledge base operations are broken** if the missing import hasn't been coincidentally resolved through some other mechanism.

---

## Current Code

```python
# File: rext-backend/src/utils/embedding.py
# Lines: 1-31
from langchain_openai import OpenAIEmbeddings

from src.utils.logger import logger

_embedding_model = None

def get_embedding():
    """
    Get OpenAI embedding model for vector retrieval tasks.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    try:
        api_key = os.getenv("OPENAI_API_KEY")  # BUG: os is not imported!
        if not api_key:
            logger.warning("OPENAI_API_KEY not found in environment")

        _embedding_model = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=api_key  # Will be None if env var not set
        )
        return _embedding_model
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {e}", exc_info=True)
        # Final fallback — also uses os.getenv without import!
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=os.getenv("OPENAI_API_KEY")  # BUG: same missing import
        )
```

---

## Why This Matters (Context & Reasoning)

The `get_embedding()` function is the single point of initialization for the OpenAI embedding model used across the entire knowledge base system. It is called by:
- `vector_store.py:106` — `get_embedding().embed_query("hello world")` during dimension detection
- `vector_store.py:119` — `get_embedding()` when loading existing FAISS index
- `vector_store.py:128` — `get_embedding()` when creating new FAISS index
- `vector_store.py:209` — `get_embedding()` when loading vector store for search/delete

Every knowledge base operation (add file, add text, add web, delete knowledge, search) passes through `vector_store.py`, which calls `get_embedding()`. If this function crashes, all knowledge operations fail.

The missing `import os` is particularly dangerous because:
1. The first call crashes with `NameError`, which is caught by the `except Exception` block
2. The except block's "fallback" also uses `os.getenv()`, causing another `NameError`
3. This second error propagates up unhandled, crashing the caller
4. The `_embedding_model` singleton is never set, so every subsequent call also crashes
5. Users see an incomprehensible `NameError` traceback instead of a helpful "API key missing" message

---

## Impact

- **Severity:** Complete failure of all knowledge base operations if `os` import is missing. If the import issue has been coincidentally resolved (e.g., through a wildcard import elsewhere), the secondary issue of continuing with `api_key=None` causes cryptic authentication errors on actual API calls.
- **Affected Users/Flows:** All knowledge creation (file, text, web), knowledge deletion, and knowledge search flows.
- **Blast Radius:** All workspaces, all users. The embedding model is a shared singleton.

---

## Recommended Solution

### Step 1: Fix the Missing Import and Add Fail-Fast Validation

```python
# File: rext-backend/src/utils/embedding.py
# Replace the ENTIRE file content with:
import os

from langchain_openai import OpenAIEmbeddings

from src.utils.logger import logger

_embedding_model = None


def get_embedding() -> OpenAIEmbeddings:
    """
    Get or create the singleton OpenAI embedding model.

    Uses the text-embedding-3-small model (1536 dimensions).
    Fails fast if OPENAI_API_KEY is not set.

    Returns:
        OpenAIEmbeddings: Configured embedding model instance.

    Raises:
        ValueError: If OPENAI_API_KEY environment variable is not set.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required but not set. "
            "Please set it in your .env file or environment."
        )

    _embedding_model = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
    )
    logger.info("OpenAI embedding model initialized successfully (text-embedding-3-small)")
    return _embedding_model
```

### Step 2: Remove Test Code from Module Level

The original file has test code at the bottom (`if __name__ == "__main__":` block with emoji in print statements). If this test code is needed, it should reference the correct model name. The replacement above removes it — if test code is desired, create a separate test file instead.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/vector_store.py` | `2, 106, 119, 128, 209` | All calls to `get_embedding()` — these will now get a clear `ValueError` if API key is missing |
| `rext-backend/src/api/tasks/knowledge_task.py` | N/A | Indirectly affected via vector_store calls |
| `rext-backend/src/services/knowledge_service.py` | N/A | Indirectly affected via vector_store calls |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Unset the `OPENAI_API_KEY` environment variable
2. Start the backend server
3. Attempt to create any knowledge item (file, text, or web)
4. Observe `NameError: name 'os' is not defined` in the server logs

### After Fix (Verify the Solution):
1. **Test missing API key:** Unset `OPENAI_API_KEY`, start the server, attempt knowledge creation → should get a clear `ValueError` message: "OPENAI_API_KEY environment variable is required but not set"
2. **Test valid API key:** Set `OPENAI_API_KEY` to a valid key, start the server, create a text knowledge item → should succeed
3. **Test singleton caching:** Create two knowledge items in sequence → the second should reuse the cached model (check logs for only one "initialized successfully" message)

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/ -v -k "embedding or knowledge or vector" --no-header
```

---

## Acceptance Criteria

- [ ] `import os` is present at the top of `embedding.py`
- [ ] `get_embedding()` raises `ValueError` with a clear message when `OPENAI_API_KEY` is not set
- [ ] The fallback `except` block that silently retries with the same broken code is removed
- [ ] The function has a proper return type annotation (`-> OpenAIEmbeddings`)
- [ ] Singleton caching still works (model is only initialized once)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [OpenAI API Key Best Practices](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [The Twelve-Factor App — Config](https://12factor.net/config)
- **Related Issues/PRs:** [langchain-openai OpenAIEmbeddings API Reference](https://python.langchain.com/docs/integrations/text_embedding/openai/)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** TASK-194 (Rate Limiting on OpenAI API Calls — the embedding function must work first)
- **Related:** TASK-004 (B1 — Deprecated datetime.utcnow()), TASK-045 (B2 — Deprecated datetime.utcnow() in models)
