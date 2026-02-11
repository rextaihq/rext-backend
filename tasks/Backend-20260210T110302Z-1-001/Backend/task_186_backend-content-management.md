# Task 186: Fix Typo "coonect" in sites.py Comment

## Metadata
- **Task ID:** TASK-186
- **Source:** Backend Content Management Audit (Finding #32 under P3 Low)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

In `src/api/routes/content/modules/sites.py` at line 47, a comment reads `#coonect new site` — a misspelling of "connect." While this is a trivial cosmetic issue with no runtime impact, comments serve as documentation for developers reading the code. Misspelled comments reduce the professionalism of the codebase and can cause confusion when searching for terms (e.g., `grep -r "connect"` would miss this comment).

Additionally, the comment style is inconsistent with Python conventions: it lacks a space after the `#` character and does not follow PEP 8's recommendation for inline comments (`# ` with a space, followed by a capitalized sentence). The comment is also redundant since the function name `connect_site` and its docstring `"""Connect a new external site"""` already convey the purpose.

The audit report also identified two other low-value comments in the same file (`#list of connected sites` on line 25, `#details of site` on line 96, `#update the details of connected site` on line 121, `#delete a site` on line 156) that follow the same pattern of being redundant with the function name and docstring. These could be cleaned up at the same time.

---

## Current Code

```python
# File: src/api/routes/content/modules/sites.py
# Line: 47
#coonect new site
@router.post("/connect")
@db_transaction_handler("connect site", "Site connected successfully")
@require_permissions("content.create", workspace_scoped=True)
async def connect_site(
```

Other similar redundant comments in the same file:
```python
# Line 25:
#list of connected sites
@router.get("/list")

# Line 96:
#details of site
@router.get("/{site_id}")

# Line 121:
#update the details of connected site
@router.patch("/{site_id}")

# Line 156:
#delete a site
@router.delete("/{site_id}")
```

---

## Why This Matters (Context & Reasoning)

The `sites.py` file contains the WordPress site integration management endpoints — a user-facing feature for connecting, configuring, and managing external publishing sites. Developers working on this file should be able to trust that comments are accurate. While this is the lowest priority type of fix, it contributes to overall code quality and professionalism. The redundant comments also add visual noise to the file since every function already has a proper docstring that describes its purpose.

---

## Impact

- **Severity:** No runtime impact. Purely cosmetic code quality issue.
- **Affected Users/Flows:** None. Only affects developers reading the source code.
- **Blast Radius:** Isolated to comments in `sites.py`.

---

## Recommended Solution

Remove the typo comment and the other redundant section comments. Each function already has a descriptive name and a docstring — the inline comments above them add no value.

### Step 1: Remove redundant comments from sites.py

```python
# File: src/api/routes/content/modules/sites.py

# Remove line 25: "#list of connected sites"
# Remove line 47: "#coonect new site"
# Remove line 96: "#details of site"
# Remove line 121: "#update the details of connected site"
# Remove line 156: "#delete a site"
```

After removal, each endpoint declaration should start directly with its decorator, for example:

```python
@router.get("/list")
@require_permissions("content.read", workspace_scoped=True)
async def list_connected_sites(
```

```python
@router.post("/connect")
@db_transaction_handler("connect site", "Site connected successfully")
@require_permissions("content.create", workspace_scoped=True)
async def connect_site(
```

```python
@router.get("/{site_id}")
@require_permissions("content.read", workspace_scoped=True)
async def get_site_details(
```

```python
@router.patch("/{site_id}")
@db_transaction_handler("update site", "Site connection updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_site(
```

```python
@router.delete("/{site_id}")
@db_transaction_handler("disconnect site", "Site disconnected successfully")
@require_permissions("content.delete", workspace_scoped=True)
async def delete_site(
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| None | - | This is an isolated comment-only change |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `src/api/routes/content/modules/sites.py`
2. Observe line 47 reads `#coonect new site` (typo)
3. Observe other redundant comments at lines 25, 96, 121, 156

### After Fix (Verify the Solution):
1. Open `src/api/routes/content/modules/sites.py`
2. Confirm the typo comment and all redundant section comments are removed
3. Confirm each endpoint still has its docstring intact
4. Start the application and verify sites endpoints are accessible

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "content or site" -v
```

---

## Acceptance Criteria

- [ ] The `#coonect new site` typo comment on line 47 is removed
- [ ] Other redundant section comments (`#list of connected sites`, `#details of site`, `#update the details of connected site`, `#delete a site`) are removed
- [ ] All function docstrings remain intact
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 8 — Comments](https://peps.python.org/pep-0008/#comments) — Python style guide for comments: use `# ` with a space, write complete sentences, avoid redundant comments that restate the obvious
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** N/A
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
