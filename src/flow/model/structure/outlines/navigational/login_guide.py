# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class LoginGuideOutline(BaseOutline):
#     """Outline for a guide directing users on how to log in or access their accounts."""
#     platform_name: str = Field(description="The platform the user is trying to access.")
#     common_login_issues: List[str] = Field(description="List of issues like 'Forgot Password' or '2FA Failures'.")
#     support_contact_included: bool = Field(default=True, description="Whether to include a link to actual support.")


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / ACCESS ENTRY
# -------------------------


class LoginHero(BaseModel):
    headline: str = Field(description="Clear instruction: how to access the system")
    subheadline: str = Field(description="Explains login methods and supported options")

    primary_cta: str = Field(default="Login")
    secondary_cta: Optional[str] = Field(
        default="Create Account", description="Optional fallback for new users"
    )

    supported_methods: List[str] = Field(
        description="e.g., email/password, Google, Apple, SSO, passkey"
    )


# -------------------------
# AUTHENTICATION METHODS
# -------------------------


class AuthMethod(BaseModel):
    method_name: str
    description: str
    steps: List[str]


class AuthenticationSystem(BaseModel):
    methods: List[AuthMethod]


# -------------------------
# PASSWORDLESS & MODERN AUTH (2026 STANDARD)
# -------------------------


class ModernAuth(BaseModel):
    passwordless_login: bool = Field(default=True)
    magic_link_enabled: bool = Field(default=True)
    passkey_support: bool = Field(default=True)
    biometric_login: Optional[bool] = False


# -------------------------
# SSO / ENTERPRISE LOGIN
# -------------------------


class SSOProvider(BaseModel):
    name: str
    supported: bool
    setup_notes: Optional[str]


class SSOSystem(BaseModel):
    providers: List[SSOProvider]


# -------------------------
# TROUBLESHOOTING LOGIN ISSUES
# -------------------------


class LoginIssue(BaseModel):
    issue: str
    cause: Optional[str]
    solution_steps: List[str]


class LoginTroubleshooting(BaseModel):
    issues: List[LoginIssue]


# -------------------------
# ACCOUNT RECOVERY SYSTEM
# -------------------------


class AccountRecovery(BaseModel):
    forgot_password_flow: List[str]
    email_recovery_steps: List[str]
    account_unlock_steps: Optional[List[str]] = Field(default_factory=list)
    backup_codes_info: Optional[str]


# -------------------------
# SECURITY LAYER (CRITICAL IN 2026)
# -------------------------


class SecurityInfo(BaseModel):
    mfa_required: bool
    mfa_methods: Optional[List[str]] = Field(
        default_factory=list, description="Authenticator app, SMS, email OTP, hardware key"
    )
    suspicious_login_detection: Optional[bool] = True
    session_timeout_policy: Optional[str]


# -------------------------
# DEVICE & SESSION MANAGEMENT
# -------------------------


class DeviceSession(BaseModel):
    active_devices_view: Optional[bool] = True
    logout_all_devices: Optional[bool] = True
    session_duration: Optional[str]


# -------------------------
# ERROR STATES (LOGIN FAIL UX)
# -------------------------


class LoginError(BaseModel):
    error_type: str
    meaning: str
    resolution: List[str]


class LoginErrorHandling(BaseModel):
    errors: List[LoginError]


# -------------------------
# SUPPORT ESCALATION
# -------------------------


class SupportChannel(BaseModel):
    channel: Literal["live_chat", "email", "help_center", "ticket_system"]
    availability: Optional[str]
    response_time: Optional[str]


class LoginSupport(BaseModel):
    channels: List[SupportChannel]


# -------------------------
# CTA SYSTEM
# -------------------------


class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default="Secure login with encrypted authentication", description="Trust reinforcement"
    )


# -------------------------
# FINAL LOGIN GUIDE SCHEMA
# -------------------------


class LoginGuideOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page.",
    )

    target_audience: List[str]
    tone: Literal["Instructional", "Reassuring", "Clear", "Technical", "Supportive", "Neutral"]

    # Entry experience
    hero: LoginHero

    # Authentication system
    authentication: AuthenticationSystem

    # Modern login methods (2026 standard)
    modern_auth: ModernAuth

    # Enterprise login support
    sso: Optional[SSOSystem]

    # Security layer
    security: SecurityInfo

    # Device/session management
    sessions: DeviceSession

    # Recovery system (critical)
    account_recovery: AccountRecovery

    # Error handling
    error_handling: LoginErrorHandling

    # Troubleshooting
    troubleshooting: LoginTroubleshooting

    # Support escalation
    support: LoginSupport

    # CTA layer
    cta: CTASection

    # Optimization Layer (2026 auth UX standard)
    target_login_time_seconds: Optional[int] = Field(
        default=30, description="Ideal time to complete login successfully"
    )

    failed_login_recovery_success_rate_goal: Optional[str] = Field(
        default=">90%", description="Target recovery success rate after login failure"
    )

    auth_methods_priority: Optional[List[str]] = Field(
        default_factory=list,
        description="Preferred login methods order (e.g., passkey → SSO → password)",
    )

    target_word_count: int = Field(
        default=600, ge=300, le=2000, description="Login guides are ultra-compact utility pages"
    )
