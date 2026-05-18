import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        payload = {
            "store_url": "monitod.myshopify.com",
            "access_token": "dumy api access token",
            "is_active": True,
            "integration_type": "shopify"
        }
        resp = await client.post("http://localhost:2024/api/v1/shopify/connect", json=payload, headers={"Content-Type": "application/json"})
        print(f"Status /shopify/connect: {resp.status_code}")
        print(resp.text)
        
        resp2 = await client.post("http://localhost:2024/api/v1/content/sites/connect", json=payload, headers={"Content-Type": "application/json"})
        print(f"Status /content/sites/connect: {resp2.status_code}")
        print(resp2.text)

asyncio.run(main())
