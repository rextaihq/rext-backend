#!/usr/bin/env python3
"""
Script to retrieve details about the LemonSqueezy license product.
Product ID: 668197
"""

import asyncio
import httpx
import os
import json
from pathlib import Path

# Load .env file manually
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


async def main():
    api_key = os.getenv("LEMONSQUEEZY_API_KEY")
    product_id = "668197"

    if not api_key:
        print("Error: LEMONSQUEEZY_API_KEY not found in .env")
        return

    print("=" * 80)
    print("LemonSqueezy License Product Details")
    print("=" * 80)
    print(f"\nProduct ID: {product_id}\n")

    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
        }

        try:
            # Fetch product details
            response = await client.get(
                f"https://api.lemonsqueezy.com/v1/products/{product_id}",
                headers=headers,
                timeout=30.0,
            )

            if response.status_code != 200:
                print(f"Error: API returned {response.status_code}")
                print(response.text)
                return

            product_data = response.json()
            product = product_data.get("data", {})
            attrs = product.get("attributes", {})

            print("PRODUCT DETAILS:")
            print(f"  Name: {attrs.get('name')}")
            print(f"  Status: {attrs.get('status')}")
            print(f"  Description: {attrs.get('description', 'N/A')}")
            print(f"  Price: ${attrs.get('price', 0) / 100:.2f}")
            print(f"  Buy Now URL: {attrs.get('buy_now_url')}")
            print()

            # Fetch variants
            var_response = await client.get(
                f"https://api.lemonsqueezy.com/v1/variants?filter[product_id]={product_id}",
                headers=headers,
                timeout=30.0,
            )

            if var_response.status_code == 200:
                variants_data = var_response.json()
                variants = variants_data.get("data", [])

                print(f"VARIANTS ({len(variants)} found):")
                for variant in variants:
                    var_attrs = variant.get("attributes", {})
                    var_id = variant["id"]
                    var_name = var_attrs.get("name", "Default")
                    price = var_attrs.get("price", 0) / 100
                    is_subscription = var_attrs.get("is_subscription", False)

                    print(f"\n  Variant: {var_name}")
                    print(f"    ID: {var_id}")
                    print(f"    Price: ${price:.2f}")
                    print(f"    Type: {'Subscription' if is_subscription else 'One-time purchase'}")
                    print(f"    Status: {var_attrs.get('status')}")

                    # License-specific fields
                    print("    License Settings:")
                    print(f"      - Has license keys: {var_attrs.get('has_license_keys', False)}")
                    print(
                        f"      - License activation limit: {var_attrs.get('license_activation_limit', 'N/A')}"
                    )
                    print(
                        f"      - License length value: {var_attrs.get('license_length_value', 'N/A')}"
                    )
                    print(
                        f"      - License length unit: {var_attrs.get('license_length_unit', 'N/A')}"
                    )

            # Save to file for reference
            output_file = Path(__file__).parent.parent / "docs/testing/license_product_details.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w") as f:
                json.dump(
                    {
                        "product": product_data,
                        "variants": variants_data if var_response.status_code == 200 else None,
                    },
                    f,
                    indent=2,
                )

            print(f"\n\nFull details saved to: {output_file}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
