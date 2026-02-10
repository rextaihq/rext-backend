# Task 191: Replace `backref` with `back_populates` in ContentMedia Model

## Metadata
- **Task ID:** TASK-191
- **Source:** Backend Content Management Audit (Finding #37 under P3 Low)
- **Audit Report:** `audit-reports/backend-content-management.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `ContentMedia` model in `src/api/models/content_models/content_media.py` defines its SQLAlchemy relationships using the `backref` parameter instead of `back_populates`:

```python
content = relationship("Content", backref="media_items")
media = relationship("Media", backref="used_in_content")
```

This is inconsistent with the rest of the codebase. A thorough search of all SQLAlchemy relationship definitions reveals that **51 out of 59 relationships** (86%) use the modern `back_populates` pattern, while only **8 relationships** use the legacy `backref` pattern. The `backref` usage is concentrated in just two areas: the subscription models (`licenses.py`, `subscriptions.py`, `trial_conversions.py`, `payment_methods.py`) and the content models (`content_media.py`).

The SQLAlchemy 2.0 documentation explicitly labels `backref` as a **legacy** parameter: "The `relationship.backref` keyword should be considered legacy, and use of `relationship.back_populates` with explicit `relationship()` constructs should be preferred." The key differences are:

1. **Explicitness:** `back_populates` requires both sides of the relationship to be explicitly defined in their respective models. This makes the relationship visible when reading either model, improving code discoverability.
2. **Tooling support:** Static type checkers (mypy), IDEs (VS Code, PyCharm), and autocompletion tools can properly resolve `back_populates` attributes because they are explicitly declared. `backref` attributes are dynamically generated at runtime, making them invisible to static analysis.
3. **PEP 484 / SQLAlchemy 2.0 typing:** SQLAlchemy 2.0's new typed mapping features (`Mapped[]`, `mapped_column()`) work best with `back_populates` because the attributes are present in source code.

Currently, `ContentMedia` uses `backref="media_items"` which dynamically adds a `media_items` attribute to the `Content` model and `backref="used_in_content"` which dynamically adds a `used_in_content` attribute to the `Media` model. Neither the `Content` model nor the `Media` model has any explicit declaration of these reverse relationships, making them invisible when reading those files.

---

## Current Code

```python
# File: src/api/models/content_models/content_media.py
# Lines: 64-66
    # Relationships
    content = relationship("Content", backref="media_items")
    media = relationship("Media", backref="used_in_content")
```

For context, the `Content` model currently defines its relationships as:

```python
# File: src/api/models/content_models/content.py
# Lines: 47-50
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan")
```

Note: `Content` has no explicit `media_items` relationship — it is dynamically injected by `ContentMedia`'s `backref`.

And the `Media` model:

```python
# File: src/api/models/media_models/media.py
# Lines: 104-106
    workspace = relationship("WorkspaceModel", back_populates="media")
    user = relationship("Users", back_populates="media")
```

Note: `Media` has no explicit `used_in_content` relationship — it is also dynamically injected.

---

## Why This Matters (Context & Reasoning)

`ContentMedia` is a junction table that links content items to media files. It enables tracking which media files are used within content body, supporting features like: listing all media in a piece of content, finding all content that uses a specific media file, preventing deletion of in-use media, and identifying orphaned media files.

The `media_items` reverse relationship on `Content` is actively used in the codebase — for example, in `content_service.py:160-168` where media items are cleared and re-added during content updates. A developer reading `content.py` would see no declaration of `media_items` and might not realize it exists until they encounter it being used in service code. With `back_populates`, both sides are explicit.

This inconsistency also matters for future adoption of SQLAlchemy 2.0's typed mapping features. The project currently uses the classic `Column()` style, but when migrating to `Mapped[]/mapped_column()`, `back_populates` is required for proper type inference.

---

## Impact

- **Severity:** Low — functionally equivalent. Improves code discoverability, IDE support, and SQLAlchemy 2.0 compatibility.
- **Affected Users/Flows:** No user-facing impact.
- **Blast Radius:** Requires changes to three model files (`content_media.py`, `content.py`, `media.py`) to add explicit reverse relationship declarations.

---

## Recommended Solution

### Step 1: Update `ContentMedia` to use `back_populates`

```python
# File: src/api/models/content_models/content_media.py
# Replace lines 64-66 with:
    # Relationships
    content = relationship("Content", back_populates="media_items")
    media = relationship("Media", back_populates="used_in_content")
```

### Step 2: Add explicit `media_items` relationship to `Content` model

```python
# File: src/api/models/content_models/content.py
# Add after line 50 (after the seo_data relationship):
    media_items = relationship("ContentMedia", back_populates="content", cascade="all, delete-orphan")
```

The full relationships section of `Content` should now be:

```python
# File: src/api/models/content_models/content.py
# Lines: 47-51 (after fix)
    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan")
    media_items = relationship("ContentMedia", back_populates="content", cascade="all, delete-orphan")
```

### Step 3: Add explicit `used_in_content` relationship to `Media` model

```python
# File: src/api/models/media_models/media.py
# Add after line 106 (after the user relationship):
    used_in_content = relationship("ContentMedia", back_populates="media", cascade="all, delete-orphan")
```

The full relationships section of `Media` should now be:

```python
# File: src/api/models/media_models/media.py
# Lines: 104-107 (after fix)
    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="media")
    user = relationship("Users", back_populates="media")
    used_in_content = relationship("ContentMedia", back_populates="media", cascade="all, delete-orphan")
