import sys
import os
import asyncio
from pathlib import Path
from uuid import uuid4, UUID

# Add src to python path
sys.path.append(str(Path(__file__).parent.parent))

from src.services.sse_service import event_stream_manager, OperationEvent
from src.utils.logger import logger

async def test_sse_formatting():
    logger.info("Testing SSE formatting...")
    operation_id = f"test-op-{uuid4()}"
    user_id = uuid4()
    
    # Subscribe to the stream
    stream = event_stream_manager.subscribe(operation_id, user_id)
    
    # Get the first event (connection established)
    try:
        connection_event = await stream.__anext__()
        logger.info(f"Received connection event: {connection_event}")
        
        if not isinstance(connection_event, dict):
            logger.error("❌ Connection event is not a dictionary!")
            return False
            
        if "data" not in connection_event or "event" not in connection_event:
            logger.error("❌ Connection event missing required SSE fields!")
            return False
            
        logger.info("✅ SSE formatting verified successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to get SSE event: {str(e)}")
        return False

if __name__ == "__main__":
    if asyncio.run(test_sse_formatting()):
        sys.exit(0)
    else:
        sys.exit(1)
