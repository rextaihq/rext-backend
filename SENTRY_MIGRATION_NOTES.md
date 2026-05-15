# Sentry Logging Integration Update (2026)

## Summary of Changes

Successfully migrated from standard Python `logging` to **Sentry SDK** for advanced error tracking, monitoring, and real-time visibility in terminal and Sentry dashboard.

---

## Files Updated

### 1. `/src/flow/engines/seo/keyword_clustering.py`
- **Changes**: 27 Sentry log calls
- **Migration**: All `logger.info()`, `logger.warning()`, `logger.error()`, and `logger.debug()` calls replaced
- **Added Imports**: `sentry_sdk`, `capture_exception`, `capture_message`, `push_scope`

### 2. `/src/flow/engines/router/outline.py`
- **Changes**: 7 Sentry log calls
- **Migration**: All routing logic logs now use Sentry
- **Added Imports**: `sentry_sdk`, `capture_message`, `push_scope`

---

## What Changed

### Before (Standard Logger)
```python
logger.info("Keyword clustering: starting analysis")
logger.warning("No keywords extracted for clustering")
logger.error("KeywordExtractor failed\n%s", traceback.format_exc())
```

### After (Sentry SDK - 2026 Best Practice)
```python
with push_scope() as scope:
    scope.set_tag("module", "keyword_clustering")
    scope.set_tag("status", "started")
    capture_message("keyword_clustering: starting analysis", level="info")

with push_scope() as scope:
    scope.set_tag("module", "keyword_clustering")
    scope.set_tag("status", "no_keywords_extracted")
    scope.set_context("extraction_stats", {...})
    capture_message("keyword_clustering: no keywords extracted from SERP data", level="warning")

with push_scope() as scope:
    scope.set_tag("module", "keyword_clustering")
    scope.set_tag("operation", "extract_keywords")
    scope.set_context("extraction_data", {...})
    capture_exception(e)
```

---

## Key Benefits

✅ **Real-Time Monitoring**: See all logs instantly in Sentry dashboard  
✅ **Structured Context**: Tagged metadata for filtering and searching  
✅ **Error Aggregation**: Automatic grouping of similar errors  
✅ **Performance Tracking**: Integrated performance monitoring  
✅ **Alert Management**: Configure alerts based on event types  
✅ **Breadcrumb Trail**: Full context chain for debugging  
✅ **Terminal Visibility**: When configured with LoggingIntegration  

---

## Sentry Integration Details

### Tags Used (for filtering in Sentry)
- `module`: Name of the module (e.g., "keyword_clustering", "outline_router")
- `status`: Current status (e.g., "started", "approved", "error")
- `operation`: Type of operation (e.g., "persist_clusters", "extract_keywords")
- `validation`: Type of validation that failed

### Context Data (visible in Sentry event details)
- `seed_info`: Seed keyword and intent information
- `extraction_stats`: Statistics about keyword extraction
- `clustering_result`: Results from clustering operation
- `iteration_info`: Information about workflow iterations
- `persistence`: File persistence details

### Log Levels
- `"info"`: General informational messages
- `"warning"`: Warning messages for non-critical issues
- `"error"`: Error messages (used via `capture_exception()`)

---

## Terminal Output Integration

To see Sentry logs in your terminal:

1. **Ensure Sentry is initialized** in your main application:
   ```python
   from src.api.lib.sentry_config import init_sentry
   from src.api.config import settings
   
   init_sentry(settings)
   ```

2. **Configure environment variables** in `.env`:
   ```
   SENTRY_DSN=https://key@sentry.io/project-id
   SENTRY_ENVIRONMENT=development  # or production
   SENTRY_ENABLE_TRACING=true
   ```

3. **View logs via**:
   - **Sentry Dashboard**: https://sentry.io/ (preferred)
   - **Terminal**: If LoggingIntegration is configured
   - **LangSmith**: For LangGraph workflow tracing

---

## Testing

Run the integration test to verify all changes:

```bash
python3 test_sentry_integration.py
```

Expected output:
```
✅ Total Sentry calls: 34
✅ Files checked: 2
✅ All files have been migrated to Sentry logging
```

---

## Backward Compatibility

The standard `logger` object is still imported and available, but:
- **Deprecated for new code**: Use Sentry SDK instead
- **Existing fallback**: If Sentry is not initialized, errors will still be logged to stdout

---

## 2026 Best Practices

1. **Always use `push_scope()`**: Provides structured context for each log
2. **Add relevant tags**: Makes filtering and searching easier
3. **Include context data**: Helps with debugging and rootcauseanalysis
4. **Use appropriate levels**: info, warning, error for categorization
5. **Capture full tracebacks**: `capture_exception(e)` includes full stack
6. **Avoid logging sensitive data**: Sentry has PII filtering, but be careful

---

## Accessing Logs

### Via Sentry Dashboard
1. Navigate to https://sentry.io/
2. Select your project
3. Filter by tags (module, status, operation)
4. Click on events to see full context data
5. Create alerts for specific error patterns

### Via Environment Variable Setup
Set these for enhanced tracing:
```bash
SENTRY_TRACES_SAMPLE_RATE=0.1        # 10% of transactions
SENTRY_PROFILES_SAMPLE_RATE=0.1      # 10% of profiles
SENTRY_SEND_DEFAULT_PII=false        # Don't log PII
SENTRY_DEBUG=false                   # Production mode
```

---

## Troubleshooting

**Q: I don't see logs in Sentry**  
A: Verify SENTRY_DSN is set and init_sentry() is called at startup

**Q: Logs not showing in terminal**  
A: LoggingIntegration must be configured in sentry_config.py

**Q: Performance impact?**  
A: Minimal - Sentry async sends by default. Use traces_sample_rate to tune.

---

## Related Files

- Configuration: `src/api/lib/sentry_config.py`
- Settings: `src/api/config.py` (SENTRY_* variables)
- Test: `test_sentry_integration.py` (verification script)

---

**Last Updated**: May 15, 2026  
**Migration Status**: ✅ Complete
