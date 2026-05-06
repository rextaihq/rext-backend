# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class CheckoutPageOutline(BaseOutline):
#     """Outline for an e-commerce checkout flow page."""
#     store_name: str = Field(description="The generic or specific store name.")
#     trust_signals: List[str] = Field(description="E.g., 'Norton Secured', 'Money-back Guarantee'.")
#     accepted_payment_methods: List[str] = Field(description="E.g., 'Visa', 'PayPal', 'Crypto'.")
#     upsell_or_cross_sell: Optional[str] = Field(description="Any 'Frequently bought together' item.")


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# Core UI Blocks
# -------------------------

class OrderItem(BaseModel):
    name: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)
    total_price: float = Field(ge=0)


class PricingBreakdown(BaseModel):
    subtotal: float = Field(ge=0)
    discount: Optional[float] = Field(default=0)
    tax: Optional[float] = Field(default=0)
    shipping: Optional[float] = Field(default=0)
    total: float = Field(ge=0)


class OrderSummary(BaseModel):
    items: List[OrderItem]
    pricing: PricingBreakdown
    currency: str = Field(description="ISO currency code (e.g., USD, PKR)")


# -------------------------
# User Input Sections
# -------------------------

class CustomerInfo(BaseModel):
    email: str
    phone: Optional[str]


class Address(BaseModel):
    full_name: str
    address_line1: str
    address_line2: Optional[str]
    city: str
    state: Optional[str]
    postal_code: str
    country: str


class ShippingSection(BaseModel):
    required: bool = True
    address: Address
    delivery_options: Optional[List[str]] = Field(
        default_factory=list,
        description="e.g., Standard, Express"
    )


class BillingSection(BaseModel):
    same_as_shipping: bool = True
    billing_address: Optional[Address]


# -------------------------
# Payment Layer
# -------------------------

class PaymentMethod(BaseModel):
    method_type: Literal[
        "card", "paypal", "bank_transfer", "wallet", "cod"
    ]
    provider: Optional[str] = Field(description="Stripe, PayPal, etc.")


class PaymentSection(BaseModel):
    available_methods: List[PaymentMethod]
    default_method: Optional[str]
    save_payment_option: Optional[bool] = False


# -------------------------
# Trust & Compliance
# -------------------------

class TrustSignals(BaseModel):
    security_badges: List[str] = Field(
        description="SSL, PCI-DSS, payment logos"
    )
    guarantees: Optional[List[str]] = Field(
        default_factory=list,
        description="Money-back, secure checkout"
    )
    testimonials_snippet: Optional[List[str]] = []


class LegalSection(BaseModel):
    terms_url: str
    privacy_url: str
    refund_policy_url: Optional[str]


# -------------------------
# UX / Conversion Optimization
# -------------------------

class CTASection(BaseModel):
    primary_cta: str = Field(
        description="e.g., 'Complete Purchase'"
    )
    loading_text: Optional[str] = Field(
        default="Processing..."
    )


class ErrorHandling(BaseModel):
    inline_validation: bool = True
    error_messages: List[str]


class CheckoutFlow(BaseModel):
    type: Literal["one-page", "multi-step"]
    steps: Optional[List[str]] = Field(
        default_factory=list,
        description="Used if multi-step (e.g., Info → Shipping → Payment)"
    )


# -------------------------
# Main Schema
# -------------------------

class CheckoutPageOutline(BaseModel):
    # Core Metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    conversion_goal: Literal[
        "complete_purchase", "start_subscription", "confirm_order"
    ]
    
    # Flow
    checkout_flow: CheckoutFlow
    
    # Sections
    order_summary: OrderSummary
    customer_info: CustomerInfo
    shipping: Optional[ShippingSection]
    billing: BillingSection
    payment: PaymentSection
    
    # Trust Layer
    trust: TrustSignals
    legal: LegalSection
    
    # UX Enhancements
    cta: CTASection
    error_handling: ErrorHandling
    
    # Optimization
    abandoned_cart_recovery: Optional[bool] = False
    coupon_field_enabled: Optional[bool] = True
    
    # Analytics / Tracking (important in 2026)
    tracking_events: Optional[List[str]] = Field(
        default_factory=list,
        description="e.g., add_payment_info, purchase"
    )