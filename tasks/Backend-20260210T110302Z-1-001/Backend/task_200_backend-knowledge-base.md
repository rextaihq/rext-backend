# Task 200: Add Similarity Search API Endpoint for Knowledge Base

## Metadata
- **Task ID:** TASK-200
- **Source:** Backend Knowledge Base Audit (Finding #9 under P1 High)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P1 High
- **Category:** broken-functionality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The Knowledge Base stores document chunks as vector embeddings in a FAISS index (via `src/utils/vector_store.py`) for retrieval-augmented generation. The `load_vector_store()` function at line 173 returns a fully initialized `FAISS` object from LangChain which natively supports `similarity_search()`, `similarity_search_with_score()`, and their async variants. However, no API endpoint in `src/api/routes/workspaces/workspace_knowledge.py` exposes this search capability. The frontend is therefore unable to perform semantic search over the knowledge base and can only do client-side filtering on pre-fetched metadata.

The audit report references `src/services/embedding_service.py:382-448` as having a `similarity_search()` method, but this file does not exist in the current codebase. The actual vector store operations (add, load, delete) live in `src/utils/vector_store.py`. There is no search wrapper function — only the raw FAISS object returned by `load_vector_store()`. This means both a search utility function and a new route endpoint need to be created to expose vector similarity search to API consumers.

The FAISS instance loaded via LangChain's `FAISS.load_local()` supports metadata-based filtering, which is critical for multi-tenant isolation. Each document stored in FAISS includes `workspace_id`, `knowledge_base_id`, `knowledge_id`, and `knowledge_type` in its metadata (set during `add_to_vector_store()` at lines 136-150). Search results must be filtered to only return documents belonging to the requesting user's workspace.

---

## Current Code

```python
# File: rext-backend/src/utils/vector_store.py
# Lines: 173-212 (load_vector_store — only function available for search)
def load_vector_store(file_path: str = None) -> FAISS:
    """
    Load a FAISS vector store from local storage.
    ...
    Example:
        >>> vector_store = load_vector_store()
        >>> results = vector_store.similarity_search("query text", k=5)
    """
    if file_path is None:
        config = load_yaml()
        file_path = config["vectorStore"]["store_path"]

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Vector store not found at: {file_path}")

    vector_store = FAISS.load_local(
        file_path,
        get_embedding(),
        allow_dangerous_deserialization=True
    )
    return vector_store
```

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# No search endpoint exists — file ends at line 679 with delete_text_knowledge
```

---

## Why This Matters (Context & Reasoning)

The entire purpose of embedding knowledge documents into a vector store is to enable semantic similarity search for RAG workflows. Without an API endpoint exposing this search, the vector embeddings generated during file/text/web knowledge creation serve no purpose at the API level. The frontend must resort to client-side text matching on titles and metadata, which provides none of the semantic understanding that vector search offers. As the knowledge base grows, client-side search becomes increasingly inadequate — it cannot find conceptually related content, only exact text matches.

FAISS's `similarity_search_with_score()` method returns both the matching `Document` objects and their L2 distance scores, enabling the frontend to display relevance-ranked results. The metadata filtering ensures workspace isolation without needing separate FAISS indexes per workspace. According to LangChain's FAISS documentation, `similarity_search_with_score()` accepts a `filter` parameter (dict) that matches against document metadata, making workspace-scoped queries straightforward.

---

## Impact

- **Severity:** The core RAG search capability is completely inaccessible via the API. Vector embeddings are generated and stored but cannot be queried.
- **Affected Users/Flows:** Any user or frontend feature that needs to search knowledge by semantic similarity (e.g., AI content generation, knowledge search, RAG pipelines).
- **Blast Radius:** Affects all workspaces. The write path (embedding generation) works, but the read path (similarity search) is missing.

---

## Recommended Solution

### Step 1: Add Search Function to `vector_store.py`

```python
# File: rext-backend/src/utils/vector_store.py
# Add after the load_vector_store function (after line 212):

def search_vector_store(
    query: str,
    workspace_id: str,
    knowledge_base_id: str = None,
    k: int = 10,
    score_threshold: float = None,
) -> list[dict]:
    """
    Search the FAISS vector store for documents similar to the query.

    Performs semantic similarity search with workspace-level isolation
    via metadata filtering.

    Args:
        query: The search query text.
        workspace_id: Workspace ID for multi-tenant isolation (required).
        knowledge_base_id: Optional KB ID to narrow search scope.
        k: Maximum number of results to return (default 10).
        score_threshold: Optional maximum L2 distance score. Lower is more similar.
                        Results with score above this threshold are excluded.

    Returns:
        List of dicts with keys: content, metadata, score.
    """
    vector_store = load_vector_store()

    # Build metadata filter for workspace isolation
    filter_dict = {"workspace_id": workspace_id}
    if knowledge_base_id:
        filter_dict["knowledge_base_id"] = knowledge_base_id

    results_with_scores = vector_store.similarity_search_with_score(
        query=query,
        k=k,
        filter=filter_dict,
    )

    search_results = []
    for doc, score in results_with_scores:
        # If score_threshold is set, skip results above the threshold
        if score_threshold is not None and score > score_threshold:
            continue

        search_results.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": round(float(score), 4),
        })

    logger.info(
        f"Search completed",
        extra={
            "workspace_id": workspace_id,
            "query_length": len(query),
            "results_returned": len(search_results),
            "k": k,
        },
    )

    return search_results
