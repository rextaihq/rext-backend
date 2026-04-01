from typing import Annotated

from pydantic import BaseModel, Field


class SEOTopics(BaseModel):
    topics: Annotated[
        list[str],
        Field(
            min_length=5,
            max_length=5,
            description="Exactly five SEO topics related to the given topic",
        ),
    ]
