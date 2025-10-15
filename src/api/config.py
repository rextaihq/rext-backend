"""
API Configuration Settings

Centralized configuration using environment variables with Pydantic validation.
Note: dotenv is loaded in server.py before importing this module.
"""
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables with validation."""

    # JWT & Authentication (REQUIRED with validation)
    SECRET_KEY: str = Field(..., min_length=32, description="JWT access token secret key (min 32 chars)")
    REFRESH_SECRET_KEY: str = Field(..., min_length=32, description="JWT refresh token secret key (min 32 chars)")
    ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, description="Access token expiration (minutes)")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token expiration (days)")

    # Frontend Configuration
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend application URL")
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated CORS allowed origins"
    )

    # Environment
    ENVIRONMENT: str = Field(default="development", description="Application environment")
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    @field_validator('SECRET_KEY', 'REFRESH_SECRET_KEY')
    @classmethod
    def validate_secret_strength(cls, v: str, info) -> str:
        """
        Validate that secret keys are strong enough for production use.

        Args:
            v: The secret key value
            info: Validation info context

        Returns:
            The validated secret key

        Raises:
            ValueError: If the secret key is too weak
        """
        if not v or len(v) < 32:
            raise ValueError(
                f'{info.field_name} must be at least 32 characters long. '
                f'Use scripts/generate_jwt_secret.py to generate a secure key.'
            )
        # Warn if using obvious placeholder values
        if v in ['your-secret-key-here', 'changeme', 'secret', 'password']:
            raise ValueError(
                f'{info.field_name} contains an insecure placeholder value. '
                f'Use scripts/generate_jwt_secret.py to generate a secure key.'
            )
        return v

    @field_validator('DEBUG', mode='before')
    @classmethod
    def parse_debug(cls, v) -> bool:
        """Parse DEBUG from string to boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return False

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(',') if origin.strip()]

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars not defined in this class


# Singleton pattern for settings
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get or create the global settings instance.

    This function implements a singleton pattern to ensure settings are
    loaded only once during application startup.

    Returns:
        Settings: The validated application settings

    Raises:
        ValueError: If required settings are missing or invalid
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Global settings instance (for backward compatibility)
# New code should use get_settings() instead
settings = get_settings()
