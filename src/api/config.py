"""
API Configuration Settings

Centralized configuration using environment variables with Pydantic validation.
Note: dotenv is loaded in server.py before importing this module.
"""
from typing import List, Optional
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables with validation."""

    # ============================================================================
    # ENVIRONMENT & DEBUG
    # ============================================================================
    ENVIRONMENT: str = Field(default="development", description="Application environment (development/production)")
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG/INFO/WARNING/ERROR)")

    # ============================================================================
    # JWT & AUTHENTICATION (REQUIRED with validation)
    # ============================================================================
    SECRET_KEY: str = Field(..., min_length=32, description="JWT access token secret key (min 32 chars)")
    REFRESH_SECRET_KEY: str = Field(..., min_length=32, description="JWT refresh token secret key (min 32 chars)")
    ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiration (minutes)")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token expiration (days)")

    # API Key Authentication (Optional)
    API_KEY: Optional[str] = Field(default=None, description="API key for service authentication")
    API_KEY_NAME: Optional[str] = Field(default="X-API-Key", description="API key header name")

    # Auth Security Settings
    AUTH_MAX_LOGIN_ATTEMPTS: int = Field(default=3, description="Maximum failed login attempts before lockout")
    AUTH_LOCKOUT_DURATION_HOURS: int = Field(default=1, description="Account lockout duration in hours")

    # ============================================================================
    # DATABASE
    # ============================================================================
    POSTGRES_URI_CUSTOM: str = Field(..., description="PostgreSQL database connection URI")

    # ============================================================================
    # REDIS CACHE
    # ============================================================================
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL for caching")
    CACHE_ENABLED: bool = Field(default=True, description="Enable Redis caching")
    CACHE_DEFAULT_TTL: int = Field(default=300, description="Default cache TTL in seconds (5 minutes)")

    # ============================================================================
    # FRONTEND & CORS
    # ============================================================================
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend application URL")
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated CORS allowed origins"
    )
    CORS_ALLOWED_HEADERS: str = Field(
        default="Authorization,Content-Type,Accept,X-Request-ID,X-API-Key",
        description="Comma-separated list of allowed CORS request headers",
    )

    # ============================================================================
    # SERVER CONFIGURATION
    # ============================================================================
    HOST: str = Field(default="0.0.0.0", description="Server host address")
    PORT: int = Field(default=8000, description="Server port", ge=1, le=65535)

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=1000, description="Rate limit: requests per minute", ge=1)
    RATE_LIMIT_PER_HOUR: int = Field(default=10000, description="Rate limit: requests per hour", ge=1)
    RATE_LIMIT_PER_DAY: int = Field(default=100000, description="Rate limit: requests per day", ge=1)
    RATE_LIMITING_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    

    # Trusted reverse proxy IPs (comma-separated)
    TRUSTED_PROXY_IPS: str = Field(default="127.0.0.1,::1",description="Comma-separated list of trusted reverse proxy IPs")

    # ============================================================================
    # AI SERVICES
    # ============================================================================
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    PERPLEXITY_API_KEY: Optional[str] = Field(default=None, description="Perplexity AI API key")
    LANGSMITH_DEV_URL: Optional[str] = Field(default=None, description="LangSmith development URL")
    LANGSMITH_API_KEY: Optional[str] = Field(default=None, description="LangSmith API key")

    # ============================================================================
    # EMAIL / SMTP
    # ============================================================================
    SMTP_SERVER: Optional[str] = Field(default=None, description="SMTP server address")
    SMTP_PORT: int = Field(default=587, description="SMTP server port", ge=1, le=65535)
    EMAIL_ADDRESS: Optional[str] = Field(default=None, description="Email sender address")
    EMAIL_PASSWORD: Optional[str] = Field(default=None, description="Email sender password")

    # ============================================================================
    # MONITORING & OBSERVABILITY
    # ============================================================================
    SENTRY_DSN: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error tracking (optional)"
    )
    SENTRY_ENVIRONMENT: Optional[str] = Field(
        default=None,
        description="Sentry environment name (defaults to ENVIRONMENT if not set)"
    )
    SENTRY_TRACES_SAMPLE_RATE: float = Field(
        default=0.1,
        description="Sentry performance monitoring sample rate (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(
        default=0.1,
        description="Sentry profiling sample rate (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    SENTRY_ENABLE_TRACING: bool = Field(
        default=True,
        description="Enable Sentry performance tracing"
    )
    SENTRY_SEND_DEFAULT_PII: bool = Field(
        default=False,
        description="Send personally identifiable information to Sentry"
    )
    SENTRY_MAX_BREADCRUMBS: int = Field(
        default=50,
        description="Maximum number of breadcrumbs to send",
        ge=0,
        le=100
    )
    SENTRY_DEBUG: bool = Field(
        default=False,
        description="Enable Sentry debug mode (verbose logging)"
    )
    SENTRY_ATTACH_STACKTRACE: bool = Field(
        default=True,
        description="Attach stack traces to all messages"
    )
    SENTRY_RELEASE: Optional[str] = Field(
        default=None,
        description="Sentry release identifier (e.g., git commit SHA)"
    )

    # ============================================================================
    # FILE UPLOAD
    # ============================================================================
    UPLOAD_DIR: str = Field(default="/app/secure_uploads", description="Directory for uploaded files")
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, description="Maximum file upload size in MB", ge=1, le=1000)

    # Image constraints
    MAX_IMAGE_WIDTH: int = Field(default=4096, description="Maximum image width in pixels", ge=1)
    MAX_IMAGE_HEIGHT: int = Field(default=4096, description="Maximum image height in pixels", ge=1)
    MIN_IMAGE_WIDTH: int = Field(default=10, description="Minimum image width in pixels", ge=1)
    MIN_IMAGE_HEIGHT: int = Field(default=10, description="Minimum image height in pixels", ge=1)

    # File Security - MIME Type Whitelist
    from src.config.storage_config import get_all_allowed_types
    ALLOWED_MIME_TYPES: str = Field(
        default=get_all_allowed_types(),
        description="Comma-separated list of allowed MIME types for file uploads"
    )

    # File Security - Virus Scanning
    VIRUS_SCAN_ENABLED: bool = Field(
        default=False,
        description="Enable virus scanning for uploaded files"
    )
    VIRUS_SCAN_METHOD: str = Field(
        default="none",
        description="Virus scanning method: 'clamav', 'virustotal', or 'none'"
    )
    VIRUSTOTAL_API_KEY: Optional[str] = Field(
        default=None,
        description="VirusTotal API key (required if VIRUS_SCAN_METHOD=virustotal)"
    )
    CLAMAV_HOST: str = Field(
        default="localhost",
        description="ClamAV daemon host"
    )
    CLAMAV_PORT: int = Field(
        default=3310,
        description="ClamAV daemon port",
        ge=1,
        le=65535
    )
    CLAMAV_BINARY_PATH: str = Field(
        default="/usr/bin/clamdscan",
        description="Absolute path to the clamdscan binary"
    )
    VIRUS_SCAN_FAIL_BEHAVIOR: str = Field(
        default="closed",
        description="Behavior when virus scanner is unavailable: 'closed' (reject upload) or 'open' (allow upload). "
                    "Production should always use 'closed'. Use 'open' only for development/testing."
    )

    # Subscription Tier Limits - File Size (in MB)
    TIER_FREE_MAX_FILE_SIZE_MB: int = Field(default=10, description="Free tier: max file size in MB", ge=1)
    TIER_PRO_MAX_FILE_SIZE_MB: int = Field(default=50, description="Pro tier: max file size in MB", ge=1)
    TIER_ENTERPRISE_MAX_FILE_SIZE_MB: int = Field(default=200, description="Enterprise tier: max file size in MB", ge=1)

    # Subscription Tier Limits - Total Storage (in MB)
    TIER_FREE_MAX_STORAGE_MB: int = Field(default=100, description="Free tier: max total storage in MB", ge=1)
    TIER_PRO_MAX_STORAGE_MB: int = Field(default=1024, description="Pro tier: max total storage in MB (1GB)", ge=1)
    TIER_ENTERPRISE_MAX_STORAGE_MB: int = Field(default=10240, description="Enterprise tier: max total storage in MB (10GB)", ge=1)

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_allowed_origins(cls, v: str) -> str:
        """Reject '*' when credentials are enabled."""
        origins = [origin.strip() for origin in v.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError(
                "ALLOWED_ORIGINS cannot include '*' when credentialed CORS is enabled. "
                "Provide explicit origins."
            )
        return ",".join(origins)

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

    @field_validator('DEBUG', 'RATE_LIMITING_ENABLED', mode='before')
    @classmethod
    def parse_bool(cls, v) -> bool:
        """Parse boolean fields from string to boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return False

    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid value."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f'LOG_LEVEL must be one of: {", ".join(valid_levels)}')
        return v_upper

    # ============================================================================
    # HELPER PROPERTIES
    # ============================================================================

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(',') if origin.strip()]

    @property
    def cors_allowed_headers_list(self) -> List[str]:
        """Parse comma-separated CORS_ALLOWED_HEADERS into a list."""
        return [header.strip() for header in self.CORS_ALLOWED_HEADERS.split(",") if header.strip()]

    @property
    def database_url(self) -> str:
        """Alias for POSTGRES_URI_CUSTOM for backward compatibility."""
        return self.POSTGRES_URI_CUSTOM

    @property
    def upload_dir_path(self) -> Path:
        """Get UPLOAD_DIR as a Path object."""
        return Path(self.UPLOAD_DIR)

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"

    @property
    def sentry_environment(self) -> str:
        """Get Sentry environment, defaulting to ENVIRONMENT."""
        return self.SENTRY_ENVIRONMENT or self.ENVIRONMENT

    @property
    def sentry_enabled(self) -> bool:
        """Check if Sentry monitoring is enabled."""
        return bool(self.SENTRY_DSN)

    @property
    def allowed_mime_types_list(self) -> List[str]:
        """Parse comma-separated ALLOWED_MIME_TYPES into a list."""
        return [mime.strip() for mime in self.ALLOWED_MIME_TYPES.split(',') if mime.strip()]

    @property
    def virus_scanning_enabled(self) -> bool:
        """Check if virus scanning is enabled and properly configured."""
        if not self.VIRUS_SCAN_ENABLED:
            return False
        if self.VIRUS_SCAN_METHOD == "virustotal" and not self.VIRUSTOTAL_API_KEY:
            return False
        return self.VIRUS_SCAN_METHOD in ["clamav", "virustotal"]

    def get_tier_file_size_limit(self, tier: str) -> int:
        """
        Get max file size limit in MB for a subscription tier.

        Args:
            tier: Subscription tier name (free, pro, enterprise)

        Returns:
            Max file size in MB
        """
        tier_lower = tier.lower()
        if tier_lower == "pro":
            return self.TIER_PRO_MAX_FILE_SIZE_MB
        elif tier_lower == "enterprise":
            return self.TIER_ENTERPRISE_MAX_FILE_SIZE_MB
        else:  # free or unknown defaults to free
            return self.TIER_FREE_MAX_FILE_SIZE_MB

    def get_tier_storage_limit(self, tier: str) -> int:
        """
        Get max total storage limit in MB for a subscription tier.

        Args:
            tier: Subscription tier name (free, pro, enterprise)

        Returns:
            Max storage in MB
        """
        tier_lower = tier.lower()
        if tier_lower == "pro":
            return self.TIER_PRO_MAX_STORAGE_MB
        elif tier_lower == "enterprise":
            return self.TIER_ENTERPRISE_MAX_STORAGE_MB
        else:  # free or unknown defaults to free
            return self.TIER_FREE_MAX_STORAGE_MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

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
