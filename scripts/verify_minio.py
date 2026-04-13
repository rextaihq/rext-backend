import sys
import os
from pathlib import Path

# Add src to python path
sys.path.append(str(Path(__file__).parent.parent))

from src.utils.storage import storage_service
from src.utils.logger import logger

def test_minio_connection():
    logger.info("Testing MinIO connection...")
    success = storage_service.check_connection()
    if success:
        logger.info("✅ Successfully connected to MinIO!")
        
        # Try to ensure bucket exists (test permissions)
        try:
            storage_service._ensure_bucket_exists()
            logger.info(f"✅ Bucket '{storage_service.bucket_name}' is ready.")
        except Exception as e:
            logger.error(f"❌ Failed to ensure bucket exists: {str(e)}")
            return False
            
        return True
    else:
        logger.error("❌ Failed to connect to MinIO.")
        return False

if __name__ == "__main__":
    if test_minio_connection():
        sys.exit(0)
    else:
        sys.exit(1)