```

**Note on `cascade="all, delete-orphan"`:** This cascade ensures that when a `Content` or `Media` record is deleted, the associated `ContentMedia` junction records are also removed. This is consistent with the `ondelete="CASCADE"` defined on the foreign keys in `ContentMedia`.

---

## Other Affected Locations

The same `backref` pattern exists in 6 other relationships across subscription models:

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/models/subscription_models/licenses.py` | `53` | `user = relationship("Users", backref="licenses")` |
| `src/api/models/subscription_models/subscriptions.py` | `77` | `user = relationship("Users", backref="subscriptions")` |
| `src/api/models/subscription_models/trial_conversions.py` | `103-105` | Three `backref` relationships (user, subscription, plan) |
| `src/api/models/subscription_models/payment_methods.py` | `43` | `user = relationship("Users", backref="payment_methods")` |

These should be addressed in a separate task for consistency (already tracked in TASK-050).

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `src/api/models/content_models/content_media.py` and observe lines 65-66 use `backref=`.
2. Open `src/api/models/content_models/content.py` and confirm there is no `media_items` relationship defined.
3. Open `src/api/models/media_models/media.py` and confirm there is no `used_in_content` relationship defined.

### After Fix (Verify the Solution):
1. Confirm `content_media.py` uses `back_populates=` on both relationships.
2. Confirm `content.py` has an explicit `media_items = relationship(...)` line.
3. Confirm `media.py` has an explicit `used_in_content = relationship(...)` line.
4. Verify the application starts without SQLAlchemy relationship configuration errors.
5. Test content creation with media items to ensure the junction table still works.
6. Test content deletion to ensure cascade deletes work correctly.

### Run Existing Tests:
```bash
cd rext-backend
python -m pytest tests/unit/services/test_content_service.py -v
python -m pytest tests/ -k "media" -v
```

---

## Acceptance Criteria

- [ ] `ContentMedia.content` relationship uses `back_populates="media_items"` instead of `backref="media_items"`
- [ ] `ContentMedia.media` relationship uses `back_populates="used_in_content"` instead of `backref="used_in_content"`
- [ ] `Content` model has an explicit `media_items` relationship with `back_populates="content"`
- [ ] `Media` model has an explicit `used_in_content` relationship with `back_populates="media"`
- [ ] Application starts without relationship configuration errors
- [ ] Content CRUD operations with media items work correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 — Using the legacy 'backref' relationship parameter](https://docs.sqlalchemy.org/en/20/orm/backref.html) — States that `backref` "should be considered legacy" and `back_populates` is preferred
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy Relationship: backref vs back_populates](https://medium.com/@kimberlymlove15/sqlalchemy-relationship-status-its-complicated-backref-vs-back-populates-9eaf07335a13) — Explains advantages of `back_populates` for explicitness and tooling support
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-050 (Mixed back_populates vs backref Patterns, B2) — addresses the same pattern in subscription models
