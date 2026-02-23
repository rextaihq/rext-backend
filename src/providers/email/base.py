"""
Email Provider Interface

Abstract base class for all email providers.
Implements provider abstraction pattern for easy switching between email services.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from src.utils.datetime_utils import utc_now


@dataclass
class EmailRecipient:
    """Email recipient information"""
    email: str
    name: Optional[str] = None

    def __post_init__(self):
        """Validate email format"""
        if not self.email or "@" not in self.email:
            raise ValueError(f"Invalid email address: {self.email}")


@dataclass
class EmailMessage:
    """
    Email message structure.
    
    Represents a complete email with all necessary fields for sending.
    """
    to: List[EmailRecipient]
    subject: str
    html: str
    from_email: str
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    cc: Optional[List[EmailRecipient]] = None
    bcc: Optional[List[EmailRecipient]] = None
    tags: Optional[Dict[str, str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None

    def __post_init__(self):
        """Validate message fields"""
        if not self.to:
            raise ValueError("At least one recipient is required")
        if not self.subject:
            raise ValueError("Subject is required")
        if not self.html:
            raise ValueError("HTML content is required")
        if not self.from_email or "@" not in self.from_email:
            raise ValueError(f"Invalid from_email: {self.from_email}")


@dataclass
class EmailResult:
    """
    Result of email send operation.
    
    Contains success status, provider message ID, and error information if any.
    """
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    provider_response: Optional[Dict[str, Any]] = None
    sent_at: Optional[datetime] = field(default_factory=utc_now)

    def __repr__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"<EmailResult({status}, message_id={self.message_id})>"


class IEmailProvider(ABC):
    """
    Abstract interface for email providers.
    
    All email provider implementations (Resend, SMTP, Mock) must implement this interface.
    This enables easy switching between providers and testing.
    """

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> EmailResult:
        """
        Send a single email.
        
        Args:
            message: EmailMessage object with all email details
            
        Returns:
            EmailResult with success status and provider response
            
        Raises:
            Exception: If send fails and can't be handled gracefully
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Get the provider name (e.g., 'resend', 'smtp', 'mock').
        
        Returns:
            String identifier for this provider
        """
        pass

    @abstractmethod
    async def verify_connection(self) -> bool:
        """
        Verify provider connection and credentials.
        
        Returns:
            True if connection is valid, False otherwise
        """
        pass

    def supports_feature(self, feature: str) -> bool:
        """
        Check if provider supports a specific feature.
        
        Args:
            feature: Feature name (e.g., 'webhooks', 'attachments', 'templates')
            
        Returns:
            True if feature is supported, False otherwise
        """
        # Default implementation - providers can override
        supported_features = {'basic_email'}
        return feature in supported_features
