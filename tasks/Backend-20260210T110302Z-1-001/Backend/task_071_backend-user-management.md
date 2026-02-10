# Task 071: Deprecated `imghdr` Module with Known Bypass Vulnerabilities

## Metadata
- **Task ID:** TASK-071
- **Source:** B3 - User Management (Finding #9 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** dependency
- **Effort Estimate:** small (< 1 hour)

---

## Description

The avatar upload endpoint in `src/api/routes/users/profile.py` uses the `imghdr` standard library module (imported at line 20, used at line 232) to validate uploaded image files by inspecting their magic bytes. The `imghdr` module was deprecated in Python 3.11 via PEP 594 ("Removing dead batteries from the standard library") and was completely removed in Python 3.13. The project currently constrains Python to `>=3.11,<3.12` (in `pyproject.toml` line 10), so the module still works, but it will break immediately upon any Python version upgrade to 3.13+.

Beyond deprecation, `imghdr` has known bypass vulnerabilities documented in CPython issue tracker (bugs.python.org #26337). Because `imghdr.what()` only checks a minimal number of bytes at the file header, an attacker can craft a malicious file by prepending valid image magic bytes (e.g., the PNG header `\x89PNG\r\n\x1a\n`) to a payload containing arbitrary content such as embedded scripts. The `imghdr.what()` function will report it as a valid image despite the malicious payload. This issue was closed as "won't fix" because the module was already slated for removal.

The project already has the `filetype` package (version `>=1.2.0`) and `Pillow` (version `>=11.3.0`) declared in `pyproject.toml`. The `filetype` package provides a direct drop-in replacement via `filetype.guess_mime()` that checks up to 261 header bytes (significantly more thorough than `imghdr`) and returns MIME type strings. For defense-in-depth, Pillow's `Image.verify()` can structurally validate that the file is actually a parseable image, not just a file with prepended magic bytes.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/profile.py
# Line 20 (import):
import imghdr
```

```python
# File: rext-backend/src/api/routes/users/profile.py
# Lines 231-247 (usage):
        # Validate actual file content using magic bytes (not just Content-Type header)
        image_type = imghdr.what(None, file_content)
        allowed_image_types = ['jpeg', 'png', 'gif', 'webp']

        if image_type not in allowed_image_types:
            logger.warning(
                f"Invalid image file uploaded by user {user_id}. " +
                f"Content-Type: {file.content_type}, Actual type: {image_type}",
                extra={"user_id": str(user_id)}
            )
            return error(
                message="Invalid image file. File content does not match an allowed image format (JPEG, PNG, GIF, WebP).",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
```

---

## Why This Matters (Context & Reasoning)

Avatar upload is a user-facing feature where arbitrary files are submitted to the server. Proper file type validation is a critical security control that prevents:

1. **Stored XSS attacks** — malicious files disguised as images that, when served, execute scripts in the browser.
2. **Server-side exploits** — crafted files that exploit image processing libraries (e.g., ImageTragick-style vulnerabilities).
3. **Storage abuse** — non-image files consuming storage quota.

Using a deprecated, known-vulnerable validation module undermines this security control. The `imghdr` module's minimal header checking means a file like `malicious.png` with valid PNG bytes prepended but PHP/JavaScript in the body would pass validation.

The `filetype` package, already a project dependency, provides significantly better detection by examining up to 261 bytes of the file header and matching against comprehensive magic byte signatures for 19 image formats. Combined with Pillow's `Image.verify()` (which actually attempts to parse the image structure without fully decoding pixel data), this creates a robust two-layer validation approach.

---

## Impact

- **Severity:** Image type validation can be bypassed with crafted files. Application will break completely on Python 3.13 upgrade (ModuleNotFoundError). DeprecationWarning emitted on every avatar upload under Python 3.11.
- **Affected Users/Flows:** Any user uploading a profile avatar via the `POST /profile/avatar` endpoint.
- **Blast Radius:** Isolated to the avatar upload endpoint. No other file in the codebase uses `imghdr`.

---

## Recommended Solution

### Step 1: Replace the `imghdr` import with `filetype` and `PIL`

```python
# File: rext-backend/src/api/routes/users/profile.py
# Remove line 20:
# OLD: import imghdr

# Add these imports (near the top of the file, with other imports):
import filetype
from PIL import Image
import io
```

### Step 2: Replace the `imghdr.what()` validation block

```python
# File: rext-backend/src/api/routes/users/profile.py
# Replace lines 231-247 with:

        # Validate actual file content using magic bytes (not just Content-Type header)
        ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

        detected_mime = filetype.guess_mime(file_content)

        if detected_mime is None or detected_mime not in ALLOWED_MIME_TYPES:
            logger.warning(
                f"Invalid image file uploaded by user {user_id}. "
                f"Content-Type: {file.content_type}, Detected MIME: {detected_mime}",
                extra={"user_id": str(user_id)}
            )
            return error(
                message="Invalid image file. File content does not match an allowed image format (JPEG, PNG, GIF, WebP).",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Structural validation: verify the file is a parseable image, not just valid magic bytes
        try:
            img = Image.open(io.BytesIO(file_content))
            img.verify()
        except Exception:
            logger.warning(
                f"Corrupted or malformed image uploaded by user {user_id}. "
                f"Content-Type: {file.content_type}, Detected MIME: {detected_mime}",
                extra={"user_id": str(user_id)}
            )
            return error(
                message="Image file appears to be corrupted or malformed.",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )
```

### Notes on the changes:

1. **`filetype.guess_mime(file_content)`** accepts `bytes` directly (same as `imghdr.what(None, data)`) but returns a MIME type string like `"image/jpeg"` instead of a bare type name like `"jpeg"`. The allowed types list is updated accordingly.
2. **`Image.verify()`** adds a second validation layer that actually parses the image structure. This catches the bypass attack where valid magic bytes are prepended to a non-image payload. `verify()` is lightweight — it validates structure without decoding pixel data.
3. No new dependencies are required. Both `filetype>=1.2.0` and `pillow>=11.3.0` are already in `pyproject.toml`.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| None | — | `imghdr` is only imported and used in `profile.py`. No other files in the codebase use this module. |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Run `python -c "import imghdr"` — observe the `DeprecationWarning` under Python 3.11.
2. Upload a valid JPEG avatar via `POST /profile/avatar` — should succeed.
3. Create a crafted file: prepend valid PNG magic bytes (`\x89PNG\r\n\x1a\n`) to a text file containing `<script>alert('xss')</script>`. Upload it as an avatar — observe that `imghdr.what()` reports it as `"png"` and the upload succeeds.

### After Fix (Verify the Solution):
1. Upload a valid JPEG avatar — should succeed (200 response with avatar URL).
2. Upload a valid PNG avatar — should succeed.
3. Upload a valid GIF avatar — should succeed.
4. Upload a valid WebP avatar — should succeed.
5. Upload a `.txt` file renamed to `.png` — should be rejected ("Invalid image file").
6. Upload the crafted PNG-header + malicious payload file — should be rejected by the `Image.verify()` check ("Image file appears to be corrupted or malformed").
7. Upload an SVG file — should still be blocked by the existing SVG check on line 250.
8. Verify no `DeprecationWarning` for `imghdr` appears in server logs.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "avatar or profile or upload" -v
```

---

## Acceptance Criteria

- [ ] `import imghdr` is removed from `profile.py`
- [ ] `filetype.guess_mime()` is used for magic byte detection
- [ ] `Image.verify()` is used as a secondary structural validation
- [ ] Allowed types are checked against MIME strings (`image/jpeg`, `image/png`, `image/gif`, `image/webp`)
- [ ] Valid images (JPEG, PNG, GIF, WebP) are accepted
- [ ] Invalid files and crafted bypass files are rejected
- [ ] No `DeprecationWarning` for `imghdr` in server output
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [PEP 594 — Removing dead batteries from the standard library](https://peps.python.org/pep-0594/) — lists `imghdr` as deprecated and recommends `filetype` or `python-magic` as replacements
- **Security Advisory:** [CPython bugs.python.org #26337](https://bugs.python.org/issue26337) — demonstrates `imghdr` bypass vulnerability with crafted files; closed as "won't fix"
- **Migration Guide:** [Python 3.13 What's New — Removed Modules](https://docs.python.org/3.13/whatsnew/3.13.html) — confirms `imghdr` removal in Python 3.13
- **Best Practice Reference:** [filetype.py GitHub — h2non/filetype.py](https://github.com/h2non/filetype.py) — documentation for the replacement package, supports up to 261 header bytes
- **Related Issues/PRs:** [Pillow Image.verify() documentation](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.verify) — structural validation without full pixel decode

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-004 (deprecated `datetime.utcnow()` — same category of deprecated stdlib usage)
