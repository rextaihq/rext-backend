# Task 050: Migrate All backref Usages to Explicit back_populates Relationships

## Metadata
- **Task ID:** TASK-050
- **Source:** Backend Database & Migrations Audit (Finding #17 under P2 Medium)
- **Audit Report:** `audit-reports/backend-database-migrations.md`
- **Priority:** P2 Medium
- **Category:** code-quality
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The codebase mixes two SQLAlchemy relationship configuration patterns: the legacy `backref` keyword and the modern `back_populates` keyword. Eight relationship declarations across five model files use `backref`, while all other ~60+ relationships in the codebase use `back_populates`. The `backref` keyword is considered legacy in SQLAlchemy 2.0, where `back_populates` is the recommended approach because it makes both sides of a bidirectional relationship explicit and discoverable.

The `backref` keyword implicitly creates a reverse relationship attribute on the target model — for example, `user = relationship("Users", backref="subscriptions")` on `UserSubscription` (line 77 of `subscriptions.py`) silently adds a `.subscriptions` attribute to `Users` without any visible declaration in the `Users` model file. This makes the `Users` model's API surface partially hidden: a developer reading `users.py` cannot see that `Users` has a `.subscriptions` attribute, a `.trial_conversions` attribute, a `.licenses` attribute, or a `.payment_methods` attribute, because these are declared in other files via `backref`.

A comprehensive grep search found **8 `backref=` usages** across **5 files**, two more than the audit report identified (the audit missed `licenses.py:53` and `payment_methods.py:43`):

1. `subscriptions.py:77` — `user = relationship("Users", backref="subscriptions")`
2. `trial_conversions.py:103` — `user = relationship("Users", backref="trial_conversions")`
3. `trial_conversions.py:104` — `subscription = relationship("UserSubscription", backref="trial_conversions")`
4. `trial_conversions.py:105` — `plan = relationship("SubscriptionPlan", backref="trial_conversions")`
5. `content_media.py:65` — `content = relationship("Content", backref="media_items")`
6. `content_media.py:66` — `media = relationship("Media", backref="used_in_content")`
7. `licenses.py:53` — `user = relationship("Users", backref="licenses")`
8. `payment_methods.py:43` — `user = relationship("Users", backref="payment_methods")`

The `Users` model (`users.py`) has no corresponding `back_populates` declarations for `subscriptions`, `trial_conversions`, `licenses`, or `payment_methods`. Similarly, `Content` has no visible `media_items` relationship, `Media` has no `used_in_content` relationship, `UserSubscription` has no `trial_conversions` relationship from its side, and `SubscriptionPlan` has no `trial_conversions` relationship.

---

## Current Code

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Line 77: backref creates implicit Users.subscriptions
    user = relationship("Users", backref="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")  # Correct pattern on same model!
```

```python
# File: rext-backend/src/api/models/subscription_models/trial_conversions.py
# Lines 103-105: Three backrefs on one model
    user = relationship("Users", backref="trial_conversions")
    subscription = relationship("UserSubscription", backref="trial_conversions")
    plan = relationship("SubscriptionPlan", backref="trial_conversions")
```

```python
# File: rext-backend/src/api/models/content_models/content_media.py
# Lines 65-66: Both relationships use backref
    content = relationship("Content", backref="media_items")
    media = relationship("Media", backref="used_in_content")
```

```python
# File: rext-backend/src/api/models/subscription_models/licenses.py
# Line 53: backref creates implicit Users.licenses
    user = relationship("Users", backref="licenses")
```

```python
# File: rext-backend/src/api/models/subscription_models/payment_methods.py
# Line 43: backref creates implicit Users.payment_methods
    user = relationship("Users", backref="payment_methods")
```

---

## Why This Matters (Context & Reasoning)

The `Users` model is the central entity in the Rext backend, referenced by dozens of other models. When four of its reverse relationships are implicitly defined via `backref` in other files, a developer reading `users.py` sees relationships like `notification_preferences`, `sessions`, `email_preferences`, `preferences`, `media`, `oauth_accounts`, `onboarding`, `discount_usages`, `refunds`, and `notifications` — all explicit via `back_populates`. But they cannot see `subscriptions`, `trial_conversions`, `licenses`, or `payment_methods` without searching the entire codebase. This inconsistency makes the `Users` model's API surface incomplete and misleading.

The SQLAlchemy 2.0 migration guide explicitly states: "The `backref` keyword should now be considered legacy, and the `relationship.back_populates` migration is preferred." While `backref` is not formally deprecated with a warning, the SQLAlchemy maintainers recommend `back_populates` for all new code and encourage migration of existing code.

Mixing the two patterns on the same model (as `UserSubscription` does — `backref` for `user` but `back_populates` for `plan`) further compounds the confusion.

---

## Impact

- **Severity:** No runtime error. This is a maintainability and discoverability issue. Developers may unknowingly create conflicting relationships or fail to find existing ones.
- **Affected Users/Flows:** Development velocity. Every developer working with the `Users`, `Content`, `Media`, `UserSubscription`, or `SubscriptionPlan` models is affected.
- **Blast Radius:** Low to moderate. The changes are syntactic (no schema changes), but touch multiple model files on both sides of each relationship.

---

## Recommended Solution

For each `backref` usage, replace it with `back_populates` on the source model and add an explicit `relationship()` with `back_populates` on the target model.

### Step 1: Fix UserSubscription.user (subscriptions.py)

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Line 77 — Change:
#   user = relationship("Users", backref="subscriptions")
# To:
    user = relationship("Users", back_populates="subscriptions")
```

```python
# File: rext-backend/src/api/models/user_models/users.py
# Add after line 57 (after refunds relationship):
    subscriptions = relationship("UserSubscription", back_populates="user", cascade="all, delete-orphan")
```

### Step 2: Fix TrialConversion relationships (trial_conversions.py)

```python
# File: rext-backend/src/api/models/subscription_models/trial_conversions.py
# Lines 103-105 — Change:
#   user = relationship("Users", backref="trial_conversions")
#   subscription = relationship("UserSubscription", backref="trial_conversions")
#   plan = relationship("SubscriptionPlan", backref="trial_conversions")
# To:
    user = relationship("Users", back_populates="trial_conversions")
    subscription = relationship("UserSubscription", back_populates="trial_conversions")
    plan = relationship("SubscriptionPlan", back_populates="trial_conversions")
```

```python
# File: rext-backend/src/api/models/user_models/users.py
# Add after the subscriptions relationship added in Step 1:
    trial_conversions = relationship("TrialConversion", back_populates="user", cascade="all, delete-orphan")
```

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Add after the existing relationships (after line 80):
    trial_conversions = relationship("TrialConversion", back_populates="subscription")
```

```python
# File: rext-backend/src/api/models/subscription_models/plans.py
# Add after line 50 (after subscriptions relationship):
    trial_conversions = relationship("TrialConversion", back_populates="plan")
```

### Step 3: Fix ContentMedia relationships (content_media.py)

```python
# File: rext-backend/src/api/models/content_models/content_media.py
# Lines 65-66 — Change:
#   content = relationship("Content", backref="media_items")
#   media = relationship("Media", backref="used_in_content")
# To:
    content = relationship("Content", back_populates="media_items")
    media = relationship("Media", back_populates="used_in_content")
```

```python
# File: rext-backend/src/api/models/content_models/content.py
# Add after line 50 (after seo_data relationship):
    media_items = relationship("ContentMedia", back_populates="content", cascade="all, delete-orphan")
```

```python
# File: rext-backend/src/api/models/media_models/media.py
# Add after line 106 (after user relationship):
    used_in_content = relationship("ContentMedia", back_populates="media")
```

### Step 4: Fix License.user (licenses.py)

```python
# File: rext-backend/src/api/models/subscription_models/licenses.py
# Line 53 — Change:
#   user = relationship("Users", backref="licenses")
# To:
    user = relationship("Users", back_populates="licenses")
```

```python
# File: rext-backend/src/api/models/user_models/users.py
# Add after the trial_conversions relationship:
    licenses = relationship("License", back_populates="user")
```

### Step 5: Fix PaymentMethod.user (payment_methods.py)

```python
# File: rext-backend/src/api/models/subscription_models/payment_methods.py
# Line 43 — Change:
#   user = relationship("Users", backref="payment_methods")
# To:
    user = relationship("Users", back_populates="payment_methods")
```

```python
# File: rext-backend/src/api/models/user_models/users.py
# Add after the licenses relationship:
    payment_methods = relationship("PaymentMethod", back_populates="user", cascade="all, delete-orphan")
```

### Summary of All Changes to users.py

After all steps, the Users model will have these new explicit relationships added:

```python
# File: rext-backend/src/api/models/user_models/users.py
# Add these after the existing relationships (after line 58):
    subscriptions = relationship("UserSubscription", back_populates="user", cascade="all, delete-orphan")
    trial_conversions = relationship("TrialConversion", back_populates="user", cascade="all, delete-orphan")
    licenses = relationship("License", back_populates="user")
    payment_methods = relationship("PaymentMethod", back_populates="user", cascade="all, delete-orphan")
```

Note: `License` uses `ondelete="SET NULL"` on the FK (nullable), so `cascade="all, delete-orphan"` is not appropriate — omit the cascade or use a soft reference.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/api/models/user_models/users.py` | 44-58 | Existing relationship declarations — new relationships added alongside these |
| `rext-backend/src/api/models/subscription_models/plans.py` | 50 | Existing `subscriptions` relationship — `trial_conversions` relationship added alongside |
| `rext-backend/src/api/models/subscription_models/subscriptions.py` | 77-80 | Existing relationships — `trial_conversions` reverse relationship added |
| `rext-backend/src/api/models/content_models/content.py` | 47-50 | Existing relationships — `media_items` reverse relationship added |
| `rext-backend/src/api/models/media_models/media.py` | 104-106 | Existing relationships — `used_in_content` reverse relationship added |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open `rext-backend/src/api/models/user_models/users.py` and search for `subscriptions` — it is NOT listed among the explicit relationships
2. In a Python shell, verify the implicit attribute exists: `hasattr(Users, 'subscriptions')` returns `True` despite no visible declaration
3. Run `grep -r "backref=" rext-backend/src/api/models/` — count 8 results

### After Fix (Verify the Solution):
1. Open `users.py` — verify `subscriptions`, `trial_conversions`, `licenses`, and `payment_methods` are all explicitly listed
2. Run `grep -r "backref=" rext-backend/src/api/models/` — should return 0 results
3. In a Python shell, verify all relationships still work:
   - `user.subscriptions` returns the user's subscriptions
   - `subscription.user` returns the subscription's user
   - `trial_conversion.plan` returns the plan
   - `content_media.content` returns the content
4. Verify no circular import issues by starting the FastAPI app

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v --no-header
```

---

## Acceptance Criteria

- [ ] Zero `backref=` usages remain in the models directory (`grep -r "backref=" src/api/models/` returns nothing)
- [ ] All 8 relationships converted to explicit `back_populates` on both sides
- [ ] `Users` model has explicit `subscriptions`, `trial_conversions`, `licenses`, `payment_methods` relationships
- [ ] `Content` model has explicit `media_items` relationship
- [ ] `Media` model has explicit `used_in_content` relationship
- [ ] `UserSubscription` model has explicit `trial_conversions` relationship
- [ ] `SubscriptionPlan` model has explicit `trial_conversions` relationship
- [ ] Application starts without import errors or relationship configuration warnings
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 Relationship Configuration — back_populates](https://docs.sqlalchemy.org/en/20/orm/relationships.html#setting-bi-directional-back-populates) — Official documentation for `back_populates` as the preferred bidirectional relationship configuration
- **Security Advisory:** N/A
- **Migration Guide:** [SQLAlchemy 2.0 Major Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html) — States "The backref keyword should now be considered legacy"
- **Best Practice Reference:** [SQLAlchemy Relationships Without Foreign Keys (back_populates guide)](https://that.guru/blog/sqlalchemy-relationships-without-foreign-keys/) — Practical guide to replacing `backref` with `back_populates`
- **Related Issues/PRs:** N/A

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-051 (Mixed Column vs mapped_column — `trial_conversions.py` is affected by both tasks; coordinate to avoid merge conflicts)
