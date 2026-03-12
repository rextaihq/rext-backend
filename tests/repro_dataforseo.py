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
                print(f"❌ No tasks in response. Full data: {data}")
                return
            
            task = tasks[0]
            print(f"Task status: {task.get('status_message')} (code: {task.get('status_code')})")
            
            result = task.get("result")
            if not result or not result[0]:
                print(f"❌ No result in tasks[0]. Task: {task}")
                return
            
            res = result[0]
            items = res.get("items", [])
            print(f"✅ Data found! Result keys: {res.keys()}")
            print(f"Items count: {len(items)}")
            if items:
                print(f"First item keyword: {items[0].get('keyword')}")
                print(f"First item intent: {items[0].get('search_intent_info', {}).get('main_intent')}")
            else:
                print("⚠️ Items list is empty.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    # TEST 1: CURRENT "FIXED" PAYLOAD
    fixed_payload = [{
        "location_name": "United States",
        "language_code": "en",
        "keywords": ["unlimited wordpress support"],
        "include_serp_info": True,
        "include_seed_keyword": True
    }]
    print("\n--- Testing Fixed Payload (with extra flags) ---")
    await test_dataforseo_payload(fixed_payload)

    # TEST 2: MINIMAL PAYLOAD
    minimal_payload = [{
        "location_name": "United States",
        "language_code": "en",
        "keywords": ["unlimited wordpress support"]
    }]
    print("\n--- Testing Minimal Payload ---")
    await test_dataforseo_payload(minimal_payload)

    # TEST 4: PAKISTAN LOCATION
    pakistan_payload = [{
        "location_name": "Pakistan",
        "language_code": "en",
        "keywords": ["unlimited wordpress support"]
    }]
    print("\n--- Testing Pakistan Location ---")
    await test_dataforseo_payload(pakistan_payload)

if __name__ == "__main__":
    asyncio.run(main())
