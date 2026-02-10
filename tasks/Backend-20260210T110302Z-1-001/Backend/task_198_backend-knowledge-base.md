# Task 198: Implement Missing File Type Loaders for Knowledge Base Uploads

## Metadata
- **Task ID:** TASK-198
- **Source:** Backend Knowledge Base Audit (Finding #5 under P1 High)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The `load_split_file_data()` function in `src/utils/utils.py` only implements document loaders for PDF (via `PyMuPDFLoader`) and CSV (via `CSVLoader`) file types. However, the file upload route in `src/api/routes/workspaces/workspace_knowledge.py` (lines 352-367) explicitly allows uploads of DOC, DOCX, TXT, XLS, XLSX, and image files by listing their MIME types in `allowed_types`. When a user uploads any of these non-PDF/CSV file types, the `load_split_file_data()` function falls through to the `else` branch at line 19 which sets `documents = []`. This empty list then triggers the `if not documents: raise ValueError("No documents loaded")` check at line 21-22, which is caught by the generic exception handler at line 29 and silently returns an empty list `[]`.

Back in `knowledge_service.py` line 142-148, the empty chunks list causes `len(chunks) == 0` to be true, which raises a `RextValidationException` with the message "Failed to extract content from the file." This means users can successfully upload DOCX, TXT, XLSX, and other files (they pass MIME validation), but the system always fails to extract content from them, giving a misleading error that implies the file is empty or corrupt when in fact the loader simply doesn't exist for that file type.

According to the LangChain Community documentation, the proper loaders for these file types are `Docx2txtLoader` (for DOCX/DOC), `TextLoader` (for TXT), and `UnstructuredExcelLoader` (for XLS/XLSX), all available from `langchain_community.document_loaders`. These loaders require additional Python packages (`docx2txt` for Word files, `openpyxl` for Excel files) that are not currently listed in `pyproject.toml`.

---

## Current Code

```python
# File: rext-backend/src/utils/utils.py
# Lines: 1-32
from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader
from src.utils.splitter import split_data

from src.api.lib.logger import auto_logger

logger = auto_logger()

def load_split_file_data(file_path: str) -> str:
    """Load and return the content of a file as text."""
    try:
        # load file
        if file_path.endswith(".pdf"):
            loader = PyMuPDFLoader(file_path)
            documents = loader.load()
        elif file_path.endswith(".csv"):
            loader = CSVLoader(file_path)
            documents = loader.load()
        else:
            documents = []

        if not documents:
            raise ValueError("No documents loaded")

        # split into chunks
        chunks_data = split_data(documents=documents,chunk_size=1000,overlap=200)

        return chunks_data

    except Exception as e:
        logger.info(f"⚠️ Error loading file {file_path}: {e}")
        return []
```

---

## Why This Matters (Context & Reasoning)

The Knowledge Base is a core RAG (Retrieval-Augmented Generation) feature of Rext AI. Users upload documents so the system can extract their content, split it into chunks, generate vector embeddings, and use those embeddings for contextual content generation. If uploaded files can't be processed, the entire knowledge pipeline is broken for that file type. The route explicitly advertises support for DOC, DOCX, TXT, XLS, XLSX, and image MIME types — users expect these to work. The current silent failure (files are stored but never searchable) creates a poor user experience and wastes storage.

---

## Impact

- **Severity:** Users uploading DOCX, DOC, TXT, XLS, or XLSX files always get "Failed to extract content" errors despite the UI accepting those file types. Files are stored but contribute zero searchable knowledge.
- **Affected Users/Flows:** Any user uploading non-PDF/non-CSV files to the Knowledge Base.
- **Blast Radius:** Affects all workspaces attempting to use document-based knowledge from Word, Excel, or plain text files.

---

## Recommended Solution

### Step 1: Add Required Dependencies to `pyproject.toml`

```toml
# File: rext-backend/pyproject.toml
# Add these to the dependencies list:
    "docx2txt>=0.8",
    "openpyxl>=3.1.0",
```

### Step 2: Replace `src/utils/utils.py` with Full Loader Support

```python
# File: rext-backend/src/utils/utils.py
# Replace entire file content:
import os
from typing import List

from langchain_community.document_loaders import (
    PyMuPDFLoader,
    CSVLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from langchain_core.documents import Document

from src.utils.splitter import split_data
from src.api.lib.logger import auto_logger

logger = auto_logger()

# Map file extensions to their corresponding LangChain document loader classes.
# Each loader converts a file into a list of LangChain Document objects.
LOADER_MAP: dict[str, type] = {
    ".pdf": PyMuPDFLoader,
    ".csv": CSVLoader,
    ".docx": Docx2txtLoader,
    ".doc": Docx2txtLoader,
    ".txt": TextLoader,
    ".xlsx": UnstructuredExcelLoader,
    ".xls": UnstructuredExcelLoader,
}

SUPPORTED_EXTENSIONS = set(LOADER_MAP.keys())


def load_split_file_data(
    file_path: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> List[Document]:
    """
    Load a file, extract its text content, and split into chunks for vector embedding.

    Supports: PDF, CSV, DOCX, DOC, TXT, XLSX, XLS.

    Args:
        file_path: Absolute path to the file on disk.
        chunk_size: Maximum characters per chunk (default 1000).
        overlap: Overlapping characters between consecutive chunks (default 200).

    Returns:
        List of LangChain Document objects (chunks), each with page_content and metadata.

    Raises:
        ValueError: If the file extension is not supported or no content could be extracted.
    """
    ext = os.path.splitext(file_path)[1].lower()
    loader_cls = LOADER_MAP.get(ext)

    if loader_cls is None:
        raise ValueError(
            f"Unsupported file extension '{ext}'. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        loader = loader_cls(file_path)
        documents = loader.load()
    except Exception as e:
        logger.error(f"Failed to load file {file_path} with {loader_cls.__name__}: {e}")
        raise ValueError(f"Failed to extract content from file: {e}") from e

    if not documents:
        raise ValueError(f"No content could be extracted from {file_path}")

    chunks_data = split_data(documents=documents, chunk_size=chunk_size, overlap=overlap)

    if not chunks_data:
        raise ValueError(f"File content was extracted but produced zero chunks: {file_path}")

    logger.info(
        f"File loaded and split successfully",
        extra={
            "file_path": file_path,
            "extension": ext,
            "documents_loaded": len(documents),
            "chunks_produced": len(chunks_data),
        },
    )

    return chunks_data
```

### Step 3: Install New Dependencies

```bash
cd rext-backend && pip install docx2txt>=0.8 openpyxl>=3.1.0
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/knowledge_service.py` | `142` | Calls `load_split_file_data()` — will now get proper errors instead of empty lists |
| `rext-backend/src/api/routes/workspaces/workspace_knowledge.py` | `352-367` | Defines allowed MIME types — should stay in sync with loader support |
| `rext-backend/tests/unit/services/test_knowledge_service.py` | `53, 137, 167` | Mocks `load_split_file_data` — tests may need updating for new signature |
| `rext-backend/src/utils/splitter.py` | `105-107` | Error handling returns `[]` — related issue (see TASK-202) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Start the backend server
2. Upload a `.docx` file via `POST /workspaces/{id}/knowledge/files`
3. Observe the response: `400 "Failed to extract content from the file"`
4. Upload a `.txt` file — same error
5. Upload a `.xlsx` file — same error
6. Upload a `.pdf` file — works correctly

### After Fix (Verify the Solution):
1. Upload a `.docx` file — should succeed, return file knowledge with chunk_count > 0
2. Upload a `.txt` file — should succeed
3. Upload a `.xlsx` file — should succeed
4. Upload a `.pdf` file — still works
5. Upload a `.csv` file — still works
6. Upload an unsupported file type (e.g., `.mp3`) — should get clear error about unsupported extension
7. Upload an empty `.txt` file — should get "No content could be extracted" error

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_knowledge_service.py -v
```

---

## Acceptance Criteria

- [ ] `load_split_file_data()` successfully extracts content from DOCX files
- [ ] `load_split_file_data()` successfully extracts content from DOC files
- [ ] `load_split_file_data()` successfully extracts content from TXT files
- [ ] `load_split_file_data()` successfully extracts content from XLSX files
- [ ] `load_split_file_data()` successfully extracts content from XLS files
- [ ] PDF and CSV files continue to work as before
- [ ] Unsupported file extensions raise a clear `ValueError` (not silent empty list)
- [ ] Return type annotation is corrected to `List[Document]` (was `str`)
- [ ] `docx2txt` and `openpyxl` are added to `pyproject.toml`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [LangChain Community Docx2txtLoader](https://python.langchain.com/api_reference/community/document_loaders/langchain_community.document_loaders.word_document.Docx2txtLoader.html)
- **Official Docs:** [LangChain Microsoft Excel Integration](https://docs.langchain.com/oss/python/integrations/document_loaders/microsoft_excel)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [LangChain Document Loaders Overview](https://python.langchain.com/api_reference/community/document_loaders.html)
- **Related Issues/PRs:** [langchain-ai/langchain#12399 — Docx2txtLoader issues](https://github.com/langchain-ai/langchain/issues/12399)

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-201 (Return Type Annotation Mismatch — same file, same function)
