"""
File Security Module

Provides comprehensive file upload security including:
- MIME type validation
- Virus scanning (ClamAV/VirusTotal)
- Subscription tier limit enforcement
- Storage quota management

Usage:
    from src.utils.file_security import FileSecurityValidator

    validator = FileSecurityValidator(db_session, settings)
    result = await validator.validate_upload(file_bytes, filename, user_id, workspace_id)
    if not result.is_valid:
        raise ValidationError(result.error_message)
"""

import io
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path

import filetype
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import Settings
from src.api.models.media_models.media import Media

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of file security validation."""
    is_valid: bool
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    current_storage_mb: Optional[float] = None
    file_size_mb: Optional[float] = None


class FileSecurityValidator:
    """
    Comprehensive file security validator.

    Validates files against:
    - MIME type whitelist
    - Subscription tier limits (file size, storage quota)
    - Virus scanning (optional)
    """

    def __init__(self, db: AsyncSession, settings: Settings):
        """
        Initialize validator.

        Args:
            db: Database session for quota queries
            settings: Application settings with security config
        """
        self.db = db
        self.settings = settings
        self.allowed_mime_types = settings.allowed_mime_types_list

    def _scan_unavailable_result(self, reason: str, filename: str) -> ValidationResult:
        """
        Return appropriate result when virus scanning is unavailable.

        In fail-closed mode (production default), rejects the upload.
        In fail-open mode (development), allows the upload with a warning.

        Args:
            reason: Why the scan failed (for logging)
            filename: Original filename (for logging)

        Returns:
            ValidationResult based on fail behavior setting
        """
        fail_behavior = getattr(self.settings, 'VIRUS_SCAN_FAIL_BEHAVIOR', 'closed').lower()

        if fail_behavior == "open":
            logger.warning(
                f"Virus scan unavailable (fail-open mode) for {filename}: {reason}. "
                f"Upload allowed without scan."
            )
            return ValidationResult(is_valid=True)

        logger.error(
            f"Virus scan unavailable (fail-closed mode) for {filename}: {reason}. "
            f"Upload rejected for security."
        )
        return ValidationResult(
            is_valid=False,
            error_message="File upload temporarily unavailable. Virus scanning service is not responding. Please try again later.",
            error_code="SCAN_UNAVAILABLE"
        )

    async def validate_upload(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        workspace_id: Optional[str] = None,
        subscription_tier: str = "free"
    ) -> ValidationResult:
        """
        Comprehensive file upload validation.

        Args:
            file_bytes: File content as bytes
            filename: Original filename
            user_id: User ID performing upload
            workspace_id: Optional workspace context
            subscription_tier: User's subscription tier (free/pro/enterprise)

        Returns:
            ValidationResult with is_valid and error details
        """
        file_size_bytes = len(file_bytes)
        file_size_mb = file_size_bytes / (1024 * 1024)

        # Step 1: Validate MIME type
        mime_result = self.validate_mime_type(file_bytes, filename)
        if not mime_result.is_valid:
            return mime_result

        # Step 2: Check file size against tier limit
        size_result = self.validate_file_size(file_size_mb, subscription_tier)
        if not size_result.is_valid:
            return size_result

        # Step 3: Check storage quota
        quota_result = await self.validate_storage_quota(
            user_id, workspace_id, file_size_mb, subscription_tier
        )
        if not quota_result.is_valid:
            return quota_result

        # Step 4: Virus scan (if enabled)
        if self.settings.virus_scanning_enabled:
            virus_result = await self.scan_for_viruses(file_bytes, filename)
            if not virus_result.is_valid:
                return virus_result

        # All checks passed
        return ValidationResult(
            is_valid=True,
            file_size_mb=file_size_mb,
            current_storage_mb=quota_result.current_storage_mb
        )

    def validate_mime_type(self, file_bytes: bytes, filename: str) -> ValidationResult:
        """
        Validate file MIME type against whitelist.

        Uses filetype library to detect actual MIME type from file content
        (not trusting client-provided Content-Type header).

        Args:
            file_bytes: File content
            filename: Original filename for logging

        Returns:
            ValidationResult
        """
        # Detect MIME type from file content
        kind = filetype.guess(file_bytes)

        if kind is None:
            # filetype couldn't detect type - could be text file
            # Check if it's likely a text file
            try:
                file_bytes[:1024].decode('utf-8')
                # Looks like UTF-8 text
                if filename.endswith(('.txt', '.md', '.markdown')):
                    detected_mime = 'text/plain' if filename.endswith('.txt') else 'text/markdown'
                else:
                    logger.warning(f"Could not detect MIME type for: {filename}")
                    return ValidationResult(
                        is_valid=False,
                        error_message="Unable to determine file type. Please upload a supported file format.",
                        error_code="UNKNOWN_FILE_TYPE"
                    )
            except UnicodeDecodeError:
                logger.warning(f"Could not detect MIME type and not UTF-8 text: {filename}")
                return ValidationResult(
                    is_valid=False,
                    error_message="Unable to determine file type. Please upload a supported file format.",
                    error_code="UNKNOWN_FILE_TYPE"
                )
        else:
            detected_mime = kind.mime

        # Check against whitelist
        if detected_mime not in self.allowed_mime_types:
            logger.warning(
                f"Blocked file upload: {filename} - "
                f"MIME type {detected_mime} not in whitelist"
            )
            return ValidationResult(
                is_valid=False,
                error_message=f"File type '{detected_mime}' is not allowed. "
                             f"Allowed types: {', '.join(self.allowed_mime_types)}",
                error_code="INVALID_MIME_TYPE"
            )

        logger.info(f"MIME type validation passed: {filename} ({detected_mime})")
        return ValidationResult(is_valid=True)

    def validate_file_size(self, file_size_mb: float, subscription_tier: str) -> ValidationResult:
        """
        Validate file size against subscription tier limit.

        Args:
            file_size_mb: File size in megabytes
            subscription_tier: User's subscription tier

        Returns:
            ValidationResult
        """
        max_size_mb = self.settings.get_tier_file_size_limit(subscription_tier)

        if file_size_mb > max_size_mb:
            logger.warning(
                f"File size {file_size_mb:.2f}MB exceeds {subscription_tier} tier "
                f"limit of {max_size_mb}MB"
            )
            return ValidationResult(
                is_valid=False,
                error_message=f"File size ({file_size_mb:.2f}MB) exceeds your tier limit ({max_size_mb}MB). "
                             f"Upgrade to upload larger files.",
                error_code="FILE_TOO_LARGE",
                file_size_mb=file_size_mb
            )

        return ValidationResult(is_valid=True, file_size_mb=file_size_mb)

    async def validate_storage_quota(
        self,
        user_id: str,
        workspace_id: Optional[str],
        new_file_size_mb: float,
        subscription_tier: str
    ) -> ValidationResult:
        """
        Validate storage quota against subscription tier limit.

        Queries current storage usage and checks if new file would exceed limit.

        Args:
            user_id: User ID
            workspace_id: Optional workspace ID
            new_file_size_mb: Size of new file in MB
            subscription_tier: User's subscription tier

        Returns:
            ValidationResult with current_storage_mb
        """
        # Query current storage usage
        stmt = select(func.sum(Media.file_size)).where(
            Media.user_id == user_id,
            Media.deleted_at.is_(None)
        )
        if workspace_id:
            stmt = stmt.where(Media.workspace_id == workspace_id)

        result = await self.db.execute(stmt)
        total_bytes = result.scalar() or 0
        # Convert Decimal to float to avoid type errors in arithmetic operations
        current_storage_mb = float(total_bytes) / (1024 * 1024)

        # Get tier storage limit
        max_storage_mb = self.settings.get_tier_storage_limit(subscription_tier)

        # Check if new file would exceed limit
        projected_storage_mb = current_storage_mb + new_file_size_mb

        if projected_storage_mb > max_storage_mb:
            logger.warning(
                f"Storage quota exceeded: current={current_storage_mb:.2f}MB, "
                f"new_file={new_file_size_mb:.2f}MB, limit={max_storage_mb}MB"
            )
            return ValidationResult(
                is_valid=False,
                error_message=f"Storage quota exceeded. You're using {current_storage_mb:.2f}MB "
                             f"of {max_storage_mb}MB. This file would put you at "
                             f"{projected_storage_mb:.2f}MB. Upgrade for more storage.",
                error_code="STORAGE_QUOTA_EXCEEDED",
                current_storage_mb=current_storage_mb,
                file_size_mb=new_file_size_mb
            )

        logger.info(
            f"Storage quota check passed: {projected_storage_mb:.2f}MB / {max_storage_mb}MB"
        )
        return ValidationResult(
            is_valid=True,
            current_storage_mb=current_storage_mb,
            file_size_mb=new_file_size_mb
        )

    async def scan_for_viruses(self, file_bytes: bytes, filename: str) -> ValidationResult:
        """
        Scan file for viruses using configured method.

        Args:
            file_bytes: File content
            filename: Original filename for logging

        Returns:
            ValidationResult
        """
        method = self.settings.VIRUS_SCAN_METHOD.lower()

        if method == "clamav":
            return await self._scan_clamav(file_bytes, filename)
        elif method == "virustotal":
            return await self._scan_virustotal(file_bytes, filename)
        else:
            logger.error(f"Unknown virus scan method: {method}")
            return self._scan_unavailable_result(
                f"Unknown virus scan method: {method}",
                filename
            )

    async def _scan_clamav(self, file_bytes: bytes, filename: str) -> ValidationResult:
        """
        Scan file using ClamAV daemon.

        Args:
            file_bytes: File content
            filename: Original filename

        Returns:
            ValidationResult
        """
        try:
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(file_bytes)
                tmp_file_path = tmp_file.name

            try:
                result = subprocess.run(
                    ['clamdscan', '--no-summary', tmp_file_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    logger.info(f"ClamAV scan passed: {filename}")
                    return ValidationResult(is_valid=True)
                elif result.returncode == 1:
                    logger.error(f"ClamAV detected virus in: {filename}")
                    return ValidationResult(
                        is_valid=False,
                        error_message="File failed virus scan. Upload blocked for security.",
                        error_code="VIRUS_DETECTED"
                    )
                else:
                    logger.error(f"ClamAV scan error (return code {result.returncode}): {result.stderr}")
                    return self._scan_unavailable_result(
                        f"ClamAV returned unexpected code {result.returncode}: {result.stderr}",
                        filename
                    )

            finally:
                Path(tmp_file_path).unlink(missing_ok=True)

        except FileNotFoundError:
            logger.error("clamdscan command not found. ClamAV not installed or not in PATH.")
            return self._scan_unavailable_result("clamdscan binary not found", filename)
        except subprocess.TimeoutExpired:
            logger.error(f"ClamAV scan timeout for: {filename}")
            return self._scan_unavailable_result("ClamAV scan timed out after 30s", filename)
        except Exception as e:
            logger.error(f"ClamAV scan error: {e}", exc_info=True)
            return self._scan_unavailable_result(f"ClamAV error: {e}", filename)

    async def _scan_virustotal(self, file_bytes: bytes, filename: str) -> ValidationResult:
        """
        Scan file using VirusTotal API.

        Args:
            file_bytes: File content
            filename: Original filename

        Returns:
            ValidationResult
        """
        if not self.settings.VIRUSTOTAL_API_KEY:
            logger.error("VirusTotal API key not configured")
            return self._scan_unavailable_result("VirusTotal API key not configured", filename)

        try:
            url = "https://www.virustotal.com/api/v3/files"
            headers = {"x-apikey": self.settings.VIRUSTOTAL_API_KEY}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, headers=headers,
                    files={"file": (filename, io.BytesIO(file_bytes))},
                    timeout=30
                )

                if response.status_code != 200:
                    logger.error(f"VirusTotal API error: {response.status_code} - {response.text}")
                    return self._scan_unavailable_result(
                        f"VirusTotal API returned {response.status_code}",
                        filename
                    )

                data = response.json()
                analysis_id = data.get("data", {}).get("id")

                if not analysis_id:
                    logger.error("VirusTotal: No analysis ID in response")
                    return self._scan_unavailable_result(
                        "VirusTotal returned no analysis ID",
                        filename
                    )

                analysis_url = f"https://www.virustotal.com/api/v3/analyses/{analysis_id}"
                analysis_response = await client.get(analysis_url, headers=headers, timeout=30)

                if analysis_response.status_code != 200:
                    logger.error(f"VirusTotal analysis error: {analysis_response.status_code}")
                    return self._scan_unavailable_result(
                        f"VirusTotal analysis fetch returned {analysis_response.status_code}",
                        filename
                    )

            analysis_data = analysis_response.json()
            stats = analysis_data.get("data", {}).get("attributes", {}).get("stats", {})
            malicious_count = stats.get("malicious", 0)

            if malicious_count > 0:
                logger.error(f"VirusTotal detected malware in: {filename} ({malicious_count} engines)")
                return ValidationResult(
                    is_valid=False,
                    error_message="File failed virus scan. Upload blocked for security.",
                    error_code="VIRUS_DETECTED"
                )

            logger.info(f"VirusTotal scan passed: {filename}")
            return ValidationResult(is_valid=True)

        except httpx.HTTPError as e:
            logger.error(f"VirusTotal API request error: {e}", exc_info=True)
            return self._scan_unavailable_result(f"VirusTotal HTTP error: {e}", filename)
        except Exception as e:
            logger.error(f"VirusTotal scan error: {e}", exc_info=True)
            return self._scan_unavailable_result(f"VirusTotal error: {e}", filename)


# Convenience function for quick validation
async def validate_file_upload(
    db: AsyncSession,
    settings: Settings,
    file_bytes: bytes,
    filename: str,
    user_id: str,
    workspace_id: Optional[str] = None,
    subscription_tier: str = "free"
) -> ValidationResult:
    """
    Convenience function for file upload validation.

    Args:
        db: Database session
        settings: Application settings
        file_bytes: File content
        filename: Original filename
        user_id: User ID
        workspace_id: Optional workspace ID
        subscription_tier: Subscription tier

    Returns:
        ValidationResult
    """
    validator = FileSecurityValidator(db, settings)
    return await validator.validate_upload(
        file_bytes, filename, user_id, workspace_id, subscription_tier
    )
