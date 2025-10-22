#!/usr/bin/env python3
"""
Simple script to list LemonSqueezy products using direct API calls.
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
    store_id = os.getenv('LEMONSQUEEZY_STORE_ID') or os.getenv('LEMONSQUEEZY_STORE_ID')

    if not api_key:
        print("Error: LEMONSQUEEZY_API_KEY not found in .env")
        return

    if not store_id:
        print("Error: LEMONSQUEEZY_STORE_ID not found in .env")
        return

    print("=" * 80)
    print("LemonSqueezy Products and Variants")
    print("=" * 80)
    print(f"\nStore ID: {store_id}")
    print(f"API Key: {api_key[:20]}...\n")

    async with httpx.AsyncClient() as client:
        # Fetch products
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
        }

        try:
            response = await client.get(
                f"https://api.lemonsqueezy.com/v1/products?filter[store_id]={store_id}",
                headers=headers,
                timeout=30.0
            )

            if response.status_code != 200:
                print(f"Error: API returned {response.status_code}")
                print(response.text)
                return

            data = response.json()
            products = data.get('data', [])

            if not products:
                print("No products found in store")
                return

            print(f"Found {len(products)} products:\n")

            product_map = {}

            for product in products:
                attrs = product.get('attributes', {})
                product_id = product['id']
                name = attrs.get('name', 'Unnamed')

                print(f"Product: {name}")
                print(f"  ID: {product_id}")
                print(f"  Status: {attrs.get('status')}")
                print(f"  Description: {attrs.get('description', 'N/A')[:100]}")
                print()

                # Fetch variants
                var_response = await client.get(
                    f"https://api.lemonsqueezy.com/v1/variants?filter[product_id]={product_id}",
                    headers=headers,
                    timeout=30.0
                )

                if var_response.status_code == 200:
                    variants = var_response.json().get('data', [])

                    if variants:
                        print(f"  Variants:")
                        for variant in variants:
                            var_attrs = variant.get('attributes', {})
                            var_id = variant['id']
                            var_name = var_attrs.get('name', 'Default')
                            price = var_attrs.get('price', 0) / 100
                            interval = var_attrs.get('interval', 'one_time')

                            print(f"    - {var_name}")
                            print(f"      ID: {var_id}")
                            print(f"      Price: ${price:.2f}/{interval if interval != 'one_time' else 'one-time'}")

                            # Store in map
                            key = f"{name.lower().replace(' ', '_')}_{interval}"
                            product_map[key] = {
                                'product_id': product_id,
                                'variant_id': var_id,
                                'name': name,
                                'variant_name': var_name,
                                'price': price,
                                'interval': interval
                            }
                        print()

            # Print mapping table
            print("\n" + "=" * 80)
            print("SQL UPDATE STATEMENTS")
            print("=" * 80)
            print("\n-- Copy these to update your subscription_plans table:\n")

            # Group by product
            products_grouped = {}
            for key, val in product_map.items():
                prod_name = val['name']
                if prod_name not in products_grouped:
                    products_grouped[prod_name] = {}
                products_grouped[prod_name][val['interval']] = val

            for prod_name, intervals in products_grouped.items():
                monthly = intervals.get('month', {})
                yearly = intervals.get('year', {})

                if monthly or yearly:
                    # Determine plan_id based on name
                    if 'basic' in prod_name.lower():
                        plan_id = 'basic'
                    elif 'professional' in prod_name.lower() or 'pro' in prod_name.lower():
                        plan_id = 'professional'
                    elif 'enterprise' in prod_name.lower():
                        plan_id = 'enterprise'
                    else:
                        plan_id = prod_name.lower().replace(' ', '_')

                    print(f"UPDATE subscription_plans SET")
                    print(f"  lemonsqueezy_product_id = '{monthly.get('product_id') or yearly.get('product_id')}'")
                    if monthly:
                        print(f"  , lemonsqueezy_monthly_variant_id = '{monthly['variant_id']}'")
                    if yearly:
                        print(f"  , lemonsqueezy_yearly_variant_id = '{yearly['variant_id']}'")
                    print(f"WHERE plan_id = '{plan_id}';")
                    print()

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
