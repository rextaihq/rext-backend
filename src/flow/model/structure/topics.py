from pydantic import BaseModel, Field, conlist


class SEOTopics(BaseModel):
    topics: conlist(str, min_length=5, max_length=5) = Field(
        description="Exactly five topics related to the given topic"
    )
