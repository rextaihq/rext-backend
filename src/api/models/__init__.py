# Models are imported individually where needed
# This file intentionally left mostly empty to avoid circular import issues
# and to allow lazy loading of model relationships

# Only import the base to ensure it's available
from src.api.database.database import Base

__all__ = ["Base"]
