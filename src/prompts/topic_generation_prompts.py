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
- Industry Specific Focus: {industry_specific_focus}
- Content Type: {content_type}
- Content Type (Other): {content_type_other}
- Platform: {platform}
- Platform (Other): {platform_other}
- Audience: {audience}
- Purpose: {purpose}
- Purpose (Other): {purpose_other}
- Tone: {tone}
- Tone (Other): {tone_other}
- Keywords: {keywords}
- Notes: {notes}
- Additional Notes: {additional_notes}
- Exclude: {exclude}
- Focus: {focus}
- Subject: {subject}
- Region: {region}
- Content Language: {language}
- Content Timing Preference: {content_timing_preference}
- Content Originality Preference: {content_originality_preference}
- Number of Ideas Required: {num_ideas}
- Timestamp: {timestamp}

### Task:
Generate {num_ideas} creative and engaging topic ideas. 
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
    "id": "topic_001",
    "title": "Example Title",
    "angle": "Unique angle",
    "description": "Optional description",
    "channel_fit": ["blog", "social-media"],
    "audience_fit": ["developers", "tech enthusiasts"],
    "why_it_works": "Reason why this is a strong idea",
    "scores": {{
      "relevance": 0.95,
      "freshness": 0.90,
      "novelty": 0.85
    }},
    "tags": ["AI", "Robotics", "Healthcare"],
    "is_saved": false
  }}
]
"""
    return ChatPromptTemplate.from_template(template)