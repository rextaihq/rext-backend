from pydantic import BaseModel, Field, conlist


class TopicPair(BaseModel):
    title: str = Field(description="The name or title of the SEO topic")
    description: str = Field(description="A brief description of what the topic covers")

class SEOTopics(BaseModel):
    topics: conlist(TopicPair, min_length=5, max_length=5) = Field(
        description="Exactly five SEO topics related to the given topic"
    )
