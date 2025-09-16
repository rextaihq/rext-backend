from langchain_core.prompts import ChatPromptTemplate


def topic_generation_prompt() -> ChatPromptTemplate:
    """
    Construct a LangChain ChatPromptTemplate for topic generation
    based on TopicGeneration input.
    """
    template = """
You are an AI assistant that generates high-quality, creative, and relevant content topic ideas.

### Context:
- Wizard Mode: {wizardMode}
- Industry: {industry}
- Industry (Other): {industry_other}
- subject: {subject}
- Audience: {audience}
- Purpose: {purpose}
- Purpose (Other): {purpose_other}
- Number of Topics Required: {num_topics}
- Timestamp: {timestamp}

### Task:
Generate {num_topics} creative and engaging topic ideas. 
For each topic, provide:
- **Title**: A catchy headline
- **Angle**: The specific perspective or unique approach
- **Description**: A short explanation of the topic
- **Channel Fit**: Best platforms/channels (e.g. blog, social media, newsletter)
- **Audience Fit**: Which audience segment will find this valuable
- **Why It Works**: Explain briefly why this idea would succeed
- **Tags**: Relevant categorization tags

Format the output as **JSON array** of objects with this structure:
[
  {{
    "title": "Example Title",
    "angle": "Unique angle",
    "description": "A comprehensive explanation of what this content will cover and why it's valuable",
    "channel_fit": ["blog", "social-media"],
    "audience_fit": ["developers", "tech enthusiasts"],
    "why_it_works": "Reason why this is a strong idea",
    "scores": {{
      "relevance": 0.95,
      "seo_potential": 0.88,
      "trend_level": 0.92,
      "uniqueness": 0.75,
      "reader_interest": 0.90,
      "actionable_potential": 0.95,
      "brand_alignment": 0.85,
      "controversy": 0.15
    }},
    "tags": ["AI", "Robotics", "Healthcare"]
  }}
]
"""
    return ChatPromptTemplate.from_template(template)