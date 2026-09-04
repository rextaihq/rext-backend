# Account‑Creation IP Allowlist — Admin API

Frontend integration guide for the **Account‑Creation IP Allowlist** feature.

---

## 1. What this feature does

The backend permanently caps how many accounts **without an active paid
subscription** a single "device" (client IP + User‑Agent fingerprint) may
create — `MAX_NON_PAID_ACCOUNTS_PER_DEVICE = 5`. See
`check_device_account_limit` in `src/api/routes/users/auth.py`.

That cap is a problem for an organization whose staff all sign up from behind a
single corporate NAT gateway: to the backend they all look like **one device**
(same public egress IP), so the 6th internal signup is blocked with **HTTP 403**.

The allowlist fixes that: an admin registers the organization's **approved
public egress IP address(es)**. When a registration request's verified client IP
matches an **active** allowlist entry, the per‑device cap is skipped for that
request. Every other IP is unaffected — the cap still applies exactly as before.

The list is stored in the database (`account_creation_ip_allowlist` table) and
managed entirely through the admin API below — there is no environment variable
and no server restart involved.

---

## 2. How the "verified client IP" is obtained (why the allowlist is safe)

- The API runs behind **Traefik/Coolify**. Traefik terminates TLS and forwards
  the request with an `X-Forwarded-For` header.
- The app **never reads `X-Forwarded-For` directly.** Uvicorn's
  `ProxyHeadersMiddleware` (wired up in `src/api/server.py`) rewrites
  `request.client.host` from `X-Forwarded-For` **only when the immediate peer is
  a trusted proxy**, i.e. its address is in the `TRUSTED_PROXY_IPS` setting. For
  any other client the real TCP socket address is used.
- Result: an ordinary client cannot spoof an allowlisted IP by sending its own
  `X-Forwarded-For` — that header is only honoured for the trusted Traefik hop,
  and the middleware walks the forwarded chain from the right, returning the
  first *untrusted* address.

> **Infra action required (see §7):** `TRUSTED_PROXY_IPS` must list Traefik's
> address/subnet in production. Its default (`127.0.0.1,::1`) is not correct for
> the dockerised Coolify setup and must be set by the infra team, otherwise
> `request.client.host` is Traefik's container IP for everyone and the allowlist
> (and the existing per‑device cap) compare against the wrong address.

---

## 3. Auth & permissions

| | |
|---|---|
| Base URL | `/api/v1/admin/account-creation-allowlist` |
| Auth | `Authorization: Bearer <access_token>` — the **same admin session token** the UI already uses for every other `/api/v1/admin/*` call. Obtained from the normal login flow; nothing feature-specific. |
| Who can call | Any user whose account has the **`admin`** or **`super_admin`** role. Enforced by the shared `is_admin` dependency (`src/api/middleware/permissions.py`), which passes when the user holds any role with `hierarchy_level >= 80` (`admin` = 80, `super_admin` = 100). `super_admin` also bypasses all permission checks globally. |
| Unauthenticated | `401` (invalid / expired / revoked token) or `422` (no `Authorization` header at all). |
| Authenticated non-admin | `403` — `{"error": {"message": "Admin access required", "status_code": 403}}` |

**No additional secret, environment variable, API key, or backend-only
credential is required or accepted for these endpoints.** Authorization is purely
the caller's admin role on their normal session token — identical to
`/api/v1/admin/customers`, `/api/v1/admin/monitoring/*`, etc. There is also no
extra RBAC permission string to grant; role membership is the whole gate.

### Example — list entries

```bash
curl -sS https://api.example.com/api/v1/admin/account-creation-allowlist \
  -H "Authorization: Bearer $ADMIN_ACCESS_TOKEN"
```

```jsonc
// 200 OK
{
  "success": true,
  "message": "Account creation allowlist retrieved successfully",
  "data": {
    "entries": [
      {
        "id": "0e1d2c3b-4a59-6879-8a9b-0c1d2e3f4a5b",
        "ip_address": "198.51.100.24",
        "label": "HQ NAT gateway",
        "is_active": true,
        "created_by": "b7c8d9e0-1111-2222-3333-444455556666",
        "created_at": "2026-09-01T10:15:00+00:00",
        "updated_at": "2026-09-01T10:15:00+00:00"
      }
    ],
    "total_count": 1
  },
  "error": null,
  "meta": { "request_id": "req_…", "timestamp": "…", "version": "1.0" }
}
```

### Example — non-admin caller

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://api.example.com/api/v1/admin/account-creation-allowlist \
  -H "Authorization: Bearer $REGULAR_USER_TOKEN"
