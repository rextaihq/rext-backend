# Task 025: Refactor global default_permissions to Class Constant

## Metadata
- **Task ID:** TASK-025
- **Source:** B1 - Authentication & Authorization (Finding #23 under P3 Low)
- **Audit Report:** `audit-reports/backend-authentication.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `auth_service.py` file defines `default_permissions` as a module-level list (lines 61-66) and accesses it using the `global` keyword inside class methods (lines 216, 749). This is a Python anti-pattern that reduces code maintainability and violates object-oriented design principles.

Current implementation:

```python
# Module level (line 61-66)
default_permissions = [
    "user.update",
    "user.read",
    "workspace.create",
    "subscription.read"
]

# Inside method (line 216)
global default_permissions
```

The `global` statement is problematic because:

1. **Hidden dependencies:** Methods using `global` have implicit dependencies on module-level state that aren't visible in their signatures.
2. **Testing difficulty:** Mocking or overriding the value requires patching module-level state rather than using dependency injection.
3. **Accidental mutation:** Lists are mutable; any code could modify `default_permissions` and affect all subsequent calls.
4. **Violation of encapsulation:** The permissions are logically part of the `AuthService` class but are defined outside it.
5. **Code clarity:** Developers must search for where `default_permissions` is defined rather than looking at the class definition.

According to Python best practices, the `global` keyword should be avoided. Using module-level constants (ALL_CAPS naming) or class constants is preferred for shared configuration values.

---

## Current Code

```python
# File: rext-backend/src/services/auth_service.py
# Lines: 61-66 - Module-level definition
default_permissions = [
            "user.update",
            "user.read",
            "workspace.create",
            "subscription.read"
        ]
class AuthService:
    """Service for authentication business logic"""
    # ...
```

```python
# File: rext-backend/src/services/auth_service.py
# Line 216 - Usage inside login_user method
async def login_user(
    self,
    email: str,
    password: str,
    device_info: Dict[str, str],
    background_tasks: Optional[BackgroundTasks] = None,
    db: Optional[AsyncSession] = None,
) -> Tuple[Users, Dict[str, Any]]:
    # ...
    global  default_permissions  # <-- Anti-pattern: global keyword
    result = await self.db.execute(
        select(Users)
        # ...
    )
```

```python
# File: rext-backend/src/services/auth_service.py
# Line 749 - Usage inside _assign_default_permissions_to_role method
async def _assign_default_permissions_to_role(self, role: Role) -> None:
    """
    Assign default permissions to a role, avoiding duplicates.
    """
    global default_permissions  # <-- Anti-pattern: global keyword

    # Get existing permissions for the role
    existing_perms_result = await self.db.execute(
        # ...
    )
```

---

## Why This Matters (Context & Reasoning)

The `global` keyword is widely considered an anti-pattern in Python for several reasons documented by authoritative sources:

1. **Python Anti-Patterns Documentation:** "Global variables are dangerous because they can be simultaneously accessed from multiple sections of a program, which frequently results in bugs."

2. **Real Python:** "Even though defining global variables within your functions using either the global keyword or the globals() function is perfectly possible in Python, it's not a best practice."

3. **Baeldung:** "Global variables also make code difficult to read, because they force you to search through multiple functions or even modules just to understand all the different locations where the global variable is used and modified."

The recommended alternatives are:
- **Class constants** for values logically associated with a class
- **Module-level constants** (ALL_CAPS naming) for true constants
- **Configuration objects** for values that might change between environments

In this case, `default_permissions` is logically part of the `AuthService` class's responsibility, so a class constant is the most appropriate solution.

---

## Impact

- **Severity:** Low. The code works correctly; this is purely a maintainability issue.
- **Affected Users/Flows:** None directly. This is an internal refactoring.
- **Blast Radius:** Limited to `AuthService` class and its methods.

---

## Recommended Solution

Refactor `default_permissions` to a class constant within `AuthService`, following Python naming conventions (ALL_CAPS for constants) and using a tuple instead of a list to prevent accidental mutation.

### Step 1: Remove Module-Level Definition

```python
# File: rext-backend/src/services/auth_service.py
# Delete lines 61-66:
# default_permissions = [
#             "user.update",
#             "user.read",
#             "workspace.create",
#             "subscription.read"
#         ]
```

### Step 2: Add Class Constant to AuthService

```python
# File: rext-backend/src/services/auth_service.py
# Add inside AuthService class, after docstring (around line 68):

class AuthService:
    """Service for authentication business logic"""

    # Default permissions assigned to new users during registration
    # Using tuple to prevent accidental mutation
    DEFAULT_PERMISSIONS: tuple[str, ...] = (
        "user.update",
        "user.read",
        "workspace.create",
        "subscription.read",
    )

    def __init__(self, db: AsyncSession):
        # ...
```

### Step 3: Update login_user Method

```python
# File: rext-backend/src/services/auth_service.py
# Line 216 - Remove the global statement entirely:

async def login_user(
    self,
    email: str,
    password: str,
    device_info: Dict[str, str],
    background_tasks: Optional[BackgroundTasks] = None,
    db: Optional[AsyncSession] = None,
) -> Tuple[Users, Dict[str, Any]]:
    """..."""
    # Find user (eagerly load relationships to avoid lazy loading in async context)
    from sqlalchemy.orm import selectinload
    # DELETE THIS LINE: global  default_permissions
    result = await self.db.execute(
        # ...
    )
```

### Step 4: Update _assign_default_permissions_to_role Method

```python
# File: rext-backend/src/services/auth_service.py
# Lines 742-776 - Update the method:

async def _assign_default_permissions_to_role(self, role: Role) -> None:
    """
    Assign default permissions to a role, avoiding duplicates.

    Args:
        role: Role object
    """
    # DELETE THIS LINE: global default_permissions

    # Get existing permissions for the role to avoid adding duplicates
    existing_perms_result = await self.db.execute(
        select(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
    )
    existing_perms = {p_name for p_name, in existing_perms_result}

    # Use class constant instead of global variable
    permissions_to_add_names = [p for p in self.DEFAULT_PERMISSIONS if p not in existing_perms]

    if not permissions_to_add_names:
        logger.debug(f"Role '{role.name}' already has all default permissions.")
        return

    # Fetch permission objects to add
    permissions_to_add_result = await self.db.execute(
        select(Permission).where(Permission.name.in_(permissions_to_add_names))
    )
    permissions_to_add = permissions_to_add_result.scalars().all()

    for permission in permissions_to_add:
        self.db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    if permissions_to_add:
        await self.db.flush()
        logger.info(f"Assigned {len(permissions_to_add)} missing default permissions to role: {role.name}")
```

### Step 5: Search for Other Usages and Update

Check if `default_permissions` is used elsewhere in the codebase:

```bash
grep -rn "default_permissions" rext-backend/
```

Based on the audit, the only usages are in `auth_service.py`. If other files reference it, they should import from `AuthService`:

```python
from src.services.auth_service import AuthService

# Access as:
AuthService.DEFAULT_PERMISSIONS
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/services/auth_service.py` | 61-66 | Module-level definition to remove |
| `rext-backend/src/services/auth_service.py` | 216 | `global` statement to remove |
| `rext-backend/src/services/auth_service.py` | 749 | `global` statement to remove |

---

## Testing Instructions

### Before Fix (Current State):
1. Note the module-level `default_permissions` list
2. Observe `global` keyword usage in methods
3. The code works but has maintainability issues

### After Fix (Verify the Refactoring):
1. Verify class constant exists:
   ```python
   from src.services.auth_service import AuthService
   print(AuthService.DEFAULT_PERMISSIONS)
   # Expected: ('user.update', 'user.read', 'workspace.create', 'subscription.read')
   ```

2. Verify constant is immutable (tuple, not list):
   ```python
   try:
       AuthService.DEFAULT_PERMISSIONS.append("new.permission")
   except AttributeError:
       print("Correctly using tuple - cannot append")
   ```

3. Test user registration assigns default permissions:
   - Register a new user
   - Check user has the default permissions assigned

4. Verify no `global` keyword remains:
   ```bash
   grep -n "global.*default_permissions" rext-backend/src/services/auth_service.py
   # Should return no results
   ```

### Run Existing Tests:
```bash
cd rext-backend
pytest tests/ -v -k "auth or register or permission"
```

---

## Acceptance Criteria

- [ ] Module-level `default_permissions` list removed
- [ ] `DEFAULT_PERMISSIONS` class constant added to `AuthService`
- [ ] Constant uses tuple (immutable) instead of list
- [ ] Constant follows ALL_CAPS naming convention
- [ ] All `global default_permissions` statements removed
- [ ] All references updated to use `self.DEFAULT_PERMISSIONS`
- [ ] User registration still assigns default permissions correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Programming FAQ - Global Variables](https://docs.python.org/3/faq/programming.html)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python Anti-Patterns - Using the global statement](https://docs.quantifiedcode.com/python-anti-patterns/maintainability/using_the_global_statement.html)
- **Additional Reference:** [Real Python - Python Constants](https://realpython.com/python-constants/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** None
