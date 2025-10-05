"""
API Configuration Settings

Centralized configuration using environment variables.
Note: dotenv is loaded in server.py before importing this module.
"""
import os
from typing import List


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # Frontend Configuration
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
        self.ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

        # Environment
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(',') if origin.strip()]


# Global settings instance
settings = Settings()
