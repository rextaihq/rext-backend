#!/usr/bin/env python3
"""Export OpenAPI schema from FastAPI application."""
import json
import sys
from pathlib import Path

# Add project root and src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from api.server import app

try:
    from api.lib.logger import auto_logger
    logger = auto_logger()
except ImportError:
    # Fallback to print if logger not available
    class FallbackLogger:
        def info(self, msg): print(msg)
        def error(self, msg): print(f"ERROR: {msg}", file=sys.stderr)
    logger = FallbackLogger()

def export_openapi():
    """Export OpenAPI schema to JSON file."""
    try:
        logger.info("Generating OpenAPI schema...")
        openapi_schema = app.openapi()

        output_path = Path(__file__).parent.parent / "openapi.json"
        with open(output_path, "w") as f:
            json.dump(openapi_schema, f, indent=2)

        logger.info(f"✅ OpenAPI schema exported to {output_path}")
        print(f"✅ OpenAPI schema exported successfully to {output_path}")

    except Exception as e:
        logger.error(f"Failed to export OpenAPI schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    export_openapi()
