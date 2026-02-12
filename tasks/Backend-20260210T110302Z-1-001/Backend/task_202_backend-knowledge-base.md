# Task 202: Fix Empty Content Silently Returns Zero Chunks in Splitter

## Metadata
- **Task ID:** TASK-202
- **Source:** Backend Knowledge Base Audit (Finding #14 under P2 Medium)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P2 Medium
- **Category:** data-integrity
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `split_data()` function in `src/utils/splitter.py` at lines 105-106 has a bare `except Exception` handler that catches all errors — including `ValueError` raised for invalid input at line 100 — logs the error at `INFO` level using an incorrect `logger.info("Error:", str(e))` call, and returns an empty list `[]`. This silent failure means that when content splitting fails for any reason (malformed input, unexpected document types, internal errors), the caller receives an empty list with no indication that an error occurred.

The primary caller is `load_split_file_data()` in `src/utils/utils.py` at line 25, which assigns the result to `chunks_data` and returns it. When `split_data()` silently returns `[]`, the `load_split_file_data()` function also returns `[]` (since it has its own bare exception handler at line 29-31 that converts any exception to `[]`). This empty list then propagates to `KnowledgeService.add_file_knowledge()` at line 142-144, where `len(chunks) == 0` triggers a `RextValidationException` with the message "Failed to extract content from the file." While this does prevent empty knowledge entries from being created, the user receives a misleading error suggesting the file is corrupt or empty, when in fact the splitter may have encountered a programming bug, a memory error, or an incompatible document format.

The `logger.info("Error:", str(e))` call at line 106 is also syntactically incorrect for structured logging — it passes `str(e)` as a positional argument rather than interpolating it, which means the actual error message may not appear in the log output depending on the logging configuration. Combined with the `INFO` level (instead of `ERROR`), this makes debugging splitter failures extremely difficult in production.

---

## Current Code

```python
# File: rext-backend/src/utils/splitter.py
# Lines: 67-107

    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap
        )

        chunked_docs = []

        if isinstance(documents, list) and all(isinstance(doc, Document) for doc in documents):
            # Case 1: Input is a list of Documents
            for doc in documents:
                chunks = text_splitter.split_text(doc.page_content)
                for idx, chunk in enumerate(chunks):
                    chunked_docs.append(Document(
                        page_content=chunk,
                        metadata={
                            **doc.metadata,
                            "chunk_id": idx,
                            "total_chunks": len(chunks),
                            "length": len(chunk)
                        }
                    ))
        elif isinstance(documents, str):
            # Case 2: Input is a plain string
            chunks = text_splitter.create_documents([documents])
            for idx, doc in enumerate(chunks):
                doc.metadata.update({
                    "chunk_id": idx,
                    "total_chunks": len(chunks),
                    "length": len(doc.page_content)
                })
                chunked_docs.append(doc)
        else:
            raise ValueError("documents must be either a string or List[Document].")

        logger.info(f"Data split successfully! Total chunks: {len(chunked_docs)}")
        return chunked_docs

    except Exception as e:
        logger.info("Error:", str(e))    # Wrong: INFO level, incorrect format
        return []                        # Silent failure: returns empty list
```

```python
# File: rext-backend/src/utils/utils.py
# Lines: 24-31 (caller also has silent failure)

        # split into chunks
        chunks_data = split_data(documents=documents,chunk_size=1000,overlap=200)

        return chunks_data

    except Exception as e:
        logger.info(f"⚠️ Error loading file {file_path}: {e}")
        return []
```

```python
# File: rext-backend/src/services/knowledge_service.py
# Lines: 142-148 (ultimate consumer receives misleading error)
        chunks = load_split_file_data(file_metadata["secure_path"])

        if len(chunks) == 0:
            raise RextValidationException(
                message="Failed to extract content from the file",
                field_errors={"file": ["No content could be extracted from file"]}
            )
```

---

## Why This Matters (Context & Reasoning)

Silent failures in the data pipeline are one of the most dangerous patterns in backend systems. When the text splitter fails silently, the error is masked behind a generic "Failed to extract content" message that gives users (and developers) no clue about the root cause. A developer debugging a file upload failure would see the `RextValidationException` in the knowledge service and assume the file is empty or corrupt, when the actual cause might be a bug in the splitter logic, a missing dependency, or a memory issue during chunk creation.

The incorrect log format `logger.info("Error:", str(e))` compounds the problem. In most Python logging configurations, `logger.info("Error:", str(e))` treats `str(e)` as an argument to `%`-style formatting of the message `"Error:"`, which has no format specifiers — so the actual error message is silently discarded. Even if the error were logged correctly, using `INFO` level means it would be filtered out in production environments that typically log at `WARNING` or higher.

Proper error handling here should either propagate the exception to the caller (letting the caller decide how to handle it) or log at `ERROR` level with the full exception traceback and re-raise.

---

## Impact

- **Severity:** Splitter failures are invisible in logs and produce misleading user-facing error messages. Debugging file processing failures is extremely difficult.
- **Affected Users/Flows:** Any file or text knowledge creation that encounters a splitter error.
- **Blast Radius:** Affects the entire knowledge ingestion pipeline (file upload, text creation, web scraping) since all paths use `split_data()`.

---

## Recommended Solution

### Step 1: Fix Error Handling in `split_data()`

```python
# File: rext-backend/src/utils/splitter.py
# Replace lines 105-107 (the except block):

    except ValueError:
        # Re-raise validation errors (e.g., invalid input type) as-is
        raise
    except Exception as e:
        logger.error(
            f"Failed to split documents into chunks: {e}",
            exc_info=True,
        )
        raise ValueError(f"Text splitting failed: {e}") from e
```

This change:
1. Lets `ValueError` (from invalid input at line 100) propagate directly instead of being caught and silenced
2. Logs unexpected errors at `ERROR` level with full traceback (`exc_info=True`)
3. Re-raises as `ValueError` so callers can handle it appropriately
4. Removes the silent `return []` path entirely

### Step 2: Update `load_split_file_data()` Error Handling (Complementary)

```python
# File: rext-backend/src/utils/utils.py
# Replace lines 29-31 (the except block):

    except Exception as e:
        logger.error(f"Error loading file {file_path}: {e}", exc_info=True)
        return []
```

This changes the log level from `INFO` to `ERROR` and adds `exc_info=True` for the full traceback. The `return []` is kept here because the caller (`knowledge_service.py` line 144) already handles empty chunks gracefully.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/utils.py` | `25` | Calls `split_data()` — will now receive exceptions instead of empty list |
| `rext-backend/src/utils/utils.py` | `29-31` | Exception handler catches errors from `split_data()` — should log at ERROR |
| `rext-backend/src/services/knowledge_service.py` | `142-148` | Calls `load_split_file_data()` — behavior unchanged (still checks `len(chunks) == 0`) |
| `rext-backend/src/services/knowledge_service.py` | `316-325` | `add_text_knowledge()` also calls `split_data()` directly for text content |
| `rext-backend/tests/unit/services/test_knowledge_service.py` | `167-183` | `test_add_file_knowledge_empty_content` — mocks `load_split_file_data` to return `[]`, still valid |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Pass an invalid document type to `split_data()` (e.g., a dict) — observe: returns `[]` silently
2. Check logs — the error message is either missing or logged at INFO level
3. Upload a file that triggers a splitter error — user sees "Failed to extract content from the file" with no useful details in logs

### After Fix (Verify the Solution):
1. Pass an invalid document type to `split_data()` — should raise `ValueError` with clear message
2. Simulate a splitting failure — should log at ERROR level with full traceback
3. Upload a valid PDF file — should still work normally (success path unchanged)
4. Upload a valid CSV file — should still work normally
5. Check that the caller (`load_split_file_data()`) properly catches the new exceptions
6. Verify logs contain ERROR-level entries for any splitting failures

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_knowledge_service.py -v
```

---

## Acceptance Criteria

- [ ] `split_data()` no longer returns `[]` on error — it raises exceptions
- [ ] `ValueError` from input validation (line 100) propagates without being caught
- [ ] Unexpected errors are logged at `ERROR` level with `exc_info=True`
- [ ] Incorrect `logger.info("Error:", str(e))` format is fixed
- [ ] `load_split_file_data()` logs errors at `ERROR` level (not `INFO`)
- [ ] Success path behavior is unchanged (valid files still produce chunks)
- [ ] No new warnings or errors introduced for valid inputs
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python logging — Exception Information](https://docs.python.org/3.11/library/logging.html#logging.Logger.error)
- **Official Docs:** [LangChain RecursiveCharacterTextSplitter](https://python.langchain.com/api_reference/text_splitters/character/langchain_text_splitters.character.RecursiveCharacterTextSplitter.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python Exception Handling Best Practices](https://docs.python.org/3.11/tutorial/errors.html)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-198 (Finding #5 — rewrites `utils.py` which also calls `split_data()`)
- **Related:** TASK-201 (Finding #6 — fixes return type annotation in the same calling function)
