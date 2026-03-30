import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from src.web.shopify import ShopifyConnector

async def test_collision_retry():
    # Mock ShopifyConnector and its client
    connector = ShopifyConnector(store_url="test-store", access_token="test-token")
    connector._client = AsyncMock()
    
    # Mock _get_default_blog_id
    connector._get_default_blog_id = AsyncMock(return_value=123)
    
    # Mock first response: 422 Handle taken
    first_resp = AsyncMock()
    first_resp.status_code = 422
    first_resp.text = '{"errors":{"handle":["has already been taken"]}}'
    
    # Mock second response: 201 Created
    second_resp = AsyncMock()
    second_resp.status_code = 201
    second_resp.json.return_value = {
        "article": {
            "id": 456,
            "handle": "my-blog-988-abcd",
            "title": "my blog",
            "published_at": "2026-03-30T10:00:00Z"
        }
    }
    
    # Mock blog response (for URL construction)
    blog_resp = AsyncMock()
    blog_resp.status_code = 200
    blog_resp.json.return_value = {"blog": {"handle": "news"}}
    
    # Set up client.post to return first then second
    connector._client.post.side_effect = [first_resp, second_resp]
    connector._client.get.return_value = blog_resp
    
    print("Testing publish_blog_post with handle collision...")
    result = await connector.publish_blog_post(
        title="my blog",
        body_html="<p>hello</p>",
        handle="my-blog-988"
    )
    
    print(f"Result: {result}")
    
    # Verify calls
    assert connector._client.post.call_count == 2
    
    # Check first call payload
    first_call_args = connector._client.post.call_args_list[0]
    assert first_call_args.kwargs['json']['article']['handle'] == "my-blog-988"
    
    # Check second call payload (should have suffix)
    second_call_args = connector._client.post.call_args_list[1]
    new_handle = second_call_args.kwargs['json']['article']['handle']
    print(f"Second call handle: {new_handle}")
    assert new_handle.startswith("my-blog-988-")
    assert len(new_handle) > len("my-blog-988-")
    
    print("Test passed!")
    await connector.close()

if __name__ == "__main__":
    asyncio.run(test_collision_retry())
