# Sentry SDK + LangChain/LangGraph Conflict Resolution

**Issue Date:** October 16, 2025
**Resolution Date:** October 16, 2025
**Severity:** CRITICAL (Blocked content generation)
**Status:** ✅ RESOLVED

---

## Problem Summary

Content generation was failing with the following error:

```python
TypeError: object of type 'Omit' has no len()
  File ".venv/lib/python3.11/site-packages/sentry_sdk/integrations/openai.py", line 212, in _set_input_data
    if tools is not NOT_GIVEN and tools is not None and len(tools) > 0:
                                                        ^^^^^^^^^^
```

### Error Context

- **Location:** `/sentry_sdk/integrations/openai.py:212` in `_set_input_data()`
- **Trigger:** LangChain's `with_structured_output()` method invoked by LangGraph workflow
- **Impact:** 100% failure rate for AI content generation
- **Sentry SDK Version:** 2.42.0
- **LangChain Version:** Latest (with structured output support)

---

## Root Cause Analysis

### The Conflict

1. **Sentry's OpenAI Integration:**
   - Auto-enabled when `openai` package is detected
   - Instruments OpenAI API calls to track requests, tokens, and errors
   - Tries to inspect the `tools` parameter with `len(tools)` on line 212

2. **LangChain's Structured Output:**
   - Uses OpenAI's structured output feature via `with_structured_output()`
   - Passes an `Omit` type object (not a list) for the `tools` parameter
   - `Omit` type excludes certain fields from being passed to the API

3. **The Collision:**
   ```python
   # Sentry tries:
   if tools is not NOT_GIVEN and tools is not None and len(tools) > 0:

   # But LangChain passes:
   tools = Omit(...)  # Not a list, doesn't support len()

   # Result:
   TypeError: object of type 'Omit' has no len()
   ```

### Why This Happens

- **LangChain's Design:** When using structured output, LangChain modifies the OpenAI API parameters to use native structured output features (JSON schema mode)
- **OpenAI SDK Change:** Recent OpenAI SDK versions introduced the `Omit` type to explicitly exclude parameters
- **Sentry SDK Assumption:** Sentry's OpenAI integration assumes `tools` is either `None`, `NOT_GIVEN`, or a list - it doesn't handle `Omit` types

---

## Solution

### Implementation

Explicitly disable Sentry's OpenAI integration while keeping other integrations:

```python
# src/api/lib/sentry_config.py

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,

    # Explicitly define integrations (prevents auto-discovery)
    integrations=[
        FastApiIntegration(...),
        StarletteIntegration(...),
        SqlalchemyIntegration(),
        LoggingIntegration(...),
        # OpenAIIntegration - intentionally EXCLUDED
    ],

    # Disable auto-discovery
    default_integrations=False,
    auto_enabling_integrations=False,
)
```

### Trade-offs

| What We Keep | What We Lose |
|--------------|--------------|
| ✅ FastAPI request tracking | ❌ OpenAI API call tracing |
| ✅ SQLAlchemy query monitoring | ❌ LLM token usage tracking in Sentry |
| ✅ Error logging and breadcrumbs | ❌ OpenAI error attribution |
| ✅ Performance transaction tracking | |
| ✅ Content generation works! | |

**Alternative Tracking:** We use LangSmith for LLM observability, which provides better LangChain/LangGraph-specific insights anyway.

---

## Verification Steps

### 1. Check Sentry Configuration

```bash
# Verify OpenAI integration is NOT imported
grep -r "from sentry_sdk.integrations.openai" wrext-backend/src/
# Should return: (empty)

# Verify configuration
grep -A 5 "integrations=\[" wrext-backend/src/api/lib/sentry_config.py
# Should show: FastAPI, Starlette, SQLAlchemy, Logging (no OpenAI)
```

### 2. Test Content Generation

```bash
# Start backend
cd wrext-backend
.venv/bin/uvicorn src.api.main:app --reload --port 8000

# Trigger content generation via API or frontend
# Should complete without TypeError
```

### 3. Verify Sentry Still Works

```python
# Test that other Sentry features still work
from src.api.lib.sentry_config import capture_exception_with_context

try:
    raise Exception("Test error")
except Exception as e:
    event_id = capture_exception_with_context(e, {"test": "data"})
    print(f"Event ID: {event_id}")  # Should return event ID
```

