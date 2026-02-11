# Task 201: Fix Return Type Annotation Mismatch in load_split_file_data

## Metadata
- **Task ID:** TASK-201
- **Source:** Backend Knowledge Base Audit (Finding #6 under P1 High)
- **Audit Report:** `audit-reports/backend-knowledge-base.md`
- **Priority:** P1 High
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `load_split_file_data()` function in `src/utils/utils.py` at line 8 declares a return type of `-> str`, but it actually returns two different types: a `List[Document]` (from `split_data()` at line 25) on the success path, and an empty `list` (`[]`) on the error path (line 31). The `split_data()` function in `src/utils/splitter.py` has a correct return type annotation of `-> List[Document]`, confirming that `chunks_data` assigned at line 25 is always `List[Document]`. The caller in `src/services/knowledge_service.py` at line 142-144 treats the result as a list by calling `len(chunks)`, which works at runtime but contradicts the declared `-> str` type.

This type mismatch means static type checkers like `mypy` and `pyright` will report errors for every call site that uses list operations on the return value. IDE autocompletion will suggest string methods instead of list methods, and any new developer reading the function signature will incorrectly assume it returns a plain string. The `-> str` annotation is misleading and should be corrected to `-> List[Document]` to match the actual behavior, with proper imports added.

---

## Current Code

```python
# File: rext-backend/src/utils/utils.py
# Lines: 1-31
from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader
from src.utils.splitter import split_data

from src.api.lib.logger import auto_logger

logger = auto_logger()

def load_split_file_data(file_path: str) -> str:    # <-- Wrong return type
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

        return chunks_data                           # <-- Returns List[Document]

    except Exception as e:
        logger.info(f"⚠️ Error loading file {file_path}: {e}")
        return []                                    # <-- Returns list (empty)
```

```python
# File: rext-backend/src/utils/splitter.py
# Lines: 9-13 (correct return type for reference)
def split_data(
    documents: Union[List[Document], str],
    chunk_size: int = 1000,
    overlap: int = 200
) -> List[Document]:                                 # <-- Correctly typed
```

```python
# File: rext-backend/src/services/knowledge_service.py
# Lines: 142-148 (caller treats return as list)
        chunks = load_split_file_data(file_metadata["secure_path"])

        if len(chunks) == 0:                         # <-- Uses list operations
            raise RextValidationException(
                message="Failed to extract content from the file",
                field_errors={"file": ["No content could be extracted from file"]}
            )
```

---

## Why This Matters (Context & Reasoning)

Type annotations are a core part of Python's type safety system. When a function declares `-> str` but returns `List[Document]`, it creates a cascade of problems: static analysis tools flag false errors at every call site, IDE features like autocompletion suggest wrong methods (e.g., `.upper()` instead of `.append()`), and developers reading the code are misled about the function's contract. In a production codebase where multiple developers collaborate, incorrect type annotations can lead to bugs when someone trusts the declared type and writes code expecting a string return value.

Additionally, if the project adds `mypy` or `pyright` to CI/CD in the future, this mismatch will cause build failures. Correcting it now is trivial and prevents technical debt from accumulating.

---

## Impact

- **Severity:** Type checkers report errors, IDE autocompletion is incorrect, developers are misled about the function's actual return type.
- **Affected Users/Flows:** Any developer working with `load_split_file_data()` or running static type analysis.
- **Blast Radius:** Localized to `src/utils/utils.py` and its callers. No runtime behavior change.

---

## Recommended Solution

### Step 1: Fix the Return Type Annotation

```python
# File: rext-backend/src/utils/utils.py
# Replace the entire file:

from typing import List

from langchain_community.document_loaders import PyMuPDFLoader, CSVLoader
from langchain_core.documents import Document
from src.utils.splitter import split_data

from src.api.lib.logger import auto_logger

logger = auto_logger()

def load_split_file_data(file_path: str) -> List[Document]:
    """Load a file and return its content as a list of Document chunks."""
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
        chunks_data = split_data(documents=documents, chunk_size=1000, overlap=200)

        return chunks_data

    except Exception as e:
        logger.info(f"⚠️ Error loading file {file_path}: {e}")
        return []
```

The changes are:
1. Add `from typing import List` import
2. Add `from langchain_core.documents import Document` import
3. Change `-> str` to `-> List[Document]`
4. Update docstring to accurately describe the return type

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/knowledge_service.py` | `142` | Calls `load_split_file_data()` — already treats return as list, no change needed |
| `rext-backend/tests/unit/services/test_knowledge_service.py` | `53, 137, 167` | Mocks `load_split_file_data` — mock returns are already lists, no change needed |
| `rext-backend/src/utils/splitter.py` | `13` | `split_data()` correctly returns `-> List[Document]` — confirms the right type |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `src/utils/utils.py` in an IDE with type checking enabled
2. Observe: Return type shows `str` but actual return is `list`
3. Run `mypy src/utils/utils.py` (if mypy is installed) — expect type errors
4. In IDE, hover over `load_split_file_data()` call — autocomplete suggests string methods

### After Fix (Verify the Solution):
1. Open `src/utils/utils.py` — return type should show `List[Document]`
2. IDE autocomplete should now suggest list methods on the return value
3. Run `mypy src/utils/utils.py` (if mypy is installed) — should pass
4. Verify no runtime changes: existing file upload flow works identically

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/unit/services/test_knowledge_service.py -v
```

---

## Acceptance Criteria

- [ ] Return type annotation changed from `-> str` to `-> List[Document]`
- [ ] `from typing import List` import added
- [ ] `from langchain_core.documents import Document` import added
- [ ] Docstring updated to reflect correct return type
- [ ] No runtime behavior changes
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python typing — List](https://docs.python.org/3.11/library/typing.html#typing.List)
- **Official Docs:** [LangChain Document class](https://python.langchain.com/api_reference/core/documents/langchain_core.documents.base.Document.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [PEP 484 — Type Hints](https://peps.python.org/pep-0484/)
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-198 (Finding #5 — rewrites the same file with full loader support, which also fixes this annotation)
