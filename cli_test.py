import asyncio
from src.flow.service.service import LangGraphService
from datetime import datetime


async def test():
    svc = LangGraphService(url="http://localhost:2024", api_key="YOUR_KEY")

    # Create assistant
    assistant = await svc.create_assistant(
        graph_id="agent", name="my_content_assistant"
    )
    print("Assistant created:", assistant)

    # Run flow (non-stream)
    result = await svc.run_assistant(
        assistant_id=assistant["assistant_id"],
        input_payload={"title": "Hello world", "audience": "developers"}
    )
    print("Run result:", result)
    
    # --- Payload for content workflow ---
    payload = {
    "title": "Ai Revolution in 2025",
    "content_language": "English",
    "status": "draft",
    "author_id":"911a4149-e279-4259-9d25-47f42795538d",
    "workspace_id": "0b4da323-108a-4430-8c4e-d17e9d319e0d",
    "topic_id": "0a694781-5d1e-48bf-9d27-a9d7a4d29555",
    "body_markdown": "",
    "content_format": "Markdown",
    "assigned_to_user_id": "911a4149-e279-4259-9d25-47f42795538d",
    "metadata": {
        "content_summary": "thsi is a test summary",
        "content_type": "blog posr",
        "target_platform": "health care",
        "target_industry": "health case",
        "target_audience": [
        "patient"
        ],
        "audience_size": "small",
        "complexity_level": "beginner",
        "content_tone": [
        "friendly"
        ],
        "target_region": "us",
        "content_objectives": [
        ""
        ],
        "source_references": [
        ""
        ],
        "content_word_count": 1,
        "reading_time_minutes": 1,
        "content_quality_scores": {
        "propertyName*": "anything"
        },
        "featured_image_prompt": "",
        "featured_image_alt_text": ""
    },
    "seo_data": {
        "content_primary_keywords": [
        "testing"
        ],
        "content_secondary_keywords": [
        "testing"
        ],
        "content_meta_description": "testing ",
        "content_search_intent": [
        "testing"
        ],
        "content_seo_score": 0,
        "content_readability_score": 0
    }
    }

    # --- Run streaming mode ---
    async for mode, chunk in svc.run_assistant_stream(
        assistant_id=assistant["assistant_id"],
        input_payload={
            "request_payload":payload
        },
        metadata={"source": "local_test"}
    ):
        # print(f"Mode: [{mode.upper()}] — keys: {list(chunk.keys()) if isinstance(chunk, dict) else chunk}")

        # print(f"Mode: [{mode.upper()}]")
        pass
    print("\n✅ Stream finished successfully.\n")

    await svc.close()

if __name__ == "__main__":
    asyncio.run(test())
