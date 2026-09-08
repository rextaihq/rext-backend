#!/usr/bin/env python
"""Point the local-development LemonSqueezy webhook at your current tunnel.

Free tunnel URLs (ngrok, cloudflared) change every time the agent restarts, so
the webhook registered in LemonSqueezy goes stale constantly. When it does,
LemonSqueezy delivers to a dead host, no webhook_events rows are written, and
purchases succeed in LemonSqueezy while the local database learns nothing.

Usage:
    ngrok http 2024        # copy the https URL it prints
    .venv/bin/python scripts/point_lemonsqueezy_webhook.py https://<id>.ngrok-free.app

    # see what is registered without changing anything
    .venv/bin/python scripts/point_lemonsqueezy_webhook.py --list

Deployed environments are protected: this refuses to modify a webhook whose URL
looks like a real host (see PROTECTED_HOSTS).
"""

import argparse
import asyncio
import sys
from urllib.parse import urlparse

import httpx

from src.config.payment_config import payment_settings

API = "https://api.lemonsqueezy.com/v1"
WEBHOOK_PATH = "/api/v1/subscriptions/webhooks/lemonsqueezy"

# Never repoint a webhook belonging to a deployed environment.
PROTECTED_HOSTS = ("rext.ai", "staging", "prod")

# Everything the backend has handlers for, so a local run behaves like production.
EVENTS = [
    "order_created",
    "order_refunded",
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_paused",
    "subscription_unpaused",
    "subscription_expired",
    "subscription_payment_success",
    "subscription_payment_failed",
    "subscription_payment_recovered",
    "subscription_payment_refunded",
    "subscription_plan_changed",
    "license_key_created",
]


def _headers() -> dict:
    if not payment_settings.lemonsqueezy_api_key:
        sys.exit("LEMONSQUEEZY_API_KEY is not set in .env")
    return {
        "Authorization": f"Bearer {payment_settings.lemonsqueezy_api_key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


def _is_protected(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(marker in host for marker in PROTECTED_HOSTS)


async def list_webhooks(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(f"{API}/webhooks", headers=_headers())

    if response.status_code == 401:
        sys.exit(
            "LemonSqueezy rejected the API key (401). It has most likely been "
            "revoked or rotated in the dashboard."
        )
    response.raise_for_status()

    return response.json().get("data", [])


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tunnel_url",
        nargs="?",
        help="Public base URL of your tunnel, e.g. https://abc123.ngrok-free.app",
    )
    parser.add_argument(
        "--list", action="store_true", help="Show registered webhooks and exit"
    )
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=30) as client:
        webhooks = await list_webhooks(client)

        if args.list or not args.tunnel_url:
            print(f"{len(webhooks)} webhook(s) registered:\n")
            for webhook in webhooks:
                url = webhook["attributes"].get("url", "")
                tag = "PROTECTED" if _is_protected(url) else "local dev"
                print(f"  [{tag}] id={webhook['id']}")
                print(f"      {url}")
            if not args.tunnel_url:
                print("\nPass a tunnel URL to repoint the local-dev webhook.")
            return

        base = args.tunnel_url.rstrip("/")
        if not base.startswith("https://"):
            sys.exit("Tunnel URL must start with https:// — LemonSqueezy requires TLS.")

        target = f"{base}{WEBHOOK_PATH}"

        editable = [w for w in webhooks if not _is_protected(w["attributes"].get("url", ""))]

        if not editable:
            sys.exit(
                "No local-dev webhook found to update. Every registered webhook "
                "points at a protected host; create one in the dashboard first."
            )
        if len(editable) > 1:
            print("Refusing to guess — more than one local-dev webhook exists:")
            for webhook in editable:
                print(f"  id={webhook['id']}  {webhook['attributes'].get('url')}")
            sys.exit("Remove the extras in the dashboard, then re-run.")

        webhook = editable[0]
        print(f"Updating webhook {webhook['id']}")
        print(f"  from: {webhook['attributes'].get('url')}")
        print(f"    to: {target}")

        # The signing secret must match .env or every delivery fails signature
        # verification with a 401 that is easy to misread as a routing problem.
        response = await client.patch(
            f"{API}/webhooks/{webhook['id']}",
            headers=_headers(),
            json={
                "data": {
                    "type": "webhooks",
                    "id": str(webhook["id"]),
                    "attributes": {
                        "url": target,
                        "events": EVENTS,
                        "secret": payment_settings.lemonsqueezy_webhook_secret,
                    },
                }
            },
        )

        if response.status_code >= 400:
            sys.exit(f"Update failed ({response.status_code}): {response.text[:400]}")

        confirmed = response.json()["data"]["attributes"].get("url")
        print(f"\nDone. LemonSqueezy now delivers to:\n  {confirmed}")
        print("\nMake a test purchase, then verify with:")
        print("  SELECT event_name, processed FROM webhook_events ORDER BY created_at DESC LIMIT 5;")


if __name__ == "__main__":
    asyncio.run(main())
