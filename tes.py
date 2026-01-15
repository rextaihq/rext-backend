import requests
import urllib3

# Disable SSL warnings for local development (remove in production!)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# WordPress REST API endpoint
url = "https://rextpostpublisher.local/wp-json/wp/v2/posts"

# Authentication using Application Password (HTTP Basic Auth)
username = "admin"
app_password = "DBC4 ziu3 5ojH AOwf AMjR sApb"  # Remove spaces for auth

# Test: Create a new post
post_data = {
    "title": "Test Post from Python",
    "content": "This is a test post created via WordPress REST API",
    "status": "draft"  # Use 'publish' to publish immediately
}

try:
    response = requests.post(
        url,
        json=post_data,
        auth=(username, app_password.replace(" ", "")),  # Remove spaces from app password
        verify=False  # Disable SSL verification for self-signed certificates (LOCAL ONLY!)
    )
    
    response.raise_for_status()  # Raise exception for 4xx/5xx status codes
    
    post = response.json()
    print(f"✅ Success! Post created:")
    print(f"   ID: {post.get('id')}")
    print(f"   Title: {post.get('title', {}).get('rendered')}")
    print(f"   Link: {post.get('link')}")
    print(f"   Status: {post.get('status')}")
    
except requests.exceptions.HTTPError as e:
    print(f"❌ HTTP Error: {e}")
    print(f"   Response: {response.text}")
except Exception as e:
    print(f"❌ Error: {e}")