from pydantic import BaseModel, Field

class EEATTrustScore(BaseModel):
    """E-E-A-T and Credibility evaluation results."""
    score: float = Field(description="Overall trust score (0-100)")
    author_credibility: float = Field(description="Verified author identity, bio, and historical reputation")
    expertise: float = Field(description="Depth of knowledge and credentials shown in the content")
    authority: float = Field(description="Domain authority and external mentions of the topic")
    trustworthiness: float = Field(description="Transparency, safety, and reliability of the platform")
    citations_references: float = Field(description="Quality and quantity of external links and expert citations")
    content_accuracy: float = Field(description="Fact-checking against known reliable sources")
    freshness: float = Field(description="How up-to-date the information and data points are")
    transparency: float = Field(description="Clear disclosures, affiliate links transparency, and contact info")
    spam_signals: float = Field(description="Absence of aggressive ads, manipulative links, or duplicate content (0 = high spam, 100 = clean)")
    technical_trust: float = Field(description="HTTPS, mobile-friendliness, and site security signals")
    reasoning: str = Field(description="Brief explanation of the scores provided")
