#!/usr/bin/env python3
"""
Script to list all products and variants from LemonSqueezy store.

This script retrieves and displays all products from your LemonSqueezy store,
including variants, pricing, and product IDs for documentation purposes.

Usage:
    python scripts/list_lemonsqueezy_products.py
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider
from src.config import settings
import structlog

logger = structlog.get_logger()


async def list_products():
    """List all products and variants from LemonSqueezy store."""

    print("=" * 80)
    print("LemonSqueezy Products and Variants")
    print("=" * 80)
    print()

    # Get credentials from settings
    api_key = settings.LEMONSQUEEZY_API_KEY
    store_id = settings.LEMONSQUEEZY_STORE_ID
    webhook_secret = settings.LEMONSQUEEZY_WEBHOOK_SECRET
    sandbox_mode = settings.LEMONSQUEEZY_SANDBOX_MODE

    if not api_key:
        print("✗ LEMONSQUEEZY_API_KEY not found in environment")
        print("  Please set it in your .env file")
        return

    if not store_id:
        print("✗ LEMONSQUEEZY_STORE_ID not found in environment")
        print("  Please set it in your .env file")
        return

    # Initialize provider
    try:
        provider = LemonSqueezyProvider(
            api_key=api_key,
            store_id=store_id,
            webhook_secret=webhook_secret,
            sandbox_mode=sandbox_mode,
        )
        print(f"✓ Connected to LemonSqueezy Store ID: {provider.store_id}")
        print(f"✓ Sandbox Mode: {sandbox_mode}")
        print(f"✓ Using API Key: {provider.api_key[:20]}...")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize LemonSqueezy provider: {e}")
        return

    # Get all products
    try:
        print("Fetching products from LemonSqueezy API...")
        print()

        response = await provider._make_request(
            "GET", f"/v1/products?filter[store_id]={provider.store_id}"
        )

        if not response or "data" not in response:
            print("✗ No products found or invalid response")
            return

        products = response["data"]

        if not products:
            print("⚠ No products found in your LemonSqueezy store")
            print()
            print("Next steps:")
            print("1. Login to https://app.lemonsqueezy.com/")
            print("2. Enable Test Mode (toggle in top right)")
            print("3. Create products for Basic, Professional, and Enterprise plans")
            print("4. Run this script again to get product IDs")
            return

        print(f"Found {len(products)} product(s):")
        print()

        # Display products with details
        for idx, product in enumerate(products, 1):
            attrs = product.get("attributes", {})
            product_id = product.get("id")

            print(f"{idx}. {attrs.get('name', 'Unnamed Product')}")
            print(f"   Product ID: {product_id}")
            print(f"   Status: {attrs.get('status', 'unknown')}")
            print(f"   Description: {attrs.get('description', 'No description')[:100]}")
            print(f"   Store ID: {attrs.get('store_id')}")
            print()

            # Get variants for this product
            try:
                variants_response = await provider._make_request(
                    "GET", f"/v1/variants?filter[product_id]={product_id}"
                )

                if variants_response and "data" in variants_response:
                    variants = variants_response["data"]

                    if variants:
                        print(f"   Variants ({len(variants)}):")
                        for var in variants:
                            var_attrs = var.get("attributes", {})
                            var_id = var.get("id")

                            # Format price
                            price = var_attrs.get("price", 0)
                            interval = var_attrs.get("interval", "one_time")
                            interval_count = var_attrs.get("interval_count", 1)

                            price_str = f"${price / 100:.2f}"
                            if interval != "one_time":
                                if interval_count > 1:
                                    price_str += f" every {interval_count} {interval}s"
                                else:
                                    price_str += f"/{interval}"

                            print(f"     - {var_attrs.get('name', 'Unnamed Variant')}")
                            print(f"       Variant ID: {var_id}")
                            print(f"       Price: {price_str}")
                            print(f"       Status: {var_attrs.get('status', 'unknown')}")

                            # Trial info
                            has_trial = var_attrs.get("has_free_trial", False)
                            if has_trial:
                                trial_interval = var_attrs.get("trial_interval", "day")
                                trial_length = var_attrs.get("trial_interval_count", 0)
                                print(f"       Trial: {trial_length} {trial_interval}s")

                            print()
                    else:
                        print("   No variants found")
                        print()

            except Exception as e:
                print(f"   ✗ Failed to fetch variants: {e}")
                print()

        print()
        print("=" * 80)
        print("Product ID Mapping Table")
        print("=" * 80)
        print()
        print("Use these IDs to update your subscription_plans table:")
        print()
        print("| Plan Name | Interval | Product ID | Variant ID | Price |")
        print("|-----------|----------|------------|------------|-------|")

        for product in products:
            attrs = product.get("attributes", {})
            product_id = product.get("id")
            product_name = attrs.get("name", "Unknown")

            try:
                variants_response = await provider._make_request(
                    "GET", f"/v1/variants?filter[product_id]={product_id}"
                )

                if variants_response and "data" in variants_response:
                    for var in variants_response["data"]:
                        var_attrs = var.get("attributes", {})
                        var_id = var.get("id")
                        var_name = var_attrs.get("name", "Default")
                        price = var_attrs.get("price", 0)
                        interval = var_attrs.get("interval", "one_time")

                        price_str = f"${price / 100:.2f}"
                        if interval != "one_time":
                            price_str += f"/{interval}"

                        print(
                            f"| {product_name} | {var_name} | {product_id} | {var_id} | {price_str} |"
                        )
            except Exception:
                print(f"| {product_name} | - | {product_id} | - | - |")

        print()
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Copy the Product IDs and Variant IDs from above")
        print("2. Update the subscription_plans table with these IDs")
        print("3. Run the database update script")
        print()

    except Exception as e:
        print(f"✗ Failed to fetch products: {e}")
        logger.exception("Error fetching products from LemonSqueezy")


if __name__ == "__main__":
    asyncio.run(list_products())
