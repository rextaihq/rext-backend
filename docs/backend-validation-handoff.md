# Backend Validation Handoff

This document describes the backend validation implemented for workspace, Brand Voice, and Persona APIs. Frontend validation should mirror these rules for immediate user feedback, but the backend remains authoritative.

## Workspace

- Name is required and at most 255 characters.
- Name allows ASCII letters, numbers, and single spaces only.
- Name must include at least one letter; numeric-only names are rejected.
- Names with special characters, emojis, HTML, or JavaScript-like content are rejected.
- Workspace lists default to newest first. The list API supports `sort_by=created_at` and `sort_by=name`.
- The backend no longer returns a hardcoded workspace status.

## Brand Voice

### Text fields

Applies to `brand_name`, `about`, `customer_profile`, and `selling_position`.

- Whitespace is normalized.
- Values must contain at least one letter.
- HTML, JavaScript, hidden/control characters, and emojis are rejected.
- `brand_name` is limited to 255 characters. `about`, `customer_profile`, and `selling_position` use their configured 2,000-character limits.

### List fields

Applies to `target_audience`, `brand_voice`, `content_pillar`, and `competitors`.

- Each list supports up to 50 items.
- Each item is text, normalized, and limited to 255 characters.
- Items must contain letters and cannot be only numbers or special characters.
- HTML, JavaScript, hidden/control characters, and emojis are rejected.
- Duplicates are rejected case-insensitively.

### Competitors

- Input must be a company name, not a URL or domain.
- Placeholder, keyboard-mash, repeated-character, and implausible names are rejected.
- The workspace own brand cannot be listed as a competitor.
- Brand Voice save verifies every manually entered competitor against `https://<normalized-name>.com`.
- A competitor is accepted only when the site responds with exact HTTP 200; redirects, unavailable sites, and non-200 results are rejected.
- Site checks use a five-second timeout, do not follow redirects, do not use proxy environment variables, and reject hosts resolving to non-public addresses.
- For instant validation before adding a UI chip, use:

```text
POST /api/v1/workspaces/{workspace_id}/brand-voice/competitors/validate
```

```json
{ "competitor": "Nike" }
```

- A `200` response permits adding the chip. A `422` response must be shown to the user and the chip must not be added.

## Persona

### Display name

- Required, 4 to 60 characters.
- Must include at least one letter.
- Allows letters, numbers, spaces, hyphens, straight apostrophes, and curly apostrophes only.
- Examples allowed: `Anne-Marie`, `O'Connor`, `D’Angelo`, `John 2`.
- Other symbols and emojis are rejected.

### Other Persona fields

- `full_name`, `professional_title`, `areas_of_expertise`, description, bio, demographics, tone, goals, pain points, and behaviors allow normal special characters within their existing length and list limits.
- HTML and JavaScript-like markup are rejected in all free-text and list fields.
- Examples allowed: `VP, R&D`, `C++ / AI`, `E-commerce & SaaS`, and `Dr. Alice @ Co.`.

## Frontend Contract

- Do not rely on client validation for security; submit all data to the backend.
- Before adding a competitor chip on Enter or `+`, call the competitor validation endpoint above.
- Show `422` response messages instead of a generic failure toast.
- Invalid values may be typed locally, but must never be appended or persisted after a backend `422`.
