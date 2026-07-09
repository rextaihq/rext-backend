"""
GA4 / GSC integration API test harness.

Logs in with credentials supplied at runtime, discovers the workspace,
WordPress site and published content automatically, then calls every
Google-integration endpoint and stores each raw response as a JSON file in
scripts/api_test_results/. Each file also contains a "field_analysis"
section describing the shape and data types of the response so you can see
exactly which fields are available and what to use later.

Usage (all credentials can be passed at runtime):

    python scripts/test_ga4_gsc_apis.py
    python scripts/test_ga4_gsc_apis.py --base-url http://localhost:2024 --email you@x.com
    python scripts/test_ga4_gsc_apis.py --workspace <workspace-id-or-slug> --days 28 --refresh

If --email / --password are omitted you are prompted interactively
(password input is hidden).
"""

import argparse
import getpass
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("The 'requests' package is required:  pip install requests")
    sys.exit(1)

RESULTS_DIR = Path(__file__).parent / "api_test_results"
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def analyze_fields(value, depth=0, max_depth=6):
    """Recursively describe the type/shape of a JSON value."""
    if depth > max_depth:
        return "…(max depth)"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        # Help identify dates/uuids at a glance
        sample = value if len(value) <= 40 else value[:37] + "..."
        return f"string (e.g. \"{sample}\")"
    if isinstance(value, list):
        if not value:
            return "array (empty)"
        return {
            "__type__": f"array of {len(value)} item(s), first item:",
            "items": analyze_fields(value[0], depth + 1, max_depth),
        }
    if isinstance(value, dict):
        return {k: analyze_fields(v, depth + 1, max_depth) for k, v in value.items()}
    return type(value).__name__


