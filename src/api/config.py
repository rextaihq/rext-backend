"""
API Configuration Settings

Centralized configuration using environment variables with Pydantic validation.
Note: dotenv is loaded in src/api/server.py before importing this module.
"""

import re
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config.hidden_secrets import HidesSecrets

# Signing secrets that are public, so never a secret: the placeholders this repository
# has shipped, and every value .env.example holds (read where the file sits beside the app).
_PLACEHOLDER_SECRETS = {"your-secret-key-here", "changeme", "secret", "password"}
_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
_EXAMPLE_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(.*)$")


def _env_example_values() -> set:
    try:
        lines = _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    values = set()
    for line in lines:
        # Commented examples ("# DATABASE_URL=...") are just as public.
        match = _EXAMPLE_ASSIGNMENT.match(line.strip().lstrip("#").strip())
        if match:
            value = match.group(1).strip().strip("'\"")
            if value:
                values.add(value)
    return values


def _is_public_secret(value: str) -> bool:
    folded = value.strip().lower()
    return (
        folded in _PLACEHOLDER_SECRETS
        or folded.startswith("replace_with")
        or value.strip() in _env_example_values()
    )


class Settings(HidesSecrets, BaseSettings):
    """Application settings loaded from environment variables with validation."""

    # ============================================================================
    # ENVIRONMENT & DEBUG
    # ============================================================================
    ENVIRONMENT: str = Field(
        default="development", description="Application environment (development/production)"
    )
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    MIGRATE_ON_START: bool = Field(
        default=False,
        description="Apply the pending Alembic migrations before serving (the image sets it)",
    )
    LOCAL_UNLIMITED_WORKSPACES: bool = Field(
        default=False,
        description="Local-only override for workspace limit testing; requires ENVIRONMENT=local",
    )
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG/INFO/WARNING/ERROR)")

    # ============================================================================
    # JWT & AUTHENTICATION (REQUIRED with validation)
    # ============================================================================
    SECRET_KEY: str = Field(
        ..., min_length=32, description="JWT access token secret key (min 32 chars)"
    )
    REFRESH_SECRET_KEY: str = Field(
        ..., min_length=32, description="JWT refresh token secret key (min 32 chars)"
    )
    ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, ge=1, description="Access token expiration (minutes)"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, ge=1, description="Refresh token expiration (days)"
    )
    REFRESH_REPLAY_GRACE_SECONDS: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="How long a rotated refresh token may resolve to its deterministic successor",
    )

    # API Key Authentication (Optional)
    API_KEY: Optional[str] = Field(default=None, description="API key for service authentication")
    API_KEY_NAME: Optional[str] = Field(default="X-API-Key", description="API key header name")

    # Auth Security Settings
    AUTH_MAX_LOGIN_ATTEMPTS: int = Field(
        default=5, description="Maximum failed login attempts before lockout"
    )
    AUTH_LOCKOUT_DURATION_HOURS: int = Field(
        default=1, description="Account lockout duration in hours"
    )
    REQUIRE_EMAIL_VERIFICATION: bool = Field(
        default=True, description="Enforce email verification before login"
    )
    USER_DELETION_RETENTION_DAYS: int = Field(
        default=14, description="Days to retain soft-deleted users before permanent purge"
    )

    # ============================================================================
    # DATABASE
    # ============================================================================
    POSTGRES_URI_CUSTOM: str = Field(..., description="PostgreSQL database connection URI")

    # Connection pool tuning — keep in sync with PgBouncer DEFAULT_POOL_SIZE
    POSTGRES_POOL_SIZE: int = Field(
        default=10, ge=1, description="SQLAlchemy connection pool size per engine"
    )
    POSTGRES_MAX_OVERFLOW: int = Field(
        default=15, ge=0, description="Max overflow connections beyond pool_size"
    )
    POSTGRES_POOL_TIMEOUT: int = Field(
        default=30, ge=5, description="Seconds to wait for a pool connection before timeout"
    )
    # Below Neon's 5-minute idle cutoff: a pooled connection older than this is
    # replaced at checkout instead of being handed out after the server closed
    # it ("cannot call Transaction.rollback(): the underlying connection is
    # closed"). pool_pre_ping cannot be used instead - see async_database.py.
    POSTGRES_POOL_RECYCLE: int = Field(
        default=280, ge=60, description="Seconds before a connection is recycled"
    )

    # ============================================================================
    # REDIS CACHE
    # ============================================================================
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL for caching"
    )
    CACHE_ENABLED: bool = Field(default=True, description="Enable Redis caching")
    CACHE_DEFAULT_TTL: int = Field(
        default=300, description="Default cache TTL in seconds (5 minutes)"
    )
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=1, description="Redis client pool size")

    # ============================================================================
    # FRONTEND & CORS
    # ============================================================================
    FRONTEND_URL: str = Field(
        default="http://localhost:3000", description="Frontend application URL"
    )
    BACKEND_URL: Optional[str] = Field(
        default=None, description="Public backend base URL, used to generate absolute callback URLs"
    )
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated CORS allowed origins",
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
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=1000, description="Rate limit: requests per minute", ge=1
    )
    RATE_LIMIT_PER_HOUR: int = Field(
        default=10000, description="Rate limit: requests per hour", ge=1
    )
    RATE_LIMIT_PER_DAY: int = Field(
        default=100000, description="Rate limit: requests per day", ge=1
    )
    RATE_LIMITING_ENABLED: bool = Field(default=True, description="Enable rate limiting")

    # The public free tools (/api/v1/tools/*, src/api/tool/limits.py): per visitor, per tool and
    # per UTC day, and one daily budget for the tools that call a model.
    FREE_TOOLS_MODEL_CALLS_PER_DAY: int = Field(
        default=20, ge=0, description="Free tools: calls per visitor per model tool per day"
    )
    FREE_TOOLS_CALLS_PER_DAY: int = Field(
        default=100, ge=0, description="Free tools: calls per visitor per other tool per day"
    )
    FREE_TOOLS_DAILY_BUDGET_USD: float = Field(
        default=5.0, ge=0, description="Free tools: the most their model calls spend per day, US$"
    )
    TURNSTILE_SECRET_KEY: Optional[str] = Field(
        default=None,
        description="Free tools: Cloudflare Turnstile's secret key for the bot check; unset, no check",
    )

    # Trusted reverse proxy IPs (comma-separated)
    TRUSTED_PROXY_IPS: str = Field(
        default="127.0.0.1,::1", description="Comma-separated list of trusted reverse proxy IPs"
    )

    # ============================================================================
    # AI SERVICES
    # ============================================================================
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    PERPLEXITY_API_KEY: Optional[str] = Field(default=None, description="Perplexity AI API key")
    AI_IMAGE_GENERATION_ENABLED: bool = Field(
        default=False,
        description=(
            "Feature flag for the image-generation model call. When disabled, the "
            "content agent still runs the full image planning pipeline (art "
            "direction, composition, alt text, placement) but never calls the paid "
            "image model — a manual-upload placeholder is embedded in the generated "
            "content instead, for the user to fill in from the editor (optional; "
            "content can be published with no image)."
        ),
    )
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
    # SHOPIFY APP BRIDGE
    # ============================================================================
    SHOPIFY_APP_SLUG: str = Field(
        default="rext-publisher-1", description="Shopify app slug used in admin launch URLs"
    )
    SHOPIFY_API_KEY: Optional[str] = Field(
        default=None, description="Shopify app client ID / API key used for OAuth installation"
    )
    SHOPIFY_API_SECRET: Optional[str] = Field(
        default=None, description="Shopify app client secret used for OAuth installation"
    )
    SHOPIFY_APP_SCOPES: str = Field(
        default="read_products,write_content",
        description="Comma-separated Shopify OAuth scopes requested during installation",
    )
    SHOPIFY_INSTALL_CALLBACK_PATH: str = Field(
        default="/api/routes/integrations/shopify/install/callback",
        description="Backend callback path registered in the Shopify app setup",
    )
    SHOPIFY_INTEGRATION_RETURN_PATH: str = Field(
        default="/integrations",
        description="Frontend path to redirect to after Shopify installation completes",
    )
    SHOPIFY_APP_ENTRY_PATH: str = Field(
        default="/app/blogpost", description="Shopify app entry path in admin"
    )
    SHOPIFY_BRIDGE_BASE_URL: Optional[str] = Field(
        default=None, description="Base URL for server-to-server calls to the Shopify app backend"
    )
    SHOPIFY_BRIDGE_PUBLISH_ENDPOINT: str = Field(
        default="/app/api/rext/publish",
        description="Relative endpoint used for app-bridge blog publish requests",
    )
    SHOPIFY_BRIDGE_SHARED_SECRET: Optional[str] = Field(
        default=None, description="Shared secret used to sign Rext -> Shopify app bridge requests"
    )

    # ============================================================================
    # MONITORING & OBSERVABILITY
    # ============================================================================
    ERROR_LOG_MIN_SEVERITY: str = Field(
        default="medium",
        description=(
            "Lowest severity persisted to error_logs and shown in the admin "
            "Error Logs tab. One of: warning, error, critical (the previous "
            "release's medium/high are still accepted and normalised)."
        ),
    )
    ERROR_LOG_CAPTURE_LOGGED_ERRORS: bool = Field(
        default=True,
        description=(
            "Record logger.error/logger.critical calls from anywhere in the "
            "application as error_logs rows. Most failures are caught, logged "
            "and recovered from rather than raised, so without this they exist "
            "only in stdout. Deduplicated per module and message."
        ),
    )
    ERROR_LOG_DEPENDENCY_THROTTLE_SECONDS: int = Field(
        default=300,
        ge=0,
        description=(
            "Minimum seconds between recorded failures for the same "
            "infrastructure dependency. A dependency that is down fails on "
            "every request, so this stops one outage from burying every other "
            "error on the dashboard."
        ),
    )
    ERROR_LOG_MAX_VALIDATION_FIELDS: int = Field(
        default=20,
        ge=1,
        description=(
            "Maximum number of invalid fields recorded on a single validation "
            "error. Bounds the stored metadata so one request rejecting "
            "hundreds of fields cannot write an unbounded row."
        ),
    )
    ERROR_LOG_EXCLUDED_PATH_PREFIXES: List[str] = Field(
        default=["/api/v1/admin/monitoring"],
        description=(
            "Request paths whose errors are not persisted. The monitoring "
            "endpoints are excluded so a failure there cannot fill the very "
            "table an operator is reading to diagnose it."
        ),
    )
    METRICS_EXCLUDED_PATH_PREFIXES: List[str] = Field(
        default=["/api/v1/admin/monitoring"],
        description=(
            "Request paths excluded from API usage counters. The monitoring "
            "dashboard polls itself, so counting it makes the metric measure "
            "the act of looking at it."
        ),
    )
    REPORTING_TIMEZONE: str = Field(
        default="UTC",
        description=(
            "Timezone used to align reporting periods to calendar days, so "
            "'7 days' means seven whole local days rather than a rolling 168h."
        ),
    )
    SENTRY_DSN: Optional[str] = Field(
        default=None, description="Sentry DSN for error tracking (optional)"
    )
    SENTRY_ENVIRONMENT: Optional[str] = Field(
        default=None, description="Sentry environment name (defaults to ENVIRONMENT if not set)"
    )
    SENTRY_TRACES_SAMPLE_RATE: float = Field(
        default=0.1,
        description="Sentry performance monitoring sample rate (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )
    SENTRY_PROFILES_SAMPLE_RATE: float = Field(
        default=0.1, description="Sentry profiling sample rate (0.0-1.0)", ge=0.0, le=1.0
    )
    SENTRY_ENABLE_TRACING: bool = Field(
        default=True, description="Enable Sentry performance tracing"
    )
    SENTRY_SEND_DEFAULT_PII: bool = Field(
        default=False, description="Send personally identifiable information to Sentry"
    )
    SENTRY_MAX_BREADCRUMBS: int = Field(
        default=50, description="Maximum number of breadcrumbs to send", ge=0, le=100
    )
    SENTRY_DEBUG: bool = Field(
        default=False, description="Enable Sentry debug mode (verbose logging)"
    )
    SENTRY_ATTACH_STACKTRACE: bool = Field(
        default=True, description="Attach stack traces to all messages"
    )
    SENTRY_RELEASE: Optional[str] = Field(
        default=None, description="Sentry release identifier (e.g., git commit SHA)"
    )

    # ============================================================================
    # FILE UPLOAD
    # ============================================================================
    UPLOAD_DIR: str = Field(
        default="/app/secure_uploads", description="Directory for uploaded files"
    )
    MAX_UPLOAD_SIZE_MB: int = Field(
        default=10, description="Maximum file upload size in MB", ge=1, le=1000
    )

    # Image constraints
    MAX_IMAGE_WIDTH: int = Field(default=4096, description="Maximum image width in pixels", ge=1)
    MAX_IMAGE_HEIGHT: int = Field(default=4096, description="Maximum image height in pixels", ge=1)
    MIN_IMAGE_WIDTH: int = Field(default=10, description="Minimum image width in pixels", ge=1)
    MIN_IMAGE_HEIGHT: int = Field(default=10, description="Minimum image height in pixels", ge=1)

    # File Security - MIME Type Whitelist
    from src.config.storage_config import get_all_allowed_types

    ALLOWED_MIME_TYPES: str = Field(
        default=",".join(get_all_allowed_types()),
        description="Comma-separated list of allowed MIME types for file uploads",
    )

    # File Security - Virus Scanning
    VIRUS_SCAN_ENABLED: bool = Field(
        default=False, description="Enable virus scanning for uploaded files"
    )
    VIRUS_SCAN_METHOD: str = Field(
        default="none", description="Virus scanning method: 'clamav', 'virustotal', or 'none'"
    )
    VIRUSTOTAL_API_KEY: Optional[str] = Field(
        default=None, description="VirusTotal API key (required if VIRUS_SCAN_METHOD=virustotal)"
    )
    CLAMAV_HOST: str = Field(default="localhost", description="ClamAV daemon host")
    CLAMAV_PORT: int = Field(default=3310, description="ClamAV daemon port", ge=1, le=65535)
    CLAMAV_BINARY_PATH: str = Field(
        default="/usr/bin/clamdscan", description="Absolute path to the clamdscan binary"
    )
    VIRUS_SCAN_FAIL_BEHAVIOR: str = Field(
        default="closed",
        description="Behavior when virus scanner is unavailable: 'closed' (reject upload) or 'open' (allow upload). "
        "Production should always use 'closed'. Use 'open' only for development/testing.",
    )

    # Subscription Tier Limits - File Size (in MB)
    TIER_FREE_MAX_FILE_SIZE_MB: int = Field(
        default=10, description="Free tier: max file size in MB", ge=1
    )
    TIER_PRO_MAX_FILE_SIZE_MB: int = Field(
        default=50, description="Pro tier: max file size in MB", ge=1
    )
    TIER_ENTERPRISE_MAX_FILE_SIZE_MB: int = Field(
        default=200, description="Enterprise tier: max file size in MB", ge=1
    )

    # Subscription Tier Limits - Total Storage (in MB)
    TIER_FREE_MAX_STORAGE_MB: int = Field(
        default=100, description="Free tier: max total storage in MB", ge=1
    )
    TIER_PRO_MAX_STORAGE_MB: int = Field(
        default=1024, description="Pro tier: max total storage in MB (1GB)", ge=1
    )
    TIER_ENTERPRISE_MAX_STORAGE_MB: int = Field(
        default=10240, description="Enterprise tier: max total storage in MB (10GB)", ge=1
    )

    # ============================================================================
    # MINIO / S3 STORAGE
    # ============================================================================
    MINIO_ENDPOINT: str = Field(default="localhost:9000", description="MinIO/S3 endpoint")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="MinIO/S3 access key")
    MINIO_SECRET_KEY: str = Field(default="minioadmin", description="MinIO/S3 secret key")
    MINIO_BUCKET: str = Field(default="rext-media", description="MinIO/S3 bucket name")
    MINIO_USE_SSL: bool = Field(default=False, description="Use SSL for MinIO/S3 connection")
    MINIO_PUBLIC_URL: Optional[str] = Field(
        default=None,
        description="Public URL for accessing MinIO files (e.g. via CDN or reverse proxy)",
    )

    @field_validator("ERROR_LOG_MIN_SEVERITY")
    @classmethod
    def _validate_error_log_min_severity(cls, v: str) -> str:
        """Reject an unknown level loudly instead of silently logging nothing."""
        # Configured on the stored scale (warning/error/critical). The previous
        # release used the API scale, so "medium" and "high" are still accepted
        # and normalised rather than failing a deploy on an existing .env.
        allowed = {"warning", "error", "critical", "medium", "high"}
        if (v or "").lower() not in allowed:
            raise ValueError(f"ERROR_LOG_MIN_SEVERITY must be one of {sorted(allowed)}, got {v!r}")
        return v.lower()

    @field_validator("MINIO_USE_SSL", mode="before")
    @classmethod
    def parse_minio_ssl(cls, v) -> bool:
        """Parse boolean field from string to boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return False

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

    @field_validator("SECRET_KEY", "REFRESH_SECRET_KEY", mode="before")
    @classmethod
    def refuse_public_secrets(cls, v, info):
        """A signing secret anyone can read is refused, whatever its length: the
        placeholders this repository has shipped, any "replace_with…" value, and any
        value in .env.example (which is public)."""
        if isinstance(v, str) and _is_public_secret(v):
            raise ValueError(
                f"{info.field_name} contains an insecure placeholder value. "
                "Generate one with `openssl rand -hex 32`."
            )
        return v

    @model_validator(mode="after")
    def refuse_one_secret_for_both_tokens(self):
        """Access and refresh tokens are signed with different secrets, so one can't
        stand in for the other."""
        if self.SECRET_KEY == self.REFRESH_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY and REFRESH_SECRET_KEY must differ. "
                "Generate each with `openssl rand -hex 32`."
            )
        return self

    @field_validator("SECRET_KEY", "REFRESH_SECRET_KEY")
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
                f"{info.field_name} must be at least 32 characters long. "
                f"Use scripts/generate_jwt_secret.py to generate a secure key."
            )
        return v

    @field_validator("DEBUG", "RATE_LIMITING_ENABLED", mode="before")
    @classmethod
    def parse_bool(cls, v) -> bool:
        """Parse boolean fields from string to boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return False

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid value."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_levels)}")
        return v_upper

    # ============================================================================
    # HELPER PROPERTIES
    # ============================================================================

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

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
    def frontend_root_url(self) -> str:
        """Return the configured frontend origin normalized to its root path."""
        return f"{self.FRONTEND_URL.rstrip('/')}/"

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
        return [mime.strip() for mime in self.ALLOWED_MIME_TYPES.split(",") if mime.strip()]

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
        # A validation error at startup names the setting, never its value: a rejected
        # secret, or the whole input for a check across settings, would reach the logs.
        hide_input_in_errors=True,
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
