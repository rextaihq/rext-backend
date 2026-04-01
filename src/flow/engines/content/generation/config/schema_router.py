from src.flow.engines.content.generation.config.outline_schemas import (
    ComparisonOutline,
    ConversionOutline,
    InformationalOutline,
    ListOutline,
)


PATTERN_TO_SCHEMA = {
    "educational": InformationalOutline,
    "list": ListOutline,
    "comparison": ComparisonOutline,
    "conversion": ConversionOutline,
    "proof": InformationalOutline,
    "navigational": ConversionOutline,
}
