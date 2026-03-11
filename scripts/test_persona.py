
import asyncio
from uuid import UUID
from src.api.database.async_database import get_async_db_context
from src.services.workspace_pipeline import WorkspacePipeline
from src.api.schema.knowledge_schema import BrandSchema
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_extraction():
    workspace_id = UUID("dfcdd331-ec59-47d7-b5e2-8488748cd501")
    user_id = UUID("0a96fdb3-9834-4749-ae69-9a2e6101c9e8")
    url = "https://revnix.com"
    
    async with get_async_db_context() as db:
        pipeline = WorkspacePipeline(
            db=db,
            operation_id="test-op",
            workspace_id=workspace_id,
            user_id=user_id,
            url=url
        )
        
        # Test content with real person + audience description
        content = """
        Revnix specialized in SEO and AI content. The company was founded by Mobheen Abdullah, 
        who serves as our CEO. Mobheen has over 15 years of experience in digital marketing.
        
        Our platform is perfect for the "Busy Marketing Manager" who needs to automate 
        their daily content generation tasks. We also serve "Small Business Owners" 
        located in urban areas.
        """
        
        print("--- Testing Selective Extraction ---")
        brand_schema = await pipeline._default_brand_voice_generator(content)
        print(f"Extracted {len(brand_schema.personas)} personas.")
        for p in brand_schema.personas:
            print(f" - Found Persona: {p.name} ({p.professional_title})")
            if p.name in ["Busy Marketing Manager", "Small Business Owner"]:
                print("❌ FAILED: Extracted a dummy target audience persona!")
        
        if any(p.name == "Mobheen Abdullah" for p in brand_schema.personas):
            print("✅ SUCCESS: Correctly extracted real person.")
            
        print("\n--- Testing Persistence ---")
        await pipeline._persist_brand_voice(brand_schema)
        await db.commit()
        print("Persistence complete.")

if __name__ == "__main__":
    asyncio.run(test_extraction())
