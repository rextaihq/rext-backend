# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class ContactUsOutline(BaseOutline):
#     """Outline for a contact page or guide."""
#     company_name: str = Field(description="The company being contacted.")
#     contact_methods: List[str] = Field(description="Channels available (e.g., 'Email', 'Phone', 'Live Chat').")
#     expected_response_time: Optional[str] = Field(description="When the user can expect a reply.")
#     office_locations: Optional[List[str]] = Field(description="Physical addresses, if applicable.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO SECTION (CLARITY + REDUCES FRUSTRATION)
# -------------------------

class ContactHero(BaseModel):
    headline: str = Field(description="Clear reassurance-driven headline")
    subheadline: str = Field(description="Sets expectation: who to contact and how fast response is")

    response_time_sla: Optional[str] = Field(
        default=None,
        description="e.g., 'We respond within 24 hours'"
    )

    primary_cta: str = Field(default="Send Message")


# -------------------------
# CONTACT INTENT ROUTING (2026 CRITICAL FEATURE)
# -------------------------

class ContactReason(BaseModel):
    reason: str = Field(description="Why user is contacting (support, sales, partnership, etc.)")
    route_to: str = Field(description="Internal routing destination (team or system)")
    expected_response_time: Optional[str]


class ContactRouting(BaseModel):
    options: List[ContactReason]


# -------------------------
# CONTACT CHANNELS (MULTI-CHANNEL REALITY)
# -------------------------

class ContactChannels(BaseModel):
    email: Optional[str]
    phone: Optional[str]
    live_chat_available: bool = False
    whatsapp: Optional[str]
    social_links: Optional[List[str]] = Field(default_factory=list)
    support_portal: Optional[str]


# -------------------------
# CONTACT FORM (REDUCED FRICTION DESIGN)
# -------------------------

class ContactField(BaseModel):
    field_name: str
    field_type: Literal[
        "text", "email", "phone", "textarea", "dropdown", "checkbox"
    ]
    required: bool
    placeholder: Optional[str] = None


class ContactForm(BaseModel):
    fields: List[ContactField]
    auto_classification_enabled: bool = Field(
        default=True,
        description="AI classifies request type automatically"
    )
    file_upload_enabled: Optional[bool] = False


# -------------------------
# SUPPORT EXPECTATION SYSTEM
# -------------------------

class SupportExpectations(BaseModel):
    sla_by_type: List[ContactReason]
    availability_hours: Optional[str]
    timezone: Optional[str]


# -------------------------
# LOCATION / COMPANY INFO
# -------------------------

class CompanyLocation(BaseModel):
    office_locations: Optional[List[str]]
    map_link: Optional[str]


# -------------------------
# TRUST LAYER
# -------------------------

class TrustSignals(BaseModel):
    security_notes: Optional[List[str]] = Field(
        default_factory=list,
        description="Spam protection, encryption, GDPR compliance"
    )
    response_reliability: Optional[str]
    customer_satisfaction_metrics: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# FAQ (CONTACT-SPECIFIC)
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class ContactFAQ(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# CTA SYSTEM (LOW FRICTION)
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default=None,
        description="e.g., 'No spam. We reply fast.'"
    )


# -------------------------
# FINAL CONTACT US PAGE SCHEMA
# -------------------------

class ContactUsOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Friendly", "Professional", "Reassuring",
        "Conversational", "Helpful", "Direct"
    ]

    # Intent classification
    contact_intent_types: List[str] = Field(
        description="e.g., support, sales, billing, partnership, media"
    )

    # Page Structure (routing-first model)
    hero: ContactHero
    routing: ContactRouting
    channels: ContactChannels
    form: ContactForm
    expectations: SupportExpectations
    location: Optional[CompanyLocation]

    # Trust + reassurance
    trust: TrustSignals

    # FAQ
    faq: Optional[ContactFAQ]

    # CTA layer
    cta: CTASection

    # Optimization Layer (2026 support systems)
    auto_ticket_creation: bool = Field(
        default=True,
        description="Automatically converts form submission into support ticket"
    )

    ai_response_suggestion: bool = Field(
        default=True,
        description="AI suggests responses or routes query intelligently"
    )

    target_time_to_contact_seconds: Optional[int] = Field(
        default=90,
        description="Ideal time for user to successfully initiate contact"
    )

    target_word_count: int = Field(
        default=500,
        ge=200,
        le=1500,
        description="Contact pages are ultra-light UX pages"
    )