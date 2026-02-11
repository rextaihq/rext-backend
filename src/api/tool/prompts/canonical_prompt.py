from langchain_core.prompts import PromptTemplate

canonical_prompt = PromptTemplate(
    input_variables=["url"],
    template="""
You are an SEO expert.

Generate a valid HTML canonical tag for the given URL.

URL:
{url}

Rules:
- Use https
- Remove tracking parameters
- Normalize trailing slashes
- Prefer lowercase URLs
- Follow SEO best practices

Return ONLY the canonical tag.
Example:
<link rel="canonical" href="https://example.com/page" />
"""
)
