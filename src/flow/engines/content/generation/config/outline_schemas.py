# src/models/outline_schemas.py

class BaseSection(BaseModel):
    section_type: str
    heading: str
    heading_level: Literal["H1", "H2", "H3"]
    description: str
    key_points: List[str]
    content_format: Optional[str]


class InformationalOutline(BaseModel):
    title: str
    sections: List[BaseSection]
    faqs: List[str]


class ListOutline(BaseModel):
    title: str
    sections: List[BaseSection]


class ComparisonOutline(BaseModel):
    title: str
    sections: List[BaseSection]


class ConversionOutline(BaseModel):
    title: str
    sections: List[BaseSection]
    primary_cta: str