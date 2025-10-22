#!/usr/bin/env python3
"""
Create a checkout session for the license product.
This will generate a URL for testing the fixed webhook handler.
"""

import asyncio
import httpx
import os
from pathlib import Path

# Load .env file manually
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


async def main():
    api_key = os.getenv('LEMONSQUEEZY_API_KEY')
    store_id = os.getenv('LEMONSQUEEZY_STORE_ID')

    # Test user ID
    user_id = "54048b28-3012-487c-8479-1ca7ab5453c6"

    if not api_key or not store_id:
        print("Error: Missing LEMONSQUEEZY_API_KEY or LEMONSQUEEZY_STORE_ID")
        return

    print("=" * 80)
    print("Creating Checkout Session for License Product")
    print("=" * 80)
    print(f"\nProduct ID: 668197")
    print(f"Variant ID: 1049956")
    print(f"User ID: {user_id}\n")

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }

        checkout_data = {
            "data": {
                "type": "checkouts",
                "attributes": {
                    "custom_price": None,
                    "product_options": {
                        "enabled_variants": [1049956],
                        "redirect_url": f"http://localhost:3000/checkout/success",
                        "receipt_button_text": "Go to Dashboard",
                        "receipt_link_url": f"http://localhost:3000/",
                    },
                    "checkout_options": {
                        "embed": False,
                        "media": True,
                        "logo": True,
                        "desc": True,
                        "discount": True,
                        "dark": False,
                        "subscription_preview": True,
                        "button_color": "#2563eb"
                    },
                    "checkout_data": {
                        "email": "mobeen@revnix.com",
                        "name": "Test User",
                        "custom": {
                            "user_id": user_id
                        }
                    },
                    "preview": False,
                },
                "relationships": {
                    "store": {
                        "data": {
                            "type": "stores",
                            "id": store_id
                        }
                    },
                    "variant": {
                        "data": {
                            "type": "variants",
                            "id": "1049956"
                        }
                    }
                }
            }
        }

        try:
            response = await client.post(
                "https://api.lemonsqueezy.com/v1/checkouts",
                headers=headers,
                json=checkout_data,
                timeout=30.0
            )

            if response.status_code == 201:
                data = response.json()
                checkout_attrs = data['data']['attributes']
                checkout_url = checkout_attrs['url']

                print("✅ Checkout URL created successfully!")
                print()
                print("=" * 80)
                print("CHECKOUT URL:")
                print("=" * 80)
                print(checkout_url)
                print()
                print("=" * 80)
                print("TEST CARD DETAILS:")
                print("=" * 80)
                print("Card Number: 4242 4242 4242 4242")
                print("Expiry: Any future date (e.g., 12/25)")
                print("CVC: Any 3 digits (e.g., 123)")
                print("=" * 80)
                print()
                print("After completing the purchase:")
                print("1. Wait a few seconds for the webhook to process")
                print("2. Run: .venv/bin/python scripts/check_licenses.py")
                print("3. Run: .venv/bin/python scripts/test_license_management.py")
                print()

            else:
                print(f"❌ Failed to create checkout: {response.status_code}")
                print(response.text)

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