class ApiTester:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.seq = 0
        self.summary = []
        RESULTS_DIR.mkdir(exist_ok=True)

    def call(self, name: str, method: str, path: str, params=None, body=None, timeout=120):
        """Call an endpoint, save the full result + field analysis to JSON."""
        self.seq += 1
        url = f"{self.base_url}{path}"
        record = {
            "name": name,
            "method": method,
            "url": url,
            "params": params,
            "request_body": body,
        }
        print(f"\n[{self.seq:02d}] {method} {path}")
        try:
            resp = self.session.request(method, url, params=params, json=body, timeout=timeout)
            record["status_code"] = resp.status_code
            try:
                payload = resp.json()
            except ValueError:
                payload = {"raw_text": resp.text[:2000]}
            record["response"] = payload
            record["ok"] = resp.ok
            data = payload.get("data") if isinstance(payload, dict) else None
            record["field_analysis"] = analyze_fields(data if data is not None else payload)
            print(f"     -> HTTP {resp.status_code} {'OK' if resp.ok else 'FAILED'}")
        except requests.RequestException as exc:
            record.update({"status_code": 0, "error": str(exc), "ok": False})
            print(f"     -> ERROR: {exc}")

        fname = RESULTS_DIR / f"{RUN_STAMP}_{self.seq:02d}_{name}.json"
        fname.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        print(f"     saved: {fname.name}")
        self.summary.append({
            "seq": self.seq,
            "name": name,
            "endpoint": f"{method} {path}",
            "status": record.get("status_code"),
            "ok": record.get("ok", False),
            "file": fname.name,
        })
        return record

    def get_data(self, record):
        """Extract the 'data' envelope from a saved record, or None."""
        if not record.get("ok"):
            return None
        resp = record.get("response")
        if isinstance(resp, dict):
            return resp.get("data", resp)
        return None


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Test GA4/GSC integration APIs")
    parser.add_argument("--base-url", default="http://localhost:2024", help="Backend base URL")
    parser.add_argument("--email", help="Login email (prompted if omitted)")
    parser.add_argument("--password", help="Login password (prompted if omitted)")
    parser.add_argument("--workspace", help="Workspace id or slug (auto-picks first if omitted)")
    parser.add_argument("--days", type=int, default=28, help="Metrics window in days")
    parser.add_argument("--refresh", action="store_true",
                        help="Force on-demand GSC/GA4 sync on the performance endpoint")
    parser.add_argument("--max-content", type=int, default=3,
                        help="How many published articles to test per-content endpoints on")
    args = parser.parse_args()

    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")

    t = ApiTester(args.base_url)
    print(f"\nResults directory: {RESULTS_DIR}")
    print(f"Run stamp: {RUN_STAMP}")

    # -- 1. Login ------------------------------------------------------------
    login = t.call("auth_login", "POST", "/api/v1/user/login",
                   body={"email": email, "password": password})
    login_data = t.get_data(login)
    if not login_data or "access_token" not in login_data:
        print("\nLogin failed — cannot continue. Is the backend running at "
              f"{args.base_url}?")
        _write_summary(t)
        sys.exit(1)
    t.session.headers["Authorization"] = f"Bearer {login_data['access_token']}"
    print(f"     logged in as: {login_data.get('user', {}).get('email', email)}")

    # -- 2. Discover workspace -------------------------------------------------
    workspace_id = args.workspace
    if not workspace_id:
        ws = t.call("workspaces_all", "GET", "/api/v1/workspaces/all")
        ws_data = t.get_data(ws) or {}
        workspaces = ws_data.get("workspaces") or ws_data.get("items") or []
        if not workspaces:
            print("\nNo workspaces found for this user — cannot continue.")
            _write_summary(t)
            sys.exit(1)
        workspace_id = workspaces[0].get("id") or workspaces[0].get("slug")
        print(f"     using workspace: {workspaces[0].get('name')} ({workspace_id})")
    wq = {"workspace_id": workspace_id}

    # -- 3. Google connection status ------------------------------------------
    status = t.call("google_status", "GET", "/api/v1/integrations/google/", params=wq)
    status_data = t.get_data(status) or {}
    if not status_data.get("connected"):
        print("\nWARNING: Google is NOT connected for this workspace — "
              "the endpoints below will likely fail.")

    # -- 4. Search Console verified sites + GA4 properties ----------------------
    t.call("gsc_sites", "GET", "/api/v1/integrations/google/search-console/sites", params=wq)
    t.call("ga4_properties", "GET", "/api/v1/integrations/google/analytics/properties", params=wq)

    # -- 5. WordPress sites + their GSC/GA4 mapping ----------------------------
    wp = t.call("wordpress_sites", "GET", "/api/v1/integrations/wordpress/", params=wq)
    wp_data = t.get_data(wp) or {}
    wp_sites = wp_data.get("sites") or wp_data.get("items") or []
    for site in wp_sites:
        site_id = site.get("id")
        if site_id:
            t.call(f"site_mapping_{site.get('site_name', site_id)[:20]}", "GET",
                   f"/api/v1/integrations/google/sites/{site_id}/mapping", params=wq)

    # -- 6. Workspace-level analytics endpoints --------------------------------
    days_q = {**wq, "days": args.days}
    t.call("dashboard", "GET", "/api/v1/integrations/google/dashboard/", params=days_q)
    t.call("content_inventory", "GET", "/api/v1/integrations/google/content-inventory/",
           params=days_q)
    t.call("opportunities", "GET", "/api/v1/integrations/google/opportunities", params=days_q)

    # -- 7. Per-content endpoints (published articles) --------------------------
    content = t.call("content_list_published", "GET", "/api/v1/content/",
                     params={**wq, "status": "published", "limit": 50})
    c_data = t.get_data(content) or {}
    items = c_data.get("items") or c_data.get("content") or c_data.get("contents") or []
    if not items:
        # fall back to any content at all
        content = t.call("content_list_all", "GET", "/api/v1/content/",
                         params={**wq, "limit": 50})
        c_data = t.get_data(content) or {}
        items = c_data.get("items") or c_data.get("content") or c_data.get("contents") or []

    if not items:
        print("\nNo content found in this workspace — skipping per-content endpoints.")
    for item in items[: args.max_content]:
        cid = item.get("id")
        title = (item.get("title") or "untitled")[:30]
        print(f"\n--- content: {title} ({cid}) ---")
        perf_params = {**wq, "days": args.days}
        if args.refresh:
            perf_params["refresh"] = "true"
        t.call("content_performance", "GET",
               f"/api/v1/integrations/google/content/{cid}/performance", params=perf_params)
        t.call("content_health_score", "GET",
               f"/api/v1/integrations/google/content/{cid}/health-score", params=wq)
        t.call("content_opportunity_score", "GET",
               f"/api/v1/integrations/google/content/{cid}/opportunity-score", params=days_q)

    _write_summary(t)


def _write_summary(t: ApiTester):
    summary_file = RESULTS_DIR / f"{RUN_STAMP}_00_summary.json"
    summary_file.write_text(json.dumps(t.summary, indent=2), encoding="utf-8")
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for row in t.summary:
        mark = "PASS" if row["ok"] else "FAIL"
        print(f"  [{mark}] {row['name']:<32} HTTP {row['status']:<4} -> {row['file']}")
    passed = sum(1 for r in t.summary if r["ok"])
    print(f"\n  {passed}/{len(t.summary)} calls succeeded")
    print(f"  Summary: {summary_file}")
    print("  Open each JSON file and look at the 'field_analysis' key to see the")
    print("  exact fields and data types each API returns.")


if __name__ == "__main__":
    main()
