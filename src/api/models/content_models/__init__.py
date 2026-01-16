from .content import Content
from .content_progress import ContentProgress
from .content_seo_data import ContentSEOData
from .content_review import ContentReview
from .content_version import ContentVersion
from .connected_site import ConnectedSite
from .content_media import ContentMedia

# Deprecated models (consolidated into Content.metadata_json, tracking_json, etc.)
# These are kept for backward compatibility during migration but will be removed
try:
    from .content_metadata import ContentMetadata
    from .content_ai_config import ContentAIConfig
    from .content_structure import ContentStructure
    from .content_research_config import ContentResearchConfig
    from .content_tracking import ContentTracking
    _deprecated_models_available = True
except ImportError:
    # Tables dropped after migration 40fd95ca1e8d
    ContentMetadata = None
    ContentAIConfig = None
    ContentStructure = None
    ContentResearchConfig = None
    ContentTracking = None
    _deprecated_models_available = False

__all__ = [
    "Content",
    "ContentProgress",
    "ContentSEOData",
    "ContentReview",
    "ContentVersion",
    "ConnectedSite",
    "ContentMedia",
    # Deprecated (use Content.metadata_json, tracking_json, ai_config_json, structure_json, research_config_json instead)
    "ContentMetadata",
    "ContentAIConfig",
    "ContentStructure",
    "ContentResearchConfig",
    "ContentTracking",
]