# => 403
```

---

## 4. Response envelope

Every endpoint returns the standard wrapper:

```jsonc
{
  "success": true,
  "message": "Account creation allowlist retrieved successfully",
  "data": { /* endpoint-specific, see below */ },
  "error": null,
  "meta": { "request_id": "…", "timestamp": "…", "processing_time_ms": 12, "version": "1.0" }
}
```

Errors:

```jsonc
{
  "success": false,
  "data": null,
  "error": {
    "code": "validation_failed",
    "message": "IP address is not a valid public egress address",
    "severity": "medium",
    "status_code": 422,
    "details": [
      { "field": "ip_address", "message": "192.168.1.10 falls in the non-routable range 192.168.0.0/16 - the allowlist must hold the organization's public egress IP(s), not private / loopback / link-local addresses", "code": "field_validation_error" }
    ]
  },
  "meta": { "…": "…" }
}
```

---

## 5. Endpoints

### 5.1 List entries

```
GET /api/v1/admin/account-creation-allowlist
```

Returns **all** entries (active and inactive), newest first.

**200** `data`:

```jsonc
{
  "entries": [
    {
      "id": "0e1d2c3b-4a59-6879-8a9b-0c1d2e3f4a5b",
      "ip_address": "198.51.100.24",
      "label": "HQ NAT gateway",
      "is_active": true,
      "created_by": "b7c8d9e0-1111-2222-3333-444455556666",  // admin user id, may be null
      "created_at": "2026-09-01T10:15:00+00:00",
      "updated_at": "2026-09-01T10:15:00+00:00"
    },
    {
      "id": "…",
      "ip_address": "203.0.113.0/24",
      "label": null,
      "is_active": false,
      "created_by": null,
      "created_at": "2026-08-20T09:00:00+00:00",
      "updated_at": "2026-08-25T14:30:00+00:00"
    }
  ],
  "total_count": 2
}
```

### 5.2 Add an entry

```
POST /api/v1/admin/account-creation-allowlist
Content-Type: application/json
```

Body:

| field | type | required | notes |
|---|---|---|---|
| `ip_address` | string | ✅ | A single IPv4/IPv6 address **or** a CIDR range. Stored **normalized** (IPv6 compressed/lower‑cased, CIDR host bits zeroed — `203.0.113.5/24` → `203.0.113.0/24`). Must be a **public** address — private (`10/8`, `172.16/12`, `192.168/16`), loopback, link‑local, ULA, multicast and unspecified ranges are rejected with `422`. |
| `label` | string \| null | ❌ | Free text, ≤ 255 chars. e.g. `"London office egress"`. |
| `is_active` | boolean | ❌ | Defaults to `true`. Send `false` to stage an entry without it taking effect yet. |

Example:

```json
{ "ip_address": "198.51.100.24", "label": "HQ NAT gateway", "is_active": true }
```

**201** `data`: the created entry object (same shape as a list item).

Errors:

| status | when |
|---|---|
| `422` | `ip_address` missing, malformed, or a non‑public/reserved range |
| `409` | the normalized address is already in the list (`error.code = "duplicate_resource"`) |
| `403` | caller is not an admin |

### 5.3 Update an entry

```
PATCH /api/v1/admin/account-creation-allowlist/{entry_id}
Content-Type: application/json
```

Only `label` and `is_active` are editable. The `ip_address` is immutable —
delete and re‑add to change it. Send only the fields you want to change.

| field | type | notes |
|---|---|---|
| `label` | string \| null | `null` clears the label |
| `is_active` | boolean | toggling to `false` immediately stops that entry from bypassing the cap |

Example — disable an entry without deleting it:

```json
{ "is_active": false }
```

**200** `data`: the updated entry object.

Errors: `404` if `entry_id` doesn't exist, `403` if not admin, `422` for a bad body.

### 5.4 Delete an entry

```
DELETE /api/v1/admin/account-creation-allowlist/{entry_id}
```

Permanently removes the entry.

**200** `data`:

```json
{ "id": "0e1d2c3b-4a59-6879-8a9b-0c1d2e3f4a5b", "deleted": true }
```

Errors: `404` if `entry_id` doesn't exist, `403` if not admin.

---

## 6. Suggested UI

Placement is the frontend team's call. A reasonable home is a **new admin page**
(e.g. `/admin/security`) or a **card on an existing admin settings/monitoring
page**, gated with the existing `AdminGuard` (role `admin` / `super_admin`).

Minimum viable surface:

1. A table of entries — columns: IP / CIDR, Label, Status (Active/Inactive
   toggle → `PATCH`), Added (date + admin), Actions (Delete → `DELETE` with a
   confirm dialog).
2. An "Add IP" form — `ip_address` (required) + `label` (optional). Surface the
   `422` `error.details[0].message` inline on the field (it explains *why* an IP
   was rejected, e.g. "that's a private address"). Surface `409` as "already in
   the list".
3. Helper text near the form:
   > Enter your organization's **public internet‑facing (egress) IP** — the
   > address this app sees when your staff connect, not an internal
   > `192.168.x` / `10.x` address. Ask your network/infra team if unsure. You
   > can add more than one, and CIDR ranges (e.g. `198.51.100.0/28`) are allowed.

There is **no bulk endpoint** — add IPs one at a time.

Cache note: the backend caches the active set for up to **5 minutes** (Redis).
A create/update/delete invalidates that cache immediately, so the UI doesn't
need to do anything special, but a brand‑new entry can take effect on the very
next signup rather than being instant under rare cache races.

---

## 7. Deployment — what to do per environment (stage, then main)

Nothing here happens automatically. CI builds the image and triggers the Coolify
deploy; it does **not** run migrations, and the app does **not** migrate on
startup.

### 7.1 Run the database migration — REQUIRED

Migration `20260901ipallow` creates `account_creation_ip_allowlist` **and merges
the two current Alembic heads** (`20260828digest` + `a1p2e3r4s5o6`) into one — so
until it lands, plain `alembic upgrade head` errors with "Multiple head
revisions". Run it right after the deploy finishes, before anyone opens the admin
screen:

```bash
# exec into the running rext-api container (or a Coolify one-off command)
alembic upgrade head          # or: python migrate.py upgrade
```

In the container `POSTGRES_URI_CUSTOM` points at PgBouncer (transaction pooling).
This migration is plain `CREATE TABLE` + `CREATE INDEX`, which is safe through
PgBouncer, but if your convention is to migrate against Postgres directly, the
container already has the direct URL in `DATABASE_URI`:

```bash
POSTGRES_URI_CUSTOM="$DATABASE_URI" alembic upgrade head
```

If you skip this: the 4 new admin endpoints return 500 (missing table). Nothing
else breaks — the signup cap keeps working and `is_ip_allowlisted` fails closed.

### 7.2 Set `TRUSTED_PROXY_IPS` — REQUIRED, per environment

| | |
|---|---|
| Where | Coolify → rext-backend (stage / prod) → **Environment Variables**. `docker-compose.yml` now wires it through (`TRUSTED_PROXY_IPS: ${TRUSTED_PROXY_IPS:-127.0.0.1,::1}`). |
| Value | The Docker subnet of the **`coolify`** network (Traefik reaches this container over it — `traefik.docker.network=coolify`). Find it: `docker network inspect coolify \| grep Subnet` — typically something like `10.0.0.0/8` or a `/16`. |
| Why | Traefik's peer IP on that bridge is private (never loopback). With the default `127.0.0.1,::1`, `ProxyHeadersMiddleware` won't trust Traefik's `X-Forwarded-For`, so `request.client.host` becomes **Traefik's IP for every request** — breaking the allowlist, the per-device signup cap, rate-limit keys, and audit-log IPs. |
| Alternative | `*` (trust any `X-Forwarded-For`) is acceptable only because the app is never exposed except through Traefik; pin the subnet if it's stable. |

Redeploy (or next deploy) after setting it. Verify: after deploy, an authed
request's audit log / rate-limit logs should show real client IPs, not one
constant private address.

### 7.3 Nothing else

- **No env var for the allowlist itself** — it's DB-only. Starts empty (safe: cap
  applies to everyone); admins add IPs via the UI.
- **Redis** — reuses the existing `rext-cache-redis`. If it's down the service
  falls back to a direct DB read; no config.
- **The allowlisted egress IP(s)** — added by an admin through the API once the
  org's public egress IP is known. **None are shipped in code or seeded.**

### 7.4 Rollback

Migration has a clean `downgrade()`. If you roll the image back, `alembic
downgrade -1` too — or just leave the empty table (old code never queries it).

---

## 8. Backend reference (for reviewers)

| concern | location |
|---|---|
| Model / table | `src/api/models/admin_models/account_creation_ip_allowlist.py` |
| Migration | `alembic/versions/20260901ipallow_add_account_creation_ip_allowlist.py` |
| Service (CRUD + `is_ip_allowlisted`, Redis cache) | `src/services/account_creation_allowlist_service.py` |
| Pure IP matching / validation helpers | `src/utils/ip_allowlist.py` |
| Admin routes | `src/api/routes/admin/account_creation_allowlist_routes.py` |
| Request/response schemas | `src/api/schema/account_creation_allowlist_schema.py` |
| Route registration | `src/api/registry/routes.py` — `admin_account_creation_allowlist_router` under `/api/v1/admin` |
| Auth dependency | `is_admin` from `src/api/middleware/permissions.py` (used as `Depends(is_admin)` on all four routes) |
| Integration point (the bypass) | `check_device_account_limit` in `src/api/routes/users/auth.py` |
| Proxy / client‑IP handling | `ProxyHeadersMiddleware` in `src/api/server.py`, `TRUSTED_PROXY_IPS` in `src/api/config.py` |
| Tests | `tests/routes/admin/test_account_creation_allowlist_routes.py` (HTTP auth: admin/super_admin CRUD, non-admin 403, unauthenticated 401), `tests/unit/services/test_account_creation_allowlist_service.py`, `tests/utils/test_ip_allowlist.py` |