```

### Step 2: Add Search Request Schema

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Add after the existing schema classes (after line 55):

class KnowledgeSearchRequest(BaseModel):
    """Payload for searching knowledge via vector similarity."""

    query: constr(strip_whitespace=True, min_length=1, max_length=1000)
    knowledge_base_id: Optional[UUID] = None
    limit: int = 10
    score_threshold: Optional[float] = None
```

### Step 3: Add Search Route Endpoint

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# Add after the get_workspace_knowledge route (after line 99), before _resolve_workspace:

@router.post("/search")
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("search knowledge", auto_commit=False)
async def search_knowledge(
    workspace_id: str,
    request: Request,
    payload: KnowledgeSearchRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Search knowledge base using vector similarity."""
    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    from src.utils.vector_store import search_vector_store

    results = search_vector_store(
        query=payload.query,
        workspace_id=str(workspace.id),
        knowledge_base_id=str(payload.knowledge_base_id) if payload.knowledge_base_id else None,
        k=payload.limit,
        score_threshold=payload.score_threshold,
    )

    return success(
        data={
            "results": results,
            "query": payload.query,
            "total_results": len(results),
        },
        request=request,
        message="Knowledge search completed successfully",
    )
```

### Step 4: Add Import for `search_vector_store`

```python
# File: rext-backend/src/api/routes/workspaces/workspace_knowledge.py
# At the top of the file, add to imports (or keep the local import in step 3):
from src.utils.vector_store import search_vector_store
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/utils/vector_store.py` | `173-212` | `load_vector_store()` returns FAISS instance — new `search_vector_store()` builds on it |
| `rext-backend/src/utils/vector_store.py` | `136-150` | Metadata attachment in `add_to_vector_store()` — search filter keys must match these |
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `57-60` | Router definition — new `/search` endpoint registers here |
| `rext-backend/config/config.yaml` | N/A | `vectorStore.store_path` — used by `load_vector_store()` to locate the FAISS index |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Confirm no `/search` endpoint exists: `GET /workspaces/{id}/knowledge/search` → 405 Method Not Allowed or 404
2. Confirm no `POST /workspaces/{id}/knowledge/search` → 404 Not Found
3. Verify that vector store has data by checking FAISS index exists at the configured path

### After Fix (Verify the Solution):
1. Create some knowledge entries (text or file) to populate the vector store
2. Search: `POST /workspaces/{id}/knowledge/search` with body `{"query": "relevant search term", "limit": 5}`
3. Response should contain matching results with content, metadata, and similarity scores
4. Verify workspace isolation: search from workspace A should not return workspace B's documents
5. Test with `knowledge_base_id` filter: results should be limited to that specific KB
6. Test with `score_threshold`: results above the threshold should be excluded
7. Test with empty query: should get validation error (min_length=1)
8. Test when vector store doesn't exist (no FAISS index): should get a graceful error, not 500

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_knowledge_service.py -v
```

---

## Acceptance Criteria

- [ ] New `search_vector_store()` function added to `src/utils/vector_store.py`
- [ ] New `POST /workspaces/{workspace_id}/knowledge/search` endpoint is accessible
- [ ] Search results are filtered by `workspace_id` (multi-tenant isolation)
- [ ] Optional `knowledge_base_id` filter works correctly
- [ ] Optional `score_threshold` filter excludes low-relevance results
- [ ] `limit` parameter caps the number of returned results
- [ ] Response includes content, metadata, and similarity score for each result
- [ ] Graceful error when vector store doesn't exist (FileNotFoundError handled)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [LangChain FAISS similarity_search_with_score](https://python.langchain.com/api_reference/community/vectorstores/langchain_community.vectorstores.faiss.FAISS.html#langchain_community.vectorstores.faiss.FAISS.similarity_search_with_score)
- **Official Docs:** [FAISS Metadata Filtering in LangChain](https://python.langchain.com/docs/integrations/vectorstores/faiss/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [LangChain Vector Store Search Patterns](https://python.langchain.com/docs/how_to/vectorstores/)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None (FAISS index and `load_vector_store()` already exist)
- **Blocks:** None
- **Related:** TASK-194 (Finding #15 — score_threshold parameter unused, same domain)
