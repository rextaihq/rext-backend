"""
Security tests for file upload validation.

Tests:
- MIME type validation
- File size limits by subscription tier
- Storage quota enforcement
- Virus scanning integration (mocked)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.file_security import FileSecurityValidator, ValidationResult
from src.api.config import Settings


# Test fixtures
@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_settings():
    """Mock settings with test configuration."""
    settings = MagicMock(spec=Settings)
    settings.allowed_mime_types_list = [
        "image/jpeg",
        "image/png",
        "application/pdf",
        "text/plain"
    ]
    settings.TIER_FREE_MAX_FILE_SIZE_MB = 10
    settings.TIER_PRO_MAX_FILE_SIZE_MB = 50
    settings.TIER_ENTERPRISE_MAX_FILE_SIZE_MB = 200
    settings.TIER_FREE_MAX_STORAGE_MB = 100
    settings.TIER_PRO_MAX_STORAGE_MB = 1024
    settings.TIER_ENTERPRISE_MAX_STORAGE_MB = 10240
    settings.VIRUS_SCAN_ENABLED = False
    settings.virus_scanning_enabled = False
    settings.get_tier_file_size_limit = lambda tier: {
        "free": 10,
        "pro": 50,
        "enterprise": 200
    }.get(tier.lower(), 10)
    settings.get_tier_storage_limit = lambda tier: {
        "free": 100,
        "pro": 1024,
        "enterprise": 10240
    }.get(tier.lower(), 100)
    return settings


@pytest.fixture
def validator(mock_db, mock_settings):
    """Create validator instance."""
    return FileSecurityValidator(mock_db, mock_settings)


# MIME Type Tests
class TestMIMETypeValidation:
    """Test MIME type validation."""

    def test_valid_jpeg(self, validator):
        """Test that JPEG images are accepted."""
        # JPEG magic bytes
        jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        result = validator.validate_mime_type(jpeg_bytes, "test.jpg")
        assert result.is_valid

    def test_valid_png(self, validator):
        """Test that PNG images are accepted."""
        # PNG magic bytes
        png_bytes = b'\x89PNG\r\n\x1a\n'
        result = validator.validate_mime_type(png_bytes, "test.png")
        assert result.is_valid

    def test_valid_pdf(self, validator):
        """Test that PDF documents are accepted."""
        # PDF magic bytes
        pdf_bytes = b'%PDF-1.4'
        result = validator.validate_mime_type(pdf_bytes, "test.pdf")
        assert result.is_valid

    def test_valid_text_file(self, validator):
        """Test that text files are accepted."""
        text_bytes = b'Hello, world! This is a text file.'
        result = validator.validate_mime_type(text_bytes, "test.txt")
        assert result.is_valid

    def test_reject_executable(self, validator):
        """Test that executable files are rejected."""
        # Windows EXE magic bytes
        exe_bytes = b'MZ\x90\x00'
        result = validator.validate_mime_type(exe_bytes, "virus.exe")
        assert not result.is_valid
        assert result.error_code == "UNKNOWN_FILE_TYPE" or result.error_code == "INVALID_MIME_TYPE"

    def test_reject_unknown_binary(self, validator):
        """Test that unknown binary files are rejected."""
        random_bytes = b'\x00\x01\x02\x03\x04\x05'
        result = validator.validate_mime_type(random_bytes, "unknown.bin")
        assert not result.is_valid


# File Size Tests
class TestFileSizeValidation:
    """Test file size limit enforcement."""

    def test_free_tier_accepts_small_file(self, validator):
        """Test free tier accepts files under 10MB."""
        file_size_mb = 5.0
        result = validator.validate_file_size(file_size_mb, "free")
        assert result.is_valid

    def test_free_tier_rejects_large_file(self, validator):
        """Test free tier rejects files over 10MB."""
        file_size_mb = 15.0
        result = validator.validate_file_size(file_size_mb, "free")
        assert not result.is_valid
        assert result.error_code == "FILE_TOO_LARGE"
        assert "15.00MB" in result.error_message
        assert "10MB" in result.error_message

    def test_pro_tier_accepts_30mb_file(self, validator):
        """Test pro tier accepts files under 50MB."""
        file_size_mb = 30.0
        result = validator.validate_file_size(file_size_mb, "pro")
        assert result.is_valid

    def test_pro_tier_rejects_60mb_file(self, validator):
        """Test pro tier rejects files over 50MB."""
        file_size_mb = 60.0
        result = validator.validate_file_size(file_size_mb, "pro")
        assert not result.is_valid
        assert result.error_code == "FILE_TOO_LARGE"

    def test_enterprise_tier_accepts_150mb_file(self, validator):
        """Test enterprise tier accepts files under 200MB."""
        file_size_mb = 150.0
        result = validator.validate_file_size(file_size_mb, "enterprise")
        assert result.is_valid

    def test_enterprise_tier_rejects_250mb_file(self, validator):
        """Test enterprise tier rejects files over 200MB."""
        file_size_mb = 250.0
        result = validator.validate_file_size(file_size_mb, "enterprise")
        assert not result.is_valid


# Storage Quota Tests
class TestStorageQuotaValidation:
    """Test storage quota enforcement."""

    @pytest.mark.asyncio
    async def test_accepts_when_under_quota(self, validator, mock_db):
        """Test upload allowed when under storage quota."""
        # Mock current usage: 50MB
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 50 * 1024 * 1024))

        result = await validator.validate_storage_quota(
            user_id="user123",
            workspace_id="workspace123",
            new_file_size_mb=10.0,
            subscription_tier="free"
        )
        assert result.is_valid
        assert result.current_storage_mb == 50.0

    @pytest.mark.asyncio
    async def test_rejects_when_over_quota(self, validator, mock_db):
        """Test upload rejected when exceeding storage quota."""
        # Mock current usage: 95MB (free tier limit is 100MB)
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 95 * 1024 * 1024))

        result = await validator.validate_storage_quota(
            user_id="user123",
            workspace_id="workspace123",
            new_file_size_mb=10.0,  # Would put total at 105MB
            subscription_tier="free"
        )
        assert not result.is_valid
        assert result.error_code == "STORAGE_QUOTA_EXCEEDED"
        assert "95.00MB" in result.error_message
        assert "100MB" in result.error_message

    @pytest.mark.asyncio
    async def test_pro_tier_higher_quota(self, validator, mock_db):
        """Test pro tier has higher storage quota."""
        # Mock current usage: 500MB
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 500 * 1024 * 1024))

        result = await validator.validate_storage_quota(
            user_id="user123",
            workspace_id="workspace123",
            new_file_size_mb=100.0,
            subscription_tier="pro"  # 1GB limit
        )
        assert result.is_valid  # 600MB < 1024MB

    @pytest.mark.asyncio
    async def test_soft_deleted_files_excluded_from_quota(self, validator, mock_db):
        """Test that soft-deleted files do not count toward storage quota."""
        # Mock: 50MB of active files (soft-deleted files should be excluded by query)
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 50 * 1024 * 1024))

        result = await validator.validate_storage_quota(
            user_id="user123",
            workspace_id="workspace123",
            new_file_size_mb=40.0,
            subscription_tier="free"  # 100MB limit
        )
        assert result.is_valid  # 50MB + 40MB = 90MB < 100MB limit

        # Verify the query was constructed with deleted_at filter
        call_args = mock_db.execute.call_args
        # The SQL statement should contain a WHERE clause filtering deleted_at IS NULL
        stmt = call_args[0][0]
        compiled = str(stmt.compile())
        assert "deleted_at IS NULL" in compiled or "deleted_at" in compiled


# Virus Scanning Tests (Mocked)
class TestVirusScanningValidation:
    """Test virus scanning integration."""

    @pytest.mark.asyncio
    async def test_clean_file_passes_clamav(self, validator, mock_settings):
        """Test clean file passes ClamAV scan."""
        mock_settings.virus_scanning_enabled = True
        mock_settings.VIRUS_SCAN_METHOD = "clamav"

        with patch('subprocess.run') as mock_run:
            # ClamAV returns 0 for clean files
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = await validator.scan_for_viruses(b"clean file content", "test.txt")
            assert result.is_valid

    @pytest.mark.asyncio
    async def test_infected_file_rejected_clamav(self, validator, mock_settings):
        """Test infected file rejected by ClamAV."""
        mock_settings.virus_scanning_enabled = True
        mock_settings.VIRUS_SCAN_METHOD = "clamav"

        with patch('subprocess.run') as mock_run:
            # ClamAV returns 1 for infected files
            mock_run.return_value = MagicMock(returncode=1, stderr="")

            result = await validator.scan_for_viruses(b"EICAR test virus", "virus.txt")
            assert not result.is_valid
            assert result.error_code == "VIRUS_DETECTED"

    @pytest.mark.asyncio
    async def test_scanner_error_fails_closed_by_default(self, validator, mock_settings):
        """Test that scanner errors fail closed (reject upload) by default."""
        mock_settings.virus_scanning_enabled = True
        mock_settings.VIRUS_SCAN_METHOD = "clamav"
        mock_settings.VIRUS_SCAN_FAIL_BEHAVIOR = "closed"

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("clamdscan not found")

            result = await validator.scan_for_viruses(b"file content", "test.txt")
            assert not result.is_valid
            assert result.error_code == "SCAN_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_scanner_error_fails_open_when_configured(self, validator, mock_settings):
        """Test that scanner errors fail open when explicitly configured."""
        mock_settings.virus_scanning_enabled = True
        mock_settings.VIRUS_SCAN_METHOD = "clamav"
        mock_settings.VIRUS_SCAN_FAIL_BEHAVIOR = "open"

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("clamdscan not found")

            result = await validator.scan_for_viruses(b"file content", "test.txt")
            assert result.is_valid  # Fails open when explicitly configured

    @pytest.mark.asyncio
    async def test_virustotal_missing_key_fails_closed(self, validator, mock_settings):
        """Test that missing VirusTotal API key fails closed by default."""
        mock_settings.virus_scanning_enabled = True
        mock_settings.VIRUS_SCAN_METHOD = "virustotal"
        mock_settings.VIRUSTOTAL_API_KEY = None
        mock_settings.VIRUS_SCAN_FAIL_BEHAVIOR = "closed"

        result = await validator.scan_for_viruses(b"file content", "test.txt")
        assert not result.is_valid
        assert result.error_code == "SCAN_UNAVAILABLE"


# Integration Tests
class TestFullValidationPipeline:
    """Test complete validation workflow."""

    @pytest.mark.asyncio
    async def test_valid_file_passes_all_checks(self, validator, mock_db):
        """Test that valid file passes all validation checks."""
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 0))

        # JPEG file, 5MB
        jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * (5 * 1024 * 1024)

        result = await validator.validate_upload(
            file_bytes=jpeg_bytes,
            filename="photo.jpg",
            user_id="user123",
            workspace_id="workspace123",
            subscription_tier="free"
        )
        assert result.is_valid

    @pytest.mark.asyncio
    async def test_invalid_mime_type_fails(self, validator, mock_db):
        """Test that invalid MIME type fails validation."""
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 0))

        # Random binary data
        result = await validator.validate_upload(
            file_bytes=b'\x00\x01\x02\x03',
            filename="unknown.bin",
            user_id="user123",
            workspace_id="workspace123",
            subscription_tier="free"
        )
        assert not result.is_valid
        assert "UNKNOWN_FILE_TYPE" in (result.error_code or "")

    @pytest.mark.asyncio
    async def test_oversized_file_fails(self, validator, mock_db):
        """Test that oversized file fails validation."""
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 0))

        # JPEG file, 20MB (exceeds free tier 10MB limit)
        jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * (20 * 1024 * 1024)

        result = await validator.validate_upload(
            file_bytes=jpeg_bytes,
            filename="huge.jpg",
            user_id="user123",
            workspace_id="workspace123",
            subscription_tier="free"
        )
        assert not result.is_valid
        assert result.error_code == "FILE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_quota_exceeded_fails(self, validator, mock_db):
        """Test that quota exceeded fails validation."""
        # Mock: user already using 98MB of 100MB quota
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 98 * 1024 * 1024))

        # JPEG file, 5MB (would exceed quota)
        jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * (5 * 1024 * 1024)

        result = await validator.validate_upload(
            file_bytes=jpeg_bytes,
            filename="photo.jpg",
            user_id="user123",
            workspace_id="workspace123",
            subscription_tier="free"
        )
        assert not result.is_valid
        assert result.error_code == "STORAGE_QUOTA_EXCEEDED"
