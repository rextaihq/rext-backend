import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SITE_URL = "https://staging.wpaegis.com"
API_ENDPOINT = f"{SITE_URL}/wp-json/rext-ai/v1/posts"
API_KEY = "rext_1aad9bb0cb9c6aa8d930bb0ff6ba41e01a0749dcef5773d38f618d86a7788aff"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

post_data = {
    "title": "Test Post from Python",
    "content": "This is a test post created via custom API",
    "status": "draft"
}

try:
    response = requests.post(
        API_ENDPOINT,
        headers=headers,
        json=post_data,
        verify=False,
        timeout=10
    )

    print("Status:", response.status_code)
    print("Response:", response.text)

except Exception as e:
    print("❌ Error:", e)
