from langchain_core.prompts import PromptTemplate

title_prompt = PromptTemplate(
    input_variables=["keyword", "topic", "brand", "tone"],
    template="""
You are a Senior SEO Content Strategist. Your goal is to generate 5 distinct, high-CTR title tags for 2026.

### Constraints:
1. **Length:** 50-60 characters (perfect for Google display).
2. **Keyword:** Include "{keyword}" naturally.
3. **Format:** Each title must follow the format: [Compelling Title] | {brand}
4. **Variety Requirement:** Do not repeat the same structure. Provide 5 different angles:
   - **Angle 1 (Listicle):** Start with a number (e.g., 7 Best...).
   - **Angle 2 (Guide/How-to):** Focus on authority (e.g., Ultimate Guide to...).
   - **Angle 3 (Question/Benefit):** Solve a problem or ask a question.
   - **Angle 4 (Freshness):** Mention "2026" or "Latest".
   - **Angle 5 (Brand-First):** Focus on the brand's unique value proposition.

### Context:
- **Topic:** {topic}
- **Tone:** {tone}
- **Brand:** {brand}

### Output Instruction:
Return ONLY the 5 bullet points. No introductory text. No conversational filler.
"""
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
"""
)