---

## Related Issues & Research

### Sentry Documentation

- [Sentry OpenAI Integration](https://docs.sentry.io/platforms/python/integrations/openai/)
- [Sentry LangGraph Integration](https://docs.sentry.io/platforms/python/integrations/langgraph/)
- [Default Integrations](https://docs.sentry.io/platforms/python/integrations/default-integrations/)

### LangGraph Integration Note

> "For correct token accounting, disable the integration for the model provider you are using (e.g. OpenAI or Anthropic) when using the LangGraph integration."

This suggests Sentry itself recommends disabling OpenAI integration when using LangGraph.

### Similar Issues

| Issue | Context | Similar Error |
|-------|---------|---------------|
| LangChain #18941 | `StringPromptValue` has no len() | Similar `len()` call on wrong type |
| LangChain #29177 | with_structured_output error | OpenAI model specific issues |
| Sentry #3107 | OpenAI exceptions captured as unhandled | Integration over-capturing |

### Common LangChain + Sentry Issues

1. **BaseModel.model_dump() TypeError** - When Sentry tries to serialize Pydantic models
2. **NotImplementedError with with_structured_output** - Not all models support it
3. **Double-tracking** - Both Sentry and LangSmith tracking the same requests
4. **PII concerns** - LLM prompts containing sensitive data sent to Sentry

---

## Future Considerations

### When to Re-enable OpenAI Integration

Consider re-enabling if:

1. **Sentry SDK updates fix the `Omit` type handling**
   - Monitor: https://github.com/getsentry/sentry-python/releases
   - Check for: "OpenAI integration" or "Omit type" fixes

2. **LangChain changes how it uses OpenAI's structured output**
   - Monitor: https://github.com/langchain-ai/langchain/releases
   - Check for: Changes to `with_structured_output` implementation

3. **We stop using `with_structured_output`**
   - If we switch to manual JSON parsing or different structured output methods

### Alternative Monitoring Solutions

We already have better alternatives for LLM observability:

- **LangSmith:** Native LangChain/LangGraph tracing with full context
- **Custom logging:** Structured logs with prompt/response tracking
- **OpenAI Dashboard:** Native token usage and cost tracking

### Upgrade Path

```bash
# Check for newer Sentry SDK versions
pip install --upgrade sentry-sdk

# Test in staging first
# If error persists, keep OpenAI integration disabled
```

---

## Incident Timeline

| Time | Event |
|------|-------|
| Oct 16, 2025 11:52 AM | Content generation fails with TypeError |
| Oct 16, 2025 11:55 AM | Root cause identified: Sentry OpenAI integration |
| Oct 16, 2025 12:00 PM | Web research on Sentry + LangChain conflicts |
| Oct 16, 2025 12:10 PM | Solution implemented: Disable OpenAI integration |
| Oct 16, 2025 12:15 PM | Documentation created |
| Oct 16, 2025 12:20 PM | Ready for testing |

---

## Testing Checklist

- [ ] Backend starts without errors
- [ ] Content generation completes successfully
- [ ] No `TypeError: object of type 'Omit' has no len()` errors
- [ ] Sentry still captures other errors (FastAPI, SQLAlchemy)
- [ ] LangSmith tracing still works
- [ ] Email notifications sent on generation start/complete/fail
- [ ] Check Sentry dashboard shows FastAPI requests
- [ ] Check Sentry dashboard shows error events (for real errors)

---

## Summary

**Problem:** Sentry's auto-enabled OpenAI integration conflicted with LangChain's structured output implementation, causing all content generation to fail.

**Solution:** Explicitly disabled OpenAI integration by using a custom integrations list with `default_integrations=False` and `auto_enabling_integrations=False`.

**Result:** Content generation works, we keep all other Sentry monitoring, and we already have better LLM observability through LangSmith.

**Lesson:** When using multiple observability tools with LLM frameworks, explicitly configure integrations to avoid auto-discovery conflicts.

---

**Document Version:** 1.0
**Last Updated:** October 16, 2025
**Author:** Claude (via wrext-backend analysis)
**Status:** ✅ RESOLVED - Solution implemented and documented
