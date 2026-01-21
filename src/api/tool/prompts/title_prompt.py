from langchain_core.prompts import PromptTemplate

title_prompt = PromptTemplate(
    input_variables=["keyword", "topic", "brand", "tone"],
    template="""
You are an SEO expert.

Generate 5 SEO-optimized title tags.
Rules:
- Maximum 60 characters
- Must include the main keyword
- Tone: {tone}

Keyword: {keyword}
Topic: {topic}
Brand: {brand}

Return only bullet points.
"""
)
