from langchain_core.prompts import PromptTemplate

title_prompt = PromptTemplate(
    input_variables=["keyword", "topic", "brand", "tone"],
    template="""
You are a Senior SEO Content Strategist. Your goal is to generate distinct, high-CTR title tags for 2026.

### Constraints:
1. **Length:** Generate titles strictly between 50–60 characters inclusive. 60 is a strict maximum. Count every single character, space, and punctuation mark carefully. Never return a title under 50 or over 60 characters.
2. **Keyword:** Keep the primary keyword "{keyword}" natural and preferably near the beginning.
3. **Brand:** Include the brand name "{brand}" when provided.
4. **Format:** Each title must follow the format: [Compelling Title] | {brand} (or adapt naturally if brand is provided).
5. **Variety Requirement:** Do not repeat the same structure. Provide different angles (Listicle, Guide, Question/Benefit, Freshness 2026, Brand-First).

### Context:
- **Topic:** {topic}
- **Tone:** {tone}
- **Brand:** {brand}
- **Keyword:** {keyword}

### Output Instruction:
Generate 8 distinct candidate title tags, one per line. Every single title must be strictly between 50 and 60 characters inclusive counting all letters, spaces, and punctuation.
Return ONLY 8 bullet points, one per line. No introductory text. No conversational filler.
""",
)

idea_prompt = PromptTemplate(
    input_variables=["ideas_count", "topic", "content_type"],
    template="""
You are an expert Content Strategist and Creative Director. Your goal is to generate {ideas_count} high-performing, engaging, and unique content ideas for the topic: '{topic}' specifically tailored as a '{content_type}'.

Guidelines:
- Focus on viral potential and high audience engagement.
- Ensure ideas are practical, non-technical, and easy for humans to relate to.
- Mix different content styles (e.g., educational, storytelling, trend-based).
- Return a clear list of ideas matching the requested schema.
""",
)
