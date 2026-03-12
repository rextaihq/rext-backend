import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

DATAFORSEO_BACKLINKS_URL = os.getenv("DATAFORSEO_BACKLINKS_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")

headers = {
    "Authorization": f"Basic {AUTH_HEADER}",
    "Content-Type": "application/json"
}

async def test_dataforseo_payload(payload):
    print(f"Testing payload: {payload}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(DATAFORSEO_BACKLINKS_URL, headers=headers, json=payload)
            print(f"Status Code: {response.status_code}")
            data = response.json()
            # print(f"Response: {data}")
            tasks = data.get("tasks", [])
            if not tasks:
                print("❌ No tasks in response")
                return
            
            result = tasks[0].get("result")
            if not result or not result[0]:
                print("❌ No result in tasks[0]")
                return
            
            print("✅ Data found!")
            print(f"Result keys: {result[0].keys()}")
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    # CURRENT WRONG PAYLOAD
    wrong_payload = [{
        "location_name": "United States",
        "language_code": "en",
        "keyword": "unlimited wordpress support",
        "include_serp_info": True,
        "include_seed_keyword": True
    }]
    print("\n--- Testing Wrong Payload ---")
    await test_dataforseo_payload(wrong_payload)

    # PROPOSED CORRECT PAYLOAD (using 'keywords' plural for keyword_overview/live)
    correct_payload = [{
        "location_name": "United States",
        "language_code": "en",
        "keywords": ["unlimited wordpress support"]
    }]
    print("\n--- Testing Correct Payload ---")
    await test_dataforseo_payload(correct_payload)

if __name__ == "__main__":
    asyncio.run(main())
